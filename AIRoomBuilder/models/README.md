# 家具模型库

把 `.glb` 文件直接放在本目录，后端会自动检测：存在则在 scene.json 中标记为 `gltf`，
不存在则降级为参数化几何体。**无需修改任何代码。**

> **当前状态（2026-08-10）**：26 个品类已全部用 `tools/gen_models.py` 离线生成了
> **风格化程序化模型**（多部件 + PBR 材质：木/布/金属/陶瓷），可直接看到效果。
> 这些不是写实模型；若要更真实，按下方「模型来源」替换为 Kenney / Quaternius 等 CC0 写实 `.glb`，
> **保持文件名不变即可热替换**，无需改代码。
> 注：`.glb` 已被 `.gitignore` 忽略，本地能跑但不会进版本库（协作需 Git LFS 或模型 CDN）。

## 文件命名

必须与 `backend/app/services/catalog.py` 中各品类的 `asset` 字段一致：

```
sofa.glb           armchair.glb       coffee_table.glb   tv_stand.glb
tv.glb             bookshelf.glb      rug.glb            bed.glb
nightstand.glb     wardrobe.glb       dresser.glb        dining_table.glb
dining_chair.glb   cabinet.glb        desk.glb           office_chair.glb
plant.glb          floor_lamp.glb     ceiling_lamp.glb   curtain.glb
ac.glb             fridge.glb         counter.glb        toilet.glb
sink.glb           bathtub.glb
```

## 优先补齐的 12 个品类

覆盖约 80% 的常见场景，先做这些：

`sofa` · `coffee_table` · `tv_stand` · `bed` · `nightstand` · `wardrobe` ·
`dining_table` · `dining_chair` · `desk` · `office_chair` · `bookshelf` · `plant`

## 模型来源（均可商用）

| 来源 | 许可 | 特点 |
| --- | --- | --- |
| [Kenney Furniture Kit](https://kenney.nl/assets) | CC0 | 风格统一、体积小，**最推荐用于 Demo** |
| [Poly Haven](https://polyhaven.com/models) | CC0 | 写实质量高，文件偏大 |
| [Sketchfab](https://sketchfab.com/search?licenses=322a749bcfa841b29dff1e8a1bb74b0b) | 筛 CC0 | 品类全，风格需自行统一 |
| [Quaternius](https://quaternius.com/) | CC0 | 低多边形，适合轻量场景 |

> ⚠️ **风格统一比单件精度更重要。** 混搭不同来源的模型会让整个场景显得廉价，
> 宁可全用一套低模，也不要写实模型和卡通模型混放。

## 尺寸与朝向要求

渲染器会自动把模型缩放到 `scene.json` 声明的尺寸，并把原点对齐到底面中心，
所以**不需要**你手动调整比例。但有两点必须自己保证：

1. **正面朝向 +Z。** 模型导出时正面要对着 +Z 轴，否则沙发会背对着房间。
2. **无多余变换。** 导出前在建模软件里 Apply 所有变换，避免 bbox 计算出错。

## 压缩

单个文件建议控制在 2MB 以内：

```bash
npx @gltf-transform/cli optimize input.glb output.glb --compress draco --texture-size 1024
```
