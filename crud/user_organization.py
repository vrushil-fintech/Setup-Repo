from typing import Dict, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_user_organization_link(db_session: AsyncSession, user_id: str, organization_id: str, role: str):
    sql_query = text(
        """
INSERT INTO codesherlock.user_organization (user_id, organization_id, role)
VALUES (:user_id, :organization_id, :role)
ON CONFLICT DO NOTHING;
    """
    )
    try:
        await db_session.execute(sql_query, {"user_id": user_id, "organization_id": organization_id, "role": role})
        logger.info("User organization links created", extra={"user_id": user_id, "organization_id": organization_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"user_id": user_id, "organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def create_user_organization_link_bulk(db_session: AsyncSession, user_org_data: List[Dict[str, str | None]]):
    EXPECTED_KEYS = {"user_id", "organization_id", "role"}
    valid_data = []

    for entry in user_org_data:
        if not EXPECTED_KEYS.issubset(entry.keys()):
            logger.error("Invalid user organization data structure.", extra={"entry": entry})
            return
        if None in entry.values():
            logger.error("Null values present in entry. User ID, Organization ID, and Role must not be null.", extra={"entry": entry})
            return
        valid_data.append(entry)

    sql_query = text(
        """
INSERT INTO codesherlock.user_organization (user_id, organization_id, role)
VALUES (:user_id, :organization_id, :role)
ON CONFLICT DO NOTHING;
    """
    )
    try:
        await db_session.execute(sql_query, user_org_data)
        logger.info("User organization links created")
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_organization_id_for_user_id(db_session: AsyncSession, user_id: str):
    sql_query = text(
        """
SELECT uo.organization_id, uo.role
FROM codesherlock.user_organization uo
JOIN codesherlock.github_installation gi ON uo.organization_id = gi.organization_id
WHERE uo.user_id = :user_id AND gi.is_active = TRUE;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"user_id": user_id})
        result = db_result.fetchall()
        org_ids = [(str(row[0]), row[1]) for row in result] if result else None
        logger.info(f"Organization ids retrieved", extra={"user_id": user_id})
        return org_ids
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_user_id_role_for_organization_id(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
SELECT uo.user_id, uo.role
FROM codesherlock.user_organization uo
JOIN codesherlock.github_installation gi ON uo.organization_id = gi.organization_id
WHERE uo.organization_id = :organization_id AND gi.is_active = TRUE;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"organization_id": organization_id})
        result = db_result.fetchall()
        logger.info(f"User ids and roles retrieved", extra={"organization_id": organization_id})
        if result:
            return [{
                "user_id": str(row[0]),
                "role": row[1]
            } for row in result
            ]

        return None

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def delete_user_organization_link(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
UPDATE codesherlock.user_organization
SET is_active = FALSE
WHERE organization_id = :organization_id;
    """
    )
    try:
        await db_session.execute(sql_query, {"organization_id": organization_id})
        logger.info(f"User organization links deleted", extra={"organization_id": organization_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return


async def get_user_org_row(db_session: AsyncSession, user_id: str, organization_id: str):
    sql_query = text(
        """
SELECT *
FROM codesherlock.user_organization
WHERE user_id = :user_id
  AND organization_id = :organization_id;
        """
    )

    try:
        db_result = await db_session.execute(
            sql_query,
            {"user_id": user_id, "organization_id": organization_id},
        )
        row = db_result.mappings().first()  # return a single row as dict-like

        logger.info(
            "User-organization row retrieved successfully",
            extra={"user_id": user_id, "organization_id": organization_id},
        )

        if row:
            return dict(row)

        return None

    except Exception as e:
        await db_session.rollback()
        logger.error(
            f"Database error occurred: {e}",
            extra={"user_id": user_id, "organization_id": organization_id},
        )
        raise HTTPException(
            status_code=503,
            detail="We're having trouble retrieving user organization data. Please try again later.",
        )