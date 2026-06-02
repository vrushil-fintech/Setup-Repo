import asyncio
from app.api.pr_details import post_pull_request_comment
from app.crud.github_installation import get_github_installation_token




async def notify_reviewers(payload, db_session):
    pr_data = payload.get("pull_request", {})
    repo_data = payload.get("repository", {})
    repo_owner = repo_data.get("owner", {})
    installation_id = payload.get("installation", {}).get(
        "id"
    )  # Extract installation ID

    pr_details = {
        "title": pr_data.get("title"),
        "number": pr_data.get("number"),
        "state": pr_data.get("state"),
        "created_at": pr_data.get("created_at"),
        "updated_at": pr_data.get("updated_at"),
        "merged": pr_data.get("merged", False),
        "url": pr_data.get("html_url"),
        "base_sha": pr_data.get("base", {}).get("sha"),
        "head_sha": pr_data.get("head", {}).get("sha"),
    }

    pr_reviewers = [
        reviewer.get("login") for reviewer in pr_data.get("requested_reviewers", [])
    ]

    pr_details["reviewers"] = pr_reviewers

    # Get the stored GitHub installation token
    token = await get_github_installation_token(
        db_session=db_session,
        installation_id=int(installation_id)
    )

    await asyncio.gather(
        *[
            post_pull_request_comment(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                f"@{reviewer} **CodeSherlock.AI** has completed its review. ✅",
                token["access_token"],
            )
            for reviewer in pr_details["reviewers"]
        ]
    )
