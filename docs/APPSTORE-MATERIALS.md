# 应用中心上架材料清单（JiuwenSwarm for fnOS）

> 对应 `RELEASE-CHECKLIST.md` A1–A8 逐项填写。标注规则：
> **【官方】** = 已安装技能 `fnos-app-development` 引用官方文档明确要求；**【未覆盖】** = 规范未明确，按建议处理，提交前需向官方确认。

## A1. manifest 元信息

| # | 字段 | 实际值 | 证据 / 位置 |
|---|---|---|---|
| A1-01 | `appname` | `jiuwenswarm` | `manifest:1`；与网关前缀 `/app/jiuwenswarm`、Socket 名、入口 ID 前缀一致 |
| A1-02 | `version` | `0.2.9-12` | `manifest:2`；fnpack 1.3.3 只接受 `x.y.z[-r]`（整数），上游 `0.2.9.beta5` 的第 8 次打包修订；pip 版本仍为 `0.2.9b5`（`app/server/VERSION`）。上一版为 `0.2.9-7` |
| A1-03 | `display_name` | `JiuwenSwarm` | `manifest:3`；与桌面入口 `title`、图标品牌一致 |
| A1-04 | `desc` | 多智能体协作与 Skill 自演进工作台，经统一网关访问，模型 API Key 本机配置，数据保存在应用数据目录 | `manifest:4`；未声明未实现能力 |
| A1-05 | `source` | `thirdparty` | `manifest:5` |
| A1-06 | `platform` | `x86` | `manifest:6`；包内含 cp312 manylinux x86_64 wheel，**不能用 `all`** |
| A1-07 | `maintainer` / `maintainer_url` | `openJiuwen` / `https://gitcode.com/openJiuwen/jiuwenswarm` | `manifest:8-9` |
| A1-08 | `distributor` / `distributor_url` | 未声明（发布者=维护者，避免占位 URL 被打回） | `manifest` 无该字段 |
| A1-09 | `os_min_version` | `1.1.3100` | `manifest:13`；网关型必需 |
| A1-10 | `os_max_version` | 未声明 | 无明确上限，不虚写上界 |
| A1-11 | `changelog` | 首个飞牛 fnOS 版本：统一网关入口 /app/jiuwenswarm，离线 wheel 集安装，数据落应用数据目录 | `manifest:22` |
| A1-12 | `ctl_stop` | `true` | 服务型，允许用户启停 |
| A1-13 | `install_type` | 未声明（用户选存储位置） | 默认行为 |
| A1-14 | `install_dep_apps` | **声明 `install_dep_apps=python312`** | 工作区 `manifest:21` 即上架形态（历史 test 包由构建期暂存删行得到，该形态已随 test 档位移除）；CLI 安全闸对带依赖包拦截（实测），唯一安装通道为应用中心 UI；运行时探测见 A7-01 |
| A1-15 | `desktop_uidir` / `desktop_applaunchname` | `ui` / `jiuwenswarm.main` | 与 `app/ui/config` 中入口 ID 完全一致 |
| A1-16 | `service_port` / `checkport` | **不声明** / `false` | 网关型不得声明 service_port（上架门禁 R1） |
| A1-17 | `disable_authorization_path` | `true` | 不访问用户目录，不申请授权路径 |
| A1-18 | `micro_app` | 未声明 | 未使用 `@trimjs/web-app`（上游前端不依赖该 SDK） |

## A2. 图标规格

| # | 项 | 实际值 |
|---|---|---|
| A2-01 | 包图标 | `ICON.PNG` 64×64（2,258 B）、`ICON_256.PNG` 256×256（9,541 B），均 < 1024 KB；RGBA、四角透明（圆角外 alpha=0） |
| A2-02 | 格式/色彩 | PNG、8-bit RGBA（带 alpha），未嵌入 ICC，按 PNG 默认解释为 sRGB |
| A2-03 | 体积 | 均 ≤ 1024 KB ✅ |
| A2-04 | 画布与风格 | 完整正方形；橙色圆角方形满铺、四角透明，白色网络节点图形居中、不贴边；由官方 SVG（`viewBox 0 0 28 28`）渲染，64px 下可辨 |
| A2-05 | 入口图标 | `app/ui/images/icon_64.png`（2,258 B）、`icon_256.png`（9,541 B）在位且与包图标同源同哈希；`config` 引用 `images/icon_{0}.png` |

