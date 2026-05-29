from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import uuid
from typing import Optional, List
from app.dependencies import logger


async def get_plan(db_session: AsyncSession):
    sql_query = text(
        """
        SELECT plan_id, plan_name, amount, plan_type
        FROM codesherlock.plan
        """
    )
    try:
        db_result = await db_session.execute(sql_query)
        result = list(db_result.fetchall())
        data = []

        for item in result:
            plan_id, plan_name, amount, plan_type = item
            data.append(
                {
                    "plan_id": plan_id,
                    "plan_name": plan_name,
                    "amount": amount,
                    "plan_type": plan_type,
                }
            )

        return data if data else None

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred: {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching available plans. Please try again later.",
        )


async def insert_order(
    db_session: AsyncSession,
    order_id: str,
    user_id: uuid.UUID,
    plan_id: int,
    status: str,
    created_at: datetime,
):
    # Define the SQL query for inserting an order using % formatting
    sql_query = text(
        """
        INSERT INTO codesherlock.order (user_id, plan_id, status, created_at, order_id)
        VALUES (:user_id, :plan_id, :status, :created_at, :order_id)
        RETURNING order_id
    """
    )

    try:
        # Execute the SQL query with provided parameters using % formatting
        db_result = await db_session.execute(
            sql_query,
            {
                "order_id": order_id,
                "user_id": str(user_id),
                "plan_id": plan_id,
                "status": status,
                "created_at": created_at,
            },
        )

        # Fetch the order_id of the inserted row
        order_id = db_result.fetchone()[0]

        return order_id  # Return the order_id of the inserted order
    except Exception as e:
        # Rollback the transaction in case of an error
        await db_session.rollback()
        logger.error(f"Database error occured {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble creating your order. Please try again later.",
        )


async def update_order_status(
    db_session: AsyncSession, order_id: str, new_status: str, updated_at: datetime
):
    # Define the SQL query for updating the status of an order
    sql_query = text(
        """
        UPDATE codesherlock.order
        SET status = :new_status, updated_at = :updated_at
        WHERE order_id = :order_id AND status != :new_status;
    """
    )

    try:
        # Execute the SQL query with provided parameters
        dbresult = await db_session.execute(
            sql_query,
            {"order_id": order_id, "new_status": new_status, "updated_at": updated_at},
        )

        return dbresult
    except Exception as e:
        # Rollback the transaction in case of an error
        await db_session.rollback()
        logger.error("Database error occured: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your plan status. Please try again later.",
        )


async def update_order_status(
    db_session: AsyncSession, order_id: str, new_status: str
):
    # Define the SQL query for updating the status of an order
    sql_query = text(
        """
        UPDATE codesherlock.order
        SET status = :new_status
        WHERE order_id = :order_id AND status != :new_status;
    """
    )

    try:
        # Execute the SQL query with provided parameters
        dbresult = await db_session.execute(
            sql_query,
            {"order_id": order_id, "new_status": new_status},
        )

        return dbresult
    except Exception as e:
        # Rollback the transaction in case of an error
        await db_session.rollback()
        logger.error("Database error occured: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your plan status. Please try again later.",
        )


async def activate_pre_purchased_users_by_order_id(
    db_session: AsyncSession, order_id: str, end_date: datetime
) -> list[dict]:
    try:
        # Update is_active and end_date for matching pre-purchased users
        update_query = text(
            """
            UPDATE codesherlock.pre_purchased_user
            SET is_active = TRUE,
                is_claimed = FALSE,
                end_date = :end_date
            WHERE order_id = :order_id
            RETURNING order_id, github_id
            """
        )

        result = await db_session.execute(
            update_query,
            {
                "order_id": order_id,
                "end_date": end_date,
            },
        )
        rows = result.fetchall()

        if not rows:
            logger.warning(
                f"No pre-purchased users found for order_id '{order_id}'",
                extra={"order_id": order_id},
            )
            raise HTTPException(
                status_code=404,
                detail="No pre-purchased users found for this order.",
            )

        return [
            {
                "order_id": row[0],
                "github_id": row[1],
            }
            for row in rows
        ]

    except Exception as e:
        await db_session.rollback()
        logger.error(
            f"Failed to activate pre-purchased users: {str(e)}",
            extra={"order_id": order_id},
        )
        raise HTTPException(
            status_code=500,
            detail="Error activating pre-purchased users. Please try again later.",
        )

