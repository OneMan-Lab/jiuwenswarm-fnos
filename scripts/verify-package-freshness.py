#!/usr/bin/env python3
"""校验 .fpk 内的关键脚本与工作区文件逐字节一致（防「改了代码但打进旧包」）。

为什么需要：
    0.2.9-8 出现过一次流程事故：多网卡版 supervisor.py 在工作区写好（17:24），
    但包在 17:06 就打完了，设备上跑的是旧文件，导致整整一轮排查指向错误方向。
    逻辑 review 抓不到这类问题，只有「包内 sha256 == 工作区 sha256」能抓到。

用法：
    python3 scripts/verify-package-freshness.py jiuwenswarm-0.2.9-9.fpk swarm-fnos-app

退出码：0 一致；1 有不一致（逐条打印）；2 参数错误。
"""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import tempfile
from pathlib import Path

# 参与比对的工作区相对路径（包内同名）
MONITORED = [
    "cmd/main",
    "cmd/install_callback",
    "cmd/upgrade_callback",
    "cmd/uninstall_callback",
    "cmd/install_init",
    "cmd/uninstall_init",
    "cmd/config_init",
    "cmd/config_callback",
    "cmd/upgrade_init",
    "app/ui/config",
    "app/server/init_env.sh",
    "app/server/runtime.sh",
    "app/server/supervisor.py",
    "app/server/uds_gateway.py",
    "app/server/detect_gateway_uid.py",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _norm_manifest(data: bytes) -> bytes:
    """fnpack 会重排 manifest（对齐等号、追加 checksum），因此按「键=值」归一化后比较。

    测试包/上架包只差 install_dep_apps 一行、以及 checksum，两者都剔除。
    """
    out = {}
    for line in data.decode("utf-8", "replace").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in ("checksum", "install_dep_apps"):
            continue
        out[key] = value.strip()
    return "\n".join(f"{k}={v}" for k, v in sorted(out.items())).encode()


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    fpk, appdir = Path(argv[1]), Path(argv[2])
    if not fpk.is_file():
        print(f"ERROR: 找不到 {fpk}", file=sys.stderr)
        return 1

    with tarfile.open(fpk) as outer:
        member = outer.extractfile("app.tgz")
        if member is None:
            print("ERROR: .fpk 内缺少 app.tgz", file=sys.stderr)
            return 1
        inner_bytes = member.read()
        top = {m.name: outer.extractfile(m).read() for m in outer if m.isfile() and m.name != "app.tgz"}
    with tarfile.open(fileobj=io.BytesIO(inner_bytes)) as inner:
        package = {m.name: inner.extractfile(m).read() for m in inner if m.isfile()}

    failures = 0
    targets = list(MONITORED)
    targets += [f"app/wheelhouse/{p.name}" for p in sorted((appdir / "app/wheelhouse").glob("*.whl"))]
    targets.append("manifest")

    for rel in targets:
        disk = appdir / rel
        if not disk.is_file():
            print(f"MISS  {rel}: 工作区不存在", file=sys.stderr)
            failures += 1
            continue
        if rel.startswith(("cmd/", "config/")) or rel == "manifest":
            pkg_data = top.get(rel)  # cmd/*、config/*、manifest 在 .fpk 顶层
        else:
            pkg_data = package.get(rel[4:] if rel.startswith("app/") else rel)
        if pkg_data is None:
            print(f"MISS  {rel}: 包内不存在（工作区有）", file=sys.stderr)
            failures += 1
            continue
        disk_data = disk.read_bytes()
        if rel == "manifest":
            same = _norm_manifest(pkg_data) == _norm_manifest(disk_data)
        else:
            same = sha(pkg_data) == sha(disk_data)
        if same:
            print(f"  OK   {rel}  sha256={sha(pkg_data)[:8]}…  ({len(pkg_data)} B)")
        else:
            failures += 1
            print(
                f"  FAIL {rel}: 包内 {sha(pkg_data)[:8]}…/{len(pkg_data)} B "
                f"!= 工作区 {sha(disk_data)[:8]}…/{len(disk_data)} B",
                file=sys.stderr,
            )

    # 反向检查：包内是否夹带了工作区已删/未跟踪的脚本（仅提示，不阻断）
    monitored_inner = {r[4:] if r.startswith("app/") else r for r in MONITORED}
    extra = [
        n
        for n in package
        if n.startswith(("server/", "cmd/"))
        and n not in monitored_inner
        and n.rsplit("/", 1)[-1].endswith((".sh", ".py"))
    ]
    if extra:
        print(f"[freshness] 提示：包内另有脚本 {sorted(extra)}")

    if failures:
        print(
            f"ERROR: {failures} 个文件与工作区不一致 —— 拒绝交付（很可能在构建后又改了代码，请重新构建）。",
            file=sys.stderr,
        )
        return 1
    print("[freshness] 结论：包内关键脚本与工作区逐字节一致")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
