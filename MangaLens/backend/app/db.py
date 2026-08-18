from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# 数据库引擎 —— 同款见 AIRoomBuilder/backend/app/db.py 第8-12行
# create_engine：连上 SQLite 文件（config.py 里定义的 data/app.db）
# connect_args 是 SQLite 专属配置，多线程访问需要，照抄即可
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 所有表的"祖宗" —— 同款见 AIRoomBuilder db.py 第16-17行
# models.py 里的表类都继承它，数据库才知道有哪些表
class Base(DeclarativeBase):
    pass


# 给接口用的数据库连接 —— 同款见 AIRoomBuilder db.py 第20-25行
# FastAPI 的 Depends(get_db) 就是调它：进来给连接，用完自动关
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 启动时自动建表 —— 同款见 AIRoomBuilder db.py 第28-30行
# 表不存在就创建，已存在就跳过（不会清空数据）
def init_db() -> None:
    from . import models  # noqa: F401  确保 ORM 模型已注册到 metadata
    Base.metadata.create_all(bind=engine)
