"""启动隔离 HTTP 服务，用官方 MCP 客户端验证真实传输及业务调用。"""

import asyncio
import base64
import json
import os
import socket
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

import httpx2
import pytest
import requests
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from PIL import Image


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_official_client_upload_annotation_download_and_revocation(
    tmp_path: Path, mode
):
    # 1. 使用独立进程、空库和系统分配端口，不接触运行中的开发服务。
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    data = tmp_path / "data"
    root = Path(__file__).resolve().parents[3]
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "PYTHONPATH": str(root),
        "YOLO_MCP_DATA_DIR": str(data),
        "YOLO_MCP_DATABASE_URL": f"sqlite:///{(data / 'app.sqlite').as_posix()}",
    }
    base = f"http://127.0.0.1:{port}"
    with (tmp_path / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=tmp_path,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    if (
                        requests.get(
                            f"{base}/api/v1/users/bootstrap", timeout=1
                        ).status_code
                        == 200
                    ):
                        break
                except requests.RequestException:
                    pass
                if process.poll() is not None or time.monotonic() > deadline:
                    pytest.fail((tmp_path / "server.log").read_text(encoding="utf-8"))
                time.sleep(0.1)
            credentials = {"username": "admin@example.com", "password": "Mcp-test-123"}
            assert (
                requests.post(
                    f"{base}/api/v1/users/signup", json=credentials
                ).status_code
                == 201
            )
            session = requests.post(
                f"{base}/api/v1/users/login", json=credentials
            ).json()["data"]["token"]
            headers = {"Authorization": session}
            issued = requests.post(
                f"{base}/api/v1/users/tokens",
                headers=headers,
                json={"name": "official MCP client"},
            )
            assert issued.status_code == 201, issued.text
            token = issued.json()["data"]
            bearer = {"Authorization": f"Bearer {token['token']}"}

            # 2. 两种协议协商方式均通过真实 TCP 调用，不跳过认证中间件。
            async def workflow():
                async with httpx2.AsyncClient(headers=bearer) as http:
                    async with Client(
                        streamable_http_client(f"{base}/mcp", http_client=http),
                        mode=mode,
                    ) as client:
                        tools = await client.list_tools()
                        assert len(tools.tools) >= 22

                        async def call(name, arguments):
                            result = await client.call_tool(name, arguments)
                            assert not result.is_error, result
                            return json.loads(result.content[0].text)

                        project = await call(
                            "create_project", {"name": "Official client"}
                        )
                        pid = project["id"]
                        config = {
                            "tools": [
                                {
                                    "tool": "rectTool",
                                    "config": {
                                        "attributes": [
                                            {"key": "object", "value": "object"}
                                        ]
                                    },
                                }
                            ]
                        }
                        await call(
                            "update_project",
                            {
                                "project_id": pid,
                                "changes": {"config": json.dumps(config)},
                            },
                        )
                        image = BytesIO()
                        Image.new("RGB", (24, 24), "blue").save(image, format="PNG")
                        ids = []
                        for split in ("train", "test"):
                            uploaded = await call(
                                "upload_image",
                                {
                                    "project_id": pid,
                                    "filename": f"{split}.png",
                                    "image_base64": base64.b64encode(
                                        image.getvalue()
                                    ).decode(),
                                    "split": split,
                                },
                            )
                            sid = uploaded["sample_id"]
                            ids.append(sid)
                            result = {
                                "width": 24,
                                "height": 24,
                                "rectTool": {
                                    "result": [
                                        {
                                            "x": 1,
                                            "y": 2,
                                            "width": 10,
                                            "height": 8,
                                            "label": "object",
                                        }
                                    ]
                                },
                            }
                            saved = await call(
                                "save_annotation",
                                {
                                    "project_id": pid,
                                    "sample_id": sid,
                                    "result": result,
                                    "annotated_count": 1,
                                },
                            )
                            assert saved["state"] == "DONE"
                        rows = await call(
                            "list_samples", {"project_id": pid, "split": "test"}
                        )
                        assert rows["total"] == 1 and rows["data"][0]["id"] == ids[1]
                        sample = await call(
                            "get_sample", {"project_id": pid, "sample_id": ids[0]}
                        )
                        assert (
                            requests.get(base + sample["file"]["url"]).status_code
                            == 200
                        )
                        model = data / f"projects/{pid}/models/example.pt"
                        model.write_bytes(b"synthetic model download")
                        assert (
                            "example.pt"
                            in (await call("list_models", {"project_id": pid}))[
                                "models"
                            ]
                        )
                        download = await call(
                            "get_model_download",
                            {"project_id": pid, "model_name": "example.pt"},
                        )
                        assert (
                            requests.get(
                                base + download["path"], headers=bearer
                            ).content
                            == b"synthetic model download"
                        )
                        assert (await call("list_training_runs", {"project_id": pid}))[
                            "total"
                        ] == 0
                        invalid = await client.call_tool(
                            "get_training_run", {"project_id": pid, "run_id": 999}
                        )
                        assert invalid.is_error
                        assert (
                            requests.delete(
                                f"{base}/api/v1/users/tokens/{token['id']}",
                                headers=headers,
                            ).status_code
                            == 200
                        )
                        with pytest.raises(Exception):
                            await client.call_tool("list_projects", {})

            asyncio.run(workflow())
        finally:
            process.terminate()
            process.wait(timeout=15)
