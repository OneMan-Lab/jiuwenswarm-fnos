> 本文为开源发布版，设备与环境标识已脱敏。

# 飞牛 fnOS 应用开发清单（可打钩）

> 三份清单：**① 开工前**（选型与设计决策）、**② 上架前**（权限/资源/材料门禁）、**③ 真机验收**（装/入口/WS/安全/卸载，每条带判据与命令）。
> 标注：`[规范]` 官方要求（注章节）｜`[实测]` 本项目验证过其必要性｜`[经验]` 建议。
> 详细理由见 `fnos-app-playbook.md` 对应章节，反例见 `anti-patterns.md`。
> **用法**：逐条打钩；拿不到证据的项写「未验证」而不是留空——"没勾"和"勾了但没证据"在上架评审里是两种性质。

---

## ① 开工前清单（设计决策，改起来最贵）

### A. 访问模型选型

- [ ] **A1 应用是否有 WebSocket / SSE 长连接**？有 ⇒ 排除 `index.cgi`（不支持 WS）`[规范] advanced §1`
- [ ] **A2 是否常驻进程**？是 ⇒ 排除 `index.cgi`（每请求起进程）`[规范] advanced §1`
- [ ] **A3 是否需要复用 NAS 登录态 / 嵌入门户 iframe**？需要 ⇒ **统一网关**是唯一选择 `[规范] advanced §2`
- [ ] **A4 若选独立端口**：是否已接受三个代价——① 端口无 TLS（设备实测 7/7 端口型应用都没有 TLS）② https 门户下 iframe 混合内容阻断 ③ LAN 裸端口绕过 fnOS 登录 `[实测]`
- [ ] **A5 访问模型已写进方案文档**，并说明"为什么不是另外两种"

**自检命令**（有设备时，先看平台期望什么）：
```bash
$CLI --profile <p> app entry list            # 看官方内建应用是否都走 /app 或短根级前缀
$CLI --profile <p> app config detail <app>   # 看同类的第三方应用是声明 port 还是走路径
```
判据：`type` 字段**不能**用来判形态，必须看 `uri.port` 是否为空 + `uri.path` 前缀 `[实测]`。

### B. 依赖策略

- [ ] **B1 依赖应用已声明**：`install_dep_apps=python312` / `nodejs_v22` / `java-21-openjdk` `[规范] advanced §7`
- [ ] **B2 依赖是否递归缺失**：依赖检查**不递归**，自己用到的每个依赖都要直接声明 `[规范] advanced §5`
- [ ] **B3 生命周期脚本里注入了 PATH**：`export PATH=/var/apps/<rt>/target/bin:$PATH` `[规范] advanced §7`
- [ ] **B4 是否接受"依赖声明会堵死 CLI 安装"** ⇒ 决定是否走**双包线**：测试包不带 `install_dep_apps`，上架包带 `[实测]`
- [ ] **B5 离线依赖已打齐**：`wheelhouse/` + `WHEELS.txt`（名称/版本/sha256）+ 安装时 `--no-index --find-links`
- [ ] **B6 直接 URL 依赖已改写**：`name @ git+https://…` 会让 pip 强制回源，必须改写为 `name==<version>` 并重算 `RECORD` `[实测]`
- [ ] **B7 `python312` 缺 `ensurepip` 的兜底路径存在**（用 wheelhouse 内 `pip-*.whl` 自举）`[未验证]`（本项目未触发该分支）

### C. 数据落盘与升级语义

- [ ] **C1 数据根只落在 `TRIM_PKGVAR` 下**：配置/会话/日志/run 都由该根派生；`HOME=TRIM_PKGHOME`、`TMPDIR=TRIM_PKGTMP`、`PYTHONPYCACHEPREFIX` 也不出卷 `[规范] dev-guide §7`
- [ ] **C2 已明确"手动安装 = 重装，平台会清空 `data/`"**，并写进 README（向导"保留数据"实测拦不住）`[实测]`
- [ ] **C3 设备历史残留策略已定**：无自有标记文件（`.fnos-app-meta`）且非空时整体改名 `data.legacy-<ts>` 保留，不删不覆盖 `[经验]`
- [ ] **C4 首次启动缺配置的降级路径**：给可读错误，不白屏/不无限转圈 `[规范] release §4`（依赖不可用也要测）
- [ ] **C5 升级通道是否真能走通已确认**：CLI 不能升级已装应用（`10236`）、不在商店就没有更新入口 ⇒ **不对外承诺"数据保留的更新按钮"** `[实测]`

### D. 安全模型（先设计，后写代码）

