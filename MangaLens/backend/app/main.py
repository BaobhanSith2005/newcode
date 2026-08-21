"""MangaLens 后端入口 —— 异步版。

同款对照：AIRoomBuilder/backend/app/main.py（入口结构）
         + AIRoomBuilder/backend/app/api/images.py（上传+后台任务+轮询）

完整流程：
  前端 POST /api/images/upload → 立刻返回图片ID（0.1秒）
  后端后台任务按板块分派：漫画图（不传batch_id）→ 直接嵌字；书页图 → 视觉翻译
  前端 GET /api/images/{id}/result 轮询，直到 status=done
"""
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image as PILImage
from sqlalchemy.orm import Session

from .api.batches import router as batches_router
from .api.docs import router as docs_router
from .api.monitor import router as monitor_router
from .config import UPLOAD_DIR, settings
from .db import SessionLocal, get_db, init_db
from .models import Batch, Image
from .schemas import ImageOut
from .services.inpaint import inpaint, paint_white
from .services.ocr import (MAX_TILT_DEG, _tilt_deg, count_rows, detect_text,
                           pair_entries, union_boxes)
from .services.render import render_texts
from .services.timing import (checkpoint, elapsed_seconds, end_task,
                              start_task)
from .services.vision import analyze_image, render_translate

# 启动时自动建表 —— 同款见 AIRoomBuilder main.py 第42-45行 lifespan
@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="漫画 / 小说识图翻译 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 把批次接口插座插进应用 —— 同款见 AIRoomBuilder main.py 第64行 include_router
app.include_router(batches_router)
# 文本文件翻译（小说 txt）插座
app.include_router(docs_router)
# 计时台账插座（测试阶段监控用）
app.include_router(monitor_router)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_BYTES = 20 * 1024 * 1024

# 嵌字任务的总时限（秒）——用户拍板：超时直接终止整个任务。
# 从 90 秒（1分钟半）放宽到 180 秒（3分钟）：模型回话慢也给它等完
# （用户实测 id=18 连等两个 45 秒都没等到回话，ReadTimeout 挂掉）。
# 检查点：OCR 后 / 翻译后 / 擦除后。
# 注意：LaMa 擦除本身就好几分钟，正式换回 lama 前要先调大这个值
TASK_BUDGET_SECONDS = 180


# --------------------------------------------------------------------------- 后台任务

def _run_translate(image_id: int) -> None:
    """后台任务：调大模型翻译，把状态写回数据库。
    同款见 AIRoomBuilder/backend/app/api/images.py 第23-42行 _run_analysis。
    注意：必须新建 Session——请求作用域的 Session 此时已关闭。"""
    db = SessionLocal()
    try:
        img = db.get(Image, image_id)
        if not img:
            return
        img.status = "running"
        img.progress = "云端翻译中…"
        db.commit()
        start_task(image_id, "书页翻译")
        try:
            result = analyze_image(img.path, style=img.style)
            checkpoint(image_id, "云端翻译")
            img.result = json.dumps(result, ensure_ascii=False)
            img.status = "done"
            img.error = None
            img.progress = "完成"
        except Exception as exc:  # noqa: BLE001 失败信息要能回传给前端
            img.status = "failed"
            img.error = f"{type(exc).__name__}: {exc}"
            img.progress = "失败"
        end_task(image_id, img.status)
        db.commit()
    finally:
        db.close()


def _timeout_fail(img: Image, image_id: int, db: Session) -> None:
    """任务超时：按用户拍板直接终止整个任务（批量处理等不起）。
    写 failed + 中文报错（带总耗时）+ 封计时台账，一条龙。
    error 里的耗时跟 result 接口 progress 里的"已过 X 秒"同一个来源。"""
    img.status = "failed"
    el = elapsed_seconds(image_id)
    img.error = (f"任务超时（超过 {TASK_BUDGET_SECONDS} 秒，"
                 f"共耗时 {int(el)} 秒），已终止" if el is not None
                 else f"任务超时（超过 {TASK_BUDGET_SECONDS} 秒），已终止")
    img.progress = "失败"
    end_task(image_id, "failed")
    db.commit()


# --------------------------------------------------------------------------- 后台任务

