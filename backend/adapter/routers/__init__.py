from fastapi import FastAPI

from backend.common.config import settings
from backend.adapter.routers import user
from backend.adapter.routers import project
from backend.adapter.routers import sample
from backend.adapter.routers import attachment
from backend.adapter.routers import pre_annotation
from backend.adapter.routers import training


def add_router(app: FastAPI):
    app.include_router(user.router, prefix=settings.API_V1_STR)
    app.include_router(project.router, prefix=settings.API_V1_STR)
    app.include_router(attachment.router, prefix=settings.API_V1_STR)
    app.include_router(sample.router, prefix=settings.API_V1_STR)
    app.include_router(pre_annotation.router, prefix=settings.API_V1_STR)
    app.include_router(training.router, prefix=settings.API_V1_STR)
