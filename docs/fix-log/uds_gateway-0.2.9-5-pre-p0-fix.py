#!/usr/bin/env python3
# app/server/uds_gateway.py —— fnOS 统一网关的 UDS 入口桥（纯标准库）
#
#   fnOS 网关（校验 NAS 登录态、注入 X-Trim-*）
#        └─AF_UNIX─> ${TRIM_APPDEST}/app.sock   ← 本文件
#              └─TCP─> 127.0.0.1:${FRONTEND_PORT}（jiuwenswarm app_web）
#
# 职责只有两件事：
#   1) 门禁：只放行管理员（X-Trim-Isadmin: true）。上游 web 模式自身没有账号体系，
#      这一层是唯一可信的访问控制点（见交付说明「鉴权语义」）。
#   2) 前缀归一：把 /app/jiuwenswarm/xxx 改写为 /xxx。上游 app_web 只认根路径，
#      改写只动请求行；请求头与后续字节（含 WebSocket 帧）零改动地双向转发。
# 不解析响应、不解帧、不改 header 大小写，因此 WebSocket / SSE / 大文件流天然透明。
#
# 退出码：0 正常退出（SIGTERM/SIGINT），1 配置或监听失败。

from __future__ import annotations

import asyncio
import fnmatch
import os
import signal
import socket
import stat
import struct
import sys
from urllib.parse import unquote, urlsplit

SOCKET_PATH = os.environ.get("JW_SOCKET", "")
UPSTREAM_HOST = os.environ.get("FRONTEND_HOST", "127.0.0.1")
UPSTREAM_PORT = int(os.environ.get("FRONTEND_PORT", "15173"))
GATEWAY_PREFIX = (os.environ.get("JW_GATEWAY_PREFIX", "/app/jiuwenswarm") or "").rstrip("/")
REQUIRE_ADMIN = os.environ.get("JW_REQUIRE_ADMIN", "1") not in ("0", "false", "no")
SOCKET_MODE = int(os.environ.get("JW_SOCKET_MODE", "0666"), 8)
# 对端进程身份白名单（SO_PEERCRED）。默认只信任 root 发起的连接：
# fnOS 网关注入的 X-Trim-* 只有来自 root（网关）才可信；同机其它应用的普通用户
# 即使能连上 0666 的 socket，也无法凭自带 header 冒充管理员。
# 若真机确认网关以非 root 身份运行，把其 uid/gid 写入 ${TRIM_PKGVAR}/app.env：
#   JW_GATEWAY_UID=1234    或    JW_GATEWAY_GID=5678
# 注意：uid/gid 只写日志，**不参与判定**。不同 NAS 上网关 worker 的 uid 会变
# （现场实测为 101/712），硬编码必然在别的设备上翻车。判定只认 exe/comm 白名单。
# 仅本地调试用：放行任意本机对端（不安全，会失去 SO_PEERCRED 防护）
ALLOW_ANY_PEER = os.environ.get("JW_ALLOW_ANY_PEER", "0") in ("1", "true", "yes")

# 对端可执行文件/进程名白名单（glob）。校验在读取任何请求字节之前完成。
PEER_ALLOWLIST = [
    p.strip()
    for p in os.environ.get(
        "JW_GATEWAY_PEER_ALLOW",
        os.environ.get(
            "PEER_EXE_ALLOWLIST",
            "nginx,trim_http_cgi,trim_open_gateway,trim_*,trim-*,agent-gateway,agent_gateway",
        ),
    ).split(",")
    if p.strip()
]

MAX_HEAD = 64 * 1024
HEAD_TIMEOUT = 15.0
CONNECT_TIMEOUT = 10.0
CHUNK = 64 * 1024

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

