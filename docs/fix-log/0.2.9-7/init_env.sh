#!/bin/bash
# app/server/init_env.sh —— 统一环境变量（由 cmd/* 以 `.` 方式引入，不单独执行）
#
# 只使用框架提供的 TRIM_* 变量定位路径，绝不硬编码 /var/apps/...。
# 约定：
#   TRIM_APPDEST → target（应用文件，升级会被替换）
#   TRIM_PKGVAR  → var（运行数据，跨升级保留）
#   TRIM_PKGHOME → home（应用用户数据）
#   TRIM_PKGTMP  → tmp（临时文件，可清空）
# 所有可写数据都落在这四个目录内，保证卸载不残留数据卷外的文件。

: "${TRIM_APPDEST:?TRIM_APPDEST is required}"
: "${TRIM_PKGVAR:?TRIM_PKGVAR is required}"
: "${TRIM_PKGHOME:?TRIM_PKGHOME is required}"
: "${TRIM_PKGTMP:?TRIM_PKGTMP is required}"

# ---------------------------------------------------------------- 运行时 ----
# Python 3.12 运行时：**不通过 install_dep_apps 声明**（CLI 安全闸会拦截带依赖的包），
# 改为「文档前置依赖 + 运行时探测」。候选顺序：python312 应用 → PATH 上的 python3.12 → python3。
PYTHON_RUNTIME_BIN="/var/apps/python312/target/bin"
_jw_py_ok() {
  [ -n "${1:-}" ] || return 1
  [ -x "${1}" ] || return 1
  "${1}" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1
}
PYTHON3=""
for _jw_cand in "${PYTHON_RUNTIME_BIN}/python3" "${PYTHON_RUNTIME_BIN}/python3.12"                  "$(command -v python3.12 2>/dev/null || true)"                  "$(command -v python3 2>/dev/null || true)"; do
  if _jw_py_ok "${_jw_cand}"; then
    PYTHON3="${_jw_cand}"
    break
  fi
done
if [ -n "${PYTHON3}" ]; then
  export PATH="$(dirname "${PYTHON3}"):$PATH"
  export PYTHON3
else
  export PYTHON3=""
  echo "[jiuwenswarm] WARN: 未找到 Python 3.12 运行时；请先在应用中心安装 python312" >&2
fi
unset _jw_cand

# ------------------------------------------------------------ 应用布局 ----
export JW_VENV="${TRIM_PKGVAR}/venv"
export JW_DATA="${TRIM_PKGVAR}/data"
export JW_LOGS="${TRIM_PKGVAR}/logs"
export JW_RUN="${TRIM_PKGVAR}/run"
export JW_PID_FILE="${JW_RUN}/supervisor.pid"
export JW_LAUNCHER_LOG="${JW_LOGS}/launcher.log"
export JW_WHEELHOUSE="${TRIM_APPDEST}/wheelhouse"
export JW_SERVER_DIR="${TRIM_APPDEST}/server"
export JW_SOCKET="${TRIM_APPDEST}/app.sock"

# 用户主目录重定向到应用 home，避免污染系统用户目录 / 写入不可写位置。
export HOME="${TRIM_PKGHOME}"
export JIUWENSWARM_HOME="${TRIM_PKGHOME}"

# 唯一需要设置的数据根变量：profile / config / logs / run 全部由它派生。
export JIUWENSWARM_DATA_DIR="${JW_DATA}"

# Python 临时文件与字节码缓存都收进应用自己的目录，避免落到 /tmp 或 target。
export TMPDIR="${TRIM_PKGTMP}"
export PYTHONPYCACHEPREFIX="${TRIM_PKGVAR}/pycache"

# ------------------------------------------------------------ 端口规划 ----
# 全部只监听 127.0.0.1：对外唯一入口是 fnOS 网关 → ${JW_SOCKET}。
# 用 JW_ 前缀保存本应用自己的端口，避免继承宿主/其它应用导出的 FRONTEND_PORT 等同名变量
# （构建/调试环境里这些变量很常见，继承会导致端口漂移）。
export JW_FRONTEND_PORT="${JW_FRONTEND_PORT:-15173}"
export JW_WEB_PORT="${JW_WEB_PORT:-19000}"
export JW_GATEWAY_PORT="${JW_GATEWAY_PORT:-19001}"
export JW_AGENT_SERVER_PORT="${JW_AGENT_SERVER_PORT:-18092}"
export FRONTEND_HOST="127.0.0.1"
export FRONTEND_PORT="${JW_FRONTEND_PORT}"
export WEB_HOST="127.0.0.1"
export WEB_PORT="${JW_WEB_PORT}"
export GATEWAY_HOST="127.0.0.1"
export GATEWAY_PORT="${JW_GATEWAY_PORT}"
export AGENT_SERVER_HOST="127.0.0.1"
export AGENT_SERVER_PORT="${JW_AGENT_SERVER_PORT}"
export AGENT_PORT="${JW_AGENT_SERVER_PORT}"

