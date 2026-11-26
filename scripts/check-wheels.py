#!/usr/bin/env python3
"""校验离线 wheel 集：架构/ABI 必须适配 x86_64 + CPython 3.12，并生成清单与 SHA256SUMS。

用法：python3 scripts/check-wheels.py app/wheelhouse
退出码：0 全部通过；1 存在不兼容 wheel 或缺关键包。
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

REQUIRED = {"workswarm", "pip"}
X86_PLAT = re.compile(r"^(manylinux\S*_x86_64|linux_x86_64|any)$")
BAD_PLAT = ("aarch64", "arm64", "armv7l", "musllinux", "win32", "win_amd64", "macosx", "i686")
CP_RE = re.compile(r"^cp3(\d+)$")


def parse(name: str) -> tuple[str, str, list[str], list[str], list[str]]:
    parts = name[: -len(".whl")].split("-")
    if len(parts) < 5:
        raise ValueError(f"wheel 文件名不符合规范：{name}")
    return parts[0], parts[1], parts[-3].split("."), parts[-2].split("."), parts[-1].split(".")


def check_one(name: str) -> list[str]:
    _dist, _version, py, abi, plat = parse(name)
    problems: list[str] = []
    for p in plat:
        if any(bad in p for bad in BAD_PLAT):
            problems.append(f"平台 {p} 与目标设备 x86_64 不兼容")
        elif not X86_PLAT.match(p):
            problems.append(f"平台 {p} 未确认是 manylinux x86_64/any")

    pure = "py3" in py and "none" in abi and "any" in plat
    if not pure:
        ok_py = any(CP_RE.match(t) and int(CP_RE.match(t).group(1)) <= 12 for t in py)
        ok_py = ok_py or any(t.startswith("py3") for t in py)
        for tag in py:
            m = CP_RE.match(tag)
            if m and int(m.group(1)) > 12:
                problems.append(f"Python 标签 {tag} 高于 cp312")
        if not ok_py:
            problems.append(f"Python/ABI 标签 {py}/{abi} 不匹配 cp312")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    wh = Path(argv[1])
    wheels = sorted(wh.glob("*.whl"))
    if not wheels:
        print(f"ERROR: {wh} 中没有 wheel", file=sys.stderr)
        return 1

    bad: list[str] = []
    names: set[str] = set()
    lines: list[str] = []
    for wheel in wheels:
        try:
            dist, version, _py, _abi, _plat = parse(wheel.name)
        except ValueError as exc:
            bad.append(str(exc))
            continue
        names.add(dist)
        problems = check_one(wheel.name)
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        lines.append(f"{wheel.name}\t{version}\t{digest}")
        if problems:
            bad.append(f"{wheel.name}: {'; '.join(problems)}")

    missing = REQUIRED - names
    if missing:
        bad.append(f"缺少必需的 wheel: {sorted(missing)}")

    (wh / "WHEELS.txt").write_text(
        "wheel\tversion\tsha256\n" + "\n".join(lines) + "\n", encoding="utf-8"
    )
    (wh / "SHA256SUMS").write_text(
        "\n".join(f"{line.split(chr(9))[2]}  {line.split(chr(9))[0]}" for line in lines) + "\n",
        encoding="utf-8",
    )

    print(f"wheel 总数 {len(wheels)}，清单：{wh / 'WHEELS.txt'}")
    if bad:
        print("发现不兼容项：", file=sys.stderr)
        for item in bad:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("架构/ABI 校验通过（x86_64 + cp312 / 纯 py）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
