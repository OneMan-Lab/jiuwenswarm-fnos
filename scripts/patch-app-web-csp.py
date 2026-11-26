#!/usr/bin/env python3
"""把 workswarm wheel 里的 CSP `frame-ancestors 'none'` 改成 `'self'`。

为什么需要：
    fnOS 门户（http://<设备>:5666）用 iframe 嵌入 /app/jiuwenswarm，两者同源。
    上游 app_web.py 给顶层文档发 `Content-Security-Policy: frame-ancestors 'none'`，
    浏览器会直接拒载 iframe（白屏），控制台报
    `Framing 'http://<设备>:5666/' violates ... "frame-ancestors 'none'"`。
    `'self'` 只允许同源页面嵌入，既恢复门户访问又不放宽到任意站点。

为什么改 wheel 而不是改上游源码：
    上游源码仓按约定只读（构建前后 `git status --porcelain` 必须为空）。
    这里对 app/wheelhouse 里已构建好的 workswarm wheel 做定点替换，
    并重算该文件的 RECORD 记录，保证 pip 安装时记录一致。

用法：
    python3 scripts/patch-app-web-csp.py app/wheelhouse
    python3 scripts/patch-app-web-csp.py app/wheelhouse --check   # 只校验不修改

幂等：已经是 'self' 时直接返回 0。

退出码（CI 语义）：
    0  已打好补丁（或 --check 下确认已是 'self'）
    1  需要打补丁但未打（--check），或上游已改动导致补丁无法定位
    2  参数错误

CI 用法（build 之后、打包之前）：
    python3 scripts/patch-app-web-csp.py app/wheelhouse          # 幂等打补丁
    python3 scripts/patch-app-web-csp.py app/wheelhouse --check  # 断言已生效，否则退出 1
`scripts/build-fpk.sh` 已内置这两步作为构建闸门。
"""

from __future__ import annotations

import base64
import hashlib
import sys
import tempfile
import zipfile
from pathlib import Path

TARGET = "jiuwenswarm/channels/web/app_web.py"
OLD = '_TOP_LEVEL_DOCUMENT_CSP = "frame-ancestors \'none\'"'
NEW = '_TOP_LEVEL_DOCUMENT_CSP = "frame-ancestors \'self\'"'


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def _patch_wheel(wheel: Path, check_only: bool) -> int:
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        if TARGET not in names:
            print(f"ERROR: {wheel.name} 中缺少 {TARGET}", file=sys.stderr)
            return 1
        source = zf.read(TARGET).decode("utf-8")
        if NEW in source and OLD not in source:
            print(f"[csp-patch] {wheel.name} 已是 frame-ancestors 'self'，跳过")
            return 0
        count = source.count(OLD)
        if count != 1:
            detail = (
                "目标常量不存在（上游可能已改名/删除，或改用其它 CSP 写法）"
                if count == 0
                else f"目标常量出现 {count} 次（期望 1）"
            )
            print(
                f"ERROR: {wheel.name}: {detail}；"
                f"请打开 {TARGET} 核对 `_TOP_LEVEL_DOCUMENT_CSP` 后更新本脚本，"
                "不要跳过——跳过会打出一个门户 iframe 白屏的包",
                file=sys.stderr,
            )
            return 1
        patched = source.replace(OLD, NEW).encode("utf-8")

        record_name = next(
            n for n in names if n.endswith(".dist-info/RECORD") and n.startswith("workswarm-")
        )
        record = zf.read(record_name).decode("utf-8").splitlines()
        new_record = [
            _record_line(TARGET, patched) if line.split(",")[0] == TARGET else line
            for line in record
        ]
        if not any(line.split(",")[0] == TARGET for line in record):
            print(f"ERROR: {record_name} 中没有 {TARGET} 条目", file=sys.stderr)
            return 1
        record_bytes = ("\n".join(new_record) + "\n").encode("utf-8")

        if check_only:
            print(f"[csp-patch] CHECK: {wheel.name} 需要打补丁（当前 'none'）")
            return 1

        tmp = Path(tempfile.mkstemp(suffix=".whl", dir=str(wheel.parent))[1])
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
                for info in zf.infolist():
                    data = zf.read(info)
                    if info.filename == TARGET:
                        data = patched
                    elif info.filename == record_name:
                        data = record_bytes
                    out.writestr(info, data)
            tmp.replace(wheel)
        finally:
            tmp.unlink(missing_ok=True)

    # 回读确认
    with zipfile.ZipFile(wheel) as zf:
        after = zf.read(TARGET).decode("utf-8")
    assert NEW in after and OLD not in after, "补丁回读校验失败"
    print(f"[csp-patch] {wheel.name} 已改为 frame-ancestors 'self'")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    wheelhouse = Path(argv[1])
    check_only = "--check" in argv[2:]
    wheels = sorted(wheelhouse.glob("workswarm-*.whl"))
    if not wheels:
        print(f"ERROR: {wheelhouse} 中没有 workswarm-*.whl", file=sys.stderr)
        return 1
    rc = 0
    for wheel in wheels:
        rc |= _patch_wheel(wheel, check_only)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
