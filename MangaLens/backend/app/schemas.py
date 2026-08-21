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
                      description="批次名称，比如书名/漫画名。")
    kind: str = Field(default="novel", pattern="^(novel|manga)$",
                      description="板块：novel=小说书页（合成txt）/ manga=漫画图（批量嵌字成品）")


class BatchOut(BaseModel):
    """返回给前端的批次信息 —— 同款见 AIRoomBuilder schemas.py 第11-16行 ProjectOut"""
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="批次唯一 ID")
    name: str = Field(description="批次名称")
    kind: str = Field(description="板块：novel 小说 / manga 漫画")
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
    progress: str | None = Field(
        default=None,
        description="任务进行到哪一步的中文提示（如：② 云端翻译中…）。"
                    "running 时看它就知道后台在干嘛；done=完成，failed=失败",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="翻译结果：status=done 时非空，含 texts[] 列表",
    )
    style: str = Field(description="翻译风格")
    # rendered_path 故意不放出来 —— 同款 DocOut 的原则：服务器文件路径是内部信息，
    # 前端看 status=done 且 batch_id 为空（漫画图）就知道成品好了，调 render/download 下载
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


class DocOut(BaseModel):
    """返回给前端的文本文件翻译任务（小说 txt/epub）。
    注意：path / out_path 故意不放出来——服务器上的文件路径是内部信息，
    前端只需要知道文件名和下载接口，不需要知道文件在服务器哪个角落。"""
    model_config = ConfigDict(from_attributes=True)
    id: int = Field(description="文档任务唯一 ID")
    filename: str = Field(description="上传时的原始文件名")
    file_type: str = Field(description="文件类型：txt（epub 下一阶段）")
    status: str = Field(description="处理状态：pending → running → done / failed")
    error: str | None = Field(default=None, description="失败时的错误信息")
    style: str = Field(description="翻译风格（默认文学风）")
    created_at: datetime = Field(description="上传时间（ISO-8601, UTC）")

