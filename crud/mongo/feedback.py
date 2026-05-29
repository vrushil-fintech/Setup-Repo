from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

# from app.models import (

# )
from app.dependencies import logger


async def update_feedback_mongo(
    mongo_db: AsyncIOMotorDatabase, user_id: str, analysis_id: str, feedback: str
):
    if not ObjectId.is_valid(analysis_id):
        raise Exception("Invalid analysis id.")

    analysis_id = ObjectId(analysis_id)
    try:
        query = {"_id": analysis_id, "user_id": user_id}
        await mongo_db.get_collection("factor_analysis").update_one(
            query, {"$set": {"feedback": feedback}}
        )
        logger.info(
            "Feedback %s updated for analysis id %s.",
            feedback,
            str(analysis_id),
            extra={"user_id": str(user_id)},
        )
    except Exception as e:
        logger.error(f"Database error occured: {e}", extra={"user_id": user_id})
        raise Exception(
            "We're having trouble updating your feedback. Please try again later."
        )