def _run_render(image_id: int) -> None:
    """后台任务：漫画嵌字四步流水线 OCR → 翻译 → 擦除 → 画字。
    同款 _run_translate 的结构：新建 Session、状态机 running→done/failed。
    漫画图上传后直接走这里——不做"先视觉翻译再嵌字"两段式：
    用户要的就是成品图，对照表没人看，两段式又慢又费钱，
    所以大模型只在"翻译"这一步出现（口语风）：独立看原图翻（译文以模型为准）；
    定位是本地工作（用户拍板）：difflib 配对（第一版同款）——
    模型答卷的 original 认领 OCR 片段，认领到的框拼成气泡大框。
    状态机也复用 status/error：一张图同一时间只跑一个任务，一套状态就够了。"""
    db = SessionLocal()
    try:
        img = db.get(Image, image_id)
        if not img:
            return
        img.status = "running"
        img.error = None
        img.progress = "① OCR 识别文字中…"
        db.commit()
        start_task(image_id, "嵌字")
        # 整条流水线的生死线：OCR + 翻译 + 擦除 + 画字都在时限内跑完，
        # 超时按用户拍板直接终止（检查点见下方 ①②③ 注释）
        deadline = time.monotonic() + TASK_BUDGET_SECONDS
        try:
            # ① OCR：拿到 (文字, 四点坐标)，ocr.py 已按阅读顺序排好。
            #    注意 OCR 是本地模型，只认字不翻译，这一步不花钱
            items = detect_text(img.path)
            # ①.5 滤掉纯数字/符号的碎渣（状态栏时间、电量、页码这类）——
            #    不是气泡台词，翻译了也会画在奇怪的地方。
            #    正则范围：英文字母/日文假名/中日韩汉字
            _letter_re = re.compile(r"[A-Za-z぀-ヿ一-鿿가-힯]")
            items = [it for it in items if _letter_re.search(it["text"])]
            if not items:
                img.status = "failed"
                img.error = "没检测到可嵌的文字"
                img.progress = "失败"
                end_task(image_id, "failed")
                db.commit()
                return
            # ①.7 倾斜的文字（斜体效果音、竖排台词）不擦不画、原样保留——
            #    横排译文画到斜框上只会更乱（用户反馈"倾斜的处理得不够好"）。
            #    跳过比画坏强：成品图里它们保持原样
            items_ok = [it for it in items
                        if _tilt_deg(it["box"]) <= MAX_TILT_DEG]
            if not items_ok:
                img.status = "failed"
                img.error = "文字全是倾斜的（竖排/斜体），没有可嵌的水平文字"
                img.progress = "失败"
                end_task(image_id, "failed")
                db.commit()
                return
            skipped = len(items) - len(items_ok)
            checkpoint(image_id, "OCR 识别")
            # 检查点①：OCR 之后、调模型之前
            if time.monotonic() >= deadline:
                _timeout_fail(img, image_id, db)
                return
            # ② 翻译（唯一的大模型调用）——第一版定稿方案（用户拍板回归）：
            #    模型独立看原图，一个气泡一条（original+translation），
            #    定位是本地工作：difflib 配对认领 OCR 片段框。
            #    不补翻、不判死（用户拍板"取消让大模型重试的步骤，
            #    至少要出图"）：模型漏了原文就只擦不画、照样出图，
            #    完成进度里上报漏了几条、漏的是哪些字
            img.progress = "② 云端翻译中（最久的一步）…"
            db.commit()
            vision_items = render_translate(img.path, items_ok)
            checkpoint(image_id, "云端翻译")
            # 检查点②：翻译之后（网关慢/重试会吃掉大把时间）
            if time.monotonic() >= deadline:
                _timeout_fail(img, image_id, db)
                return
            if not vision_items:
                img.status = "failed"
                img.error = "大模型没有返回翻译结果，重新发起一次"
                img.progress = "失败"
                end_task(image_id, "failed")
                db.commit()
                return
            # ③ 本地定位 ④ 译文画回（用户定的原则：翻译归模型、定位归本地）：
            #    定位 = 第一版同款的 difflib 配对：模型答卷的 original 认领
            #    OCR 片段（片段是 original 的子串 → 满分；认领不到再按相似度
            #    ≥0.5 兜底），认领到的片段框拼成气泡大框。
            #    擦除 = 全擦所有水平片段小框（第一版思路：贴着文字、不碰漫画线条；
            #    没被认领的片段 = 噪音也擦——第一版就是全擦才擦得干净）。
            #    倾斜片段在 ①.7 已剔除，不擦不画
            erase_boxes = [it["box"] for it in items_ok]
            paired = pair_entries(vision_items, items_ok)
            render_items: list[dict] = []
            for p in paired:
                bubble_box = union_boxes(p["boxes"])
                # 原文行高 = 认领片段框的平均高度——译文按它匹配字号
                # （render.py 用 ORIG_H_SCALE 打折），整页字号跟原文一致
                orig_h = sum(max(pt[1] for pt in b) - min(pt[1] for pt in b)
                             for b in p["boxes"]) / len(p["boxes"])
                render_items.append({
                    "text": p["translation"],
                    "box": bubble_box, "orig_h": round(orig_h),
                    # 换行目标：原文占几行铺几行（render.py 平衡换行）
                    "lines": count_rows(p["boxes"]),
                })
            if vision_items and not render_items:
                img.status = "failed"
                img.error = "模型答卷没能配上任何 OCR 片段（原文对不上），重新发起一次"
                img.progress = "失败"
                end_task(image_id, "failed")
                db.commit()
                return
            # 没被认领的片段：漏译只擦不画，完成进度里上报（用户拍板）
            claimed_boxes = {tuple(tuple(pt) for pt in b)
                             for p in paired for b in p["boxes"]}
            missing = [it["text"] for it in items_ok
                       if tuple(tuple(pt) for pt in it["box"])
                       not in claimed_boxes]
            unclaimed = len(missing)
            # 白板模式（测试提速）：跳过 LaMa 直接涂白，几毫秒完事；
            # 正式效果在 .env 里加 ERASE_MODE=lama 切回来
            if settings.erase_mode == "white":
                img.progress = "③ 白板涂白原文中…"
                db.commit()
                image = PILImage.open(img.path)
                image = paint_white(image, erase_boxes)
                checkpoint(image_id, "白板涂白")
            else:
                img.progress = "③ LaMa 擦除原文中…"
                db.commit()
                image = PILImage.open(img.path)
                image = inpaint(image, erase_boxes)
                checkpoint(image_id, "LaMa 擦除")
            # 检查点③：擦除之后、画字之前
            if time.monotonic() >= deadline:
                _timeout_fail(img, image_id, db)
                return
            img.progress = "④ 译文嵌入画字中…"
            db.commit()
            image = render_texts(image, render_items)

            out = UPLOAD_DIR / f"render_{img.id}.png"
            image.save(out)
            checkpoint(image_id, "画字保存")
            img.rendered_path = str(out)
            img.status = "done"
            img.error = None
            if not unclaimed and not skipped:
                img.progress = "完成"
            else:
                parts = []
                if unclaimed:
                    # 漏译上报：报数量 + 具体是哪些字（最多列 5 条），
                    # 用户看进度就能判断漏的是台词还是 UI 噪音
                    shown = "、".join(missing[:5])
                    if unclaimed > 5:
                        shown += " 等"
                    parts.append(f"{unclaimed} 条未认领只擦不画：{shown}")
                if skipped:
                    parts.append(f"{skipped} 条倾斜文字原样保留")
                img.progress = f"完成（{'；'.join(parts)}）"
        except Exception as exc:  # noqa: BLE001 失败信息要能回传给前端
            img.status = "failed"
            # 失败也把总耗时附在 error 里——用户复制 result JSON 时一次带齐
            el = elapsed_seconds(image_id)
            img.error = (f"{type(exc).__name__}: {exc}"
                         + (f"，共耗时 {int(el)} 秒" if el is not None else ""))
            img.progress = "失败"
        end_task(image_id, img.status)
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- 接口

