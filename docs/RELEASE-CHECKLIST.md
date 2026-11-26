# fnOS 上架材料要求与发布前门禁清单（RELEASE-CHECKLIST）

> 适用对象：JiuwenSwarm 的 fnOS 原生应用包（本仓库的 `manifest` + `app/` + `cmd/` + `config/` + `wizard/`）
> 用途：① 让开发一次把上架材料做对；② 作为发布审核的判定标尺（43 项门禁，每条都有合格判据与证据形式）
> 版本基线：应用包 `0.2.9-12`；上游 JiuwenSwarm `0.2.9b5`

> **证据引用约定（重要）**：文中出现的 `DEVICE-READY.md`、`ENTRY-SURVEY.md`、`VERIFY-REPORT.md`、
> `DELIVERY-NOTES.md`、`DELIVERY-CHECKLIST.md`、`QA-REPORT.md` 等，是**项目内部取证文件，不随本仓库发布**。
> 这些引用保留为"该判据当初由哪份证据支撑"的出处标记，读者按"内部证据（未公开）"理解即可；
> 门禁条目本身（检查方法 / 合格判据 / 证据形式）可独立使用，不依赖那些文件。
> 其中的型号、版本、uid、网段等实值，在本仓库一律以 `<FNOS_VERSION>`、`<APP_UID>`、`<NAS_IP>` 等占位符表示。

---

## 0. 证据边界与标注规则（先读这一节，否则后面的引用会被误读）

| 标注 | 含义 | 可靠性 |
|---|---|---|
| `[release §4]` `[dev-guide §4]` `[advanced §8]` `[open-api §1.1]` `[cli-tools §1]` | 已安装 skill `fnos-app-development` v1.1.1 的 `references/*.md` 章节 | **二手提炼层**：该 skill 自述「提炼自飞牛官方文档 developer.fnnas.com，2026-10 快照 v1.1.4」（`GENERATION.md` L3-L7）。**不是官网实时版**，上架前若官网已更新，以官网为准 |
| `[源码 path:line]` | 本次在项目内直接读取的代码取证 | 一手，可直接复核 |
| `[实测 …]` | device-ops 已在真机/网络上取得的证据，引用其报告文件与章节 | 一手（转引），报告见 `ENTRY-SURVEY.md` / `DEVICE-READY.md` |
| **【未覆盖】** | skill 文档中**没有**该条款 | 相对本文一律写「规范未明确，建议……」，**不得当作官方要求**执行或对外声明 |

> 未取得证据的条目在审核报告中一律记「未验证」，不接受「应该没问题」式结论。
> 本文不包含任何 token、密钥、密码。

---

## 1. 结论摘要

1. **官方文档对上架材料明确覆盖的只有 5 类**：manifest 元信息准确性、最终 `.fpk` 包、图标规格、截图真实性、发布前测试清单 `[release §4][advanced §8]`。
2. **明确未覆盖、必须提交前与官方确认的**：应用分类与标签、中英文名称/简介的字段与长度限制、截图尺寸/数量/格式、`.fpk` 包体上限、版本号语义规则（是否允许 build 号）、独立的「隐私与权限说明」文档格式。→ 见 A4/A5/A6/A8 与 §5 未验证项。
3. **门禁清单共 43 项**（B1 权限 6 / B2 资源与 Scope 6 / B3 生命周期 9 / B4 入口与网关 9 / B5 开放 API 7 / B6 卸载与验证 6），每项含「检查方法 + 合格判据 + 证据形式」。
4. **JiuwenSwarm 场景有 2 条架构级前置门禁**（§4 高风险点 R1、R2）：若最终采用「独立端口型」或「网关下 WS 不通」，则**不应进入上架流程**，先回到方案层重新决策。这两条不是材料问题，是能否上架的问题。

**分级定义（审核报告统一使用）**
- **P0 阻断上架**：安全漏洞、权限过大且无必要、数据丢失风险、授权缺失（含网关鉴权缺失）。
- **P1 上架前必须修复**：元信息错误、图标不合规、错误不可见、依赖未声明、可复现的功能缺陷。
- **P2 建议改进**：可维护性、日志可读性、文案。

---

## 2. A. 应用中心上架材料 Checklist

> 使用方式：app-dev 交付时逐行填「实际值 / 证据路径」；qa-reviewer 按「来源」列判定是否为官方要求。

### A1. manifest 元信息（必填与必须准确）

`[dev-guide §4]` 只把 `appname` 明确标为「必填」；其余字段是「文档列出」+ `[release §4]` 要求「应用名称、描述、版本、维护者、支持的系统版本范围、平台、更新说明——**务必准确**」。因此本表区分「必填（官方明示）」与「必须准确（官方明示）」两档。

