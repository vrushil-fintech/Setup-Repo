from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Form, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import HTMLResponse

from app.database import get_db
from app.dependencies import logger
from app.crud.payments import (
    get_plan,
    insert_order,
    update_order_status,
    get_order_details_by_user_id_org_id,
    update_order_plan_by_order_id,
)
from app.api.payments import (
    call_checkout_api,
    call_session_api,
    get_subscription_status,
    cancel_order,
    upgrade_plan,
    upcoming_order_details,
)
from app.api.payments import get_subscription_status

router = APIRouter()


@router.post("/orderdetails")
async def order_details(
    user_id: str = Form(), db_session: AsyncSession = Depends(get_db)
):
    response = await get_order_details_by_user_id_org_id(db_session, user_id)
    logger.info("Order details retrieved.", extra={"user_id": user_id})
    return response


@router.post("/order/status")
async def order_handler(
    order_id: str = Form(...), db_session: AsyncSession = Depends(get_db)
):
    updated_at = datetime.now(timezone.utc)

    # Retrieve subscription status
    result = await get_subscription_status(order_id)
    new_status = result["status"]
    logger.info("Subscription status retrieved for order %s: %s", order_id, new_status)

    if new_status != "none":  # Check if new_status is not "none"
        # Update order status only if new_status is not "none"
        result = await update_order_status(db_session, order_id, new_status, updated_at)
        if result.rowcount > 0:
            await db_session.commit()
            logger.info("Order status updated for order %s: %s", order_id, new_status)
    print(new_status)
    return {"status": new_status}


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
    db_session: AsyncSession = Depends(get_db),
):

    order_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    price_name = f"Fixed Amount {amount}"

    if plan_name.lower() == "free":
        status = "free"
        order_id = await insert_order(
            db_session, order_id, user_id, plan_id, status, created_at
        )
        response_data = {
            "message": "successful",
            "order_id": order_id,
            "plan_name": plan_name,
        }
    else:
        # Call the checkout API if plan is not free
        result = await call_checkout_api(
            customer_email,
            customer_name,
            plan_name,
            price_name,
            interval,
            amount,
            order_id,
            user_id,
            redirect_url,
        )
        status = "pending"
       
        order_id = await insert_order(
            db_session, order_id, user_id, plan_id, status, created_at
        )

        session_id = result["data"]["sessionId"]
        logger.info("Checkout session created: %s", session_id)

        response_data = {"session_id": session_id}

    await db_session.commit()
    return response_data


@router.get("/checkout/{session_id}", response_class=HTMLResponse)
async def order_handler(session_id: str, db_session: AsyncSession = Depends(get_db)):

    # Call session API
    html_content = await call_session_api(session_id)

    # Return the HTML content directly
    return HTMLResponse(content=html_content)


@router.get("/plans")
async def plan(request: Request, db_session: AsyncSession = Depends(get_db)):
    result = await get_plan(db_session)
    logger.info("Plans retrieved")
    return result
