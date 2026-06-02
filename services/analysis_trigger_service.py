import re

from app.api.pr_details import get_pull_request_details
from app.config import GITHUB_APP_ID
from app.database import AsyncSessionFactory
from app.services.installation_token_service import fetch_installation_token_installid
from app.services.pr_review_pipeline import pr_review_pipeline
from app.dependencies import logger


async def trigger_analysis_from_pr(payload):
    pr_data = payload.get("pull_request", {})
    sender = payload.get("sender", {})
    repo_data = payload.get("repository", {})
    installation_id = payload.get("installation", {}).get(
        "id"
    )  # Extract installation ID
    factor = "power_analysis"

    try:
        pr_details = {
            "title": pr_data.get("title"),
            "number": pr_data.get("number"),
            "state": pr_data.get("state"),
            "created_at": pr_data.get("created_at"),
            "updated_at": pr_data.get("updated_at"),
            "merged": pr_data.get("merged", False),
            "url": pr_data.get("html_url"),
            "base_branch": pr_data.get("base", {}).get("ref"),
            "head_branch": pr_data.get("head", {}).get("ref"),
            "base_sha": pr_data.get("base", {}).get("sha"),
            "head_sha": pr_data.get("head", {}).get("sha"),
            "github_user_id": sender.get("id", None),
            "github_username": sender.get("login", None),
            "requested_reviewers": pr_data.get("requested_reviewers", []),
        }
    except Exception as e:
        logger.error(f"Failed to extract PR details: {str(e)}")
        return

    await pr_review_pipeline(pr_details, repo_data, installation_id, factor)
    return


async def trigger_analysis_from_comment(payload):
    comment_body = payload["comment"]["body"].strip()

    # Match pattern like "/pr-bot analyze security"
    pattern = rf"^@{re.escape(GITHUB_APP_ID)}\s+analyze\s+(\w+)"
    match = re.match(pattern, comment_body, re.IGNORECASE)

    if not match:
        return

    factor = match.group(1).lower()
    if factor not in ["owasp", "cwe_mitre", "cwe_kev"]:
        return

    repo_data = payload.get("repository", {})
    sender = payload.get("sender", {})
    installation_id = payload["installation"]["id"]
    async with AsyncSessionFactory() as db_session:
        try:
            token = await fetch_installation_token_installid(db_session, int(installation_id))
            await db_session.commit()
            if not token:
                return
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Failed to fetch installation token: {str(e)}")
            return

    pr_url = payload["issue"]["pull_request"]["url"]

    pr_data = await get_pull_request_details(
        access_token=token["access_token"], pr_url=pr_url
    )
    try:
        pr_details = {
            "title": pr_data.get("title"),
            "number": pr_data.get("number"),
            "state": pr_data.get("state"),
            "created_at": pr_data.get("created_at"),
            "updated_at": pr_data.get("updated_at"),
            "merged": pr_data.get("merged", False),
            "url": pr_data.get("html_url"),
            "base_branch": pr_data.get("base", {}).get("ref"),
            "head_branch": pr_data.get("head", {}).get("ref"),
            "base_sha": pr_data.get("base", {}).get("sha"),
            "head_sha": pr_data.get("head", {}).get("sha"),
            "github_user_id": sender.get("id", None),
            "github_username": sender.get("login", None),
            "requested_reviewers": pr_data.get("requested_reviewers", []),
        }
    except Exception as e:
        logger.error(f"Failed to extract PR details: {str(e)}")
        return

    # Trigger your custom analysis logic
    await pr_review_pipeline(pr_details, repo_data, installation_id, factor)
    return
