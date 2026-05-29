from app.config import EMAIL_SERVICE_CONNECTION_STRING, EMAIL_SENDER_ADDRESS
from app.dependencies import logger
from app.services.email_client import get_email_client
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader

template_loader = FileSystemLoader("app/templates")
jinja_env = Environment(loader=template_loader)

async def send_code(email: str, code: str, code_type: str):
    connection_string = EMAIL_SERVICE_CONNECTION_STRING
    template = jinja_env.get_template("OTPEmailTemplate.html")
    html_content = template.render(otp=code)
    
    message = {
        "content": {
            "subject": "Let's Verify Your CodeSherlock Account!",
            "html": html_content,
        },
        "recipients": {
            "to": [
                {
                    "address": email,
                }
            ]
        },
        "senderAddress": EMAIL_SENDER_ADDRESS,
    }
    try:
        client = get_email_client()
        poller = client.begin_send(message)
        result = poller.result()
    except Exception as e:
        logger.error("Error occurred while sending code: %s", e, extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having truble sending your code. Please try again later.")
    return