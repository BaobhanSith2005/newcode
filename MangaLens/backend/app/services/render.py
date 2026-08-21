"""译文画回气泡 —— PIL 画字：自动换行 + 字号自适应。

把译文塞进气泡 = 两个循环（像往行李箱装衣服）：
  ① 换行循环：单位（中文逐字/英文整词）一个个往行里装，装不下就换行
  ② 字号循环：字号从大到小试，直到所有行都装得进气泡，装不下换小一号
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 中文字体候选：微软雅黑最常见，没有就依次退（不同 Windows 字体略有差异）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",   # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf", # 黑体
    r"C:\Windows\Fonts\simsun.ttc", # 宋体
]
MIN_FONT = 10  # 最小字号：再小看不清，宁可略微超框
# 原文行高 → 译文初始字号的系数：跟第一版成品同一个系数
# （0.55 × 行框高）——用户实测三张图里第一版这个字号最合适、整页统一。
# 觉得字偏大/偏小就调这里
ORIG_H_SCALE = 0.55

# 换行单位：连续英文/数字算一个单位（不拆散单词），其余每个字符一个单位
_UNITS_RE = re.compile(r"[A-Za-z0-9]+|.", re.S)


def get_font(size: int) -> ImageFont.FreeTypeFont:
    """按字号加载中文字体（Windows 自带，不用另装）。"""
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"找不到中文字体，试过: {FONT_CANDIDATES}")


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    """把文字按最大宽度切行：装得下就继续装，装不下就换行。
    译文里自带的换行符保留（模型偶尔输出两行对话）。"""
    lines: list[str] = []
    cur = ""
    for unit in _UNITS_RE.findall(text):
        if unit == "\n":
            lines.append(cur)
            cur = ""
            continue
        cand = cur + unit
        if cur and font.getbbox(cand)[2] - font.getbbox(cand)[0] > max_w:
            lines.append(cur)  # 装不下了，这一行封口
            cur = unit
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def _wrap_balanced(text: str, font: ImageFont.FreeTypeFont, max_w: float,
                   n_lines: int) -> list[str]:
    """把译文平均铺成 n 行（每行尽量不超宽）——跟原文的行数对齐。
    大模型的译文往往不分行，本地按 OCR 拆出的原文行数来分：
    像报纸排版，先按总字数均分每行拿多少字，再按实际宽度微调。
    （译文自带的换行符忽略——本地行结构才是准的）"""
    units = [u for u in _UNITS_RE.findall(text) if u != "\n"]
    if not units:
        return [""]
    lines: list[str] = []
    start = 0
    for li in range(n_lines):
        remain = n_lines - li - 1
        # 这一行最多能拿的单位数 = 总数 - 后面每行至少留 1 个
        limit = len(units) - remain if remain else len(units)
        cur = ""
        i = start
        while i < min(start + limit, len(units)):
            cand = cur + units[i]
            if cur and font.getbbox(cand)[2] - font.getbbox(cand)[0] > max_w:
                break  # 这一行装满了，剩下的留给后面的行
            cur = cand
            i += 1
        lines.append(cur)
        start = i
    # 译文比原文短时（常见：中文更紧凑）会剩空行，去掉
    return [l for l in lines if l] or [""]


def _bbox_of(points: list[list[float]]) -> tuple[int, int, int, int]:
    """四点坐标 → 外接矩形 (left, top, right, bottom)。
    画字只需要矩形范围，不用管四点原来的形状。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def render_texts(img: Image.Image, items: list[dict]) -> Image.Image:
    """把译文画回气泡。items = [{"text": 译文, "box": 四点坐标}, ...]。
    直接改在传入的图上（也返回它，方便链式调用）。
    v1 只画横排；日漫竖排气泡后续版本再说。"""
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    for it in items:
        text = it["text"].strip()
        if not text:
            continue
        left, top, right, bottom = _bbox_of(it["box"])
        max_w = right - left
        max_h = bottom - top
        # 原文行数（本地 OCR 按行拆出来的）：译文按这个行数平衡换行——
        # 大模型译文不分行也没关系，本地行结构补上
        lines_target = it.get("lines")

        # 字号起点：有原文行高就照原文匹配（整页统一，跟原文字一样大），
        # 没有（旧调用方）退回"气泡高度 55%"的旧规则。
        # 起点只是试穿的第一件衣服：装不下照样往下缩号
        orig_h = it.get("orig_h")
        size = max(MIN_FONT, int(orig_h * ORIG_H_SCALE) if orig_h
                   else int(max_h * 0.55))
        while size >= MIN_FONT:
            font = get_font(size)
            if "\n" in text:
                # 模型自己分了行（译文带 \n）：尊重模型的分行，
                # 本地只兜底"超宽才断行"（_wrap 会保留译文里的换行符）
                lines = _wrap(text, font, max_w)
            elif lines_target:
                lines = _wrap_balanced(text, font, max_w, lines_target)
            else:
                lines = _wrap(text, font, max_w)
            line_h = sum(font.getmetrics())  # (ascent, descent) 相加 = 行高
            # 平衡换行的最后一行可能超宽（译文太长装不进指定行数），
            # 超宽也一样缩号重试
            fits_w = all(font.getbbox(l)[2] - font.getbbox(l)[0] <= max_w
                         for l in lines)
            if line_h * len(lines) <= max_h and fits_w:
                break
            size -= 2
        else:
            # while 没 break 走到这：最小号都装不下，就用最小号（宁可超框）
            font = get_font(MIN_FONT)
            if "\n" in text:
                lines = _wrap(text, font, max_w)
            elif lines_target:
                lines = _wrap_balanced(text, font, max_w, lines_target)
            else:
                lines = _wrap(text, font, max_w)

        # 画：整块垂直居中，每行水平居中
        line_h = sum(font.getmetrics())
        y = top + (max_h - line_h * len(lines)) / 2
        for line in lines:
            l, _t, r, _b = font.getbbox(line)
            # 水平居中要减去 bbox 的左边偏移（有些字形自带左侧留白）
            x = left + (max_w - (r - l)) / 2 - l
            draw.text((x, y), line, font=font, fill=(0, 0, 0))
            y += line_h
    return img