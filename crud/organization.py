from typing import List
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_organization(db_session: AsyncSession, name: str, type: str, platform_type_id: int, platform_id: int, enterprise_id: str = None):
    if not name or not type:
        logger.error("Invalid input: name and type cannot be empty.")
        raise Exception(detail="Invalid input: name and type cannot be empty.")

    sql_query = text(
        """
INSERT INTO codesherlock.organization (name, type, platform_type_id, platform_id, enterprise_id)
VALUES (:name, :type, :platform_type_id, :platform_id, :enterprise_id)
    """
    )
    try:
        await db_session.execute(sql_query, {"name": name, "type": type, "platform_type_id": platform_type_id, "platform_id": platform_id, "enterprise_id": enterprise_id})
        logger.info("Organization created", extra={"org_name": name, "type": type, "platform_type_id": platform_type_id, "platform_id": platform_id, "enterprise_id": enterprise_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"org_name": name, "type": type, "platform_type_id": platform_type_id, "platform_id": platform_id, "enterprise_id": enterprise_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

    return

async def get_organization(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
SELECT name, type, platform_type_id, platform_id FROM codesherlock.organization
WHERE id = :organization_id;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"organization_id": organization_id})
        result = db_result.fetchone()
        logger.info(f"Organization retrieved", extra={"organization_id": organization_id})
        if result:
            return {
                "name": result[0],
                "type": result[1],
                "platform_type_id": result[2],
                "platform_id": result[3]
            }
        else:
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

async def get_organization_id_from_github_id(db_session: AsyncSession, platform_type_id: int, platform_id: int):
    sql_query = text(
        """
SELECT id, type FROM codesherlock.organization
WHERE platform_type_id = :platform_type_id AND platform_id = :platform_id;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"platform_type_id": platform_type_id, "platform_id": platform_id})
        result = db_result.fetchone()
        logger.info(f"Organization retrieved", extra={"platform_id": platform_id})
        if result:
            return {
                "id": str(result[0]),
                "type": result[1]
            }
        else: 
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"platform_id": platform_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )
async def get_organization_id_from_name(db_session: AsyncSession, name: str):
    sql_query = text(
        """
SELECT id FROM codesherlock.organization
WHERE name = :name;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {"name": name})
        result = db_result.fetchone()
        logger.info(f"Organization retrieved", extra={"org_name": name})
        if result:
            return str(result[0])
        else:
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"org_name": name})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )

async def get_organization_id_installation_id(db_session: AsyncSession, github_organization_ids: List[int]):
    sql_query = text(
        """
SELECT o.id, o.type, o.platform_id, i.installation_id
FROM codesherlock.organization AS o
JOIN codesherlock.github_installation AS i
ON o.id = i.organization_id
WHERE o.platform_type_id = 1 AND o.platform_id IN :github_organization_ids AND i.is_active = TRUE;
"""
    ).bindparams(bindparam("github_organization_ids", expanding=True))
    try:
        db_result = await db_session.execute(sql_query, {"github_organization_ids": github_organization_ids})
        result = db_result.fetchall()
        logger.info(f"Active installations and Organizations retrieved")
        if result:
            mapping = []
            for row in result:
                mapping.append({
                    "organization_id": str(row[0]),
                    "type": row[1],
                    "platform_id": row[2],
                    "installation_id": row[3]
                })
            return mapping
        
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}")
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )
