# JiuwenSwarm for 飞牛 fnOS

把 [JiuwenSwarm](https://gitcode.com/openJiuwen/jiuwenswarm)（多智能体协作 + Skill 自演进的工作台，Python 后端 + 前端 SPA + WebSocket）
封装成**飞牛 fnOS 原生应用包（`.fpk`）**的适配工程。

本仓库只做 **fnOS 适配层**：应用包结构、生命周期脚本、统一网关入口与 UDS 桥、离线依赖打包。
不修改上游业务代码。

| 项 | 值 |
|---|---|
| 应用包版本 | `0.2.9-12` |
| 上游 JiuwenSwarm | `0.2.9b5`（[gitcode](https://gitcode.com/openJiuwen/jiuwenswarm) @ 提交 `7b95d38f2ac56acc5efe07e17e371cc3a8804376`） |
| 目标平台 | `x86`（x86_64）／ CPython 3.12 |
| fnOS 最低版本 | `1.1.3100`（`manifest.os_min_version`） |
| 访问模型 | 纯统一网关（`gatewayPrefix=/app/jiuwenswarm` + `gatewaySocket=app.sock`），**不声明 `service_port`** |
| 许可 | 上游 Apache-2.0；本适配层同上（上游 `LICENSE` 随上游源码分发，本仓库不重复存放） |

---

## 1. 这是什么、为什么这么做

JiuwenSwarm 本身是一个"本机跑的 Web 服务"：进程监听几个 `127.0.0.1` 端口，浏览器直接访问。
fnOS 要求的是另一种形态——**应用包 + 平台托管生命周期 + 平台网关入口 + 可离线安装**。两者之间有 5 个必须补齐的缺口：

| 缺口 | 本仓库的做法 | 详见 |
|---|---|---|
| 没有 `.fpk` 结构 | `manifest` / `config/privilege` / `config/resource` / `cmd/` 生命周期 / `wizard/` 卸载向导 / `app/ui/config` 入口 | §4 |
| 只能在浏览器里直接连端口 | 统一网关 + Unix Socket 桥（`app/server/uds_gateway.py`），对平台只暴露 `app.sock`，**不开任何 LAN 端口** | §6 |
| 装依赖要联网 | 262 个 wheel 全量离线进包，安装期 `pip install --no-index`；只依赖平台应用 `python312` | `docs/BUILD.md` |
| 门户 iframe 里白屏 | 在 wheel 层把上游 CSP `frame-ancestors 'none'` 改为 `'self'`（`scripts/patch-app-web-csp.py`） | §8 |
| 前端写死根路径 `/logo.svg`、WS 同源校验拒网关域名 | wheel 层补 logo 前缀；桥内做 Origin 判定 + 归一化 | §8 |

一句话：**上游代码不动，所有适配都落在包结构、生命周期脚本、网关桥与构建期 wheel 补丁上**。

---

## 2. 当前状态（先看这张表，别把"未验证"当"已验证"）

| 能力 | 状态 | 说明 |
|---|---|---|
| 构建 `.fpk`（应用中心包，唯一产物） | **已验证（构建机实测）** | 2026-11-27 CI run `46028608438` 单包链路端到端成功（9m24s），唯一产物 `jiuwenswarm-0.2.9-12.fpk`；历史双包形态自 0.2.9-12 起取消 |
| 真机安装（命令行 `install-fpk`） | **已验证（历史事实）** | 0.2.9-12 测试包经命令行安装验证（该测试包已停止构建） |
| 真机启动 / 入口 / 管理员门禁 | **已验证** | `version=0.2.9-12`、`running`、入口 `/app/jiuwenswarm` |
| 门户 iframe 打开 | **已验证** | 修 CSP 后不白屏 |
| IP 访问下 WebSocket 对话 | **行为层已验证（双向收发成功）**；`101` 协议层**未取得** | 用户侧能对话、桥侧分支标记命中；无有效会话时请求停在网关鉴权层，抓不到握手响应（见 §8.3 与下行） |
| 域名 / DDNS 访问下 WebSocket | **已验证（fnos DDNS，行为层）** | 需网关转发 `X-Forwarded-*`；**其他自定义域名（含内网 `*.local`）未单独实测**，机制上同走代理头分支，见 §8 |
| `/ws` 返回 `101` 的**协议层**证据 | **未取得** | 无有效会话时请求停在网关鉴权层，抓不到握手响应；当前结论只到「双向收发成功」的行为层，见 §8.3 |
| 应用中心 UI 安装（唯一产物，依赖 `python312` 自动安装） | **未验证** | 唯一产物 `jiuwenswarm-0.2.9-12.fpk` 已构建成功，待真机经应用中心 UI 安装验证 |
| 「保留数据升级」通道（`upgrade_callback`） | **未验证（通道本身不成立）** | 本应用不在商店，CLI 对已装应用直接拒（`10236`），无更新入口 |
| 卸载「清除全部应用数据」 | **代码已修，真机未重验** | 0.2.9-10 起修（参数归一化 + fail-open + 恒 `exit 0`）；判据见 §9 |
| 飞牛外网中继域名（厂商 DDNS）后续固件是否继续带 `X-Forwarded-*` | **未验证** | 若不再带，桥会降级为 `fallback` 放行 + WARN（功能不退化，本地防线不生效） |
| 长文本流式 / 大文件下载被网关超时或体积截断 | **未压测** | — |

> 完整未验证清单与知情接受项见 `docs/RELEASE-CHECKLIST.md` 与 `docs/APPSTORE-MATERIALS.md`。

---

## 3. 仓库结构

```
.
├── manifest                 # 应用元信息（appname / version / platform / install_dep_apps …）
├── ICON.PNG / ICON_256.PNG  # 包根图标（64×64 / 256×256，fnpack 打包必需）
├── config/
│   ├── privilege            # 运行身份：package（非 root）
│   └── resource             # 资源声明（本应用无额外资源需求）
├── cmd/                     # 生命周期脚本
│   ├── main                 #   start / stop / status
│   ├── install_init / install_callback
│   ├── upgrade_init / upgrade_callback
│   ├── uninstall_init / uninstall_callback
│   └── config_init / config_callback
├── wizard/uninstall         # 卸载向导（是否清除数据）
├── app/
│   ├── ui/config            # 入口声明（iframe / gatewayPrefix / gatewaySocket）
│   ├── ui/images/           # 入口图标 icon_64.png / icon_256.png
│   └── server/
│       ├── init_env.sh      # 环境探测（python312）、app.env 纯解析
│       ├── runtime.sh       # venv 幂等安装 / wheel 指纹 / 数据目录准备
│       ├── supervisor.py    # 拉起三个子进程、日志轮转、WS 白名单注入
│       ├── uds_gateway.py   # 统一网关 UDS 桥（peer 校验 / WS Origin / 静态特例）
│       ├── detect_gateway_uid.py
│       └── VERSION          # 上游 pip 版本（0.2.9b5）
├── scripts/                 # 构建与校验脚本（见 docs/BUILD.md）
├── requirements/
│   └── wheelhouse-manifest.txt   # 262 个 wheel 的文件名/版本/sha256（二进制不入库）
├── docs/
│   ├── BUILD.md             # 完整构建链路
│   ├── APPSTORE-MATERIALS.md# 上架材料字段映射与体积/峰值数据
│   ├── RELEASE-CHECKLIST.md # 43 项上架门禁（检查方法 / 判据 / 证据形式）
│   └── fix-log/             # 各版本脚本快照与图标变更记录
└── knowledge-base/          # 实战经验（方法论向，非构建必需）
```

**不在仓库里的东西**（`.gitignore` 已覆盖）：`.fpk`、`app/wheelhouse/*.whl`、`*.tgz`、`__pycache__`、
`app.env` / `.env`、`venv/`、`logs/`、上游源码 `jiuwenswarm/`。

---

## 4. 应用包结构（外部人最常问的部分）

| 文件 | 作用 | 关键点 |
|---|---|---|
| `manifest` | 平台识别应用 | `platform=x86`；`os_min_version=1.1.3100`；`checkport=false`；`ctl_stop=true`；`install_dep_apps=python312`（上架形态，唯一产物） |
| `config/privilege` | 运行身份 | `run-as: package`，全程非 root |
| `config/resource` | 资源声明 | `{}` —— 本应用不申请共享目录、不申请硬件 |
| `app/ui/config` | 桌面入口 | `type: iframe`、`gatewayPrefix: /app/jiuwenswarm`、`gatewaySocket: app.sock`、`allUsers: false`（仅管理员） |
| `wizard/uninstall` | 卸载向导 | 单选 `wizard_delete_data`：默认 `false`（保留数据） |
| `cmd/*` | 生命周期 | 全部幂等；`status` 运行返回 0、未运行返回 3 |

**为什么没有 `service_port`**：应用走统一网关，平台只通过 `app.sock` 访问，不需要对外端口。
`checkport=false` 是同一决策的另一半——不要让平台去探测一个不存在的端口。

---

## 5. 前置条件

### 5.1 构建机

| 项 | 要求 | 用途 |
|---|---|---|
| 架构 | **x86_64 Linux** | wheel 必须 manylinux x86_64 / 纯 py；目标设备同为 x86_64 |
| Python | **3.12.x** | 与设备 `python312` 对齐，wheel 标签 `cp312` |
| Node.js | ≥ 20 | 仅构建期（前端 `npm run build`） |
| npm / git | 可用 | 前端依赖、`gitcode.com` 源依赖 |
| 网络 | 可访问 PyPI 镜像与 `gitcode.com` | **仅构建机**；安装期与运行期完全离线 |
| fnpack | 1.3.3 | `curl -fL https://static2.fnnas.com/fnpack/fnpack-1.3.3-linux-amd64 -o fnpack && chmod +x fnpack` |
| 磁盘 | ≥ 10 GB 空余 | wheelhouse 约 468 MB、`.fpk` 约 482 MB、暂存目录与 `/tmp` |

### 5.2 目标设备

| 项 | 要求 |
|---|---|
| fnOS | ≥ `1.1.3100`，x86_64 |
| 运行时依赖 | 应用中心已安装 **`python312`**（缺失时 `cmd/main start` 会写明确错误并 `status=3`，不会起半截） |
| 权限 | 仅 **NAS 管理员**可用（`allUsers=false` + 网关注入 `X-Trim-Isadmin` 判定） |
| 空间 | 安装卷 ≥ 1 GB（wheelhouse 468 MB + target）；数据卷 ≥ 5 GB（venv 约 2 GB + 首启 data） |

---

## 6. 构建

完整链路见 **[`docs/BUILD.md`](docs/BUILD.md)**。三条命令概括：

```bash
# 0) 取上游源码（放在本仓库同级目录，或用 JIUWENSWARM_SRC 指定）
git clone https://gitcode.com/openJiuwen/jiuwenswarm ../jiuwenswarm
git -C ../jiuwenswarm checkout 7b95d38f2ac56acc5efe07e17e371cc3a8804376   # 0.2.9b5

# 1) 构造载荷：前端 dist + 262 个离线 wheel（联网，约 20–40 分钟）
bash scripts/build-payload.sh

# 2) 打 .fpk（自动跑 CSP / logo 补丁闸门 + manifest 断言 + 新鲜度校验；唯一应用中心档位）
TMPDIR=$HOME/fnpack-tmp FNPACK=/path/to/fnpack bash scripts/build-fpk.sh
```

产出的唯一包为**应用中心包**：

| 产物 | `install_dep_apps` | 适用通道 |
|---|---|---|
| `jiuwenswarm-0.2.9-12.fpk`（应用中心包，唯一产物） | `python312` | **仅应用中心 UI**（命令行安全闸会拦截带依赖的包；历史测试包与 CLI 安装通道已随单包化决策取消） |

> 说明：`fnpack build` 把产物写到**当前工作目录**（与 `-d` 无关），`scripts/build-fpk.sh` 已在暂存目录内 `cd` 后再执行；
> 暂存目录用硬链接复制（`cp -al`），不会复制 468 MB 的 wheelhouse。

---

## 7. 安装到设备

### 7.1 普通用户路径（推荐，无需命令）

1. 应用中心 → **手动安装** → 选择 `.fpk`（唯一产物，manifest 已声明 `install_dep_apps=python312`）；
2. 若提示缺运行时：先在应用中心安装 **`python312`**，再重试；
3. 安装完成后应用会自动启动（设备默认 `autoRunNewApp=true`）；
4. 用**管理员账号**登录 fnOS，点桌面 JiuwenSwarm 卡片。

### 7.2 命令行路径（历史通道，已不可用）

> 历史事实：以下命令仅对已停止构建的历史测试包（0.2.9-12 及以前的双包形态）验证过。
> 单包化后唯一产物含 `install_dep_apps=python312`，CLI `app install-fpk` 会触发安全闸拦截（带依赖的包），
> 真机安装统一走 §7.1 应用中心 UI 手动安装。

```bash
app install-fpk jiuwenswarm-0.2.9-12.fpk --volume-id 1 --dry-run        # 预演，不落盘
app install-fpk jiuwenswarm-0.2.9-12.fpk --volume-id 1 --accept-license # 正式安装
app status jiuwenswarm        # 期望 version=0.2.9-12、running
app entry list | grep jiuwenswarm   # 期望 /app/jiuwenswarm
```

- 设备 `<NAS_IP>` 换成你自己的地址，例如入口 `http://<NAS_IP>:5666/app/jiuwenswarm`。
- 未签名包若被拒，需导入开发者证书重签（`SIGN=1 bash scripts/build-fpk.sh`）。
- **已安装应用再 `install-fpk` 会被拒**（返回 `{"code":10236}`，无 force/overwrite）：卸载后重装，或用应用中心手动安装覆盖。

### 7.3 首次启动

首次打开会自动补齐工作区：`config/config.yaml`、`config/config-gateway.yaml`、`config/.env`、agent 模板与语言文件。
在左侧「配置信息」填模型服务（Provider / API Key / 模型名）。**API Key 只写本机数据目录，不随包分发**。

---

## 8. 访问模型与关键机制

### 8.1 网关链路

```
浏览器 ──► fnOS nginx (:5666/:5667, 登录态 + 管理员判定)
        ──► Unix Socket  $TRIM_APPDEST/app.sock
        ──► 桥 app/server/uds_gateway.py
              ├──► 127.0.0.1:15173  app_web（静态页 + /api 反代）
              ├──► 127.0.0.1:19000  WebChannel（/api）
              └──► 127.0.0.1:19001  Gateway（/ws）
```

### 8.2 桥的三条设计约束

1. **只解析头部，其余原样字节转发**。桥读 `\r\n\r\n` 之前的部分（≤64 KB，15 s 超时），改写 `Host` 后把请求体、WS 帧、chunked 响应全部 `_pipe` 透传——一旦桥开始"理解" HTTP 响应，`101 Switching Protocols` 与 WS 帧就会出问题。
2. **对端身份判定早于读任何请求字节**。`SO_PEERCRED` 取 pid/uid/gid，再按 `/proc/<pid>/exe` 的 **realpath 全路径**匹配白名单，并要求该文件 **root 属主**、父目录 **不可被普通用户写**。读不到 `exe` 直接拒绝（fail-closed）。原因：本应用唯一的鉴权是网关注入的 `X-Trim-Isadmin`，而这类头任何本机进程都能伪造。
3. **socket 默认 0666，能收紧才收紧**。配置 `JW_GATEWAY_GID` 后启动时用 `setfacl -m g:<gid>:rw` 授权并 chmod `0660`；`setfacl` 缺失或失败一律**回退 0666 + WARN**（绝不半收紧，否则网关 worker 会被锁在门外）。chmod 必须在 `start_unix_server()` 之后执行，否则被 umask 覆盖。

### 8.3 WebSocket 的来源校验（这段是踩坑最多的地方）

浏览器的 WS 握手一定带 `Origin`。上游有两层校验，都只按**主机名白名单**精确匹配：

- `app_web`（15173）：`Origin` 主机 == `Host`，或落在 `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS`；
- `agent_gateway`：`JIUENSWARM_ENABLE_ORIGIN_CHECK=1` 时，`Origin` 主机必须在同一白名单里。

**但 fnOS 的 nginx 转发到 UDS 桥时会把 `Host` 改写成回环地址**，原始主机名只出现在 `X-Forwarded-Host`。
于是"`Origin`（设备 IP 或域名）vs `Host`（127.0.0.1）"永远不相等 ⇒ 403、页面能开但聊天一直断。

本工程的解法（`app/server/uds_gateway.py`）：

1. 桥内判定 `Origin` 是否与**用户实际访问的主机**一致：`Host` 优先（且必须恰好一个、可解析）；仅当 `Host` 缺失或只剩回环时才用 `X-Forwarded-Host` / `X-Original-Host` / `X-Forwarded-Server` 兜底；
2. 通过后把 `Origin` **归一化**为 `http://127.0.0.1` 再交给上游（上游白名单里本就有回环）；
3. 一个可信候选都没有 ⇒ 放行但打 `WARN fallback-allow` 并计数；
4. 每次判定写一个 **0 字节标记文件** `logs/ws-origin-last-<branch>.flag`（`match-host` / `match-x-forwarded` / `fallback` / `deny-*`），并把被拒时的六个值（`origin/host/xfh/xoh/xfs/reason`）写进 403 响应体——设备上读不到日志内容时，看**文件名**就知道走到哪一步。

> 代价必须说清：归一化意味着上游那两层校验在本链路上被**旁路**，真正的来源校验只剩桥这一层；
> 若走到 `fallback`，两层同时失效（此时功能优先，风险由"域 Cookie + 网关注入身份头 + 管理员门禁"兜底）。

### 8.4 前端资源与 CSP

上游产物里有两处不适合网关前缀的硬编码，均在 **wheel 层**打补丁（源码仓只读）：

| 问题 | 补丁 | 效果 |
|---|---|---|
| 顶层文档 `Content-Security-Policy: frame-ancestors 'none'` | `scripts/patch-app-web-csp.py` → `'self'` | 门户 iframe 不再白屏；仍只允许同源嵌入 |
| 前端根路径引用 `/logo.svg` | `scripts/patch-app-web-logo.py` → `/app/jiuwenswarm/logo.svg` | 品牌图不再 404 |

这两个补丁脚本都支持 `--check`，且被 `scripts/build-fpk.sh` 作为**构建闸门**调用：补丁打不上（上游改了目标行）→ 构建直接失败，不会静默产出"看起来正常但没修"的包。

---

## 9. 数据、升级与卸载

### 9.1 数据落点

| 内容 | 路径 |
|---|---|
| 数据根 | `$TRIM_PKGVAR/data` |
| 配置（含模型 API Key） | `$TRIM_PKGVAR/data/config/{config.yaml,config-gateway.yaml,.env}` |
| 会话 / 记忆 / skills / 产出 | `$TRIM_PKGVAR/data/profile/...` |
| 日志 | `$TRIM_PKGVAR/data/logs/`、`$TRIM_PKGVAR/logs/{launcher.log,install.log}`（launcher.log 超 20 MB 轮转，保留 1 份） |
| venv（含 wheel 指纹） | `$TRIM_PKGVAR/venv`、`$TRIM_PKGVAR/venv/.workswarm-wheel.sha256` |
| socket | `$TRIM_APPDEST/app.sock` |

### 9.2 升级的现实

- 本应用**不在应用商店**，没有「更新」按钮；CLI 对已装应用直接拒（`10236`）。
- **fnOS 的"手动安装 = 重装"流程会清空 `@appdata/<应用>/data`**（平台行为，不是本应用删的）；`app.env` 与 `home/` 会存活。
- 安装向导里的「保留现有数据」对 `data/` **不生效**（实测）。
- ⇒ **升级/重装前请先备份 `数据卷/@appdata/jiuwenswarm/data`**，尤其是 `data/config/.env`（模型 API Key）。
- venv 会比对 wheel 的 sha256 指纹，**内容变化即重建**——即使上游版本号没变（本工程给 wheel 打过补丁），也不会继续跑旧代码。

### 9.3 卸载

- 默认**保留**数据目录；只有向导勾选「清除全部应用数据」才删除 `data/`、`app.env`、app home。
- 删除逻辑三条硬规则：**参数校验 fail-fast**（`TRIM_PKGVAR` 未注入直接中止，绝不删）、**删除动作 fail-open**（单项失败只 WARN 继续）、**退出码恒 0**（非 0 会让平台判卸载失败）。
- 判据（自己核对时用）：卸载后 `@appdata/jiuwenswarm/app.env` **不存在**即通过。
  **不要用 `data/`、`home/` 是否存在来判断**——安装流程会重建它们。
- ⚠️ **该修复真机尚未重验**（0.2.9-10 起代码已修）。若你发现勾了清除仍有残留，请按 `.flag`/日志定位并反馈。
- ⚠️ **删除本地文件 ≠ 密钥失效**：`data/config/.env` 里存过真实 API Key 的，请到模型平台**重置/轮换**。

---

## 10. 常见问题

| 现象 | 排查 |
|---|---|
| 桌面能开，但门户里空白 | 多为 CSP：确认 `.fpk` 是用带补丁闸门的 `scripts/build-fpk.sh` 构建的（`patch-app-web-csp.py --check` 必须通过） |
| 页面能开，聊天一直断开/重连 | WS 握手被拒。看 `$TRIM_PKGVAR/logs/ws-origin-last-*.flag` 文件名：`deny-*` 看 403 响应体六值；`fallback` 说明网关没带 `X-Forwarded-*` |
| 入口 403（首次安装） | 桥的对端校验拒绝。查 `$TRIM_PKGVAR/logs/launcher.log` 的 `403 peer pid=.. uid=.. gid=.. exe=.. comm=.. reason=..`；若网关 worker 与 app 不同 uid 且 `exe` 读不到，把 uid（可逗号多值）写进 `app.env` 的 `JW_GATEWAY_UID`：`JW_GATEWAY_UID=<GW_UID>,<GW_UID2>`（`chmod 600 app.env`），然后 `cmd/main stop && cmd/main start` |
| 显示已停止 | `$TRIM_PKGVAR/logs/launcher.log`、`install.log`；`cmd/main status; echo $?` |
| 提示缺运行时 | 应用中心安装 `python312` 后重启应用；`cmd/main start` 会自检并用 wheelhouse 自动重建 venv |
| 改了 `app.env` 不生效 | 文件必须**应用用户所有**且 group/other 不可写（建议 `600`）；键必须在白名单内，非法行会被 WARN 忽略 |
| 端口冲突 | `app.env` 里改 `JW_WEB_PORT` / `JW_GATEWAY_PORT` / `JW_AGENT_SERVER_PORT` / `JW_FRONTEND_PORT` 后重启 |

`app.env` 只做**纯解析**（不 `source`），键白名单：`JW_GATEWAY_PEER_ALLOW`、`JW_SOCKET_MODE`、`JW_REQUIRE_ADMIN`、
`JW_GATEWAY_UID`、`JW_GATEWAY_GID`、`JW_FRONTEND_PORT`、`JW_WEB_PORT`、`JW_GATEWAY_PORT`、`JW_AGENT_SERVER_PORT`、
`JW_WS_ALLOWED_ORIGIN_HOSTS`。

---

## 11. 已知限制

1. **仅管理员可用**：`allUsers=false` + 网关桥强制管理员判定；上游无账号体系，**多用户不隔离**（每个人要独立部署实例）。
2. **仅 x86_64**：arm64 需另建 arm64 wheel 集并改 `manifest.platform`。
3. **体积大**：`.fpk` 约 482 MB；安装后安装卷约 0.5 GB、数据卷约 2 GB。平台未给出包体上限，提交前需与官方确认。
4. **无商店更新通道**：只能手动安装；重装会清 `data/`（见 §9.2）。
5. **可选能力默认不可用**：Playwright 浏览器自动化需另下 Chromium；`bubblewrap` 沙箱未启用；TUI/桌面端入口未提供。
6. **WS 来源校验的边界**：桥接受任何"能解析到本机"的域名；归一化后上游两层校验不再生效。DNS rebinding 类攻击靠域 Cookie + 网关注入身份头 + 管理员门禁 + 上游 token 兜底，不等价于"绝对不可绕过"。
7. **未压测**：长文本流式输出、大文件下载是否被网关超时/体积限制截断。
8. **`101` 缺协议层证据**：WS 可用是"用户侧能对话 + 桥侧分支标记命中"的行为证据；在没有有效会话时请求停在网关鉴权层，抓不到握手响应。不要把它写成"协议层已验证"。
9. **无「更新」通道**：本应用不在商店，CLI 拒升级已装应用（`10236`），`upgrade_callback` 只是代码意图，**不对外承诺保留数据升级**（真机未验证）。

---

## 12. 脱敏声明

本仓库对外发布前做过敏感信息审计（规则与逐文件清单为内部资料），发布内容遵循以下约定：

- **占位符**：`<NAS_IP>`、`<NAS_DOMAIN>`、`<NAS_HOSTNAME>`、`<HOME>`、`<USER>`、`<VOL>`、`<APP_UID>`、`<GW_UID>`、`<FNOS_VERSION>`、`<KERNEL_VERSION>`、`<NIC>`、`<DEVICE_MODEL>`、`<SKILL_DIR>`。
- **不含凭据**：仓库内**没有**任何 `api_key` / `token` / `password` / cookie 取值，也没有 `app.env` 实例。
  文中出现的 `desktop_token`、`JW_GATEWAY_UID=1234` 等仅为**概念或示例值**。
- **不含第三方信息**：不记录他人设备上安装了哪些应用、端口映射或内网拓扑。
- **二进制不入库**：262 个 wheel 只登记在 `requirements/wheelhouse-manifest.txt`（文件名/版本/sha256），
  `.fpk` 通过 `scripts/build-*.sh` 现场生成。
- **示例域名统一用 `nas.example.com`**，避免与真实域名混用造成误读。
- 内部取证文件（真机报告、交付说明、审核报告等）**不发布**；引用它们的地方只是"该判据由哪份证据支撑"的出处标记。

> 本仓库自带可执行复查工具：`python3 scripts/sensitive-scan.py --strict .`
> （`--strict` 命中未解释项即退出码 1，可直接放进 CI；`--loose` 只出报告并逐条打印白名单依据）。
> 当前对整仓库跑 `--strict` 的结果是 **0 未解释命中**。
> **扫描范围是文本文件**：扫描器按后缀跳过二进制/构建产物（`.png/.jpg/.whl/.fpk/.zip/.pdf/.woff*` 等），
> 本仓库当前 120 个文件中有 4 个 PNG 图标不在扫描范围内（`ICON.PNG`、`ICON_256.PNG`、`app/ui/images/icon_{64,256}.png`），
> 其元数据另行抽查过（无 `tEXt/iTXt/zTXt/eXIf` 块）。

> 已知局限：本次是**文本级**审计（正则 + 逐文件清单），二进制仅抽查图片元数据；不含 Git 历史清理。
> 若你在使用中发现仍有可定位个人/设备的信息，请开 issue 指出。

---

## 13. 进一步阅读

| 文档 | 内容 |
|---|---|
| [`docs/BUILD.md`](docs/BUILD.md) | 完整构建链路：上游取得、wheelhouse 重建、4 个 git 源依赖改写、两个构建脚本的调用顺序与前置、离机构建 |
| [`docs/APPSTORE-MATERIALS.md`](docs/APPSTORE-MATERIALS.md) | 上架材料字段映射、体积/峰值数据、版本语义 |
| [`docs/RELEASE-CHECKLIST.md`](docs/RELEASE-CHECKLIST.md) | 43 项上架门禁：检查方法 / 合格判据 / 证据形式 |
| [`docs/fix-log/`](docs/fix-log/) | 各版本脚本快照与图标变更记录（含补丁前后对比） |
| [`requirements/wheelhouse-manifest.txt`](requirements/wheelhouse-manifest.txt) | 离线 wheel 清单（文件名/版本/sha256） |
| `knowledge-base/` | 实战经验与方法论（踩坑地图、可观测性设计、验收判据） |

---

## 14. 来源与致谢

上游 [JiuwenSwarm](https://gitcode.com/openJiuwen/jiuwenswarm)（Apache-2.0）由 openJiuwen 维护。
本仓库只包含 fnOS 适配代码与打包脚本；上游源码在构建时单独获取，不随本仓库分发。