async def get_order_details_by_user_id_org_id(
    db_session: AsyncSession, user_id: str, organization_id: str = None
) -> dict:
    try:
        # Define the SQL query to select the latest order details for the given user_id
        # and optionally filter by organization_id if provided
        sql_query = text(
            """
    SELECT o.order_id, o.purchaser_user_id, o.status, o.created_at, o.plan_id
    FROM codesherlock.order AS o
    WHERE o.purchaser_user_id = :purchaser_user_id
      AND (CAST(:organization_id AS UUID) IS NULL OR o.organization_id = CAST(:organization_id AS UUID))
    ORDER BY o.created_at DESC
    LIMIT 1
    """
        )

        # Execute the SQL query with user_id and organization_id parameters
        db_result = await db_session.execute(
            sql_query, {"purchaser_user_id": user_id, "organization_id": organization_id}
        )

        # Fetch the first (and only) row from the result set
        row = db_result.fetchone()

        if not row:
            logger.warning(
                f"Order for purchaser_user_id '{user_id}' with organization_id '{organization_id}' not found.",
                extra={"user_id": user_id, "organization_id": organization_id},
            )
            raise HTTPException(
                status_code=404,
                detail="We're having trouble finding your order. Please contact support.",
            )

        # Construct order details dictionary with nested plan and plan_type details
        order_data = {
            "order_id": row[0],
            "user_id": row[1],
            "status": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "plan_id": row[4],
        }

        logger.info(
            f"Retrieved order details for purchaser_user_id '{user_id}' with organization_id '{organization_id}'.")
        return order_data

    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Database error occurred: %s",
            str(e),
            extra={"user_id": user_id, "organization_id": organization_id},
        )
        if not isinstance(e, HTTPException) or e.status_code != 404:
            raise HTTPException(
                status_code=503,
                detail="We're having trouble fetching your plan status. Please try again later.",
            )
        else:
            raise e


async def get_user_order_details(
    db_session: AsyncSession,
    user_id: str,
    organization_id: Optional[str],  # Accepts None or 'null' as string
) -> dict:
    try:
        # Normalize frontend-sent 'null' or empty string to Python None

        sql_query = text(
            """
            SELECT 
                uo.order_id, 
                uo.end_date, 
                o.status,
                p.plan_id AS plan_id,
                p.plan_name,
                p.plan_type
            FROM codesherlock.user_order AS uo
            JOIN codesherlock.order AS o ON uo.order_id = o.order_id
            JOIN codesherlock.plan AS p ON o.plan_id = p.plan_id
            WHERE uo.user_id = :user_id 
              AND (
                (CAST(:organization_id AS UUID) IS NULL AND uo.organization_id IS NULL) OR 
                (CAST(:organization_id AS UUID) IS NOT NULL AND uo.organization_id = CAST(:organization_id AS UUID))
              )
            ORDER BY uo.assigned_at DESC
            LIMIT 1
            """
        )

        result = await db_session.execute(
            sql_query, {"user_id": user_id, "organization_id": organization_id}
        )
        row = result.fetchone()

        if not row:
            logger.warning(
                f"No user plan found for user_id='{user_id}', organization_id='{organization_id}'",
                extra={"user_id": user_id, "organization_id": organization_id},
            )
            return {
                "order_id": None,
                "end_date": None,
                "status": None,
                "plan": None,
            }

        logger.info(
            f"Retrieved user plan for user_id='{user_id}', organization_id='{organization_id}'")
        return {
            "order_id": row[0],
            "end_date": row[1].isoformat() if row[1] else None,
            "status": row[2],
            "plan": {
                "plan_id": row[3],
                "plan_name": row[4],
                "plan_type": row[5],
            },
        }

    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Failed to retrieve user plan: %s",
            str(e),
            extra={"user_id": user_id, "organization_id": organization_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to retrieve user plan. Please try again later.",
        )


async def update_user_plan_end_date(
    db_session: AsyncSession,
    user_id: str,
    organization_id: str,
    new_end_date: datetime,
) -> bool:
    """
    Updates the end_date for a user in the user_order table.

    Returns True if update was successful, False otherwise.
    """
    try:
        update_query = text(
            """
            UPDATE codesherlock.user_order
            SET end_date = :new_end_date
            WHERE user_id = :user_id AND organization_id = :organization_id
        """
        )
        result = await db_session.execute(
            update_query,
            {
                "new_end_date": new_end_date,
                "user_id": user_id,
                "organization_id": organization_id,
            },
        )

        if result.rowcount == 0:
            logger.warning(
                f"No user_plan record updated for user_id={user_id}, organization_id={organization_id}"
            )
            return False

        logger.info(
            f"Successfully updated end_date for user_id={user_id}, organization_id={organization_id} to {new_end_date}"
        )
        return True

    except Exception as e:
        await db_session.rollback()
        logger.error(
            f"Error updating end_date for user_id={user_id}, organization_id={organization_id}: {str(e)}"
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to update user plan. Please try again later.",
        )


