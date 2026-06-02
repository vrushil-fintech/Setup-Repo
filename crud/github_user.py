import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_github_user(db_session: AsyncSession, user_id: str, github_id: int, github_login: str):
    sql_query = text(
        """
INSERT INTO codesherlock.github_user (user_id, github_id, github_login)
VALUES (:user_id, :github_id, :github_login);
    """
    )
    try:
        await db_session.execute(sql_query, {"user_id": user_id, "github_id": github_id, "github_login": github_login})
        logger.info("Github user created", extra={"user_id": user_id, "github_id": github_id, "github_login": github_login})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"user_id": user_id, "github_id": github_id, "github_login": github_login})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_github_id_from_user_id(db_session: AsyncSession, user_id: str):
    sql_query = text(
        """
SELECT github_id FROM codesherlock.github_user
WHERE user_id = :user_id;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"user_id": user_id})
        result = db_result.fetchone()
        logger.info(f"Github id retrieved", extra={"user_id": user_id})
        if result:
            return result[0]
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_user_id_from_github_id(db_session: AsyncSession, github_id: int):
    sql_query = text(
        """
SELECT user_id FROM codesherlock.github_user
WHERE github_id = :github_id;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"github_id": github_id})
        result = db_result.fetchone()
        logger.info(f"User id retrieved", extra={"github_id": github_id})
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"github_id": github_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_user_ids_from_github_ids(
    db_session: AsyncSession, github_ids: list[int]
) -> dict[str, int]:
    try:
        query = text(
            """
            SELECT user_id, github_id
            FROM codesherlock.github_user
            WHERE github_id = ANY(:github_ids)
            """
        )

        result = await db_session.execute(query, {"github_ids": github_ids})
        rows = result.fetchall()

        return {row[0]: row[1] for row in rows}  # user_id: github_id

    except Exception as e:
        logger.error(
            f"Error fetching user_ids from github_ids: {str(e)}",
            extra={"github_ids": github_ids},
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve user IDs.")

    return
