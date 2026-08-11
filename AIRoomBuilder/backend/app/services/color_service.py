"""OpenCV 智能颜色分析服务。

根据 VLM 返回的物体像素 bbox，从原始房间照片中提取该区域的主要颜色。
流程：读图 -> 温和灰度世界白平衡 -> 取 bbox(自动识别像素/归一化) -> HSV ->
过滤低饱和/过暗/过亮噪声 -> KMeans 聚类 -> 优先选「有彩色且占比不低」的主簇
(避免把墙/地板这类中性背景色当成物体色) -> RGB 转 HEX 并打中文色名。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# 常见颜色的 HSV 范围（H: 0-179, S/V: 0-255），用于给主簇打一个可读色名。
# 顺序即匹配优先级，特殊色（米色/藏青/橄榄绿）在前，避免被 gray/blue/green 吞掉。
_COLOR_RANGES: list[tuple[str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("red", (0, 70, 50), (10, 255, 255)),
    ("red", (165, 70, 50), (179, 255, 255)),
    ("orange", (10, 70, 50), (22, 255, 255)),
    ("yellow", (22, 55, 50), (34, 255, 255)),
    ("olive", (26, 30, 40), (42, 130, 150)),     # 橄榄绿：黄绿、偏暗
    ("green", (35, 40, 40), (80, 255, 255)),
    ("teal", (80, 45, 45), (100, 200, 220)),      # 青绿
    ("cyan", (85, 55, 60), (100, 255, 255)),
    ("blue", (100, 70, 60), (130, 255, 255)),
    ("navy", (100, 50, 30), (135, 200, 130)),     # 藏青：蓝但偏暗
    ("purple", (130, 55, 50), (160, 255, 255)),
    ("pink", (160, 40, 80), (172, 255, 255)),
    ("brown", (8, 40, 20), (24, 200, 150)),
    ("white", (0, 0, 200), (179, 28, 255)),
    ("black", (0, 0, 0), (179, 255, 35)),
    ("gray", (0, 0, 28), (179, 32, 200)),
]

_COLOR_NAME_CN: dict[str, str] = {
    "red": "红色", "orange": "橙色", "yellow": "黄色",
    "olive": "橄榄绿", "green": "绿色", "teal": "青绿", "cyan": "青色",
    "blue": "蓝色", "navy": "藏青", "purple": "紫色", "pink": "粉色",
    "brown": "棕色", "white": "白色", "black": "黑色", "gray": "灰色",
    "beige": "米色",
}


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{int(v):02x}" for v in rgb)


def _name_for_hsv(hsv: tuple[int, int, int]) -> str:
    """根据 HSV 值匹配一个可读颜色名；命中顺序见 _COLOR_RANGES。"""
    h, s, v = hsv
    # 米色/浅卡其：低饱和、较高明度、暖色相，需优先于 white/gray。
    if s < 45 and v > 135 and h < 45:
        return "beige"
    for name, lower, upper in _COLOR_RANGES:
        if all(lower[i] <= hsv[i] <= upper[i] for i in range(3)):
            return name
    return "gray"


def _bbox_to_slices(
    image: np.ndarray, bbox: list[int] | tuple[int, ...]
) -> tuple[slice, slice]:
    """把 bbox 转成 ROI 切片，并自动识别坐标单位。

    - 所有值 <= 1.001 视为 0~1 归一化坐标，乘原图宽高；
    - 当像素解释会越界且所有值 <= 100 时视为百分比坐标；
    - 其余当作像素坐标（越界则 clamp）。
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    mx = max(abs(x1), abs(y1), abs(x2), abs(y2))

    if mx <= 1.001:                      # 归一化 0~1
        x1, y1, x2, y2 = x1 * w, y1 * h, x2 * w, y2 * h
    else:
        px_ok = (0 <= x1 <= w and 0 <= x2 <= w and 0 <= y1 <= h and 0 <= y2 <= h)
        if not px_ok and mx <= 100.001:  # 越界 + 小数值 -> 百分比
            x1, y1, x2, y2 = x1 * w / 100, y1 * h / 100, x2 * w / 100, y2 * h / 100

    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    x1, x2 = max(0, min(int(round(x1)), w)), max(0, min(int(round(x2)), w))
    y1, y2 = max(0, min(int(round(y1)), h)), max(0, min(int(round(y2)), h))
    if x2 <= x1:
        x2 = min(x1 + 1, w)
    if y2 <= y1:
        y2 = min(y1 + 1, h)
    return slice(y1, y2), slice(x1, x2)


