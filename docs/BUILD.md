# 构建链路（BUILD）

> 目标：让**没参与过本项目的人**，在一台干净的 x86_64 Linux 上，从上游源码走到可安装的 `.fpk`。
> 本文只写"怎么做 + 为什么这么做"，不复制脚本全文；脚本本身在 `scripts/` 下，短小可读。
>
> 版本基线：应用包 `0.2.9-12`；上游 JiuwenSwarm `0.2.9b5`（提交 `7b95d38f2ac56acc5efe07e17e371cc3a8804376`）。
> 目标设备：fnOS ≥ `1.1.3100`，x86_64。

---

## 0. 全景（先看这张图，再按顺序执行）

```
上游源码 (gitcode @ 7b95d38f)
        │
        ├─(1) npm 构建前端 ──► channels/web/frontend/dist/
        │
        └─(2) pip wheel ─────► app/wheelhouse/*.whl  (262 个，含 4 个 git 源依赖)
                                   │
                              (3) offlineize-wheelhouse.py  直接 URL 依赖 → 精确版本
                                   │
                              (4) check-wheels.py           架构/ABI 校验 + 生成清单
                                   │
                              (4b) 清单对齐闸门             WHEELS.txt vs wheelhouse-manifest.txt
                                   │                        （CI 强制；本地手工方法见 §5）
                              (5) build-fpk.sh
                                   ├─ CSP 补丁  (patch-app-web-csp.py  + --check)
                                   ├─ logo 补丁 (patch-app-web-logo.py + --check)
                                    ├─ manifest 断言 + 恒等原子替换（Q-01 机制）
                                    ├─ fnpack build --nosign
                                    └─ 新鲜度校验 + install_dep_apps 断言 + verify-fpk.sh
                                    │
                                    ▼
                         jiuwenswarm-0.2.9-12.fpk             (应用中心包，唯一产物)
```

**顺序不能颠倒**：`.fpk` 里的 wheel 是第 2 步的产物，补丁是第 5 步对 wheel 的再加工；
先打包再改 wheel = 打出旧内容（本工程用第 5 步的新鲜度闸门专门防这个）。

---

## 1. 取得上游源码（版本必须钉死）

```bash
git clone https://gitcode.com/openJiuwen/jiuwenswarm.git ../jiuwenswarm
git -C ../jiuwenswarm checkout 7b95d38f2ac56acc5efe07e17e371cc3a8804376
git -C ../jiuwenswarm log -1 --format='%H %ci %s'
# 期望：7b95d38f2ac56acc5efe07e17e371cc3a8804376 ... fix(web): 渠道设置页保存/加载失败反馈可见化...
```

要点：

1. **不要把上游版本变成隐式依赖**。本仓库所有补丁都按上游的**具体行为**定位（`app_web.py` 的 CSP 常量、`dist` 里的 `/logo.svg`），
   上游一改动，补丁就会失败——这是**设计**，不是意外（见 §5 闸门）。因此：
   - 应用包版本 `0.2.9-12` 对应 pip 版本 `0.2.9b5`（`app/server/VERSION`）；
   - 构建脚本、`docs/APPSTORE-MATERIALS.md`、`requirements/wheelhouse-manifest.txt` 三处都写着这个版本；
   - 换上游提交 = 换应用版本号，不要"就地升级"。
2. 目录约定：仓库放在工程**同级**的 `../jiuwenswarm`；也可以用 `JIUWENSWARM_SRC=/abs/path` 覆盖。
3. 源码仓**只读**：构建前后 `git -C ../jiuwenswarm status --porcelain` 必须为空。
   所有补丁都打在 **wheel** 上，不打在上游源码上（原因见 §4）。

构建机要求：**x86_64 Linux + Python 3.12.x + Node.js ≥ 20 + npm + git + 可访问 PyPI 镜像与 gitcode.com**。
`scripts/build-payload.sh` 开头会硬校验架构与 Python 版本，不满足直接退出。

---

## 2. 构造载荷（`scripts/build-payload.sh`）

```bash
bash scripts/build-payload.sh
# 可用环境变量：JIUWENSWARM_SRC / PYTHON / PIP_INDEX
#   默认 PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
```

脚本做四件事（**会先 `rm -rf app/wheelhouse`**，即整目录重建）：

### 2.1 前端构建