async def get_order_status_by_order_id(db_session: AsyncSession, order_id: str) -> dict:
    try:
        # Include purchaser_user_id and plan_id
        sql_query = text(
            """
            SELECT o.order_id, o.purchaser_user_id, o.status, o.created_at, o.plan_id
            FROM codesherlock.order AS o
            WHERE o.order_id = :order_id
            LIMIT 1
            """
        )

        db_result = await db_session.execute(sql_query, {"order_id": order_id})
        row = db_result.fetchone()

        if not row:
            logger.warning(
                f"Order with order_id '{order_id}' not found.",
                extra={"order_id": order_id},
            )
            raise HTTPException(
                status_code=404,
                detail="We're having trouble finding this order. Please contact support.",
            )

        # Return the updated order information including purchaser_user_id and plan_id
        return {
            "order_id": row[0],
            "purchaser_user_id": row[1],
            "status": row[2],
            "created_at": row[3].isoformat() if row[3] else None,
            "plan_id": row[4],
        }

    except Exception as e:
        logger.error(
            f"Database error while fetching order: {str(e)}",
            extra={"order_id": order_id},
        )
        raise HTTPException(
            status_code=503,
            detail="Something went wrong while retrieving the order details. Please try again later.",
        )


async def add_user_plan_assignments(
    db_session: AsyncSession,
    user_ids: list[str],
    order_id: str,
    assigned_at: datetime,
    organization_id: Optional[str] = None,
    end_date: Optional[datetime] = None,
) -> list[dict]:
    is_active = True
    if not user_ids:
        return []

    try:
        is_active = True

        # Create parameterized multi-row insert
        values_clause = []
        parameters = {}

        for idx, user_id in enumerate(user_ids):
            values_clause.append(
                f"(:user_id_{idx}, :organization_id_{idx}, :order_id_{idx}, :assigned_at_{idx}, :end_date_{idx}, :is_active_{idx})"
            )
            parameters.update({
                f"user_id_{idx}": user_id,
                f"organization_id_{idx}": organization_id,
                f"order_id_{idx}": order_id,
                f"assigned_at_{idx}": assigned_at,
                f"end_date_{idx}": end_date,
                f"is_active_{idx}": is_active,
            })

        insert_query = text(f"""
            INSERT INTO codesherlock.user_order
                (user_id, organization_id, order_id, assigned_at, end_date, is_active)
            VALUES {', '.join(values_clause)}
            RETURNING id, user_id, organization_id, order_id, assigned_at, end_date, is_active
        """)

        result = await db_session.execute(insert_query, parameters)
        await db_session.commit()

        rows = result.fetchall()
        logger.info(
            "Successfully assigned plans to users",
            extra={"user_ids": user_ids, "organization_id": organization_id, "order_id": order_id}
        )

        return [
            {
                "id": row[0],
                "user_id": row[1],
                "organization_id": row[2],
                "order_id": row[3],
                "assigned_at": row[4].isoformat() if row[4] else None,
                "end_date": row[5].isoformat() if row[5] else None,
                "is_active": row[6],
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(
            f"Failed to assign plans to users: {str(e)}",
            extra={"user_ids": user_ids, "organization_id": organization_id, "order_id": order_id}
        )
        await db_session.rollback()
        raise HTTPException(
            status_code=503,
            detail="We are having trouble assigning order. Please try again later."
        )


async def mark_pre_purchased_user_claimed(
    db_session: AsyncSession,
    claimed_github_ids: List[int],  # if they come as strings
    order_id: str,
) -> None:
    try:
        update_query = text(
            """
            UPDATE codesherlock.pre_purchased_user
            SET is_claimed = TRUE
            WHERE github_id = ANY(:github_ids) AND order_id = :order_id
            """
        )

        await db_session.execute(
            update_query, {"github_ids": claimed_github_ids, "order_id": order_id}
        )

        logger.info(
            f"Marked {len(claimed_github_ids)} pre-purchased users as claimed for order_id {order_id}"
        )

    except Exception as e:
        logger.error(f"Error marking pre-purchased user as claimed: {e}")
        await db_session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update is_claimed for pre-purchased users: {str(e)}",
        )


async def update_order_plan_by_order_id(
    db_session: AsyncSession, order_id: int
) -> None:
    try:
        # Define the SQL query to update the plan_id in the order table
        sql_query = text(
            """
            UPDATE codesherlock.order AS o
            SET plan_id = (
                SELECT pt.plan_id
                FROM codesherlock.plan AS p
                WHERE p.plan_type = 'yearly'
            )
            WHERE o.order_id = :order_id
        """
        )

        # Execute the SQL query with the provided user_id parameter
        db_result = await db_session.execute(sql_query, {"order_id": order_id})

        # Check if any rows were affected by the update
        row = db_result.fetchone()

        if not row:
            raise ValueError(
                f"No order found for order_id '{order_id}' or no yearly plan available."
            )

    except Exception as e:
        await db_session.rollback()
        logger.error("Database error occured: %s", str(e))
        raise HTTPException(
            status_code=503,
            detail="We're having trouble upgrading your order. Please try again later.",
        )


async def insert_order_new(
    db_session: AsyncSession,
    order_id: str,
    user_id: str,
    plan_id: str,
    status: str,
    seats: int,
    created_at: datetime,
    organization_id: Optional[str] = None,
):
    sql_query = text(
        """
        INSERT INTO codesherlock.order (
            purchaser_user_id,
            plan_id,
            status,
            created_at,
            order_id,
            seats,             -- <-- added
            organization_id
        )
        VALUES (
            :purchaser_user_id,
            :plan_id,
            :status,
            :created_at,
            :order_id,
            :seats,            -- <-- added
            :organization_id
        )
        RETURNING order_id
        """
    )

    try:
        # Normalize frontend-sent 'null' or empty string to Python None
        if organization_id in ("null", ""):
            organization_id = None
        db_result = await db_session.execute(
            sql_query,
            {
                "order_id": order_id,
                "purchaser_user_id": str(user_id),
                "plan_id": plan_id,
                "status": status,
                "created_at": created_at,
                "seats": seats,  # <-- added
                "organization_id": organization_id
            },
        )

        inserted_order_id = db_result.fetchone()[0]
        logger.info("Successfully inserted new order with order_id: %s", order_id)
        return inserted_order_id

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred: {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble creating your order. Please try again later.",
        )


async def insert_order_prepurchased(
    db_session: AsyncSession,
    github_ids: List[int],
    order_id: str,
    reserved_at: datetime,
):
    sql_query = text(
        """
        INSERT INTO codesherlock.pre_purchased_user (github_id, order_id, reserved_at)
        VALUES (:github_id, :order_id, :reserved_at)
    """
    )

    try:
        for gid in github_ids:
            await db_session.execute(
                sql_query,
                {
                    "github_id": gid,
                    "order_id": order_id,
                    "reserved_at": reserved_at,
                },
            )

        logger.info(
            f"Inserted {len(github_ids)} pre-purchased users for order_id {order_id}"
        )
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error inserting pre-purchased users: {e}")
        raise


async def get_pre_purchased_user_organization_id(db_session: AsyncSession, github_id: int):
    sql_query = text(
        """
SELECT p.order_id, p.end_date, o.organization_id, o.purchaser_user_id
FROM codesherlock.pre_purchased_user AS p
JOIN codesherlock.order AS o ON p.order_id = o.order_id
WHERE p.is_active = TRUE AND p.github_id = :github_id AND p.is_claimed = FALSE;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {"github_id": github_id})
        result = db_result.fetchall()
        logger.info(f"Pre-purchased user order details retrieved for github_id: {github_id}", extra={"github_id": github_id})
        if result:
            response = []
            for row in result:
                response.append(
                    {
                        "order_id": row[0],
                        "end_date": row[1],
                        "organization_id": row[2],
                        "purchaser_user_id": row[3],
                    }
                )
            return response
        else:
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error getting pre-purchased user organization_id: {e}")
        raise


async def get_plan_status_for_github_user(
    db_session: AsyncSession, github_id: int, has_logged_in: bool, organization_id: str
) -> dict:
    try:
        result = await db_session.execute(
            text(
                """
                SELECT p.order_id, p.is_active, p.end_date
                FROM codesherlock.pre_purchased_user p
                JOIN codesherlock.order o ON p.order_id = o.order_id
                WHERE p.github_id = :github_id
                  AND o.organization_id = :organization_id
                  AND end_date IS NOT NULL
                ORDER BY p.end_date DESC
                LIMIT 1
                """
            ),
            {"github_id": github_id, "organization_id": organization_id},
        )

        row = result.fetchone()
        # if the user's order is there in pre purchased
        if row:
            order_id, is_active, end_date = row

            if is_active:
                status = "active"
            else:
                status = "free" if has_logged_in else "no plan"

            return {"status": status}

        # if the user's order is not there in pre purchased
        else:
            return {"status": "free" if has_logged_in else "no plan"}

    except Exception as e:
        logger.error(f"Error fetching plan status for github_id {github_id}: {e}")
        raise

async def inactive_user_order_details(db_session: AsyncSession, order_id: str):
    query = text(
        """
UPDATE codesherlock.user_order
SET is_active = FALSE
WHERE order_id = :order_id;
        """
    )
    try:
        await db_session.execute(query, {"order_id": order_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error in occurred in invalidating user order details: {e}", extra={"order_id": order_id})

async def inactive_pre_purchased_user_details(db_session: AsyncSession, order_id: str):
    query = text(
        """
UPDATE codesherlock.pre_purchased_user
SET is_active = FALSE
WHERE order_id = :order_id;
        """
    )
    try:
        await db_session.execute(query, {"order_id": order_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error in occurred in invalidating pre-purchased user details: {e}", extra={"order_id": order_id})
