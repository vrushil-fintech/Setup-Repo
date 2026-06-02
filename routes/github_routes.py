from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.github import get_github_organization_members, get_installation_repositories
from app.crud.github_installation import (
    get_github_installation,
)
from app.crud.github_repository import get_github_repository
from app.crud.github_user import get_github_id_from_user_id, get_user_id_from_github_id
from app.crud.organization import get_organization
from app.crud.user_organization import (
    get_organization_id_for_user_id,
    get_user_id_role_for_organization_id
)
from app.crud.users import get_user, get_user_by_id
from app.crud.payments import get_plan_status_for_github_user, get_user_order_details
from app.database import get_db
from app.dependencies import logger
from app.middleware.cookie_verification import cookie_verification
from app.services.installation_token_service import fetch_installation_token_installid

router = APIRouter()


@router.get("/github/repositories/{organization_id}")
async def github_repositories(
    organization_id: str,
    db_session: AsyncSession = Depends(get_db),
    email: str = Depends(cookie_verification),
):
    try:
        repositories = await get_github_repository(
            db_session=db_session, organization_id=organization_id
        )
        if not repositories:
            installation_id = await get_github_installation(db_session=db_session, organization_id=organization_id)
            if not installation_id:
                logger.error(f"No active installation found for org: {organization_id}")
                return

            token = await fetch_installation_token_installid(db_session=db_session, installation_id=installation_id)
            if not token:
                logger.error(f"Failed to fetch installation token")
                return

            result_repos = await get_installation_repositories(access_token=token["access_token"])
            if not result_repos:
                return []

            repositories = []
            for repo in result_repos:
                repositories.append({
                    "github_id": repo.get("id"),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "github_html_url": repo.get("html_url")
                })

        return repositories
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="We're having trouble finding your repositories. Please try again later.",
        )


@router.post("/user_org_details")
async def dashboard(
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
):
    user = await get_user(db_session, email)
    try:
        organization_ids = await get_organization_id_for_user_id(
            db_session, user.userid
        )
        user_org_details = []
        if not organization_ids:
            return []

        for org_id, role in organization_ids:
            org_details = await get_organization(db_session, org_id)
            if org_details:
                installation_id = await get_github_installation(db_session, org_id)
                user_org_details.append(
                    {
                        "installation_id": installation_id,
                        "organization_id": org_id,
                        "organization_name": org_details["name"],
                        "organization_type": org_details["type"],
                        "role": role,
                    }
                )
            else:
                logger.error(f"failed to get organization id")
                raise HTTPException(
                    status_code=503,
                    detail="We're having trouble finding your organizations. Please try again later.",
                )

        return user_org_details

    except Exception as e:
        logger.error(f"Failed to fetch user_org_details: {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble finding your organizations. Please try again later.",
        )


@router.get("/organization_members/{organization_id}")
async def organization_members(
    organization_id: str,
    db_session: AsyncSession = Depends(get_db),
    email: str = Depends(cookie_verification),
):
    github_org_members = []
    try:
        organization = await get_organization(db_session, organization_id)

        if organization["type"].lower() == "user":
            users_data = await get_user_id_role_for_organization_id(
                db_session=db_session, organization_id=organization_id
            )
            for user_d in users_data:
                user = await get_user_by_id(db_session=db_session, user_id=user_d["user_id"])
                user_github_id = await get_github_id_from_user_id(
                    db_session=db_session, user_id=user_d["user_id"]
                )
                order_details = await get_user_order_details(
                    db_session,
                    user_id=user.userid,
                    organization_id=organization_id,
                )
                github_org_members.append(
                    {
                        "name": user.name,
                        "github_id": user_github_id,
                        "role": user_d["role"],
                        "has_logged_in": True,
                        "plan_status": order_details["status"],
                    }
                )

            return github_org_members

        else:
            installation_id = await get_github_installation(db_session, organization_id)
            if not installation_id:
                logger.error(f"No installation found for org: {organization_id}")
                raise Exception(detail="No installation found")
            token = await fetch_installation_token_installid(
                db_session=db_session, installation_id=installation_id
            )
            if not token:
                logger.error(f"Failed to fetch installation token for org: {organization_id}")
                raise Exception(detail="Failed to fetch installation token")

            result_data = await get_github_organization_members(
                access_token=token["access_token"],
                organization=organization,
            )

            if result_data:
                for member in result_data:
                    github_id = member.get('id')
                    role = member.get('role')
                    name = member.get('login')

                    user_id = await get_user_id_from_github_id(
                        db_session=db_session, github_id=int(github_id)
                    )
                    has_logged_in = user_id is not None

                    member_data = {
                        'name': name,
                        'github_id': github_id,
                        'role': role,
                        'has_logged_in': has_logged_in
                    }

                    plan_status_info = await get_plan_status_for_github_user(
                        db_session=db_session,
                        github_id=github_id,
                        has_logged_in=has_logged_in,
                        organization_id=organization_id
                    )
                    member_data['plan_status'] = plan_status_info.get('status')

                    github_org_members.append(member_data)

            return github_org_members

    except Exception as e:
        logger.error(f"Error occurred while fetching org members: {e}", extra={"organization_id": organization_id})
        raise HTTPException(status_code=503, detail="We're having trouble fetching organization members. Please try again later.")
