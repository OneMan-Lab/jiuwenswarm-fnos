> 本文为开源发布版，设备与环境标识已脱敏。

# 应用开发与打包实战经验（可复用）

> 来源：把 JiuwenSwarm（Python + 前端 SPA + WebSocket 的常驻服务）改造成飞牛 fnOS 原生应用（`.fpk`），
> 从 v1 到 v12（版本 0.2.9-5 → 0.2.9-12）的完整开发过程。
> 用途：给后来做「把现成 Web 服务塞进 fnOS 统一网关」的人一套能直接照做的方法与踩坑地图。
> 证据标注：`[实测]` 本机/真机真实执行输出｜`[静态]` 代码、配置、响应头原文可查｜`[推断]` 由前两者推理、无直接观测｜`[未验证]` 缺证据
> 代码基线：`swarm-fnos-app/` @ 0.2.9-12（文中的行号以此版本为准，同时给出符号名以防偏移）。

**工程根**：`<WORKSPACE>/swarm-fnos-app`
**上游源码（只读）**：`<WORKSPACE>/jiuwenswarm`

---

## 0. 一句话总览（七条经验的一句话版）

| # | 经验 | 一句话 |
|---|---|---|
| 1 | CSP 白屏 | 门户 iframe 白屏不是"网关/WS 坏了"，是上游给了 `frame-ancestors 'none'`；改 `'self'`，别去补 `connect-src` |
| 2 | 依赖声明 | `install_dep_apps` 会让 CLI 安装被安全闸拦下，所以出**双包**：测试包不带、上架包带 |
| 3 | 升级重建 | 「版本号相同」≠「内容相同」，venv 必须比 **wheel sha256**，否则升级用户永远用旧代码 |
| 4 | UDS 桥 | 只解析头部、其余**纯字节转发**，才能透传 WS 帧；身份判定用 `SO_PEERCRED` + exe 全路径，读不到就拒 |
| 5 | WS Origin | 两次判断都错：先是"网关不支持 WS"，后是"只校验 Host 就够"。真相是 **nginx 改写了 Host**，必须靠 `X-Forwarded-Host` 兜底 |
| 6 | 卸载脚本 | 三句话：**参数校验 fail-fast、删除动作 fail-open、退出码永远 0** |
| 7 | 构建防御 | 包内文件必须与源码**逐字节**一致；补丁匹配不到就**拒绝构建**——两个闸门都是被事故逼出来的 |

---

## 1. CSP 导致门户 iframe 白屏

### 1.1 现象

- 直接打开 `http://<设备>:5666/app/jiuwenswarm`（顶层窗口）→ **正常**。
- 在飞牛门户里点应用图标（门户用 iframe 嵌入 `/app/jiuwenswarm`）→ **白屏**，页面无任何内容。
- 浏览器控制台唯一有效线索：
  ```
  Framing 'http://<设备>:5666/' violates the following Content Security Policy directive:
  "frame-ancestors 'none'". The request has been blocked.
  ```
  `[实测]`

**这个组合本身就是判据**：顶层能开、iframe 打不开 ⇒ 问题在"能不能被嵌入"，与网关、端口、WS、前端路由全部无关。

### 1.2 根因

上游把静态文档策略写死为禁止被嵌入：

```python
# jiuwenswarm/channels/web/app_web.py:527
class _SpaStaticHandler(SimpleHTTPRequestHandler):
    _TOP_LEVEL_DOCUMENT_CSP = "frame-ancestors 'none'"
    _EMBEDDABLE_DOCUMENT_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"

# app_web.py:3208-3215 —— 静态页（_static_cache_control 非空）走 top-level 策略
def _host_document_policy(self) -> str | None:
    if is_enterprise():
        return None
    if getattr(self, "_static_cache_control", None) or urlparse(self.path).path == "/api/v1/auth/callback":
        return self._TOP_LEVEL_DOCUMENT_CSP
    return self._EMBEDDABLE_DOCUMENT_CSP
```
`[静态]`

要点：**index.html 命中的是 top-level 分支**（它有 static cache control），所以直接吃 `'none'`。
`_EMBEDDABLE_DOCUMENT_CSP` 那个分支并不是"更友好的版本"，它是给**代理内容**用的 sandbox 策略（见 1.5）。

### 1.3 定位过程（可复现）

```bash
# 1) 拿真实响应头，不猜
curl -sI http://<设备>:5666/app/jiuwenswarm/ | grep -i content-security-policy
#   期望看到 frame-ancestors 'none'

# 2) 从本地 wheel 里确认常量（不需要设备）
cd swarm-fnos-app
unzip -p app/wheelhouse/workswarm-*.whl jiuwenswarm/channels/web/app_web.py \
  | grep -n "frame-ancestors"

# 3) 确认这份 wheel 就是被打进包的（否则改错地方）
python3 scripts/verify-package-freshness.py jiuwenswarm-0.2.9-12.fpk .
```

### 1.4 解法：在 wheel 层定点替换（源码仓只读）

上游源码仓约定只读（构建前后 `git -C ../jiuwenswarm status --porcelain` 必须为空），所以补丁落在**已构建的 wheel** 上：

```bash
python3 scripts/patch-app-web-csp.py app/wheelhouse           # 幂等：已是 'self' 直接跳过
python3 scripts/patch-app-web-csp.py app/wheelhouse --check    # 断言已生效，否则 exit 1
```

`scripts/patch-app-web-csp.py` 做三件事：解包 wheel → 替换 `_TOP_LEVEL_DOCUMENT_CSP` 常量 → **重算该文件的 `RECORD`（sha256 + size）后重新打包**。
最后一步最容易漏：只改内容不改 RECORD，pip 装的时候会报 hash 不匹配。

`scripts/build-fpk.sh:43-48` 把这两步做成**构建闸门**：补丁打不上（上游改了目标行）→ 直接 exit 1，绝不静默打出未修复的包。

### 1.5 为什么**不能**靠补 `connect-src` 解决

这是本项目被讨论最多的一条，结论分两半：

**（a）`connect-src` 本来就不存在 —— 补它是在收紧，不是在修复** `[静态]`+`[实测]`
该策略只有 `frame-ancestors` 一条，**没有** `connect-src` / `default-src` / `script-src` / `img-src`，
响应头里也没有 `X-Frame-Options`。即 WebSocket、API 请求、静态资源**本来不受 CSP 约束**。
补 `connect-src 'self'` 只会新增限制，且部分旧浏览器不把 `'self'` 映射到 `ws://` / `wss://`，反而可能把 WS 拦断。

**（b）想让服务端"按真实 Origin 生成白名单"是不可能的** `[静态]`
桥会把 `Host` 统一改写为 `127.0.0.1:15173` 再发给上游（`app/server/uds_gateway.py:177-182`，`_build_head`）：

```python
if low == "host":
    lines.append(f"Host: {UPSTREAM_HOST}:{UPSTREAM_PORT}")   # 上游只监听本机
    has_host = True
    continue
```

