"""epub 保结构翻译 —— MangaLens 目前最复杂的一块，但只用 Python 自带工具。

epub 本质 = zip 压缩包，里面是 xhtml 网页文件。
翻译策略（保结构）：
  解包 → 找 .xhtml → 按"块级元素"抽文字 → 打包成组批量翻译
       → 译文塞回原标签内部 → 重新打包。
标签和插图（<img>）原样保留，只换文字。带插图的块用"占位符法"：
  <img> 换成 [[IMG0]] 再送去翻译，模型不动占位符，译文回来再换回原图。

块边界用正则精确匹配（试过 HTMLParser 的 getpos 定位，有 ±1 误差且
不同环境行为不一致——保结构最怕位置错一位，弃用）。
"""
from __future__ import annotations

import html as html_lib
import re
import zipfile
from pathlib import Path

from .vision import translate_text

CHUNK_CHARS = 3000  # 同款 doc.py 的切块上限

# 块级元素 = "翻译的最小单位"。一段一段翻，而不是一字一字翻。
BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6",
              "li", "blockquote", "td", "th", "dd", "dt", "figcaption")
# 匹配 "<p ...>内容</p>" 整块：开标签和闭标签必须同名（(?P=tag) 回引用）。
# .*? 惰性匹配到第一个同名闭标签；DOTALL 让块可以跨行。
BLOCK_RE = re.compile(
    r"<(?P<tag>" + "|".join(BLOCK_TAGS) + r")\b[^>]*>"
    r"(?P<inner>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL)

# <img> 标签（含自闭合 <img .../>）。[^>]*? 匹配到第一个 > 为止。
IMG_RE = re.compile(r"<img\b[^>]*?>", re.IGNORECASE)
# 图片占位符：送给模型前替换 <img>，模型原样保留，译文回来再换回图片
IMG_PH = "[[IMG{}]]"
IMG_PH_RE = re.compile(r"\[\[IMG\d+\]\]")


def _extract_blocks(html_text: str) -> list[dict]:
    """按块级标签精确切块。返回的块包含：
    tag, start, end（标签内部的范围）, imgs, masked。
    start/end 指向"标签内部"：替换时外面的 <p></p> 原样保留——保结构的关键。"""
    blocks: list[dict] = []
    for m in BLOCK_RE.finditer(html_text):
        inner = m.group("inner")
        text = " ".join(re.sub(r"<[^>]*?>", " ", inner).split())
        if not text:  # 空块 / 纯图片块不翻
            continue
        imgs = IMG_RE.findall(inner)
        if imgs:
            # <img> 换成占位符：模型只看到"文字+[[IMG0]]"，插图位置不丢
            segs = [re.sub(r"<[^>]*?>", "", s).strip() for s in IMG_RE.split(inner)]
            masked = "".join(t + (IMG_PH.format(i) if i < len(imgs) else "")
                             for i, t in enumerate(segs))
        else:
            masked = text
        blocks.append({"tag": m.group("tag").lower(), "imgs": imgs,
                       "start": m.start("inner"), "end": m.end("inner"),
                       "masked": masked})
    return blocks


def _translate_blocks(blocks: list[dict], style: str) -> tuple[str | None, int]:
    """把块打包成≤3000字的组，逐组调大模型，译文按空行拆回。
    带插图的块也参与（送出去的文字里是占位符）；占位符对不上的块保留原文。
    成功后往每个块里写 b["translation"]。
    返回 (错误信息或None, 保留原文的块数)。"""
    kept = 0

    # 打包：跟 doc.py 切块同款思路，只是单位从"段"变成"块"
    groups: list[list[dict]] = []
    cur: list[dict] = []
    size = 0
    for b in blocks:
        if cur and size + len(b["masked"]) > CHUNK_CHARS:
            groups.append(cur)
            cur, size = [], 0
        cur.append(b)
        size += len(b["masked"])
    if cur:
        groups.append(cur)

    for group in groups:
        joined = "\n\n".join(b["masked"] for b in group)
        try:
            result = translate_text(joined, style=style)
        except Exception as exc:  # noqa: BLE001
            return f"翻译失败: {type(exc).__name__}: {exc}", kept
        parts = [p.strip() for p in re.split(r"\n\s*\n", result) if p.strip()]
        if len(parts) == len(group):
            for b, part in zip(group, parts):
                if b["imgs"] and len(IMG_PH_RE.split(part)) != len(b["imgs"]) + 1:
                    kept += 1  # 模型弄丢了占位符 → 这一块保留原文（优雅降级）
                else:
                    b["translation"] = part
        else:
            # 段落数对不上（模型偶尔合并/多分）→ 这组保留原文，不硬套
            kept += len(group)
    return None, kept


def translate_epub_file(in_path: Path, out_path: Path, style: str = "文学风") -> str | None:
    """整本 epub 翻译。返回 None = 成功；返回字符串 = 错误原因。"""
    try:
        with zipfile.ZipFile(in_path) as zin:
            names = zin.namelist()
            html_names = [n for n in names
                          if Path(n).suffix.lower() in (".xhtml", ".html", ".htm")]
            if not html_names:
                return "epub 里没找到正文网页文件"

            new_content: dict[str, bytes] = {}
            for name in html_names:
                html_text = zin.read(name).decode("utf-8", errors="ignore")
                blocks = _extract_blocks(html_text)
                if not blocks:
                    new_content[name] = zin.read(name)
                    continue
                err, _kept = _translate_blocks(blocks, style)
                if err:
                    return f"{name}: {err}"

                # 从后往前替换——前面的偏移不会被后面的替换搞乱
                for b in reversed(blocks):
                    if "translation" not in b:
                        continue
                    if b["imgs"]:
                        # 占位符换回原图，其余文字转义——图一个不少地插回原位
                        segs = IMG_PH_RE.split(b["translation"])
                        safe = "".join(html_lib.escape(s) + img
                                       for s, img in zip(segs, b["imgs"]))
                        safe += html_lib.escape(segs[-1])
                    else:
                        safe = html_lib.escape(b["translation"])  # 防 < > & 破坏标签
                    html_text = html_text[:b["start"]] + safe + html_text[b["end"]:]
                new_content[name] = html_text.encode("utf-8")

            with zipfile.ZipFile(out_path, "w") as zout:
                # epub 规范：mimetype 必须第一个写入且不压缩
                if "mimetype" in names:
                    zout.writestr("mimetype", zin.read("mimetype"),
                                  compress_type=zipfile.ZIP_STORED)
                for name in names:
                    if name == "mimetype":
                        continue
                    data = new_content[name] if name in new_content else zin.read(name)
                    zout.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
        return None
    except zipfile.BadZipFile:
        return "不是有效的 epub 文件（解包失败）"