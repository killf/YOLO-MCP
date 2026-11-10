from fastapi import FastAPI

from backend.middleware.content_type import ContentTypeMiddleware
from backend.middleware.tracing import TracingMiddleWare


def add_middleware(app: FastAPI):
    app.add_middleware(TracingMiddleWare)
    app.add_middleware(ContentTypeMiddleware)
