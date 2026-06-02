import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.payments import fetch_subscription_summary
from app.crud.usage import reset_token_usage_user_id_org_id
from app.dependencies import logger
from datetime import datetime, timezone
from app.crud.payments import (
    add_user_plan_assignments,
    get_user_order_details,
    inactive_pre_purchased_user_details,
    inactive_user_order_details,
    insert_order_new,
    get_user_order_details,
    update_user_plan_end_date,
)


async def sync_order_status(db_session: AsyncSession, user_id: str, org_id: str):
    # Step 1: Get internal DB status
    if org_id in ("null", ""):
        org_id = None

    user_order = await get_user_order_details(db_session, user_id, org_id)
    order_id = user_order["order_id"]
    end_date_str = user_order["end_date"]
    plan = user_order.get("plan")

    if plan == None:
        created_at = datetime.now(timezone.utc)
        # Insert order
        order_id = str(uuid.uuid4())
        status = "free"

        order_id = await insert_order_new(
            db_session=db_session,
            order_id=order_id,
            user_id=user_id,
            plan_id="c7feaa58-f9d1-4511-82c5-c04d2b20ffcb",
            status=status,
            created_at=created_at,
            seats=1,
            organization_id=org_id,
        )

        assigned_at = datetime.now(timezone.utc)
        await add_user_plan_assignments(
            db_session=db_session,
            user_ids=[user_id],
            organization_id=org_id,
            order_id=order_id,
            assigned_at=assigned_at,
            end_date=None,
        )

        await db_session.commit()

        return {
            "status": "free",
            "end_date": None,
            "plan": {
                "plan_id": "c7feaa58-f9d1-4511-82c5-c04d2b20ffcb",
                "plan_name": "free",
                "plan_type": "free",
            },
        }

    elif plan["plan_name"] == "free":
        return {
            "status": "free",
            "end_date": None,
            "plan": plan,
        }

    # Step 2: If paid plan, Get external subscription status from Stripe
    end_date = datetime.fromisoformat(end_date_str) if end_date_str else None
    now = datetime.now(timezone.utc)  # Changed from datetime.utcnow()

    # Step 2a: If end_date of plan is not reached, return
    if end_date and end_date > now:
        return {
            "status": "active",
            "end_date": end_date_str,
            "plan": plan,
        }

    # Step 2b: If end_date of plan is reached, check Stripe status
    else:
        subscription_data = await fetch_subscription_summary(order_id)
        stripe_status = subscription_data.get("status")
        stripe_end_date = subscription_data.get("current_period_end")

        logger.info(
            "Order %s: Stripe status = %s, DB end_date = %s, Stripe end_date = %s",
            order_id,
            stripe_status,
            end_date_str,
            stripe_end_date,
        )

        if stripe_status == "active":
            stripe_end_date_str = subscription_data.get("current_period_end")
            stripe_end_date = datetime.fromisoformat(stripe_end_date_str)
            if stripe_end_date > now:
                updated = await update_user_plan_end_date(
                    db_session=db_session,
                    user_id=user_id,
                    organization_id=org_id,
                    new_end_date=stripe_end_date,
                )
                await db_session.commit()

                # If previous end_date was present (it would be null for existing paid users)
                if updated and end_date:
                    # reset token usage of user as order renewed
                    await reset_token_usage_user_id_org_id(
                        db_session=db_session, user_id=user_id, organization_id=org_id
                    )
                    await db_session.commit()

                    return {
                        "status": "active",
                        "end_date": stripe_end_date_str,
                        "plan": plan,
                    }

                else:
                    return {
                        "status": "active",
                        "end_date": stripe_end_date_str,
                        "plan": plan,
                    }
        
        # if order is not active
        else:
            await inactive_user_order_details(
                db_session=db_session, order_id=order_id
            )
            await inactive_pre_purchased_user_details(
                db_session=db_session, order_id=order_id
            )

            await db_session.commit()

            return {
                "status": "free",
                "end_date": end_date_str,
                "plan": {
                    "plan_id": "c7feaa58-f9d1-4511-82c5-c04d2b20ffcb",
                    "plan_name": "free",
                    "plan_type": "free",
                },
            }
