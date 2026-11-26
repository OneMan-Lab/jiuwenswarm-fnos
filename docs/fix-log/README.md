# 修复归档（fix-log）

目的：让每一版的鉴权/网关实现可追溯。工程不是 git 仓库、`.fpk` 会被新版覆盖，
因此**每次出包都把关键脚本按版本快照留在这里**，供审核与后续回归对照。

## 版本 ↔ 文件 ↔ sha256

| 版本 | 文件 | sha256 | 说明 |
|---|---|---|---|
| 0.2.9-5（P0 修复前） | `uds_gateway-0.2.9-5-pre-p0-fix.py` | `4e2bb255113b5991e5ceb2ca21df307b8503849e0508765a6d91c42d9bd298a4` | 首包 `461d91d4…` 内的版本。P0-01（basename 白名单可绕过）、P0-02（跨用户读 exe EACCES 未处理）都存在。**QA 复现「本地 /tmp/nginx 返回 200」用的就是这段代码**，自本文件归档起该对照链可核验。 |
| 0.2.9-5（P0 修复后） | `uds_gateway-0.2.9-5.py` | `5857a1d6ddf8bf6b71a13be60af236fc1d101f922d76303f2c1950bc56fdf6c0` | P0-01/P0-02/P1-01 修复版；socket `chown`+0660 方案（真机 EPERM，见 0.2.9-6）。 |
| 0.2.9-6 | `uds_gateway-0.2.9-6.py`、`0.2.9-6/` | `361eec7fb2211763cf98efbaf1017eaebdc4f02f3d59950771eba6f87267a567` | socket 收紧改为 `setfacl`（多组、失败一律回退 0666，绝不 0660）；与 CSP 修复、日志轮转同版。 |
| 0.2.9-7 | `uds_gateway-0.2.9-7.py`、`0.2.9-7/` | `361eec7fb2211763cf98efbaf1017eaebdc4f02f3d59950771eba6f87267a567`（`_main` 之外与上版相同） | v4：重写 `cmd/uninstall_callback`（不再 source target、删除三重校验、失败 exit 1）；`runtime.sh`/`cmd/main` 增加 wheel sha256 指纹判定，升级时内容变化即重建 venv。网关桥本身未改。 |
| 0.2.9-8 | `uds_gateway-0.2.9-8.py`、`0.2.9-8/` | `361eec7f…`（网关桥未改） | v5：修 WS Origin 白名单（`supervisor.py` 启动时把本机 IP/主机名并入 `config/.env` 的 `JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS`）；`init_env.sh` 增加 `JW_WS_ALLOWED_ORIGIN_HOSTS` 自定义键；图标换官方 SVG。详见 `ICONS.md` 与 DELIVERY-NOTES §3.16。 |
| 0.2.9-9 | `supervisor.py`、`patch-app-web-logo.py`、`0.2.9-9/` | `supervisor.py` `f0feefdc…` | v6：WS 白名单改为枚举所有网卡 IPv4（`ioctl(SIOCGIFADDR)` + `ip -4` 双路径），修多网卡设备漏 IP 导致的仍 403；新增 wheel 层前端补丁把 `"/logo.svg"` 改写为 `/app/jiuwenswarm/logo.svg`，修网关下品牌图 404。详见 DELIVERY-NOTES §3.17/§3.18。 |
| 0.2.9-10 | `uninstall_callback`、`0.2.9-10/` | `uninstall_callback` `d168618d…` | v7：修 P0-03「清除全部应用数据」不生效——`wizard_delete_data` 归一化（`true/True/1/yes/on`）并打印原值；删除 fail-open、`app.env` 隐私优先、恒 `exit 0`、残留清单入日志；`APP_HOME` 按 basename 判定并支持父目录回退。详见 DELIVERY-NOTES §9.11。 |
| 0.2.9-11 | `uds_gateway.py`、`0.2.9-11/` | `uds_gateway.py` `caea731a…`（31,594 B） | v8：WS Origin 改桥内同源判定（Host + X-Forwarded-Host/X-Original-Host/X-Forwarded-Server 多源），通过后 Origin 归一化为 `http://127.0.0.1`；判不出基准时回退放行；判决写 `ws-origin.log` 与 403 响应体。详见 DELIVERY-NOTES §9.12。 |
| 0.2.9-12 | `uds_gateway.py`、`uninstall_callback`、`0.2.9-12/` | `uds_gateway.py` `199a8e48…`（34,156 B）、`uninstall_callback` `b4d94323…`（7,973 B）、`supervisor.py` `a6ae902e…`（12,943 B） | v9（qa 必修 M1/M2/M3/R4）：Host 优先、多 Host 拒、解析失败拒（含 `@`）、fallback WARN+计数；新增分支标记文件；日志轮转保留最近 200 行；卸载候选路径二次校验。详见 DELIVERY-NOTES §9.12/§9.11。 |

