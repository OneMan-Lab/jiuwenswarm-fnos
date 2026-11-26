> 本文为开源发布版，设备与环境标识已脱敏。

# fnOS 真机验证与取证经验（fnos-cli 边界）

> 文中引用的 `VERIFY-REPORT.md`、`QA-REPORT.md`、`QA-ORIGIN-REVIEW.md`、`DELIVERY-NOTES.md`、`ENTRY-SURVEY.md` 等均为本次项目的内部过程记录，与原始设备输出一样未随本文发布；引用仅用于标明结论来源与可追溯性。

> **适用场景**：手头只有 `fnos-cli`（HTTP/HTTPS 接口），**没有设备 shell**，需要完成「装包 → 启停 → 验功能 → 验安全 → 取证」的闭环。
> **来源**：2026-11-26 一次真实项目（JiuwenSwarm 打包为 fnOS 应用，v2→v12 共 7 个包）的完整验证过程，原始证据见内部验证记录（未随本文发布，§1–§39）。
> **标注约定**：`【实测】`= 有命令与输出；`【推断】`= 由实测推出的结论；`【未验证】`= 本轮拿不到证据，不猜。
> **设备基线（本文所有实测的环境）**：fnOS <FNOS_VERSION> / x86_64 / 内核 <KERNEL_VERSION> / 卷 `<VOL>`；`fnos-cli` `<CLI_VERSION>`；profile `<PROFILE>` → `<NAS_IP>`（5666 http / 5667 https）。

---

## 0. 一句话总览

> **在"读不到内容、不能升级、不能带向导卸载、日志全打码"的环境里，唯一可靠的观测维度是"元数据 + 差分 + 文件名 + 端口/进程"；所有结论都必须标注证据强度，且必须设计「对照组」，否则极易把"工具缺陷"误读成"设备事实"。**

---

## 1. fnos-cli 能力边界清单（逐条实测）

### 1.1 应用安装 / 升级

| # | 能力 | 实测结论 | 证据 |
|---|---|---|---|
| 1 | **升级已装应用** | ❌ **不能**。对已安装应用执行 `app install-fpk` → `{"code":10236,"data":null,"msg":""}`，设备状态不变 | `Error: app-center request POST /app-center/v1/install/task failed: ({"code":10236,...})`，耗时 91 s |
| 2 | **`app update` 装本地包** | ❌ **不能**。只认商店包；`--package-type file` → `code 10030` | `app update --package-type file` |
| 3 | **全新安装** | ✅ **可以**，但**必报超时**（见 1.2） | `app install-fpk <fpk> --volume-id 1 --accept-license --yes` |
| 4 | **依赖声明闸** | ⚠️ 包里写 `install_dep_apps=python312` 时，CLI 会拒绝并要求走 App Center UI：`app-center install has dependency app changes that require App Center UI`，**无 flag 可绕过**【实测】 | 同上 |
| 5 | **上传的 `.fpk` 是否留在设备** | ❌ **不留**。上传后 `/<VOL>/appcenter-downloads/upload/<ts>/` **为空**，只余已解包目录 `*-tpk/` | `file ls /<VOL>/appcenter-downloads/upload/<ts>` |
| 6 | **安装耗时 vs CLI 等待窗口** | ⚠️ CLI 等待窗口 ≈ **208 s**，短于"创建 venv + 装 262 个 wheel"的实际耗时 ⇒ **必报** `timed out waiting for app-center install task`，但**设备侧会继续并成功**（约 15 s 后 `starting`，数分钟后 `running`） | `Error: timed out waiting for app-center install task 1795678799193397890-jiuwenswarm …` |

**结论**：**只要目标版本是"已装应用的更新"，CLI 就不是通路** —— 必须由用户在 App Center UI「手动安装」选 `.fpk`（UI 路径可覆盖升级）。CLI 只在"设备上没有该应用"时可用。

### 1.2 卸载

