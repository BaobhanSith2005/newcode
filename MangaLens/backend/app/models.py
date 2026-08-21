"""数据库表定义 —— 同款见 AIRoomBuilder/backend/app/models.py。

MangaLens 两张表：
  Batch（批次：novel 小说 / manga 漫画）1 ──对多── N Image（图片）
  漫画散图（快速测试用）不属于任何批次（batch_id 为空），一张 images 表服务两个板块。
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Batch(Base):
    """一个上传批次：一批图按板块走不同流水线——
    novel 小说：书页图 → 合成一个txt；manga 漫画：图片 → 批量嵌字成品。
    同款见 AIRoomBuilder models.py 第13-23行 Project 表：
    "一个项目管多张图"和"一个批次管多张图"是同一个结构。"""
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="未命名批次")

    # 板块：novel（小说书页图 → 合成txt）/ manga（漫画图 → 批量嵌字成品）。
    # upload 按 batch.kind 决定分派 _run_translate 还是 _run_render。
    # 注意：init_db 只建新表不补列——旧 app.db 没这列，要删库重建（用户已知）
    kind: Mapped[str] = mapped_column(String(20), default="novel")

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

    # 任务进度文字（如"② 云端翻译中…"）。后台任务每进入一个阶段就写一次，
    # 前端轮询 result 接口时带上它，用户就知道跑到哪一步了。
    # 跟 status 的区别：status 是"状态机"（给代码判断用），progress 是给人看的。
    progress: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 大模型返回的翻译结果（JSON 文本）—— 同款见 AIRoomBuilder models.py 第39行
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 翻译风格（直译/文学风/口语风/古风）
    style: Mapped[str] = mapped_column(String(20), default="直译")

    # 嵌字成品 PNG 路径 —— 漫画图上传后直接嵌字（见 main.py _run_render），
    # 成品存文件路径不存内容，同款 Doc 表的 out_path。书页图不嵌字，这列一直空。
    rendered_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    # 一对多关系的"多"这头：我属于哪个批次 —— 同款 models.py 第42行
    batch: Mapped[Batch | None] = relationship(back_populates="images")

class Doc(Base):
    """一个文本文件翻译任务（小说 txt，以后还有 epub）。
    跟 Image 表同款思路：同样的状态机，同样的 error 字段。
    区别在"结果"：大文件翻译的结果不存数据库，只存文件路径。"""
    __tablename__ = "docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(500))                  # 上传的原文件路径
    out_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 译文文件路径
    file_type: Mapped[str] = mapped_column(String(10), default="txt")  # txt | epub（以后）

    # 状态机 —— 同款见 Image 表：pending → running → done / failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 翻译风格 —— 小说默认文学风，跟图片默认直译不同
    style: Mapped[str] = mapped_column(String(20), default="文学风")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