复算命令：`identify ICON.PNG ICON_256.PNG app/ui/images/*.png` → 64×64 / 256×256。
本轮图标由官方 SVG（sha256 `34f39694…`）用 `rsvg-convert` 渲染，新旧哈希见 `docs/fix-log/ICONS.md`。

## A3. 截图与演示材料（提交前需补齐真实截图）

| # | 项 | 要求 / 计划 |
|---|---|---|
| A3-01 | 真实性【官方】 | 必须为安装后真实界面截图，禁止占位页/设计稿 |
| A3-02 | 覆盖核心流程【官方】 | 计划 3–4 张：① 应用入口首屏（会话列表）② 模型配置页（API Key 已打码）③ 会话对话与工具调用 ④ 产出文件/技能页 |
| A3-03 | 尺寸/数量/格式【未覆盖】 | 建议 1920×1080 PNG，3–5 张；截图内**不得出现真实用户名、内网 IP、API Key、文件路径** |

> 本次交付不含截图（无真机登录态），由 t3 安装验证后补拍。

## A4. 中英文名称与简介

| # | 项 | 内容 |
|---|---|---|
| A4-01【官方】 | 中文名称/简介 | 名称 `JiuwenSwarm`；简介见 `manifest` `desc` |
| A4-02【未覆盖】 | 英文/长度 | 未提供独立英文字段；建议英文名 `JiuwenSwarm`，英文简介：`Multi-agent collaboration and self-evolving skill workbench, accessible through the fnOS gateway.` 长度限制提交前向官方确认 |
| A4-03【官方】 | 一致性 | 应用中心名称、桌面入口 `title`、截图标题统一为 `JiuwenSwarm` |

## A5. 分类与标签【未覆盖】

规范 `manifest` 无分类字段。建议后台表单中归入「开发工具 / AI」，标签：`AI`、`Agent`、`多智能体`、`工作流`；不自造分类号。提交前向官方确认可选项。

## A6. 版本号与升级策略

| # | 项 | 内容 |
|---|---|---|
| A6-01【官方】 | 版本格式 | **实测 fnpack 1.3.3 要求 `x.y.z[-r]`（r 为整数）**，`-beta.5` 会被拒绝；当前 `0.2.9-12`（= 上游 beta5） |
| A6-02【官方】 | 升级语义 | `upgrade_init` 停止服务 → 替换 target → `upgrade_callback` 按新版本重建 venv（`$TRIM_PKGVAR/venv`），数据目录 `$TRIM_PKGVAR/data` 不动；`changelog` 必填 |
| A6-03【未覆盖】 | 构建号 | 不使用 `+build`；预发布用 `-r` 序号（fnpack 实测约束）；同一版本号不重发 |
| — | 兼容基线 | 升级前版本的数据目录结构由上游迁移逻辑兼容（`common/paths.py` 兼容软链）；本包只保证不改数据目录路径 |

## A7. 依赖与 Scope 声明

