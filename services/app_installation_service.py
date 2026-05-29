from app.api.github import get_installation_repositories
from app.crud.github_repository import create_github_repository, delete_github_repository_on_organization_id
from app.crud.github_user import get_user_id_from_github_id
from app.crud.organization import create_organization, get_organization_id_from_github_id
from app.crud.github_installation import create_github_installation, delete_github_installation
from app.crud.user_organization import create_user_organization_link, delete_user_organization_link
from app.database import AsyncSessionFactory
from app.dependencies import logger

from app.services.installation_token_service import fetch_installation_token_installid
from app.services.github_app_email_utils import send_github_app_install_email
from app.crud.users import get_user_by_id


async def handle_app_installation(payload):
    installation = payload.get("installation", {})
    installation_id = installation.get("id")
    if not installation_id:
        logger.error("Missing installation ID in webhook payload.")
        return

    account = installation.get("account", {})
    account_id = account.get("id")
    account_type = account.get("type")
    account_login = account.get("login")

    if not account_id or not account_type or not account_login:
        logger.error("Missing account details in payload", extra={"installation_id": installation_id})
        return

    if account_type == "Organization":
        logger.info("Organization installation detected.", extra={"account_id": account_id})
        if payload.get("requester"):
            github_id = payload.get("requester", {}).get("id")
            account_role = "member"
        else:
            github_id = payload.get("sender", {}).get("id")
            account_role = "admin"
    elif account_type == "User":
        logger.info("User installation detected.", extra={"account_id": account_id})
        github_id = account_id
        account_role = "admin"
    else:
        logger.error("Unknown account type", extra={"account_type": account_type})
        return

    requester = payload.get("requester", {})
    sender = payload.get("sender", {})

    async with AsyncSessionFactory() as db_session:
        try:
            organization_details = await get_organization_id_from_github_id(db_session, 1, int(account_id))
            if not organization_details:
                await create_organization(db_session, account_login, account_type, 1, int(account_id))
                organization_details = await get_organization_id_from_github_id(db_session, 1, int(account_id))

            token_dict = await fetch_installation_token_installid(db_session, installation_id)

            await create_github_installation(
                db_session,
                organization_details["id"],
                int(installation_id),
                token_dict["access_token"],
                token_dict["expires_at"],
            )

            user_id = await get_user_id_from_github_id(db_session, int(github_id))
            await create_user_organization_link(db_session, user_id, organization_details["id"], account_role)

            repositories = await get_installation_repositories(token_dict["access_token"])
            for repo in repositories:
                await create_github_repository(
                    db_session=db_session,
                    repo_name=repo["name"],
                    repo_full_name=repo["full_name"],
                    github_id=repo["id"],
                    organization_id=organization_details["id"],
                    github_html_url=repo["html_url"],
                )

            await db_session.commit()

            user = await get_user_by_id(db_session, user_id)

        except Exception as e:
            await db_session.rollback()
            logger.error(
                f"Error occurred while handling github app installation {e}",
                extra={"account_id": account_id, "installation_id": installation_id},
            )
            return

    github_username = requester.get("login", "") if payload.get("requester") else sender.get("login", "")
    await send_github_app_install_email(user.email, github_username)


async def handle_app_uninstallation(payload):
    installation = payload.get("installation", {}) or {}
    installation_id = installation.get("id")
    org_github_id = installation.get("account", {}).get("id")

    if not installation_id:
        logger.error("Missing installation ID in webhook payload.")
        return

    async with AsyncSessionFactory() as db_session:
        try:
            organization = await get_organization_id_from_github_id(db_session, 1, int(org_github_id))
            await delete_github_installation(db_session, installation_id)
            await delete_github_repository_on_organization_id(
                db_session=db_session,
                organization_id=organization["id"],
            )
            await db_session.commit()
        except Exception as e:
            await db_session.rollback()
            logger.error(
                f"Failed to delete github user installation {e}",
                extra={"account_id": org_github_id, "installation_id": installation_id},
            )
