from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, BackgroundTasks, Form, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.crud.github_user import get_user_ids_from_github_ids
from app.crud.usage import reset_token_usage_user_id_org_id
from app.database import get_db
from app.dependencies import logger
from app.crud.payments import (
    get_order_details_by_user_id_org_id,
    get_plan,
    insert_order_new,
    insert_order_prepurchased,
    update_order_status,
    update_order_plan_by_order_id,
    update_order_status,
    activate_pre_purchased_users_by_order_id,
    add_user_plan_assignments,
    mark_pre_purchased_user_claimed,
)
from app.api.payments import (
    call_checkout_api,
    call_session_api,
    cancel_order,
    upgrade_plan,
    upcoming_order_details,
    fetch_subscription_summary,
)
from app.middleware.cookie_verification import cookie_verification
from fastapi import HTTPException

from app.services.order_handler_service import sync_order_status

router = APIRouter()

@router.post("/order/handle")
async def order_handler(
    user_id: str = Form(...),
    org_id: Optional[str] = Form(default=None),
    db_session: AsyncSession = Depends(get_db),
):
    try:
        order_details = await get_order_details_by_user_id_org_id(db_session, user_id, org_id)
        order_id = order_details["order_id"]
        updated_at = datetime.now(timezone.utc)

        # Retrieve subscription status
        subscription_data = await fetch_subscription_summary(order_id)
        new_status = subscription_data.get("status")

        logger.info("Subscription status retrieved for order %s: %s", order_id, new_status)

        # If purchaser made a successful transaction
        if order_details["status"] == "pending" and new_status == "active":
            stripe_end_date = subscription_data.get("current_period_end")
            end_date = datetime.fromisoformat(stripe_end_date) if stripe_end_date else None
            await update_order_status(db_session, order_id, new_status)
            activated_users_details = await activate_pre_purchased_users_by_order_id(
                db_session, order_id, end_date
            )

            # mark existing users claimed
            github_ids = [user["github_id"] for user in activated_users_details]

            user_id_github_map = await get_user_ids_from_github_ids(db_session, github_ids)
            user_ids = list(user_id_github_map.keys())
            claimed_github_ids = list(user_id_github_map.values())

            period_end = subscription_data.get("current_period_end")

            assigned_at = datetime.now(timezone.utc)
            end_date = (
                datetime.strptime(period_end, "%Y-%m-%dT%H:%M:%SZ") if period_end else None
            )

            await mark_pre_purchased_user_claimed(db_session, claimed_github_ids, order_id)

            # Assign plan to each user
            await add_user_plan_assignments(
                db_session=db_session,
                user_ids=user_ids,
                organization_id=org_id,
                order_id=order_id,
                assigned_at=assigned_at,
                end_date=end_date,
            )

            # reset existing users' usage to 0
            for user_id in user_ids:
                await reset_token_usage_user_id_org_id(db_session, user_id, org_id)

            await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while updating order status {e}", extra={"user_id": user_id, "organization_id": org_id})
        raise HTTPException(status_code=503, detail="We are having trouble updating order status. Please try again later.")


@router.post("/order/status")
async def order_handler(
    user_id: str = Form(...),
    org_id: str = Form(...),
    db_session: AsyncSession = Depends(get_db),
):
    try:
        response = await sync_order_status(
            db_session=db_session, user_id=user_id, org_id=org_id
        )
        return response
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while fetching order status {e}", extra={"user_id": user_id, "organization_id": org_id})
        raise HTTPException(status_code=503, detail="We are having trouble fetching your order status. Please try again later.")


@router.post("/order/upgrade")
async def order_handler(
    request: Request,
    order_id: str = Form(),
    plan_name: str = Form(),
    interval: str = Form(),
    amount: float = Form(),
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
):
    price_name = f"Fixed Amount {int(amount)}"
    updated_at = datetime.now(timezone.utc)
    response = await upgrade_plan(plan_name, price_name, interval, amount, order_id)
    await update_order_plan_by_order_id(db_session, order_id)
    await db_session.commit()

    result = await upcoming_order_details(order_id)
    logger.info("Order upgraded: %s", result)
    return result


@router.post("/order/cancel")
async def order_cancel(
    request: Request,
    order_id: str = Form(),
    plan_name: str = Form(),
    email: str = Depends(cookie_verification),
):

    result = await cancel_order(order_id, plan_name)

    logger.info("Order cancelled: %s", order_id)
    end = result["current_period_end"]
    return {"status": "success", "end": end, "message": "Order cancelled successfully."}


@router.get("/plans")
async def plan(
    request: Request,
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
):
    result = await get_plan(db_session)
    logger.info("Plans retrieved")
    return result


