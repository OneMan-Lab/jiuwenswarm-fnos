#!/bin/bash
# scripts/build-fpk.sh —— 调用 fnpack 生成 .fpk，并做结构自检
#
# 用法：
#   bash scripts/build-fpk.sh                          # 测试包（默认，manifest 不含 install_dep_apps）
#   BUILD_PROFILE=appstore bash scripts/build-fpk.sh   # 上架包（manifest 含 install_dep_apps=python312）
#   SIGN=1 bash scripts/build-fpk.sh                   # 使用已导入的开发者证书签名（正式分发）
# 环境变量：
#   FNPACK=/path/to/fnpack        # fnpack 可执行文件（默认取 PATH）
#   BUILD_PROFILE=test|appstore   # 见上
#
# 两个 profile 的唯一差异是 manifest 中的 install_dep_apps 一行：
#   - 测试包不带：命令行 install-fpk 有安全闸会拦截「带依赖」的包；
#   - 上架包带：应用中心 UI 安装依赖是正常流程。
# 构建在硬链接暂存目录中进行，绝不修改工作区里的 manifest。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FNPACK="${FNPACK:-fnpack}"
SIGN="${SIGN:-0}"
PROFILE="${BUILD_PROFILE:-test}"

case "${PROFILE}" in
  test|appstore) ;;
  *) echo "ERROR: BUILD_PROFILE 只能是 test 或 appstore（当前：${PROFILE}）" >&2; exit 2 ;;
esac

cd "${APP_DIR}"

if ! FNPACK_BIN="$(command -v "${FNPACK}" 2>/dev/null)"; then
  echo "ERROR: 未找到 fnpack。安装方式见 README「构建」章节：" >&2
  echo "  curl -fL https://static2.fnnas.com/fnpack/fnpack-1.3.3-linux-amd64 -o fnpack && chmod +x fnpack" >&2
  echo "  然后 FNPACK=./fnpack bash scripts/build-fpk.sh" >&2
  exit 1
fi
FNPACK="${FNPACK_BIN}"

if [ ! -d app/wheelhouse ] || [ -z "$(find app/wheelhouse -name '*.whl' -print -quit)" ]; then
  echo "ERROR: app/wheelhouse 为空。请先执行 bash scripts/build-payload.sh" >&2
  exit 1
fi

# CSP 补丁闸门：上游 app_web.py 若改动，patch 脚本会明确失败（绝不静默打出一个没修的包）。
# 先补（幂等），再以 --check 断言补丁已在 wheel 里生效；CI 可直接复用同一条命令。
"${PYTHON_OR_PY:-python3}" scripts/patch-app-web-csp.py app/wheelhouse \
  || { echo "ERROR: CSP 补丁失败（上游 app_web.py 可能已改动）。请按 scripts/patch-app-web-csp.py 的报错更新补丁后再构建。" >&2; exit 1; }
"${PYTHON_OR_PY:-python3}" scripts/patch-app-web-csp.py app/wheelhouse --check \
  || { echo "ERROR: wheel 中未发现 frame-ancestors 'self'，拒绝构建（否则门户 iframe 会白屏）。" >&2; exit 1; }

# 前端根路径闸门：dist 里 `"/logo.svg"` 这类根路径在网关前缀下会 404（品牌图空白）。
"${PYTHON_OR_PY:-python3}" scripts/patch-app-web-logo.py app/wheelhouse \
  || { echo "ERROR: 前端 logo 路径补丁失败（dist 结构可能已改动）。按 scripts/patch-app-web-logo.py 报错处理后重试。" >&2; exit 1; }
"${PYTHON_OR_PY:-python3}" scripts/patch-app-web-logo.py app/wheelhouse --check \
  || { echo "ERROR: wheel 前端仍有根路径 /logo.svg，拒绝构建（会导致网关下 404）。" >&2; exit 1; }

VERSION="$(grep -E '^version[[:space:]]*=' manifest | head -n1 | sed -E 's/^[^=]+=[[:space:]]*//; s/[[:space:]]+$//')"
STAGE="$(dirname "${APP_DIR}")/.build-fpk-${PROFILE}"

cleanup() { rm -rf "${STAGE}"; }
trap cleanup EXIT

