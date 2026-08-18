"""MangaLens 后端入口 —— 异步版。

同款对照：AIRoomBuilder/backend/app/main.py（入口结构）
         + AIRoomBuilder/backend/app/api/images.py（上传+后台任务+轮询）

完整流程：
  前端 POST /api/images/upload → 立刻返回图片ID（0.1秒）
  后端后台任务偷偷调大模型（几十秒）
  前端 GET /api/images/{id}/result 轮询，直到 status=done
"""
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .api.batches import router as batches_router
from .config import UPLOAD_DIR, settings
from .db import SessionLocal, get_db, init_db
from .models import Batch, Image
from .schemas import ImageOut
from .services.vision import analyze_image

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

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_BYTES = 20 * 1024 * 1024


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
        db.commit()
        try:
            result = analyze_image(img.path, style=img.style)
            img.result = json.dumps(result, ensure_ascii=False)
            img.status = "done"
            img.error = None
        except Exception as exc:  # noqa: BLE001 失败信息要能回传给前端
            img.status = "failed"
            img.error = f"{type(exc).__name__}: {exc}"
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- 接口

def _to_out(img: Image) -> ImageOut:
    """把数据库记录转成接口返回对象。
    数据库里 result 存的是 JSON 字符串（Text 列），返回前要 json.loads 转回字典。
    同款见 AIRoomBuilder/backend/app/api/images.py 第113-118行：
    存的时候 dumps（打包成字符串），取的时候 loads（解包回字典），一存一取对称。"""
    return ImageOut(
        id=img.id,
        batch_id=img.batch_id,
        filename=img.filename,
        order=img.order,
        status=img.status,
        error=img.error,
        result=json.loads(img.result) if img.result else None,
        style=img.style,
        created_at=img.created_at,
    )


@app.get("/api/health", tags=["health"], summary="健康检查")
def health():
    return {
        "ok": True,
        "vision_provider": settings.resolved_provider(),
        "vision_model": settings.resolved_model(),
        "note": "provider 为 mock 时使用内置数据，无需 API Key",
    }


@app.post("/api/images/upload", response_model=ImageOut, tags=["images"],
          summary="上传漫画/书页图片",
          description="保存图片并立即返回。大模型翻译在后台进行，用 result 接口轮询进度。",
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

    # ①.5 带了 batch_id 就先验证批次存在 —— 不存在的批次不接图
    if batch_id is not None and not db.get(Batch, batch_id):
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

    # ④ 把"调大模型"挂到后台，立刻返回 —— 同款见 AIRoomBuilder images.py 第91-92行
    background.add_task(_run_translate, img.id)
    return _to_out(img)


@app.get("/api/images/{image_id}/result", response_model=ImageOut, tags=["images"],
         summary="轮询翻译结果",
         description="轮询直到 status=done；failed 时 error 字段有原因。",
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

