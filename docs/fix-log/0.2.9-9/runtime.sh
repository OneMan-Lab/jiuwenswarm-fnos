#!/bin/bash
# app/server/runtime.sh —— 运行时（venv）安装与数据目录准备
# 由 cmd/install_callback、cmd/upgrade_callback 引入；依赖 init_env.sh 已先行加载。

JW_VERSION_FILE="${JW_SERVER_DIR}/VERSION"

jw_log() { echo "[jiuwenswarm] $*"; }

jw_fail() {
  jw_log "ERROR: $*"
  if [ -n "${TRIM_TEMP_LOGFILE:-}" ]; then
    printf '%s\n' "$*" >"${TRIM_TEMP_LOGFILE}"
  fi
  return 1
}

jw_pip_version() {
  # VERSION 里写的是 pip 可识别的规范化版本（例如 0.2.9b5）
  tr -d '[:space:]' <"${JW_VERSION_FILE}"
}

# ---- 运行时指纹 -----------------------------------------------------------
# 只看版本号不够：同一个上游版本（0.2.9b5）可能因为本项目的补丁（CSP 等）而
# 内容不同。v2→v3 升级时版本串没变，但 wheel 内容变了，只比版本号会导致
# 「跳过重建、继续用旧 wheel」，修复对升级用户完全不生效。
# 因此把当前 wheel 的 sha256 记进 venv，安装/启动时比对，不一致就重建。
JW_WHEEL_FP_NAME=".workswarm-wheel.sha256"

jw_wheel_fingerprint() {
  local whl
  whl="$(ls "${JW_WHEELHOUSE}"/workswarm-*.whl 2>/dev/null | head -n 1)"
  [ -n "${whl}" ] || return 1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${whl}" | awk '{print $1}'
  else
    "${PYTHON3:-python3}" -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "${whl}"
  fi
}

# venv 里记录的 wheel 指纹是否与当前包内 wheel 一致（文件缺失视为不一致）。
jw_venv_fingerprint_ok() {
  local want have
  want="$(jw_wheel_fingerprint)" || return 1
  have="$(cat "${JW_VENV}/${JW_WHEEL_FP_NAME}" 2>/dev/null || true)"
  [ -n "${have}" ] && [ "${have}" = "${want}" ]
}

jw_ensure_dirs() {
  mkdir -p "${JW_DATA}" "${JW_LOGS}" "${JW_RUN}" "${TRIM_PKGHOME}" "${TRIM_PKGTMP}" || return 1
  [ -w "${JW_DATA}" ] || return 1
  return 0
}

# 数据目录兼容处理（对应上架门禁 R5）：
#   - 有本应用的安装标记 → 视为自己的数据，原地保留（升级场景）
#   - 无标记但目录非空 → 是历史包/残留数据，整体改名保留，绝不静默覆盖
#   - 同时把 var 下其它历史残留（如 home/、cache/）原样保留并列出来，不删除
JW_INSTALL_MARKER="${JW_DATA}/.fnos-app-meta"
jw_prepare_data_dir() {
  if [ -d "${JW_DATA}" ] && [ -n "$(ls -A "${JW_DATA}" 2>/dev/null)" ] \
      && [ ! -f "${JW_INSTALL_MARKER}" ]; then
    local legacy="${JW_DATA}.legacy-$(date '+%Y%m%d-%H%M%S')"
    if mv "${JW_DATA}" "${legacy}" 2>/dev/null; then
      jw_log "WARN: 检测到无安装标记的历史数据目录，已整体保留为 ${legacy}（未删除）；本次使用全新数据目录"
    else
      jw_fail "数据目录 ${JW_DATA} 非空且无安装标记，改名失败，请手工处理后重试"
      return 1
    fi
  fi
  mkdir -p "${JW_DATA}" || return 1
  {
    printf 'appname=%s\n' "${TRIM_APPNAME:-jiuwenswarm}"
    printf 'appver=%s\n' "${TRIM_APPVER:-unknown}"
    printf 'installed_at=%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')"
  } >"${JW_INSTALL_MARKER}"

  local leftover
  for leftover in "${TRIM_PKGVAR}/home" "${TRIM_PKGVAR}/cache"; do
    [ -e "${leftover}" ] && jw_log "INFO: 保留历史残留目录 ${leftover}（未修改）"
  done
  return 0
}

# 在没有 ensurepip 的 Python 发行版上，用 wheelhouse 里的 pip wheel 自举。
jw_bootstrap_pip() {
  local venv="$1" pip_whl
  pip_whl="$(ls "${JW_WHEELHOUSE}"/pip-*.whl 2>/dev/null | head -n 1)"
  [ -n "${pip_whl}" ] || { jw_fail "wheelhouse 缺少 pip wheel：${JW_WHEELHOUSE}"; return 1; }
  "${venv}/bin/python" - "${pip_whl}" "${JW_WHEELHOUSE}" <<'PY'
import sys
wheel, wheelhouse = sys.argv[1], sys.argv[2]
sys.path.insert(0, wheel)
from pip._internal.cli.main import main
raise SystemExit(main([
    "install", "--no-index", "--find-links", wheelhouse,
    "--disable-pip-version-check", "--no-cache-dir", "pip",
]))
PY
}

