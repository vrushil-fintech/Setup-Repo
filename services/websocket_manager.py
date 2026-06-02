from typing import Dict
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from app.dependencies import logger
from app.models import ResponseClass


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        """
        Accepts a WebSocket connection and adds it to the active connections.
        """
        await websocket.accept()
        if user_id in self.active_connections:
            logger.warning(
                f"WebSocket connection already exists.", extra={"user_id": user_id}
            )
            await self.send_error(
                websocket=websocket,
                status_code=422,    # before analysis error have uniform status_codes
                error_message="You already have an ongoing analysis. Please wait for it to complete before starting a new one.",
            )
            return False

        self.active_connections[user_id] = websocket
        logger.info(f"WebSocket connected.", extra={"user_id": user_id})
        return True

    async def disconnect(self, user_id: str):
        """
        Removes a WebSocket connection from the active connections.
        """
        websocket = self.active_connections.pop(user_id, None)
        if websocket:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close()
                logger.info(f"WebSocket disconnected.", extra={"user_id": user_id})
            except Exception as e:
                logger.warning(
                    f"Error while disconnecting WebSocket: {str(e)}",
                    extra={"user_id": user_id},
                )

    async def send_json(self, user_id: str, response: ResponseClass):
        """
        Sends a JSON response to a specific WebSocket connection.
        Ensures the connection exists before sending.
        Returns True on success, False on any failure.
        """
        websocket = self.active_connections.get(user_id, None)
        if not websocket:
            logger.warning(
                "send_json failed: no active WebSocket connection found in active_connections.",
                extra={"user_id": user_id},
            )
            return False

        if websocket.client_state != WebSocketState.CONNECTED:
            logger.warning(
                f"send_json failed: WebSocket state is {websocket.client_state}, not CONNECTED. Disconnecting.",
                extra={"user_id": user_id},
            )
            await self.disconnect(user_id)
            return False

        try:
            await websocket.send_json(response.model_dump())
            return True
        except Exception as e:
            logger.error(
                f"send_json failed: exception while sending to WebSocket: {str(e)}",
                extra={"user_id": user_id},
            )
            await self.disconnect(user_id)
            return False

    async def send_error(
        self,
        status_code: int,
        error_message: str,
        user_id: str = None,
        websocket: WebSocket = None,
    ):
        """
        Sends an error message over a WebSocket and then closes the connection.
        """
        if not websocket:
            if user_id:
                websocket = self.active_connections.get(user_id)
            else:
                logger.warning(
                    f"No active WebSocket connection for user.",
                    extra={"user_id": user_id},
                )
                return

        try:
            error_response = ResponseClass(
                status_code=status_code, error_message=error_message
            )
            await websocket.send_json(error_response.model_dump())
        except Exception as e:
            logger.warning(
                f"Failed to send error message: {str(e)}", extra={"user_id": user_id}
            )
        finally:
            try:
                if websocket and websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.close()
            except Exception as e:
                logger.warning(
                    f"Error closing WebSocket in send_error: {str(e)}",
                    extra={"user_id": user_id},
                )
            # Always remove from active_connections so no stale entry remains
            if user_id:
                self.active_connections.pop(user_id, None)
                logger.info(
                    f"WebSocket removed from active_connections after send_error.",
                    extra={"user_id": user_id},
                )


websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    return websocket_manager