```bash
cd "${SRC_DIR}/jiuwenswarm/channels/web/frontend"
npm ci --no-audit --no-fund          # 有 lock 文件则 ci，否则 install
VITE_API_BASE=/app/jiuwenswarm \
VITE_WS_BASE=/app/jiuwenswarm \
  npm run build -- --base=/app/jiuwenswarm/
```

三个参数对应三处前缀：`--base` 管静态资源 URL，`VITE_API_BASE` 管 HTTP 接口前缀，`VITE_WS_BASE` 管 WebSocket 前缀。
**任何一个漏掉**，应用在网关下就会出"页面能开但请求 404 / 聊天断"的现象。

### 2.2 离线 wheel 集（`app/wheelhouse/`）

```bash
python3 -m pip wheel --wheel-dir app/wheelhouse --no-cache-dir \
        --index-url "$PIP_INDEX" "$SRC_DIR"

python3 -m pip download --only-binary=:all: --no-cache-dir \
        --dest app/wheelhouse --index-url "$PIP_INDEX" pip setuptools wheel
```

- 第一条：把 `workswarm`（即上游）及其**全部**依赖构建/下载成 wheel，含 `openjiuwen*`、`agent-gateway` 这类 git 源依赖。
- 第二条：补 `pip / setuptools / wheel`——设备侧 `python312` 可能缺 `ensurepip`，届时用 wheelhouse 里的 `pip` wheel 自举。
- 结果：**262 个 wheel**，约 **468 MB**。这就是 `.fpk` 体积的主要来源。
- `--no-cache-dir` 是刻意的：缓存会让人误判"离线可复现"，实际换机器就失败。

### 2.3 把 4 个 git 源依赖改写为精确版本（`scripts/offlineize-wheelhouse.py`）

这是**整个离线方案能成立的关键一步**。上游 `workswarm` 的 `METADATA` 里有 4 条直接 URL 依赖：

```
Requires-Dist: openjiuwen @ git+https://gitcode.com/openJiuwen/openjiuwen.git@...
Requires-Dist: openjiuwen-computeruse @ git+https://gitcode.com/...
Requires-Dist: openjiuwen-e2a @ git+https://gitcode.com/...
Requires-Dist: agent-gateway @ git+https://gitcode.com/...
```

pip 遇到这种依赖会**强制回源克隆**——即使 wheelhouse 里已经躺着同名 wheel，`--no-index` 也拦不住它。
结果就是"号称离线安装，实际还得联网"。

脚本做的是**元数据级**改写（不动任何 Python 代码）：

```
Requires-Dist: openjiuwen @ git+https://…      →  Requires-Dist: openjiuwen==0.1.21
```

版本号取自 wheelhouse 里**实际构建出来的那个 wheel**（不是猜的），改写后重算 `RECORD` 里的 sha256/size。
本版改写结果（可在清单里核对）：

| 依赖 | 改写后 |
|---|---|
| `openjiuwen` | `==0.1.21` |
| `openjiuwen-computeruse` | `==0.0.1` |
| `openjiuwen-e2a` | `==0.3.0` |
| `agent-gateway` | `==0.0.1` |

> 注意：`openjiuwen-runtime-foundation`、`openjiuwen-security` 是普通 PyPI/index 依赖，不需要改写。
> 若上游新增了 git 源依赖，脚本会打印出来并要求你确认——**不要手动改成 `>=`**，离线安装需要精确版本。

### 2.4 校验架构/ABI 并生成清单（`scripts/check-wheels.py`）

```bash
python3 scripts/check-wheels.py app/wheelhouse
# 期望：wheel 总数 262 ... 架构/ABI 校验通过（x86_64 + cp312 / 纯 py）
```

它同时写出两份清单（不提交，只在本地产物里）：

- `app/wheelhouse/WHEELS.txt`：`wheel<TAB>version<TAB>sha256`
- `app/wheelhouse/SHA256SUMS`：`sha256  wheel名`（供 `sha256sum -c`）

**为什么必须校验**：设备是 x86_64 + CPython 3.12。混进一个 `aarch64` 或 `cp313` 的 wheel，
构建期看不出问题，安装期才炸。脚本对 `aarch64/arm64/armv7l/musllinux/win*/macosx/i686` 以及 `cp3>12` 的标签一律判失败。

### 2.5 清单对齐闸门（CI 强制；本地手工方法见 §5）

