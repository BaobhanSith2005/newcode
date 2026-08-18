"""批次接口 —— 同款见 AIRoomBuilder/backend/app/api/projects.py。

小说板块：一个批次 = 一本要翻译的书。
"""
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Batch, Image
from ..schemas import BatchCreate, BatchOut, ImageOut

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.post("", response_model=BatchOut, summary="创建批次",
             description="新建一个小说翻译批次。之后上传书页图时带上批次ID。")
def create_batch(payload: BatchCreate, db: Session = Depends(get_db)):
    """同款见 AIRoomBuilder projects.py 第12-19行 create_project"""
    batch = Batch(name=payload.name)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return batch


@router.get("", response_model=list[BatchOut], summary="批次列表",
           description="返回全部批次，按 ID 倒序（最新在前）。")
def list_batches(db: Session = Depends(get_db)):
    """同款见 AIRoomBuilder projects.py 第22-25行 list_projects"""
    return db.scalars(select(Batch).order_by(Batch.id.desc())).all()


@router.get("/{batch_id}", response_model=BatchOut, summary="获取批次",
            description="按 ID 获取单个批次。",
            responses={404: {"description": "批次不存在"}})
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    """同款见 AIRoomBuilder projects.py 第28-34行 get_project"""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    return batch


@router.get("/{batch_id}/images", response_model=list[ImageOut], summary="批次图片列表",
            description="返回批次下的全部书页图，按 order 从小到大（页码顺序）。")
def list_batch_images(batch_id: int, db: Session = Depends(get_db)):
    """同款见 AIRoomBuilder images.py 第95-100行 list_images，
    区别：那里按 id 倒序，这里按 order 升序——合成 txt 的页码顺序靠它。
    直接返回数据库对象即可，ImageOut 里的校验器会自动把 result 字符串解包成字典。"""
    return db.scalars(
        select(Image).where(Image.batch_id == batch_id).order_by(Image.order.asc())
    ).all()


@router.delete("/{batch_id}", summary="删除批次",
               description="删除批次及其下所有图片记录（级联）。",
               responses={404: {"description": "批次不存在"}})
def delete_batch(batch_id: int, db: Session = Depends(get_db)):
    """同款见 AIRoomBuilder projects.py 第37-45行 delete_project"""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    db.delete(batch)
    db.commit()
    return {"ok": True}

@router.get("/{batch_id}/download", summary="下载整批合成txt",
            description="把批次内全部书页按 order 顺序拼成一个对照txt。",
            responses={404: {"description": "批次不存在"},
                       409: {"description": "批次为空或还有图片没翻译完"}})
def download_batch(batch_id: int, db: Session = Depends(get_db)):
    """整批下载 —— 用到的全是旧技能：排序、409、Response、dumps/loads。"""
    batch = db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")

    images = db.scalars(
        select(Image).where(Image.batch_id == batch_id).order_by(Image.order.asc())
    ).all()
    if not images:
        raise HTTPException(409, "批次里还没有图片")

    # 全部翻译完才给下载，否则 txt 里会有洞
    not_done = [i for i in images if i.status != "done" or not i.result]
    if not_done:
        raise HTTPException(409, f"还有 {len(not_done)} 张没翻译完，全部完成后再下载")

    # 按 order 顺序拼接：每页一个分隔头 + 原文/译文对照
    lines: list[str] = []
    for page_no, img in enumerate(images, start=1):
        data = json.loads(img.result)
        lines.append(f"========== 第 {page_no} 页（{img.filename}）==========")
        lines.append("")
        for item in data.get("texts", []):
            lines.append(item["original"])
            lines.append(item["translation"])
            lines.append("")
        lines.append("")

    return Response(
        content="\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="batch_{batch_id}.txt"'},
    )


@router.post("/{batch_id}/images/{image_id}/move", response_model=list[ImageOut],
             summary="调整书页顺序",
             description="把某张图在批次内上移/下移一位，返回调整后的完整顺序。")
def move_image(batch_id: int, image_id: int, direction: str = Query("up"),
               db: Session = Depends(get_db)):
    """调序 —— 解决"传错顺序后重新排"的需求。
    算法三步：排队 → 编号 → 跟邻居换号。"""
    img = db.get(Image, image_id)
    if not img or img.batch_id != batch_id:
        raise HTTPException(404, "图片不在该批次中")
    if direction not in ("up", "down"):
        raise HTTPException(400, "direction 只能是 up 或 down")

    # ① 排队：批次内所有图按 order 从小到大排好
    siblings = db.scalars(
        select(Image).where(Image.batch_id == batch_id).order_by(Image.order.asc())
    ).all()

    # ② 编号：先把顺序归一化成 0,1,2...（防止两张图 order 撞车，交换就没效果）
    for i, s in enumerate(siblings):
        s.order = i

    # ③ 换号：找到这张图在第几位，跟邻居（上一位/下一位）交换 order
    idx = siblings.index(img)
    target = idx - 1 if direction == "up" else idx + 1
    if target < 0 or target >= len(siblings):
        raise HTTPException(400, "已经在最前/最后，不能再移")

    neighbor = siblings[target]
    img.order, neighbor.order = neighbor.order, img.order
    db.commit()

    # ④ 返回新的完整顺序，前端拿到直接刷新列表
    return sorted(siblings, key=lambda x: x.order)