| # | 能力 | 实测结论 | 证据 |
|---|---|---|---|
| 7 | **带向导卸载** | ❌ **不能**。`app uninstall` 只有 `--yes`，无向导字段入口 | `Error: app-center uninstall requires custom wizard parameters; run it from App Center UI` |
| 8 | **clum 强制卸载**（`--yes`） | 只能走"无向导"路径；含 `wizard/uninstall` 的包会被上面那条拦住 | 同上 |

**结论**：**卸载必须在 UI 完成**；这意味着"卸载类脚本的验证"**必须借用户的真实卸载动作**，不能自己制造场景。

### 1.3 执行 / 交互能力

| # | 能力 | 实测结论 |
|---|---|---|
| 9 | **shell / 命令执行** | ❌ 完全无（无 `exec`/`ssh`/`script` 类子命令）。不要试图"开 SSH"绕行——那是设备配置改动，不属于验证动作 |
| 10 | **文件内容读取（`cat`）** | ❌ 无 `file cat`；`file prop` 只给元数据 |
| 11 | **日志读取** | ❌ 见 1.5，全部打码或只匹配文件名 |

### 1.4 文件系统接口的坑（**最容易被误读的一类**）

| # | 现象 | 实测 | 正确用法 |
|---|---|---|---|
| 12 | `file ls-dir <app 私有目录>` | 返回 **`[]`**（0 项），但目录确实存在 | **改用 `file ls`**（同路径正常返回清单）。`ls-dir` 只适合普通共享目录 |
| 13 | `file ls /<VOL>/@appdata/<app>` | **漏项**：只列出 6 项（`home/ cache/ README-DATA.txt info.log bootstrap.log app.env`），而实际存在的 `data/ venv/ run/ logs/` **全没列** | **目录级列举不能用于完整性判定**；"没列出来" ≠ "不存在" |
| 14 | `file ls` 具体文件/子目录 | ✅ 可靠（`file ls <dir>` 列该目录、`file prop <file>` 拿 `size/btim/mtim/uid`） | 文件级访问优先 |
| 15 | `file prop` 某个确实存在的文件 | ✅ 可靠。例：`/<VOL>/@appdata/<app>/logs/launcher.log` 一度返回 `errno 4100`（假阴性），后续同路径又能正常返回 `size` | 偶发假阴性时**换时间点/换命令重试**，不要立刻判"不存在" |
| 16 | 目录列举与 `file prop` 的大小口径 | ⚠️ 曾出现 `install.log`：`file prop` 报 5 544 B、`file ls` 报 55 448 B | **以 `file ls` 及跨时间点差分准**；同一数值不要跨命令混用 |

### 1.5 日志与内容类探针（全部不可达）

| 手段 | 实测结果 |
|---|---|
| `file download-url <文件>` | `{"download":[{"uri":"[REDACTED]"}]}` —— **CLI 打码** |
| `raw file.download --json '{"files":[…]}}' --yes` | 同样 `uri=[REDACTED]` —— **raw 通道也打码**，不是只有高层命令打码 |
| `file search "<关键字>" <目录>` | **只匹配文件名**：搜 `launcher` 命中 `launcher.log`；搜 `socket dir` / `mode=0o755` / `peer_allow` / `no-exe` 全返回 `[]`（而这些串极可能在日志里）⇒ **不能当内容探针** |
| `logger list` / 日志模块 | 返回 **0 条** |
| `file access` | 返回的是**调用方权限掩码**，不是文件 mode 位 |
| `file search <…>` | 部分端点直接 500：`failed to call HTTP proxy …` |

**结论**：**日志内容在本工具能力内不可达**。任何依赖"读日志确认某行"的验收设计，都必须准备**不读内容的替代通路**（见 §2）。

### 1.6 监控 / 网络

