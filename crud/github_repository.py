from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_github_repository(db_session: AsyncSession, repo_name: str, repo_full_name: str, github_id: int, organization_id: str, github_html_url: str):
    if not repo_name or not repo_full_name or not organization_id or not github_html_url:
        raise Exception(detail="All fields are required while inserting in github repository.")

    is_active = True
    sql_query = text(
        """
INSERT INTO codesherlock.github_repository (name, full_name, github_id, organization_id, github_html_url, is_active)
VALUES (:name, :full_name, :github_id, :organization_id, :github_html_url, :is_active);
"""
    )
    try:
        await db_session.execute(
            sql_query,
            {
                "name": repo_name,
                "full_name": repo_full_name,
                "github_id": github_id,
                "organization_id": organization_id,
                "github_html_url": github_html_url,
                "is_active": is_active
            },
        )
        logger.info(f"Successfully inserted github repository details", extra={"repo_name": repo_name})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"repo_name": repo_name})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble processing your request. Please try again later.",
        )

    return

async def get_github_repository(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
SELECT github_id, name, full_name, github_html_url
FROM codesherlock.github_repository
WHERE organization_id = :organization_id AND is_active = TRUE;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {"organization_id": organization_id})
        result = db_result.fetchall()
        logger.info(f"Successfully retrieved github repository details", extra={"organization_id": organization_id})
        if result:
            repos = []
            for row in result:
                repos.append({
                    "github_id": row[0],
                    "name": row[1],
                    "full_name": row[2],
                    "github_html_url": row[3]
                })
            
            return repos
        return []
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble processing your request. Please try again later.",
        )

async def get_github_repository_on_fullname(db_session: AsyncSession, repo_full_name: str):
    sql_query = text(
        """
SELECT id, full_name
FROM codesherlock.github_repository
WHERE full_name = :repo_full_name AND is_active = TRUE;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {"repo_full_name": repo_full_name})
        result = db_result.fetchone()
        logger.info(f"Successfully retrieved github repository details", extra={"repo_full_name": repo_full_name})
        if result:
            return {
                "id": result[0],
                "full_name": result[1]
            }
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"repo_full_name": repo_full_name})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble processing your request. Please try again later.",
        )

async def delete_github_repository_on_github_id(db_session: AsyncSession, github_id: int):
    sql_query = text(
        """
UPDATE codesherlock.github_repository
SET is_active = FALSE
WHERE github_id = :github_id;
"""
    )

    try:
        await db_session.execute(sql_query, {"github_id": github_id})
        logger.info(f"Successfully deleted github repository details", extra={"github_id": github_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"github_id": github_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble processing your request. Please try again later.",
        )
    
    return

async def delete_github_repository_on_organization_id(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
UPDATE codesherlock.github_repository
SET is_active = FALSE
WHERE organization_id = :organization_id;
"""
    )

    try:
        await db_session.execute(sql_query, {"organization_id": organization_id})
        logger.info(f"Successfully deleted github repository details", extra={"organization_id": organization_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"organization_id": organization_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble processing your request. Please try again later.",
        )
    
    return