载荷构建完成后、打包之前，重建的 `app/wheelhouse/` 必须与 `requirements/wheelhouse-manifest.txt` 清单对齐
（方法与 §5 手工方法逐字一致：清单去注释排序 vs `WHEELS.txt` 去表头排序，`diff -u` 比对，非空即失败）。
GitHub Actions 的 `build-fpk.yml` 把这一步作为强制闸门内置，失败时按两类给出处置指引：

- **文件名/版本差异 = 依赖漂移**：升级 `requirements/wheelhouse-manifest.txt`，并同步执行「换上游提交 = 换应用版本号」纪律（§1）。
- **仅 sha 差异 = 构建环境差异**：按 §5 方法人工复核（先比文件名集合，再比可从索引直接下载项的 sha；本机构建包以版本号为准）。

---

## 3. 打包（`scripts/build-fpk.sh`）

```bash
TMPDIR=$HOME/fnpack-tmp FNPACK=/path/to/fnpack bash scripts/build-fpk.sh
```

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `BUILD_PROFILE` | 仅接受 `appstore`（或不设置，等价）；历史值 `test` 及其他值报错终止 | `appstore` |
| `FNPACK` | fnpack 可执行文件 | 取 `PATH` |
| `SIGN` | `1` = 用已导入的开发者证书签名 | `0`（`--nosign`） |
| `TMPDIR` | 临时目录 | 系统默认（**建议显式指定**，见 §8） |

### 3.1 应用中心档位（唯一档位）

| | 应用中心包（唯一产物） |
|---|---|
| `install_dep_apps` | `python312` |
| 产物名 | `jiuwenswarm-<version>.fpk` |
| 安装通道 | **仅应用中心 UI**（CLI `install-fpk` 有安全闸会拦截带依赖的包） |

决策记录：平台把 `install_dep_apps` 当作"会改动系统依赖"的强操作，命令行 `install-fpk` 有安全闸会拦截带依赖的包；
应用中心 UI 安装依赖是正常流程。历史上（0.2.9-12 及以前）曾因此同时构建"测试包"（暂存期删行，供 CLI 真机验证）与
"上架包"（应用中心通道）两个包；自 0.2.9-12 单包化决策起**取消测试包，仅出应用中心包**——CLI 安装通道随之放弃，
真机验证统一走应用中心 UI 手动安装同一包。理由：唯一包带渠道后缀是冗余信息；双轨档位与双包文档的长期漂移成本高；
CLI 验证场景由 UI 安装同一包覆盖。

实现方式：脚本把工程**硬链接**复制到暂存目录（`cp -al`，避免复制 468 MB），对暂存 `manifest` 先断言上架形态
（`install_dep_apps=python312` 在位，缺失即 fail-fast），再做**内容恒等的原子替换**
——写入走**临时文件 + `os.replace` 原子替换**（替换后暂存 manifest 指向新 inode，硬链接被打断，绝不改工作区；
历史上曾因原地 `write_text` 截断重写硬链接文件而静默删掉工作区 `install_dep_apps` 行，即分析报告 Q-01，已修复），
然后 `cd` 到暂存目录执行 `fnpack build`。

### 3.2 打包时的三道闸门

| 闸门 | 作用 | 失败表现 |
|---|---|---|
| **CSP 补丁** `patch-app-web-csp.py` + `--check` | 把 `frame-ancestors 'none'` 改成 `'self'`；`--check` 断言已生效 | 上游改动导致定位失败 → 构建中止 |
| **logo 补丁** `patch-app-web-logo.py` + `--check` | 把 dist 里根路径 `/logo.svg` 补上网关前缀 | 同上 |
| **新鲜度** `verify-package-freshness.py` | 包内关键脚本与工作区**逐字节**比对 | 不一致 → 拒绝交付 |

外加 **install_dep_apps 断言**：包内 `manifest` 必须是 `install_dep_apps=python312`（上架形态）——直接读产物里的 `manifest` 校验。

> 这三道闸门都来自真实事故：曾出现"代码 17:24 改好、包 17:06 就打完了"，设备上跑旧文件，整轮排查方向全错。
> 逻辑 review 抓不到这类问题，只有 sha 比对能抓。

### 3.3 `fnpack` 的两个坑

