#!/bin/bash
# scripts/build-fpk.sh —— 调用 fnpack 生成 .fpk，并做结构自检
#
# 用法：
#   bash scripts/build-fpk.sh                          # 应用中心档位（唯一档位，默认）
#   BUILD_PROFILE=appstore bash scripts/build-fpk.sh   # 显式指定应用中心档位（与裸跑等价）
#   SIGN=1 bash scripts/build-fpk.sh                   # 使用已导入的开发者证书签名（正式分发）
# 环境变量：
#   FNPACK=/path/to/fnpack        # fnpack 可执行文件（默认取 PATH）
#   BUILD_PROFILE=appstore        # 唯一合法取值；历史值 test 档位已移除，传入即报错退出
#   BUILD_STAGE=/abs/dir          # 暂存目录覆盖（默认取工程同级目录；工程同级只读时可用，
#                                 #   但必须与工程同文件系统，否则硬链接复制回退为全量复制）
#
# 唯一产物为应用中心包 jiuwenswarm-{VERSION}.fpk（包内 manifest 含 install_dep_apps=python312），
# 仅可经 fnOS 应用中心 UI 安装：CLI `app install-fpk` 有安全闸会拦截「带依赖」的包
# （历史双包策略已取消，决策记录见 docs/BUILD.md §3.1）。
# 构建在硬链接暂存目录中进行：暂存 manifest 走「断言 + 恒等原子替换」（临时文件 + os.replace
# 打断硬链接），绝不修改工作区里的 manifest。
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FNPACK="${FNPACK:-fnpack}"
SIGN="${SIGN:-0}"
PROFILE="${BUILD_PROFILE:-appstore}"

case "${PROFILE}" in
  appstore) ;;
  *) echo "ERROR: 仅支持应用中心档位，test 档位已移除（当前 BUILD_PROFILE=${PROFILE}）。直接 bash scripts/build-fpk.sh，或显式 BUILD_PROFILE=appstore。" >&2; exit 2 ;;
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
STAGE="${BUILD_STAGE:-$(dirname "${APP_DIR}")/.build-fpk}"

cleanup() { rm -rf "${STAGE}"; }
trap cleanup EXIT

echo "[build-fpk] profile=${PROFILE} version=${VERSION}"
cleanup
mkdir -p "${STAGE}"
# 硬链接复制（同一文件系统，几乎不占空间），避免复制 468MB wheelhouse
cp -al "${APP_DIR}/." "${STAGE}/" 2>/dev/null || cp -a "${APP_DIR}/." "${STAGE}/"
rm -f "${STAGE}"/*.fpk 2>/dev/null || true

# 暂存 manifest 写入：先断言工作区 manifest 已是上架形态（install_dep_apps=python312 在位），
# 再做内容恒等的原子替换。
# 硬链接暂存下 path 与工作区 manifest 共享同一 inode：对暂存文件的任何原地重写都会写穿工作区
# （Q-01：历史上曾因原地 write_text 截断重写而静默删掉工作区 install_dep_apps 行）。
# 因此即便内容恒等，也必须先写临时文件（新建 inode）再以 os.replace 原子替换，打断硬链接；
# fnpack 对暂存文件是否有原地写行为未经证实，此机制保证工作区 manifest 绝不被动。
# 若工作区 manifest 缺 install_dep_apps=python312，说明配置漂移，在 fnpack 之前 fail-fast，
# 绝不静默修复。
"${PYTHON_OR_PY:-python3}" - "${STAGE}/manifest" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
if not any(ln.strip().startswith("install_dep_apps") and "python312" in ln for ln in lines):
    print("ERROR: 工作区 manifest 应为上架形态（含 install_dep_apps=python312），当前缺失。"
          "请检查 manifest 是否被改动，修正后重跑构建。", file=sys.stderr)
    sys.exit(1)
tmp = path.with_name("manifest.tmp")
tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
os.replace(tmp, path)
PY

echo "[build-fpk] manifest 差异（预期为空；fnpack 若重排键值属可接受现象）："
diff -u manifest "${STAGE}/manifest" || true

# fnpack 把 .fpk 写到「当前工作目录」，与 -d 无关，因此在暂存目录内执行
if [ "${SIGN}" = "1" ]; then
  ( cd "${STAGE}" && "${FNPACK}" build )
else
  ( cd "${STAGE}" && "${FNPACK}" build --nosign )
fi

BUILT="${STAGE}/jiuwenswarm.fpk"
[ -s "${BUILT}" ] || { echo "ERROR: fnpack 未产出 ${BUILT}" >&2; exit 1; }

OUT="${APP_DIR}/jiuwenswarm-${VERSION}.fpk"
rm -f "${OUT}"
ln -f "${BUILT}" "${OUT}" 2>/dev/null || cp -f "${BUILT}" "${OUT}"

# 新鲜度闸门：包内关键脚本必须与工作区逐字节一致。
# 0.2.9-8 曾因「构建后又改代码」把旧 supervisor.py 打进包，导致整轮排查指向错误方向。
"${PYTHON_OR_PY:-python3}" scripts/verify-package-freshness.py "${OUT}" "${APP_DIR}" \
  || { echo "ERROR: 包内文件与工作区不一致，拒绝交付（请重新执行构建）。" >&2; exit 1; }

# install_dep_apps 断言：包内 manifest 必须是上架形态（与暂存期前置断言构成双层防御）
TMP_CHECK="$(mktemp -d)"
tar xzf "${OUT}" -C "${TMP_CHECK}" manifest
grep -qE '^install_dep_apps[[:space:]]*=[[:space:]]*python312' "${TMP_CHECK}/manifest" \
  || { echo "ERROR: 包内 manifest 缺少 install_dep_apps=python312" >&2; exit 1; }
rm -rf "${TMP_CHECK}"

echo "[build-fpk] 产物：${OUT}"
ls -lh "${OUT}"
sha256sum "${OUT}"
bash scripts/verify-fpk.sh "${OUT}"

# 成功路径尾部：清理当前版本的旧双包命名残留（FR-04）。指定文件名而非 glob，
# 避免误删新产物与其他版本号产物；构建失败时不会到达此处（保留现场排查）。
rm -f "${APP_DIR}/jiuwenswarm.fpk" "${APP_DIR}/jiuwenswarm-${VERSION}-appstore.fpk"
echo "[build-fpk] 旧双包命名残留已清理（如存在）"