# 个人版走 WebSocket；企业版分支需要额外后端，不启用。
export WEB_TRANSPORT="websocket"

# ------------------------------------------------------------ 网关门禁 ----
# 网关前缀：前端构建时已把静态资源 / API / WS 全部锚定在这一前缀下。
export JW_GATEWAY_PREFIX="${JW_GATEWAY_PREFIX:-/app/jiuwenswarm}"
# 仅允许 NAS 管理员使用：JiuwenSwarm 可读写工作区文件、执行命令，且自身无账号体系，
# 因此必须依赖网关注入的 X-Trim-Isadmin 作为唯一门槛。
export JW_REQUIRE_ADMIN="${JW_REQUIRE_ADMIN:-1}"
# 对端进程白名单（SO_PEERCRED + /proc/<pid>/exe|comm）：默认只信任 fnOS 网关进程。
# 真机若被误拒，日志会出现 `403 peer ... comm=... exe=...`，把实际名字加进这里即可
# （写入 ${TRIM_PKGVAR}/app.env，然后 cmd/main stop && start，无需重打包）。
export JW_GATEWAY_PEER_ALLOW="${JW_GATEWAY_PEER_ALLOW:-/usr/sbin/nginx,/usr/sbin/trim_http_cgi,/usr/sbin/trim_open_gateway,/usr/sbin/trim_*,/usr/bin/nginx,/usr/bin/trim_*,/usr/local/sbin/trim_*,/usr/local/bin/trim_*}"
# socket 第二道防线：0600=网关与 app 同 uid；0660=不同 uid 但同组；0666=过渡态。
# 默认 0666 以便网关身份未知时先跑通（鉴权由 peer 白名单保证），t3 确认后应收紧。
export JW_SOCKET_MODE="${JW_SOCKET_MODE:-0666}"

