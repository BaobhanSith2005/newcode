"""小说 txt 翻译流水线：读 → 切块 → 逐块翻译 → 拼回写文件。"""

from pathlib import Path

from .epub import translate_epub_file
from .vision import translate_text

CHUNK_CHARS = 3000  # 每块最多约3000字：太大超模型上下文，太小上下文割裂


def split_chunks(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """按段落切块。
    策略：空行分段，然后小段打包，塞满 limit 前不换块。
    宁可块小一点，也不把一句话掰两半。"""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for p in paras:
        if cur and size + len(p) > limit:
            chunks.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(p)
        size += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def translate_txt_file(in_path: Path, out_path: Path, style: str = "文学风") -> str | None:
    """整本翻译。返回 None = 成功；返回字符串 = 错误原因（含哪块挂了）。"""
    try:
        text = in_path.read_text("utf-8")
    except UnicodeDecodeError:
        # 中文小说 txt 常见 gbk 编码，utf-8 读不了就换 gbk
        text = in_path.read_text("gbk", errors="ignore")

    chunks = split_chunks(text)
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        try:
            parts.append(translate_text(chunk, style=style))
        except Exception as exc:  # noqa: BLE001 哪块挂了要说清楚
            return f"第 {i}/{len(chunks)} 块翻译失败: {type(exc).__name__}: {exc}"

    out_path.write_text("\n\n".join(parts), "utf-8")
    return None


def translate_doc_file(in_path: Path, out_path: Path, file_type: str,
                       style: str = "文学风") -> str | None:
    """总入口：按文件类型分派到对应流水线。
    txt 走纯文本切块，epub 走保结构翻译。以后再加格式（比如 pdf），
    只在这里加一行分支，接口和后台任务都不用动——这就是分派器的价值。"""
    if file_type == "epub":
        return translate_epub_file(in_path, out_path, style=style)
    return translate_txt_file(in_path, out_path, style=style)
