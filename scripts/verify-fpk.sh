#!/bin/bash
# scripts/verify-fpk.sh —— 校验 .fpk 结构与关键载荷（不安装、不改设备）
# 用法：bash scripts/verify-fpk.sh jiuwenswarm.fpk
set -euo pipefail

FPK="${1:-}"
[ -n "${FPK}" ] && [ -f "${FPK}" ] || { echo "用法: $0 <app.fpk>" >&2; exit 2; }

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "[verify] 解开 fpk 外层"
tar xzf "${FPK}" -C "${TMP}"

fail=0
check() { if eval "$2"; then echo "  OK   $1"; else echo "  FAIL $1"; fail=1; fi; }

check "manifest 存在" "[ -f '${TMP}/manifest' ]"
check "config/privilege 存在" "[ -f '${TMP}/config/privilege' ]"
check "config/resource 存在" "[ -f '${TMP}/config/resource' ]"
check "cmd/main 存在" "[ -f '${TMP}/cmd/main' ]"
check "cmd/install_callback 存在" "[ -f '${TMP}/cmd/install_callback' ]"
check "ICON.PNG 存在" "[ -f '${TMP}/ICON.PNG' ]"
check "ICON_256.PNG 存在" "[ -f '${TMP}/ICON_256.PNG' ]"
check "app.tgz 存在" "[ -s '${TMP}/app.tgz' ]"
check "privilege 是合法 JSON" "python3 -m json.tool '${TMP}/config/privilege' >/dev/null"
check "resource 是合法 JSON" "python3 -m json.tool '${TMP}/config/resource' >/dev/null"
check "manifest 含 appname" "grep -qE '^appname[[:space:]]*=' '${TMP}/manifest'"
check "manifest 含 version" "grep -qE '^version[[:space:]]*=' '${TMP}/manifest'"
check "manifest 声明 gateway 型（无 service_port）" "! grep -qE '^service_port[[:space:]]*=' '${TMP}/manifest'"

echo "[verify] 解开 app.tgz"
mkdir -p "${TMP}/app"
tar xzf "${TMP}/app.tgz" -C "${TMP}/app"
check "ui/config 存在" "[ -f '${TMP}/app/ui/config' ]"
check "ui/config 声明 gatewaySocket" "grep -q 'gatewaySocket' '${TMP}/app/ui/config'"
check "ui/config 声明 gatewayPrefix" "grep -q '/app/jiuwenswarm' '${TMP}/app/ui/config'"
check "入口图标 icon_64.png" "[ -f '${TMP}/app/ui/images/icon_64.png' ]"
check "入口图标 icon_256.png" "[ -f '${TMP}/app/ui/images/icon_256.png' ]"
check "server/supervisor.py" "[ -f '${TMP}/app/server/supervisor.py' ]"
check "server/uds_gateway.py" "[ -f '${TMP}/app/server/uds_gateway.py' ]"
check "wheelhouse/workswarm wheel" "ls '${TMP}/app/wheelhouse'/workswarm-*.whl >/dev/null 2>&1"
check "wheelhouse/SHA256SUMS" "[ -f '${TMP}/app/wheelhouse/SHA256SUMS' ]"
check "前端 dist 已打入 workswarm wheel" \
  "python3 -c \"import zipfile,glob,sys; w=glob.glob('${TMP}/app/wheelhouse/workswarm-*.whl')[0]; n=zipfile.ZipFile(w).namelist(); sys.exit(0 if any('channels/web/frontend/dist/index.html' in x for x in n) else 1)\""

echo "[verify] 前端 base path"
if command -v python3 >/dev/null; then
  W="$(ls "${TMP}"/app/wheelhouse/workswarm-*.whl | head -n1)"
  python3 - "${W}" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
names = [n for n in z.namelist() if n.endswith("frontend/dist/index.html")]
if not names:
    print("  FAIL wheel 内找不到 index.html"); raise SystemExit(1)
html = z.read(names[0]).decode("utf-8", "replace")
ok = "/app/jiuwenswarm/assets/" in html
print(("  OK   " if ok else "  FAIL ") + "index.html 资源前缀 = /app/jiuwenswarm/")
raise SystemExit(0 if ok else 1)
PY
  [ $? -eq 0 ] || fail=1
fi

if [ "${fail}" -ne 0 ]; then
  echo "[verify] 结论：失败"
  exit 1
fi
echo "[verify] 结论：通过"
