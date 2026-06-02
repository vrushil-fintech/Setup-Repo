from fastapi import HTTPException
import httpx
from datetime import datetime
from app.config import STRIPE_REST_API
from app.dependencies import logger


async def call_checkout_api(
    customer_email: str,
    customer_name: str,
    plan_name: str,
    price_name: str,
    interval: str,
    amount: float,
    order_id,
    user_id,
    redirect_url,
    seats: int,
):
    if not isinstance(order_id, str) or not order_id:
        raise ValueError("Invalid order_id: must be a non-empty string.")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("Invalid user_id: must be a non-empty string.")
    if not isinstance(seats, int) or seats <= 0:
        raise ValueError("Invalid seats: must be a positive integer.")
    url = STRIPE_REST_API + "/checkout"
    order_id = str(order_id)
    user_id = str(user_id)
    amount = int(amount)
    payload = {
        "checkoutData": {
            "customerData": {"emailId": customer_email, "name": customer_name},
            "planDetails": [
                {
                    "productData": {
                        "name": plan_name,
                        "baseProductName": "CodeSherlock",
                    },
                    "priceData": {
                        "name": price_name,
                        "currency": "USD",
                        "interval": interval,
                        "intervalCount": "1",
                        "usageType": "licensed",
                        "amount": amount,
                        "recurring": True,
                        "quantity": seats,
                    },
                }
            ],
            "paymentMode": "multiproduct_subscription",
            "orderId": order_id,
            "userId": user_id,
            "redirectUrl": redirect_url,
        }
    }

    headers = {"base-product": "CodeSherlock"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except Exception as e:
            logger.error(
                f"Failed to call checkout API: {str(e)}",
                extra={"user_id": str(user_id)},
            )
            raise HTTPException(
                status_code=503,
                detail=f"We're having trouble processing your order. Please try again later.",
            )


async def call_session_api(session_id):
    url = f"{STRIPE_REST_API}/checkout?session_id={session_id}"
    headers = {"base-product": "CodeSherlock"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)

            response.raise_for_status()  # Raise HTTPError for bad responses

            # Parse JSON response
            if "application/json" in response.headers.get("content-type", ""):
                # Parse JSON response
                api_data = response.json()
                return api_data
            else:
                # Handle HTML response or other content types
                # You might want to return the raw content or handle it differently
                return response.content

        except Exception as e:
            # Handle HTTP errors (status codes >= 400)
            logger.error(
                f"Failed to call payment API: {str(e)}",
                extra={"session_id": str(session_id)},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble getting your payment details. Please try again later.",
            )


async def get_subscription_status(order_id):
    url = f"{STRIPE_REST_API}/subscription/get-status?orderId={order_id}"
    headers = {"base-product": "CodeSherlock"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(
                f"Failed to get subscription status: {str(e)}",
                extra={"order_id": str(order_id)},
            )
            raise HTTPException(
                status_code=503,
                detail=f"We're having trouble getting your payment details. Please try again later.",
            )


def to_iso(timestamp: int | None) -> str | None:
    if not timestamp:
        return None
    return datetime.utcfromtimestamp(timestamp).isoformat() + "Z"


async def fetch_subscription_summary(order_id: str) -> dict:
    url = f"{STRIPE_REST_API}/subscription?orderId={order_id}"
    headers = {"base-product": "CodeSherlock"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()

            if result.get("status") != 1:
                logger.warning(
                    f"Subscription API returned non-success status: {result}"
                )
                raise HTTPException(
                    status_code=502, detail="Subscription service error."
                )

            data = result.get("data", {})
            subscription = data.get("subscription", {})
            invoices = data.get("invoices", [])
            logger.info("Subscription summary fetched")

            # Extract important fields
            return {
                "subscription_id": subscription.get("id"),
                "status": subscription.get("status"),
                "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
                "current_period_start": to_iso(
                    subscription.get("current_period_start")
                ),
                "current_period_end": to_iso(subscription.get("current_period_end")),
                "plan": {
                    "nickname": subscription.get("item", {}).get("nickname"),
                    "unit_amount": subscription.get("item", {}).get("unit_amount"),
                    "currency": subscription.get("item", {}).get("currency"),
                },
                "invoices": [
                    {
                        "invoice_id": inv.get("id"),
                        "amount_paid": inv.get("amount_paid"),
                        "status": inv.get("status"),
                        "pdf_url": inv.get("pdf_url"),
                        "created_at": to_iso(inv.get("created")),
                        "period_start": to_iso(inv.get("period_start")),
                        "period_end": to_iso(inv.get("period_end")),
                    }
                    for inv in invoices
                ],
            }

        except Exception as e:
            logger.error(
                f"Failed to fetch subscription details: {str(e)}",
                extra={"order_id": order_id},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble retrieving your subscription. Please try again later.",
            )


async def cancel_order(order_id, plan_name):
    url = f"{STRIPE_REST_API}/subscription/update-pay-as-you-go"

    payload = {
        "subscriptionData": {
            "orderId": order_id,
            "toBeImmediate": {"updatePricesData": [], "removePricesData": []},
            "toBeScheduled": {
                "updatePricesData": [],
                "removePricesData": [
                    {
                        "productData": {
                            "name": plan_name,
                            "baseProductName": "CodeSherlock",
                        }
                    }
                ],
            },
        }
    }

    headers = {"base-product": "CodeSherlock"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses

            # If response status code is 500, check for custom error message

            # Parse JSON response for other status codes
            return response.json()

        except Exception as e:
            logger.error(
                f"Failed to cancel order: {str(e)}", extra={"order_id": str(order_id)}
            )
            raise HTTPException(
                status_code=503,
                detail=f"We're having trouble cancelling your order. Please try again later.",
            )


async def upgrade_plan(
    plan_name: str, price_name, interval: str, amount: float, order_id
):
    # Endpoint path
    endpoint = "subscription/update-pay-as-you-go"

    # Construct the full URL
    url = f"{STRIPE_REST_API}/{endpoint}"
    order_id = str(order_id)
    amount = int(amount)

    payload = {
        "subscriptionData": {
            "orderId": order_id,
            "toBeImmediate": {"updatePricesData": [], "removePricesData": []},
            "toBeScheduled": {
                "updatePricesData": [
                    {
                        "productData": {
                            "name": plan_name,
                            "baseProductName": "CodeSherlock",
                        },
                        "priceData": {
                            "name": price_name,
                            "currency": "USD",
                            "interval": interval,
                            "intervalCount": "1",
                            "usageType": "licensed",
                            "amount": amount,
                            "recurring": True,
                            "quantity": 1,
                        },
                    }
                ],
                "removePricesData": [],
            },
        }
    }

    headers = {"base-product": "CodeSherlock"}

    async with httpx.AsyncClient() as client:
        try:
            print(plan_name, price_name, interval, amount)
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except Exception as e:
            logger.error(
                f"Failed to upgrade plan: {str(e)}", extra={"order_id": str(order_id)}
            )
            raise HTTPException(
                status_code=503,
                detail=f"We're having trouble upgrading your plan. Please try again later.",
            )


async def upcoming_order_details(order_id):
    url = f"{STRIPE_REST_API}/invoice/retrieve-upcoming-invoice?orderId={order_id}"
    order_id = str(order_id)

    async with httpx.AsyncClient() as client:
        try:

            response = await client.get(url)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except httpx.HTTPError as e:
            logger.error(
                f"Failed to get upcoming order details: {str(e)}",
                extra={"order_id": str(order_id)},
            )
            raise HTTPException(
                status_code=503, detail=f"Failed to get upcoming order details"
            )
