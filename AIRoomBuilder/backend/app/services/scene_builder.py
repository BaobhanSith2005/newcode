"""analysis.json → scene.json 的确定性构建管线。

整个项目的核心设计：**把 AI 的不确定性限制在视觉识别这一步**，
之后的尺寸、布局、资产绑定全部由确定性代码完成。

管线：
  1. 房间定尺       room_type → 预设尺寸（可被用户覆盖）
  2. 品类归一化     自由文本 → 受控词表
  3. 尺寸查表       category + size_class → 真实米制 W/D/H
  4. 朝向推导       against_wall / rotation_hint → rotation_y（吸附到 90° 栅格）
  5. 贴墙吸附       靠墙家具的背面与墙面对齐
  6. 依附关系       茶几→沙发前方，办公椅→书桌前方，床头柜→床两侧
  7. 边界钳制       包围盒不得出房间
  8. 重叠消解       俯视矩形迭代分离
  9. 资产绑定       匹配 glb，缺失则降级为参数化几何体
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from ..config import MODELS_DIR
from .catalog import get_prior, get_room_default, get_size, normalize_category

SCHEMA_VERSION = "1.0"

# 朝向（物体正面指向的方位）→ rotation_y。0° 表示正面朝 +Z。
FACING_TO_ROT = {"south": 0.0, "east": 90.0, "north": 180.0, "west": 270.0}
# 靠墙 → 正面应朝向房间内侧
WALL_TO_ROT = {"north": 0.0, "west": 90.0, "south": 180.0, "east": 270.0}

# 侧向依附：床头柜贴在床的左右两侧
LATERAL_ATTACH = {"nightstand": "bed"}

# 缺失 glb 时前端使用的参数化替身类型
FALLBACK_SHAPE = {
    "rug": "plane",
    "plant": "plant", "floor_lamp": "lamp", "ceiling_lamp": "lamp",
    "sofa": "sofa", "armchair": "sofa",
    "bed": "bed",
    "dining_chair": "chair", "office_chair": "chair",
    "coffee_table": "table", "dining_table": "table", "desk": "table",
    "tv": "screen",
}
OPENING_WIDTH = {"S": 0.9, "M": 1.4, "L": 2.0}


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clamp_dim(v: Any, lo: float, hi: float) -> float | None:
    """把模型估的房间尺度值夹到合理范围；无效/非数/超界返回 None。"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x <= 0 or not math.isfinite(x):
        return None
    return max(lo, min(hi, x))


def _footprint(w: float, d: float, rot: float) -> tuple[float, float]:
    """旋转 90/270 度后，俯视占地的 X/Z 尺寸互换。"""
    return (d, w) if int(round(rot)) % 180 == 90 else (w, d)


def _forward(rot: float) -> tuple[float, float]:
    """rotation_y 对应的正面单位向量 (dx, dz)。"""
    r = int(round(rot)) % 360
    return {0: (0.0, 1.0), 90: (1.0, 0.0), 180: (0.0, -1.0), 270: (-1.0, 0.0)}.get(r, (0.0, 1.0))


def snap_to_wall(o: dict, wall: str, W: float, D: float) -> None:
    """把物体背面贴到指定墙面。只改垂直于墙的那个坐标，沿墙方向的位置保持不变。"""
    fw, fd = _footprint(o["size"]["w"], o["size"]["d"], o["rotation_y"])
    if wall == "north":
        o["position"][2] = -D / 2 + fd / 2
    elif wall == "south":
        o["position"][2] = D / 2 - fd / 2
    elif wall == "west":
        o["position"][0] = -W / 2 + fw / 2
    elif wall == "east":
        o["position"][0] = W / 2 - fw / 2