- [ ] **D1 身份可信前提已定**：`X-Trim-*` 是普通请求头，可信前提是"对端确实是网关"⇒ 需要 peer 校验 `[实测]`
- [ ] **D2 peer 判据不用 `comm` / `basename`**：用 `SO_PEERCRED` + `realpath(exe)` 全路径 + 属主 root + 父目录非全局可写 `[实测]`
- [ ] **D3 peer 判定在读请求字节之前** `[实测]`
- [ ] **D4 socket 权限策略已定**：目标 `0660 + setfacl`，失败回退 `0666 + WARN`；`chmod` 在 `start_unix_server()` 之后 `[实测]`
- [ ] **D5 已列出"防线分工表"**（位置 / 真正防住什么 / 不防什么 / 失效时谁兜底）`[经验]`

### E. 可观测性设计（比日志更早决定）

- [ ] **E1 关键分支写"文件名标记"**：`logs/<topic>-last-<branch>.flag`（0 字节、覆盖写）`[实测]`
- [ ] **E2 关键判定写一行结构化日志**（原始值 + allow/deny + reason），并有轮转上限 `[实测]`
- [ ] **E3 拒绝响应体里带可读 reason**（浏览器 Network 可见，不依赖日志文件）`[实测]`
- [ ] **E4 每个"判不出来"的分支必须有 WARN + 计数**，不允许静默放行 `[实测]`

---

## ② 上架前清单（材料与质量门禁）

### A. manifest 元信息（必须准确，不只是"填了"）

- [ ] **A1 `appname` / `version` / `display_name` / `desc` / `source` / `platform` 无占位符** `[规范] dev-guide §4`
- [ ] **A2 `platform` 与包内容一致**：含架构相关二进制（cp312 manylinux wheel 等）就不能写 `all` `[规范] dev-guide §4`
- [ ] **A3 `os_min_version` 已声明**（网关型必须）`[规范] advanced §2`
- [ ] **A4 `changelog` 非空且说人话**，不是"fix bug" `[规范] release §4`
- [ ] **A5 `desc` 不夸大、不声明未实现功能** `[规范] dev-guide §4`
- [ ] **A6 `desktop_applaunchname` 与 `app/ui/config` 的入口 ID 完全一致**（否则卡片点不开）`[规范] advanced §3`
- [ ] **A7 网关型不写 `service_port`**；端口型必写 `[规范] advanced §2`
- [ ] **A8 `disable_authorization_path` 与实现一致**（不需要用户选目录才 `true`）`[规范] dev-guide §4`
- [ ] **A9 `ctl_stop` 与形态一致**（常驻服务 `true`）`[规范] dev-guide §4`

**逐行核对命令**：
```bash
grep -nE '^(appname|version|display_name|platform|os_min_version|service_port|ctl_stop|checkport|install_dep_apps|desktop_applaunchname|disable_authorization_path|changelog)=' manifest
unzip -p <pkg>.fpk app.tgz | tar -xzO manifest | diff - manifest   # 包内 manifest 与工作区对比（fnpack 会重排键序）
```

### B. 权限最小化

- [ ] **B1 `config/privilege` 为 `run-as=package`**，不是 root `[规范] dev-guide §5`
- [ ] **B2 无 `join-groups`（或只加确实需要的组）** `[规范] dev-guide §5`
- [ ] **B3 没有长期运行/对外的进程以 root 跑**；确需特权的脚本用 `runuser` 降权 `[规范] dev-guide §5`
- [ ] **B4 应用的运行 uid 与网关 uid 的差异已确认**（决定 socket 权限方案）`[实测]`
- [ ] **B5 应用数据都在应用私有目录，没有往用户共享目录乱写** `[规范] dev-guide §5`

### C. 资源与 Scope

- [ ] **C1 `config/resource` 只声明真正用到的能力**（本项目为 `{}`：不用共享目录、不链系统路径、不用 Docker 项目）`[规范] dev-guide §6`
- [ ] **C2 若调用开放 API，`api-scope` 只列实际调用的**（`trim.file.sharedAccess` / `userAccess` / `userAcl` / `path` / `trim.system.getPlatformConfig`）`[规范] open-api §1.1`
- [ ] **C3 用 JS SDK 时 `micro_app=true`** `[规范] open-api §1.2`
- [ ] **C4 中间件只声明实际用的**（`redis`/`minio`/`rabbitmq`），密钥不硬编码进包 `[规范] advanced §6`

### D. 图标与截图（官方硬性项）