于是上游从 `Host` 拼出来的"本站地址"**永远是回环**，与浏览器里的真实域名（`<NAS_DOMAIN>` 之类）无关。
唯一带着真域名的 `X-Forwarded-Host` 是**请求头、可伪造**，把它写进 CSP 源等于把可伪造值当安全边界。
所以正确选择是**让 CSP 与访问来源无关**：不放任何源相关指令，嵌入判定只用 `frame-ancestors 'self'`。

> 这一条的正确表述是"**没有可用的可信 Origin 供服务端生成 CSP**"，不是"补 connect-src 会导致 WS 失败"——
> 后者只是旧浏览器的附注，前者才是结构性的原因。`[静态]`

### 1.6 为什么不用现成的 `_EMBEDDABLE_DOCUMENT_CSP`

```python
_EMBEDDABLE_DOCUMENT_CSP = "sandbox allow-scripts allow-forms allow-popups allow-modals allow-downloads"
```

它没有 `allow-same-origin`。`sandbox` 缺这一项 ⇒ 文档进入 **opaque origin**：读不到自己的 cookie/localStorage，
`Origin` 头语义、存储分区、同源判定全部改变，应用在 iframe 里会以更诡异的方式坏掉（不是白屏，是登录态丢失/存储异常）。
`'self'` 才是"只允许同源嵌入、其余一切照旧"的最小改动。`[静态]`+`[推断]`（未逐一实测 sandbox 分支的失败形态）

### 1.7 为什么会踩坑

- 白屏可以被三个方向解释：网关没转发、WS 没连上、前端路由 404。**只有响应头能一刀切**，其余都是猜。
- 上游 CSP 是**两分支**的，看到 `sandbox ...` 那个常量容易误以为"已经有可嵌入策略，改配置切换即可"——实际切换会改变文档权限模型。
- 补丁改的是**构建产物**而不是源码，所以"我改了代码"和"包里生效了"是两件事，必须有 `--check` 闸门（见 §7）。

---

## 2. `install_dep_apps` 导致 CLI 拒绝安装：双包线的由来

### 2.1 现象

- `fnos app install-fpk jiuwenswarm.fpk`（manifest 带 `install_dep_apps=python312`）被**安全闸拦截**。
- 已安装应用再次 `install-fpk`（任何包）直接返回 `{"code":10236}` —— CLI 无 force/overwrite。`[实测]`

### 2.2 根因

平台把 `install_dep_apps` 视为"会改动系统级依赖"的强操作：UI 安装路径允许（会先装依赖再装应用），
命令行路径有安全闸，避免一条命令悄悄给 NAS 装上别的东西。`[静态]`（manifest 字段语义）+ `[实测]`（CLI 行为）

### 2.3 解法：同一份工程出两个包，差异只有一行

```
manifest:21  install_dep_apps=python312      # 工作区版本 = 上架形态
```

`scripts/build-fpk.sh:71-88` 在**硬链接暂存目录**里重写 manifest（先删再按 profile 插回，打断硬链接，不动工作区）：

```python
lines = [ln for ln in lines if not ln.strip().startswith("install_dep_apps")]
if profile == "appstore":
    # 插到 changelog 之前；没有 changelog 就追加
    ...
    out.append("install_dep_apps=python312")
```

然后 `build-fpk.sh:115-127` 对产物**断言** profile：

```bash
grep -qE '^install_dep_apps[[:space:]]*=[[:space:]]*python312' manifest  || exit 1   # appstore 必须有
! grep -qE '^install_dep_apps' manifest                                  || exit 1   # test 必须没有
```

同时 `install_callback`/`init_env.sh` 做**运行时探测**兜底（不依赖包管理器）：
`/var/apps/python312/target/bin/python3` → `python3.12` → `python3`，校验主版本必须是 3.12；找不到就写 `TRIM_TEMP_LOGFILE` 并让 `status=3`，而不是起一个跑不起来的进程。

### 2.4 取舍与纪律

| | 测试包 `jiuwenswarm-<ver>.fpk` | 上架包 `jiuwenswarm-<ver>-appstore.fpk` |
|---|---|---|
| `install_dep_apps` | 无 | `python312` |
| 安装方式 | CLI `install-fpk` / UI | **只能 UI**（应用中心） |
| 用途 | 真机验证、CLI 自动化 | 商店上架 |
| 真机状态 | 已验 | **未验证**（见 §10） |

纪律：
1. **不要拿上架包走 CLI** —— 会被闸门挡住，浪费一轮。
2. 两份产物 **sha 不同是正常的**（manifest 一行差异 + fnpack 重算 checksum），不要试图"对齐 sha"。
3. `jiuwenswarm.fpk` 是测试包的硬链，别单独分发（容易和上架包混淆）。

### 2.5 为什么会踩坑

- 依赖声明看起来"更规范、更省事"，但在这个平台上它**换掉了可用安装通道**。
- 两份产物名字只差一个后缀、体积只差几十字节，靠人记不住谁是谁 ⇒ 必须让**构建脚本断言**，而不是靠文档提醒。

---

## 3. wheel 指纹与升级重建："版本号相同"不等于"内容相同"

### 3.1 现象

给上游 wheel 打了 CSP 补丁后升级应用，**白屏依旧**。设备上检查发现：

```bash
# venv 里装的还是旧内容
grep -c "frame-ancestors 'none'" <var>/venv/lib/python3.12/site-packages/jiuwenswarm/channels/web/app_web.py
# → 1（补丁没生效）
```
`[实测]`

### 3.2 根因

`runtime.sh` 的幂等判定原本只比 pip 元数据版本：

```bash
have="$("${JW_VENV}/bin/python" -c 'import jiuwenswarm, importlib.metadata as m; print(m.version("workswarm"))')"
[ "${have}" = "${want}" ] && return 0      # 版本相同 ⇒ 跳过重建
```

而本项目的补丁**不改变上游版本号**（v2/v3 都是 `0.2.9b5`，wheel 内容 `275df5da…` → `c6959cba…`）。
结果：判定"已安装"，直接复用旧 venv，修复对**升级用户**完全无效（新装用户反而正常——这让问题看起来像"偶发"）。`[静态]`+`[实测]`

### 3.3 解法：把 wheel 的 sha256 记进 venv

`app/server/runtime.sh:26-52`：

```bash
JW_WHEEL_FP_NAME=".workswarm-wheel.sha256"
jw_wheel_fingerprint() { sha256sum "${whl}" | awk '{print $1}'; }
jw_venv_fingerprint_ok() {
  want="$(jw_wheel_fingerprint)" || return 1
  have="$(cat "${JW_VENV}/${JW_WHEEL_FP_NAME}" 2>/dev/null || true)"
  [ -n "${have}" ] && [ "${have}" = "${want}" ]
}
```

`jw_install_venv`（`runtime.sh:100-140`）判定条件是 **版本 + 指纹双一致**才跳过，且**打印重建原因**（old/new 分开写，便于区分"版本变了"还是"内容变了"）。
`cmd/main:126-137` 在**每次启动**也再比一次指纹（覆盖"安装后没启动、直接手工换 wheel"等场景）：

