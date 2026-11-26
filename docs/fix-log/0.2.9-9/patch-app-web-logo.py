#!/usr/bin/env python3
"""把 workswarm 前端 dist 里的根路径 `/logo.svg` 改写为带网关前缀的路径。

为什么需要：
    fnOS 里页面挂在 `https://<设备>/app/jiuwenswarm/`（统一网关前缀）下，
    但上游 dist 里存在**根路径**引用（`Cne="/logo.svg"`、splash 兜底
    `image.src = '/logo.svg'`）。浏览器会把它解析成 `https://<设备>/logo.svg`，
    这个路径不在网关前缀内、没被反代到本应用，于是 404、品牌图空白。

    开发环境（app_web 直接监听根路径）不会暴露该问题，只有走前缀时才出现。

为什么改 wheel 而不是改上游源码：
    上游源码仓按约定只读（构建前后 `git status --porcelain` 必须为空）。
    这里对 app/wheelhouse 里已构建好的 workswarm wheel 做定点替换，
    并重算 RECORD 记录。

用法：
    python3 scripts/patch-app-web-logo.py app/wheelhouse
    python3 scripts/patch-app-web-logo.py app/wheelhouse --check   # 只校验不修改

退出码：
    0  已打好补丁（或 --check 下确认已无根路径引用）
    1  --check 下仍存在根路径引用 / wheel 结构变化导致定位失败
    2  参数错误
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import zipfile
from pathlib import Path

PREFIX = os.environ.get("JW_GATEWAY_PREFIX", "/app/jiuwenswarm").rstrip("/")

# 只匹配「引号 + /logo.svg + 引号」，已经带前缀的 ".../app/jiuwenswarm/logo.svg" 不会被误伤。
PATTERNS = [
    ('"/logo.svg"', f'"{PREFIX}/logo.svg"'),
    ("'/logo.svg'", f"'{PREFIX}/logo.svg'"),
]

TARGET_PARTS = ("/web/frontend/dist/index.html", "/web/frontend/dist/assets/")


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def _patch_text(text: str) -> tuple[str, int]:
    hits = 0
    for old, new in PATTERNS:
        hits += text.count(old)
        text = text.replace(old, new)
    return text, hits


def _patch_wheel(wheel: Path, check_only: bool) -> int:
    with zipfile.ZipFile(wheel) as zf:
        targets = [
            n
            for n in zf.namelist()
            if "/web/frontend/dist/" in n and (n.endswith(".js") or n.endswith(".html"))
        ]
        if not targets:
            print(f"ERROR: {wheel.name} 中找不到前端 dist 入口文件", file=sys.stderr)
            return 1

        replaced: dict[str, bytes] = {}
        remaining = 0
        hit_total = 0
        for name in targets:
            raw = zf.read(name)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            new_text, hits = _patch_text(text)
            if hits:
                hit_total += hits
                if check_only:
                    remaining += hits
                    print(f"[logo-patch] {name}: 仍有 {hits} 处根路径 /logo.svg", file=sys.stderr)
                else:
                    replaced[name] = new_text.encode("utf-8")
            elif any(old in text for old, _ in PATTERNS):
                remaining += 1

        if check_only:
            if remaining:
                print(f"ERROR: {wheel.name} 仍有根路径 /logo.svg 引用（{remaining} 处）", file=sys.stderr)
                return 1
            print(f"[logo-patch] {wheel.name} 已无根路径 /logo.svg 引用")
            return 0

        if not replaced:
            print(f"[logo-patch] {wheel.name} 已全部带前缀，跳过")
            return 0

        temp = wheel.with_suffix(wheel.suffix + ".tmp")
        record_name = next((n for n in zf.namelist() if n.endswith(".dist-info/RECORD")), None)
        record_lines = zf.read(record_name).decode("utf-8").splitlines() if record_name else []
        fixed_record = []
        for line in record_lines:
            parts = line.split(",")
            if len(parts) == 3 and parts[0] in replaced:
                fixed_record.append(_record_line(parts[0], replaced[parts[0]]))
            else:
                fixed_record.append(line)
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as out:
            for item in zf.infolist():
                if record_name and item.filename == record_name:
                    continue  # 统一在末尾写一份，避免重复条目
                out.writestr(item, replaced.get(item.filename) or zf.read(item.filename))
            if record_name:
                # 保持 RECORD 自身条目不写 hash 的惯例
                fixed_record = [l for l in fixed_record if not l.startswith(record_name + ",")]
                fixed_record.append(record_name + ",,")
                out.writestr(record_name, "\n".join(fixed_record) + "\n")
        temp.replace(wheel)
        print(f"[logo-patch] {wheel.name} 已改写 {len(replaced)} 个文件 / {hit_total} 处")
        return 0


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    check_only = "--check" in argv[1:]
    root = Path(args[0])
    wheels = sorted(list(root.glob("workswarm-*.whl")) + list(root.glob("jiuwenswarm-*.whl")))
    if not wheels:
        print(f"ERROR: {root} 下没有 workswarm-*.whl", file=sys.stderr)
        return 1
    rc = 0
    for wheel in wheels:
        rc |= _patch_wheel(wheel, check_only)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
