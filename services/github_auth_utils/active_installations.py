from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.github import get_github_organizations
from app.crud.github_oauth_token import get_oauth_token
from app.crud.github_user import get_github_id_from_user_id
from app.crud.organization import get_organization_id_installation_id
from app.crud.payments import add_user_plan_assignments, get_pre_purchased_user_organization_id, mark_pre_purchased_user_claimed
from app.crud.user_organization import create_user_organization_link_bulk

from app.dependencies import logger

async def sync_installations(db_session: AsyncSession, user_id: str):
    active_installations = []

    # Step1: Fetch all orgs of user from github
    try:
        github_user_id = await get_github_id_from_user_id(db_session, user_id)
        token_dict = await get_oauth_token(db_session, int(github_user_id))

        orgs_data = await get_github_organizations(token_dict["access_token"], user_id)

        github_org_ids = [
            org.get("organization", {}).get("id")
            for org in orgs_data
            if org.get("organization") and org.get("state") == "active"
        ]

        github_org_roles = {
            org.get("organization", {}).get("id"): org.get("role")
            for org in orgs_data
            if org.get("organization") and org.get("state") == "active"
        }

        if not github_org_ids:
            logger.info("No active github orgs found for user", extra={"user_id": user_id})
            return

        if not all(isinstance(org_id, int) for org_id in github_org_ids):
            logger.error(f"Invalid org ids received: {github_org_ids}", extra={"user_id": user_id})
            return
    except Exception as e:
        logger.error(f"Error occurred while fetching github orgs: {str(e)}", extra={"user_id": user_id})
        return

    try:
        # Step2: From github orgs, check which are active installations and return
        active_installations = await get_organization_id_installation_id(db_session, github_org_ids)

        # Step3: Insert the user_id, org_id, role tuples in user_organization table
        user_org_data = []
        if active_installations:
            for installation in active_installations:
                user_org_data.append({
                    "user_id": user_id,
                    "organization_id": installation["organization_id"],
                    "role": github_org_roles.get(int(installation["platform_id"])),
                    "type": installation["type"],
                })

            await create_user_organization_link_bulk(db_session, user_org_data)
            await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error occurred while syncing installations: {str(e)}", extra={"user_id": user_id})
        return

    try:
        # Step4: Check if exists in pre_purchased_users and move to user_order
        pre_purchased_data = await get_pre_purchased_user_organization_id(db_session, int(github_user_id))
        if pre_purchased_data:
            for data in pre_purchased_data:
                await add_user_plan_assignments(
                    db_session=db_session,
                    user_ids=[user_id],
                    organization_id=data["organization_id"],
                    order_id=data["order_id"],
                    assigned_at=datetime.now(timezone.utc),
                    end_date=data["end_date"],
                )
                await mark_pre_purchased_user_claimed(
                    db_session=db_session,
                    claimed_github_ids=[int(github_user_id)],
                    order_id=data["order_id"],
                )

            logger.info("Pre-purchased data of user synced successfully", extra={"user_id": user_id})

            await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error occurred while checking pre_purchased status: {str(e)}", extra={"user_id": user_id})
        return

    return user_org_data