def _to_out(img: Image) -> ImageOut:
    """把数据库记录转成接口返回对象。
    数据库里 result 存的是 JSON 字符串（Text 列），返回前要 json.loads 转回字典。
    同款见 AIRoomBuilder/backend/app/api/images.py 第113-118行：
    存的时候 dumps（打包成字符串），取的时候 loads（解包回字典），一存一取对称。"""
    progress = img.progress or ""
    if img.status == "running":
        # 任务跑着的时候：把"已过多少秒"接在进度后面（只改返回内容，
        # 不动数据库）。用户每次刷新 result 都能看到最新耗时——
        # 复制 JSON 时时间信息就跟着走了
        el = elapsed_seconds(img.id)
        if el is not None:
            progress = f"{progress}（已过 {int(el)} 秒）"
    return ImageOut(
        id=img.id,
        batch_id=img.batch_id,
        filename=img.filename,
        order=img.order,
        status=img.status,
        error=img.error,
        progress=progress,
        result=json.loads(img.result) if img.result else None,
        # 漫画图（无批次散图 + 漫画批次的图）嵌字固定口语风——result 里就显示
        # 口语风，别显示数据库默认的"直译"（跟实际用的风格对不上）
        style=("口语风" if img.batch_id is None
               or (img.batch and img.batch.kind == "manga")
               else img.style),
        created_at=img.created_at,
    )


