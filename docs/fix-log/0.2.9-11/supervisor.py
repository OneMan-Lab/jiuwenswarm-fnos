#!/usr/bin/env python3
# app/server/supervisor.py —— 单一守护进程，管理 JiuwenSwarm 的三个子进程
#
#   supervisor（setsid，独立进程组）
#     ├─ python -m jiuwenswarm.app --keep-worker      → AgentServer 18092 + Gateway 19001
#     ├─ python -m ...channels.web.app_web            → 静态 dist + /api、/ws 反代（127.0.0.1:15173）
#     └─ python uds_gateway.py                        → ${TRIM_APPDEST}/app.sock（fnOS 网关入口）
#
# 为什么需要它：upstream 用 supervisor/MultiProcess 自己 fork，直接 TERM 父进程会留下孙进程
# 占着端口；这里以「进程组」为单位统一收口，stop 时整组退出（cmd/main 还会按 venv 路径兜底清扫）。

from __future__ import annotations

import ipaddress
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

VENV = os.environ.get("JW_VENV", "")
DATA = os.environ.get("JIUWENSWARM_DATA_DIR", "")
SERVER_DIR = os.environ.get("JW_SERVER_DIR", "")
LOG_DIR = os.environ.get("JW_LOGS", "")

STOP_TIMEOUT = int(os.environ.get("JW_STOP_TIMEOUT", "20"))
BACKOFF = float(os.environ.get("JW_CHILD_BACKOFF", "1.0"))

# --------------------------------------------------------------- 日志轮转 ----
# launcher.log 是 supervisor 与三个子进程共用的 stdout/stderr。上游组件即使只有
# INFO 级输出也会持续写（真机空载约 27 B/s ≈ 70 MB/月），必须自己兜住，
# 否则长期运行会把数据卷写满。
#
# 关键约束：子进程继承的是 cmd/main 用 `>>` 打开的 O_APPEND fd。因此**不能用
# rename 轮转**——rename 后子进程仍写旧 inode，新文件永远是空的。正确做法是
# 「把尾部拷到 .1，然后原地 truncate 原文件」：O_APPEND 让下一次写入落到新末尾
# （offset 0），fd 始终有效，也不会出现日志空窗。
LAUNCHER_LOG = os.environ.get("JW_LAUNCHER_LOG") or (
    str(Path(LOG_DIR) / "launcher.log") if LOG_DIR else ""
)
LOG_MAX_BYTES = int(os.environ.get("JW_LAUNCHER_MAX_BYTES", str(20 * 1024 * 1024)))
LOG_KEEP_BYTES = int(os.environ.get("JW_LAUNCHER_KEEP_BYTES", str(256 * 1024)))
LOG_CHECK_INTERVAL = float(os.environ.get("JW_LAUNCHER_CHECK_INTERVAL", "30"))

_shutdown = False


