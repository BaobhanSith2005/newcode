"""漫画气泡文字检测 + 译文位置配对 —— RapidOCR 封装（onnxruntime 内核，CPU 就够快）。

一次调用同时拿到"文字"和"四点坐标"——嵌字需要的两样原料：
文字送去翻译，坐标用来擦除和画回；译文回来后按文字 difflib 配对回坐标（pair_entries）。
模型内置在 rapidocr 包里，首次运行自动加载，不用另外下模型。
"""
from __future__ import annotations

import difflib
import math
import re
from pathlib import Path

from rapidocr_onnxruntime import RapidOCR

# 引擎只初始化一次（模型加载要 1~2 秒，每次请求重建太浪费）。
# 模块级变量 + 判断 None 的套路，同款见 vision.py 的模块级缓存。
_engine: RapidOCR | None = None


def get_engine() -> RapidOCR:
    global _engine
    if _engine is None:
        # det_limit_side_len：检测前把最长边缩到多少像素。默认 736 太狠——
        # 手机截图被缩到 37%，小字直接漏检（用户实测"漏字"）。1280 是
        # 速度和小字检出的平衡点；坐标会自动换算回原图尺寸，不影响配对
        _engine = RapidOCR(det_limit_side_len=1280)
    return _engine


def detect_text(img_path: Path | str) -> list[dict]:
    """检测图片里所有文字。
    返回按"从上到下、从左到右"排序的列表，每项：
    {"text": 识别出的文字, "box": [[x,y],[x,y],[x,y],[x,y]] 四点坐标,
     "score": 置信度 0~1}
    没检测到文字返回空列表。"""
    result, _elapse = get_engine()(str(img_path))
    if not result:
        return []
    # result 是 [(box, text, score), ...]，拆成好读的字典
    items = [{"text": t, "box": b, "score": s} for b, t, s in result]
    # 按左上角排序：y 优先、x 其次——跟人的阅读顺序一致，
    # 后面翻译打包、译文拆回时才能跟气泡一一对上，不串位
    items.sort(key=lambda it: (min(p[1] for p in it["box"]),
                               min(p[0] for p in it["box"])))
    return items


def _rect_of(box: list[list[float]]) -> tuple[int, int, int, int]:
    """四点坐标 → 外接矩形 (left, top, right, bottom) —— 同款 render.py 的 _bbox_of"""
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def union_boxes(boxes: list[list[list[float]]]) -> list[list[float]]:
    """多个四点框 → 一个外接矩形（输出仍是四点框）。
    气泡的画字框 = 认领它的 OCR 片段框的外接矩形。
    这里只管"拼框"这一个纯几何活，翻译分组以视觉大模型为准。"""
    rects = [_rect_of(b) for b in boxes]
    l = min(r[0] for r in rects)
    t = min(r[1] for r in rects)
    r = max(r[2] for r in rects)
    b = max(r[3] for r in rects)
    return [[l, t], [r, t], [r, b], [l, b]]


def count_rows(boxes: list[list[list[float]]]) -> int:
    """数出这些片段框一共占几行（纵向无重叠的算新一行）。
    译文按这个行数平衡换行（render.py 的 _wrap_balanced），
    跟原文的行结构对齐——大模型译文不分行，本地行数补上。"""
    rows = 0
    prev_bottom: float | None = None
    for box in sorted(boxes, key=lambda b: min(p[1] for p in b)):
        top = min(p[1] for p in box)
        bottom = max(p[1] for p in box)
        if prev_bottom is None or top >= prev_bottom:
            rows += 1
            prev_bottom = bottom
        else:
            prev_bottom = max(prev_bottom, bottom)
    return rows


# --------------------------------------------------------------------------- 本地定位

# 倾斜角度上限（度）：超过它的文字（斜体效果音、竖排台词）不擦不画、原样保留
MAX_TILT_DEG = 20.0


def _tilt_deg(box: list[list[float]]) -> float:
    """四点框的倾斜角（度）：横排≈0，竖排≈90。

    不猜点的顺序（RapidOCR 不保证第几个点是哪条边）——按几何自己找：
      ① 框比宽高得多 = 竖排文字 → 直接算 90°（跳过嵌字）
      ② 横排：y 最小的两个点连成的边就是"上边"，它跟水平线的夹角 = 倾斜"""
    l, t, r, b = _rect_of(box)
    if (b - t) > 1.5 * (r - l):
        return 90.0
    pts = sorted(box, key=lambda p: p[1])
    (x1, y1), (x2, y2) = pts[0], pts[1]
    return abs(math.degrees(math.atan2(y2 - y1, x2 - x1)))


