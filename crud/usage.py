from typing import Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import logger
from app.models import LLMUsage
from fastapi import HTTPException


async def insert_usage(
    db_session: AsyncSession,
    usage_data: Dict[str, LLMUsage],
    user_id,
    model,
    created_at,
    organization_id: str = None,
):
    if organization_id is not None and not isinstance(organization_id, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid organization_id: It must be a string."
        )
    if organization_id and len(organization_id) == 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid organization_id: It must not be an empty string."
        )

    sql_query = text(
        """
INSERT INTO codesherlock.usage(userid, api_key, model, created_at, input_tokens, response_tokens, usage_cost, organization_id)
VALUES (:userid, :api_key, :model, :created_at, :input_tokens, :response_tokens, :usage_cost, :organization_id)
RETURNING usageid;
"""
    )
    usage_ids = {}
    try:
        for characteristic, usage in usage_data.items():
            db_result = await db_session.execute(
                sql_query,
                {
                    "userid": user_id,
                    "api_key": usage.llm_deployment,
                    "model": model,
                    "created_at": created_at,
                    "input_tokens": usage.input_tokens,
                    "response_tokens": usage.response_tokens,
                    "usage_cost": usage.cost,
                    "organization_id": organization_id,
                },
            )
            results = list(db_result.fetchall())
            usage_ids[characteristic] = results[0][0]

        logger.info("Usage inserted", extra={"user_id": str(user_id)})
        return usage_ids
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Database error occured: %s", str(e), extra={"user_id": str(user_id)}
        )
        raise Exception(
            "We're having trouble processing your request. Please try again later."
        )


async def insert_characteristic_usage(
    db_session: AsyncSession,
    usage_data: Dict[str, LLMUsage],
    usage_ids,
    user_id,
    created_at,
    organization_id: str = None,
):
    if organization_id == "":
        organization_id = None
    sql_query = text(
        """
INSERT INTO codesherlock.characteristic_usage(usageid, userid, created_at, characteristic, input_tokens, response_tokens, organization_id)
VALUES (:usageid, :userid, :created_at, :characteristic, :input_tokens, :response_tokens, :organization_id);
"""
    )
    try:
        for characteristic, usage in usage_data.items():
            await db_session.execute(
                sql_query,
                {
                    "usageid": usage_ids[characteristic],
                    "userid": user_id,
                    "created_at": created_at,
                    "characteristic": characteristic,
                    "input_tokens": usage.input_tokens,
                    "response_tokens": usage.response_tokens,
                    "organization_id": organization_id,
                },
            )

        logger.info("Characteristic Usage inserted", extra={"user_id": str(user_id)})
        return
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Database error occured: %s", str(e), extra={"user_id": str(user_id)}
        )
        raise HTTPException(
            status_code=503,
            detail=f"Error occurred while upserting tokens and cost: {str(e)}",
        )


async def get_tokens_usage_by_user_id_org_id(db_session: AsyncSession, user_id: str, organization_id: str = None):
    sql_query = text(
        """
SELECT tokens_usage FROM codesherlock.usage_total
WHERE user_id = :user_id AND organization_id = :organization_id;
"""
    )
    if organization_id == "":
        organization_id = None
    try:
        db_result = await db_session.execute(sql_query, {"user_id": user_id, "organization_id": organization_id})
        result = db_result.fetchone()
        logger.info("Tokens usage retrieved", extra={"user_id": user_id})
        return result[0] if result else 0  # Return 0 if no record found
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching usage data. Please try again later.",
        )


async def upsert_tokens_usage_user_id_org_id(
    db_session: AsyncSession, user_id: str, tokens_used: int, cost: float, organization_id: str = None
):
    if organization_id == "":
        organization_id = None

    try:
        # Step 1: Check if there's already a record for the user/org in usage_total
        sql_query_total = text("""
            SELECT tokens_usage, cost_usage
            FROM codesherlock.usage_total
            WHERE user_id = :user_id
              AND organization_id IS NOT DISTINCT FROM :organization_id;
        """)
        db_result_total = await db_session.execute(
            sql_query_total, {"user_id": user_id, "organization_id": organization_id}
        )
        existing_total = db_result_total.fetchone()

        if existing_total:
            # Step 2: If record exists in usage_total, update the values
            existing_tokens_usage = existing_total[0]
            existing_cost = float(existing_total[1])

            new_tokens_usage = existing_tokens_usage + tokens_used
            new_cost = existing_cost + cost

            # Perform the update in the usage_total table
            sql_upsert = text(
                """
                UPDATE codesherlock.usage_total
                SET tokens_usage = :tokens_usage,
                    cost_usage = :cost_usage
                WHERE user_id = :user_id
                  AND organization_id IS NOT DISTINCT FROM :organization_id;
            """)

            await db_session.execute(
                sql_upsert,
                {
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "tokens_usage": new_tokens_usage,
                    "cost_usage": new_cost,
                },
            )

            logger.info(
                f"Updated tokens and cost for user_id: {user_id} and organization_id: {organization_id} in usage_total."
            )
        else:
            # Step 3: If no record, calculate sum from usage table
            sql_query_usage = text("""
                SELECT SUM(input_tokens), SUM(response_tokens), SUM(usage_cost)
                FROM codesherlock.usage
                WHERE userid = :user_id
                  AND organization_id IS NOT DISTINCT FROM :organization_id;
            """)
            db_result_usage = await db_session.execute(
                sql_query_usage, {"user_id": user_id, "organization_id": organization_id}
            )
            usage_data = db_result_usage.fetchone()

            # Sum of existing tokens and cost from the `usage` table (if they exist)
            existing_tokens = (usage_data[0] or 0) + (usage_data[1] or 0)
            existing_cost = float(usage_data[2] or 0.0)

            # Add the new tokens_used and cost to the sum
            new_tokens_usage = existing_tokens + tokens_used
            new_cost = existing_cost + cost

            # Insert the new record in usage_total table
            sql_insert = text(
                """
                INSERT INTO codesherlock.usage_total (user_id, tokens_usage, cost_usage, organization_id)
                VALUES (:user_id, :tokens_usage, :cost_usage, :organization_id);
                """
            )
            await db_session.execute(
                sql_insert,
                {
                    "user_id": user_id,
                    "tokens_usage": new_tokens_usage,
                    "cost_usage": new_cost,
                    "organization_id": organization_id,
                },
            )

            logger.info(
                f"Inserted new tokens and cost for user_id: {user_id} and organization_id: {organization_id} in usage_total."
            )

    except Exception as e:
        await db_session.rollback()
        logger.error(
            f"Error occurred while upserting tokens and cost: {e}",
            extra={"user_id": user_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Error occurred while upserting tokens and cost. Please try again later.",
        )

async def reset_token_usage_user_id_org_id(db_session: AsyncSession, user_id: str, organization_id: str = None):
    sql_query = text(
        """
UPDATE codesherlock.usage_total
SET tokens_usage = 0, cost_usage = 0, updated_at = now()
WHERE user_id = :user_id AND organization_id IS NOT DISTINCT FROM :organization_id;
"""
    )
    try:
        await db_session.execute(sql_query, {"user_id": user_id, "organization_id": organization_id})
        logger.info("Tokens usage reset", extra={"user_id": user_id, "organization_id": organization_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"user_id": user_id, "organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching usage data. Please try again later.",
        )