| 手段 | 实测结果 |
|---|---|
| `monitor net` | 字段仅 `bond/ifType/index/name/receive/transmit` —— **不含 IP**。本机：`<NIC_1>`(index 2) 收 256/发 236；`<NIC_2>`(index 1) 收 1174/发 832【实测】 |
| `monitor +status` | **子命令不存在**（`error: unrecognized subcommand '+status'`） |
| `system info` | 仅 `{"model":[10,152,128],"type":""}` —— 无主机名/IP/域名 |
| `network` 模块 | 只有 `ssh` 子命令 —— 无接口/IP 查询 |
| `monitor proc-list` | 有 `pid/uid/comm`，可**按 uid 过滤**；但**刚装完/刚重启会读到上一轮的 pid**（缓存延迟）—— 需 `stop` 一次或等待后重读 |
| `monitor proc-srv` | 不含应用分组信息 |
| `user list` / `list-ug` / `group-list` | 全部 **403 Forbidden**（拿不到 gid/用户名，只能拿 uid） |

### 1.7 其他

| 项 | 结论 |
|---|---|
| `/etc/nginx` 等系统路径 | `file` 系命令一律 `Unsupported path`（只支持 `/vol{n}/...`）⇒ **读不到 nginx 配置** |
| `@appmeta/<app>` | `file ls-dir` 返回 `[]`，`file ls` 也无内容 ⇒ 读不到磁盘上的 `manifest`/`privilege` 原文 |
| 写能力 | `file upload <dir> <local>` ✅ 可以（落地文件 **uid <USER_UID>**，即管理员身份，不是应用 uid）；`file rm --yes` ✅ 可删；`file mv`/`cp`/`mv`/`compress`/`extract`/`chown` 均在 |

---

## 2. 可替代的观测手段（"读不到内容"时的六把尺子）

### 2.1 文件存在性

- **用法**：`file prop <path>` → 非 `errno` 即存在；`file ls <dir>` 出现文件名即存在。
- **局限**：① 目录列举会漏项（§1.4 #13）⇒ **判"不存在"必须用 `file prop` 直指文件路径**；② 偶发 `errno 4100` 假阴性。
- **典型价值**：判断"某脚本创建的标记文件是否还在"。

### 2.2 字节数（size）

- **用法**：`file prop` 取 `size`；或 `file ls` 看清单里的 `size`。
- **能回答**：文件是否被写入过、是否被替换成新版本（配合已知版本的字节数）。
- **不能回答**：内容是什么。**不要用"大小变了"去推断"某一行被加了"**，除非你**能给出该行的精确长度**并做加减验证（见 2.3 的正例与反例）。
- **正例**：某配置白名单行被追加 回环别名（10 B）+ 设备主机名（5 B） ⇒ 15 B，与实测增量**精确吻合**，据此高置信推出"只加进了回环与主机名"。
- **反例**：日志行各分支长度只差 1–3 B（`Host`=域名 155 / 回环 157 / XFH 154），且 `Host` 真值未知、连接数不定 ⇒ **不可用**。

### 2.3 `btim` / `mtim` 差分

- **用法**：`file prop` 取 `btim`（创建）与 `mtim`（修改）。
- **能回答**：谁在什么时刻创建/改写了它；**新 inode 特征**（`btim == mtim` 且等于某事件时刻 ⇒ 走的是 `os.replace` 原子替换，而不是追加写）。
- **典型价值**：
  - 判定 `data/` 目录是否被"重建"：目录 `btim` 与安装时刻同秒 ⇒ 旧目录已不存在（被删后新建）；与"应用启动时刻"同秒 ⇒ 是应用初始化。
  - 判定某文件是否被改写：`btim` 被刷新到与 `mtim` 同一秒 ⇒ 换 inode。
- **局限**：只能说明"何时"，不能说明"由谁、改了什么"；两者需结合脚本行为推断。

### 2.4 文件名编码分支（**强烈推荐的可观测性设计**）

- **做法**：程序每次"判定/分支"后，写/覆盖一个 **0 字节** 标记文件，把**分支名编码进文件名**，例如
  `${JW_LOGS}/ws-origin-last-match-host.flag`、`-match-x-forwarded.flag`、`-fallback.flag`、`-deny-mismatch.flag`。