- [ ] **D1 包根目录 `ICON.PNG`(64×64) + `ICON_256.PNG`(256×256) 都在** `[规范] advanced §8`
- [ ] **D2 单文件 ≤1024 KB、PNG/JPG、sRGB、完整正方形画布** `[规范] advanced §8`
- [ ] **D3 视觉主体圆角矩形**（不要直角满铺），64 px 下可辨、不贴边 `[规范] advanced §8`
- [ ] **D4 入口图标 `ui/images/icon_64.png` + `icon_256.png` 在位**，config 写 `images/icon_{0}.png` `[规范] advanced §8`
- [ ] **D5 截图展示真实界面与核心流程**，不含占位页/真实用户名/路径/token/内网 IP `[规范] release §4`；尺寸与张数：**规范未明确，提交前问官方** `[未验证]`

### E. 生命周期脚本安全（逐条对应一次真实事故）

- [ ] **E1 九个脚本齐全**：`install_init/install_callback/main/upgrade_init/upgrade_callback/uninstall_init/uninstall_callback/config_init/config_callback` `[规范] dev-guide §8`
- [ ] **E2 `main` 退出码语义正确**：`0`=成功（status 中运行中）、`1`=失败、`3`=status 未运行 `[规范] dev-guide §8`
- [ ] **E3 `status` 不是"进程在不在"单一判据**（PID + cmdline + socket + 健康检查）`[实测]`
- [ ] **E4 失败前写 `TRIM_TEMP_LOGFILE`**，信息简短可执行 `[规范] dev-guide §8`
- [ ] **E5 `uninstall_callback` 不 `source` target 下任何脚本**（卸载阶段 target 已被删）`[实测]`
- [ ] **E6 install/upgrade 侧先 `[ -f ]` 再 `source`** `[实测]`
- [ ] **E7 向导布尔归一化**（`true|1|yes|on|y`，忽略大小写）**并打印原值** `[实测]`
- [ ] **E8 参数校验 fail-fast；删除动作 fail-open；退出码恒 `0`** `[实测]`
- [ ] **E9 所有删除目标过安全校验**：绝对路径、非 `/`、位于 `*/<appname>*` 下；**候选路径（父目录回退）重新校验**（父目录非 `/`、basename 匹配）`[实测]`
- [ ] **E10 删除顺序隐私优先**：`app.env`（含密钥）→ `home` → `data` → 运行期目录 `[实测]`
- [ ] **E11 幂等**：连续两次 install/start 无重复副作用 `[规范] dev-guide §8`
- [ ] **E12 `umask` 明确**（本项目启动段 `umask 077`）`[实测]`

### F. 入口与网关实现

- [ ] **F1 `gatewayPrefix` = `/app/<appname>`**（或带稳定子路径），版本间不变 `[规范] advanced §2`
- [ ] **F2 `gatewaySocket` 只填文件名**，socket 落在 `TRIM_APPDEST` 下 `[规范] advanced §2`
- [ ] **F3 前缀改写拒绝 `..`，根路径原样透传** `[实测]`
- [ ] **F4 非 WS 请求 `Connection: close`**（防 keep-alive 绕过前缀改写）`[实测]`
- [ ] **F5 WS 分支保留 `Upgrade`/`Connection`，其余 hop-by-hop 头丢弃** `[实测]`
- [ ] **F6 依赖 `Host` 的逻辑已全部排查**（网关会改写 `Host`，真主机名只在 `X-Forwarded-Host`）`[实测]`
- [ ] **F7 WS Origin 策略已写清**：判定基准、多值处理、判不出来怎么办、归一化旁路了哪一层 `[实测]`

### G. 构建与包本体

- [ ] **G1 补丁闸门**：补丁脚本有 `--check`，匹配不到即 `exit 1` `[实测]`
- [ ] **G2 新鲜度闸门**：包内 `cmd/*`、`app/server/*`、`ui/config`、`wheelhouse/*.whl` 与工作区**逐字节一致** `[实测]`
- [ ] **G3 profile 断言**：测试包无 `install_dep_apps`、上架包有 `[实测]`
- [ ] **G4 构建前后源码仓 `git status --porcelain` 为空**（补丁只落在构建产物层）`[实测]`
- [ ] **G5 同批命令记录 `ls -l` 字节数与 `sha256sum`**（避免两者来自不同次构建）`[实测]`
- [ ] **G6 `.fpk` 体积上限**：**规范未明确**，提交前问官方 `[未验证]`

### H. 材料完整性