`0.2.9-6/` 同时保存了本版的 `init_env.sh`、`supervisor.py`、`install_callback`、`cmd/main` 快照，
用于复现该包行为：

| 文件 | sha256 |
|---|---|
| `init_env.sh` | `dabfdb743183b242ed3879b8a161185a2fb2ea0f2fd6e4ff424f0fd87d3665f9` |
| `install_callback` | `7b12949e7e6277c73720bd248ec76c09cca096d65462a6878d7778947afeb793` |
| `main` | `7c90da86dc9a91418403305d3b2bc66252ab0bc5cc16240630ab10d3fa25725a` |
| `supervisor.py` | `39b47d15d7ee13da7780096fb349649764b40e6c31d06aa9f27fc8de128ed668` |

## 0.2.9-6 的关键差异（对照 0.2.9-5）

1. **CSP**：`app_web.py` 的 `_TOP_LEVEL_DOCUMENT_CSP` 由 `frame-ancestors 'none'` 改为 `'self'`。
   上游源码仓只读，改动通过 `scripts/patch-app-web-csp.py` 在 wheel 层完成（重算 RECORD）。
   该策略只有 `frame-ancestors`，**没有** `connect-src` / `script-src` / `img-src`，
   所以 WebSocket 与静态资源不受 CSP 限制（不是 WS 不通的原因）。
2. **日志轮转**：`supervisor.py` 增加 `launcher.log` 20 MB × 1 份轮转；**truncate 不 rename**
   （子进程继承 append fd，rename 会让它继续写旧 inode）。
3. **socket 权限**：`0600 + setfacl -m g:<gid>:rw`（支持多组），全部成功才 `0660`；
   `setfacl` 缺失/失败 → **强制回 0666 + WARN**，绝不 `0660`。
4. **`app.env` 属主**：`install_callback` 以 root 执行时 `chown TRIM_UID:TRIM_GID`；
   解析器把属主校验放宽为「root 或当前用户」，并输出正向加载日志。

## 0.2.9-7 快照 sha256

| 文件 | sha256 |
|---|---|
| `init_env.sh` | `dabfdb743183b242ed3879b8a161185a2fb2ea0f2fd6e4ff424f0fd87d3665f9` |
| `runtime.sh` | `1919c57dfef1d749d0cbc0e82c33e0e6e03f41f6d1046c4bd741c6689545a1e8` |
| `supervisor.py` | `39b47d15d7ee13da7780096fb349649764b40e6c31d06aa9f27fc8de128ed668` |
| `uds_gateway.py` | `361eec7fb2211763cf98efbaf1017eaebdc4f02f3d59950771eba6f87267a567` |
| `install_callback` | `8db2977c048bab48d927ecc056c23919b96638174fb5f4528193ba7282bfe6db` |
| `upgrade_callback` | `8f8c817f97ee4a77d4afc85bc2f04c21e3a0100d191572d21b6ea3fc1a9b1ace` |
| `uninstall_callback` | `9abc1608770f3770a3fbf5feec74cad549c7821e99d4380f08f898a0c0ed53d0` |
| `main` | `00149d99aa8b9116e4e9003adee0853bb7273cfd2f148e8fd9a1cc91bb969e36` |

## 0.2.9-8 快照 sha256

| 文件 | sha256 |
|---|---|
| `init_env.sh` | `f10cffda8cbb8da689c1bc990adac920d53bd99e61c10784770ce64a51a89c31` |
| `runtime.sh` | `1919c57dfef1d749d0cbc0e82c33e0e6e03f41f6d1046c4bd741c6689545a1e8` |
| `supervisor.py` | `bcc0181b352bd54f6999d5faffc79996d48c321a0a788cf565cf3913792531da` |
| `uds_gateway.py` | `361eec7fb2211763cf98efbaf1017eaebdc4f02f3d59950771eba6f87267a567` |
| `install_callback` | `8db2977c048bab48d927ecc056c23919b96638174fb5f4528193ba7282bfe6db` |
| `upgrade_callback` | `8f8c817f97ee4a77d4afc85bc2f04c21e3a0100d191572d21b6ea3fc1a9b1ace` |
| `uninstall_callback` | `9abc1608770f3770a3fbf5feec74cad549c7821e99d4380f08f898a0c0ed53d0` |
| `main` | `00149d99aa8b9116e4e9003adee0853bb7273cfd2f148e8fd9a1cc91bb969e36` |

## 0.2.9-9 快照

- `supervisor.py`：f0feefdc…（多网卡 IPv4 枚举）
- `patch-app-web-logo.py`：ecaa6fa8…（dist 根路径 logo 改写，构建闸门）

## 0.2.9-10 快照

- `uninstall_callback`：`d168618d…`（7,015 B，向导值归一化 + fail-open + home 父目录回退）