echo "[build-fpk] profile=${PROFILE} version=${VERSION}"
cleanup
mkdir -p "${STAGE}"
# 硬链接复制（同一文件系统，几乎不占空间），避免复制 468MB wheelhouse
cp -al "${APP_DIR}/." "${STAGE}/" 2>/dev/null || cp -a "${APP_DIR}/." "${STAGE}/"
rm -f "${STAGE}"/*.fpk 2>/dev/null || true

# 按 profile 生成暂存目录里的 manifest（写临时文件后 os.replace 原子替换，打断硬链接，不影响工作区）
"${PYTHON_OR_PY:-python3}" - "${STAGE}/manifest" "${PROFILE}" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
profile = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
lines = [ln for ln in lines if not ln.strip().startswith("install_dep_apps")]
if profile == "appstore":
    out = []
    inserted = False
    for ln in lines:
        if not inserted and ln.strip().startswith("changelog"):
            out.append("install_dep_apps=python312")
            inserted = True
        out.append(ln)
    if not inserted:
        out.append("install_dep_apps=python312")
    lines = out
text = "\n".join(lines) + "\n"
# 硬链接暂存下 path 与工作区 manifest 共享同一 inode：直接 write_text 会原地截断重写，
# 静默删掉工作区 manifest 的 install_dep_apps 行（Q-01）。先写临时文件（新建 inode），
# 再以 os.replace 原子替换，替换后 path 指向新 inode，工作区文件不再受影响。
tmp = path.with_name("manifest.tmp")
tmp.write_text(text, encoding="utf-8")
os.replace(tmp, path)
PY

echo "[build-fpk] manifest 差异："
diff -u manifest "${STAGE}/manifest" || true

# fnpack 把 .fpk 写到「当前工作目录」，与 -d 无关，因此在暂存目录内执行
if [ "${SIGN}" = "1" ]; then
  ( cd "${STAGE}" && "${FNPACK}" build )
else
  ( cd "${STAGE}" && "${FNPACK}" build --nosign )
fi

BUILT="${STAGE}/jiuwenswarm.fpk"
[ -s "${BUILT}" ] || { echo "ERROR: fnpack 未产出 ${BUILT}" >&2; exit 1; }

if [ "${PROFILE}" = "appstore" ]; then
  OUT="${APP_DIR}/jiuwenswarm-${VERSION}-appstore.fpk"
else
  OUT="${APP_DIR}/jiuwenswarm-${VERSION}.fpk"
fi
rm -f "${OUT}"
ln -f "${BUILT}" "${OUT}" 2>/dev/null || cp -f "${BUILT}" "${OUT}"
if [ "${PROFILE}" = "test" ]; then
  rm -f "${APP_DIR}/jiuwenswarm.fpk"
  ln -f "${OUT}" "${APP_DIR}/jiuwenswarm.fpk" 2>/dev/null || cp -f "${OUT}" "${APP_DIR}/jiuwenswarm.fpk"
fi

# 新鲜度闸门：包内关键脚本必须与工作区逐字节一致。
# 0.2.9-8 曾因「构建后又改代码」把旧 supervisor.py 打进包，导致整轮排查指向错误方向。
"${PYTHON_OR_PY:-python3}" scripts/verify-package-freshness.py "${OUT}" "${APP_DIR}" \
  || { echo "ERROR: 包内文件与工作区不一致，拒绝交付（请重新执行构建）。" >&2; exit 1; }

# profile 断言：包内 manifest 的 install_dep_apps 必须与 profile 一致
TMP_CHECK="$(mktemp -d)"
tar xzf "${OUT}" -C "${TMP_CHECK}" manifest
if [ "${PROFILE}" = "appstore" ]; then
  grep -qE '^install_dep_apps[[:space:]]*=[[:space:]]*python312' "${TMP_CHECK}/manifest" \
    || { echo "ERROR: 上架包缺少 install_dep_apps=python312" >&2; exit 1; }
else
  ! grep -qE '^install_dep_apps' "${TMP_CHECK}/manifest" \
    || { echo "ERROR: 测试包不应包含 install_dep_apps" >&2; exit 1; }
fi
rm -rf "${TMP_CHECK}"

echo "[build-fpk] 产物：${OUT}"
ls -lh "${OUT}"
sha256sum "${OUT}"
bash scripts/verify-fpk.sh "${OUT}"
