from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Project
from ..schemas import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut, summary="创建项目",
              description="新建一个房间识别任务容器。后续上传的图片与分析结果都挂在项目下。")
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(name=payload.name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[ProjectOut], summary="项目列表",
            description="返回全部项目，按 ID 倒序（最新在前）。")
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(select(Project).order_by(Project.id.desc())).all()


@router.get("/{project_id}", response_model=ProjectOut, summary="获取项目",
            description="按 ID 获取单个项目的详情。", responses={404: {"description": "项目不存在"}})
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.delete("/{project_id}", summary="删除项目",
                description="删除项目及其下所有图片与场景（级联）。", responses={404: {"description": "项目不存在"}})
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()
    return {"ok": True}