1. **`fnpack build` 把 `.fpk` 写到当前工作目录**，与 `-d` 参数无关 ⇒ 脚本在暂存目录里 `cd` 后执行。
2. **`fnpack` 会重排 manifest 键值并追加 `checksum`** ⇒ 比较暂存 manifest 与包内 manifest 时，要按"键=值"归一化，
   并剔除 `checksum`，否则永远不等。

安装 fnpack：

```bash
curl -fL https://static2.fnnas.com/fnpack/fnpack-1.3.3-linux-amd64 -o /usr/local/bin/fnpack
chmod +x /usr/local/bin/fnpack && fnpack --version    # 期望 1.3.3
```

---

## 4. 为什么补丁打在 wheel 上，而不是改上游源码

两个理由，都是硬约束：

1. **上游仓只读**：构建前后 `git status --porcelain` 必须为空，否则"我到底改了什么"就说不清，也无法快速跟随上游更新。
2. **改源码会被 pip 缓存/版本号骗过**：`workswarm` 的 pip 版本是 `0.2.9b5`，改了源码但不改版本号，安装侧的任何
   "版本相同就跳过"逻辑都会继续用旧内容（本工程因此引入了 wheel sha 指纹，见 §6）。

补丁脚本的共同要求（写新补丁时必须遵守）：

- **定点字符串替换**，不做正则模糊匹配；匹配不到就 `exit 1`；
- 改完**重算 zip 内 `RECORD`**（sha256 + size），否则 pip 安装会 hash 不匹配；
- 提供 `--check`（只读校验），供 CI 与构建脚本断言；
- 幂等：已经是目标状态时直接返回 0。

---

## 5. 用清单校验 wheelhouse（不靠感觉）

仓库里**不存 wheel 二进制**，只存 `requirements/wheelhouse-manifest.txt`（262 行：文件名 / 版本 / sha256）。

```bash
# 1) 重建后，把生成的清单与本仓库清单对齐比较
bash scripts/build-payload.sh && python3 scripts/check-wheels.py app/wheelhouse
grep -v '^#' requirements/wheelhouse-manifest.txt | sort > /tmp/expected.tsv
sed '1d' app/wheelhouse/WHEELS.txt | sort > /tmp/actual.tsv
diff -u /tmp/expected.tsv /tmp/actual.tsv   # 无输出 = 一致

# 2) 任一 wheel 字节级校验（本地产物）
cd app/wheelhouse && sha256sum -c SHA256SUMS
```

> **为什么 sha 可能不同**：PyPI 上的 wheel 是发行方构建的，sha 应当稳定；但 `workswarm` / `openjiuwen*` /
> `agent-gateway` / `jieba` 是**本机 pip wheel 构建**的，zip 内时间戳不同会导致 sha 不同。
> 判断"是否同一套依赖"时，先比**文件名集合**，再比**可从索引直接下载的那些**的 sha；
> 本地构建的 5–6 个包以 `pip freeze` 式版本号为准。

---

## 6. 运行期与 wheel 指纹（构建相关，务必理解）

`app/server/runtime.sh` 在**设备侧**创建 venv，并把 wheel 的 sha256 记进 `$TRIM_PKGVAR/venv/.workswarm-wheel.sha256`。

- 判定条件是 **版本 + 指纹双一致**才跳过重建；
- 任一不一致 ⇒ 重建，并打印原因（`版本变化` / `wheel sha 变化`）；
- `cmd/main` 每次启动也再比一次（覆盖"安装后没启动、手工换 wheel"这类场景）。

**为什么需要**：本项目对 wheel 打了 CSP / logo 补丁，但**上游 pip 版本没变**。
只比版本号 ⇒ 升级用户继续跑旧 wheel ⇒ 修复对他完全不生效（新装用户却正常，问题看起来像"偶发"）。

---

## 7. 离机 / 无网构建

1. 在联网构建机跑完 `scripts/build-payload.sh`；
2. 把 **`app/wheelhouse/` 整目录** + 本仓库（或至少 `workswarm-*.whl`）带到离线机器；
3. 离线机器只需 **x86_64 + Python 3.12**，先验证 wheel 集自洽：

```bash
python3 -m venv /tmp/verify-venv
/tmp/verify-venv/bin/pip install --no-index --find-links app/wheelhouse workswarm==0.2.9b5
/tmp/verify-venv/bin/python -c "import jiuwenswarm; print(jiuwenswarm.__file__)"
```