FORBIDDEN_JSON = '{"code":"FORBIDDEN","msg":"JiuwenSwarm 仅允许 NAS 管理员使用"}'.encode("utf-8")
FORBIDDEN_HTML = (
    "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
    "<title>JiuwenSwarm</title></head><body style=\"font-family:system-ui,sans-serif;"
    "margin:3rem auto;max-width:34rem;line-height:1.8\">"
    "<h3>JiuwenSwarm 仅允许 NAS 管理员使用</h3>"
    "<p>JiuwenSwarm 可以读写工作区文件并执行命令，因此只对管理员开放。"
    "请让 NAS 管理员使用管理员账号登录后打开本应用。</p>"
    "</body></html>"
).encode("utf-8")

_stopping = False


def log(msg: str) -> None:
    print(f"[uds-gateway] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[uds-gateway] ERROR: {msg}", file=sys.stderr, flush=True)


def _headers(raw: bytes) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in raw.split(b"\r\n")[1:]:
        if not line or b":" not in line:
            continue
        name, _, value = line.partition(b":")
        out.append((name.decode("latin-1").strip(), value.decode("latin-1").strip()))
    return out


def _get(headers: list[tuple[str, str]], name: str) -> str:
    lowered = name.lower()
    for key, value in headers:
        if key.lower() == lowered:
            return value
    return ""


def _is_ws(headers: list[tuple[str, str]]) -> bool:
    return "websocket" in _get(headers, "upgrade").lower() and "upgrade" in _get(
        headers, "connection"
    ).lower()


def _rewrite_target(target: str) -> str | None:
    """归一化请求目标。命中网关前缀则剥离；否则原样透传（网关自行剥离时的形态）。

    只做字符串判断，不把路径拼进任何命令。含 `..` 的路径直接拒绝。
    """
    if target.startswith(("http://", "https://")):
        parts = urlsplit(target)
        target = parts.path + (("?" + parts.query) if parts.query else "")
    path, sep, query = target.partition("?")
    if any(seg == ".." for seg in path.replace("\\", "/").split("/")):
        return None
    if GATEWAY_PREFIX and path == GATEWAY_PREFIX:
        path = "/"
    elif GATEWAY_PREFIX and path.startswith(GATEWAY_PREFIX + "/"):
        path = path[len(GATEWAY_PREFIX):]
    if not path.startswith("/"):
        return None
    return path + (sep + query if sep else "")


def _build_head(method: str, target: str, headers: list[tuple[str, str]], ws: bool) -> bytes:
    tokens = {t.strip().lower() for t in _get(headers, "connection").split(",") if t.strip()}
    lines = [f"{method} {target} HTTP/1.1"]
    has_host = False
    for name, value in headers:
        low = name.lower()
        # 身份头不向上游透传：上游不需要，也不应看到可被误用的身份字段
        if low.startswith("x-trim-"):
            continue
        if low in ("x-forwarded-prefix", "x-forwarded-proto"):
            continue
        if low == "host":
            lines.append(f"Host: {UPSTREAM_HOST}:{UPSTREAM_PORT}")
            has_host = True
            continue
        if ws:
            if low in HOP_BY_HOP and low not in ("upgrade", "connection"):
                continue
        else:
            if low in HOP_BY_HOP or low in tokens:
                continue
        lines.append(f"{name}: {value}")
    if not has_host:
        lines.append(f"Host: {UPSTREAM_HOST}:{UPSTREAM_PORT}")
    if ws:
        # 保留 Upgrade/Connection 原值即可，WS 握手依赖它们
        pass
    else:
        # 一请求一连接，避免 keep-alive 下第二个请求绕过前缀改写
        lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1", "replace")


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await src.read(CHUNK)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (ConnectionError, asyncio.IncompleteReadError, OSError):
        pass
    finally:
        try:
            if dst.can_write_eof():
                dst.write_eof()
        except (OSError, RuntimeError):
            pass


def _forbidden(headers: list[tuple[str, str]]) -> bytes:
    accept = _get(headers, "accept").lower()
    if "text/html" in accept:
        body, ctype = FORBIDDEN_HTML, "text/html; charset=utf-8"
    else:
        body, ctype = FORBIDDEN_JSON, "application/json; charset=utf-8"
    head = (
        "HTTP/1.1 403 Forbidden\r\n"
        f"Content-Type: {ctype}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin-1")
    return head + body