| # | 字段 | 官方要求强度 | 内容要求 | 来源 |
|---|---|---|---|---|
| A1-01 | `appname` | **必填** | 应用唯一标识；建议与入口 ID 前缀、网关前缀、Socket 名一致（如 `jiuwenswarm`） | `[dev-guide §4]` |
| A1-02 | `version` | 必须准确 | 格式形如 `1.0.0` / `2.1.3-beta`；须与包内实际内容一致，不得复用旧版本号重新打包 | `[dev-guide §4][release §4]` |
| A1-03 | `display_name` | 必须准确 | 应用中心/设置/界面显示名；与截图、图标品牌一致 | `[dev-guide §4][release §4]` |
| A1-04 | `desc` | 必须准确 | 应用描述，必要时可用 HTML；**不得夸大能力或声明未实现的功能** | `[dev-guide §4][release §4]` |
| A1-05 | `source` | 必须准确 | 第三方应用填 `thirdparty` | `[dev-guide §4]` |
| A1-06 | `platform` | 必须准确 | `x86` / `arm` / `all`；**仅当不含特定架构二进制时才用 `all`**——包内若含架构相关二进制（wheel/native 依赖/预编译产物），必须分架构打包或声明对应架构 | `[dev-guide §4]` |
| A1-07 | `maintainer` / `maintainer_url` | 必须准确 | 维护者与可访问的支持地址 | `[dev-guide §4][release §4]` |
| A1-08 | `distributor` / `distributor_url` | 发布者≠开发者时填写 | 留空则默认等同开发者 | `[dev-guide §4]` |
| A1-09 | `os_min_version` | 必须准确 | 支持的最低 fnOS 版本。**网关型应用必须声明**（`[advanced §2]` 举例 `1.1.3100`） | `[dev-guide §4][advanced §2]` |
| A1-10 | `os_max_version` | 有明确上限时填写 | 无上限则不写，**不要随手写一个高版本号冒充「已验证」** | `[dev-guide §4]` |
| A1-11 | `changelog` | 必须准确 | 面向用户、简洁的更新说明；升级时展示，不得为空或写「fix bug」 | `[dev-guide §4][release §4]` |
| A1-12 | `ctl_stop` | 必须与形态一致 | 服务类需用户可启停填 `true`；静态/配置型填 `false`（隐藏启停按钮） | `[dev-guide §4]` |
| A1-13 | `install_type` | 按需 | 空=用户选存储位置；`root`=装系统分区（容量敏感，慎用） | `[dev-guide §4]` |
| A1-14 | `install_dep_apps` | 必须准确 | 依赖应用，`:` 分隔，`>` 声明最低版本；**依赖检查不递归，必须直接声明自己用到的全部依赖** | `[dev-guide §4][advanced §5]` |
| A1-15 | `desktop_uidir` / `desktop_applaunchname` | 必须与包内一致 | 后者须与 `{desktop_uidir}/config` 中入口 ID 完全一致，否则应用卡片点不开 | `[dev-guide §4][advanced §3]` |
| A1-16 | `service_port` / `checkport` | 按访问模型 | 端口型必填；**网关型无需声明**（声明即多暴露一个端口面）；`checkport` 默认 `true` | `[dev-guide §4][advanced §2]` |
| A1-17 | `disable_authorization_path` | 必须与实现一致 | 不需要用户选文件/目录时设 `true`；需要却设 `true` 会导致授权入口不可用 | `[dev-guide §4]` |
| A1-18 | `micro_app` | 使用 JS SDK 时必备 | 调用 `@trimjs/web-app` 必须 `micro_app=true`，否则 SDK 无法初始化 | `[open-api §1.2]` |

### A2. 图标规格（官方明确，属硬性）

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A2-01 | 包图标两个齐全 | 包根目录必须有 `ICON.PNG`（64×64）与 `ICON_256.PNG`（256×256），缺一即打包校验不通过 | `[advanced §8][cli-tools §1 打包检查]` |
| A2-02 | 格式/色彩 | PNG/JPG、sRGB | `[advanced §8]` |
| A2-03 | 体积 | 单文件 **≤1024 KB** | `[advanced §8]` |
| A2-04 | 画布与风格 | 完整正方形画布；视觉主体用**圆角矩形**风格（不要直角满铺）；圆角与留白与系统图标一致；重要内容不贴边；64px 下仍清晰可辨 | `[advanced §8]` |
| A2-05 | 入口图标 | `app/ui/images/icon_64.png` + `icon_256.png` 均在位，`config` 里写 `images/icon_{0}.png`（`{0}` 由 fnOS 替换） | `[advanced §8]` |

### A3. 截图与演示材料

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A3-01 | 真实性 | 截图必须展示**真实应用界面和核心流程**，不能用占位页、空状态页或开发期临时设计图 | `[release §4]` |
| A3-02 | 覆盖核心流程 | 至少覆盖：应用入口首屏 → 主任务执行（对话/任务提交）→ 结果产出 | `[release §4]` 精神（「核心流程」） |
| A3-03 | 尺寸/数量/格式 | **【未覆盖】** 规范未明确，建议：提交前向官方确认分辨率、张数、是否需 UI 内不带个人数据；截图内**不得出现真实用户名、文件路径、token、内网 IP** | 建议（非官方要求） |

### A4. 中英文名称与简介

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A4-01 | 中文名称/简介 | 由 `display_name` / `desc` 承载；需与应用实际功能一致 | `[dev-guide §4]` |
| A4-02 | 英文字段与长度限制 | **【未覆盖】** 规范未明确 manifest 是否有 i18n 字段、名称/简介的字符上限。建议：① 名称保持简短且不与系统应用重名；② 简介首句写清「是什么 + 解决什么」，再写依赖条件（如需 python312 / 需接入模型服务）；③ 提交前向官方确认表单字段与长度限制 | 建议（非官方要求） |
| A4-03 | 名称一致性 | 应用中心名称、桌面入口 `title`、截图内标题三者一致（不一致属 P1 元信息错误） | `[advanced §3]` + 一致性要求 |

### A5. 分类与标签

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A5-01 | 分类/标签字段 | **【未覆盖】** 规范未明确应用分类体系与标签字段（`manifest` 字段表中无分类项）。建议：按官方后台表单实际项填写；无表单项则不提；不要自造分类号 | 建议（非官方要求） |

### A6. 版本号与升级

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A6-01 | 版本格式 | 形如 `1.0.0` 或 `2.1.3-beta` | `[dev-guide §4]` |
| A6-02 | 升级语义 | 升级必须带非空 `changelog`；升级脚本走 `upgrade_init` / `upgrade_callback`，须保证旧数据可迁移 | `[dev-guide §4][dev-guide §8]` |
| A6-03 | 构建号/beta 标识规则 | **【未覆盖】** 规范未明确是否允许 `+build`、`rc`、语义化版本强约束。建议：对外发布只用 `X.Y.Z`，预发布用 `-beta`/`-rc` 后缀，同一版本号永不重发 | 建议（非官方要求） |