| # | 项 | 内容 |
|---|---|---|
| A7-01【官方】 | 运行时依赖 | **声明 `install_dep_apps=python312`**，应用中心 UI 安装时自动处理依赖；`init_env.sh` 依次探测 `/var/apps/python312/target/bin/python3` → `python3.12` → `python3` 并校验主版本 3.12，找到后注入 PATH；缺失时 `cmd/main start` 写明确错误、`status=3` |
| A7-02【官方】 | 中间件依赖 | **无**（未使用 redis/minio/rabbitmq；不使用外部数据库） |
| A7-03【官方】 | 依赖顺序 | 单依赖，无顺序问题（manifest 已声明 `install_dep_apps=python312`，应用中心 UI 安装时自动处理） |
| A7-04【官方】 | API Scope | **无**：不调用飞牛开放 API，`config/resource` 为 `{}`；不申请 `trim.file.*` / `trim.system.*`；**不读写用户共享目录，仅访问应用自有数据目录** |
| — | 共享目录 | **无** `data-share`；不读写用户共享目录 |
| — | 网络出站 | 运行期仅访问用户配置的模型 API（由用户填写 endpoint），以及可选能力的运行时下载（默认不启用） |

**Python 依赖清单**：见 `app/wheelhouse/WHEELS.txt`（名称 / 版本 / sha256，逐行可核对）。

## A8. 隐私与权限说明【未覆盖，主动说明】

| 项 | 说明 |
|---|---|
| 读写哪些数据 | 仅应用私有目录：`$TRIM_PKGVAR/data`（配置/会话/技能/产出）、`$TRIM_PKGVAR/venv`、`$TRIM_PKGTMP`；不访问用户共享目录，不申请授权路径 |
| 是否外发数据 | **会**：对话内容、提示词与工具结果会发送到用户自行配置的模型服务（云端或本地）；API Key 仅存本机 `data/config/.env`，不随包、不上传 |
| 数据存放位置 | 全部在 NAS 本地应用数据目录；升级保留；卸载默认保留（卸载向导可清除） |
| 权限范围 | 系统用户 `jiuwenswarm`（`run-as: package`），不加入附加组，不使用 root，不写系统目录 |
| 访问控制 | 仅 NAS 管理员（`allUsers=false` + 网关桥先校验对端进程为 fnOS 网关、再校验 `X-Trim-Isadmin`）；不监听 LAN 端口 |
| 单用户实例 | 所有会话/记忆/技能共用同一数据目录，多管理员之间**不做隔离**；需要隔离请部署独立实例 |
| 执行能力提示 | 智能体可按用户指令读写其工作区内文件、执行命令；这是产品能力，不是越权 |

## 包信息与校验（提交时填写）

| 项 | 值 |
|---|---|
| **唯一产物（应用中心包）** | `jiuwenswarm-0.2.9-12.fpk`（含 `install_dep_apps=python312`；sha256 **待新构建后填写（未经真机验证）**；大小待新构建后填写） |
| 历史产物 sha256（注记） | 旧双包命名、**均已停止构建**，不得冒充新包指纹——测试包 `jiuwenswarm-0.2.9-12.fpk`（旧语义，不含 install_dep_apps）sha256 `9843091c0ed403cd6742261f097a83240cb861f86f0edaabcb7c57284e85f5e8`；上架包 `jiuwenswarm-0.2.9-12-appstore.fpk` sha256 `8794fbe424cf3b765075e27f293d966718ece9b3c6b0dc83c7b87bcb0eef9b30` |
| 签名 | 正式提交需开发者证书签名（`fnpack build`，不带 `--nosign`） |
| 安装方式 | 应用中心 UI 手动安装（CLI `app install-fpk` 被安全闸拦截，历史通道已不可用） |

## A9. 提交渠道与测试材料

| 项 | 内容 |
|---|---|
| 提交渠道 | 开发者后台上线前，经「应用中心开发者先锋交流群」提交（飞牛官网 → 粉丝群 → 开发者群 → 按指引提交）【release §4】 |
| 提交物 | `.fpk` 包 + manifest 元信息 + 图标 + 真实截图 |
| 同版本测试材料 | 本文档 A1–A8 + `docs/ARCHITECTURE.md`（机制与结论强度表）+ `docs/RELEASE-CHECKLIST.md`（43 项门禁）；真机验证的原始记录属项目内部材料，不随仓库发布 |

## A10. 发布前测试清单（release §4 骨架）