```bash
elif ! jw_venv_fingerprint_ok; then
  jw_log "WARN: 包内 wheel 与已装 venv 不一致（升级场景），重建运行时…"
  jw_install_venv || return 1
```

### 3.4 验证方法（真实重建，不是桩）

```bash
# 造一个"版本号不变、内容变了"的 wheel，放在 wheelhouse，跑一次安装函数
# 期望输出：
# [jiuwenswarm] venv 重建原因：wheel sha 变化 old=c6959cba… new=0a20c557…（版本仍为 0.2.9b5）
# [jiuwenswarm] 创建虚拟环境：…/venv.new（Python: /usr/bin/python3.12）
# [jiuwenswarm] venv 安装完成：…
# 再验证新内容确实进去了（用测试标记字符串，不要用文件时间戳）
grep -c "fnos-patch v4 marker" <var>/venv/lib/python3.12/site-packages/jiuwenswarm/channels/web/app_web.py   # → 1
```
`[实测]`

桩级矩阵（快速回归）：指纹文件缺失 → 重建；指纹一致 → `已就绪（…wheel sha …），跳过安装`；指纹不一致 → 重建并打印 old/new。

### 3.5 假阴性：残留 venv 让"全新安装"验证失真

机制（`[静态]`+`[推断]`）：
- 旧版本（≤0.2.9-9）卸载**不删 venv**（见 §6），所以设备上可能存在"上一版遗留的 venv"。
- 若重装的是**同一版本、同一 wheel**（例如反复验同一个包），`jw_install_venv` 判定"版本 + 指纹一致"⇒ **跳过重建**。
- 于是你验的其实是"复用残留 venv 能不能跑"，**不是"全新安装能不能跑"**。安装流程里的坑（缺 python312、wheelhouse 不全、权限）在这一轮里根本不会暴露。
- 更隐蔽的变体：`python312` 被平台升级后，旧 venv 的 `pyvenv.cfg` 仍指向旧解释器，venv 实际不可用 —— `venv_usable` 会兜底重建，但如果你只看"应用起来了"就下结论，会把"重建成功"误读成"安装正常"。

结论（验收纪律）：
1. 验**安装流程**时，先删 `<var>/venv`（或换一个新版本号），保证走完整重建路径。
2. 验**升级流程**时，才允许保留 venv，并且必须看日志里的 `重建原因` 一行，确认它真的重建了。

### 3.6 为什么会踩坑

- "版本号"在直觉上等于"内容标识"，但**打过补丁的 wheel** 打破了这个假设——这正是本项目所有"改了不生效"问题的共同根因。
- 卸载残留 + 幂等跳过，会组合出"安装脚本没问题、但新装用户遇到的环境你没测到"的假阴性，比直接报错更难发现。

---

## 4. UDS 网关桥的设计

### 4.1 形态：纯统一网关，没有端口

```ini
# app/ui/config（入口）
gatewayPrefix = /app/jiuwenswarm
gatewaySocket = app.sock
# manifest 中不声明 service_port
```

链路：浏览器 → fnOS nginx（:5666）→ UDS `app.sock` → **桥** `uds_gateway.py` → `127.0.0.1:15173`（app_web，静态页 + `/api`）与 `/api`→`19000`、`/ws`→`19001`。`[实测]`

### 4.2 为什么必须是"纯字节流转发"

```python
# uds_gateway.py:196-212
async def _pipe(src, dst):
    while True:
        data = await src.read(CHUNK)
        if not data: break
        dst.write(data); await dst.drain()
```

桥只做三件事：**读头部 →（按需改写）→ 发头 → 双向 `_pipe`**。

- 若桥去"解析 HTTP 响应"，就必须处理 `Transfer-Encoding: chunked`、`101 Switching Protocols`、WS 帧（二进制、无 HTTP 语义）、SSE 长连接——任何一处处理不当都会静默截断。
- WS 握手成功的关键恰恰是**不要碰** `Upgrade` / `Connection`：

```python
# _build_head:194-208
if ws:
    if low in HOP_BY_HOP and low not in ("upgrade", "connection"):
        continue          # WS 时保留 Upgrade/Connection，其余 hop-by-hop 丢掉
else:
    if low in HOP_BY_HOP or low in tokens:
        continue
...
else:
    lines.append("Connection: close")   # 非 WS：一请求一连接
```

非 WS 强制 `Connection: close` 是为了防止 **keep-alive 下的第二个请求绕过前缀改写**（浏览器复用连接，第二个请求可能不带完整前缀语义）。`[静态]`

前缀处理只做字符串判断，并且拒绝 `..`（`_rewrite_target:140-157`）：

```python
if any(seg == ".." for seg in path.replace("\\", "/").split("/")):
    return None
if GATEWAY_PREFIX and path == GATEWAY_PREFIX:      path = "/"
elif GATEWAY_PREFIX and path.startswith(GATEWAY_PREFIX + "/"): path = path[len(GATEWAY_PREFIX):]
```

注意：**根路径原样透传，不拒绝**（`/` 本来就是合法目标）；`_rewrite_target` 返回 `None` 只在 `..` 或非 `/` 开头时发生。

### 4.3 socket 权限：默认 0666 + ACL 收紧到 0660

```python
# uds_gateway.py:689-740 附近
# 注意：必须在 start_unix_server 之后再 chmod，否则会被 umask 覆盖。
# 0600 + setfacl -m g:<gid>:rw 全部成功 → chmod 0660；任何一步失败 → 回 0666 + WARN。
```

三条硬经验：
1. **chmod 必须在 `start_unix_server()` 之后**（之前会被 `os.umask(0o077)` 覆盖，`uds_gateway.py:835`）。
2. 网关 worker 与 app 不同 uid（实测网关侧多个 uid），所以 `0600` 会让网关自己进不来。正确做法是 `0660 + setfacl -m g:<gid>:rw`（属主给任意组授权**不需要**自己是组成员）。
3. `setfacl` 缺失或执行失败 ⇒ **回退 0666 并 WARN**，不能"收紧失败就拒绝服务"——可用性优先，身份校验在 4.4 兜底。

### 4.4 peer 校验：exe 全路径 + root 属主 + 父目录非全局可写

```python
# uds_gateway.py:259-307  _peer_allowed(info)
if ALLOW_ANY_PEER:                      # JW_ALLOW_ANY_PEER=1 仅本地调试
    return True, "allow-any"
if uid == 0:                            # SO_PEERCRED 由内核填，不可伪造
    return True, "uid:0(root)"
if uid in GATEWAY_UIDS or gid in GATEWAY_GIDS:   # 降级白名单（跨用户读 /proc 会 EACCES）
    return True, f"uid-allowlist:{uid}"
real = info.get("real")
if not real:
    return False, f"no-exe uid={uid} gid={gid}"          # fail-closed
for pattern in PEER_ALLOWLIST:                            # glob，但**必须在 realpath 全路径上匹配**
    if fnmatch.fnmatch(real, pattern):
        if os.stat(real).st_uid != 0:                     # 属主必须是 root
            return False, f"exe-not-root:{real}"
        if os.stat(os.path.dirname(real)).st_mode & 0o002: # 父目录不能被任意用户写
            return False, f"parent-world-writable:{real}"
        return True, f"exe:{real}"
```

