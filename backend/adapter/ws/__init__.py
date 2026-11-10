from fastapi import FastAPI

from backend.adapter.ws.sample import project_ws_endpoint


def add_ws_router(app: FastAPI):
    app.add_api_websocket_route(
        "/ws/project/{project_id}/{sample_id}", project_ws_endpoint
    )