结论口径与 `docs/ARCHITECTURE.md §7 结论强度表` 一致：**已验证 / 未验证 / 未取得** 三档，不把行为层写成协议层。

| # | 测试项 | 结果 |
|---|---|---|
| 1 | 应用可安装、可打开、可运行 | **已验证**（命令行安装测试包 → `version=0.2.9-12`、`running`、入口可开）。**上架包经应用中心 UI 安装未验证** |
| 2 | 主要流程可完成（会话/工具调用/产出） | **已验证（行为层）**：会话可建、双向收发成功。`101` 协议层证据未取得（无有效会话时请求停在网关鉴权层） |
| 3 | 数据可正确保存/读取/更新/删除 | **保存/读取已验证**（首启补齐 `config/*`、会话落盘）；**"删除"路径未单独实测**（卸载清除见第 7 行） |
| 4 | 用户无法访问未授权数据或操作（N1/N2） | **部分已验证**：未登录请求被平台拦在网关层；桥的 peer 校验在读取任何请求字节之前完成（代码可核）。**N2（非管理员 + 伪造 `X-Trim-Isadmin`）未执行**——缺非管理员登录态，属未验证项 |
| 5 | 仅暴露必要能力（无 LAN 端口） | **已验证**：`manifest` 无 `service_port`，唯一入口为 UDS `app.sock`；桥的上游全部只监听 `127.0.0.1` |
| 6 | 依赖不可用/配置错误时表现可理解（缺 python312、模型 API 错误） | **缺 `python312` 已验证**（`cmd/main start` 写 `TRIM_TEMP_LOGFILE` 并 `status=3`，不半启动）；模型 API Key 错误的界面表现随上游，未逐项记录 |
| 7 | 升级后数据保留、status 真实 | **未验证（通道不成立）**：本应用不在商店、CLI 拒升级已装应用（`10236`）；且平台"手动安装=重装"会清 `data/`。"卸载清除数据"代码已修（0.2.9-10 起）但**真机未重验** |

## 安装体积与升级峰值

| 项 | 数值 |
|---|---|
| `.fpk` | 历史双包形态约 482.7 MB（460.3 MiB，差 28 B）；唯一产物体积待新构建后复核 |
| 安装后安装卷（target/wheelhouse） | 约 0.5 GB |
| 安装后数据卷（venv + 首启 data） | 约 2 GB |
| 升级瞬间峰值（旧 venv + venv.new + wheelhouse） | 约 3–3.8 GB |

## 版本号对应关系

`manifest.version=0.2.9-12` 是 **fnpack 的 `x.y.z[-r]` 修订号语义**（实测只接受该格式，`-beta.5` 会被拒绝），
对应上游 `pyproject.toml` 的 `0.2.9.beta5`（pip 版本 `0.2.9b5`）。`changelog` 已写明对应上游版本。
修订号语义：`-r` 是**打包修订号**，不绑定上游 beta 号。`0.2.9-5` 首个修订；`-6` 修 CSP 白屏/日志轮转/socket ACL；`-7` 修卸载清数据与升级 wheel 指纹；`-8` 修网关下 WS 握手并换官方图标；`-9` 修多网卡下白名单漏 IP；`-10` 修卸载向导参数形态（清除不生效）；`-11` 网关域名访问 WS；`-12` WS Origin 判定改 Host 优先 + 代理头兜底、多 Host/非法 Host 直接拒、分支标记与日志轮转（当前版本 = 上游 `0.2.9b5` 的第 8 个打包修订）。上游正式版 `0.3.0` 则用 `0.3.0`。

## 提交前需向官方确认（规范未覆盖）

1. `.fpk` 包体上限（本包含离线 wheel 集，体积较大）；
2. 截图的尺寸/数量/格式要求；
3. 应用分类与标签可选项；
4. 是否要求独立隐私说明文档及其格式；
5. 版本号是否允许 `-beta` 后缀对外发布。