### A7. 依赖与 Scope 声明

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A7-01 | 运行时依赖 | 依赖运行时应用必须声明并注入 PATH：`install_dep_apps=python312`（或 `nodejs_v22` / `java-21-openjdk`），脚本内 `export PATH=/var/apps/python312/target/bin:$PATH` | `[advanced §7]` |
| A7-02 | 中间件依赖 | 仅声明实际用到的 `redis` / `minio` / `rabbitmq`；密钥不得硬编码进包 | `[advanced §6]` |
| A7-03 | 依赖顺序 | 多依赖**从右到左**安装启用（右边先就绪） | `[advanced §5]` |
| A7-04 | Scope 清单 | `api-scope` 只声明实际调用的 5 个之一/多个：`trim.file.sharedAccess` / `trim.file.userAccess` / `trim.file.userAcl` / `trim.file.path` / `trim.system.getPlatformConfig` | `[open-api §1.1]` |

### A8. 隐私与权限说明

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A8-01 | 独立隐私/权限说明文档 | **【未覆盖】** 规范未明确要求单独提交隐私说明文件（`release §4` 的发布材料只列 manifest、`.fpk`、图标与截图）。建议：在 `desc` 或说明文档中**主动写清**：① 会读写哪些用户数据（用户授权的目录）；② 是否外发数据（模型 API 会外发对话内容——若使用云端模型必须写明）；③ 数据存放位置（应用私有目录，卸载是否保留）；④ 不申请超出功能的 Scope | 建议（非官方要求） |

### A9. 提交方式与包

| # | 项 | 要求 | 来源 |
|---|---|---|---|
| A9-01 | 提交渠道 | 开发者后台上线前，通过「应用中心开发者先锋交流群」提交：飞牛官网（fnnas.com）→ 粉丝群 → 社区主理人 → 开发者群 → 按指引提交应用信息、包与测试材料；后台上线后以平台流程为准 | `[release §4]` |
| A9-02 | 包本体 | `fnpack build` 生成的最终 `.fpk`；打包前硬性校验项（manifest / privilege / resource / 双图标 / `app/` / `cmd/` / `wizard/` / `app/ui/`）全部通过 | `[cli-tools §1]` |
| A9-03 | 与包一致的测试材料 | 提交的测试材料须对应**同一版本**的包，不得用旧版截图/旧版包混提（一致性要求，属 P1） | `[release §4]` + 一致性要求 |

### A10. 发布前测试材料（作为上架附件）

`[release §4]` 原文清单（必须由 device-ops 在**计划支持的 fnOS 版本与硬件架构上都测**，不能只依赖一次成功安装）：

- 应用可按预期安装、打开、运行
- 主要流程可完成，无非预期错误
- 用户创建/导入的数据可正确保存、读取、更新、删除
- 用户无法访问未授权的数据或操作
- 本地 API、网络端口、后台任务只暴露真正需要的能力
- 若依赖外部服务/数据库/硬件/大模型：还要测**依赖不可用、配置错误、资源不足**时的表现

> 对 JiuwenSwarm 的落地判据：模型服务不可达时，界面必须给出可读错误而不是白屏/无限转圈（属 P1）。

---

## 3. B. 发布前质量门禁清单（逐条打钩）

> 每条格式：**检查方法 → 合格判据 → 证据形式**。
> 「证据形式」写清 qa-reviewer 要看到什么才算核验通过；拿不到就记「未验证」。

### B1. 权限最小化（6 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G1-01 | 运行用户 | 读 `config/privilege` 的 `defaults.run-as` | 为 `package`；若为 `root` 必须附「确实需要」的说明并限定在特权准备脚本 | 配置原文 + 说明 | `[dev-guide §5]` |
| G1-02 | 附加组 | 读 `join-groups` | 每一项都有对应代码路径的真实需要（如 `video`/`render`）；出现 `root`/`disk`/`docker` 等宽组即 P0 | 配置原文 + grep 依赖点 | `[dev-guide §5]` |
| G1-03 | 长期服务降权 | 读 `cmd/main` 启动段 | **面向用户、长期运行的进程不得以 root 运行**；root 脚本启动前用 `runuser -u "$TRIM_USERNAME" -- ...` 降权 | `cmd/main` 片段 | `[dev-guide §5][SKILL 关键约束一]` |
| G1-04 | 用户数据访问方式 | 读 `manifest.disable_authorization_path` + 实际读取路径来源 | 需要用户文件时：走授权（设置页/共享授权/用户授权）而非遍历整盘；不需要时设 `true` | manifest 片段 + 代码取样 | `[dev-guide §5]` |
| G1-05 | 输入信任边界 | grep 全部外部输入点 | 文件路径、请求参数、`uid`、Header 一律按不可信处理后再用 | grep 结果 + 校验代码 | `[dev-guide §5][advanced §2]` |
| G1-06 | 权限与功能匹配 | 交叉比对 Scope / 目录 / 端口与实际功能 | 不存在「声明了但用不到」的权限（Scope、data-share、join-groups、service_port 亦然） | 对照表（见附录模板） | `[open-api §1.1] 只声明真正用到的` |

### B2. 资源与 Scope 与实现一致性（6 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G2-01 | `data-share` | 读 `config/resource` 的 `data-share.shares` | 只在需要跨应用共享目录时声明；`name` 以应用名为顶级；代码侧从 `TRIM_DATA_SHARE_PATHS` 或 `/var/apps/{appname}/share/` 取路径，不硬编码 | 配置 + 代码 | `[dev-guide §6]` |
| G2-02 | `usr-local-linker` | 读配置 + 检查 `bin` 命名 | 只暴露真正需要的命令/库；命名带应用标识（`jiuwenswarm-cli`），不用 `cli`/`server`/`tool` 等通用名（会污染 `/usr/local/bin`） | 配置原文 | `[dev-guide §6]` |
| G2-03 | `docker-project` | 读配置 + 判断实际形态 | 仅 Docker 形态使用；`path` 下确有 `docker-compose.yaml` | 配置 + 文件清单 | `[dev-guide §6]` |
| G2-04 | `api-scope` 逐项对应 | 对每个声明的 Scope，`grep` 代码中的 `req` 名 | 每个 Scope 都有实际调用点；有调用点未声明的必须补（否则 403 `200003`） | Scope↔代码 对照表 | `[open-api §1.1][open-api §6.2]` |
| G2-05 | `micro_app` | 读 manifest + 检查前端是否 `import '@trimjs/web-app'` | 用 SDK → `micro_app=true`；不用 SDK → 不应声明（多余开关属 P2，但声明了不生效会造成误导） | manifest + 前端依赖 | `[open-api §1.2]` |
| G2-06 | 运行时依赖 | 读 `install_dep_apps` + 脚本 PATH | 声明了 runtime 应用；脚本内显式 `export PATH=/var/apps/<runtime>/target/bin:$PATH`；依赖版本与设备实际安装版本兼容 | manifest + 脚本 | `[advanced §7]` |

