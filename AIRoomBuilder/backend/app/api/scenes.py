import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Image, Scene
from ..schemas import SceneCreate, SceneOut, SceneUpdate
from ..services.catalog import ALLOWED_CATEGORIES, ROOM_DEFAULTS
from ..services.scene_builder import build_scene

router = APIRouter(prefix="/scenes", tags=["scenes"])


def _to_out(s: Scene) -> SceneOut:
    return SceneOut(
        id=s.id, project_id=s.project_id, image_id=s.image_id,
        scene=json.loads(s.scene_json), created_at=s.created_at, updated_at=s.updated_at,
    )


@router.post("/generate", response_model=SceneOut, summary="生成场景",
              description=(
                  "把已分析完成的图片生成为 scene.json 三维渲染契约。可选传入 room 覆盖房间尺寸"
                  "（尺寸优先级：手动覆盖 > 模型估算 > 房型预设）。"
              ),
              responses={404: {"description": "图片不存在"}, 409: {"description": "图片尚未分析完成"}})
def generate_scene(payload: SceneCreate, db: Session = Depends(get_db)):
    img = db.get(Image, payload.image_id)
    if not img:
        raise HTTPException(404, "图片不存在")
    if img.status != "done" or not img.analysis_result:
        raise HTTPException(409, f"图片尚未分析完成（当前状态：{img.status}）")

    analysis = json.loads(img.analysis_result)
    override = payload.room.model_dump(exclude_none=True) if payload.room else None
    scene = build_scene(analysis, override)

    row = Scene(project_id=img.project_id, image_id=img.id,
                scene_json=json.dumps(scene, ensure_ascii=False))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("", response_model=list[SceneOut], summary="场景列表",
            description="返回指定项目下的全部场景，按 ID 倒序。")
def list_scenes(project_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.id.desc())
    ).all()
    return [_to_out(r) for r in rows]


@router.get("/{scene_id}", response_model=SceneOut, summary="获取场景",
            description="按 ID 获取单个 scene.json 场景。", responses={404: {"description": "场景不存在"}})
def get_scene(scene_id: int, db: Session = Depends(get_db)):
    row = db.get(Scene, scene_id)
    if not row:
        raise HTTPException(404, "场景不存在")
    return _to_out(row)


@router.put("/{scene_id}", response_model=SceneOut, summary="更新场景",
             description="整体替换某个场景的 scene.json（用于前端拖拽编辑后回存）。",
             responses={404: {"description": "场景不存在"}})
def update_scene(scene_id: int, payload: SceneUpdate, db: Session = Depends(get_db)):
    row = db.get(Scene, scene_id)
    if not row:
        raise HTTPException(404, "场景不存在")
    row.scene_json = json.dumps(payload.scene, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/meta/catalog", summary="品类与房间预设",
             description="返回受控家具品类清单（ALLOWED_CATEGORIES）与各房型默认尺寸（ROOM_DEFAULTS），"
                         "前端用于渲染下拉框与房间尺寸预设。")
def get_catalog():
    return {"categories": ALLOWED_CATEGORIES, "room_defaults": ROOM_DEFAULTS}