- **为什么有效**：`file ls <dir>` **能列文件名**（不能读内容），于是"日志读不到"的环境里依然能远程判断走了哪条分支。
- **实战价值（本项目的决定性一击）**：正是靠 `ws-origin-last-match-x-forwarded.flag` 这个文件名，才确认"网关改写了 `Host`，判定改走代理头，且**没有**降级为 `fallback`"——如果只有一条日志内容，永远读不到。
- **配套建议**：分支名要**互斥且自解释**；旧标记要清理（只留最新一个），否则会误读成"多个分支都发生过"。

### 2.5 端口连通性

- **用法**：`curl -s -o /dev/null -w '%{http_code} %{size_download}\n' -m N <url>`。
- **能回答**：服务是否在监听、是否 TLS、返回码与**响应体长度**、响应头 `Server`。
- **关键判据**：`http_code=000` 表示**连接层失败**（如对明文端口发 https → TLS 握手失败），不是"应用 500"。

### 2.6 进程 uid

- **用法**：`monitor proc-list` → 过滤 `uid`；`file ls` 看 socket 文件 `uid`。
- **能回答**：应用是否以**独立 uid** 运行（应用 uid 由平台按应用递增分配，与系统用户 uid 段分离）；socket 属主是否与期望一致。
- **坑**：`monitor proc-list` 有缓存延迟；进程名常为 `python`（不是 `python3.12`）。

### 2.7 组合用法（推荐顺序）

```
存在性(file prop) → 尺寸/时间(btim/mtim) → 文件名编码(flag) → 端口/响应头 → 进程 uid
```
每一层都独立成立，不要用上层推断代替下层实测。

---

## 3. 安装与卸载的平台语义（**最容易踩的认知坑**）

### 3.1 「手动安装」= 重装，并且**清空 `data/`**

- **实测事实（用户选「清除全部应用数据」的一次）**：安装后
  - `@appdata/<app>/data` 的**目录 `btim` = 安装时刻（17:39:19）**，与应用启动时刻（17:41:13+）不同；
  - `data/config/config.yaml`、`data/agent/teams/team_control.db` 均为**启动后重写**：`team_control.db` 从 **106 496 B → 4 096 B（空库）**；
  - 而 `@appdata/<app>/app.env`（`btim 15:42`）、`home/`（`btim 11:44`）、`cache/`、`info.log`、`bootstrap.log` **全部存活**；
  - `appID` 由 50 变 52 ⇒ 确实发生了"卸载 + 安装"。
- **结论**：`data/` 是**平台在卸载/重装流程里清理**的应用数据目录（不是应用初始化覆盖，也不是本应用卸载脚本删的——脚本的删除分支会同时删 `home/` 与 `app.env`，而它们存活）。
- **用例副作用**：用户的模型 API Key（在 `data/config/.env`）、历史会话**全部丢失**，必须重填。

### 3.2 「清除数据」向导选项**可能不生效**

- 用户在向导中明确选「清除全部应用数据」，但 `app.env` 与 `home/` 仍存活 ⇒ 删除分支未执行。
- **根因（本项目实测判定）**：卸载脚本用 `[ "${wizard_delete_data:-false}" = "true" ]` 判定，而**平台传入的可能是布尔 `true` / `True` / `1`，或压根未注入** ⇒ 判 false，走"保留数据"分支。
- **修法**：参数**归一化**（`tr '[:upper:]' '[:lower:]'` + `case true|1|yes|on|y`）+ **打印原值**（`say "wizard_delete_data='${wizard_delete_data-<未注入>}'"`），下一次卸载即可定性。
- **另一条更隐蔽的失效模式**：删除动作若"遇错即停"（`fail` + `exit 1`），可能**删了第一项就退出**，剩下全留。删除类脚本必须 **fail-open**（见 §4.4）。

### 3.3 验收窗口：卸载后 → 重装前

- 重装会**重建** `data/`、`logs/`、`run/`、`TRIM_PKGHOME`（`install_callback` 与 `runtime.sh` 都 `mkdir -p`）。
- 所以"卸载清数据是否生效"**只能在卸载后、重装前的窗口内观察**；而 CLI 无法制造这个窗口（不能带向导卸载），**只能借用户的真实卸载动作**，且必须在**重装之前**完成观测，否则证据被覆盖。

