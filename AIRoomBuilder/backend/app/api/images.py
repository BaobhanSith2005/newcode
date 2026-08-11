import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from PIL import Image as PILImage
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import SessionLocal, get_db
from ..models import Image, Project
from ..schemas import AnalysisOut, ImageOut
from ..services.vision import analyze_image

router = APIRouter(prefix="/images", tags=["images"])

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_BYTES = 20 * 1024 * 1024
MAX_EDGE = 1600  # 超过则等比缩放，既省 token 又加快上传


def _run_analysis(image_id: int) -> None:
    """后台任务。用独立 Session——请求作用域的 Session 此时已关闭。"""
    db = SessionLocal()
    try:
        img = db.get(Image, image_id)
        if not img:
            return
        img.status = "running"
        db.commit()
        try:
            result = analyze_image(img.path)
            img.analysis_result = json.dumps(result, ensure_ascii=False)
            img.status = "done"
            img.error = None
        except Exception as exc:  # noqa: BLE001 失败信息要能回传给前端
            img.status = "failed"
            img.error = f"{type(exc).__name__}: {exc}"
        db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=ImageOut, summary="上传房间照片",
              description=(
                  "上传一张房间照片。支持的格式：jpg/jpeg/png/webp/bmp（≤20MB）。"
                  "超过 1600px 的图片会被等比缩放以节省 token。上传后在后台自动调用视觉模型分析，"
                  "可用 GET /analysis 轮询结果。"
              ),
              responses={404: {"description": "项目不存在"}, 400: {"description": "格式不支持或图片损坏/过大"}})
async def upload_image(
    background: BackgroundTasks,
    project_id: int,
    file: UploadFile = File(..., description="房间照片文件"),
    db: Session = Depends(get_db),
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "项目不存在")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"不支持的图片格式 {ext}，仅支持 {sorted(ALLOWED_EXT)}")

    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "图片超过 20MB")

    dest = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(raw)

    try:
        with PILImage.open(dest) as im:
            im = im.convert("RGB")
            if max(im.size) > MAX_EDGE:
                ratio = MAX_EDGE / max(im.size)
                im = im.resize((int(im.width * ratio), int(im.height * ratio)),
                               PILImage.LANCZOS)
                im.save(dest, quality=90)
            w, h = im.size
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "图片无法解析，可能已损坏")

    img = Image(project_id=project_id, filename=file.filename or dest.name,
                path=str(dest), width=w, height=h, status="pending")
    db.add(img)
    db.commit()
    db.refresh(img)

    background.add_task(_run_analysis, img.id)
    return img


@router.get("", response_model=list[ImageOut], summary="图片列表",
            description="返回指定项目下的全部图片，按 ID 倒序。")
def list_images(project_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(Image).where(Image.project_id == project_id).order_by(Image.id.desc())
    ).all()


@router.get("/{image_id}/analysis", response_model=AnalysisOut, summary="获取分析结果",
            description=(
                "轮询某张图片的视觉分析结果。轮询直到 status=done；"
                "失败时在 error 字段看到原因（如网关抖动导致的 VisionError，已自动重试）。"
            ),
            responses={404: {"description": "图片不存在"}})
def get_analysis(image_id: int, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    return AnalysisOut(
        image_id=img.id,
        status=img.status,
        error=img.error,
        analysis=json.loads(img.analysis_result) if img.analysis_result else None,
    )


@router.post("/{image_id}/reanalyze", response_model=ImageOut, summary="重新分析",
              description="对已有图片重新触发视觉分析（例如之前分析失败，或想用新 prompt 版本重试）。",
              responses={404: {"description": "图片不存在"}})
def reanalyze(image_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    img = db.get(Image, image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    img.status = "pending"
    img.error = None
    db.commit()
    db.refresh(img)
    background.add_task(_run_analysis, img.id)
    return img
