from fastapi import Request, Header, APIRouter, BackgroundTasks, Depends
from app.services.analysis_trigger_service import (
    trigger_analysis_from_comment,
    trigger_analysis_from_pr,
)
from app.services.app_installation_service import (
    handle_app_installation,
    handle_app_uninstallation,
)
from app.services.repository_updation_service import (
    add_repository_service,
    remove_repository_service,
)
from app.services.webhook_services import verify_signature
from app.services.marketplace_order_service import handle_marketplace_order
from app.dependencies import logger

router = APIRouter()


@router.post("/auth/github/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    # Verify signature
    await verify_signature(request)

    payload = await request.json()

    action = payload.get("action", "")
    logger.info(f"Event: {x_github_event} with action {action} received on webhook")

    if x_github_event == "pull_request" and payload.get("action") == "opened":
        logger.info("PR event received on webhook")
        # Add processing to background task
        background_tasks.add_task(trigger_analysis_from_pr, payload)
        return {"message": "PR event received and processing started"}

    elif x_github_event == "installation":
        if payload.get("action") == "created":
            logger.info("Installation created event received on webhook")
            background_tasks.add_task(handle_app_installation, payload)
            return {"message": "App installed"}

        elif payload.get("action") in ["deleted", "revoked"]:
            logger.info("Installation deleted event received on webhook")
            background_tasks.add_task(handle_app_uninstallation, payload)
            return {"message": "App uninstalled, cleanup started"}

    elif x_github_event == "issue_comment" and payload["action"] == "created":
        logger.info("Issue comment event received on webhook")
        background_tasks.add_task(trigger_analysis_from_comment, payload)
        return {"message": "Issue comment event received"}

    elif x_github_event == "installation_repositories":
        if payload["action"] == "added":
            logger.info("Installation repositories event received on webhook")
            background_tasks.add_task(add_repository_service, payload)
        elif payload["action"] == "removed":
            logger.info("Installation repositories event received on webhook")
            background_tasks.add_task(remove_repository_service, payload)
        else:
            logger.warning(
                f"Installation repositories event with unknown action {payload['action']} received on webhook"
            )

    elif x_github_event == "marketplace_purchase":
        if action == "purchased":
            background_tasks.add_task(handle_marketplace_order, payload)

        return {"message": "Installation repositories event received"}

    return {"message": "Not a PR event"}
