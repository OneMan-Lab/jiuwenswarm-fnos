# 图标变更记录

## 0.2.9-8（2026-11-26）换用官方 SVG 源文件

- 源文件（**已归档**）：`docs/fix-log/assets/logo.svg`（27,521 B，`viewBox="0 0 28 28"`，橙色圆角方形 + 白色网络节点）；
  原始提供位置为 `<HOME>/Desktop/<源文件名>.svg`，两者 sha256 相同，归档副本即权威副本
- 源文件 sha256：`34f3969414e63cbeaf9218d787dde869a8d96ca062d5ace803e30241472bdcb0`

渲染命令（`rsvg-convert`，本机实测）：

```bash
# 在工程根执行；源文件用归档副本，避免依赖工程外路径
rsvg-convert -w 256 -h 256 docs/fix-log/assets/logo.svg -o ICON_256.PNG
rsvg-convert -w 64  -h 64  docs/fix-log/assets/logo.svg -o ICON.PNG
cp ICON_256.PNG app/ui/images/icon_256.png
cp ICON.PNG     app/ui/images/icon_64.png
```

包内共 **4 个**图标文件（两处各两份，尺寸必须一一对应）：

| 文件 | 尺寸 | 格式/模式 | 字节 | sha256 | 四角 alpha |
|---|---|---|---|---|---|
| `ICON.PNG` | 64×64 | PNG / RGBA | 2,258 | `5690b92287e941ef2fb8fcb26b47fc2605a880ecc6e89e952e4a05edd19f44ba` | 0（透明） |
| `ICON_256.PNG` | 256×256 | PNG / RGBA | 9,541 | `2dd4e1c70995ee78c3a8d1770c9fa079ca0dcd02526ca5d6423ccd52304f2003` | 0（透明） |
| `app/ui/images/icon_64.png` | 64×64 | PNG / RGBA | 2,258 | `5690b92287e941ef2fb8fcb26b47fc2605a880ecc6e89e952e4a05edd19f44ba` | 0（透明） |
| `app/ui/images/icon_256.png` | 256×256 | PNG / RGBA | 9,541 | `2dd4e1c70995ee78c3a8d1770c9fa079ca0dcd02526ca5d6423ccd52304f2003` | 0（透明） |

校验要点：
- 尺寸精确 64/256；单文件 < 1024 KB（实际 2.2 KB / 9.5 KB）；
- RGBA，四角 alpha=0（圆角外为透明，无黑底/白底）；
- 未嵌入 ICC profile，按 PNG 默认解释为 sRGB。

### 旧图标（0.2.9-7 及更早，深蓝底自带圆角、实际不透明）

| 文件 | sha256 |
|---|---|
| `ICON.PNG` / `app/ui/images/icon_64.png` | `b6d94c8f5f399e7694882cb5af92082d38094b9b39748cbd277ea3079fd243b8` |
| `ICON_256.PNG` / `app/ui/images/icon_256.png` | `59119d35ca96933678993c324055909d74a53e562b45f56f9b0597ee1e6cf118` |

> 旧图标四角为不透明深蓝（RGB，无 alpha），新图标四角透明，差异可在 256px 下直接观察。

### 关于两档边缘像素统计差异（P2-14 答复）

同一 SVG、同一命令、仅 `-w/-h` 不同。用 alpha>0 统计「首行不透明像素占比」：

| 尺寸 | 首行不透明像素 | 占比 |
|---|---|---|
| 64 | 44 | 0.6875 |
| 128 | 80 | 0.6250 |
| 256 | 152 | 0.5938 |
| 512 | 288 | 0.5625 |

占比随尺寸增大收敛到 0.5625（= 圆角半径 21.875% 的几何值），说明**几何完全一致**，小尺寸占比偏高是抗锯齿把边缘 alpha 抬到 >0 的量化效应（尺寸越小影响越大）。不是两次不同源或不同参数渲染。
