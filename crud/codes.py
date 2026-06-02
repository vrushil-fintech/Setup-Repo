from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import logger


async def create_code(
    db_session: AsyncSession,
    email: str,
    code: str,
    creation_time: str,
    expiry_time: str,
    status: str,
):
    sql_query = text("""
                INSERT INTO codesherlock.verif_code (email, code, creation_time, expiry_time, status)
                VALUES (:email, :code, :creation_time, :expiry_time, :status)
                ON CONFLICT (email) DO UPDATE 
                SET code = EXCLUDED.code, 
                    creation_time = EXCLUDED.creation_time, 
                    expiry_time = EXCLUDED.expiry_time, 
                    status = EXCLUDED.status;
                """)
    try:
        await db_session.execute(sql_query, {"email": email, "code": code, "creation_time": creation_time, "expiry_time": expiry_time, "status": status})
        logger.info(f"Successfully created or updated verification code", extra={"email": email})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having trouble creating your OTP. Please try again later.")
    
async def get_code(db_session: AsyncSession, email: str, code: str):
    sql_query = text("""
            SELECT 1 FROM codesherlock.verif_code
            WHERE email = :email 
            AND code = :code 
            AND status = 'Valid' 
            AND expiry_time >= NOW() 
            LIMIT 1;
            """)
    try:
        db_result = await db_session.execute(sql_query, {"email": email, "code": code})
        result = db_result.fetchone()
        logger.info(f"Verification code retrieved", extra={"email": email})
        return result
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"email": email})
        raise HTTPException(status_code=503, detail="We're having trouble checking your OTP. Please try again later.")

async def update_code(db_session: AsyncSession, email: str, code: str, status: str):
    sql_query = text("""
                UPDATE codesherlock.verif_code
                SET status = :status 
                WHERE verif_code.email = :email AND verif_code.code = :code
                """)
    try:
        await db_session.execute(sql_query, {"email": email, "code": code, "status": status})
    except Exception as e:
        await db_session.rollback()
        logger.error("Database error occured: %s", str(e)) 
        raise HTTPException(status_code=503, detail="We're having trouble checking your OTP. Please try again later.")