def _peer_info(writer: asyncio.StreamWriter) -> dict:
    """取对端进程身份（Linux SO_PEERCRED，纯标准库）。

    失败时返回空 dict，由调用方按「不可信」处理（fail-closed）。
    """
    info: dict = {}
    try:
        sock = writer.get_extra_info("socket")
        raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", raw)
        info.update(pid=pid, uid=uid, gid=gid)
    except (OSError, AttributeError, struct.error):
        return info

    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            info["exe"] = os.path.basename(os.path.realpath(os.readlink(f"/proc/{pid}/exe")))
        except OSError:
            pass
        try:
            with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as fh:
                info["comm"] = fh.read().strip()
        except OSError:
            pass
    return info


def _peer_allowed(info: dict) -> tuple[bool, str]:
    """对端白名单判定。**任何请求字节读取之前**调用。

    这不是纵深防御的装饰：本应用唯一的鉴权就是「可信网关注入的 X-Trim-Isadmin」，
    而 X-Trim-* 头可以被任意本机进程伪造。只有确认对端是 fnOS 网关进程，
    这个头才可信 —— 后续维护者不得为「省事」放宽此判定。
    """
    if ALLOW_ANY_PEER:
        return True, "allow-any"
    # 主判定：exe 的 realpath basename（不可被 prctl 改名）；
    # comm 只在 exe 读取失败（EACCES 等）时兜底，且 comm 有 16 字符截断，只用 glob 匹配。
    exe = info.get("exe")
    comm = info.get("comm")
    if exe:
        for pattern in PEER_ALLOWLIST:
            if fnmatch.fnmatch(exe, pattern):
                return True, f"exe:{exe}"
        return False, "exe-not-allowlisted"
    if comm:
        for pattern in PEER_ALLOWLIST:
            if fnmatch.fnmatch(comm, pattern):
                return True, f"comm:{comm}"
        return False, "comm-not-allowlisted"
    return False, "no-exe-no-comm"


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        # === 第一道门：对端进程身份校验（早于任何请求字节读取；失败静默 close）===
        peer = _peer_info(writer)
        allowed, why = _peer_allowed(peer)
        if not allowed:
            log(
                "403 peer pid={pid} uid={uid} gid={gid} exe={exe} comm={comm} reason={why}".format(
                    pid=peer.get("pid", "?"),
                    uid=peer.get("uid", "?"),
                    gid=peer.get("gid", "?"),
                    exe=peer.get("exe", "?"),
                    comm=peer.get("comm", "?"),
                    why=why,
                )
            )
            return  # finally 中 close，不回任何响应

        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=HEAD_TIMEOUT)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            return
        if len(raw) > MAX_HEAD:
            return

        request_line = raw.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = request_line.split(" ")
        if len(parts) < 2:
            return
        method, target = parts[0].upper(), parts[1]
        headers = _headers(raw)

        uid = _get(headers, "x-trim-userid") or "-"
        is_admin = _get(headers, "x-trim-isadmin").strip().lower() == "true"
        ws = _is_ws(headers)

        if REQUIRE_ADMIN and not is_admin:
            writer.write(_forbidden(headers))
            await writer.drain()
            log(f"403 admin-required uid={uid} path={target.split('?', 1)[0][:120]}")
            return

        upstream_target = _rewrite_target(target)
        if upstream_target is None:
            writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
            await writer.drain()
            return

        try:
            up_reader, up_writer = await asyncio.wait_for(
                asyncio.open_connection(UPSTREAM_HOST, UPSTREAM_PORT), timeout=CONNECT_TIMEOUT
            )
        except (OSError, asyncio.TimeoutError) as exc:
            err(f"upstream {UPSTREAM_HOST}:{UPSTREAM_PORT} unavailable: {exc}")
            _body = "JiuwenSwarm 服务未就绪\n".encode("utf-8")
            writer.write(
                (
                    "HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain; charset=utf-8\r\n"
                    f"Content-Length: {len(_body)}\r\nConnection: close\r\n\r\n"
                ).encode("latin-1")
                + _body
            )
            await writer.drain()
            return

        up_writer.write(_build_head(method, upstream_target, headers, ws))
        await up_writer.drain()

        # 双向原始字节转发：请求体、WS 帧、分块响应都不做任何解释
        await asyncio.gather(
            _pipe(reader, up_writer),
            _pipe(up_reader, writer),
        )
        log(
            f"{'WS ' if ws else ''}{method} {upstream_target.split('?', 1)[0][:120]} "
            f"uid={uid} ok"
        )
    except (ConnectionError, OSError):
        pass
    except Exception as exc:  # noqa: BLE001 - 单连接异常不能拖垮桥
        err(f"connection failed: {type(exc).__name__}: {exc}")
    finally:
        try:
            writer.close()
        except OSError:
            pass