def _near(box_a: list[list[float]], box_b: list[list[float]]) -> bool:
    """两个框像不像同一个气泡里的相邻行：
    横向有重叠（并排关系）+ 竖向间隙小于 1.5 倍行高。"""
    la, ta, ra, ba = _rect_of(box_a)
    lb, tb, rb, bb = _rect_of(box_b)
    x_overlap = min(ra, rb) - max(la, lb)
    if x_overlap < 0.3 * min(ra - la, rb - lb):
        return False
    gap = max(tb - ba, ta - bb)
    return gap < 1.5 * max(ba - ta, bb - tb)


def _pos_tag(box: list[list[float]], w: int, h: int) -> str:
    """气泡位置标签（3×3 九宫格）："上部偏左"这类。
    编号清单里的文字可能重复（两个气泡都说"ゴゴゴ"），光看字分不清谁是谁——
    加上位置标签，模型才能把编号对上图里的气泡。由框算出来，不是由字算出来。"""
    cx = (min(p[0] for p in box) + max(p[0] for p in box)) / 2
    cy = (min(p[1] for p in box) + max(p[1] for p in box)) / 2
    vy = "上部" if cy < h / 3 else ("下部" if cy > h * 2 / 3 else "中部")
    if cx < w / 3:
        vx = "偏左"
    elif cx > w * 2 / 3:
        vx = "偏右"
    else:
        vx = ""
    return f"{vy}{vx}"


def _norm(s: str) -> str:
    """配对前的文字规整：去掉所有空白 + 转小写。
    模型抄的原文和 OCR 认的字差个空格、大小写，都不该影响配对。"""
    return re.sub(r"\s+", "", s).lower()


def _sim(a: str, b: str) -> float:
    """difflib 相似度 0~1：两个字符串有多像。"""
    return difflib.SequenceMatcher(None, a, b).ratio()


def pair_entries(entries: list[dict], items: list[dict]) -> list[dict]:
    """把模型答卷配回 OCR 片段（第一版同款 difflib 配对 + 邻居限制）。

    模型按"一个气泡一条"报 original+translation，本地要回答的问题是：
    "这条译文应该画到哪些 OCR 片段的框里？"
    配对规则（贪心，一条条认领）：
      ① 打分：跟 original 完全相同 1.0；是 original 的子串 0.9（子串越长
         越像气泡本行，同分时优先长的）；都不是 → difflib 相似度兜底
      ② 最高分（≥0.5）的片段当"锚"——认领它，框就是气泡框的起点
      ③ 其余片段必须是锚的"邻居"（同一气泡的相邻行）才认领——
         短片段（"え"这类）是整页好多原文的子串，不限制邻居就会把
         别的气泡的字吸进一个大框，译文画到两框之间乱飘（用户实测）
      ④ 一个片段只能被一条译文认领——字字相同的片段不会都抢给第一个气泡

    返回 [{original, translation, boxes: [认领到的片段四点框...]}]
    没认领到任何片段的条目被丢掉（画不了位置，只擦不画）。"""
    claimed: set[int] = set()
    out: list[dict] = []
    for e in entries:
        norm_og = _norm(e.get("original", ""))
        if not norm_og:
            continue
        # ① 给所有没被认领的片段打分
        cands: list[tuple[float, int, int]] = []   # (分数, 文字长度, 下标)
        for i, it in enumerate(items):
            if i in claimed:
                continue
            ni = _norm(it["text"])
            if not ni:
                continue
            if ni == norm_og:
                score = 1.0
            elif ni in norm_og:
                score = 0.9
            else:
                score = _sim(ni, norm_og)
            if score >= 0.5:
                cands.append((score, len(ni), i))
        if not cands:
            continue
        # ② 分数高、文字长的当锚（一个气泡的第一行）
        cands.sort(reverse=True)
        _, _, anchor_i = cands[0]
        claimed.add(anchor_i)
        boxes = [items[anchor_i]["box"]]
        # ③ 锚的邻居才能进同一个框（同气泡相邻行）
        for score, _len, i in cands[1:]:
            if score >= 0.9 and _near(union_boxes(boxes), items[i]["box"]):
                boxes.append(items[i]["box"])
                claimed.add(i)
        out.append({**e, "boxes": boxes})
    return out