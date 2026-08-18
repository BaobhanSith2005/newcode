"""数据合同（Pydantic 模型）—— 同款见 AIRoomBuilder/backend/app/schemas.py。

前端发来的数据按合同校验，返回给前端的数据按合同整形。
"""
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TranslateText(BaseModel):
    """一段文字的翻译 —— 跟 prompts.py 里约定的 JSON 形状一致"""
    original: str = Field(description="图片中的原文")
    translation: str = Field(description="翻译后的中文")


class BatchCreate(BaseModel):
    """创建批次时前端发来的数据 —— 同款见 AIRoomBuilder schemas.py 第7-8行 ProjectCreate"""
    name: str = Field(default="未命名批次", max_length=200,
                      description="批次名称，比如书名。同一批次的书页图会合成一个txt。")


class BatchOut(BaseModel):
    """返回给前端的批次信息 —— 同款见 AIRoomBuilder schemas.py 第11-16行 ProjectOut"""
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="批次唯一 ID")
    name: str = Field(description="批次名称")
    created_at: datetime = Field(description="创建时间（ISO-8601, UTC）")


class ImageOut(BaseModel):
    """返回给前端的图片信息 —— 同款见 AIRoomBuilder schemas.py 第18-27行 ImageOut"""
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="图片唯一 ID")
    batch_id: int | None = Field(default=None, description="所属批次 ID；漫画板块的图为 None")
    filename: str = Field(description="上传时的原始文件名")
    order: int = Field(default=0, description="批次内的排序号（第几张）")
    status: str = Field(description="处理状态：pending → running → done / failed")
    error: str | None = Field(default=None, description="失败时的错误信息")
    result: dict[str, Any] | None = Field(
        default=None,
        description="翻译结果：status=done 时非空，含 texts[] 列表",
    )
    style: str = Field(description="翻译风格")
    created_at: datetime = Field(description="上传时间（ISO-8601, UTC）")

    @field_validator("result", mode="before")
    @classmethod
    def parse_result(cls, v: Any) -> Any:
        """数据库存的是 JSON 字符串，这里自动解包成字典。
        有了它，任何接口直接 return 数据库对象都不会再报
        "Input should be a valid dictionary"——上次那个500的根治版。"""
        if isinstance(v, str):
            return json.loads(v) if v else None
        return v