### B3. 生命周期脚本安全与幂等（9 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G3-01 | 脚本齐全 | `ls cmd/` | `install_init` `install_callback` `main` `upgrade_init` `upgrade_callback` `uninstall_init` `uninstall_callback` `config_init` `config_callback` 九个在位，模板文件未被删改丢失 | 目录清单 | `[dev-guide §8][cli-tools §1]` |
| G3-02 | `status` 退出码 | 读 `cmd/main` 的 `status)` 分支 | 运行中 `exit 0`，未运行 `exit 3`，其他 `exit 1`；**不得恒返回 0**（会让应用中心永远显示「运行中」） | 脚本片段 + 真机 `cmd/main status; echo $?` | `[dev-guide §8]` |
| G3-03 | 用户可见错误 | grep `TRIM_TEMP_LOGFILE` | 每个 `exit 1` 之前都把清晰、可执行的原因写入 `TRIM_TEMP_LOGFILE` | 脚本片段（逐个失败分支） | `[dev-guide §8][release §2]` |
| G3-04 | 幂等性 | 通读全部脚本 | 安装/升级/配置可能被重复执行：建目录/写配置/初始化数据均须幂等（存在即跳过或可安全覆盖） | 脚本 + 重复安装实测记录 | `[dev-guide §8]` |
| G3-05 | 删除边界（框架目录） | grep `rm -rf` | **绝不删除** `TRIM_APPDEST`/`TRIM_PKGETC`/`TRIM_PKGVAR`/`TRIM_PKGHOME`/`TRIM_PKGMETA`/`TRIM_PKGTMP`；只删应用自建子目录 | grep 全量结果（P0 一律阻断） | `[SKILL 关键约束一][dev-guide §8]` |
| G3-06 | 删除边界（用户数据） | 读 `uninstall_callback` + `wizard/uninstall` | 卸载清理用户数据须经向导收集用户选择，且只删自建数据目录；默认不删用户产出 | 脚本 + wizard 配置 | `[SKILL 关键约束一]` |
| G3-07 | 路径来源 | grep `/var/apps` | 脚本与代码中**不硬编码** `/var/apps/...`（运行时 PATH 拼接 `/var/apps/python312/target/bin` 属官方示例用法，可接受），一律用 `TRIM_*` 变量 | grep 结果 + 说明 | `[dev-guide §3]` |
| G3-08 | 日志方式 | 读脚本/服务启动参数 | 生命周期脚本错误直接输出 stdout/stderr，**不另行维护日志文件**；服务日志写入 `TRIM_PKGVAR` 下而非系统目录 | 脚本片段 + 日志落点 | `[SKILL 关键约束一]` |
| G3-09 | 特权操作时机 | 读 `install_callback` / `install_init` | 涉及安装目录、环境变量、安装后初始化的逻辑放在 `install_callback`（该阶段框架目录才生成） | 脚本片段 | `[SKILL 关键约束一]` |

### B4. 入口与网关实现（9 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G4-01 | 入口前缀 | 读 `app/ui/config` 的 `.url.*.gatewayPrefix` | 必须为 `/app/{appname}` 或 `/app/{appname}/{customPath}`；版本间保持稳定；公开路径无点号 | 配置原文 | `[advanced §2]` |
| G4-02 | Socket 落点 | 读 `gatewaySocket` + 检查文件路径 | 只填文件名（如 `app.sock`），实际 Socket 文件落在 `${TRIM_APPDEST}`（`target`）下 | 配置 + 代码中 socket path | `[advanced §2]` |
| G4-03 | 最低系统版本 | 读 `manifest.os_min_version` | 网关型必须声明（`[advanced §2]` 举例 `1.1.3100`）；与真机 `<FNOS_VERSION>` 对比须满足 | manifest + `DEVICE-READY.md §3` | `[advanced §2]` |
| G4-04 | 可信身份来源 | grep `x-trim-` / `X-Trim-` | 身份**只**取自 `X-Trim-Userid` / `X-Trim-Isadmin` / `X-Trim-Username`；绝不从 query/body/cookie 取 uid | 代码片段 | `[advanced §2][SKILL 关键约束二]` |
| G4-05 | WebSocket 身份绑定 | 读 WS 握手处理 | 连接建立后用 `X-Trim-Userid` 绑定会话，后续帧不重读客户端传来的 uid；WS 路径建议稳定子路径 `/app/{appname}/ws` | 代码片段 | `[advanced §2]` |
| G4-06 | 路径穿越防护 | grep 静态文件/文件读取处理 | 标准化路径后拒绝 `..`；只从预期应用目录提供文件；非法路径返回明确状态码；**绝不把请求路径拼进 shell** | 代码片段 + 负例请求实测 | `[advanced §2][advanced §4]` |
| G4-07 | 入口字段合规 | 读 `app/ui/config` 每个入口 | 入口 ID 稳定且带 appname 前缀；`icon` 用 `images/icon_{0}.png` 且两个尺寸文件都在位；管理员专用入口同时 `allUsers=false` + `control.accessPerm=readonly`；`fileTypes` 只声明真正支持的类型 | 配置 + images 目录 | `[advanced §3][advanced §8]` |
| G4-08 | 端口暴露面 | 读 manifest + 入口配置 | 网关型**不声明** `service_port`（多一个 LAN 可达端口就是多一个未鉴权入口面，参见 R1） | manifest 原文 | `[advanced §2][ENTRY-SURVEY §2.4]` |
| G4-09 | 若走 index.cgi | 读 `app/ui/index.cgi` | `BASE_PATH` 指向 `${TRIM_APPDEST}/www`；不支持 WebSocket（有 WS 需求就不能走这条）；同样做穿越防护 | 脚本片段 | `[release §2][advanced §4]` |