@router.post("/order/create")
async def order_handler(
    request: Request,
    user_id: str = Form(),
    plan_id: str = Form(),
    customer_email: str = Form(),
    customer_name: str = Form(),
    plan_name: str = Form(),
    interval: str = Form(),
    amount: float = Form(),
    redirect_url: str = Form(),
    seats: int = Form(),
    github_ids: Optional[str] = Form(default=None),
    org_id: str = Form(),
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
):
    if plan_name != "Standard Plan":
        logger.error(f"Invalid plan name received: {plan_name}", extra={"user_id": user_id, "organization_id": org_id})
        return HTTPException(status_code=400, detail="Invalid plan name.")

    if not github_ids:
        logger.error(f"No github_ids received: {github_ids}", extra={"user_id": user_id, "organization_id": org_id})
        return HTTPException(status_code=400, detail="No github_ids received.")


    # Parse github_ids string to list of ints
    github_ids_list = []
    try:
        github_ids_list = [
            int(x.strip()) for x in github_ids.split(",") if x.strip().isdigit()
        ]
    except Exception as e:
        logger.error(f"Invalid github_ids received: {github_ids}", extra={"user_id": user_id, "organization_id": org_id})
        return HTTPException(status_code=400, detail="Invalid github_ids received.")

    try:
        order_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        price_name = f"Fixed Amount {amount}"

        # Call checkout API before DB insert
        checkout_api_result = await call_checkout_api(
            customer_email=customer_email,
            customer_name=customer_name,
            plan_name=plan_name,
            price_name=price_name,
            interval=interval,
            amount=amount,
            order_id=order_id,
            user_id=user_id,
            redirect_url=redirect_url,
            seats=seats,
        )
        status = "pending"

        # Insert order
        order_id = await insert_order_new(
            db_session=db_session,
            order_id=order_id,
            user_id=user_id,
            plan_id=plan_id,
            status=status,
            created_at=created_at,
            seats=seats,
            organization_id=org_id,
        )

        session_id = checkout_api_result["data"]["sessionId"]
        logger.info("Checkout session created: %s", session_id)

        # Call session API
        session_api_html = await call_session_api(session_id)

        # Insert pre-purchased users
        await insert_order_prepurchased(
            db_session=db_session,
            github_ids=github_ids_list,
            order_id=order_id,
            reserved_at=created_at,
        )

        await db_session.commit()  # Only commit after all operations succeed

        response_data = {
            "order_id": order_id,
            "plan_name": plan_name,
            "html": session_api_html,
        }

        logger.info("Order created successfully: %s", response_data)
        return response_data

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Order creation failed: {e}")
        raise HTTPException(
            status_code=503, detail="Failed to create order. Please try again."
        )


@router.post("/order/create/non_github")
async def order_handler(
    request: Request,
    user_id: str = Form(),
    plan_id: str = Form(),
    customer_email: str = Form(),
    customer_name: str = Form(),
    plan_name: str = Form(),
    interval: str = Form(),
    amount: float = Form(),
    redirect_url: str = Form(),
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
):
    if plan_name != "Standard Plan":
        logger.error(f"Invalid plan name received: {plan_name}", extra={"user_id": user_id})
        return HTTPException(status_code=400, detail="Invalid plan name.")

    try:
        order_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        price_name = f"Fixed Amount {amount}"

        # Call checkout API before DB insert
        checkout_api_result = await call_checkout_api(
            customer_email=customer_email,
            customer_name=customer_name,
            plan_name=plan_name,
            price_name=price_name,
            interval=interval,
            amount=amount,
            order_id=order_id,
            user_id=user_id,
            redirect_url=redirect_url,
            seats=1,
        )
        status = "pending"

        # Insert order
        order_id = await insert_order_new(
            db_session=db_session,
            order_id=order_id,
            user_id=user_id,
            plan_id=plan_id,
            status=status,
            created_at=created_at,
            seats=1,
            organization_id=None,
        )

        session_id = checkout_api_result["data"]["sessionId"]
        logger.info("Checkout session created: %s", session_id)

        # Call session API
        session_api_html = await call_session_api(session_id)

        await db_session.commit()  # Only commit after all operations succeed

        # Final response based on plan
        if plan_name.lower() == "free":
            response_data = {
                "message": "successful",
                "order_id": order_id,
                "plan_name": plan_name,
            }
        else:
            response_data = {
                "order_id": order_id,
                "plan_name": plan_name,
                "html": session_api_html,
            }

        logger.info("Order created successfully: %s", response_data)
        return response_data

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Order creation failed: {e}")
        raise HTTPException(
            status_code=503, detail="Failed to create order. Please try again."
        )


@router.post("/order/handle/non_github")
async def order_handler(
    user_id: str = Form(...),
    db_session: AsyncSession = Depends(get_db),
):
    try:
        response = await get_order_details_by_user_id_org_id(db_session, user_id)
        order_id = response["order_id"]
        updated_at = datetime.now(timezone.utc)

        # Retrieve subscription status
        subscription_data = await fetch_subscription_summary(order_id)
        new_status = subscription_data.get("status")
        stripe_end_date = subscription_data.get("current_period_end")
        end_date = datetime.fromisoformat(stripe_end_date) if stripe_end_date else None

        logger.info("Subscription status retrieved for order %s: %s", order_id, new_status)

        if response["status"] == "pending" and new_status == "active":
            stripe_end_date = subscription_data.get("current_period_end")
            end_date = (
                datetime.strptime(stripe_end_date, "%Y-%m-%dT%H:%M:%SZ") if stripe_end_date else None
            )
            assigned_at = datetime.now(timezone.utc)
            await update_order_status(db_session, order_id, new_status)

            await add_user_plan_assignments(
                db_session=db_session,
                user_ids=[user_id],
                organization_id=None,
                order_id=order_id,
                assigned_at=assigned_at,
                end_date=end_date,
            )

            await reset_token_usage_user_id_org_id(
                db_session=db_session,
                user_id=user_id,
                organization_id=None
            )

        await db_session.commit()

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while updating order status {e}", extra={"user_id": user_id})
        raise HTTPException(status_code=503, detail="We are having trouble updating order status. Please try again later.")