### 3.4 其他平台语义

| 现象 | 含义 |
|---|---|
| `install-fpk` 报 208 s 超时 | **误报**，设备侧继续执行；用 `app status` 复核 |
| `appID` 变化 | 发生过"卸载 + 安装"，不是纯覆盖 |
| 应用入口 `entry.port=""` | 走统一网关（`gatewayPrefix` + `app.sock`），不是端口型；**声明 `port` 即判为端口型**（规范硬要求） |
| 应用 uid | 每应用独立 uid（由平台按应用递增分配，gid 与 uid 相差一个固定小常数）；个别第三方应用以 uid 0 运行，属例外 |

---

## 4. 验收判据设计教训（**最值钱的一节**）

### 4.1 错判据：「重装后 `data/`、`home/`、`@apphome/<app>` 不存在」

- **为什么错**：`install_callback` 会 `mkdir -p ${JW_DATA}` 并写标记文件；`runtime.sh` 会 `mkdir -p "${JW_DATA}" "${JW_LOGS}" "${JW_RUN}" "${TRIM_PKGHOME}" "${TRIM_PKGTMP}"`。⇒ **重装后这些目录必然存在（只是空的）**。
- **后果**：用它验收，**任何一次正确的卸载都会被判成失败（假阳性）**，然后大家去修一个没坏的地方。
- **正确判据**：**`@appdata/<app>/app.env` 不存在** —— 因为**没有任何脚本会创建它**（仅管理员/应用配置写入），所以"它消失"唯一对应"删除分支执行过"。
- **辅助判据**：`@apphome/<app>` 下原 `.config`、`.jiuwenswarm` 消失（用户数据，不会被 `mkdir` 重建）；`@appdata/<app>/home/` 为空目录；应用首次打开要求重配凭据。

### 4.2 错判据：「看 HTTP 状态码」

- **实测**：未登录访问 `/app/<app>`、`/app/<app>/ws`、甚至 `/app/doesnotexist`，**一律返回 `HTTP 200` + 13 字节纯文本 `invalid token`**（前缀级兜底）。
- ⇒ **只看状态码会把"未授权"误判为"页面正常"**，也会把"路径不存在"误判为"存在"。
- **必须看**：响应体（`invalid token`）、`Content-Length`、`Content-Type`。

### 4.3 差分法（对照组）优于"预设比对"

- **思想**：任何"是否变化"的判断，都要有**装前基线**。
- **实例**：
  - 装前记 `logs/` 清单（`install.log 55 448` / `launcher.log 1 496 976` / **无** `ws-origin.log`、**无** flag）；装后"多出 `ws-origin.log` + 某个 flag" ⇒ 一眼确认新逻辑执行过。
  - 拿"上一版本的同名字节数"作对照（`index.html` 7 523 → 7 539 B、`main.js` 6 660 122 → 6 660 138 B）⇒ 无需读内容即可判断"设备上装的是哪一版前端"。
- **反面**：只写"应该是 10 169 B"而不记录基线，一旦数据目录被重建（基线从 10 141 起算而非 10 156），就会把"对的结果"判成"对不上"。

### 4.4 删除类脚本三句话原则（可直接抄进规范）

> **参数校验 fail-fast（防误删）；删除动作 fail-open（能删的尽量删掉）；退出码永远 0（避免平台误判卸载失败）。**

- **参数校验**：`TRIM_PKGVAR` 为空、目标非绝对路径、超出允许范围 → **硬中止**（`rm -rf ""`、`rm -rf /` 必须不可能发生）。
- **删除动作**：逐项独立执行，单项失败只 `WARN` 并继续；最后汇总「已删 N / 残留 M + 原因」写到 `TRIM_TEMP_LOGFILE`。
- **顺序**：隐私优先 —— `app.env`（含密钥）→ `home/`（用户数据）→ `data/` → 运行期目录（`venv/logs/run/pycache`）。
- **退出码**：**始终 `exit 0`**。`exit 1` 会让平台判"卸载失败"，可能触发回滚/报错，缺陷从"删一半"升级成"用户以为没卸掉"。
- **为什么重要**：很多人本能用 `exit 1` 表示"出错了"，结果把平台卸载流程一起搞挂。