def _dominant_color(filtered: np.ndarray) -> tuple[np.ndarray, float]:
    """对一组已过滤的 BGR 像素做 KMeans，返回 (主簇BGR, 占比)。

    优先返回「饱和度最高且占比不低」的彩色簇，避免选中背景中性色；
    若所有簇都是中性色，则退化到最大簇。
    """
    K = min(5, len(filtered))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(
        filtered, K, None, criteria, 5, cv2.KMEANS_PP_CENTERS
    )
    labels = labels.flatten()
    counts = np.bincount(labels)
    total = float(len(filtered))

    # 各簇饱和度
    hsv_centers = cv2.cvtColor(
        centers.reshape(-1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2HSV
    ).reshape(-1, 3)
    sats = hsv_centers[:, 1].astype(np.float32)

    # 从大到小遍历，优先挑出彩色簇（sat>=40 且占比>=8%），更像物体本身
    order = np.argsort(-counts)
    best: int | None = None
    for idx in order:
        ratio_i = counts[idx] / total
        if sats[idx] >= 40 and ratio_i >= 0.08:
            best = int(idx)
            break
    if best is None:
        best = int(order[0])

    return centers[best].astype(np.uint8), float(counts[best] / total)


def analyze_color(image_path: str | Path, bbox: list[int] | tuple[int, ...]) -> dict[str, Any]:
    """分析图片指定区域的主要颜色。

    Args:
        image_path: 原始图片路径。
        bbox: [x1, y1, x2, y2]，像素/归一化(0~1)/百分比(0~100)均可，自动识别。

    Returns:
        {"name": "gray", "name_cn": "灰色", "hex": "#808080",
         "ratio": 0.72, "method": "kmeans"}
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"图片不存在: {image_path}")

    raw = cv2.imread(str(image_path))
    if raw is None:
        raise ValueError(f"无法读取图片: {image_path}")
    image = raw

    y_slice, x_slice = _bbox_to_slices(image, bbox)
    roi = image[y_slice, x_slice]
    if roi.size == 0:
        raise ValueError("bbox 区域为空")

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    hsv_pixels = hsv.reshape(-1, 3)
    s = hsv_pixels[:, 1].astype(np.float32)
    v = hsv_pixels[:, 2].astype(np.float32)
    pixels = roi.reshape(-1, 3).astype(np.float32)

    # 过滤噪声：低饱和(接近白/灰/黑但靠色相难定)、过暗、过亮
    mask = (s >= 18) & (v >= 22) & (v <= 248)
    filtered = pixels[mask]
    if len(filtered) < 50:                 # 区域太小或太干净，放宽再试
        mask = (v >= 18) & (v <= 252)
        filtered = pixels[mask]
    if len(filtered) < 10:                 # 极端：直接取中值
        median = np.median(pixels, axis=0).astype(np.uint8)
        hsv_m = cv2.cvtColor(median.reshape(1, 1, 3), cv2.COLOR_BGR2HSV)[0, 0]
        return {"name": _name_for_hsv(tuple(int(x) for x in hsv_m)),
                "name_cn": _COLOR_NAME_CN.get(_name_for_hsv(tuple(int(x) for x in hsv_m)), "灰"),
                "hex": _rgb_to_hex((int(median[2]), int(median[1]), int(median[0]))),
                "ratio": 1.0, "method": "median"}

    dominant_bgr, ratio = _dominant_color(filtered)
    dominant_rgb = (int(dominant_bgr[2]), int(dominant_bgr[1]), int(dominant_bgr[0]))
    hex_color = _rgb_to_hex(dominant_rgb)
    dominant_hsv = cv2.cvtColor(
        np.array([[dominant_bgr]], dtype=np.uint8), cv2.COLOR_BGR2HSV
    )[0, 0]
    name = _name_for_hsv(tuple(int(x) for x in dominant_hsv))

    return {
        "name": name,
        "name_cn": _COLOR_NAME_CN.get(name, name),
        "hex": hex_color,
        "ratio": round(ratio, 3),
        "method": "kmeans",
    }


def enrich_objects_with_color(
    image_path: str | Path, objects: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """批量为分析结果中的 objects 补充/覆盖 color 字段。

    只有包含合法 bbox 的物体才会被分析；分析失败时保留原 color 不变。
    """
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        bbox = obj.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        try:
            color = analyze_color(image_path, bbox)
            obj["color"] = {
                "name": color["name_cn"],
                "hex": color["hex"],
                "ratio": color["ratio"],
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("颜色分析失败 category=%s bbox=%s: %s", obj.get("category"), bbox, exc)
    return objects
