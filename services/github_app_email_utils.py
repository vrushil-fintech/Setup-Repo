from app.config import EMAIL_SERVICE_CONNECTION_STRING, EMAIL_SENDER_ADDRESS
from app.dependencies import logger
from azure.communication.email import EmailClient
from fastapi import HTTPException
from jinja2 import Environment, FileSystemLoader
from app.config import FRONTEND_URL


template_loader = FileSystemLoader("app/templates")
jinja_env = Environment(loader=template_loader)

dashboard_url = f"{FRONTEND_URL}/dashboard"


async def send_github_app_install_email(email: str, github_username: str):
    connection_string = EMAIL_SERVICE_CONNECTION_STRING
    template = jinja_env.get_template("GithubAppInstallTemplate.html")
    html_content = template.render(GitHub_Username=github_username)

    message = {
        "content": {
            "subject": "Welcome to CodeSherlock — Let’s Ship Cleaner Code Together!",
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
        client = EmailClient.from_connection_string(connection_string)
        poller = client.begin_send(message)
        result = poller.result()
    except Exception as e:
        logger.error("Error occurred while sending code: %s", e, extra={"email": email})
        raise HTTPException(
            status_code=503,
            detail="We're having truble sending installation email. Please try again later.",
        )
    return


async def send_usage_email(
    email: str, username: str, tokens_left: int, percentage_remaining: int
):
    connection_string = EMAIL_SERVICE_CONNECTION_STRING
    template = jinja_env.get_template("UsageEmailTemplate.html")
    html_content = template.render(
        username=username,
        tokens_left=tokens_left,
        percentage_remaining=percentage_remaining,
        dashboard_url=dashboard_url,
    )

    message = {
        "content": {
            "subject": "Your CodeSherlock Usage",
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
        client = EmailClient.from_connection_string(connection_string)
        poller = client.begin_send(message)
        result = poller.result()
    except Exception as e:
        logger.error("Error occurred while sending code: %s", e, extra={"email": email})
        raise HTTPException(
            status_code=503,
            detail="We're having truble sending usage email. Please try again later.",
        )
    return

