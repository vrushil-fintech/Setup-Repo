import asyncio
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.dependencies import logger
from app.services.websocket_manager import WebSocketManager, get_websocket_manager

router = APIRouter()

_PING_INTERVAL_SECONDS = 30


async def _ws_ping_loop(websocket: WebSocket, user_id: str, websocket_manager: WebSocketManager):
    """Send periodic pings to prevent infrastructure idle-connection timeouts (e.g. Azure ~4 min)."""
    try:
        while True:
            await asyncio.sleep(_PING_INTERVAL_SECONDS)
            if websocket_manager.active_connections.get(user_id) is not websocket:
                break
            await websocket.send_json({"type": "ping"})
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"WebSocket ping loop stopped: {e}", extra={"user_id": user_id})


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(user_id: str, websocket: WebSocket, websocket_manager: WebSocketManager = Depends(get_websocket_manager)):
    success = await websocket_manager.connect(user_id, websocket)
    if not success:
        return

    ping_task = asyncio.create_task(_ws_ping_loop(websocket, user_id, websocket_manager))
    try:
        while True:
            data = await websocket.receive_text()

    except WebSocketDisconnect as e:
        logger.info(
            f"WebSocket disconnected by client. code={e.code}",
            extra={"user_id": user_id},
        )
        await websocket_manager.disconnect(user_id)

    except Exception as e:
        logger.error(
            f"Unexpected error in WebSocket handler: {str(e)}",
            extra={"user_id": user_id},
        )
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=503,
            error_message="We're having trouble processing your request. Please try again later.",
        )

    finally:
        ping_task.cancel()
