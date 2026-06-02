from app.dependencies import logger
from app.crud.users import insert_user, get_user
from app.crud.github_user import create_github_user, get_github_id_from_user_id
from app.services.order_handler_service import sync_order_status
from app.crud.organization import (
    create_organization,
    get_organization_id_from_github_id,
)
from app.database import AsyncSessionFactory
import uuid


async def handle_marketplace_order(payload: dict):
    action = payload.get("action")
    user = None

    async with AsyncSessionFactory() as db_session:
        try:
            # Extract details
            sender_details = extract_sender_details(payload)
            account_details = extract_account_details(payload)
            plan_details = extract_plan_details(payload)

            # User: get or create
            user = await get_user(db_session, sender_details["email"])
            if not user:
                userid = str(uuid.uuid4())
                await insert_user(
                    db_session,
                    userid,
                    sender_details["login"],
                    sender_details["email"],
                    "hashed_password",
                    account_details["login"],
                )
                user = await get_user(db_session, sender_details["email"])
            logger.info(f"User fetched or created successfully: {user.userid}")

            # Ensure github_user
            github_user_id = await get_github_id_from_user_id(db_session, user.userid)
            if not github_user_id:
                logger.info(f"creating github user for {user.userid}")
                await create_github_user(db_session, user.userid, sender_details["id"], sender_details["login"])

            # Organization: get or create
            organization_details = await get_organization_id_from_github_id(db_session, 1, account_details["id"])
            if not organization_details:
                logger.info(f"Organization not found, creating new organization: {account_details['login']}")
                await create_organization(db_session, account_details["login"], account_details["type"], 1, account_details["id"])
                organization_details = await get_organization_id_from_github_id(db_session, 1, account_details["id"])
                logger.info(f"Organization created: {organization_details}")
            else:
                logger.info(f"Organization already exists: {organization_details}")

            # Business logic
            logger.info(
                "Marketplace action '%s' by '%s' for account '%s' on plan '%s'",
                action,
                sender_details.get('login', 'unknown'),
                account_details.get('login', 'unknown'),
                plan_details.get('name', 'unknown')
            )

            await sync_order_status(
                db_session=db_session,
                user_id=user.userid,
                org_id=organization_details["id"],
            )

            # Commit once at the end
            await db_session.commit()
            logger.info("Marketplace order handled successfully")

        except Exception as e:
            await db_session.rollback()
            logger.error(f"Failed to handle marketplace order: {str(e)}. Action: {action}, User: {user.userid if user else 'None'}")

def extract_sender_details(payload: dict) -> dict:
    sender = payload.get("sender", {})
    return {
        "login": sender.get("login"),
        "id": sender.get("id"),
        "type": sender.get("type"),
        "email": sender.get("email"),
        "html_url": sender.get("html_url"),
    }

def extract_account_details(payload: dict) -> dict:
    account = payload.get("marketplace_purchase", {}).get("account", {})
    return {
        "type": account.get("type"),
        "login": account.get("login"),
        "id": account.get("id"),
        "node_id": account.get("node_id"),
        "organization_billing_email": account.get("organization_billing_email"),
    }

def extract_plan_details(payload: dict) -> dict:
    plan = payload.get("marketplace_purchase", {}).get("plan", {})
    return {
        "id": plan.get("id"),
        "name": plan.get("name"),
        "description": plan.get("description"),
        "monthly_price_in_cents": plan.get("monthly_price_in_cents"),
        "yearly_price_in_cents": plan.get("yearly_price_in_cents"),
        "price_model": plan.get("price_model"),
        "has_free_trial": plan.get("has_free_trial"),
    }