from app.database import AsyncSessionFactory
from app.api.github import get_installation_repositories
from app.crud.github_repository import create_github_repository, delete_github_repository_on_github_id, get_github_repository
from app.crud.organization import get_organization_id_from_github_id
from app.services.installation_token_service import fetch_installation_token_installid
from app.dependencies import logger

async def add_repository_service(payload):
    installation = payload.get("installation", {}) or {}
    installation_id = installation.get("id")
    org_github_id = installation.get("account", {}).get("id")

    if not installation_id or not org_github_id:
        logger.error("Missing installation or organization details in payload")
        return

    async with AsyncSessionFactory() as db_session:
        try:
            # DB: fetch token (likely stored/derived via DB)
            token = await fetch_installation_token_installid(
                db_session=db_session, installation_id=installation_id
            )
            if not token or not token.get("access_token"):
                logger.error("Failed to fetch installation token")
                return

            # External: fetch repositories from GitHub
            result_repos = await get_installation_repositories(
                access_token=token["access_token"]
            )
            result_repos_ids = [repo["id"] for repo in result_repos]

            # DB: org details and existing repos
            org_details = await get_organization_id_from_github_id(
                db_session=db_session, platform_type_id=1, platform_id=int(org_github_id)
            )

            existing_repos = await get_github_repository(
                db_session=db_session, organization_id=org_details["id"]
            )
            existing_repos_ids = [repo.get("github_id") for repo in existing_repos]

            # DB: delete repos no longer selected
            for repo in existing_repos:
                if repo["github_id"] not in result_repos_ids:
                    await delete_github_repository_on_github_id(
                        db_session=db_session, github_id=repo["github_id"]
                    )

            # DB: insert new repos
            for repo in result_repos:
                if repo["id"] not in existing_repos_ids:
                    await create_github_repository(
                        db_session=db_session,
                        github_id=repo["id"],
                        repo_name=repo["name"],
                        repo_full_name=repo["full_name"],
                        github_html_url=repo["html_url"],
                        organization_id=org_details["id"],
                    )

            await db_session.commit()
            logger.info(
                "Successfully updated repositories",
                extra={"organization_id": org_details["id"]},
            )
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error updating repositories: {e}")
            return
    

async def remove_repository_service(payload):
    repos_removed = payload.get("repositories_removed", []) or []
    repos_removed_ids = [repo.get("id") for repo in repos_removed if repo.get("id")]

    if not repos_removed_ids:
        logger.info("No repositories to remove in payload.")
        return

    async with AsyncSessionFactory() as db_session:
        try:
            for repo_id in repos_removed_ids:
                await delete_github_repository_on_github_id(
                    db_session=db_session, github_id=repo_id
                )
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            logger.error(f"Error removing repositories: {e}")
            return