### 4.5 行为证据 vs 协议证据（表述纪律）

- 本项目最终结论是「**WS 通路可用 —— 用户侧双向收发成功**」，**不是**「`/ws` 返回 101」。
- 原因：未登录/无会话时请求在**网关鉴权层**就被拦（`200 invalid token`），**本侧从未取得协议层证据**。
- 结论：**"能发能回"是功能证据，"101"是协议证据，二者不能互相替代**；交付文档里必须写清是哪一种。

### 4.6 认证与安全类判据（不要用"看起来像"代替"实测"）

- `Server: nginx` ⇒ **请求没到应用**（主站/网关处理）；**无 `Server` 头** ⇒ 桥/自建服务自己拼的响应。
- 用这个判据可以快速区分"404/502 是谁返回的"，比看现象猜强。
- 未登录时的 `200 invalid token` 属于"语义异常的 200"，**不能**用它推断应用行为。

---

## 5. 网络与网关行为实测

### 5.1 门户与端口

| 项 | 实测 |
|---|---|
| `http://IP/` | **302** → `http://IP:5666/`（带路径同样跳转） |
| `https://IP/` | **302** → `https://IP:5667/` |
| 门户 | 5666 = http、5667 = https，均可用 |

### 5.2 独立端口型应用（7 个，均无 TLS）【实测】

| 观测项 | 结果 |
|---|---|
| 端口型应用逐个测 `https://IP:<port>/` | **全部 `000`（TLS 握手失败）** |
| 同一批应用测 `http://IP:<port>/` | **全部有响应**（200 / 307 一类正常响应） |

⇒ **端口型只监听明文 HTTP，没有 TLS**（7/7）。
⇒ **推论**【推断，未用浏览器实测】：端口型 + `iframe` 在 **https 门户**下会被浏览器按**混合内容**阻断 ⇒ 端口型方案的隐性代价是"必须走 http 门户"。
⇒ **安全事实**：独立端口对局域网**裸端口直接可达**，**完全绕过 fnOS 统一登录**（无 302、无 `invalid token`）——这是"独立端口"模型的固有代价。

### 5.3 未登录网关的行为

- 对 `/app/<app>`、`/cgi/ThirdParty/<app>/*`、以及**不存在的路径**，未登录一律：`HTTP 200` + `Content-Type: text/plain` + `Content-Length: 13` + body `invalid token`【实测】
- **在 WS upgrade 之前就返回**：补齐 `Connection: Upgrade` / `Upgrade: websocket` / `Sec-WebSocket-Version: 13` / `Sec-WebSocket-Key` / `Origin` 后，响应仍是 `200` + `Server: nginx` + 13 B `invalid token`（http 5666 与 https 5667 均如此）⇒ **鉴权先于桥**，无会话拿不到 101。

### 5.4 网关会**改写请求头**（本项目的关键教训）

- 先验证据：请求带 `Connection: Upgrade` 时，网关响应里 `Connection` 是 **`keep-alive`** ⇒ nginx 会规范化/改写头。
- 真机确认：应用侧拿到的是**被改写的 `Host`**（内部地址），**原始主机名只出现在 `X-Forwarded-Host` 一类代理头里**。
- ⇒ **任何"基于 `Host` 做同源校验"的设计，在真实链路里会先失效**。正确做法：主判据 + 代理头兜底 + 判不出来时降级放行（并显式记录）。

### 5.5 内网 IP vs 域名 vs 外网

- IP 访问与域名访问**走同一条网关链路**，差异只在浏览器发出的 `Origin`/`Host` 主机名。
- 若应用侧做**主机名精确匹配**的白名单/校验，**域名一定不在默认集合里** ⇒ 表现为"IP 能用、域名不通"。这是本项目先后两次踩到的形态。

---

## 6. 当初判错的地方（复盘，至少 3 处）

### 6.1 把 `ls-dir` 返回 `[]` 当成"权限/ACL 限制"