**为什么不能用 basename / comm**（这三条是这段代码存在的全部理由）：

| 判定方式 | 绕过手法 | 是否可用 |
|---|---|---|
| `comm`（`/proc/pid/comm`） | `prctl(PR_SET_NAME)` 任意进程可自报 `nginx`，且只有 16 字节 | ❌ 仅用于日志 |
| `os.path.basename(exe)` | `cp /usr/bin/python3 /tmp/nginx && /tmp/nginx` | ❌ |
| `exe` realpath 全路径 | 需要能写 root 属主路径 | ✅ + 属主校验 + 父目录校验（挡 `/tmp/nginx`） |

**顺序**：peer 判定必须在**读任何请求字节之前**（`_handle:514-556`）。
原因：本应用唯一的鉴权是"可信网关注入的 `X-Trim-Isadmin`"，而 `X-Trim-*` 任何本机进程都能伪造。只有先确认对端真的是网关进程，这个头才有意义。

`[实测]`：注入非网关进程连接 → 无响应直接 close；日志 `403 peer ... reason=exe-not-allowlisted:...`。

### 4.5 为什么会踩坑

- "socket 0666 太宽松"是第一直觉，直接改 0600 会让网关自己也进不来（不同 uid）——**权限问题的正解往往是 ACL，不是 mode**。
- peer 校验容易写成"basename 匹配 nginx"，看起来能过测试，实际可被一条 `cp` 绕过。
- 想"顺手修一下响应头 / 处理好 Content-Length"是最大的陷阱：一旦桥开始解析 HTTP，WS 与 chunked 就会陆续出问题。

---

## 5. WS Origin 校验的两次误判

### 5.1 误判一：以为"网关不支持 WebSocket"

**当初的判断**：`/ws` 握手失败 ⇒ fnOS 统一网关大概不支持 WS 升级。
**实际**：网关支持得很好，是**应用自己**拒了握手。`[实测]`

上游两层校验：

```python
# jiuwenswarm/channels/web/app_web.py:1597-1657
def _allowed_origin_hosts(cls) -> set[str]:
    raw = os.getenv("JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS") or ""
    hosts = {i.strip().lower() for i in raw.split(",") if i.strip()}
    hosts.discard("none")
    return hosts or set(cls._LOOPBACK_HOSTNAMES)      # 未配置 ⇒ 只认 127.0.0.1/localhost

def _ws_origin_allowed(self) -> bool:
    if not origin: return True                         # 非浏览器客户端
    if origin.lower() == "null": return False
    if origin_hostname in self._allowed_origin_hosts(): return True
    outer_host = self._clean_outer_host()              # Host
    ...
    if origin_hostname == host_hostname: return origin_port in (None, host_port)
    return origin_hostname in _LOOPBACK and host_hostname in _LOOPBACK
```

```python
# agent_gateway/common/security/ws_origin.py（wheel 内）
def is_origin_check_enabled() -> bool:
    return os.getenv("JIUWENSWARM_ENABLE_ORIGIN_CHECK", "").strip() == "1"
def is_allowed_browser_origin(origin):
    allowed = get_allowed_origin_hosts()          # 只按主机名匹配
    if origin is None: return "none" in allowed
    return (urlsplit(origin).hostname or "").lower() in allowed
```

模板 `.env` 里 `JIUENSWARM_ENABLE_ORIGIN_CHECK=1`（`jiuwenswarm/resources/.env.template:212`），而白名单基线是 `127.0.0.1,localhost,none` ⇒ **从设备 IP 打开页面时 Origin 是 `http://<NAS_IP>:5666`，不在白名单，直接 403**。

**推翻依据**：把设备 IP 加进 `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS` 后立刻 101；同时 `ws-origin.log` 里能看到 `origin='http://<NAS_IP>:5666'`。

**这里还有第二个坑：`.env` 会被上游重写。**
上游 `dotenv_early.load_dotenv_runtime(..., override=True)` 用 `config/.env` **覆盖**继承来的进程环境变量，
所以"在 supervisor 里 `os.environ[...]=...` 再起子进程"是无效的——必须**写进文件**：

```python
# app/server/supervisor.py:138-185  _ensure_env_allowlist()
env_file = Path(DATA) / "config" / ".env"      # 只增不减，保留用户已有条目
...
tmp.write_text(new_text); os.replace(tmp, env_file)   # 原子写
```

### 5.2 误判二：以为"只校验 Host 就够了"

有了 §5.1 的认知后，最自然的实现是：`Origin 主机 == Host 主机` ⇒ 同源。
**实际：fnOS nginx 转发到 UDS 桥时把 `Host` 改写成了回环地址**，原始主机名只在 `X-Forwarded-Host` 里。`[实测]`

于是"Origin（域名）vs Host（127.0.0.1）"永远不相等 ⇒ **IP 与域名一起 403**。
真机证据（0.2.9-12）：

| 事实 | 判据 |
|---|---|
| 只出现 `match-x-forwarded`，从未出现 `match-host` | `file ls logs/` → `ws-origin-last-match-x-forwarded.flag` |
| 判定确实执行了 | `ws-origin.log` 存在且非空（419 B，握手次数少但 >0） |
| 落到的是命中而非降级 | flag 名不是 `fallback` |

**这条"没出现"本身就是证据**：它证明"只信 `Host`"在 fnOS 网关上不可行，三头兜底（`X-Forwarded-Host` / `X-Original-Host` / `X-Forwarded-Server`）是必需设计，而不是"保险起见多加两个头"。

### 5.3 最终方案：桥内判定 + Origin 归一化

```python
# uds_gateway.py:448-513  _origin_decision(origin, headers) -> (allow, reason, branch)
host_items = _flatten_host_values([v for n, v in headers if n.lower() == "host"])
if len(host_items) > 1:                       # 多 Host：拒
    return False, f"multi-host({len(host_items)})", "deny-multi-host"
for item in host_items:
    if _split_host(item) is None:             # Host 含 @ / 路径 / 空白：拒
        return False, "invalid-host", "deny-invalid-host"
candidates = _usable_hosts(host_items)        # 非回环、可解析
mode = "host"
if not candidates:                            # Host 缺失或只剩回环 ⇒ 才用代理头
    candidates = _usable_hosts(_flatten_host_values([v for n, v in headers
                   if n.lower() in _PROXY_HOST_HEADERS]))
    mode = "x-forwarded"
if not candidates:                            # 一个可信候选都没有
    _FALLBACK_ALLOW_COUNT += 1
    print(f"[uds-gateway] WARN fallback-allow: ... (count={_FALLBACK_ALLOW_COUNT})")
    return True, "no-host-candidate(fallback-allow)", "fallback"
```

