from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import logger
from app.models import User


async def insert_user(
    db_session: AsyncSession, userid: str, name: str, email: str, hashed_password: str, organization: str = None
):
    sql_query = text("""
        INSERT INTO codesherlock.users (userid, name, email, hashpass, organization)
        VALUES (:userid, :name, :email, :hashpass, :organization)
        """)
    try:
        await db_session.execute(sql_query, {
            "userid": userid,
            "name": name,
            "email": email,
            "hashpass": hashed_password,
            "organization": organization
        })
        logger.info(f"User inserted", extra={"email": email})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having trouble creating your account. Please try again later.")

async def get_user(db_session: AsyncSession, email: str):
    sql_query = text("SELECT users.userid, users.name, users.email, users.organization FROM codesherlock.users WHERE users.email = :email")
    try:
        db_result = await db_session.execute(sql_query, {"email": email})
        result = db_result.fetchone()
        if result is None:
            return None
        userid, name, email, organization = result
        logger.info(f"User retrieved", extra={"email": email})
        email_domain = email.split('@')[-1]
        if email_domain == "fintechglobal.center":
            role = True
        else:
            role = False

        return User(userid=str(userid), name=name, email=email, organization=organization, role=role)
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having trouble fetching your details. Please try again later.")


async def get_user_by_id(db_session: AsyncSession, user_id: str):
    sql_query = text("""
        SELECT 
            users.userid, 
            users.name, 
            users.email, 
            users.organization, 
            users.created_at
        FROM codesherlock.users 
        WHERE users.userid = :user_id
    """)

    try:
        db_result = await db_session.execute(sql_query, {"user_id": user_id})
        result = db_result.fetchone()

        if result is None:
            return None

        # Safely unpack columns
        userid, name, email, organization, created_at = result

        logger.info(f"User retrieved by ID", extra={"user_id": user_id})

        # Determine role based on email domain
        email_domain = email.split('@')[-1]
        role = email_domain == "fintechglobal.center"

        # Return your User model (assuming it accepts these fields)
        return User(
            userid=str(userid),
            name=name,
            email=email,
            organization=organization,
            role=role,
            created_at=created_at
        )

    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your details. Please try again later."
        )