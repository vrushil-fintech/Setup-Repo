import httpx
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from app.config import EVENT_GRID_NEWSLETTER_ENDPOINT, EVENT_GRID_NEWSLETTER_ACCESS_KEY, APP_ENV
from app.dependencies import logger


async def publish_event(event_type: str, subject: str, data: Dict[str, Any]) -> None:
    """
    Publishes an event to Azure Event Grid using an HTTP POST request.

    :param event_type: The type of the event.
    :param subject: A string representing the subject of the event.
    :param data: A dictionary containing the payload data.
    """
    if APP_ENV == "local":
        return
    
    event = [
        {
            "id": str(uuid.uuid4()),
            "topic": "",    # Currently not using this field, since there is only one subscriber per topic
            "eventType": event_type,
            "subject": subject,
            "data": data,
            "dataVersion": "1.0",
            "eventTime": str(datetime.now(timezone.utc)),
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "aeg-sas-key": EVENT_GRID_NEWSLETTER_ACCESS_KEY
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url=EVENT_GRID_NEWSLETTER_ENDPOINT, json=event, headers=headers)
            response.raise_for_status()  # Raise an error for bad status codes
            logger.info(f"Event '{event_type}' published successfully.")

    except Exception as e:
        logger.error(f"Failed to publish event '{event_type}': {e}")