命中后，在 `_handle:600-605` 把 `Origin` **归一化**再交给上游：

```python
if origin:
    headers = [(k, "http://127.0.0.1" if k.lower() == "origin" else v) for k, v in headers]
```

为什么必须归一化：上游两层校验（§5.1）只按**主机名白名单**精确匹配，它永远不可能预知用户的访问域名；
而 `supervisor` 已把本机地址写进 `.env` 白名单，所以归一化成 `http://127.0.0.1` 能稳定通过。
**代价必须写清**：归一化 ⇒ 上游那两层校验在本链路上被**旁路**，真正的来源校验只剩桥这一层。

### 5.4 可观测性设计（比日志更重要的东西）

设备侧常常**读不到日志内容**（只能看文件名/大小），所以每次 WS 判定都写一个 0 字节的**分支标记文件**：

```python
# uds_gateway.py:369-387  _mark_ws_branch(branch)
# 先删所有旧 ws-origin-last-*.flag，再写 ws-origin-last-<branch>.flag
```

| 分支名 | 含义 |
|---|---|
| `match-host` | 用 `Host` 命中（**本机从未出现，见 §5.2**） |
| `match-x-forwarded` | 用代理头命中（本机实际分支） |
| `fallback` | 无可信候选，放行但打 WARN |
| `deny-multi-host` / `deny-invalid-host` / `deny-mismatch` / `deny-null` / `deny-path` / `deny-scheme` | 拒绝及其原因 |

再加两个"不需要读内容"的量：
- `logs/ws-origin.log` 的**存在性与大小** = 判定逻辑跑过（0 字节 ⇒ 一次都没跑）。
- 403 响应体直接回**六个值**，浏览器 DevTools 就能看到：`origin` / `host` / `x-forwarded-host` / `x-original-host` / `x-forwarded-server` / `reason`。

`ws-origin.log` 自身也做了保护：超过 200 KB 保留最近 200 行并写 rotated 标记（`_log_ws_origin:389-410`），不清空——避免把关键那几条冲掉。

### 5.5 为什么会踩坑（方法论）

- 两个误判都"读代码看起来完全合理"，只有**真机 flag + 403 响应体**能证伪。**先造可观测性，再改逻辑**，否则你连自己错在哪一步都不知道。
- 代理头这类"环境事实"（谁改写了哪个头）**不能靠文档推断**，必须在真机上让代码把它打印出来。
- 归一化是一种"用安全边界换可用性"的交易：**必须**在代码注释、交付文档、风险表三处同时写明"上游校验已旁路"，否则下一个人会把上游校验当成有效防线。

---

## 6. 卸载脚本的失效模式与验证判据

### 6.1 失效模式一：`source` 已被删除的目录 → 提前退出，一个文件都没删

```bash
# 错误写法（历史 bug）
. "${TRIM_APPDEST}/server/init_env.sh"     # 卸载阶段 TRIM_APPDEST 已被框架删除
set -u                                     # source 失败 + 变量未定义 → unbound variable → 立刻退出
```
**后果**：用户勾了"清除全部应用数据"，但脚本死在第一行，**没有任何删除动作**，平台仍显示卸载成功。`[实测]`

**解法**：卸载脚本**绝不 source target 下的任何脚本**（`cmd/uninstall_callback:5-7` 头注释把这条写成硬规则）；
而 install/upgrade 侧则必须"先判存在、再 source"：

```bash
# cmd/install_callback:11-21
INIT_ENV="${TRIM_APPDEST:-}/server/init_env.sh"
if [ ! -f "${INIT_ENV}" ]; then
  _msg="应用文件不完整：缺少 ${INIT_ENV}，无法继续（未修改任何数据）"
  echo "[jiuwenswarm] ERROR: ${_msg}" >&2
  [ -n "${TRIM_TEMP_LOGFILE:-}" ] && printf '%s\n' "${_msg}" >"${TRIM_TEMP_LOGFILE}"
  exit 1
fi
. "${INIT_ENV}"
```

### 6.2 失效模式二：向导参数形态不匹配 → 整段删除逻辑不执行

```bash
# 错误写法：只认字符串 "true"
if [ "${wizard_delete_data:-}" = "true" ]; then DELETE=1; fi
```
平台可能传 `true` / `True` / `TRUE` / `1` / `yes` / `on`（大小写与形态不定），只认一种就等于"所有用户的清除都不生效"。
这是一次 P0（用户以为删了，实际 `app.env` 里的 API Key 还躺在磁盘上）。`[实测]`

**解法**（`cmd/uninstall_callback:38-47`）：

```bash
case "$(printf '%s' "${wizard_delete_data-}" | tr '[:upper:]' '[:lower:]')" in
  true|1|yes|on|y) DELETE_DATA=1 ;;
  *) DELETE_DATA=0 ;;
esac
logline "uninstall: wizard_delete_data 原值='${wizard_delete_data-<未注入>}'"
logline "uninstall: 解析结果 wizard_delete_data=${DELETE_DATA}（1=清除，0=保留）"
```

**同时打印原值**——排查时"平台到底传了什么"是第一个要回答的问题，别让它只能靠猜。

### 6.3 失效模式三：把删除动作写成 fail-fast

删除 5 个路径时，第 2 个失败就 `exit 1` ⇒ 后 3 个（可能包含 `app.env`，隐私最敏感）永远不删。
**正解：fail-open**（`try_rm_app:79-95`）：逐项独立执行，失败只 WARN + 记入 `RESIDUAL`，继续下一项，最后汇总。

明确区分两类操作，**并且要按当前代码的实际行为写，不能按"应该怎样"写**
（这一条我按旧版记忆写错过一次，跑一遍才发现 v12 只有一处 `abort`）：

| 类别 | 实际行为（v12，`[实测]`） | 退出码 |
|---|---|---|
| `TRIM_PKGVAR` **未注入/为空** | **唯一真正的 fail-fast**：`abort "TRIM_PKGVAR 未注入…"`，未删除任何文件 | `1` |
| 单个目标路径非法（空 / 相对路径 / `/`） | **fail-open**：`WARN: 跳过 '<p>'（拒绝删除 /）`，计入 `RESIDUAL`，继续下一项 | `0` |
| 单个目标路径越界（不在 `*/jiuwenswarm*` 下） | **fail-open**：`WARN: 跳过 '<p>'（路径不在 jiuwenswarm 目录下）`，继续 | `0` |
| `rm -rf` 单项失败（权限等） | **fail-open**：`WARN: 未删除 '<p>'（rm 失败）`，继续 | `0` |

实测对照（`TRIM_PKGVAR=空` → `rc=1` 且未删；`TRIM_PKGVAR=/tmp/evil` 且该目录存在 → 6 项全部 `WARN 跳过`、
`已删除 0 项`、`rc=0`）。**"参数非法就立刻中止"只对 `TRIM_PKGVAR` 成立**，别把目标级校验也写成 abort——
那会让一个奇怪的路径把整次卸载卡死，隐私文件反而删不掉。

