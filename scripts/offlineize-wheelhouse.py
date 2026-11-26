#!/usr/bin/env python3
"""把 wheelhouse 里所有 wheel 的「直接 URL 依赖」（git+/https/file）改写为精确版本约束。

为什么必须做：
`workswarm` 的 METADATA 里，openjiuwen / openjiuwen-computeruse / openjiuwen-e2a /
agent-gateway 是 `name @ git+https://gitcode.com/...` 形式的直接 URL 依赖。pip 遇到这类
Requires-Dist 会**强制回源克隆**，即使 wheelhouse 里已有同名 wheel，`--no-index` 也拦不住。
结果就是「离线安装」实际仍要联网 —— 这与交付目标矛盾。

本脚本只改元数据（METADATA / RECORD），不动任何代码文件：
  Requires-Dist: openjiuwen @ git+https://gitcode.com/...  →  Requires-Dist: openjiuwen==0.1.21
版本号取自 wheelhouse 中实际构建出的 wheel。改写后用 RECORD 重算 sha256/size。

用法：python3 scripts/offlineize-wheelhouse.py app/wheelhouse
退出码：0 成功（可能 0 处改写）；1 有无法解析的直接 URL 依赖。
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

DIRECT_RE = re.compile(
    r"^(Requires-Dist:\s*)(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[^\]]*\])?\s*@\s*(?P<url>(?:git\+|https?://|file://)\S*)"
    r"(?P<tail>\s*;.*)?$"
)


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def version_key(v: str) -> tuple:
    parts = re.split(r"[.\-+]", v)
    out = []
    for p in parts:
        if p.isdigit():
            out.append((0, int(p)))
        elif p:
            out.append((1, p))
    return tuple(out)


def wheel_index(wh: Path) -> dict[str, list[tuple[str, Path]]]:
    index: dict[str, list[tuple[str, Path]]] = {}
    for wheel in wh.glob("*.whl"):
        parts = wheel.name[: -len(".whl")].split("-")
        if len(parts) < 5:
            continue
        index.setdefault(norm(parts[0]), []).append((parts[1], wheel))
    return index


def rewrite_metadata(text: str, index: dict[str, list[tuple[str, Path]]]) -> tuple[str, list[str], list[str]]:
    out: list[str] = []
    changes: list[str] = []
    unresolved: list[str] = []
    for line in text.splitlines():
        m = DIRECT_RE.match(line)
        if not m:
            out.append(line)
            continue
        name = m.group("name")
        key = norm(name)
        candidates = index.get(key)
        if not candidates:
            unresolved.append(line)
            out.append(line)
            continue
        version = sorted((v for v, _ in candidates), key=version_key)[-1]
        extras = m.group("extras") or ""
        tail = m.group("tail") or ""
        new_line = f"Requires-Dist: {name}{extras}=={version}{tail}"
        out.append(new_line)
        changes.append(f"{line}\n    -> {new_line}")
    return "\n".join(out) + "\n", changes, unresolved


def write_wheel(wheel: Path, replacements: dict[str, bytes]) -> None:
    tmp = wheel.with_suffix(".whl.tmp")
    records: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(wheel) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename.endswith(".dist-info/RECORD"):
                continue
            data = replacements.get(item.filename, src.read(item.filename))
            dst.writestr(item, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            records.append((item.filename, f"sha256={digest}", str(len(data))))
    record_name = next(
        (n for n in zipfile.ZipFile(tmp).namelist() if n.endswith(".dist-info/RECORD")), None
    )
    if record_name is None:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{wheel.name} 缺少 RECORD")
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerows(records)
    writer.writerow((record_name, "", ""))
    with zipfile.ZipFile(tmp, "a", zipfile.ZIP_DEFLATED) as dst:
        dst.writestr(record_name, buf.getvalue())
    shutil.move(str(tmp), str(wheel))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    wh = Path(argv[1])
    index = wheel_index(wh)
    total_changes = 0
    unresolved_all: list[str] = []

    for wheel in sorted(wh.glob("*.whl")):
        with zipfile.ZipFile(wheel) as zf:
            meta_name = next((n for n in zf.namelist() if n.endswith(".dist-info/METADATA")), None)
            if not meta_name:
                continue
            text = zf.read(meta_name).decode("utf-8")
        new_text, changes, unresolved = rewrite_metadata(text, index)
        if changes:
            write_wheel(wheel, {meta_name: new_text.encode("utf-8")})
            total_changes += len(changes)
            print(f"[offlineize] {wheel.name}: {len(changes)} 处")
            for c in changes:
                print("  " + c.replace("\n", "\n  "))
        unresolved_all.extend(f"{wheel.name}: {u}" for u in unresolved)

    print(f"完成：改写 {total_changes} 处直接 URL 依赖")
    if unresolved_all:
        print("无法解析（wheelhouse 缺同名 wheel）：", file=sys.stderr)
        for u in unresolved_all:
            print("  " + u, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
