from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import logger

async def update_feedback(db_session: AsyncSession, user_id: str, analysis_id: int, feedback: str):
    sql_query = text(
        """
UPDATE codesherlock.analyses
SET feedback = :feedback
WHERE userid = :user_id AND analysisid = :analysis_id;  
"""
    )
    try:
        await db_session.execute(sql_query, {"user_id": user_id, "analysis_id": analysis_id, "feedback": feedback})
        logger.info("Feedback updated for analysis id %s.", analysis_id, extra={"user_id":str(user_id)})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"user_id": user_id})
        raise Exception("We're having trouble updating your feedback. Please try again later.")