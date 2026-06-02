from azure.communication.email import EmailClient
from app.config import EMAIL_SERVICE_CONNECTION_STRING
from app.dependencies import logger
import threading

# Singleton instance
singleton_email_client = None
_email_client_lock = threading.Lock()


def get_email_client() -> EmailClient:
    global singleton_email_client
    with _email_client_lock:
        if singleton_email_client is None:
            if not EMAIL_SERVICE_CONNECTION_STRING:
                logger.error(
                    "EMAIL_SERVICE_CONNECTION_STRING is missing or not configured."
                )
                return
            
            singleton_email_client = EmailClient.from_connection_string(
                EMAIL_SERVICE_CONNECTION_STRING
            )
    return singleton_email_client
