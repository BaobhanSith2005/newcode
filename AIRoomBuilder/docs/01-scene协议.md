# scene.json 协议规范 v1

> 这是 AI 侧与渲染侧之间**唯一**的数据契约。任何一端的改动都必须先改这份文档和 `scene.schema.json`。

---

## 1. 坐标系约定（必读，歧义会导致全盘错乱）

采用 Three.js 原生约定：**右手系，Y 轴向上，单位为米**。

```
        Y (上)
        │
        │
        └──────── X (右 / 东)
       ╱
      ╱
     Z (前 / 南，指向屏幕外)
```

- **原点**：房间**地面中心**。不是墙角。
- **房间尺寸**：`width` 沿 X，`depth` 沿 Z，`height` 沿 Y。
- **四面墙**：

  | 墙 | 平面位置 | 房间内侧方向 |
  | --- | --- | --- |
  | `north` | `z = -depth/2` | +Z |
  | `south` | `z = +depth/2` | -Z |
  | `west`  | `x = -width/2` | +X |
  | `east`  | `x = +width/2` | -X |

- **物体 position**：`[x, y, z]`，取物体**包围盒底面中心**。落地家具 `y = 0`；挂墙物（空调、壁灯、电视）`y` 为离地挂高。
- **物体 rotation**：只用 `rotation_y`（绕 Y 轴偏航角，单位**度**，逆时针为正）。
  `0` 表示物体正面朝向 **+Z**。因此靠北墙的家具应为 `0`，靠南墙为 `180`，靠西墙为 `90`，靠东墙为 `270`。

> ⚠️ 不使用四元数、不使用弧度、不允许 X/Z 轴旋转。家具只在地面上转圈，多余的自由度只会带来 bug。

---

## 2. 归一化俯视坐标 `floor_uv`

VLM **只输出** `floor_uv`，不输出米制坐标。

- `u ∈ [0,1]`：沿房间宽度，`0` = 西墙，`1` = 东墙
- `v ∈ [0,1]`：沿房间进深，`0` = 北墙，`1` = 南墙

转换公式（服务端执行）：

```python
x = (u - 0.5) * width
z = (v - 0.5) * depth
```

这样做的好处：VLM 不需要知道房间的真实尺寸，房间尺寸后期由用户调整时，布局能整体等比缩放而不失效。

---

## 3. 完整结构

```jsonc
{
  "schema_version": "1.0",
  "scene_id": "sc_7f3a91",
  "room": {
    "type": "living_room",
    "width": 5.0,
    "depth": 4.0,
    "height": 2.8,
    "floor": { "material": "wood_oak", "color": "#c8a97e" },
    "wall":  { "material": "paint",    "color": "#f2efe9" },
    "ceiling": { "color": "#ffffff" }
  },

  "openings": [
    {
      "id": "op_1",
      "type": "window",          // window | door
      "wall": "north",
      "offset": 0.5,             // 沿该墙的归一化位置 0~1（从西/北端起算）
      "width": 1.6,
      "height": 1.4,
      "sill": 0.9                // 窗台离地高度；门为 0
    }
  ],

  "objects": [
    {
      "id": "obj_1",
      "category": "sofa",        // 必须是受控词表中的值，见第 4 节
      "label": "三人布艺沙发",     // 展示用，可自由填写
      "asset": {
        "kind": "gltf",          // gltf | primitive
        "url": "/models/sofa.glb",
        "fallback": "box"        // 加载失败时的降级几何体
      },
      "size": { "w": 2.0, "d": 0.9, "h": 0.8 },   // 米，由尺寸先验表决定
      "position": [-0.6, 0, -1.55],
      "rotation_y": 0,
      "against_wall": "north",
      "color": "#8d9aaf",
      "confidence": 0.82,        // VLM 识别置信度，前端可用于弱化显示
      "source": "vlm"            // vlm | user | solver
    }
  ],

  "lighting": {
    "preset": "daylight",        // daylight | evening | neutral
    "ambient_intensity": 0.6,
    "main_intensity": 1.2
  },

  "meta": {
    "generated_at": "2026-08-10T16:20:00Z",
    "model": "qwen-vl-max",
    "prompt_version": "p1",
    "warnings": ["obj_3 缺少对应 glb，已降级为 primitive"]
  }
}
```

---

## 4. 受控品类词表

VLM 只允许输出下列 `category`，其他一律映射到 `unknown` 并降级渲染。**受控词表是防止 AI 自由发挥的关键约束**。

```
sofa, armchair, coffee_table, tv_stand, tv, bookshelf, rug,
bed, nightstand, wardrobe, dresser,
dining_table, dining_chair, cabinet,
desk, office_chair,
plant, floor_lamp, ceiling_lamp, curtain, air_conditioner,
fridge, kitchen_counter, toilet, sink, bathtub,
unknown
```

新增品类必须同步三处：本词表、`catalog.py` 尺寸先验、模型库 glb 文件。

---

## 5. 版本策略

- `schema_version` 遵循 `主版本.次版本`
- **次版本**：只允许新增可选字段，渲染端必须容忍未知字段
- **主版本**：字段删除或语义变更，渲染端必须显式拒绝不支持的主版本并提示

校验文件：`docs/scene.schema.json`（JSON Schema Draft 2020-12），前后端共用。
