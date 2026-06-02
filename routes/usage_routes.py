from fastapi import APIRouter, Depends
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import logger
from app.database import get_db

router = APIRouter()

@router.get("/usage")
async def usage_handler(db_session: AsyncSession = Depends(get_db)):
    sql_query = text("""
SELECT 
    users_t.email,
    u.api_key,
    u.model,
    u.created_at,
    u.input_tokens,
    u.response_tokens,
    u.usage_cost
FROM 
    codesherlock.usage AS u
LEFT JOIN 
    codesherlock.users AS users_t ON u.userid = users_t.userid
ORDER BY u.created_at DESC
LIMIT 100;
""")
    try:
        db_result = await db_session.execute(sql_query)
        data = list(db_result.fetchall())
        result = []
        for item in data:
            email, api_key, model, created_at, input_tokens, response_tokens, usage_cost = item
            result.append(
                {
                    "email": email,
                    "api_key": api_key,
                    "model": model,
                    "created_at": created_at,
                    "input_tokens": input_tokens,
                    "response_tokens": response_tokens,
                    "usage_cost": usage_cost,
                }
            )
        logger.info("Usage information retrieved successfully.")
        # connection.close()
        return result
    except Exception as e:
        await db_session.rollback()
        logger.error("Error fetching usage info: %s", str(e))
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")