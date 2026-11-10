from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.version import version as yolo_mcp_version


class ContentTypeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # add YOLO-MCP-Version header
        response.headers["YOLO-MCP-Version"] = yolo_mcp_version

        # set content-type for javascript files
        if request.url.path.endswith(".js"):
            response.headers["content-type"] = "application/javascript"

        return response
