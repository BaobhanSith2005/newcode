from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(default="未命名项目", max_length=200, description="项目名称，用于在前端列表中区分不同房间/任务。")


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="项目唯一 ID")
    name: str = Field(description="项目名称")
    created_at: datetime = Field(description="创建时间（ISO-8601, UTC）")


class ImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="图片唯一 ID")
    project_id: int = Field(description="所属项目 ID")
    filename: str = Field(description="上传时的原始文件名")
    width: int = Field(description="图片宽度（像素，上传时已被等比缩放到 ≤1600px）")
    height: int = Field(description="图片高度（像素）")
    status: str = Field(description="分析状态：pending → running → done / failed")
    error: str | None = Field(default=None, description="失败时的错误信息（如 VisionError 详情）")
    created_at: datetime = Field(description="上传时间（ISO-8601, UTC）")


class AnalysisOut(BaseModel):
    image_id: int = Field(description="图片 ID")
    status: str = Field(description="分析状态：pending / running / done / failed")
    error: str | None = Field(default=None, description="失败时的错误信息")
    analysis: dict[str, Any] | None = Field(
        default=None,
        description=(
            "视觉模型的结构化识别结果。字段包括 room_type / style / dominant_colors / "
            "objects[] / openings[] 等。结构详见 docs/01-scene协议.md。status=done 时非空。"
        ),
    )


class RoomOverride(BaseModel):
    width: float | None = Field(default=None, ge=1, le=30, description="房间东西向宽度（米），覆盖模型估算/预设值")
    depth: float | None = Field(default=None, ge=1, le=30, description="房间南北向进深（米），覆盖模型估算/预设值")
    height: float | None = Field(default=None, ge=2, le=6, description="房间层高（米），覆盖模型估算/预设值")


class SceneCreate(BaseModel):
    image_id: int = Field(description="已分析完成的图片 ID（必须 status=done）")
    room: RoomOverride | None = Field(default=None, description="可选：手动覆盖房间尺寸；不传则用模型估算或房型预设")


class SceneOut(BaseModel):
    id: int = Field(description="场景唯一 ID")
    project_id: int = Field(description="所属项目 ID")
    image_id: int | None = Field(default=None, description="来源图片 ID")
    scene: dict[str, Any] = Field(
        description=(
            "scene.json 渲染契约：包含 room（尺寸/材质）与 objects[]（家具布局）。"
            "前端 Three.js 据此渲染三维房间。结构详见 docs/scene.schema.json。"
        )
    )
    created_at: datetime = Field(description="创建时间（ISO-8601, UTC）")
    updated_at: datetime = Field(description="最近更新时间（ISO-8601, UTC）")


class SceneUpdate(BaseModel):
    scene: dict[str, Any] = Field(description="完整的 scene.json 对象，将整体替换存储中的场景")
