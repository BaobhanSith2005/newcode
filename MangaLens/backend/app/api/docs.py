"""文本文件翻译接口（小说 txt / epub）—— 结构同款见 app/api/batches.py。"""

import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import SessionLocal, get_db
from ..models import Doc
from ..schemas import DocOut
from ..services.doc import translate_doc_file

router = APIRouter(prefix="/api/docs", tags=["docs"])

ALLOWED_DOC_EXT = {".txt", ".epub"}


# --------------------------------------------------------------------------- 后台任务

def _run_translate_doc(doc_id: int) -> None:
    """后台任务：整本 txt 翻译 —— 同款见 main.py 第55-76行 _run_translate。
    状态机一模一样：running → done / failed。"""
    db = SessionLocal()
    try:
        doc = db.get(Doc, doc_id)
        if not doc:
            return
        doc.status = "running"
        db.commit()
        try:
            src = Path(doc.path)
            # 译文后缀跟原文走：txt 出 .txt，epub 出 .epub
            out = src.with_name(f"{src.stem}_译文{src.suffix}")
            err = translate_doc_file(src, out, doc.file_type, style=doc.style)
            if err:
                doc.status = "failed"
                doc.error = err
            else:
                doc.out_path = str(out)
                doc.status = "done"
                doc.error = None
        except Exception as exc:  # noqa: BLE001 失败信息要能回传给前端
            doc.status = "failed"
            doc.error = f"{type(exc).__name__}: {exc}"
        db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- 接口

@router.post("/upload", response_model=DocOut, summary="上传小说 txt / epub",
             description="保存txt并立即返回，翻译在后台进行，用 result 接口轮询。",
             responses={400: {"description": "格式不支持"}})
async def upload_doc(
    background: BackgroundTasks,
    file: UploadFile = File(..., description="小说 txt 文件"),
    style: str = Form("文学风", description="翻译风格，默认文学风"),
    db: Session = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_DOC_EXT:
        raise HTTPException(400, f"暂只支持 {sorted(ALLOWED_DOC_EXT)}")

    raw = await file.read()
    dest = UPLOAD_DIR / f"doc_{uuid.uuid4().hex}{ext}"
    dest.write_bytes(raw)

    doc = Doc(filename=file.filename or dest.name, path=str(dest),
              file_type=ext.lstrip("."), style=style)
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(_run_translate_doc, doc.id)
    return doc


@router.get("/{doc_id}/result", response_model=DocOut, summary="轮询翻译结果",
            responses={404: {"description": "任务不存在"}})
def get_doc_result(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Doc, doc_id)
    if not doc:
        raise HTTPException(404, "任务不存在")
    return doc


@router.get("/{doc_id}/download", summary="下载译文",
            responses={404: {"description": "任务不存在"},
                       409: {"description": "还没翻译完或翻译失败"}})
def download_doc(doc_id: int, db: Session = Depends(get_db)):
    """下载译文。
    FileResponse = 返回"磁盘上真实文件"的专用工具——跟之前 Response
    （返回内存里拼的文本）是两种下载：文件大时用 FileResponse 不占内存。"""
    doc = db.get(Doc, doc_id)
    if not doc:
        raise HTTPException(404, "任务不存在")
    if doc.status != "done" or not doc.out_path:
        raise HTTPException(409, f"当前状态 {doc.status}，翻译完成(done)后才能下载")

    filename = f"{Path(doc.filename).stem}_译文{Path(doc.filename).suffix}"
    # media_type 告诉浏览器"这是什么文件"：epub 有专用类型 application/epub+zip
    media_type = ("application/epub+zip" if doc.file_type == "epub"
                  else "text/plain; charset=utf-8")
    # FileResponse 的 filename 参数会自动处理好中文文件名的编码
    return FileResponse(doc.out_path, media_type=media_type, filename=filename)
