from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .config import MODELS_DIR, UPLOAD_DIR, settings
from .db import init_db

DESCRIPTION = """
# AI Room Builder API

基于多模态大模型的「室内空间理解 → Web 三维场景生成」后端。

## 处理流水线
1. **上传图片** `POST /api/images/upload` —— 上传房间照片，系统自动在后台调用视觉模型分析。
2. **轮询分析** `GET /api/images/{id}/analysis` —— 等待 `status=done`，拿到识别结果
   （房型、家具清单、俯视布局、门窗、估算的房间尺寸）。
3. **生成场景** `POST /api/scenes/generate` —— 把分析结果 + 可选房间尺寸覆盖，落成 `scene.json`
   （确定性渲染契约，详见 `docs/01-scene协议.md`）。
4. **前端渲染** —— 前端用 Three.js 加载 `scene.json` 与 `models/` 下的 `.glb` 家具模型渲染三维房间。

## 视觉模型（VLM）
- 通过环境变量 `VISION_PROVIDER` 选择：`mock` / `openai` / `dashscope` / `gemini`。
- 无 API Key 时自动回退 `mock`（内置样例数据，无需联网即可跑通全链路）。
- 当前生效的模型见 `GET /api/health` 返回的 `vision_provider` 与 `vision_model`。

## 约定
- 所有时间字段为 ISO-8601（UTC）。
- 分析/场景结果均为 JSON 对象，结构见 `docs/` 下协议文档与 `docs/scene.schema.json`。
"""

OPENAPI_TAGS = [
    {"name": "projects", "description": "项目（一次房间识别任务的工作容器）的增删查。"},
    {"name": "images", "description": "房间照片的上传与后台视觉分析；分析完成后可轮询结果或重新分析。"},
    {"name": "scenes", "description": "把分析结果生成为 scene.json、查询/更新场景、获取品类与房间尺寸预设。"},
    {"name": "health", "description": "服务健康检查，返回当前生效的视觉模型配置。"},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.mount("/models", StaticFiles(directory=MODELS_DIR), name="models")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/health", tags=["health"], summary="健康检查",
         description="返回服务可用性与当前生效的视觉模型配置（provider 与具体模型名）。")
def health():
    return {
        "ok": True,
        "vision_provider": settings.resolved_provider(),
        "vision_model": settings.resolved_model(),
        "configured_provider": settings.vision_provider,
        "note": "provider 为 mock 时使用内置样例数据，无需 API Key",
    }