class SceneBuilder:
    def __init__(self, analysis: dict[str, Any], room_override: dict | None = None):
        self.analysis = analysis or {}
        self.room_override = room_override or {}
        self.warnings: list[str] = []

    # ------------------------------------------------------------------ 主流程
    def build(self) -> dict[str, Any]:
        room_type = (self.analysis.get("room_type") or "unknown").lower()
        w0, d0, h0 = get_room_default(room_type)
        # 房间尺度优先级：用户滑块 > 模型估算 > 房型预设（保证开箱即有合理尺寸）
        est = self.analysis.get("room") or {}
        ew = _clamp_dim(est.get("width_m"), 2.0, 15.0)
        ed = _clamp_dim(est.get("depth_m"), 2.0, 15.0)
        eh = _clamp_dim(est.get("height_m"), 2.2, 4.0)
        user_w = self.room_override.get("width")
        user_d = self.room_override.get("depth")
        user_h = self.room_override.get("height")
        self.W = float(user_w or ew or w0)
        self.D = float(user_d or ed or d0)
        self.H = float(user_h or eh or h0)
        if user_w or user_d or user_h:
            size_source = "user"
        elif ew or ed or eh:
            size_source = "model"
        else:
            size_source = "preset"

        objects = [o for o in (self._make_object(i, raw)
                               for i, raw in enumerate(self.analysis.get("objects") or []))
                   if o]

        self._apply_attachments(objects)
        for o in objects:
            self._clamp_to_room(o)
        self._resolve_overlaps(objects)
        for o in objects:
            self._clamp_to_room(o)
            o["position"] = [round(v, 3) for v in o["position"]]

        return {
            "schema_version": SCHEMA_VERSION,
            "scene_id": f"sc_{uuid.uuid4().hex[:8]}",
            "room": {
                "type": room_type,
                "width": round(self.W, 2),
                "depth": round(self.D, 2),
                "height": round(self.H, 2),
                "size_source": size_source,
                "floor": {"material": "wood", "color": "#c8a97e"},
                "wall": {"material": "paint", "color": self._wall_color()},
                "ceiling": {"material": "paint", "color": "#fbfbfa"},
            },
            "openings": self._build_openings(),
            "objects": objects,
            "lighting": {"preset": "daylight", "ambient_intensity": 0.65, "main_intensity": 1.15},
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "style": self.analysis.get("style"),
                "notes": self.analysis.get("notes"),
                "vision": self.analysis.get("_meta", {}),
                "warnings": self.warnings,
            },
        }

    def _wall_color(self) -> str:
        colors = self.analysis.get("dominant_colors") or []
        for c in colors:
            if isinstance(c, str) and c.startswith("#") and len(c) == 7:
                return c
        return "#f2efe9"

    # ------------------------------------------------------------------ 单物体
    def _make_object(self, idx: int, raw: dict) -> dict | None:
        if not isinstance(raw, dict):
            return None

        category = normalize_category(raw.get("category") or raw.get("name") or "")
        prior = get_prior(category)
        if category == "unknown":
            self.warnings.append(f"未识别品类 '{raw.get('category')}'，已降级渲染")

        ow, od, oh = get_size(category, raw.get("size_class"))

        wall = (raw.get("against_wall") or "center").lower()
        if wall not in WALL_TO_ROT:
            wall = "center"

        # 朝向：靠墙优先按墙面推导（更可靠），否则用模型给的 hint
        if wall != "center":
            rot = WALL_TO_ROT[wall]
        else:
            rot = FACING_TO_ROT.get((raw.get("rotation_hint") or "south").lower(), 0.0)

        uv = raw.get("floor_uv") or [0.5, 0.5]
        try:
            u = _clamp(float(uv[0]), 0.0, 1.0)
            v = _clamp(float(uv[1]), 0.0, 1.0)
        except (TypeError, ValueError, IndexError):
            u, v = 0.5, 0.5
            self.warnings.append(f"{category} 的 floor_uv 非法，已置于房间中心")

        x = (u - 0.5) * self.W
        z = (v - 0.5) * self.D

        fw, fd = _footprint(ow, od, rot)

        # 贴墙吸附：背面与墙面对齐，只保留沿墙方向的自由度
        if wall != "center" and prior.wall_affinity:
            if wall == "north":
                z = -self.D / 2 + fd / 2
            elif wall == "south":
                z = self.D / 2 - fd / 2
            elif wall == "west":
                x = -self.W / 2 + fw / 2
            elif wall == "east":
                x = self.W / 2 - fw / 2

        # 高度：落地 0；挂墙用挂高；吸顶贴天花板
        if prior.mount == "ceiling":
            y = self.H - oh
        elif prior.mount == "wall":
            y = prior.mount_height
        else:
            y = 0.0

        # 挂墙物贴合墙面（厚度方向压到墙上）
        if prior.mount == "wall" and wall != "center":
            if wall == "north":
                z = -self.D / 2 + fd / 2
            elif wall == "south":
                z = self.D / 2 - fd / 2
            elif wall == "west":
                x = -self.W / 2 + fw / 2
            elif wall == "east":
                x = self.W / 2 - fw / 2

        asset_file = prior.asset
        if asset_file and (MODELS_DIR / asset_file).exists():
            asset = {"kind": "gltf", "url": f"/models/{asset_file}",
                     "fallback": FALLBACK_SHAPE.get(category, "box")}
        else:
            asset = {"kind": "primitive", "url": None,
                     "fallback": FALLBACK_SHAPE.get(category, "box")}

        # 颜色来源优先级：OpenCV 分析结果（dict）> VLM 直接颜色（str）> 品类默认
        raw_color = raw.get("color")
        hex_color = None
        if isinstance(raw_color, dict):
            hex_color = raw_color.get("hex")
            color_name = raw_color.get("name") or ""
        elif isinstance(raw_color, str) and raw_color.startswith("#") and len(raw_color) == 7:
            hex_color = raw_color
            color_name = ""
        if not hex_color:
            hex_color = prior.color
            color_name = ""

        material = {"color": hex_color, "name": color_name}

        return {
            "id": f"obj_{idx + 1}",
            "category": category,
            "label": raw.get("label") or category,
            "asset": asset,
            "size": {"w": ow, "d": od, "h": oh},
            "position": [x, y, z],
            "rotation_y": rot,
            "against_wall": None if wall == "center" else wall,
            "material": material,
            "confidence": float(raw.get("confidence") or 0.6),
            "source": "vlm",
            "_mount": prior.mount,          # 下划线前缀为内部字段，序列化前剔除
            "_attach": prior.attach_to,
        }

    # ------------------------------------------------------------------ 依附
    def _apply_attachments(self, objects: list[dict]) -> None:
        by_cat: dict[str, list[dict]] = {}
        for o in objects:
            by_cat.setdefault(o["category"], []).append(o)

        # 正面依附：茶几落在沙发正前方，办公椅落在书桌正前方
        for o in objects:
            attach = o.get("_attach")
            if not attach:
                continue
            host_cat, dist = attach
            if dist <= 0:
                continue
            hosts = by_cat.get(host_cat)
            if not hosts:
                continue
            host = min(hosts, key=lambda h: (h["position"][0] - o["position"][0]) ** 2
                       + (h["position"][2] - o["position"][2]) ** 2)
            # 先定朝向（背对宿主），再按新朝向算占地，否则 90/270 度时尺寸会取错
            o["rotation_y"] = (host["rotation_y"] + 180) % 360
            dx, dz = _forward(host["rotation_y"])
            hw, hd = _footprint(host["size"]["w"], host["size"]["d"], host["rotation_y"])
            ow_, od_ = _footprint(o["size"]["w"], o["size"]["d"], o["rotation_y"])
            gap = (hd if dz else hw) / 2 + dist + (od_ if dz else ow_) / 2
            o["position"][0] = host["position"][0] + dx * gap
            o["position"][2] = host["position"][2] + dz * gap
            o["against_wall"] = None          # 已脱离墙面，解除轴锁定
            o["source"] = "solver"

        # 侧向依附：床头柜贴床左右两侧
        for cat, host_cat in LATERAL_ATTACH.items():
            items = by_cat.get(cat) or []
            hosts = by_cat.get(host_cat) or []
            if not items or not hosts:
                continue
            host = hosts[0]
            dx, dz = _forward(host["rotation_y"])
            rx, rz = -dz, dx                       # 右向量
            hw, _hd = _footprint(host["size"]["w"], host["size"]["d"], host["rotation_y"])
            for i, it in enumerate(items[:2]):
                side = 1 if i == 0 else -1
                it["rotation_y"] = host["rotation_y"]
                ow_, _ = _footprint(it["size"]["w"], it["size"]["d"], it["rotation_y"])
                off = hw / 2 + 0.05 + ow_ / 2
                it["position"][0] = host["position"][0] + rx * off * side
                it["position"][2] = host["position"][2] + rz * off * side
                # 床头柜应与床头齐平贴墙，而不是停在床身中段
                host_wall = host.get("against_wall")
                if host_wall:
                    it["against_wall"] = host_wall
                    snap_to_wall(it, host_wall, self.W, self.D)
                else:
                    it["against_wall"] = None
                it["source"] = "solver"

    # ------------------------------------------------------------------ 约束
    def _clamp_to_room(self, o: dict) -> None:
        fw, fd = _footprint(o["size"]["w"], o["size"]["d"], o["rotation_y"])
        o["position"][0] = _clamp(o["position"][0], -self.W / 2 + fw / 2, self.W / 2 - fw / 2)
        o["position"][2] = _clamp(o["position"][2], -self.D / 2 + fd / 2, self.D / 2 - fd / 2)

    def _resolve_overlaps(self, objects: list[dict], iterations: int = 60) -> None:
        """俯视矩形迭代分离。地毯与非落地物不参与碰撞。"""
        movable = [o for o in objects
                   if o["_mount"] == "floor" and o["category"] != "rug"]

        for _ in range(iterations):
            moved = False
            for i in range(len(movable)):
                for j in range(i + 1, len(movable)):
                    a, b = movable[i], movable[j]
                    aw, ad = _footprint(a["size"]["w"], a["size"]["d"], a["rotation_y"])
                    bw, bd = _footprint(b["size"]["w"], b["size"]["d"], b["rotation_y"])

                    dx = b["position"][0] - a["position"][0]
                    dz = b["position"][2] - a["position"][2]
                    ox = (aw + bw) / 2 - abs(dx)      # X 方向重叠量
                    oz = (ad + bd) / 2 - abs(dz)      # Z 方向重叠量
                    if ox <= 1e-4 or oz <= 1e-4:
                        continue                      # 未相交

                    moved = True
                    # 沿穿透较浅的轴分离，位移更自然
                    if ox < oz:
                        push = (ox / 2 + 0.01) * (1 if dx >= 0 else -1)
                        self._push(a, b, push, axis=0)
                    else:
                        push = (oz / 2 + 0.01) * (1 if dz >= 0 else -1)
                        self._push(a, b, push, axis=2)

            for o in movable:
                self._clamp_to_room(o)
            if not moved:
                break

    def _push(self, a: dict, b: dict, push: float, axis: int) -> None:
        """分离两个物体。靠墙家具不允许被推离墙面，只能沿墙滑动。"""
        a_locked = self._locked_axis(a) == axis
        b_locked = self._locked_axis(b) == axis
        if a_locked and not b_locked:
            b["position"][axis] += push * 2
        elif b_locked and not a_locked:
            a["position"][axis] -= push * 2
        else:
            a["position"][axis] -= push
            b["position"][axis] += push

    @staticmethod
    def _locked_axis(o: dict) -> int | None:
        """靠墙物体被锁定的坐标轴：南北墙锁 Z，东西墙锁 X。"""
        wall = o.get("against_wall")
        if wall in ("north", "south"):
            return 2
        if wall in ("east", "west"):
            return 0
        return None

    # ------------------------------------------------------------------ 门窗
    def _build_openings(self) -> list[dict]:
        out = []
        for i, raw in enumerate(self.analysis.get("openings") or []):
            if not isinstance(raw, dict):
                continue
            wall = (raw.get("wall") or "north").lower()
            if wall not in WALL_TO_ROT:
                continue
            kind = "door" if (raw.get("type") or "window").lower() == "door" else "window"
            width = OPENING_WIDTH.get((raw.get("size_class") or "M").upper(), 1.4)
            out.append({
                "id": f"op_{i + 1}",
                "type": kind,
                "wall": wall,
                "offset": _clamp(float(raw.get("offset") or 0.5), 0.05, 0.95),
                "width": width if kind == "window" else min(width, 1.0),
                "height": 1.4 if kind == "window" else 2.05,
                "sill": 0.9 if kind == "window" else 0.0,
            })
        return out


def build_scene(analysis: dict, room_override: dict | None = None) -> dict:
    scene = SceneBuilder(analysis, room_override).build()
    for o in scene["objects"]:                      # 剔除内部字段
        o.pop("_mount", None)
        o.pop("_attach", None)
    return scene
