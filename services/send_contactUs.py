from app.config import EMAIL_SERVICE_CONNECTION_STRING, EMAIL_SENDER_ADDRESS, CONTACT_US_RECEIVER_EMAIL
from app.dependencies import logger
from azure.communication.email import EmailClient
from fastapi import HTTPException

async def send_contact_us(name: str, email: str, message_content: str):
    connection_string = EMAIL_SERVICE_CONNECTION_STRING
    message = {
        "content": {
            "subject": "[CodeSherlock] New Contact Us Submission",
            "plainText": f"""
                            You have received a new contact us submission.

                            Name: {name}
                            Email: {email}
                            Message: {message_content}
                            
                            Please respond to this inquiry at your earliest convenience.
                            """
        },
        "recipients": {
            "to": [
                {
                    "address": CONTACT_US_RECEIVER_EMAIL,
                }
            ]
        },
        "senderAddress": EMAIL_SENDER_ADDRESS,
    }
    try:
        client = EmailClient.from_connection_string(connection_string)
        poller = client.begin_send(message)
        result = poller.result()
    except Exception as e:
        logger.error("Error occurred while sending contact info: %s", e, extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having trouble sending your message. Please try again later.")
    return