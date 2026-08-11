#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""离线生成 26 个家具 .glb 模型，文件名严格对齐 backend/app/services/catalog.py。

设计约定（与渲染器 RoomRenderer.normalizeGltf 对齐）：
- 所有模型从 y=0 向上建造，底面在地板；渲染器会把 min.y 对齐到各自 position.y
  （落地=0 / 挂墙=mount_height / 吊顶=H-oh），再缩放至 scene.json 声明尺寸
- 正面朝 +Z（与 primitives.ts 一致）
- 使用 PBRMaterial：木/布/金属/陶瓷各有区分，比纯色方块明显更耐看

运行：在 backend 目录用项目 venv 执行
  ../venv/Scripts/python.exe tools/gen_models.py
"""
from __future__ import annotations
import colorsys
import math
import trimesh
from trimesh.visual.material import PBRMaterial
from trimesh.visual import TextureVisuals
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

# ---------------------------------------------------------------- 颜色工具
def _hex2rgb(h: str):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]

def _rgb2hex(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(1, c)) * 255) for c in rgb)

def srgb_to_lin(h: str):
    r, g, b = _hex2rgb(h)
    def f(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return [f(r), f(g), f(b), 1.0]

def shade(h: str, amt: float) -> str:
    r, g, b = _hex2rgb(h)
    hue, lum, sat = colorsys.rgb_to_hls(r, g, b)
    lum = max(0.0, min(1.0, lum + amt))
    return _rgb2hex(colorsys.hls_to_rgb(hue, lum, sat))

def mat(h: str, rough: float = 0.7, metal: float = 0.0, emissive: str | None = None):
    bc = srgb_to_lin(h)
    em = srgb_to_lin(emissive)[:3] if emissive else [0.0, 0.0, 0.0]
    return TextureVisuals(material=PBRMaterial(
        baseColorFactor=bc, metallicFactor=metal, roughnessFactor=rough, emissiveFactor=em
    ))

# 通用材质
WOOD        = lambda: mat("#a9855f", rough=0.6)
WOOD_DARK   = lambda: mat("#6f665c", rough=0.6)
WARDR       = lambda: mat("#8f7f6b", rough=0.6)
DRESS       = lambda: mat("#96826a", rough=0.6)
CAB         = lambda: mat("#8b7d6b", rough=0.6)
DESK        = lambda: mat("#a58c6f", rough=0.6)
NIGHT       = lambda: mat("#a08a6a", rough=0.6)
METAL       = lambda: mat("#4a4f57", rough=0.4, metal=0.85)
METAL_L     = lambda: mat("#9a9aa0", rough=0.3, metal=0.9)
CERAMIC     = lambda: mat("#f2f2f0", rough=0.25)
WHITE       = lambda: mat("#ffffff", rough=0.55)
POT         = lambda: mat("#a8724a", rough=0.8)
GREEN       = lambda: mat("#5c7f52", rough=0.8)
BLACK       = lambda: mat("#1b1d20", rough=0.4)
COUNTER     = lambda: mat("#cfcac2", rough=0.6)

# ---------------------------------------------------------------- 基础体素
def B(w, h, d, cx, cy, cz, m):
    mesh = trimesh.creation.box(extents=(w, h, d))
    mesh.apply_translation((cx, cy, cz))
    mesh.visual = m
    return mesh

def V(r, h, cx, cy, cz, m):  # 竖直圆柱（轴沿 Y）
    mesh = trimesh.creation.cylinder(radius=r, height=h, sections=20)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    mesh.apply_translation((cx, cy, cz))
    mesh.visual = m
    return mesh

def HX(r, L, cx, cy, cz, m):  # 沿 X 的横杆
    mesh = trimesh.creation.cylinder(radius=r, height=L, sections=16)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, [0, 1, 0]))
    mesh.apply_translation((cx, cy, cz))
    mesh.visual = m
    return mesh

def HZ(r, L, cx, cy, cz, m):  # 沿 Z 的横杆
    mesh = trimesh.creation.cylinder(radius=r, height=L, sections=16)
    mesh.apply_translation((cx, cy, cz))
    mesh.visual = m
    return mesh

def S(r, cx, cy, cz, m):  # 球
    mesh = trimesh.creation.icosphere(radius=r, subdivisions=2)
    mesh.apply_translation((cx, cy, cz))
    mesh.visual = m
    return mesh

# ---------------------------------------------------------------- 各品类生成器
# 尺寸基准取 catalog 的 M 号 (w, d, h)
GENERATORS = {}

def gen(name):
    def deco(fn):
        GENERATORS[name] = fn
        return fn
    return deco

@gen("sofa")
def _(W, D, H, c):
    fab = mat(c, rough=0.9); fab_d = mat(shade(c, -0.06), rough=0.9)
    seatH = H * 0.42; backD = min(0.18, D * 0.22); armW = min(0.18, W * 0.12)
    p = [B(W, seatH, D, 0, seatH / 2, 0, fab_d),
         B(W, H - seatH, backD, 0, seatH + (H - seatH) / 2, -D / 2 + backD / 2, fab),
         B(armW, H * 0.72, D - backD, -W / 2 + armW / 2, H * 0.36, backD / 2, fab),
         B(armW, H * 0.72, D - backD, W / 2 - armW / 2, H * 0.36, backD / 2, fab)]
    cw = (W - armW * 2) / 2 - 0.03
    for sx in (-1, 1):
        p.append(B(cw, 0.1, D - backD - 0.08, sx * (cw / 2 + 0.02), seatH + 0.05, backD / 2,
                   mat(shade(c, 0.07), rough=0.95)))
    return p

@gen("armchair")
def _(W, D, H, c):
    fab = mat(c, rough=0.9); fab_d = mat(shade(c, -0.06), rough=0.9)
    seatH = H * 0.45; backD = min(0.16, D * 0.22); armW = min(0.16, W * 0.16)
    return [B(W, seatH, D, 0, seatH / 2, 0, fab_d),
            B(W, H - seatH, backD, 0, seatH + (H - seatH) / 2, -D / 2 + backD / 2, fab),
            B(armW, H * 0.7, D - backD, -W / 2 + armW / 2, H * 0.35, backD / 2, fab),
            B(armW, H * 0.7, D - backD, W / 2 - armW / 2, H * 0.35, backD / 2, fab),
            B(W - armW * 2 - 0.04, 0.1, D - backD - 0.06, 0, seatH + 0.05, backD / 2,
              mat(shade(c, 0.07), rough=0.95))]

@gen("coffee_table")
def _(W, D, H, c):
    m = WOOD(); ml = mat(shade("#a9855f", -0.12), rough=0.6)
    p = [B(W, 0.05, D, 0, H - 0.025, 0, m)]
    leg = 0.04
    for sx in (-1, 1):
        for sz in (-1, 1):
            p.append(V(leg, H - 0.05, sx * (W / 2 - leg - 0.03), (H - 0.05) / 2,
                        sz * (D / 2 - leg - 0.03), ml))
    p.append(B(W - 0.1, 0.03, D - 0.1, 0, (H - 0.05) * 0.5, 0, ml))
    return p

@gen("tv_stand")
def _(W, D, H, c):
    m = WOOD_DARK(); ml = mat("#5b544c", rough=0.6)
    p = [B(W, H, D, 0, H / 2, 0, m)]
    for sx in (-1, 1):
        p.append(B(0.02, H - 0.06, D - 0.06, sx * 0.01, H / 2, 0, ml))
    for sx in (-1, 1):
        p.append(V(0.02, 0.12, sx * (W / 2 - 0.12), H - 0.06, 0, METAL_L()))
    return p

@gen("tv")
def _(W, D, H, c):
    m = BLACK(); sc = mat("#0c0d0f", rough=0.3)
    return [B(W, H, D, 0, H / 2, 0, m),
            B(W * 0.96, H * 0.82, D * 0.4, 0, H / 2, D / 2 - D * 0.2, sc)]

@gen("bookshelf")
def _(W, D, H, c):
    m = WOOD(); t = 0.04
    p = [B(t, H, D, -W / 2 + t / 2, H / 2, 0, m),
         B(t, H, D, W / 2 - t / 2, H / 2, 0, m),
         B(W, t, D, 0, t / 2, 0, m),
         B(W, t, D, 0, H - t / 2, 0, m),
         B(W, t * 0.6, D * 0.96, 0, H / 2, -D / 2 + D * 0.04, m)]
    for i in range(1, 4):
        p.append(B(W - t * 2, t, D, 0, i * H / 4, 0, m))
    # 几本书点缀
    for i in range(3):
        p.append(B(0.05, 0.22, 0.16, -W / 2 + 0.18 + i * 0.08, H / 4 + 0.13, 0,
                   mat(["#9c4a3c", "#3c6b9c", "#5c8a4a"][i], rough=0.8)))
    return p

@gen("rug")
def _(W, D, H, c):
    m = mat(c, rough=0.95)
    return [B(W, max(H, 0.02), D, 0, 0.01, 0, m),
            B(W * 0.94, 0.012, D * 0.9, 0, 0.022, 0, mat(shade(c, 0.08), rough=0.95))]

@gen("bed")
def _(W, D, H, c):
    frameH = H * 0.4
    fab = mat(shade(c, 0.1), rough=0.9)
    p = [B(W, frameH, D, 0, frameH / 2, 0, WOOD()),
         B(W - 0.06, H - frameH, D - 0.06, 0, frameH + (H - frameH) / 2, 0, fab),
         B(W, H * 1.2, 0.08, 0, H * 0.6, -D / 2 + 0.04, WOOD_DARK())]
    pw = min(0.55, W / 2 - 0.1)
    for sx in (-1, 1):
        p.append(B(pw, 0.14, 0.4, sx * (pw / 2 + 0.04), H + 0.04, -D / 2 + 0.34, WHITE()))
    return p

@gen("nightstand")
def _(W, D, H, c):
    m = NIGHT(); ml = mat(shade("#a08a6a", -0.12), rough=0.6)
    p = [B(W, H * 0.82, D, 0, H * 0.41, 0, m)]
    for i in range(2):
        p.append(B(W - 0.06, 0.03, D - 0.06, 0, H * (0.28 + i * 0.4), 0, ml))
    for sx in (-1, 1):
        p.append(V(0.02, H * 0.18, sx * (W / 2 - 0.05), H * 0.09, D / 2 - 0.03, METAL_L()))
    return p

@gen("wardrobe")
def _(W, D, H, c):
    m = WARDR(); ml = mat(shade("#8f7f6b", -0.12), rough=0.6)
    p = [B(W, H, D, 0, H / 2, 0, m)]
    p.append(B(0.02, H - 0.1, D - 0.06, 0, H / 2, D / 2 - 0.03, ml))
    for sx in (-1, 1):
        p.append(V(0.02, 0.18, sx * (W * 0.22), H / 2, D / 2 - 0.02, METAL_L()))
    return p

@gen("dresser")
def _(W, D, H, c):
    m = DRESS(); ml = mat(shade("#96826a", -0.12), rough=0.6)
    p = [B(W, H * 0.8, D, 0, H * 0.4, 0, m)]
    for i in range(3):
        p.append(B(W - 0.08, 0.03, D - 0.06, 0, H * (0.2 + i * 0.25), D / 2 - 0.03, ml))
    for sx in (-1, 1):
        for i in range(3):
            p.append(V(0.015, 0.12, sx * (W / 2 - 0.1), H * (0.2 + i * 0.25), D / 2 - 0.01, METAL_L()))
    for sx in (-1, 1):
        p.append(V(0.03, H * 0.2, sx * (W / 2 - 0.06), H * 0.1, 0, ml))
    return p

@gen("dining_table")
def _(W, D, H, c):
    m = WOOD(); ml = mat(shade("#b0894f", -0.15), rough=0.6)
    p = [B(W, 0.05, D, 0, H - 0.025, 0, m)]
    leg = 0.05
    for sx in (-1, 1):
        for sz in (-1, 1):
            p.append(V(leg, H - 0.05, sx * (W / 2 - leg - 0.03), (H - 0.05) / 2,
                        sz * (D / 2 - leg - 0.03), ml))
    return p

@gen("dining_chair")
def _(W, D, H, c):
    m = WOOD(); ml = mat(shade("#9c8a72", -0.15), rough=0.6)
    seatH = H * 0.45
    p = [B(W, 0.06, D, 0, seatH, 0, m),
         B(W, H - seatH, 0.05, 0, seatH + (H - seatH) / 2, -D / 2 + 0.025, m)]
    leg = 0.035
    for sx in (-1, 1):
        for sz in (-1, 1):
            p.append(V(leg, seatH, sx * (W / 2 - leg), seatH / 2, sz * (D / 2 - leg), ml))
    return p

@gen("cabinet")
def _(W, D, H, c):
    m = CAB(); ml = mat(shade("#8b7d6b", -0.12), rough=0.6)
    p = [B(W, H, D, 0, H / 2, 0, m)]
    p.append(B(0.02, H - 0.1, D - 0.06, 0, H / 2, D / 2 - 0.03, ml))
    for sx in (-1, 1):
        p.append(V(0.02, 0.16, sx * (W * 0.25), H / 2, D / 2 - 0.02, METAL_L()))
    return p

@gen("desk")
def _(W, D, H, c):
    m = DESK(); ml = mat(shade("#a58c6f", -0.15), rough=0.6)
    p = [B(W, 0.05, D, 0, H - 0.025, 0, m)]
    for sx in (-1, 1):
        p.append(B(0.05, H - 0.05, D - 0.1, sx * (W / 2 - 0.03), (H - 0.05) / 2, 0, ml))
    p.append(B(W * 0.4, H - 0.12, D - 0.12, -W / 2 + W * 0.2 + 0.03, (H - 0.12) / 2 + 0.02, 0, ml))
    return p

@gen("office_chair")
def _(W, D, H, c):
    m = METAL(); seatH = H * 0.45
    p = [B(W, 0.08, D, 0, seatH, 0, m),
         B(W, H * 0.5, 0.06, 0, seatH + (H * 0.5) / 2, -D / 2 + 0.03, m),
         V(0.045, seatH - 0.08, 0, (seatH - 0.08) / 2 + 0.04, 0, m),
         B(W * 0.9, 0.05, W * 0.9, 0, 0.025, 0, m)]
    for a in [0, 72, 144, 216, 288]:
        rad = math.radians(a)
        p.append(HZ(0.025, W * 0.45, math.cos(rad) * W * 0.22, 0.03, math.sin(rad) * W * 0.22, m))
    return p

@gen("plant")
def _(W, D, H, c):
    r = min(W, D) / 2
    potH = H * 0.28
    pot = trimesh.creation.cylinder(radius=r * 0.72, height=potH, sections=18)
    pot.apply_transform(trimesh.transformations.rotation_matrix(-math.pi / 2, [1, 0, 0]))
    pot.apply_translation((0, potH / 2, 0))
    pot.visual = POT()
    p = [pot]
    for i in range(6):
        ang = i / 6 * math.tau
        rr = r * (0.5 + (i % 3) * 0.18)
        p.append(S(r * (0.5 + (i % 2) * 0.25),
                   math.cos(ang) * r * 0.4, potH + H * (0.35 + (i % 3) * 0.18),
                   math.sin(ang) * r * 0.4, GREEN()))
    p.append(S(r * 0.6, 0, potH + H * 0.55, 0, GREEN()))
    return p

@gen("floor_lamp")
def _(W, D, H, c):
    r = min(W, D) / 2
    shadeMat = mat(c, rough=0.55, emissive=shade(c, 0.1))
    return [V(r * 0.8, 0.04, 0, 0.02, 0, METAL_L()),
            V(0.018, H * 0.8, 0, H * 0.4, 0, METAL_L()),
            V(r * 0.95, H * 0.2, 0, H * 0.88, 0, shadeMat)]

@gen("ceiling_lamp")
def _(W, D, H, c):
    shadeMat = mat(c, rough=0.5, emissive=shade(c, 0.15))
    return [B(W * 0.9, H, W * 0.9, 0, H / 2, 0, shadeMat),
            V(0.02, 0.06, 0, H + 0.03, 0, METAL_L())]

@gen("curtain")
def _(W, D, H, c):
    fab = mat(c, rough=0.95)
    p = [B(W, H, 0.06, 0, H / 2, 0, fab)]
    # 褶皱
    for i in range(5):
        p.append(B(W / 6, H * 0.98, 0.04, -W / 2 + W / 12 + i * W / 6, H / 2, 0.005,
                   mat(shade(c, -0.05), rough=0.95)))
    p.append(HX(0.02, W * 1.05, 0, H - 0.02, 0, METAL_L()))
    return p

@gen("ac")
def _(W, D, H, c):
    return [B(W, H, D, 0, H / 2, 0, WHITE()),
            B(W, H * 0.25, D * 0.6, 0, H * 0.2, D / 2 - 0.01, mat("#dfe3e6", rough=0.4))]

@gen("fridge")
def _(W, D, H, c):
    m = mat("#d6d9dc", rough=0.35, metal=0.3)
    p = [B(W, H, D, 0, H / 2, 0, m),
         B(W, 0.02, D, 0, H * 0.72, 0, mat("#bcc0c4", rough=0.4)),
         V(0.02, 0.3, W / 2 - 0.07, H * 0.85, D / 2 - 0.02, METAL_L()),
         V(0.02, 0.3, W / 2 - 0.07, H * 0.4, D / 2 - 0.02, METAL_L())]
    return p

@gen("counter")
def _(W, D, H, c):
    m = COUNTER(); top = mat("#3a3a3e", rough=0.4)
    p = [B(W, H, D, 0, H / 2, 0, m),
         B(W * 1.02, 0.06, D * 1.02, 0, H + 0.03, 0, top)]
    for sx in (-1, 1):
        p.append(B(0.02, H - 0.1, D - 0.06, sx * 0.01, H / 2, D / 2 - 0.03, mat("#bdb8b0", rough=0.6)))
    for sx in (-1, 1):
        p.append(V(0.02, 0.18, sx * (W * 0.25), H / 2, D / 2 - 0.02, METAL_L()))
    return p

@gen("toilet")
def _(W, D, H, c):
    m = CERAMIC()
    return [B(W * 0.85, H * 0.5, D * 0.35, 0, H * 0.75, -D / 2 + D * 0.35 / 2, m),
            V(W / 2 * 0.8, H * 0.5, 0, H * 0.25, 0, m),
            B(W * 0.6, 0.06, D * 0.6, 0, H * 0.52, 0, mat("#e8e8e6", rough=0.2))]

@gen("sink")
def _(W, D, H, c):
    m = CERAMIC(); cab = mat("#eeeeec", rough=0.5)
    return [B(W, H, D, 0, H / 2, 0, cab),
            B(W * 1.0, 0.06, D * 1.0, 0, H + 0.03, 0, mat("#3a3a3e", rough=0.4)),
            V(W * 0.32, 0.14, 0, H + 0.02, 0, m)]

@gen("bathtub")
def _(W, D, H, c):
    m = CERAMIC(); inner = mat("#e6e6e3", rough=0.3)
    return [B(W, H, D, 0, H / 2, 0, m),
            B(W - 0.2, H * 0.6, D - 0.2, 0, H * 0.32, 0, inner)]

# ---------------------------------------------------------------- 尺寸表（catalog M 号）
SIZES = {
    "sofa": (2.00, 0.90, 0.80), "armchair": (0.85, 0.85, 0.90),
    "coffee_table": (1.10, 0.60, 0.42), "tv_stand": (1.60, 0.40, 0.50),
    "tv": (1.20, 0.08, 0.70), "bookshelf": (0.90, 0.32, 1.80),
    "rug": (2.00, 1.40, 0.02), "bed": (1.50, 2.00, 0.50),
    "nightstand": (0.45, 0.40, 0.55), "wardrobe": (1.60, 0.60, 2.20),
    "dresser": (1.20, 0.45, 0.80), "dining_table": (1.40, 0.80, 0.75),
    "dining_chair": (0.45, 0.50, 0.90), "cabinet": (1.00, 0.40, 0.90),
    "desk": (1.20, 0.60, 0.75), "office_chair": (0.60, 0.60, 1.00),
    "plant": (0.50, 0.50, 1.20), "floor_lamp": (0.35, 0.35, 1.60),
    "ceiling_lamp": (0.50, 0.50, 0.30), "curtain": (1.80, 0.10, 2.30),
    "ac": (0.90, 0.25, 0.30), "fridge": (0.70, 0.70, 1.80),
    "counter": (1.80, 0.60, 0.90), "toilet": (0.40, 0.70, 0.80),
    "sink": (0.60, 0.50, 0.85), "bathtub": (1.70, 0.75, 0.60),
}
COLORS = {
    "sofa": "#8d9aaf", "armchair": "#9aa79b", "coffee_table": "#a9855f",
    "tv_stand": "#6f665c", "tv": "#26282b", "bookshelf": "#8a7355",
    "rug": "#c2b49a", "bed": "#c9c2b6", "nightstand": "#a08a6a",
    "wardrobe": "#8f7f6b", "dresser": "#96826a", "dining_table": "#b0894f",
    "dining_chair": "#9c8a72", "cabinet": "#8b7d6b", "desk": "#a58c6f",
    "office_chair": "#4a4f57", "plant": "#5c7f52", "floor_lamp": "#d8cfa8",
    "ceiling_lamp": "#efe6c8", "curtain": "#ded5c6", "ac": "#f0f0ee",
    "fridge": "#d6d9dc", "counter": "#cfcac2", "toilet": "#f4f4f2",
    "sink": "#eeeeec", "bathtub": "#f2f2f0",
}

def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    ok, fail = [], []
    for name, (W, D, H) in SIZES.items():
        parts = GENERATORS[name](W, D, H, COLORS[name])
        if not parts:
            fail.append(name); continue
        scene = trimesh.Scene()
        for i, mesh in enumerate(parts):
            scene.add_geometry(mesh, geom_name=f"p{i}", node_name=f"p{i}")
        out = MODELS_DIR / f"{name}.glb"
        try:
            scene.export(str(out))
            ok.append(name)
        except Exception as e:  # noqa
            fail.append(f"{name}:{e}")
    print(f"生成成功 {len(ok)} 个，失败 {len(fail)} 个")
    if fail:
        print("失败：", fail)
    # 校验
    sample = MODELS_DIR / "sofa.glb"
    if sample.exists():
        sc = trimesh.load(str(sample))
        ngeom = len(sc.geometry) if hasattr(sc, "geometry") else 1
        print(f"校验 sofa.glb: 几何部件={ngeom}, 大小={sample.stat().st_size} bytes")

if __name__ == "__main__":
    main()