def _clear_stale(path: str) -> None:
    if os.path.exists(path) or os.path.islink(path):
        try:
            os.unlink(path)
        except OSError as exc:
            err(f"cannot remove stale socket {path}: {exc}")


async def _main() -> int:
    if not SOCKET_PATH:
        err("JW_SOCKET is required")
        return 1
    try:
        _clear_stale(SOCKET_PATH)
    except OSError as exc:
        err(f"bind {SOCKET_PATH} failed: {exc}")
        return 1

    server = await asyncio.start_unix_server(_handle, path=SOCKET_PATH, limit=MAX_HEAD)
    # 网关进程身份未知，socket 必须对该用户可读写；UDS 仅本机可达。
    # 注意：必须在 start_unix_server 之后再 chmod，否则会被 umask 覆盖。
    os.chmod(SOCKET_PATH, SOCKET_MODE)
    sock_dir = os.path.dirname(SOCKET_PATH)
    try:
        # 网关 worker 是非 root：父目录没有 o+x 就连 socket 都无法穿越（表现为 502）
        os.chmod(sock_dir, 0o755)
    except OSError as exc:
        log(f"WARN: chmod 0755 {sock_dir} failed: {exc}")
    try:
        dst = os.stat(sock_dir)
        log(
            f"socket dir {sock_dir} mode={oct(stat.S_IMODE(dst.st_mode))} "
            f"owner={dst.st_uid}:{dst.st_gid}"
        )
    except OSError as exc:
        log(f"WARN: stat socket dir failed: {exc}")
    try:
        st = os.stat(SOCKET_PATH)
        log(
            f"socket {SOCKET_PATH} mode={oct(stat.S_IMODE(st.st_mode))} "
            f"owner={st.st_uid}:{st.st_gid} peer_allow={PEER_ALLOWLIST}"
        )
    except OSError as exc:
        log(f"WARN: stat socket failed: {exc}")
    try:
        parent_mode = stat.S_IMODE(os.stat(os.path.dirname(SOCKET_PATH)).st_mode)
        if parent_mode & 0o002:
            log(
                f"WARN: socket 父目录 world-writable（mode={oct(parent_mode)}），"
                "任何本机用户都可连接该 socket；建议在设备侧收紧 target 目录权限"
            )
        else:
            log(f"parent dir mode={oct(parent_mode)}")
    except OSError as exc:
        log(f"WARN: 无法读取 socket 父目录权限：{exc}")
    log(
        f"listening prefix={GATEWAY_PREFIX or '(none)'} "
        f"upstream={UPSTREAM_HOST}:{UPSTREAM_PORT} require_admin={int(REQUIRE_ADMIN)}"
    )

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: stop_event.set())

    serve_task = asyncio.create_task(server.serve_forever())
    try:
        await stop_event.wait()
    finally:
        serve_task.cancel()
        server.close()
        try:
            await server.wait_closed()
        except (OSError, asyncio.CancelledError):
            pass
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            pass
        log("stopped")
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(asyncio.run(_main()))