@app.get("/api/health", tags=["health"], summary="健康检查")
def health():
    # Key 的"指纹"：只露出首尾几位 + 总长度，方便核对 Key 有没有复制错/漏字符，
    # 又不把完整 Key 显示出来（API 文档人人能看，完整 Key 露出来就泄密了）
    key = settings.openai_api_key
    mask = (f"{key[:6]}…{key[-4:]}（共{len(key)}字符）"
            if len(key) >= 10 else "空或太短")
    return {
        "ok": True,
        "vision_provider": settings.resolved_provider(),
        "vision_model": settings.resolved_model(),
        "erase_mode": settings.erase_mode,
        "api_key_mask": mask,
        "note": "provider 为 mock 时使用内置数据，无需 API Key",
    }


@app.post("/api/images/upload", response_model=ImageOut, tags=["images"],
          summary="上传漫画/书页图片",
          description="保存图片并立即返回。后台按板块分派：漫画图（无批次或漫画批次）直接嵌字；小说批次书页图视觉翻译。用 result 接口轮询进度。",
          responses={400: {"description": "格式不支持或图片过大"}})
async def upload_image(
    background: BackgroundTasks,
    file: UploadFile = File(..., description="漫画/小说图片文件"),
    batch_id: int | None = Form(None, description="所属批次ID；小说书页图传，漫画图不传"),
    order: int = Form(0, description="批次内排序号（第几张）"),
    db: Session = Depends(get_db),
):
    # ① 校验格式 —— 同款见 AIRoomBuilder images.py 第61-67行
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的图片格式 {ext}，仅支持 {sorted(ALLOWED_EXT)}")

    # ①.5 带了 batch_id 就先验证批次存在 —— 不存在的批次不接图。
    #     顺便把批次对象拿到手：④ 分派要看 batch.kind 决定嵌字还是视觉翻译
    batch = db.get(Batch, batch_id) if batch_id is not None else None
    if batch_id is not None and batch is None:
        raise HTTPException(404, "批次不存在")

    # ② 保存图片 —— 同款见 AIRoomBuilder images.py 第65-70行
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "图片超过 20MB")

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(raw)

    # ③ 建数据库记录（status 默认 pending）
    img = Image(filename=file.filename or dest.name, path=str(dest))
    # 小说书页图：挂进批次 + 记页码顺序；漫画图不传 batch_id，保持"不属于任何批次"
    if batch_id is not None:
        img.batch_id = batch_id
        img.order = order

    db.add(img)
    db.commit()
    db.refresh(img)

    # ④ 挂后台任务，按板块分派 —— 同款见 AIRoomBuilder images.py 第91-92行
    #    漫画图（没传 batch_id 或属于漫画批次）：直接嵌字，一步出成品图
    #    小说批次书页图：视觉翻译出译文，供合成 txt 用
    if batch is None or batch.kind == "manga":
        background.add_task(_run_render, img.id)
    else:
        background.add_task(_run_translate, img.id)
    return _to_out(img)


@app.get("/api/images/{image_id}/result", response_model=ImageOut, tags=["images"],
         summary="轮询翻译结果",
         description="轮询直到 status=done；running 时 progress 字段显示进行到哪一步"
                     "（① OCR → ② 云端翻译 → ③ 擦除 → ④ 画字），failed 时 error 字段有原因。",
         responses={404: {"description": "图片不存在"}})
