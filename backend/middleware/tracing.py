import time

from loguru import logger
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware


class TracingMiddleWare(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        scope = request.scope
        start = time.perf_counter()
        response = None
        logger.info(f"{request.method} {scope['path']} start")

        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)

            status_code = response.status_code if response else "error"
            logger.info(
                "{} {} end status={} elapsed_ms={}",
                request.method,
                scope["path"],
                status_code,
                elapsed_ms,
            )
