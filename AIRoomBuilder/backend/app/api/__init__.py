from fastapi import APIRouter

from . import images, projects, scenes

api_router = APIRouter(prefix="/api")
api_router.include_router(projects.router)
api_router.include_router(images.router)
api_router.include_router(scenes.router)