- **当时的结论**：`file ls-dir /<VOL>/@appmeta/<app>` 返回 0 项 ⇒ 疑为 ACL/属主限制，读不到元数据。
- **实际情况**：**工具口径问题** —— 对 app 私有目录要 `file ls`（`ls-dir` 会被过滤）。
- **教训**：**工具的"空结果"不等于"对象为空"**。先换等价命令复核，再下"读不到"的结论。

### 6.2 把 404 归因成"桥缺少静态资源路由"

- **当时的结论**：前端请求 `logo.svg`，桥没有该路由 ⇒ 代理给上游 ⇒ 上游 404。
- **实际情况**：前端写死的是**站点根绝对路径 `/logo.svg`**（不是带应用前缀的 `/app/<app>/logo.svg`）⇒ **请求从未到达桥**，由主站 nginx 直接 404。
- **纠错方法**：比对包内 wheel 的 `index.html` / `main.js`（v5→v6 各 +16 B，内容是把 `'/logo.svg'` 改成 `'/app/<app>/logo.svg'`）。
- **教训**：**"现象与代码顺序吻合"是最弱证据**。要问"如果按这条路径走，必然还会发生 X"，再验证 X。

### 6.3 把"卸载清除失败"解释成"删到一半退出"

- **当时的结论**：删除顺序是 `DATA → APP_HOME → app.env`，观测是"`data` 没了、后两项还在" ⇒ 推断 `safe_rm` 白名单在 `APP_HOME` 处失败并 `exit`。
- **推翻它的证据**：`/<VOL>/@appdata/<app>/home`、`/<VOL>/@apphome/<app>`、`/<VOL>/@appshare/<app>`、`/<VOL>/@appconf/<app>` **四个路径全部存在且都含应用名** ⇒ 白名单对 `data`、`APP_HOME`、`app.env` **都会放行** ⇒ 若进了删除分支，三者会被**依次全删**，不可能只删 `data`。既然 `app.env` 还在 ⇒ **脚本根本没进那个分支**。
- **真正的机制**：`wizard_delete_data` **没被识别成字符串 `"true"`**（平台传布尔/未注入）⇒ 走 `else`（保留数据），一项都没删；`data/` 是**平台**在重装流程里清的。
- **教训**：**"删了一半"是个太顺滑的故事**。要用"必然的伴生结果"去证伪（本例：`APP_HOME` 也应当被删，而它没有）。

### 6.4 把 `.env` 差分基线记成"上一版的字节数"

- **当时的做法**：基线取 v5 时期实测的 `10 156 B`，得出增量 `+136 B`。
- **问题**：那次安装**已清空 `data/`**，`.env` 是**从模板重新生成**的 ⇒ 正确基线是模板原值 **`10 141 B`**，增量应为 **`+151 B`**。`+136` 只是数值巧合。
- **教训**：**基线必须与被测对象"同一次生命周期"**；对象被重建后，基线要跟着换。

### 6.5 用"日志行字节数"反推分支

- **当时的想法**：不同分支的日志行长度不同，可用 `size` 反推走了哪一支。
- **实测否决**：分支 A/B/C 的行长分别是 155 / 157 / 154 B，**只差 1–3 B**，且 `Host` 真值未知、连接数不定 ⇒ 总量漂移，**不可用**。
- **替代**：用 **flag 文件名**编码分支（§2.4）。
- **教训**：**差分法只在"差异显著且可枚举"时成立**；差异小于不确定性时等于噪声。

---

## 7. 可直接复用的检查清单（SOP）

### 7.1 装前（5 分钟）

1. `app status <app>` —— 记版本/状态（**这是基线**）
2. `file ls <app 数据目录>/logs` —— 记清单与大小（**这是基线**）
3. `file prop` 关键文件（`app.env`、`data/config/.env`、`venv`、`app.sock`）的 `size/btim/mtim`
4. `app entry list` —— 记 `type/path/port/status`
5. 校验待装包 `sha256sum` + `ls -l`，与申报值逐项比对

### 7.2 装后（10 分钟）