- [ ] **H1 上架材料齐备**：manifest 元信息、最终 `.fpk`、图标、截图、发布前测试清单 `[规范] release §4`
- [ ] **H2 安装后占用与升级峰值已实测并写入材料**（本项目：安装卷 ≈0.5 GB / 数据卷 ≈2 GB / 升级峰值 ≈3–3.8 GB）`[实测]`
- [ ] **H3 未验证项显式声明**：如"上架包未经真机安装"、"协议层 101 未取得" `[实测]`
- [ ] **H4 残余风险声明**：如 socket `0666` 与 peer 校验已生效 `[实测]`
- [ ] **H5 判定三选一**（可上架 / 有条件可上架+条件清单 / 不可上架），条件每条都能用一条命令证伪 `[经验]`
- [ ] **H6 分类标签、中英文名与长度限制、隐私说明格式**：**规范未明确**，按官方后台表单问 `[未验证]`

---

## ③ 真机验收清单（每条：判据 + 命令）

> 前置：`$CLI` 指 `fnos-cli` 启动器（无执行位时用 `sh <启动器>`），`<p>` 指 profile。
> 通用纪律：**每组结论记录四要素**——包 sha256 + 关键脚本 sha256 + 执行账号(uid) + 原始命令输出。

### 0. 装前基线（5 分钟，缺了后面全白测）

- [ ] **0.1 包身份**
  ```bash
  sha256sum <pkg>.fpk; ls -l <pkg>.fpk
  ```
  判据：与申报值逐项一致（sha + 字节数，同一批命令内取）`[实测]`

- [ ] **0.2 设备与应用基线**
  ```bash
  $CLI --profile <p> app status <app>          # 版本 + 状态
  $CLI --profile <p> app entry list            # type/path/port/status
  $CLI --profile <p> file ls <TRIM_PKGVAR>/logs   # 记清单与大小
  ```
  判据：日志清单（文件名 + 字节数）已记录；**这是后面"新增了什么"的对照组** `[实测]`

- [ ] **0.3 关键文件指纹基线**
  ```bash
  $CLI --profile <p> file prop <VAR>/app.env
  $CLI --profile <p> file prop <VAR>/data/config/.env
  ```
  判据：`size / btim / mtim` 已记录；**注意基线必须与本次生命周期同源**（对象被重建后基线要换）`[实测]`

### 1. 安装

- [ ] **1.1 安装执行**
  ```bash
  $CLI --profile <p> app install-fpk <pkg>.fpk --volume-id 1 --accept-license --yes
  ```
- [ ] **1.2 CLI 报 `timed out waiting for app-center install task` 时不要立刻判失败**
  ```bash
  $CLI --profile <p> app status <app>     # 等 15s~数分钟再查
  ```
  判据：设备侧会继续执行，状态最终 `running`。CLI 等待窗口 ≈208 s，短于首次建 venv（262 wheel）`[实测]`

- [ ] **1.3 已装应用想"升级"**：`install-fpk` 会返回 `{"code":10236}`，**CLI 无通路** ⇒ 必须走应用中心 UI 手动安装（会被当作重装）`[实测]`

- [ ] **1.4 依赖声明的包用 CLI 装**：会报 `requires App Center UI`（依赖变更） ⇒ 用 UI 装，或用**测试包**（无 `install_dep_apps`）验证运行时 `[实测]`

### 2. 启动与进程

- [ ] **2.1 状态与进程**
  ```bash
  $CLI --profile <p> app status <app>
  $CLI --profile <p> monitor proc-list        # 有缓存延迟，必要时 stop 后重读
  ```
  判据：`running`；进程 uid 为**应用独立 uid**（由平台按应用递增分配，与系统 uid 分离），不是 0 `[实测]`

- [ ] **2.2 socket 落点与属主**
  ```bash
  $CLI --profile <p> file ls <TRIM_APPDEST>
  ```
  判据：`app.sock` 存在，uid 与预期一致（**用 `file ls`，不要用 `ls-dir`**）`[实测]`

### 3. 入口

- [ ] **3.1 入口声明**
  ```bash
  $CLI --profile <p> app entry list
  ```
  判据：`type=iframe`（或与设计一致）/ `path=/app/<app>` / **`port=""`** / 仅管理员可见 `[实测]`

- [ ] **3.2 未登录边界**
  ```bash
  curl -s -i -m 12 "http://<host>:5666/app/<app>" | head -6
  ```
  判据：`HTTP 200` + `Server: nginx` + `Content-Length: 13` + body `invalid token`。
  **不许只看状态码**：`/app/doesnotexist` 也是 200 `[实测]`