def log(msg: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [supervisor] {msg}", flush=True)


# ---------------------------------------------------- WS Origin 白名单 ----
# 上游 config/.env 默认开 JIUWENSWARM_ENABLE_ORIGIN_CHECK=1，白名单只有
# 127.0.0.1,localhost,none。经 fnOS 网关访问时浏览器 Origin 是
# http://<设备IP或域名>:5666，不在白名单 → /ws 握手被 403（页面能开、聊天一直断）。
# 这里在启动子进程前把本机所有可达地址 + 主机名并入白名单，用户自定义域名可写
# app.env 的 JW_WS_ALLOWED_ORIGIN_HOSTS（逗号分隔），一并合并。
_WS_HOSTS_ENV = "JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS"


def _collect_origin_hosts() -> str:
    hosts: set[str] = {"127.0.0.1", "localhost", "none"}
    for item in (os.environ.get(_WS_HOSTS_ENV) or "").split(","):
        item = item.strip()
        if item:
            hosts.add(item)
    for item in (os.environ.get("JW_WS_ALLOWED_ORIGIN_HOSTS") or "").split(","):
        item = item.strip()
        if item:
            hosts.add(item)
    # 上游 config/.env 里的值（load_dotenv 不覆盖已有环境变量，会丢失用户补充项）
    env_file = Path(DATA) / "config" / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(_WS_HOSTS_ENV + "="):
                for item in line.split("=", 1)[1].split(","):
                    item = item.strip()
                    if item:
                        hosts.add(item)
    except OSError:
        pass
    try:
        hosts.add(socket.gethostname())
        hosts.add(socket.getfqdn())
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            hosts.add(info[4][0])
    except OSError:
        pass
    # 关键：hostname 解析在多网卡设备上通常只返回一个地址（甚至 127.0.1.1），
    # 会漏掉用户实际访问的那块网卡。这里直接枚举所有网卡的 IPv4。
    hosts.update(_local_ipv4_addresses())
    return ",".join(sorted(h for h in hosts if h))


def _local_ipv4_addresses() -> set[str]:
    """枚举本机所有网卡的 IPv4（排除回环）。

    两条独立路径取并集，避免依赖单一工具：
    1) ioctl(SIOCGIFADDR) 逐接口取地址（纯标准库，不依赖外部命令）；
    2) 回退/补充 `ip -4 -o addr show`（iproute2，部分精简系统可能没有）。
    """
    ips: set[str] = set()
    try:
        import fcntl

        for _index, name in socket.if_nameindex():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                packed = fcntl.ioctl(
                    sock.fileno(), 0x8915, struct.pack("256s", name.encode()[:15])
                )
                ips.add(socket.inet_ntoa(packed[20:24]))
            except OSError:
                pass
            finally:
                sock.close()
    except (ImportError, OSError):
        pass
    try:
        out = subprocess.run(
            ["ip", "-4", "-o", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
        ips.update(re.findall(r"inet (\d+\.\d+\.\d+\.\d+)/", out))
    except (OSError, subprocess.SubprocessError):
        pass
    return {ip for ip in ips if ip and not ip.startswith("127.")}



def _ensure_env_allowlist() -> None:
    """把浏览器可见的本机地址并入 config/.env 的 WS Origin 白名单。

    为什么不能只设进程环境变量：上游启动时 `load_dotenv(..., override=True)`
    （dotenv_early.load_dotenv_runtime）会用 config/.env 覆盖继承来的 env，
    所以必须直接把值写进 .env，否则子进程仍读模板里的 127.0.0.1,localhost,none。
    只增不减：保留用户已有条目；文件不存在或未启用 origin check 时不动。
    """
    env_file = Path(DATA) / "config" / ".env"
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return
    merged = _collect_origin_hosts()
    if not merged:
        return
    lines = text.splitlines()
    found = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(_WS_HOSTS_ENV + "="):
            found = True
            existing = stripped.split("=", 1)[1]
            values = [v.strip() for v in existing.split(",") if v.strip()]
            for v in merged.split(","):
                if v not in values:
                    values.append(v)
            new_line = f"{_WS_HOSTS_ENV}={','.join(values)}"
            if new_line != line:
                lines[idx] = new_line
            break
    if not found:
        lines.append(f"{_WS_HOSTS_ENV}={merged}")
    new_text = "\n".join(lines) + "\n"
    if new_text == text:
        return
    try:
        tmp = env_file.with_name(".env.tmp")
        tmp.write_text(new_text, encoding="utf-8")
        try:
            os.chmod(tmp, env_file.stat().st_mode & 0o777)
        except OSError:
            pass
        os.replace(tmp, env_file)
        print(f"[supervisor] 已更新 {env_file.name} 的 {_WS_HOSTS_ENV}", flush=True)
    except OSError as exc:
        print(f"[supervisor] WARN: 更新 {env_file} 失败：{exc}", flush=True)


def _is_lan_ipv4(value: str) -> bool:
    """是否为非回环、非未指定的 IPv4 字面量（主机名返回 False）。"""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return addr.version == 4 and not (addr.is_loopback or addr.is_unspecified)


def _children() -> list[tuple[str, list[str]]]:
    python = str(Path(VENV) / "bin" / "python")
    return [
        ("app", [python, "-m", "jiuwenswarm.app", "--keep-worker"]),
        (
            "web",
            [
                python,
                "-m",
                "jiuwenswarm.channels.web.app_web",
                "--host",
                os.environ.get("FRONTEND_HOST", "127.0.0.1"),
                "--port",
                os.environ.get("FRONTEND_PORT", "15173"),
            ],
        ),
        ("gateway-bridge", [python, str(Path(SERVER_DIR) / "uds_gateway.py")]),
    ]


def _signal(signum, _frame) -> None:
    global _shutdown
    _shutdown = True
    log(f"received signal {signum}")


def _terminate(procs: dict[str, subprocess.Popen], grace: int) -> None:
    for name, proc in procs.items():
        if proc.poll() is None:
            log(f"TERM {name} pid={proc.pid}")
            try:
                proc.terminate()
            except OSError:
                pass
    deadline = time.time() + grace
    while time.time() < deadline:
        if all(p.poll() is not None for p in procs.values()):
            break
        time.sleep(0.2)
    for name, proc in procs.items():
        if proc.poll() is None:
            log(f"KILL {name} pid={proc.pid}")
            try:
                proc.kill()
            except OSError:
                pass
    for proc in procs.values():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _rotate_launcher_log() -> None:
    """超过阈值时把尾部若干字节留给 .1，然后原地清空 launcher.log。

    只保留 1 份备份（.1），总占用上限约 LOG_MAX_BYTES + LOG_KEEP_BYTES。
    """
    if not LAUNCHER_LOG:
        return
    path = Path(LAUNCHER_LOG)
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= LOG_MAX_BYTES:
        return
    try:
        with path.open("rb") as fh:
            fh.seek(max(0, size - LOG_KEEP_BYTES))
            tail = fh.read()
        # 从完整行开始，避免备份首行被截断
        cut = tail.find(b"\n")
        if 0 <= cut < len(tail) - 1:
            tail = tail[cut + 1 :]
        backup = path.with_name(path.name + ".1")
        backup.write_bytes(tail)
        with path.open("r+b") as fh:
            fh.truncate(0)
        log(
            f"rotated {path.name}: {size} B -> 0 B（尾部 {len(tail)} B 存入 {backup.name}）"
        )
    except OSError as exc:  # 轮转失败不能影响主服务
        log(f"WARN: 轮转 {path.name} 失败：{exc}")


def main() -> int:
    global _shutdown
    if not VENV or not DATA or not SERVER_DIR:
        print("missing JW_VENV / JIUWENSWARM_DATA_DIR / JW_SERVER_DIR", file=sys.stderr)
        return 1

    Path(DATA).mkdir(parents=True, exist_ok=True)
    if LOG_DIR:
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)

    # 独立进程组：cmd/main 的 kill -PGID 能一次收走全部子进程
    try:
        os.setsid()
    except OSError:
        pass

    signal.signal(signal.SIGTERM, _signal)
    signal.signal(signal.SIGINT, _signal)

    hosts = _collect_origin_hosts()
    if hosts:
        os.environ[_WS_HOSTS_ENV] = hosts
    # 断言：白名单里必须有「非回环 IPv4」。没有就说明地址收集又退化了
    # （0.2.9-8 就是 hostname→127.0.1.1，白名单只有回环，WS 必然 403）。
    lan = [h for h in hosts.split(",") if _is_lan_ipv4(h)]
    if lan:
        print(f"[supervisor] ws allowlist 含 LAN 地址：{','.join(lan)}", flush=True)
    else:
        print(
            "[supervisor] WARN ws allowlist 无 LAN 地址（仅回环/主机名），"
            "浏览器经设备 IP 访问时 WS 可能 403；"
            "可用 app.env 的 JW_WS_ALLOWED_ORIGIN_HOSTS 手工指定访问地址",
            flush=True,
        )
    _ensure_env_allowlist()

    procs: dict[str, subprocess.Popen] = {}
    os.chdir(DATA)
    # 上一次运行可能留下很大的日志，先兜一次再启动子进程
    _rotate_launcher_log()
    for name, argv in _children():
        log(f"starting {name}: {' '.join(argv)}")
        procs[name] = subprocess.Popen(argv, cwd=DATA, close_fds=True)

    exit_code = 0
    last_log_check = time.monotonic()
    while not _shutdown:
        for name, proc in list(procs.items()):
            code = proc.poll()
            if code is not None:
                log(f"{name} exited unexpectedly with code {code}")
                exit_code = 1 if code == 0 else (code or 1)
                _shutdown = True
                break
        now = time.monotonic()
        if now - last_log_check >= LOG_CHECK_INTERVAL:
            _rotate_launcher_log()
            last_log_check = now
        time.sleep(BACKOFF)

    _terminate(procs, STOP_TIMEOUT)
    log("stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
