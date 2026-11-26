#!/usr/bin/env python3
"""尽力识别 fnOS 网关进程的 uid/gid，供 exe 不可读时的降级白名单使用。

跨用户读 /proc/<pid>/exe 受 ptrace 限制（EACCES），应用用户无法确认网关 worker 的真实
可执行文件，因此需要在安装时把网关信任域的 uid 记下来。

安全约束：只接受「父进程 uid == 0」且进程名匹配网关命名（nginx / trim_*）的进程。
普通用户无法让自己的进程拥有 root 父进程，因此不能污染这份白名单。

输出（无匹配则无输出）：
  uids=101,712
  gids=101,712
"""

from __future__ import annotations

import os
import re

NAME_PATTERNS = (re.compile(r"^nginx$"), re.compile(r"^trim[_-]"))
SKIP_SELF = os.getpid()


def read_status(pid: str) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                if key in ("Name", "Uid", "Gid", "PPid"):
                    data[key] = value.strip()
    except OSError:
        pass
    return data


def first_uid(value: str) -> int | None:
    parts = value.split()
    return int(parts[0]) if parts and parts[0].isdigit() else None


def main() -> int:
    uids: set[int] = set()
    gids: set[int] = set()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return 0

    for pid in pids:
        if int(pid) == SKIP_SELF:
            continue
        st = read_status(pid)
        name = st.get("Name", "")
        if not any(p.search(name) for p in NAME_PATTERNS):
            continue
        ppid = st.get("PPid", "")
        if not ppid.isdigit():
            continue
        parent = read_status(ppid)
        if first_uid(parent.get("Uid", "")) != 0:
            continue  # 父进程必须是 root（网关 master），防普通用户自建同名进程
        uid = first_uid(st.get("Uid", ""))
        gid = first_uid(st.get("Gid", ""))
        if uid is not None and uid != 0:
            uids.add(uid)
        if gid is not None:
            gids.add(gid)

    if uids:
        print("uids=" + ",".join(str(u) for u in sorted(uids)))
    if gids:
        print("gids=" + ",".join(str(g) for g in sorted(gids)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