- [ ] **3.3 登录后页面可用**：用户侧确认首屏渲染、无白屏（白屏先查 CSP `frame-ancestors`，见 `anti-patterns.md` AP-04）`[实测]`

### 4. WebSocket（本项目最大坑区）

- [ ] **4.1 先 IP、后域名**（顺序不能颠倒：IP 挂了就不是域名逻辑的问题）
- [ ] **4.2 功能判据（行为证据）**：对话/消息**双向收发**成功 `[实测]`
- [ ] **4.3 分支判据（元数据证据）**
  ```bash
  $CLI --profile <p> file ls <VAR>/logs
  ```
  判据：出现 `ws-origin-last-match-*.flag`（且不是 `fallback`、无 `deny-*`）；`ws-origin.log` 存在且字节数 >0 `[实测]`
- [ ] **4.4 跨站否定用例**：另一站点页面控制台执行 `new WebSocket('wss://<host>/app/<app>/ws')`，应被拒（403 `deny-*`）`[实测]`
- [ ] **4.5 协议证据（可选升级）**：浏览器 DevTools Network 里 `/ws` 为 **101**。
  **拿不到就写"行为证据"，不得写"已验证 101"** `[经验]`

### 5. 安全

- [ ] **5.1 非管理员伪造身份头**（核心承诺是否成立）
  ```js
  // 普通（非管理员）账号，同源页面 Console
  const a = await fetch('/app/<app>/', {credentials:'include'}).then(async r=>[r.status, await r.text()]);
  const b = await fetch('/app/<app>/', {headers:{'X-Trim-Isadmin':'true'}, credentials:'include'}).then(async r=>[r.status, await r.text()]);
  console.log(a[0], b[0], a[1]===b[1]);
  ```
  判据三档：`403` ⇒ 通过；`200 + invalid token`（无应用内容）⇒ 通过；`200 + 应用 HTML/JSON` ⇒ **不通过（不可上架）** `[实测]`+`[经验]`

- [ ] **5.2 未授权不能读应用内容**：不带会话 curl 首页与一个 API，判据同上（看响应体，不看状态码）`[实测]`

- [ ] **5.3 socket 权限**（若日志可读或能取 mode）：目标 `0660`；仍是 `0666` 则材料必须声明 + 说明 peer 校验已生效 `[实测]`

### 6. 卸载（必须在"重装之前"完成观测）

- [ ] **6.1 卸载前记录窗口起点**：`app status`、`file ls <VAR>`、`file prop <VAR>/app.env` `[实测]`
- [ ] **6.2 借用户真实动作卸载**：选「清除全部应用数据」（CLI 无法带向导卸载：`requires custom wizard parameters`）`[实测]`
- [ ] **6.3 窗口内判据（唯一有效）**
  ```bash
  $CLI --profile <p> file prop <VAR>/app.env      # 期望：errno（不存在）
  $CLI --profile <p> file ls <VAR>                # 期望：空或目录不存在
  ```
  判据：**`app.env` 不存在**且 `VAR` 目录空/不存在 ⇒ 清除分支执行过 `[实测]`
- [ ] **6.4 不要用这些判据**：`data/`、`home/`、`@apphome/<app>` 是否存在（会被 `mkdir -p` 重建，恒真）`[实测]`
- [ ] **6.5 错过窗口**：只能查旧数据残留（`data/config/.env`、`data/*.db`、`home/.<app>`）并用内容/时间戳区分新旧 ⇒ **记「未验证」，不得写「已验证」** `[实测]`
- [ ] **6.6 卸载后应用目录与 socket**：`TRIM_APPDEST` 下 `app.sock` 应随框架删除；若残留需在报告中记录 `[经验]`

### 7. 退出时必填的三栏

- [ ] **7.1 已实测**（命令 + 原始输出 + 包 sha + 账号 uid）
- [ ] **7.2 未验证**（明确列出，不许含糊）
- [ ] **7.3 判错复盘**（哪些判断被推翻、依据是什么——比结论更有复用价值）

---

## 附：一页纸最短路径

```
① 开工前：定访问模型（WS? 常驻? 登录态?）→ 依赖策略（双包线?）→ 数据落点 → 防线分工 → 可观测性
② 上架前：manifest 准确性 → 权限最小化 → 资源/Scope → 图标 → 九脚本硬规则 → 三闸门 → 材料+未验证声明
③ 真机：装前基线 → 装（识别 208s 误报）→ 入口（port=""）→ 未登录看响应体 → WS（先IP后域名 + flag 分支）
        → 安全（伪造头对照组）→ 卸载（窗口内 app.env）→ 三栏收口
```