### B5. 开放 API 授权最小化（7 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G5-01 | token 读取方式 | grep `TRIM_API_TOKEN` | 每次从环境变量读取；**不落数据库/文件/配置/前端**；不打印日志 | grep 全量 + 落盘检查 | `[open-api §1.3][SKILL 关键约束二]` |
| G5-02 | 调用通道 | grep `/var/run/trim_open_gateway_apiscope.socket` | 只由应用服务端经 Unix Socket 调用；前端代码中**无** socket 路径与 token | 代码 + 前端构建产物检索 | `[open-api §1.3]` |
| G5-03 | 返回前鉴权 | grep `checkUserACL` | 返回列表/预览/写入/删除前按当前用户 `uid` 检查 `readable`/`writable`/`deletable`；不允许只凭「应用已获目录 ACL」就放行 | 代码片段（每个读写点） | `[open-api §2.4]` |
| G5-04 | 路径展示 | grep `convertPath` | 对用户展示路径时必须转换；`language` 按当前界面语言传（**必填**） | 代码片段 | `[open-api §2.5]` |
| G5-05 | 共享授权限制 | grep `sharedAccess` 调用 | 仅管理员可调（普通用户会失败）；**只支持目录**；前端入口对非管理员隐藏或给出明确提示 | 代码 + 真机普通用户实测 | `[open-api §2.2]` |
| G5-06 | 用户授权语义 | grep `getUserAccessibleFolders` | 只有目录结果、不含文件授权——实现不得假设文件授权可从该接口回读，需自行持久化选择器返回的路径 | 代码片段 | `[open-api §2.3]` |
| G5-07 | 错误处理 | 读 API 调用封装 | 非 0 `code` / 非 200 有明确分支：后端 `200003`（Scope 缺失/无权限）、`200004`（token 无效）、前端 JSSDK `1000002`（Scope 或管理员不足）等，须给用户可读提示，不吞异常、不白屏 | 代码 + 真机负例（改坏 Scope 后观察） | `[open-api §6.1][open-api §6.2]` |

### B6. 卸载、数据保留与上架验证（6 项）

| ID | 检查项 | 检查方法 | 合格判据 | 证据形式 | 来源 |
|---|---|---|---|---|---|
| G6-01 | 卸载流程 | 读 `uninstall_init` / `uninstall_callback` / `wizard/uninstall` | 先停服务再清理；向导给出「保留/删除用户数据」选择并按其执行 | 脚本 + 真机卸载实测 | `[dev-guide §8][SKILL 关键约束一]` |
| G6-02 | 数据保留策略 | 检查数据落点 | 需持久化的数据在 `TRIM_PKGVAR` / `TRIM_PKGHOME`；重装/升级后仍可读取；临时文件在 `TRIM_PKGTMP` | 目录树 + 升级前后对比 | `[dev-guide §3][dev-guide §7]` |
| G6-03 | 重复安装/升级 | `appcenter-cli install-fpk` 同包二次安装 + 升级测试 | 无重复报错、无数据丢失、`status` 正确 | 命令与输出 | `[dev-guide §8][cli-tools §2]` |
| G6-04 | 安装→打开→运行 | 真机全链路 | 应用中心可装、桌面入口可开、进程在跑、端口/Socket 在听 | `app entry list` + `monitor proc-srv` + 入口实测 | `[release §1][release §2]` |
| G6-05 | 主要流程与数据 CRUD | 真机按核心流程走一遍 | 无未预期错误；用户创建/导入的数据可保存、读取、更新、删除 | 操作步骤 + 截图/日志 | `[release §4]` |
| G6-06 | 依赖不可用降级 | 停掉模型服务/中间件后再试核心流程 | 给出可读错误并可恢复，不崩溃、不死循环重试 | 实测记录 | `[release §4]` |

---

## 4. C. JiuwenSwarm 场景必看的 5 个高风险点

> 这 5 条不是「材料格式问题」，而是**可能直接决定能否上架**的架构风险。每条都给：事实与证据 → 后果 → 门禁判据 → 复核方式。

### R1（P0 级前置门禁）应用自身在源码 Web 模式下**没有鉴权**

**事实与证据**
- 源码模式（`desktop_token` 为空）下 `_check_desktop_access()` 直接 `return False`，即**不做任何校验**：`jiuwenswarm/channels/web/app_web.py:1261-1268`（docstring 原文：「源码 web 模式 (desktop_token 为空) 恒返回 False, 不做任何校验」）。
- 桌面锁定机制只在 `desktop_token` 非空时生效（`app_web.py:1295-1300` 下发 HttpOnly Cookie，否则 `_send_desktop_forbidden()`）；该 token 由桌面启动器生成，fnOS 包内的常驻服务不会自带。
- 对照实测：设备上 7 个**端口型**第三方应用在 LAN 上**不登录即可访问首页** `[ENTRY-SURVEY §2.4]`；而网关路径型在未授权时返回 `200 invalid token`，即由 fnOS nginx 统一鉴权 `[ENTRY-SURVEY §2.3]`。

**后果**：若最终用「独立端口型」暴露服务，等于把一个可执行工具（能读写文件、跑命令）以**无鉴权**形式开放给整个局域网 → **P0，直接不可上架**。