> 另一个实测细节：脚本末尾有 `rmdir -- "${VAR}"`（只在目录已空时成功）。
> 因此 `TRIM_PKGVAR` 指到**别人的空目录**时，该空目录会被删掉（无内容损失，但仍然是"删了不属于自己的路径"）。
> 这属于知情接受项，不在本次修复范围，记在这里以免后来人以为是 bug。

### 6.4 失效模式四：`exit 1` 让平台判卸载失败

**直觉**：脚本出问题应该返回非 0。
**实际**：卸载回调返回非 0 会被平台记为卸载失败（可能触发回滚/报错），比"有残留"更危险。
证据等级：`[静态]`（脚本注释 + 平台生命周期约定）＋ `[推断]`；**本项目没有专门用 `exit 1` 在真机上复现"平台报卸载失败"**，所以这一条按"平台契约"对待，不按"实测现象"引用。

**硬规则**：**始终 `exit 0`**（参数非法除外），把"删没删干净"写进 `TRIM_TEMP_LOGFILE` 让人看。

### 6.5 路径安全：`TRIM_PKGHOME=/` 会变成删 `/jiuwenswarm`

home 目录要放宽到"与 `TRIM_PKGVAR` 同名的兄弟目录"（`@apphome/jiuwenswarm` vs `@appdata/jiuwenswarm`），
但平台可能把 `TRIM_PKGHOME` 指到父目录，于是要拼候选路径——**候选路径必须重新过安全校验**：

```bash
# cmd/uninstall_callback:110-120
cand1="${p}/${want}"; cand2="$(dirname -- "${p}")/${want}"
[ -z "${c1_why}" ] && [ "$(dirname -- "${cand1}")" = "/" ] && c1_why="父目录为根"
[ -z "${c2_why}" ] && [ "$(dirname -- "${cand2}")" = "/" ] && c2_why="父目录为根"
[ -z "${c1_why}" ] && [ "$(basename -- "${cand1}")" != "${want}" ] && c1_why="basename 不符"
```

`TRIM_PKGHOME=/` ⇒ `cand2=//jiuwenswarm` ⇒ 解析为 `/jiuwenswarm` ⇒ 若没这条校验就会删根目录下的同名目录。
`[实测]`：`TRIM_PKGHOME=/` 与 `TRIM_PKGHOME=/tmp` 注入测试均未触碰 `/jiuwenswarm`，仅 WARN 跳过。

### 6.6 卸载验证的判据（这个坑值得单独记）

**唯一标准**：`@appdata/jiuwenswarm/app.env` 不存在。

理由：`install_callback` / `runtime.sh` 会**重建** `data/` 与 `home/`，所以"重装后看 data 在不在"永远为真，是无效判据；
而 `app.env` 没有任何脚本会主动创建（只在"文件不存在时"由 `install_callback` 生成一次），它是干净的探针。`[静态]`+`[实测]`

> 注意：**判据设计已完成并被本地注入测试覆盖，但"真机独立卸载"这一步尚未闭环**（见 §10）。
> 不要把"本地注入测试通过"写成"真机卸载已验证"。

### 6.7 可复现的注入测试（不需要真机）

```bash
cd swarm-fnos-app
# 场景矩阵：每个都在独立临时目录里准备 @appdata/@apphome 结构后执行
TRIM_PKGVAR=/tmp/t1/@appdata/jiuwenswarm TRIM_PKGHOME=/tmp/t1/@apphome/jiuwenswarm \
  wizard_delete_data=true bash cmd/uninstall_callback
# 期望：venv/logs/run/data/app.env 均删除；home 删除；rc=0

# 参数非法（fail-fast，未删任何东西）
TRIM_PKGVAR= bash cmd/uninstall_callback          # rc=1，提示未注入
TRIM_PKGVAR=/tmp/evil bash cmd/uninstall_callback # rc=1，路径越界

# 路径逃逸
TRIM_PKGVAR=/tmp/t2/@appdata/jiuwenswarm TRIM_PKGHOME=/ bash cmd/uninstall_callback
# 期望：WARN 父目录为根，/jiuwenswarm 未被触碰

# 残留形态（fail-open）
chmod 500 /tmp/t3/@appdata/jiuwenswarm/data       # 让它删不掉
# 期望：WARN 未删除，其余照删，rc=0
```

### 6.8 为什么会踩坑

- `source` + `set -u` 的组合会在"目录已被删除"的场景下静默中断，而卸载脚本恰恰**总在目录被删之后运行**——这是结构性陷阱，不是笔误。
- "参数只认 `true`"看起来严谨（严格的等值判断），但对平台注入值一无所知时，**严格 = 失效**。
- `exit 1` 直觉上"更诚实"，但在这个平台上诚实的方式是**日志**，不是退出码。

---

## 7. 构建流程防御

### 7.1 新鲜度闸门：防"改了代码但打进旧包"

**事故原型**：`supervisor.py` 在 17:24 改好，但 `.fpk` 是 17:06 打的；设备上跑的是旧文件，导致整整一轮排查指向错误方向。`[实测]`

**闸门**（`scripts/verify-package-freshness.py`）：

```bash
python3 scripts/verify-package-freshness.py jiuwenswarm-0.2.9-12.fpk .
# 逐个比对 MONITORED 列表里的文件：包内 sha256 == 工作区 sha256
# 不一致 → 打印差异条目 → exit 1
```

覆盖 `cmd/*`、`app/ui/config`、`app/server/*.py|*.sh`。`build-fpk.sh:131-134` 在产出后立即调用，不一致就拒绝交付。

**为什么只能靠 sha**：逻辑 review 看不出"这个包里的文件和工作区不是同一份"，时间戳也可能被硬链接/复制弄乱——只有逐字节比对能抓到。

### 7.2 补丁闸门：防"静默打出未修复的包"

```bash
# build-fpk.sh:43-48
python3 scripts/patch-app-web-csp.py app/wheelhouse            # 先打（幂等）
python3 scripts/patch-app-web-csp.py app/wheelhouse --check     # 再断言
# 补丁脚本匹配不到 OLD 常量（上游改了这行）→ exit 1 → 构建中止
```

设计要点：**"匹配不到"必须当作错误**，而不是"跳过补丁继续构建"。
上游一改动，`frame-ancestors` 这行可能换写法，此时最危险的行为是"包能打出来、但补丁没生效"。

### 7.3 源码仓只读

```bash
git -C ../jiuwenswarm status --porcelain    # 构建前后都必须为空
```
所有补丁都在**构建产物（wheel）层**做，且每个补丁脚本都要重算 zip 内的 `RECORD`。
好处：上游可随时 `git pull` 更新，不需要维护 fork；坏处：补丁与上游行号耦合 ⇒ 用 7.2 的闸门兜住。

### 7.4 打包纪律

