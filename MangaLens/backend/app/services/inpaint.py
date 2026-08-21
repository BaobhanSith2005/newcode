"""气泡区域擦除 —— ONNX 版 LaMa 封装（GPU 加速，CPU 自动回退）+ 白板涂白 paint_white。

LaMa = 三星开源的"大遮罩修复"模型：把图上遮住的地方用周围内容"脑补"出来。
我们用它擦掉气泡里的原文：OCR 坐标 → 黑白遮罩 → 模型补背景。

输入格式（g-ronimo/lama 的 ONNX 导出）：
  [1, 4, H, W]：前3通道 = 遮罩区清零的 RGB 图（0~1），第4通道 = 遮罩（0/1）
  宽高必须是 32 的倍数 → 先 pad 到倍数，推理完再裁回来
输出：[1, 3, H, W] RGB（0~1）
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFilter

# 模型文件位置：backend/models/lama.onnx（你从浏览器下载的那个，名字改成这个）
MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "models" / "lama.onnx"
PAD_UNIT = 32  # 模型要求宽高是 32 的倍数

_session: ort.InferenceSession | None = None


def get_session() -> ort.InferenceSession:
    """加载模型（只加载一次，同款 ocr.py 的 get_engine）。
    providers 列表的妙处：CUDA 优先，没有 GPU 自动回退 CPU——
    代码不用写死，换机器也能跑。"""
    global _session
    if _session is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"找不到 LaMa 模型 {MODEL_PATH}，请先从 "
                "https://huggingface.co/g-ronimo/lama/resolve/main/lama_fp16.onnx "
                "下载并改名成 lama.onnx")
        _session = ort.InferenceSession(
            str(MODEL_PATH),
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    return _session


def _mask_from_boxes(size: tuple[int, int],
                     boxes: list[list[list[float]]]) -> Image.Image:
    """把 OCR 四点坐标画成黑白遮罩：白(255) = 要擦掉的区域。
    画完用 MaxFilter 扩一圈：OCR 框和文字边缘贴合不严，留 5 像素余量，
    擦得更干净（MaxFilter 就是图像学里的"膨胀"操作）。"""
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        pts = [(float(x), float(y)) for x, y in box]
        draw.polygon(pts, fill=255)
    return mask.filter(ImageFilter.MaxFilter(5))


def inpaint(img: Image.Image, boxes: list[list[list[float]]]) -> Image.Image:
    """擦除图片中 boxes 圈出的所有区域，返回擦好的 PIL 图。
    boxes 为空直接返回原图——没有文字就不用动模型。"""
    if not boxes:
        return img

    img = img.convert("RGB")
    w, h = img.size
    mask = _mask_from_boxes((w, h), boxes)

    # pad 到 32 的倍数（模型硬性要求），记住补了多少，最后裁回来
    pad_r = (PAD_UNIT - w % PAD_UNIT) % PAD_UNIT
    pad_b = (PAD_UNIT - h % PAD_UNIT) % PAD_UNIT
    img_p = np.pad(np.asarray(img).astype("float32") / 255.0,
                   ((0, pad_b), (0, pad_r), (0, 0)))
    mask_p = np.pad(np.asarray(mask).astype("float32") / 255.0,
                    ((0, pad_b), (0, pad_r)))

    # 拼成模型要的 [1, 4, H, W]：前3通道 = 遮罩区清零的图，第4通道 = 遮罩
    masked = img_p * (1 - mask_p[..., None])
    x = np.concatenate([masked, mask_p[..., None]], axis=2)
    x = x.transpose(2, 0, 1)[None].astype("float32")

    sess = get_session()
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0]

    # 输出 [1,3,H,W] → 裁掉 pad → 转回 PIL
    out = out[0].transpose(1, 2, 0)[:h, :w]
    out_img = Image.fromarray((np.clip(out, 0, 1) * 255).astype("uint8"))

    # 只把遮罩区域换成模型补的结果，其余像素保持原样——
    # paste 的第三参数 mask 就是这个意思：白的地方用新图，黑的地方不动。
    # 这样模型对无关区域产生的细微色差不会影响整张图。
    img.paste(out_img, (0, 0), mask)
    return img


def paint_white(img: Image.Image, boxes: list[list[list[float]]]) -> Image.Image:
    """白板方案：跳过 LaMa，直接把文字区域涂成白色（测试提速用）。
    跟 inpaint() 用同一套遮罩（白 = 要盖掉的区域），只是把"模型脑补背景"
    换成"盖一层白色"：漫画气泡多数本来就是白底，效果基本看不出来；
    彩色/花纹背景会露出白色补丁——所以定位是测试模式，正式效果用 inpaint()。
    boxes 为空直接返回原图——没有文字就不用动。"""
    if not boxes:
        return img
    img = img.convert("RGB")
    mask = _mask_from_boxes(img.size, boxes)
    # paste 的第三参数 mask：白的地方盖白色，黑的地方不动——同款 inpaint() 最后一步
    img.paste(Image.new("RGB", img.size, (255, 255, 255)), (0, 0), mask)
    return img