4. 再用 fnpack 打包（fnpack 是静态单文件，不依赖网络）：`FNPACK=/path/to/fnpack bash scripts/build-fpk.sh`。

> 校验点：`pip install` 阶段**不应出现任何网络请求**。若出现 `Cloning git+https://…`，说明 §2.3 的改写没生效。

---

## 8. 常见错误与处理

| 报错 / 现象 | 原因 | 处理 |
|---|---|---|
| `ERROR: app/wheelhouse 为空。请先执行 bash scripts/build-payload.sh` | 没跑载荷步骤，或 `wheelhouse` 被清 | 跑 §2 |
| `ERROR: CSP 补丁失败（上游 app_web.py 可能已改动）` | 上游把 `frame-ancestors 'none'` 那行改了 | 读补丁脚本报错，按新代码更新 `TARGET/OLD/NEW`；**不要**跳过闸门 |
| `ERROR: 包内文件与工作区不一致，拒绝交付` | 打包后又改了代码 | 重新构建（这正是闸门存在的意义） |
| `ERROR: 包内 manifest 缺少 install_dep_apps=python312` | 暂存/工作区 manifest 缺 `install_dep_apps=python312` | 核对工作区 `manifest` 是否被改动（应含 `install_dep_apps=python312`），修正后重跑 |
| `ERROR: 仅支持应用中心档位，test 档位已移除…` | 按旧习惯传了 `BUILD_PROFILE=test` 等历史值 | 去掉该环境变量直接跑，或显式 `BUILD_PROFILE=appstore` |
| `No space left on device` | `/tmp` 太小（暂存目录 + fnpack 临时文件） | `TMPDIR=$HOME/fnpack-tmp`，确保 ≥10 GB |
| `.fpk` 落在奇怪目录 | `fnpack build` 写到 cwd | 用 `scripts/build-fpk.sh`（已在暂存目录内 cd） |
| 构建机 Python 不是 3.12 | wheel 标签变 `cp313` 等 | 用 3.12 的解释器（`PYTHON=python3.12`） |
| `架构/ABI 校验` 失败 | 混入 arm64 / musllinux / cp313 | 检查镜像源是否返回了错误平台的 wheel |

---

## 9. 可复现性说明（诚实版）

- **同一个上游提交 + 同一构建机**：可以稳定产出功能一致的包；但**不保证字节级一致**（zip 时间戳、fnpack 追加的 `checksum`）。
- **跨构建机**：`workswarm`、`openjiuwen*`、`agent-gateway`、`jieba` 是本机构建的 wheel，sha 会不同；
  其余从索引下载的 wheel sha 应当一致（可用 §5 的 diff 判定）。
- **判断"是否同一份产物"**：优先看 `manifest.version` + `app/server/*` 的 sha（`verify-package-freshness.py` 的比对口径），
  而不是看 `.fpk` 的整体 sha。
- 本仓库的 `.fpk` **不入库**，需要时现场构建或从 Release 下载。

---

## 10. 构建后的验收（不装设备也能做一半）