| 规则 | 理由 |
|---|---|
| 除 P0 不重打包 | 每打一次包就产生一个新 sha，验证证据与包的对齐关系全部要重做 |
| 文档不在 `.fpk` 内 | 改文档不影响包 sha，"文档同步"与"出包"是两件事 |
| 只改日志/可观测性不出包 | 收益小于"证据失效"的代价，攒到下一次实质改动 |
| 判"实质改动"看是否影响：功能可用性 / 安全边界 / 数据安全 | 三者任一命中才算 P0/P1 |

### 7.5 fnpack 的两个环境坑

1. **`fnpack build` 把 `.fpk` 写到当前工作目录，与 `-d` 参数无关** ⇒ 必须在暂存目录里 `cd` 再执行（`build-fpk.sh:92-96`）：

```bash
( cd "${STAGE}" && "${FNPACK}" build --nosign )
```

2. **/tmp 可能满** ⇒ 构建时显式指定临时目录：

```bash
TMPDIR=$HOME/fnpack-tmp FNPACK=/tmp/fnpack bash scripts/build-fpk.sh
BUILD_PROFILE=appstore TMPDIR=$HOME/fnpack-tmp FNPACK=/tmp/fnpack bash scripts/build-fpk.sh
```

3. **暂存目录用硬链接**（`cp -al`）避免每次复制 468 MB wheelhouse；改 manifest 前先删再写以**打断硬链接**，保证不污染工作区。

### 7.6 为什么会踩坑

- 构建脚本的**副作用**（写 cwd、吃 /tmp、改 manifest）都在"构建成功"时不可见，只在失败或对比 sha 时暴露。
- "包能打出来"被误当成"包是对的"。这两个判断之间需要一个独立的、**能失败的**校验（sha 比对 + profile 断言）。

---

## 8. 被推翻的初始判断（过程留档）

> 这一节比结论更重要：**每一个"我以为"都曾经是一个看起来很合理的实现**。

| # | 我以为 | 实际是 | 推翻依据 |
|---|---|---|---|
| 1 | 网关不支持 WebSocket 升级 | 网关支持；是应用 origin 白名单不含设备 IP 才 403 | 把设备 IP 加进 `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS` 后立刻 101 `[实测]` |
| 2 | 同源判定用 `Origin == Host` 就够 | nginx 改写了 `Host`，永远不等；必须靠 `X-Forwarded-Host` 兜底 | 真机 flag 从未出现 `match-host`，只出现 `match-x-forwarded` `[实测]` |
| 3 | 卸载后看 `data/`、`home/` 在不在就知道清没清 | 平台重装/安装会重建这两个目录，判据恒真；唯一干净探针是 `app.env` | 设备侧实测"重装清空 `@appdata/<app>/data`"（`[实测-设备侧]`）+ `install_callback`/`runtime.sh` 会 `mkdir -p` 重建（`[静态]`） |
| 4 | 卸载脚本出错应 `exit 1` | 退出码非 0 会让平台判卸载失败/回滚，比残留更危险 | `[静态]` 脚本硬规则 + 平台生命周期契约；**未用 `exit 1` 真机复现** `[未验证]` |
| 5 | 版本号相同 ⇒ venv 无需重建 | 补丁改了 wheel 内容但不动版本号 ⇒ 升级用户继续跑旧代码 | venv 内 `app_web.py` 仍是 `'none'`，指纹不同 `[实测]` |
| 6 | iframe 白屏要补 `connect-src` | 该 CSP 本来就没有 `connect-src`，问题在 `frame-ancestors 'none'`；补 `connect-src` 是收紧且可能拦断 WS | `curl -sI` 响应头只有 `frame-ancestors` `[实测]` |
| 7 | socket 0666 太宽，直接改 0600 | 网关 worker 与 app 不同 uid，0600 会把自己锁在外面；正解是 `0660 + setfacl`，失败回退 0666 | 网关连接被拒 + 多 uid 实测 `[实测]` |
| 8 | peer 校验匹配进程名（`comm`/basename）就够 | 可被 `cp /usr/bin/python3 /tmp/nginx` 与 `prctl` 伪造；必须 realpath 全路径 + root 属主 + 父目录非全局可写 | 构造伪造进程连接成功 `[实测]` |
| 9 | 多 `Host` 一律拒绝是必要的硬化 | 反代可能追加 `Host`，一律拒会误伤正常访问；改为"任一可解析非回环候选与 Origin 匹配即放行" | 审查指出误伤场景（R13），改为任一匹配 `[推断]`+审查结论 |
| 10 | 只要进程环境变量设了 allowlist 就生效 | 上游 `dotenv load(override=True)` 用 `config/.env` 覆盖进程环境 ⇒ 必须写文件 | 子进程仍读到模板默认值 `[实测]` |

---

## 9. 可直接抄的检查清单

### 9.1 接入统一网关（新应用自检）

- [ ] `gatewayPrefix` / `gatewaySocket` 正确，manifest **不写** `service_port`（除非真要端口型）
- [ ] 桥在 `start_unix_server()` **之后** chmod；不能 chmod 时回退 0666 + WARN
- [ ] peer 判定在**读请求字节之前**；exe 用 realpath 全路径 + 属主 + 父目录校验；读不到 → deny
- [ ] WS 场景：`Host` 改写 + `Origin` 处理策略明确（是否归一化、旁路了哪一层校验，写进注释）
- [ ] 前缀剥离只做字符串判断，拒绝 `..`；非 WS 强制 `Connection: close`
- [ ] 每次判定写**分支标记文件**（0 字节，文件名即结论）+ 一个可读的拒绝响应体

### 9.2 生命周期脚本自检

- [ ] 卸载脚本**不 source** 任何 target 下脚本
- [ ] install/upgrade 侧先 `[ -f ]` 再 `source`
- [ ] 向导布尔参数**归一化**（`true/1/yes/on`，忽略大小写），并打印原值
- [ ] 参数校验 fail-fast（**仅限 `TRIM_PKGVAR` 未注入**）；目标级异常与删除动作一律 fail-open；**退出码恒 0**
- [ ] 所有删除目标过 `_unsafe_reason`（绝对路径、非 `/`、位于应用目录下）
- [ ] 候选路径（父目录回退）**重新校验**：父目录不能是 `/`、basename 必须匹配
- [ ] 幂等：连续两次 install/start 不产生重复副作用

### 9.3 构建自检

- [ ] 源码仓 `git status --porcelain` 为空
- [ ] 补丁脚本有 `--check`，匹配不到就 `exit 1`
- [ ] 产物过 `verify-package-freshness.py`（逐字节）
- [ ] profile 断言：测试包无 `install_dep_apps`，上架包必须有
- [ ] `TMPDIR` 指向大分区；暂存目录硬链接；改 manifest 先删再写
- [ ] 记录产物 `ls -l` 字节数与 `sha256sum`（**同一批命令内取**，避免字节数与 sha 来自不同次构建）

### 9.4 版本/升级自检

