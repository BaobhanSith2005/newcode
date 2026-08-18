"""数据库表定义 —— 同款见 AIRoomBuilder/backend/app/models.py。

MangaLens 两张表：
  Batch（小说批次）1 ──对多── N Image（图片）
  漫画板块的图不属于任何批次（batch_id 为空），一张 images 表服务两个板块。
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Batch(Base):
    """一个小说上传批次：一批书页图 → 合成一个txt。
    同款见 AIRoomBuilder models.py 第13-23行 Project 表：
    "一个项目管多张图"和"一个批次管多张图"是同一个结构。"""
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="未命名批次")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # 一对多关系的"一"这头：一个批次名下挂着 N 张图
    # cascade="all, delete-orphan" = 删批次时把它的图记录一起删 —— 同款 models.py 第20-21行
    images: Mapped[list["Image"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan")


class Image(Base):
    """一张上传待翻译的图片 —— 同款见 AIRoomBuilder models.py 第26-42行 Image 表"""
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 所属批次。可空 = 漫画板块的图不属于任何批次 —— 同款见 models.py 第30行 project_id
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=True)

    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))

    # 批次内的排序号（第几张）。合成 txt 时按它从小到大排，
    # 这就是"传错顺序可以在后端重新排序"的抓手。
    order: Mapped[int] = mapped_column(Integer, default=0)

    # pending | running | done | failed —— 同款见 AIRoomBuilder models.py 第37行
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 大模型返回的翻译结果（JSON 文本）—— 同款见 AIRoomBuilder models.py 第39行
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 翻译风格（直译/文学风/口语风/古风）
    style: Mapped[str] = mapped_column(String(20), default="直译")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # 一对多关系的"多"这头：我属于哪个批次 —— 同款 models.py 第42行
    batch: Mapped[Batch | None] = relationship(back_populates="images")