def get_result(image_id: int, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    return _to_out(img)

@app.get("/api/images/{image_id}/download", tags=["images"],
         summary="下载翻译对照txt",
         description="把翻译结果拼成对照txt，浏览器直接下载。",
         responses={404: {"description": "图片不存在"},
                    409: {"description": "还没翻译完或翻译失败"}})
def download_result(image_id: int, db: Session = Depends(get_db)):
    """文件下载接口。
    注意：这个功能 AIRoomBuilder 没有同款——它的前端自己渲染3D场景，
    不需要从后端下载文件。这是 MangaLens 第一个"返回文件"的接口。"""
    # ① 找记录 —— 同款见本文件 get_result 接口开头
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")

    # ② 没翻译完就不给下载。409 是新学的状态码：Conflict（冲突）
    #    = "你的请求本身没错，但现在状态不对，不能干这件事"
    #    注意：漫画图没有 result（直接嵌字），会被这里的 409 拦住——正常，
    #    漫画板块下载成品图走 render/download 接口，不经过这里
    if img.status != "done" or not img.result:
        raise HTTPException(409, f"当前状态 {img.status}，翻译完成(done)后才能下载")

    # ③ 从数据库取 result 字符串 → loads 解包成字典 → 拼成对照文本
    #    （存的时候 dumps、取的时候 loads，跟 _to_out 里一个套路）
    data = json.loads(img.result)
    lines: list[str] = []
    for item in data.get("texts", []):
        lines.append(item["original"])     # 原文一行
        lines.append(item["translation"])  # 译文一行
        lines.append("")                   # 空行分隔，好看

    # ④ 返回"文件"。之前所有接口返回的都是 JSON（字典），
    #    这次要返回纯文本，用 Response 手动指定内容+类型
    return Response(
        content="\n".join(lines),                        # 拼好的整篇文本
        media_type="text/plain; charset=utf-8",          # 告诉浏览器：这是文本文件
        headers={
            # attachment = "附件"：浏览器会弹出下载保存框，而不是在页面里打开
            "Content-Disposition": f'attachment; filename="translation_{img.id}.txt"',
        },
    )


@app.post("/api/images/{image_id}/render", response_model=ImageOut, tags=["images"],
          summary="嵌字（漫画图上传后自动跑；失败后在这里重试）",
          description="OCR 检测文字 → LaMa 擦除 → 口语风翻译 → 画字成品PNG。"
                      "用 result 接口轮询 status。",
          responses={404: {"description": "图片不存在"},
                     409: {"description": "任务正在进行中"}})
def render_image(image_id: int, background: BackgroundTasks,
                 db: Session = Depends(get_db)):
    # ① 找记录 —— 同款本文件 get_result 接口开头
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")

    # ② 一道 409 把关（Conflict = 请求没错，但当前状态不能干这件事）：
    #    任务跑着时不许重复发起（防连点）。
    #    failed 之后可以重试；done 之后也允许重新嵌（想换个效果时）
    if img.status == "running":
        raise HTTPException(409, "任务正在进行中，别着急")

    # ③ 挂后台任务立刻返回 —— 同款 upload 接口第④步
    background.add_task(_run_render, image_id)
    return _to_out(img)


@app.get("/api/images/{image_id}/render/download", tags=["images"],
         summary="下载嵌字成品PNG",
         responses={404: {"description": "图片不存在"},
                    409: {"description": "还没嵌字或嵌字失败"}})
def download_rendered(image_id: int, db: Session = Depends(get_db)):
    """下载嵌字成品图。
    FileResponse = 返回"磁盘上真实文件"的专用工具 —— 同款 docs.py 的 download_doc。
    跟上方 download_result 的 Response（返回内存里拼的文本）是两种下载。"""
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    if not img.rendered_path:
        raise HTTPException(409, "还没有嵌字成品，等 status=done 后再来")

    # FileResponse 的 filename 参数会自动处理好中文文件名的编码
    filename = f"{Path(img.filename).stem}_嵌字.png"
    return FileResponse(img.rendered_path, media_type="image/png", filename=filename)