1. `app status`：版本是否为新版本、是否 `running`
2. `file ls <@appcenter/<app>>`：`app.sock` 是否存在、`uid` 是否符合预期
3. `app entry list`：`type=iframe` / `path=/app/<app>` / **`port=""`** 是否无回归
4. `file ls <logs>`：**新增了哪些文件**（尤其 `*.flag` / 新日志名）
5. 未登录边界：`curl -i <门户>/app/<app>` → 仍应 `200` + `Server: nginx` + `invalid token`
6. 关键行为：请求用户按路径验证（IP / 域名各一次），再看 **flag 文件名**判分支

### 7.3 判定纪律

- 每条结论标注 `【实测】/【推断】/【未验证】`
- **"工具空结果"只能产出"未验证"，不能产出"不存在"**
- **表述约束**：行为证据不写成协议证据（"能发能回" ≠ "101"）；不写"已验证"除非有真机命令与输出
- **拒绝写"应该没事"** —— 要么给量化上界（如"日志稳态上限 ≈20.25 MB、约 17.4 h 轮转一次"），要么写"未验证"

### 7.4 交付物建议结构

```
1. 环境基线（版本/架构/卷/入口形态）
2. 能力边界（能做/不能做，逐条带命令）
3. 装前基线 → 装后对照（差分）
4. 功能验证（用户侧行为 + 服务端元数据佐证）
5. 安全边界（未登录、越权、伪造头）
6. 平台语义（安装/升级/卸载/清数据）
7. 未验证项（明确列出，不许含糊）
8. 判据演进与判错复盘（最有复用价值）
```

---

## 8. 附录：命令速查

```bash
CLI=/path/to/skills/fnos-cli/scripts/fnos-cli     # 启动器；无执行位时用 sh <启动器>

# —— 应用 ——
$CLI --profile <p> app status <app>                       # 版本 + 状态
$CLI --profile <p> app entry list                         # 入口（type/path/port/status）
$CLI --profile <p> app start|stop|restart <app> --yes
$CLI --profile <p> app install-fpk <file.fpk> --volume-id 1 --accept-license --yes
$CLI --profile <p> app uninstall <app> --yes              # 含向导的包会被拒

# —— 文件/元数据（可靠子集）——
$CLI --profile <p> file ls <dir>                          # 列目录（app 私有目录用它，不用 ls-dir）
$CLI --profile <p> file prop <path>                       # size / btim / mtim / uid
$CLI --profile <p> file upload <dir> <local> --yes        # 落地 uid=<USER_UID>
$CLI --profile <p> file rm <path> --yes

# —— 运行态 ——
$CLI --profile <p> monitor proc-list                      # 有缓存延迟，必要时 stop 后重读
$CLI --profile <p> monitor net                            # 只有收发字节，无 IP

# —— HTTP 侧（不经 CLI）——
curl -s -o /dev/null -w 'code=%{http_code} size=%{size_download}\n' -m 12 <url>
curl -s -i -m 12 -H 'Connection: Upgrade' -H 'Upgrade: websocket' \
     -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
     -H 'Origin: http://<host>:5666' http://<host>:5666/app/<app>/ws | head -8
```

---

## 9. 一页纸结论（给赶时间的人）

1. **CLI 不能升级、不能带向导卸载、读不到日志内容** —— 这三件事决定了"验收必须借用户动作 + 用元数据取证"。
2. **目录列举不可信，文件级 `file prop` 可靠**；"空/漏项"≠"不存在"。
3. **差分（装前基线）是主力方法**，但基线必须与被测对象同一生命周期。
4. **判据要选"只有该动作才会改变"的量**（如 `app.env` 是否存在），不要选"脚本自己会重建"的量（如 `data/`、`home/`）。
5. **状态码不够，必须看响应体**（`200 invalid token`）。
6. **把分支编码进文件名**，是"读不到内容"环境下最便宜的远程可观测性。
7. **网关会改写 `Host`**；任何"最严格"的校验都要先问：它在真实链路里会不会先失效？
8. **行为证据 ≠ 协议证据**；未验证就写未验证。
