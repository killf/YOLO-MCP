from fastapi import Depends, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import BaseModel

from backend.clients.ws import sampleConnectionManager
from backend.common.websocket import ConnectionData, Message, MessageType
from backend.dependencies.user import verify_ws_token


class ProjectSampleWsPayload(BaseModel):
    project_id: int
    user_id: int
    username: str
    sample_id: int


def get_project_sample_connection_payloads(conns: ConnectionData):
    if not conns:
        return Message(type=MessageType.PEERS, data=[])

    return Message(
        type=MessageType.PEERS,
        data=[
            ProjectSampleWsPayload(
                project_id=conn.data.project_id,
                user_id=conn.data.user_id,
                username=conn.data.username,
                sample_id=conn.data.sample_id,
            )
            for conn in conns
        ],
    )


async def project_ws_endpoint(
    websocket: WebSocket, project_id: int, sample_id: int, user=Depends(verify_ws_token)
):
    if not user:
        return

    client_id = f"project_{project_id}"

    async def sync_peers():
        connections = sampleConnectionManager.active_connections
        current_connections = connections.get(client_id, {})
        sample_payload = get_project_sample_connection_payloads(
            current_connections.values()
        )

        await sampleConnectionManager.send_message(
            client_id=client_id, message=sample_payload
        )

    connection = None

    async def cleanup():
        await sampleConnectionManager.disconnect(client_id, websocket)
        await sync_peers()

    try:
        connection = await sampleConnectionManager.connect(
            client_id,
            websocket,
            data=ProjectSampleWsPayload(
                project_id=project_id,
                user_id=user.id,
                username=user.username,
                sample_id=sample_id,
            ),
        )

        await sync_peers()

        while True:
            try:
                data = await websocket.receive_text()
                message = Message.model_validate_json(data)

                if message.type == MessageType.PONG:
                    connection.update_heartbeat()

            except WebSocketDisconnect as e:
                logger.info(
                    f"WebSocket disconnected for client {client_id}: Code={e.code}"
                )
                break

    except WebSocketDisconnect as e:
        logger.info(
            "WebSocket disconnected during setup for client {}: Code={}",
            client_id,
            e.code,
        )
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        await cleanup()