**门禁判据（任一不满足即不得提交）**
1. 必须为统一网关路径型（`/app/jiuwenswarm` + `gatewaySocket`），且 `manifest` 不声明 `service_port`；
2. 应用必须消费 `X-Trim-Userid` 作为唯一身份来源，管理类操作校验 `X-Trim-Isadmin`；
3. 若因 WS 不通被迫保留端口形态，则**必须在应用内自建鉴权**（此路径无官方支持文档，属额外风险，需 Leader 决策并写进遗留风险）。

**复核方式**：安装后从同网段另一台机器 `curl http://<IP>:5666/app/jiuwenswarm`（须为 `invalid token` 或登录态页面，**不能是 `text/plain` 之外的可直接使用界面**）；同时确认设备上 `nmap`/`monitor` 视角**没有**新增 LAN 可直接访问的 application 端口。

---

### R2（P0 级前置门禁）网关前缀 + **WebSocket 透传**未验证

**事实与证据**
- JiuwenSwarm 个人版默认走 WebSocket 传输：`_web_transport()` 返回 `websocket`（`app_web.py:491-499`），并以自研 handler 处理 upgrade（`_is_websocket_upgrade` `:806`、`_proxy_websocket_tunnel` `:995`）。
- fnOS 网关下 WS 是否被正常代理：**`[未验证]`**——`[ENTRY-SURVEY §5.1]` 明确指出「`/app/<name>` 前缀下的 WS 升级是否被 fnOS 网关正常代理是本次裁决最大的未知数」；原因见 `[ENTRY-SURVEY §2.3]`：未登录前一律 `invalid token`，无法观察路由行为。
- 网关字段约束：`gatewayPrefix` 必须 `/app/{appname}`，`protocol`/`port` 被忽略 `[advanced §2]`。

**后果**：WS 不通 → 对话流、实时任务、长连接全部失效，应用「能打开但不能用」→ 属 P1 功能缺陷；若强行改用端口型又触发 R1 的 P0。

**门禁判据**
1. 前端所有静态资源与 API 支持 base path `/app/jiuwenswarm`（不得硬编码根路径 `/`）；
2. WS 连接地址由 `window.location` 推导（`wss://host/app/jiuwenswarm/ws`），不写死 `127.0.0.1:port`；
3. 真机登录态下浏览器 DevTools 中 WS 握手返回 **101**，且能持续收发帧；
4. 长响应（模型流式输出）不被网关超时截断（`[未验证]`，需压测）。

**复核方式**：device-ops 提供 DevTools Network 截图或 `wscat`/`curl -i -N -H "Upgrade: websocket"` 输出；qa-reviewer 只认 101 与后续帧证据，不接受「本地能连」替代。

---

### R3（P1）常驻 Python 服务的托管语义与状态真实性

**事实与证据**
- 服务为 Python 标准库 `ThreadingHTTPServer`（`app_web.py:31` 导入、`:3561` 启动），运行时要求 `requires-python = ">=3.11,<3.15"`（`pyproject.toml:10`）→ 必须依赖设备上的 `python312`（真机已装 **v3.12.4-11**，`[DEVICE-READY §3]`），且**版本上限 3.15 之外不可用**。
- fnOS 对 `cmd/main status` 的判定是 `0=运行中 / 3=未运行` `[dev-guide §8]`；应用自带守护逻辑时须改测自身 status `[SKILL 关键约束一]`。
- 真机默认 `autoRunNewApp=true`，安装后会自动启动 `[ENTRY-SURVEY §6 第 6 条]` → 验证「不自动启动」需显式 `--no-start`。

**后果**：`status` 恒返回 0 会让应用中心永远显示「运行中」，服务崩溃后用户无从察觉；PATH 未注入会导致 `python3` 解析到系统旧版本而启动失败（且错误未必写进 `TRIM_TEMP_LOGFILE`）。

**门禁判据**：`status` 退出码随真实 PID 变化（杀掉进程后必须变 3）；启动失败必须写 `TRIM_TEMP_LOGFILE`；`ctl_stop` 与是否允许手动启停一致。
**复核方式**：真机 `cmd/main status; echo $?` → `kill` 服务 → 再 `status` → 两次退出码必须不同；`cat` 安装失败时的 `TRIM_TEMP_LOGFILE`。

---

### R4（P1）包体量与安装体积

**事实与证据**
- 项目源码树 **545 MB**（`du -sh jiuwenswarm` 实测 2026-11-26）；其中 `jiuwenswarm/channels/web` 47 MB（含前端 dist）、`jiuwenswarm/resources` 14 MB。
- 打包硬校验项只校验结构，**未提及包体上限** → 包大小限制 **【未覆盖】**，`[cli-tools §1]` 无相关条目。

**后果**：体积过大 → 上传/安装耗时、存储占用、升级失败回滚风险；含 `.git`、`tests`、缓存会显著放大（`.git` 通常与工作树同量级）。

**门禁判据**：打包内容排除 `.git`、`tests`、`__pycache__`、`node_modules`（若已构建为 dist）、日志与本地数据；在报告中给出 `.fpk` 实际大小与安装后占用；与官方确认是否有大小限制（提交前）。
**复核方式**：`fnpack build` 后 `ls -lh *.fpk`、`du -sh` 解包内容；install 后 `du -sh <VOL>/@appcenter/jiuwenswarm`。

---

### R5（P1）数据目录落点与设备历史残留冲突

**事实与证据**
- 设备上**已存在** `jiuwenswarm` 残留目录（`[ENTRY-SURVEY §2.8]`）；`DEVICE-READY §6 第 7 条` 要求在安装前对 `<VOL>/@app{meta,share,data,home,conf}/jiuwenswarm` 做存在性/mtime 快照，安装后对比，判断是「复用」还是「覆盖历史残留」。
- 框架目录由系统统一创建/迁移/回收，`TRIM_PKGVAR` 等**绝不可 `rm -rf`** `[SKILL 关键约束一]`。
- JiuwenSwarm 会写 workspace / 会话 / skills / 记忆等运行数据，落点必须显式指向 `TRIM_PKGVAR` / `TRIM_PKGHOME`（`[dev-guide §7]`）。