# 可选：用户自定义覆盖（**纯解析，不 source**）。
# source 等于执行任意 shell；这里只按白名单键 + 字符集校验解析 `KEY=VALUE`，
# 未知键/非法行一律忽略并 WARN，不中断启动。
JW_APP_ENV="${TRIM_PKGVAR}/app.env"
if [ -f "${JW_APP_ENV}" ]; then
  _jw_env_ok=1
  _jw_env_why=""
  # 属主必须是 root 或当前用户：root 属主来自「生命周期脚本以 root 执行」的安装路径，
  # 内容仍由安装脚本生成；当前用户属主是 chown 成功后的常态。
  _jw_owner="$(stat -c '%u' "${JW_APP_ENV}" 2>/dev/null || true)"
  _jw_self="$(id -u 2>/dev/null || echo '?')"
  if [ "${_jw_owner}" != "0" ] && [ "${_jw_owner}" != "${_jw_self}" ]; then
    _jw_env_ok=0
    _jw_env_why="属主 uid=${_jw_owner} 不是 root 或当前用户（${_jw_self}）"
  fi
  _jw_mode="$(stat -c '%a' "${JW_APP_ENV}" 2>/dev/null || true)"
  if [ -z "${_jw_mode}" ]; then
    _jw_env_ok=0
    _jw_env_why="${_jw_env_why:-无法读取权限位}"
  else
    _jw_g="${_jw_mode: -2:1}"
    _jw_o="${_jw_mode: -1}"
    case "${_jw_g}" in 2|3|6|7) _jw_env_ok=0; _jw_env_why="${_jw_env_why:-group 可写（mode=${_jw_mode}）}" ;; esac
    case "${_jw_o}" in 2|3|6|7) _jw_env_ok=0; _jw_env_why="${_jw_env_why:-other 可写（mode=${_jw_mode}）}" ;; esac
  fi
  if [ "${_jw_env_ok}" != "1" ]; then
    echo "[jiuwenswarm] WARN: 忽略 ${JW_APP_ENV}：${_jw_env_why}；要求属主为 root 或本应用用户且 group/other 不可写（建议 chown 应用用户 + chmod 600）" >&2
  else
    _jw_loaded=""
    while IFS= read -r _jw_line || [ -n "${_jw_line}" ]; do
      case "${_jw_line}" in ''|'#'*) continue ;; esac
      if ! printf '%s' "${_jw_line}" | grep -Eq '^[A-Z_][A-Z0-9_]*=.+$'; then
        echo "[jiuwenswarm] WARN: app.env 忽略非法行：${_jw_line}" >&2
        continue
      fi
      _jw_key="${_jw_line%%=*}"
      _jw_val="${_jw_line#*=}"
      case "${_jw_key}" in
        JW_GATEWAY_PEER_ALLOW)
          if printf '%s' "${_jw_val}" | grep -Eq '^[A-Za-z0-9_./*,:-]+$'; then
            export JW_GATEWAY_PEER_ALLOW="${_jw_val}"
            _jw_loaded="${_jw_loaded} JW_GATEWAY_PEER_ALLOW"
          else
            echo "[jiuwenswarm] WARN: app.env 中 ${_jw_key} 含非法字符，已忽略" >&2
          fi
          ;;
        JW_SOCKET_MODE)
          if printf '%s' "${_jw_val}" | grep -Eq '^0?[0-7]{3}$'; then
            export JW_SOCKET_MODE="${_jw_val}"
            _jw_loaded="${_jw_loaded} JW_SOCKET_MODE"
          else
            echo "[jiuwenswarm] WARN: app.env 中 ${_jw_key} 必须是八进制权限（如 0660）" >&2
          fi
          ;;
        JW_REQUIRE_ADMIN)
          case "${_jw_val}" in 0|1|true|false|yes|no)
            export JW_REQUIRE_ADMIN="${_jw_val}"
            _jw_loaded="${_jw_loaded} JW_REQUIRE_ADMIN"
            ;;
            *) echo "[jiuwenswarm] WARN: app.env 中 ${_jw_key} 取值非法，已忽略" >&2 ;;
          esac
          ;;
        JW_GATEWAY_UID|JW_GATEWAY_GID)
          if printf '%s' "${_jw_val}" | grep -Eq '^[0-9]{1,7}(,[0-9]{1,7})*$'; then
            export "${_jw_key}=${_jw_val}"
            _jw_loaded="${_jw_loaded} ${_jw_key}"
          else
            echo "[jiuwenswarm] WARN: app.env 中 ${_jw_key} 必须是数字" >&2
          fi
          ;;
        JW_FRONTEND_PORT|JW_WEB_PORT|JW_GATEWAY_PORT|JW_AGENT_SERVER_PORT)
          if printf '%s' "${_jw_val}" | grep -Eq '^[0-9]{2,5}$'; then
            export "${_jw_key}=${_jw_val}"
            _jw_loaded="${_jw_loaded} ${_jw_key}"
          else
            echo "[jiuwenswarm] WARN: app.env 中 ${_jw_key} 必须是端口号" >&2
          fi
          ;;
        *)
          echo "[jiuwenswarm] WARN: app.env 忽略未授权键 ${_jw_key}" >&2
          ;;
      esac
    done <"${JW_APP_ENV}"
    # 正向日志：真机读不到文件内容时，这一行就是「白名单是否生效」的唯一证据。
    echo "[jiuwenswarm] app.env 已加载（owner=${_jw_owner} mode=${_jw_mode}）：JW_GATEWAY_UID=${JW_GATEWAY_UID:-<未设>} JW_GATEWAY_GID=${JW_GATEWAY_GID:-<未设>} peer_allow=${JW_GATEWAY_PEER_ALLOW}" >&2
  fi
  unset _jw_env_ok _jw_env_why _jw_owner _jw_self _jw_mode _jw_g _jw_o _jw_line _jw_key _jw_val
  unset _jw_loaded
else
  echo "[jiuwenswarm] app.env 未加载（${JW_APP_ENV} 不存在；使用默认值 peer_allow=${JW_GATEWAY_PEER_ALLOW} JW_REQUIRE_ADMIN=${JW_REQUIRE_ADMIN}）" >&2
fi

# 清理可能残留的跨实例地址，避免子进程被指向别的服务。
unset GATEWAY_URL AGENT_SERVER_URL 2>/dev/null || true
