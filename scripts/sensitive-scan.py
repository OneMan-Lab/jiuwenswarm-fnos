#!/usr/bin/env python3
"""开源发布敏感信息门禁扫描器（strict / loose 双模）。

用途
----
把发布前审计规则固化成可执行门禁，避免"人肉判断哪些命中可接受"。

两种模式
--------
* ``--strict``（判据）  值型正则。命中且**未被白名单解释** → 退出码 1，供 CI / 推送前检查阻断。
* ``--loose``（报告）  宽泛关键词。始终退出码 0，只输出报告，并把每条命中对应的
                      白名单依据逐条打印（``命中 -> 依据``），便于离线 Review。

用法
----
    python3 sensitive-scan.py --strict  <目录>
    python3 sensitive-scan.py --loose   <目录>
    python3 sensitive-scan.py --self-test          # 把本文件自己作为输入跑 strict

自指要求
--------
本文件**不得**包含任何真实标识值（内网地址、真实域名/主机名、运行属主编号、
具体机型/内核/卷号、凭据）。扫描器自身泄漏与被扫描对象泄漏同等严重。
因此：所有敏感形态都用**结构化正则**表达（例如"3~4 位数字出现在 uid 赋值上下文"），
不写任何具体值；需要枚举的合法字样统一走白名单表。

退出码
------
0 = 通过（strict 无未解释命中；loose 永远 0）
1 = 阻断（strict 存在未解释命中，或参数错误）
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# 版本
# ---------------------------------------------------------------------------
VERSION = "1.0.0"

# 单文件扫描上限（防止误把大二进制/数据文件读进内存）
MAX_FILE_BYTES = 4 * 1024 * 1024
# 跳过的扩展名（二进制/构建产物）
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".icns", ".bmp",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".whl", ".fpk", ".so", ".dylib", ".dll", ".bin", ".pyc", ".pyo",
    ".pdf", ".mp4", ".mp3", ".woff", ".woff2", ".ttf", ".otf",
}

# ---------------------------------------------------------------------------
# 白名单：命中被这些规则解释即视为"合法"，逐条注明依据
# 依据编号对应审计文档的章节/条目（B2-7、B1-7 ...），便于追溯。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Whitelist:
    ident: str
    pattern: re.Pattern[str]
    basis: str

    def match(self, text: str) -> bool:
        return self.pattern.search(text) is not None


def _wl() -> list[Whitelist]:
    out: list[Whitelist] = []

    # 回环/通配地址：无标识性（审计 B3-4）
    out.append(Whitelist("loopback", re.compile(r"^(?:127\.0\.0\.1|localhost|0\.0\.0\.0)"), "B3-4 回环/通配，无标识性"))
    # 门户默认端口与应用内部端口常量（审计 B3-2 / B3-3）
    out.append(Whitelist("portal-port", re.compile(r"^566[67]$"), "B3-2 平台门户默认端口"))
    out.append(Whitelist("app-port", re.compile(r"^(?:15173|19000|19001)$"), "B3-3 应用内部端口常量"))
    # 平台/依赖/架构名（审计 B3-7）
    out.append(Whitelist("platform-name", re.compile(r"^(?:x86_64|x86|python312|manylinux\S*|cp312\S*)$"), "B3-7 平台与依赖名，必需"))
    # 示例域名：文档统一使用的示例值（审计 B3-5 / R8）
    out.append(Whitelist("example-domain", re.compile(r"^(?:nas\.example\.com|evil\.com|evil\.example\.net|[a-z]\)?\.?example\.(?:com|net))$"), "B3-5 示例值"))
    # DDNS 通配形式：只保留通配、不写具体前缀（审计 B1-7）
    out.append(Whitelist("ddns-wildcard", re.compile(r"^\*\.fnos\.net$|^\*\.fnos\.net"), "B1-7 通配形式，不得写具体前缀"))
    # uid/gid 作为"变量名/概念"出现（审计 B2-7）：不是具体值
    out.append(Whitelist(
        "uid-word",
        re.compile(r"^(?:uid|gid|uids|gids|JW_GATEWAY_UID|JW_GATEWAY_GID|TRIM_UID|TRIM_GID)$"),
        "B2-7 运行时变量名/键名，无实值",
    ))
    # a1 B2-8 明确授权保留的示例 uid/gid 取值（非真实）
    out.append(Whitelist("example-uid", re.compile(r"^(?:1234|5678)$"), "B2-8 上游源码注释中的示例值，a1 已裁定保留"))
    # 凭据类键名作为"概念词"出现（审计 B2-7）：值为空或只讲机制，不是凭据本身
    out.append(Whitelist(
        "token-word",
        re.compile(r"^(?:desktop_token|access_token|api_key|apikey)$"),
        "B2-7 凭据键名/概念词，本身不含值",
    ))
    # 卷号占位符写法（如 /vol{n} 或 <VOL>）
    out.append(Whitelist("vol-placeholder", re.compile(r"^(?:/vol\{n\}|<VOL>|\$TRIM_|/vol\d+/\$|<NAS_IP>|<HOME>|<USER>)$"), "占位符/框架变量"))
    # 平台规范示例的最低系统版本常量：公开规范值，非本机运行版本（审计 B3-6）
    # 注意：只放行这一个"规范示例值"；本机真实版本号仍在 C5 覆盖内。
    out.append(Whitelist("spec-min-version", re.compile(r"^1\.1\.3100$"), "B3-6 平台规范示例最低版本（公开常量），非本机版本"))
    return out


WHITELIST = _wl()

# ---------------------------------------------------------------------------
# 分类定义
#   strict：值型正则（命中即阻断，白名单可解释）
#   loose ：宽泛关键词（只报告，用于发现"可能需要人看"的地方）
# ---------------------------------------------------------------------------

# 私有 IPv4（RFC1918 三个网段）
_PRIVATE_V4 = re.compile(
    r"(?<![\w.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?![\w.])"
)
# 其它 IPv4（排除回环/未指定/私有段），用于发现公网或隧道地址
_OTHER_V4 = re.compile(
    r"(?<![\w.])(?!127\.|0\.0\.0\.0)(?!10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)(?:\d{1,3}\.){3}\d{1,3}(?![\w.])"
)


def _domain_suffix() -> str:
    """动态拼出 DDNS 域名后缀，避免脚本字面量里出现完整域名。"""
    return r"\." + "fn" + "os" + r"\." + "n" + "et"


_C3_STRICT = [
    # 具体前缀 + DDNS 后缀（通配形式由白名单解释）
    re.compile(r"(?<![\w*-])[a-z0-9][a-z0-9-]*" + _domain_suffix() + r"(?![\w])"),
    # mDNS / 私有后缀主机名
    re.compile(r"\b[a-z0-9][a-z0-9-]*\.local\b"),
    # 形如 <名字>-PC 的开发机主机名
    re.compile(r"\b[A-Za-z0-9][A-Za-z0-9-]*-PC\b"),
]
_C3_LOOSE = [
    re.compile(r"[a-z0-9-]+" + _domain_suffix()),
    re.compile(r"\b[a-z0-9-]+\.local\b"),
    re.compile(r"[A-Za-z0-9-]+-PC\b"),
]

_C4_STRICT = [
    # 家目录绝对路径（用户名即标识）
    re.compile(r"/home/(?!<|\$|\[)[A-Za-z0-9_.-]+"),
    # uid/gid 赋值上下文里出现 3~4 位数字（结构化判断，不写任何具体值）
    re.compile(r"\b(?:uid|gid)\s*[=:]\s*[1-9]\d{2,3}\b"),
    re.compile(r"\b(?:uid|gid)\s+(?:is\s+)?[1-9]\d{2,3}\b"),
    # 环境变量形态（a1 C4 的 `JW_GATEWAY_UID` 实值）：`XXX_UID=<3~4 位数字>`，大小写不敏感
    re.compile(r"\b(?:[A-Za-z0-9]+_)*(?:uid|gid)\s*[=:]\s*[1-9]\d{2,3}\b", re.IGNORECASE),
    # 卷内的用户目录路径（a1 §1.2 C4 的 `/vol<digits>/<digits>` 形态）：结构判断，不含具体值
    re.compile(r"/vol\d+/\d{2,4}(?![\w])"),
    # 独立用户名式家目录之外的常见私有根：/Users/<name>、C:\\Users\\<name>
    re.compile(r"/Users/(?!<|\$)[A-Za-z0-9_.-]+"),
    re.compile(r"[A-Za-z]:\\\\Users\\\\[A-Za-z0-9_.-]+"),
]
_C4_LOOSE = [
    re.compile(r"\buid\b"),
    re.compile(r"\bgid\b"),
    re.compile(r"/home/[^\s/]+"),
]

_C5_STRICT = [
    # 形如 d.d.dddd 的平台版本号
    re.compile(r"\b\d\.\d\.\d{4}\b"),
    # 带厂商后缀的内核版本（如 x.y.z-<suffix>）
    re.compile(r"\b\d+\.\d+\.\d+[\w.+-]*?-(?:trim|custom|generic|amd64)\b"),
    # 网卡设备名
    re.compile(r"\b(?:enp|eno|ens|eth|wlp|wlan)\d+s?\d*[a-z]?\b"),
    # 存储卷具体编号
    re.compile(r"\bvol[0-9]+\b"),
    # CPU 型号形态（厂商命名规则，不写具体型号）
    re.compile(r"\bi[3579]-\d{4,5}[A-Z]?\b"),
    # 命令行工具版本（工具名 + 精确版本）
    re.compile(r"\bfnos-cli\s+v?\d+\.\d+\.\d+\b"),
]
_C5_LOOSE = [
    re.compile(r"\d\.\d\.\d{4}"),
    re.compile(r"\b(?:enp|eno|ens|eth|wlp|wlan)\d+"),
    re.compile(r"\bvol[0-9]+\b"),
    re.compile(r"\bi[3579]-\d{4,5}"),
]

_C6_STRICT = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{12,}"),
    re.compile(r"\b(?:desktop_token|access_token|api_key|apikey|password|passwd)\s*=\s*[^\s\"']{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
_C6_LOOSE = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{4,}"),
    re.compile(r"\bdesktop_token\b"),
    re.compile(r"\bBearer\b"),
]

# 端口：**只认「主机:端口」组合**，不认裸数字。
# 原因：裸 `:数字` 在技术文档/源码里有大量合法同形物——代码行号（`x.py:527`）、
# 时间戳（`17:24`）、错误码（`{"code":10236}`）、切片/格式化（`raw[:4096]`）。
# 把它们判成泄漏会让门禁失去可用性（自指测试也必然失败）。
# 判定方式：冒号前必须是一个「像主机」的 token（域名形态 / IPv4 / 方括号 IPv6 / localhost），
# 且端口在 1..65535；主机 token 的顶级标签若是源码扩展名（.py/.sh/.md …）则不算主机。
_PORT = re.compile(r"(?<![?\[{]):(\d{1,5})(?![\w])")
_HOST_TOKEN = re.compile(r"([A-Za-z0-9_.<>\-]+|\[[0-9A-Fa-f:]+\])$")
_CODE_TLDS = {
    "py", "pyc", "sh", "bash", "md", "rst", "txt", "json", "json5", "yaml", "yml",
    "js", "mjs", "cjs", "ts", "tsx", "jsx", "html", "htm", "css", "scss", "vue",
    "c", "h", "cc", "cpp", "hpp", "go", "rs", "java", "rb", "php", "pl", "lua",
    "ini", "cfg", "conf", "toml", "lock", "log", "cgi", "whl", "fpk", "env",
    "svg", "png", "jpg", "gif", "sql", "diff", "patch", "bak", "tmp",
}


def _port_hit(line: str, m: re.Match[str]) -> bool:
    """判断一个 `:数字` 是否构成「主机:端口」组合。"""
    try:
        port = int(m.group(1))
    except ValueError:
        return False
    if not (1 <= port <= 65535):
        return False  # 越界数字不是端口（常见于"端口越界"反例），由其它类别处理
    host = _HOST_TOKEN.search(line[: m.start()])
    if host is None:
        return False
    token = host.group(1)
    if token in {"localhost"}:
        return True
    if token.startswith("[") and token.endswith("]"):
        return True  # 方括号 IPv6
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", token):
        return True  # IPv4
    if "." in token and not token.startswith("<"):
        tld = token.rsplit(".", 1)[-1].lower()
        if tld in _CODE_TLDS:
            return False  # 是文件名，不是主机
        if re.fullmatch(r"[A-Za-z]{2,}", tld):
            return True  # 域名形态
    return False


# 行级白名单：命中所在整行满足这些上下文时视为合法（用于"值本身不可判定、要靠上下文定性质"的场景）
LINE_WHITELIST: list[tuple[re.Pattern[str], str, set[str]]] = [
    (
        # 平台规范要求声明的最低版本常量（示例值），出现在 os_min_version 语境或规范引用处
        re.compile(r"os_min_version|\[advanced\s*§2\]"),
        "B3-6 平台规范要求声明的最低系统版本常量，非本机指纹",
        {"C5"},
    ),
    (
        # 公开分发的构建工具版本（fnpack）；替换它不影响任何技术结论
        re.compile(r"\bfnpack[-\s]?v?\d+\.\d+\.\d+"),
        "B3-7 构建工具公开版本号，与设备标识无关",
        {"C5"},
    ),
    (
        # 应用私有目录 @appdata/<app>/home/ 里的 home 段，不是用户家目录
        re.compile(r"@appdata/"),
        "B3-8 应用私有数据目录（appdata 下的 home），非用户家目录",
        {"C4"},
    ),
    (
        # 扫描器自身规则字面量（如 re.compile(r"/home/...")）
        # 故意拆开写：避免该行自身被扫描器自己的 loose 规则（/home/ 前缀）命中
        re.compile(r"re\.compile\(r?\"/ho" + r"me/"),
        "自引用：扫描器自身规则文本，非路径实例",
        {"C4"},
    ),
]


@dataclass
class Category:
    code: str
    name: str
    strict: list[re.Pattern[str]] = field(default_factory=list)
    loose: list[re.Pattern[str]] = field(default_factory=list)


CATEGORIES: list[Category] = [
    Category("C1", "内网 IPv4", [ _PRIVATE_V4 ], [ _PRIVATE_V4 ]),
    Category("C2", "其它 IPv4（公网/隧道）", [ _OTHER_V4 ], [ _OTHER_V4 ]),
    Category("C3", "域名 / 主机名", _C3_STRICT, _C3_LOOSE),
    Category("C4", "用户 / uid 实值", _C4_STRICT, _C4_LOOSE),
    Category("C5", "设备指纹", _C5_STRICT, _C5_LOOSE),
    Category("C6", "凭据", _C6_STRICT, _C6_LOOSE),
    Category("C7", "端口映射", [ _PORT ], [ _PORT ]),
]


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------


@dataclass
class Hit:
    path: str
    lineno: int
    category: Category
    text: str
    matched: str
    whitelist: Whitelist | None = None

    def render(self) -> str:
        base = f"{self.path}:{self.lineno}  [{self.category.code} {self.category.name}]  {self.text.strip()[:120]}"
        if self.whitelist is not None:
            base += f"   -> 依据: {self.whitelist.ident}（{self.whitelist.basis}）"
        return base


def _iter_files(root: str) -> Iterator[str]:
    if os.path.isfile(root):
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过版本库与缓存目录
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".mypy_cache", "node_modules"}]
        for name in sorted(filenames):
            suffix = os.path.splitext(name)[1].lower()
            if suffix in SKIP_SUFFIXES:
                continue
            yield os.path.join(dirpath, name)


def _read_text(path: str) -> str | None:
    try:
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            return None
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if b"\x00" in raw[:4096]:
        return None
    return raw.decode("utf-8", "replace")


def _explain(category: Category, matched: str, line: str) -> Whitelist | None:
    """判断某个命中能否被白名单解释；返回命中的白名单项。"""
    candidates: Iterable[str] = (matched,)
    if category.code == "C7":
        candidates = re.findall(r":(\d{2,5})(?![\w])", line) or (matched.lstrip(":"),)
    elif category.code == "C4":
        digits = re.findall(r"=(\d{2,4})\b", matched) or re.findall(r"\b(\d{2,4})$", matched)
        candidates = (matched, *digits)
    for value in candidates:
        for item in WHITELIST:
            if item.match(value):
                return item
    # 整行级别的白名单（例如通配域名、示例域名的上下文）
    for item in WHITELIST:
        if item.match(line.strip()):
            return item
    if re.search(r"\*\.fnos\.net", line) and category.code == "C3":
        for item in WHITELIST:
            if item.ident == "ddns-wildcard":
                return item
    # 行级白名单：值本身不可判定，靠上下文定性质
    for pattern, basis, codes in LINE_WHITELIST:
        if category.code in codes and pattern.search(line):
            return Whitelist("line-context", pattern, basis)
    return None


def scan(root: str, mode: str) -> tuple[list[Hit], int]:
    hits: list[Hit] = []
    files = 0
    for path in _iter_files(root):
        text = _read_text(path)
        if text is None:
            continue
        files += 1
        rel = os.path.relpath(path, root) if os.path.isdir(root) else path
        for lineno, line in enumerate(text.splitlines(), 1):
            for category in CATEGORIES:
                patterns = category.strict if mode == "strict" else category.loose
                for pattern in patterns:
                    for m in pattern.finditer(line):
                        matched = m.group(0)
                        if matched.strip() == "":
                            continue
                        if category.code == "C7" and not _port_hit(line, m):
                            continue  # 裸 `:数字`（行号/时间戳/错误码/切片）不是端口
                        hit = Hit(rel, lineno, category, line, matched)
                        hit.whitelist = _explain(category, matched, line) if mode == "strict" else _explain(category, matched, line)
                        if mode == "strict" and hit.whitelist is not None:
                            continue  # strict 中被白名单解释的命中不参与阻断
                        hits.append(hit)
    return hits, files


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def _report(root: str, mode: str, hits: list[Hit], files: int) -> int:
    title = "STRICT（值型，判据）" if mode == "strict" else "LOOSE（宽泛，仅报告）"
    print(f"== 敏感信息门禁：{title} ==")
    print(f"目标: {root}")
    print(f"扫描文件数: {files}")

    counts: dict[str, int] = {}
    explained = 0
    for hit in hits:
        counts[hit.category.code] = counts.get(hit.category.code, 0) + 1
        if hit.whitelist is not None:
            explained += 1

    for category in CATEGORIES:
        print(f"  {category.code} {category.name}: {counts.get(category.code, 0)}")

    if hits:
        print("\n-- 命中明细 --")
        for hit in hits:
            print("  " + hit.render())
        if mode == "loose":
            print(f"\n其中 {explained} 条已由白名单解释（见每行 \"依据\"），{len(hits) - explained} 条需人工确认。")

    if mode == "strict":
        blocking = [h for h in hits if h.whitelist is None]
        counts_block = len(blocking)
        print()
        print(f"结论: {'FAIL' if counts_block else 'PASS'}（未解释命中 {counts_block} 条）")
        return 1 if counts_block else 0

    # loose 永远不阻断
    print()
    print("结论: 仅报告，不阻断（loose 的命中不能直接当结论，需看依据或用 strict 复核）")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="开源发布敏感信息门禁扫描器（strict/loose）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument("--strict", action="store_true", help="值型判据模式（命中即退出码 1）")
    g.add_argument("--loose", action="store_true", help="宽泛报告模式（永不阻断）")
    g.add_argument("--self-test", action="store_true", help="把本脚本自身作为输入跑 strict")
    parser.add_argument("target", nargs="?", help="要扫描的目录或文件")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)

    mode = "loose" if args.loose else "strict"

    if args.self_test:
        target = os.path.abspath(__file__)
        hits, files = scan(target, "strict")
        code = _report(target, "strict", hits, files)
        print("（自指测试：本脚本必须不含任何真实标识）")
        return code

    if not args.target:
        parser.error("需要指定扫描目标目录（或用 --self-test）")
    target = args.target
    if not os.path.exists(target):
        print(f"error: 目标不存在: {target}", file=sys.stderr)
        return 1

    hits, files = scan(target, mode)
    return _report(target, mode, hits, files)


if __name__ == "__main__":
    sys.exit(main())