**后果**：数据写进包目录（`target`）→ 升级即丢；或写进系统目录 → 卸载残留、多用户数据互串；覆盖历史残留目录 → 可能读到上一版不兼容的配置而启动异常。

**门禁判据**：所有可写路径来自 `TRIM_PKGVAR`/`TRIM_PKGHOME`/`TRIM_PKGTMP`；`install_callback` 对历史目录做兼容处理（检测到旧版数据时给出明确提示或迁移，不静默覆盖）；卸载向导提供「保留数据」选项。
**复核方式**：安装前后快照对比表；升级（同包二次安装）后检查会话/配置是否仍在；卸载后检查 `@appdata` 是否符合所选策略。

---

## 5. 未验证项与「规范未明确」汇总（提交前必须闭环）

| # | 项 | 状态 | 需要什么材料 / 怎么闭环 |
|---|---|---|---|
| U1 | 截图尺寸、数量、格式、是否需去敏 | **规范未明确** | 向官方开发者群/主理人确认；同时按「真实界面 + 去敏」自设下限 |
| U2 | 应用分类体系与标签字段 | **规范未明确** | 以官方后台表单实际项为准；manifest 无对应字段 |
| U3 | 中英文名称/简介的字段与长度限制 | **规范未明确** | 提交前问官方；暂按 A4-02 建议执行 |
| U4 | `.fpk` 包体上限 / 上传限制 | **规范未明确** | 问官方；无论有无上限都应按 R4 裁剪 |
| U5 | 版本号是否允许 `+build` / `rc` 等语义 | **规范未明确** | 问官方；对外统一 `X.Y.Z` + `-beta` |
| U6 | 是否需要独立隐私说明文档 | **规范未明确** | 问官方；无论是否需要都建议在 `desc` 明示数据流向 |
| U7 | 网关下 WebSocket/SSE 是否被代理 | **未验证（关键）** | device-ops 安装后 101 握手 + 持续收发实测（R2） |
| U8 | 网关鉴权通过后的真实路由行为（是否 strip 前缀、改写 Host/Origin） | **未验证** | 安装后观察；`app config proxy-access` 属写操作，需谨慎 |
| U9 | 网关/nginx 对长响应、大响应体的超时与体积限制 | **未验证** | 大模型长输出压测 |
| U10 | 文档快照时效性（v1.1.4 / 2026-10）与官网实时差异 | **需复核** | 上架前对照 developer.fnnas.com 现行条款 |

---

## 6. 附录：交付前自查表模板（app-dev 填写，随包提交）

```
应用名 / 版本：
包路径与 sha256：
fnpack 版本：
构建命令：

[ ] A1-01..A1-18 manifest 字段已核对，实际值见下表
[ ] A2-01..A2-05 图标规格已核验（附 ICON.PNG / ICON_256.PNG 尺寸与体积）
[ ] A3 截图取自真实界面（附文件清单）
[ ] A7 依赖与 Scope 逐项对应代码调用点
[ ] B3 全部 9 项生命周期门禁自测通过（附 status 退出码记录）
[ ] B4 网关配置逐字段核对（附 app/ui/config 原文）
[ ] B5 全部 7 项开放 API 门禁自测通过（附 grep 证据）
[ ] R4 包体已裁剪，给出 .fpk 实际大小
[ ] 已知未验证项：______（不得留空，无则写「无」）
```

**权限/资源对照表**（qa-reviewer 用于判定「声明即需要」）

| 声明项 | 声明值 | 对应代码/脚本位置 | 是否真实需要 | 判定 |
|---|---|---|---|---|
| `privilege.run-as` | | | | |
| `join-groups` | | | | |
| `data-share` | | | | |
| `usr-local-linker` | | | | |
| `api-scope`（逐项） | | | | |
| `service_port` | | | | |
| `install_dep_apps` | | | | |

---

## 7. 审核产出模板（qa-reviewer 出报告时使用）

```
结论：可上架 / 修复后可上架 / 暂不可上架
审核范围：□ 全量上架审核  □ 定向复核（变动点：______）
待审对象：工程目录 <path>  ／ .fpk <path> + sha256  ／ 真机验证报告 <path>

一、已核验通过（条目编号 + 一行证据）
二、已核验不通过
   | 编号 | 级别 | 位置 | 问题 | 证据 | 建议 |
三、未验证（说明缺什么材料、谁来补）
四、复核方式（只复核变动点与受影响项）
```

---

## 8. 修订记录：R1 门禁从「权限位」升级为「运行时 peer 身份校验」（2026-11-26 追加）

Leader 定调后，R1 的判定方式与判据变更如下，**t4 以此为准**（替代 §4-R1 中「必须网关型 + 不声明 service_port」之外的权限位判断）。

### 8.1 背景
初版预审发现 `app/server/uds_gateway.py:276` 将网关 UDS 设为 `0o666`，当时判为 P0：唯一门禁是 `X-Trim-Isadmin: true`，而 0666 下同机任意用户进程可直连 socket 伪造该头。
修复方案改为 **`SO_PEERCRED` 运行时校验对端进程身份**（accept 后取 `pid/uid/gid`，比对 `/proc/<pid>/exe` 或 `/proc/<pid>/comm` 是否属于网关），文件权限降为第二道防线。

