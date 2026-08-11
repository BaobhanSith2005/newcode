"""视觉模型 Prompt。

设计原则（改 Prompt 前务必先读）：
1. **不问图像坐标，只问俯视平面布局。** 图像坐标 → 平面坐标需要相机位姿与深度，
   那是真实三维重建的活儿，本项目不做。而 VLM 见过海量户型图，具备俯视布局的常识推理能力。
2. **家具尺寸不问米数（查表决定）。** 单件家具的真实尺寸由服务端先验表给出，问了只会得到幻觉数值。
   但**房间整体尺度例外**：这是用户目标"大致判断房间大小"所需，允许模型基于可见参照物（门高≈2.0m、
   人高≈1.7m、床≈1.5~2.0m）做粗略估算，宁粗勿假，无法判断可填 null。
3. **强制受控词表。** 开放式输出会产出上百种同义品类，无法映射到模型库。
4. **靠墙关系比坐标更可靠。** 离散拓扑判断的准确率远高于连续数值回归，
   服务端用它做吸附矫正。

修改本文件时必须同步升级 PROMPT_VERSION，否则会命中旧缓存。
"""

from __future__ import annotations

from .catalog import ALLOWED_CATEGORIES

PROMPT_VERSION = "p3"

ROOM_TYPES = [
    "living_room", "bedroom", "dining_room", "study",
    "kitchen", "bathroom", "balcony", "office", "unknown",
]

SYSTEM_PROMPT = """你是一名室内空间分析专家，专长是把室内照片转换为俯视平面布局数据。
你只输出 JSON，不输出任何解释、注释或 Markdown 代码块标记。"""


def build_user_prompt() -> str:
    return f"""分析这张室内照片，输出该房间的**俯视平面布局**。

## 坐标系定义（重要）

想象你站在房间正上方向下俯视，把房间简化为一个矩形：

- `u`：从**西墙**(0.0) 到 **东墙**(1.0) 的归一化位置
- `v`：从**北墙**(0.0) 到 **南墙**(1.0) 的归一化位置

请以拍摄者背后为南墙（south）来建立方位，即：照片正对的那面墙记为 **north**，
照片左侧的墙为 **west**，右侧的墙为 **east**。

注意：`u`/`v` 是**平面图坐标**，不是物体在照片画面中的像素位置。
例如照片里靠着正对墙面的沙发，其 v 应接近 0.1，而不是它在画面中的高度。

## 输出要求

1. `room_type` 从以下取值：{", ".join(ROOM_TYPES)}
2. 每件家具的 `category` **必须**取自下列受控词表，不得自创：
{", ".join(ALLOWED_CATEGORIES)}
3. `size_class` 只能是 S / M / L（相对该品类的常规尺寸）。**不要输出具体米数。**
4. `against_wall` 取值：north / south / east / west / center（不靠墙的填 center）
5. `rotation_hint` 表示家具正面朝向：north / south / east / west
   （靠墙家具的正面应朝向房间内部）
6. `bbox` 为该物体在照片中的大致像素包围盒 `[x1, y1, x2, y2]`，必须基于原图坐标给出，
   用于后续 OpenCV 提取真实颜色。如果某物体在画面中非常分散或难以框定，可填 `[0, 0, 0, 0]`。
7. 只输出**可见且确定**的家具，宁少勿多。不要输出墙壁、地板、天花板本身。
8. `confidence` 为 0~1 的识别置信度。

## 房间整体尺度估算（这是「判断房间大小」所需，允许粗略）

基于照片中可见的参照物推算（门高≈2.0m、成年人高≈1.7m、单人床≈1.0m 宽 / 双人床≈1.5m 宽、
标准书桌≈1.2m 宽）。坐标系：东西向（西墙↔东墙）= 宽度，南北向（北墙↔南墙）= 深度。

- `width_m`：房间东西向净宽（米）
- `depth_m`：房间南北向净深（米）
- `height_m`：层高（米，通常 2.6~3.0）

若照片角度无法可靠判断某一项，该项填 `null`，**不要编造精确值**。

## 输出格式（严格 JSON，不要加代码块）

{{
  "room_type": "living_room",
  "style": "modern",
  "dominant_colors": ["#e8e2d8", "#8d9aaf"],
  "room": {{ "width_m": 4.5, "depth_m": 3.8, "height_m": 2.8 }},
  "objects": [
    {{
      "category": "sofa",
      "label": "三人布艺沙发",
      "floor_uv": [0.30, 0.14],
      "against_wall": "north",
      "rotation_hint": "south",
      "size_class": "L",
      "bbox": [120, 200, 520, 420],
      "confidence": 0.9
    }}
  ],
  "openings": [
    {{ "type": "window", "wall": "east", "offset": 0.5, "size_class": "M" }}
  ],
  "notes": "采光良好的现代客厅"
}}"""


# 第四阶段：自然语言改布局（"把沙发移到窗户旁边"）
EDIT_SYSTEM_PROMPT = """你是室内布局编辑助手。用户会给你一份 scene.json 和一句修改指令。
你只输出一个 JSON 补丁数组，描述需要对哪些物体做什么修改，不输出解释。

补丁格式：
[
  {"op": "move",   "id": "obj_1", "floor_uv": [0.7, 0.2]},
  {"op": "rotate", "id": "obj_1", "rotation_y": 90},
  {"op": "remove", "id": "obj_3"},
  {"op": "add",    "category": "plant", "floor_uv": [0.9, 0.9], "size_class": "M"}
]

只允许 move / rotate / remove / add 四种操作。坐标沿用 u(西→东) / v(北→南) 归一化平面坐标。"""