```bash
# 1) 结构自检（脚本内已自动调用，也可单独跑）
bash scripts/verify-fpk.sh jiuwenswarm-0.2.9-12.fpk
# 期望：manifest / config/privilege / config/resource / cmd/main / ICON*.PNG / app.tgz 全部 OK；
#       manifest 不含 service_port；app/ui/config 含 gatewayPrefix 与 gatewaySocket

# 2) 新鲜度（包内 == 工作区）
python3 scripts/verify-package-freshness.py jiuwenswarm-0.2.9-12.fpk .

# 3) 记录指纹（唯一产物；同一批命令内取，避免大小与 sha 来自不同次构建）
ls -l jiuwenswarm-0.2.9-12.fpk
sha256sum jiuwenswarm-0.2.9-12.fpk

# 4) 发布前敏感信息门禁（0 未解释命中才可推送）
python3 -B scripts/sensitive-scan.py --strict .
# 期望：结论 PASS（未解释命中 0 条），退出码 0
# 注意扫描范围：只扫文本文件，按后缀跳过二进制（.png/.whl/.fpk/.zip/.pdf 等）。
#   仓库共 120 个文件，其中 4 个是 PNG 图标（ICON.PNG / ICON_256.PNG / app/ui/images/*.png），
#   故 --strict 报出 "扫描文件数: 116" 属正常；不要把 116≠120 当成漏扫。
#   用 -B（或 PYTHONDONTWRITEBYTECODE=1）：避免"以模块方式导入"时 SourceFileLoader
#   把 __pycache__ 写进被检查目录——门禁工具污染被检查对象是比漏扫更难查的一类问题。

# 4b) PNG 不被正则扫描覆盖，但元数据块可能带软件名/机型/原始路径 —— 构建期抽查一次
for f in ICON.PNG ICON_256.PNG app/ui/images/*.png; do
  printf '%s: ' "$f"
  grep -aoE 'tEXt|iTXt|zTXt|eXIf|tIME' "$f" | sort -u | tr '\n' ' '; echo
done
# 期望：每行只输出文件名 + 空（无任何块名）。若出现块名，先剥元数据（optipng -strip all / svgo）再入库。

# 4c) 目录纯净度（四类；命中即失败，不能靠 .gitignore 兜底）
find . -mindepth 1 -path ./.git -prune -o \( -name '*[{},]*' -o -name '* *' \) -print
find . -mindepth 1 -path ./.git -prune -o \( -name '.*' ! -name '.gitignore' -o -name '*.bak' \
     -o -name '*.orig' -o -name '*~' -o -name '*.tmp' -o -name '*.log' -o -name 'redact*' \) -print
find . -mindepth 1 -path ./.git -prune -o \( -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' \) -print
find . -mindepth 1 -path ./.git -prune -o -type f -size +1M -print
# 期望：四条全部空输出。

# 5) 想看清每条命中被判为"可接受"的依据（不阻断）
python3 scripts/sensitive-scan.py --loose .
```

> **扫描器冻结（对外契约，改前必读）**
>
> | 项 | 值 |
> |---|---|
> | 文件 | `scripts/sensitive-scan.py` |
> | 大小 / mtime | **19,987 B** / **2026-11-26 22:31:14** |
> | sha256 | `d0ccf62b388086acf1e998c05a5208081e4ce913c683620e4fb8ea6fc9fd4f4c` |
> | 冻结时间 | **2026-11-26 22:34**（发布基线；取代 22:29 的 `f1ea0189…`） |
>
> **本轮变更（只增不减）**：C4 补漏 `XXX_UID=` 前缀赋值与 `/vol<n>/<uid>` 目录形态两类召回；
> 同时**收回两条超出审计授权的白名单**（`single-letter-host`、`std-volume`）——它们原本放过了
> "单字母主机名"与"写死的卷名（`<VOL>`）"，属越界放行。净效果是判据更严：旧版对这两类写法是"绿"，
> 新版能抓出真实越界（覆盖只增不减、白名单只减不增）。
>
> 为什么写在这里：本文件是外部贡献者唯一会读的操作文档。若冻结版本只记在团队私有文档里，
> 外部人改了这个脚本再跑门禁，**得到的 PASS 没人能判断是否可信**。
>
> 如果你确实要改它，PASS 不能直接等同于本项目的结论，必须同时做到四件事：
> 1. 跑 `python3 -B scripts/sensitive-scan.py --self-test`（扫描器自身不得含真实值）；
> 2. 重跑全量 `--strict` 并记录扫描文件数与各类命中；
> 3. 在 PR 里说明**改了什么、是"只增不减"（提高覆盖）还是放宽了判据**；
> 4. 更新本段的 sha256 与冻结时间。
>
> 判断"是否等价或更强"的口径：逐条对照 `docs/RELEASE-CHECKLIST.md` 与审计规则里的 C1–C7 七类
> （内网 IPv4 / 其它 IPv4 / 域名主机名 / 用户与 uid 实值 / 设备指纹 / 凭据 / 主机:端口），
> 要求**每类检测能力等价或更强、白名单不比原授权范围更宽**。任何一类变弱都应视为阻断。

> `.gitignore` **只能防提交，不能防污染**：`.git` 只决定"哪些文件进历史"，不改变工作目录里已有的文件。
> 所以"目录是否纯净"必须由上面 4c 的 `find` 判定（可失败），不能写成"反正 .gitignore 里有 `__pycache__/`"。

真机验收（安装 / 启动 / 入口 / WS / 卸载）见 `docs/RELEASE-CHECKLIST.md` 与 `README.md` §2 的状态表。
