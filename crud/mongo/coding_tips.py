from motor.motor_asyncio import AsyncIOMotorDatabase
from app.dependencies import logger


async def get_coding_tips_mongo(mongo_db: AsyncIOMotorDatabase):
    try:
        result = await mongo_db.get_collection("coding_tips").find().to_list(length=15)
        for item in result:
            item["id"] = str(item.pop("_id", None))
        logger.info("Coding tips retrieved")
        return result
    except Exception as e:
        logger.error("Error fetching coding tips: %s", str(e))