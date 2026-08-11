"""家具尺寸先验目录。

设计要点：**不让视觉模型输出米制尺寸**（它会幻觉，同图两次能差 40%）。
模型只输出 category + size_class，真实尺寸在这里查表得到。
查表结果确定、可复现，且符合家具行业标准件规格。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MountType = Literal["floor", "wall", "ceiling"]


@dataclass(frozen=True)
class Prior:
    category: str
    # (宽 w, 深 d, 高 h) 单位米；键为 size_class
    sizes: dict[str, tuple[float, float, float]]
    color: str = "#b9b3aa"
    mount: MountType = "floor"
    mount_height: float = 0.0          # wall/ceiling 类的离地高度
    wall_affinity: bool = False        # 默认是否贴墙
    asset: str | None = None           # models/ 下的 glb 文件名
    # 依附关系：(宿主 category, 相对宿主正前方距离 m)
    attach_to: tuple[str, float] | None = None
    keep_clear: float = 0.0            # 前方需要保留的通行净距


def _s(m: tuple[float, float, float], ratio_s=0.8, ratio_l=1.25):
    """由中号尺寸推导 S / L，仅缩放水平尺寸，高度基本不变。"""
    w, d, h = m
    return {
        "S": (round(w * ratio_s, 2), round(d * ratio_s, 2), h),
        "M": m,
        "L": (round(w * ratio_l, 2), round(d * ratio_l, 2), h),
    }


CATALOG: dict[str, Prior] = {p.category: p for p in [
    # ---------- 客厅 ----------
    Prior("sofa", {"S": (1.50, 0.85, 0.80), "M": (2.00, 0.90, 0.80), "L": (2.60, 0.95, 0.82)},
          "#8d9aaf", wall_affinity=True, asset="sofa.glb", keep_clear=0.5),
    Prior("armchair", _s((0.85, 0.85, 0.90)), "#9aa79b", asset="armchair.glb"),
    Prior("coffee_table", _s((1.10, 0.60, 0.42)), "#a9855f", asset="coffee_table.glb",
          attach_to=("sofa", 0.55)),
    Prior("tv_stand", _s((1.60, 0.40, 0.50)), "#6f665c", wall_affinity=True, asset="tv_stand.glb"),
    Prior("tv", {"S": (0.95, 0.07, 0.58), "M": (1.20, 0.08, 0.70), "L": (1.50, 0.08, 0.87)},
          "#26282b", mount="wall", mount_height=0.95, wall_affinity=True, asset="tv.glb"),
    Prior("bookshelf", _s((0.90, 0.32, 1.80)), "#8a7355", wall_affinity=True, asset="bookshelf.glb"),
    Prior("rug", _s((2.00, 1.40, 0.02)), "#c2b49a", asset="rug.glb"),

    # ---------- 卧室 ----------
    Prior("bed", {"S": (0.95, 2.00, 0.50), "M": (1.50, 2.00, 0.50), "L": (1.80, 2.00, 0.52)},
          "#c9c2b6", wall_affinity=True, asset="bed.glb", keep_clear=0.6),
    # 床头柜走侧向依附，见 scene_builder.LATERAL_ATTACH，不用 attach_to（那是正面依附）
    Prior("nightstand", _s((0.45, 0.40, 0.55)), "#a08a6a",
          wall_affinity=True, asset="nightstand.glb"),
    Prior("wardrobe", _s((1.60, 0.60, 2.20)), "#8f7f6b", wall_affinity=True, asset="wardrobe.glb"),
    Prior("dresser", _s((1.20, 0.45, 0.80)), "#96826a", wall_affinity=True, asset="dresser.glb"),

    # ---------- 餐厅 / 收纳 ----------
    Prior("dining_table", _s((1.40, 0.80, 0.75)), "#b0894f",
          asset="dining_table.glb", keep_clear=0.7),
    Prior("dining_chair", _s((0.45, 0.50, 0.90)), "#9c8a72", asset="dining_chair.glb"),
    Prior("cabinet", _s((1.00, 0.40, 0.90)), "#8b7d6b", wall_affinity=True, asset="cabinet.glb"),

    # ---------- 书房 ----------
    Prior("desk", _s((1.20, 0.60, 0.75)), "#a58c6f", wall_affinity=True, asset="desk.glb"),
    Prior("office_chair", _s((0.60, 0.60, 1.00)), "#4a4f57", asset="office_chair.glb",
          attach_to=("desk", 0.55)),

    # ---------- 软装 / 设备 ----------
    Prior("plant", _s((0.50, 0.50, 1.20)), "#5c7f52", asset="plant.glb"),
    Prior("floor_lamp", _s((0.35, 0.35, 1.60)), "#d8cfa8", asset="floor_lamp.glb"),
    Prior("ceiling_lamp", _s((0.50, 0.50, 0.30)), "#efe6c8", mount="ceiling", asset="ceiling_lamp.glb"),
    Prior("curtain", _s((1.80, 0.10, 2.30)), "#ded5c6", mount="wall", mount_height=0.0,
          wall_affinity=True, asset="curtain.glb"),
    Prior("air_conditioner", _s((0.90, 0.25, 0.30)), "#f0f0ee", mount="wall", mount_height=2.05,
          wall_affinity=True, asset="ac.glb"),

    # ---------- 厨卫 ----------
    Prior("fridge", _s((0.70, 0.70, 1.80)), "#d6d9dc", wall_affinity=True, asset="fridge.glb"),
    Prior("kitchen_counter", _s((1.80, 0.60, 0.90)), "#cfcac2", wall_affinity=True, asset="counter.glb"),
    Prior("toilet", _s((0.40, 0.70, 0.80)), "#f4f4f2", wall_affinity=True, asset="toilet.glb"),
    Prior("sink", _s((0.60, 0.50, 0.85)), "#eeeeec", wall_affinity=True, asset="sink.glb"),
    Prior("bathtub", _s((1.70, 0.75, 0.60)), "#f2f2f0", wall_affinity=True, asset="bathtub.glb"),

    # ---------- 兜底 ----------
    Prior("unknown", _s((0.60, 0.60, 0.60)), "#b0b0b0"),
]}

ALLOWED_CATEGORIES: list[str] = [c for c in CATALOG if c != "unknown"]

# 常见中英文别名 → 受控词表。VLM 偶尔会不听话，这里做一层归一化。
ALIASES: dict[str, str] = {
    "couch": "sofa", "settee": "sofa", "沙发": "sofa",
    "chair": "armchair", "单人沙发": "armchair", "扶手椅": "armchair",
    "tea_table": "coffee_table", "side_table": "coffee_table", "茶几": "coffee_table",
    "table": "dining_table", "餐桌": "dining_table", "书桌": "desk", "写字台": "desk",
    "tv_cabinet": "tv_stand", "media_console": "tv_stand", "电视柜": "tv_stand",
    "television": "tv", "monitor": "tv", "电视": "tv",
    "shelf": "bookshelf", "书架": "bookshelf", "carpet": "rug", "地毯": "rug",
    "床": "bed", "double_bed": "bed", "single_bed": "bed",
    "bedside_table": "nightstand", "床头柜": "nightstand",
    "closet": "wardrobe", "衣柜": "wardrobe", "chest_of_drawers": "dresser",
    "stool": "dining_chair", "餐椅": "dining_chair",
    "potted_plant": "plant", "绿植": "plant", "盆栽": "plant",
    "lamp": "floor_lamp", "落地灯": "floor_lamp", "吊灯": "ceiling_lamp",
    "窗帘": "curtain", "空调": "air_conditioner", "aircon": "air_conditioner",
    "refrigerator": "fridge", "冰箱": "fridge",
}


def normalize_category(raw: str) -> str:
    if not raw:
        return "unknown"
    k = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if k in CATALOG:
        return k
    if k in ALIASES:
        return ALIASES[k]
    # 宽松包含匹配，例如 "large_sofa" → sofa
    for cat in CATALOG:
        if cat != "unknown" and cat in k:
            return cat
    return "unknown"


def get_prior(category: str) -> Prior:
    return CATALOG.get(category, CATALOG["unknown"])


def get_size(category: str, size_class: str | None) -> tuple[float, float, float]:
    prior = get_prior(category)
    sc = (size_class or "M").upper()
    return prior.sizes.get(sc, prior.sizes["M"])


# 房间类型 → 默认尺寸（宽, 深, 高）。比深度估计更可靠，用户可在前端微调。
ROOM_DEFAULTS: dict[str, tuple[float, float, float]] = {
    "living_room": (5.0, 4.0, 2.8),
    "bedroom": (3.6, 3.6, 2.8),
    "dining_room": (4.0, 3.4, 2.8),
    "study": (3.2, 3.0, 2.8),
    "kitchen": (3.0, 2.4, 2.6),
    "bathroom": (2.4, 2.0, 2.5),
    "balcony": (3.0, 1.5, 2.6),
    "office": (5.0, 4.0, 2.9),
    "unknown": (4.5, 3.8, 2.8),
}


def get_room_default(room_type: str) -> tuple[float, float, float]:
    return ROOM_DEFAULTS.get((room_type or "").lower(), ROOM_DEFAULTS["unknown"])
