#!/bin/bash
# scripts/build-payload.sh —— 构建 fnOS 包内运行载荷（前端 dist + 离线 wheel 集）
#
# 前置：构建机需 x86_64 Linux、Python 3.12、Node.js >= 20、npm、git，且可访问
#       PyPI 镜像与 gitcode.com（git 源依赖）。
# 产物：app/wheelhouse/*.whl、app/wheelhouse/SHA256SUMS、app/wheelhouse/WHEELS.txt
# 说明：本脚本不打包 .fpk，打包由 scripts/build-fpk.sh（调用 fnpack）完成。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="${JIUWENSWARM_SRC:-$(cd "${APP_DIR}/../jiuwenswarm" && pwd)}"
PYTHON="${PYTHON:-python3}"
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
GATEWAY_PREFIX="/app/jiuwenswarm"

log() { echo "[build-payload] $*"; }
die() { echo "[build-payload] ERROR: $*" >&2; exit 1; }

[ -f "${SRC_DIR}/pyproject.toml" ] || die "找不到 JiuwenSwarm 源码：${SRC_DIR}（可用 JIUWENSWARM_SRC 覆盖）"
command -v "${PYTHON}" >/dev/null || die "缺少 ${PYTHON}"
command -v npm >/dev/null || die "缺少 npm（构建期只需 Node，运行期不需要）"
command -v git >/dev/null || die "缺少 git（openjiuwen / agent-gateway 来自 git 源）"

# ---------------------------------------------------------------- 架构校验 ----
arch="$(uname -m)"
[ "${arch}" = "x86_64" ] || die "目标设备为 x86_64，当前构建机是 ${arch}；请换 x86_64 构建机或交叉构建"
"${PYTHON}" - <<'PY' || die "构建机 Python 需为 3.12（与设备 python312 一致）"
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(f"python is {sys.version.split()[0]}, need 3.12.x")
PY

# ---------------------------------------------------------------- 前端 dist ----
WEB_DIR="${SRC_DIR}/jiuwenswarm/channels/web/frontend"
log "构建前端：${WEB_DIR}（base=${GATEWAY_PREFIX}/，API/WS 前缀=${GATEWAY_PREFIX}）"
cd "${WEB_DIR}"
if [ -f package-lock.json ]; then
  npm ci --no-audit --no-fund || npm install --no-audit --no-fund
else
  npm install --no-audit --no-fund
fi
VITE_API_BASE="${GATEWAY_PREFIX}" \
VITE_WS_BASE="${GATEWAY_PREFIX}" \
  npm run build -- "--base=${GATEWAY_PREFIX}/"
[ -f "${WEB_DIR}/dist/index.html" ] || die "前端构建未产出 dist/index.html"

# ---------------------------------------------------------------- 离线 wheels ----
WHEELHOUSE="${APP_DIR}/app/wheelhouse"
log "重建离线 wheel 集：${WHEELHOUSE}"
rm -rf "${WHEELHOUSE}"
mkdir -p "${WHEELHOUSE}"

log "解析并构建 workswarm 及其全部依赖（含 gitcode 源依赖）"
"${PYTHON}" -m pip wheel \
  --wheel-dir "${WHEELHOUSE}" \
  --no-cache-dir \
  --index-url "${PIP_INDEX}" \
  "${SRC_DIR}"

log "补充 pip / setuptools / wheel（离线自举用）"
"${PYTHON}" -m pip download \
  --only-binary=:all: --no-cache-dir \
  --dest "${WHEELHOUSE}" \
  --index-url "${PIP_INDEX}" \
  pip setuptools wheel

log "把 git/URL 直接依赖改写为精确版本（pip 离线安装必需）"
"${PYTHON}" "${APP_DIR}/scripts/offlineize-wheelhouse.py" "${WHEELHOUSE}"

log "校验 wheel 架构与生成清单"
"${PYTHON}" "${APP_DIR}/scripts/check-wheels.py" "${WHEELHOUSE}"

log "完成。wheel 数量：$(find "${WHEELHOUSE}" -name '*.whl' | wc -l)"
log "下一步：bash scripts/build-fpk.sh"