### 8.2 修订后的门禁判据（G4-10，新增）
| 项 | 要求 |
|---|---|
| 判定时机 | accept 后、读请求前立即 `getsockopt(SO_PEERCRED)` |
| 身份匹配 | `/proc/<pid>/exe` basename 或 `/proc/<pid>/comm` 命中网关白名单 |
| 权限不足兜底 | 读 `exe` 出现 EACCES 时退到 `comm`；两者都读不到 → **拒绝**（fail-closed，不得「读不到就放行」） |
| 进程已退出 | `/proc/<pid>` 不存在 → 拒绝 |
| 白名单可配 | 走 `${TRIM_PKGVAR}/app.env`（`init_env.sh` 末尾已 source），使真机误拒可改配置修复，**无需重打包** |
| 拒绝日志 | 结构化输出 `403 peer uid= gid= pid= comm= exe=`，供一次真机即自证网关身份 |
| 文件权限 | 0660/0666 均可接受，但报告中须写明「依赖 peer 校验，文件权限仅纵深防御」 |

### 8.3 行为验证用例（t3 顺带执行，均为只读 curl；不看权限位猜结论）
| 用例 | 身份 | 操作 | 合格判据 | 不过的定性 |
|---|---|---|---|---|
| **N1** 伪造 peer | 本机**非 root、非网关**账号 | `curl --unix-socket ${TRIM_APPDEST}/app.sock -H 'X-Trim-Isadmin: true' ...` | HTTP 403 | P0 |
| **N2** 伪造头经网关 | **非管理员** NAS 用户 + 登录态 | `curl -H 'X-Trim-Isadmin: true' https://<IP>:5667/app/jiuwenswarm` | HTTP 403 | **P0**：说明 fnOS nginx 未覆盖客户端自带 `X-Trim-Isadmin`，app 侧校验无法补救 |
| **N3** 防误拒 | 管理员 + 登录态 | 正常打开 `/app/jiuwenswarm` | 200 且页面可用 | P0 回归，不接受「退回 0666」 |

> N1 中 root 被拒或放行均属设计预期，不判失败——因此测试身份必须在记录中写明。
>
> **N2 失败时的替代方案受文档约束**：`[open-api §1.1]` 的 Scope 表只有 `trim.file.sharedAccess` / `trim.file.userAccess` / `trim.file.userAcl` / `trim.file.path` / `trim.system.getPlatformConfig` 五项，**没有任何「查询用户是否为管理员」的接口**。「用 `X-Trim-Userid` 反查管理员身份」在官方开放 API 上没有对等能力，不能作为落地方案写进交付文档。N2 失败后现实可选项只有：① 应用自建鉴权（首次启动设置管理员口令，或一次性初始化 token，不依赖网关注入头）；② 放弃「仅管理员」主张，改为全登录用户可用并在应用内划权限边界。

**这不是二选一的中立选项（Leader 裁决，2026-11-26）**：
- **选①，不选②**。方案②等于把 JiuwenSwarm 的文件读写与命令执行能力开放给 NAS 上的所有账号（家庭场景下可能包含访客账号）——这不是权限配置问题，而是把 shell 交给全家，风险面在 NAS 产品里不可接受。
- 方案①的代价是改交互与数据结构（首次启动设管理员口令 / 一次性初始化 token），但它是 N2 失败时唯一自洽的路。
- 因此 N2 返回 200 时，处理方式是**切换方案①并重做入口鉴权部分**，而不是降级为全用户可用。

### 8.4 前置口径：方案①的「首次启动窗口」（Leader 定，2026-11-26；仅在 N2 失败时生效）

若 N2 返回 200 而启用方案①，「首次启动 → 管理员设口令」之间必须 deny-by-default，口径已定，不要在实施时临时设计：

1. **口令未初始化时**：所有业务请求一律 403，只放行初始化页面本身；
2. **一次性初始化令牌**：安装/首次启动时随机生成，写入 `${TRIM_PKGVAR}/` 下仅属主可读的文件（`0600`）；其**位置**在安装日志与 `cmd/main status` 输出中提示（不打印令牌本身）；
3. **用后即失效**；严禁「口令为空即放行」之类兜底——那正是被规避的窗口。

**待定风险（实施时必须一并解决，不在上文三点头内）**：令牌的**分发通道**与 N2 失败的前提相互冲突——

- 若靠「`X-Trim-Isadmin` 才能看到初始化页」，则在 N2 失败的前提下该头本身不可信，等于把令牌泄露给任何能伪造头的用户，方案自相矛盾；
- 因此 N2 失败后，令牌只能靠**带外通道**交付：管理员在设备上以 root/应用用户身份读取该文件，或由安装流程输出到仅管理员可见的位置。
- 必须在安装文档里写明「首次初始化需要设备侧读取令牌」这一步，否则用户会卡在初始化页无法进入（属 P1 体验缺陷）。

> **表述修正（Leader，2026-11-26）**：上文第 1 点「只放行初始化页面本身」**不是**「初始化页要判身份才给看」——那样会踩进下面的自相矛盾。
> 正确理解：① 初始化页对任何人可见都无所谓，它只是一张表单、不执行特权操作；② 真正的门是**令牌**，没有令牌看到页面也只是空壳；③ 令牌走带外通道分发（设备侧以 root/应用用户读 `${TRIM_PKGVAR}` 下 0600 文件），首次初始化须在安装文档写清这一步；④ 令牌首次使用后立即失效，并绑定首个完成初始化的会话。
> 如此则即使 N2 失败、身份头完全不可信，方案依然自洽：**公开入口 + 私密令牌，安全性不依赖任何可伪造的头**。

> 若 N2 通过（网关注入头可信），本节整体作废，不实施方案①。

### 参考文件

- 技能证据：`<SKILL_DIR>/fnos-app-development/{SKILL.md, GENERATION.md, references/{dev-guide,advanced,open-api,cli-tools,release}.md}`（手写提炼层，快照 v1.1.4 / 2026-10）
- 项目证据：`jiuwenswarm/jiuwenswarm/channels/web/app_web.py`、`jiuwenswarm/pyproject.toml`
- 真机证据：`DEVICE-READY.md`（§2.5 待安装包为空、§3 设备基线）、`ENTRY-SURVEY.md`（§2.3 未授权 HTTP 实测、§2.4 端口型裸奔、§2.8 残留目录、§5 未验证项、§6 验收检查点）