- [ ] venv 里记录 wheel sha256，判定条件是"版本 **且** 指纹"双一致
- [ ] 跳过重建时打印 `已就绪（…sha…）`；重建时打印 `重建原因：版本变化 / wheel sha 变化`（分开写）
- [ ] 启动前再比一次指纹（覆盖"装完没启动"场景）
- [ ] 验"全新安装"前先删 `<var>/venv`，否则验的是复用残留

---

## 10. 本文件覆盖不到 / 未验证的部分

| 项 | 状态 | 说明 |
|---|---|---|
| 上架包在应用中心 UI 安装（依赖 `python312` 自动安装） | **未验证** | 只有命令行测试包被真机验证过 |
| `upgrade_callback`「保留数据升级」通道 | **未验证** | CLI 对已装应用直接 `10236` 拒绝；应用不在商店，无更新入口。用户文档不承诺此能力 |
| 卸载「清除全部应用数据」真机闭环 | **未验证**（代码已修，v10 起） | 判据 `@appdata/jiuwenswarm/app.env` 不存在；等真实卸载时确认 |
| 外网中继（`*.fnos.net`）后续固件是否继续带 `X-Forwarded-*` | **未验证** | 若某天只剩回环值，会退化为 `fallback`（有 WARN + flag 可见，功能不退化） |
| `Origin` 端口越界（`:99999`）显式 deny | **已知项** | 当前由外层 `except` 兜住并关连接：fail-closed、无安全后果，但 deny 原因读不出 |
| `Origin` 侧未做 `@`/路径校验 | **已知项** | Host 侧已做；两侧语义应对称化（待办） |
| `favicon` 根路径常量 | **已知项** | `/favicon.png` 可能 404，不影响功能 |

---

## 附录 A：关键文件索引

| 文件 | 作用 | 关键符号 |
|---|---|---|
| `app/server/uds_gateway.py` | UDS 网关桥（唯一入口） | `_peer_allowed` `_rewrite_target` `_build_head` `_pipe` `_origin_decision` `_mark_ws_branch` |
| `app/server/supervisor.py` | 三子进程管理、日志轮转、`.env` 白名单注入 | `_local_ipv4_addresses` `_ensure_env_allowlist` `_rotate_launcher_log` |
| `app/server/runtime.sh` | venv 安装/重建（幂等 + 指纹） | `jw_wheel_fingerprint` `jw_venv_fingerprint_ok` `jw_install_venv` |
| `app/server/init_env.sh` | 环境探测、`app.env` 纯解析与键白名单 | — |
| `cmd/main` | start/stop/status；启动前校验指纹 | `start_process` |
| `cmd/install_callback` | 数据目录准备 + 离线安装 | 前置检查后 `source` |
| `cmd/uninstall_callback` | 卸载清理（三句话原则） | `_unsafe_reason` `try_rm_app` `try_rm_home` |
| `scripts/build-fpk.sh` | 双 profile 构建 + 三道闸门 | manifest 重写 / profile 断言 / 新鲜度 |
| `scripts/patch-app-web-csp.py` | CSP 定点补丁（含 RECORD 重算） | `TARGET` `OLD` `NEW` `--check` |
| `scripts/verify-package-freshness.py` | 包内 vs 工作区逐字节比对 | `MONITORED` |

## 附录 B：命令速查

```bash
# 构建（测试包 / 上架包）
TMPDIR=$HOME/fnpack-tmp FNPACK=/tmp/fnpack bash scripts/build-fpk.sh
BUILD_PROFILE=appstore TMPDIR=$HOME/fnpack-tmp FNPACK=/tmp/fnpack bash scripts/build-fpk.sh

# 校验包内文件是否等于工作区
python3 scripts/verify-package-freshness.py jiuwenswarm-0.2.9-12.fpk .

# 断言 CSP 补丁在 wheel 内生效
python3 scripts/patch-app-web-csp.py app/wheelhouse --check

# 本地跑桥的 origin 判定（不启服务）
python3 - <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("m", "app/server/uds_gateway.py")
m = importlib.util.module_from_spec(spec); sys.modules["m"] = m; spec.loader.exec_module(m)
H = lambda n, v: (n, v)
cases = [
    ("域名正常",      "https://nas.example.com",   [H("Host","127.0.0.1:15173"), H("X-Forwarded-Host","nas.example.com:5667")]),
    ("跨站伪造",      "https://evil.com",          [H("Host","127.0.0.1:15173"), H("X-Forwarded-Host","nas.example.com")]),
    ("多 Host",       "https://evil.com",          [H("Host","a.example.com"), H("Host","evil.com")]),
    ("@ 混淆",        "https://evil.com",          [H("Host","nas.example.com:5667@evil.com")]),
    ("回环 + 无代理头", "https://evil.com",         [H("Host","127.0.0.1:15173")]),
]
for name, origin, hs in cases:
    print(name, "->", m._origin_decision(origin, hs))
PY

# 卸载清理注入测试（示例：清除）
# 注意：逐条 mkdir，不要用 {a,b,c} 花括号（某些执行环境不展开，会造出一个字面量目录，误导判读）
rm -rf /tmp/t1
mkdir -p /tmp/t1/@appdata/jiuwenswarm/venv   /tmp/t1/@appdata/jiuwenswarm/data
mkdir -p /tmp/t1/@appdata/jiuwenswarm/logs   /tmp/t1/@appdata/jiuwenswarm/run
mkdir -p /tmp/t1/@appdata/jiuwenswarm/pycache /tmp/t1/@apphome/jiuwenswarm
echo "key=1" > /tmp/t1/@appdata/jiuwenswarm/app.env

TRIM_PKGVAR=/tmp/t1/@appdata/jiuwenswarm \
TRIM_PKGHOME=/tmp/t1/@apphome/jiuwenswarm \
wizard_delete_data=True bash cmd/uninstall_callback; echo "rc=$?"
find /tmp/t1 -mindepth 1        # 期望只剩 /tmp/t1/@appdata 与 /tmp/t1/@apphome

# 实测输出（v12）：
#   wizard_delete_data 原值='True' → 解析结果 =1（大小写归一化生效）
#   已删除 app.env / @apphome/jiuwenswarm / data / venv / logs / run / pycache
#   清理汇总：已删除 7 项
#   rc=0
```

期望值速查（`_origin_decision`，附录 B 第一段脚本的实测输出）：

| 用例 | 返回 |
|---|---|
| 域名正常（Host=回环 + `X-Forwarded-Host`=域名） | `(True, 'match:nas.example.com:5667', 'match-x-forwarded')` |
| 跨站伪造 | `(False, 'origin-host-mismatch', 'deny-mismatch')` |
| 多 Host | `(False, 'multi-host(2)', 'deny-multi-host')` |
| `@` 混淆 | `(False, 'invalid-host', 'deny-invalid-host')` |
| 回环 Host 且无代理头 | `(True, 'no-host-candidate(fallback-allow)', 'fallback')` + 一条 `WARN fallback-allow` |