# 幂等安装：版本一致且可 import 时直接复用；否则重建到 .new 再原子替换。
jw_install_venv() {
  local want have fp have_fp
  want="$(jw_pip_version)" || return 1
  [ -n "${want}" ] || { jw_fail "无法读取版本文件 ${JW_VERSION_FILE}"; return 1; }
  fp="$(jw_wheel_fingerprint || true)"

  if [ -x "${JW_VENV}/bin/python" ]; then
    have="$("${JW_VENV}/bin/python" -c 'import jiuwenswarm, importlib.metadata as m; print(m.version("workswarm"))' 2>/dev/null || true)"
    have_fp="$(cat "${JW_VENV}/${JW_WHEEL_FP_NAME}" 2>/dev/null || true)"
    if [ "${have}" = "${want}" ] && [ -n "${fp}" ] && [ "${have_fp}" = "${fp}" ]; then
      jw_log "venv 已就绪（workswarm ${have}，wheel sha ${fp}），跳过安装"
      return 0
    fi
    if [ "${have}" != "${want}" ]; then
      jw_log "venv 重建原因：版本变化 old=${have:-<未知>} new=${want}"
    else
      jw_log "venv 重建原因：wheel sha 变化 old=${have_fp:-<无记录>} new=${fp:-<未知>}（版本仍为 ${want}）"
    fi
  fi

  if [ -z "${PYTHON3:-}" ]; then
    jw_fail "未找到 Python 3.12 运行时。请先在应用中心安装 python312 后重试。"
    return 1
  fi
  [ -d "${JW_WHEELHOUSE}" ] || { jw_fail "离线 wheel 目录不存在：${JW_WHEELHOUSE}"; return 1; }
  ls "${JW_WHEELHOUSE}"/workswarm-*.whl >/dev/null 2>&1 \
    || { jw_fail "wheelhouse 缺少 workswarm wheel，安装包不完整"; return 1; }

  local new_venv="${JW_VENV}.new"
  rm -rf "${new_venv}"
  jw_log "创建虚拟环境：${new_venv}（Python: ${PYTHON3}）"
  if ! "${PYTHON3}" -m venv "${new_venv}" >/dev/null 2>&1; then
    jw_log "python -m venv 失败（可能缺少 ensurepip），改用 --without-pip 并从 wheel 自举"
    rm -rf "${new_venv}"
    "${PYTHON3}" -m venv --without-pip "${new_venv}" || { jw_fail "创建虚拟环境失败"; return 1; }
    jw_bootstrap_pip "${new_venv}" || return 1
  fi

  jw_log "离线安装依赖：workswarm==${want}"
  if ! "${new_venv}/bin/python" -m pip install \
      --no-index --find-links "${JW_WHEELHOUSE}" \
      --disable-pip-version-check --no-cache-dir \
      "workswarm==${want}" >>"${JW_LOGS}/install.log" 2>&1; then
    jw_fail "依赖安装失败，详见 ${JW_LOGS}/install.log"
    rm -rf "${new_venv}"
    return 1
  fi

  if ! "${new_venv}/bin/python" -c 'import jiuwenswarm' >/dev/null 2>&1; then
    jw_fail "依赖安装后无法 import jiuwenswarm"
    rm -rf "${new_venv}"
    return 1
  fi

  # 记录本次安装的 wheel 指纹，供下次升级判定（写入后再原子切换）
  if [ -n "${fp}" ]; then
    printf '%s\n' "${fp}" >"${new_venv}/${JW_WHEEL_FP_NAME}" || jw_log "WARN: 写入 wheel 指纹失败（不影响本次安装）"
  fi

  rm -rf "${JW_VENV}"
  mv "${new_venv}" "${JW_VENV}" || { jw_fail "切换虚拟环境失败"; return 1; }
  jw_log "venv 安装完成：${JW_VENV}"
  return 0
}

# 首次初始化工作区（非交互，stdin 非 TTY 时 upstream 默认 zh）。
# 失败不阻断安装：应用启动时 prepare_runtime_workspace() 会自动补齐。
jw_init_workspace() {
  [ -x "${JW_VENV}/bin/python" ] || return 0
  jw_log "初始化数据目录：${JW_DATA}"
  if HOME="${TRIM_PKGHOME}" JIUWENSWARM_DATA_DIR="${JW_DATA}" \
      "${JW_VENV}/bin/python" -m jiuwenswarm.init_workspace </dev/null \
      >>"${JW_LOGS}/install.log" 2>&1; then
    jw_log "工作区初始化完成"
  else
    jw_log "WARN: jiuwenswarm-init 未成功（启动时会自动补齐），详见 ${JW_LOGS}/install.log"
  fi
  return 0
}
