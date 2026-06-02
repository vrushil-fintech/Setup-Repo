from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import logger
from app.database import get_mongo_db
from app.crud.mongo.coding_tips import get_coding_tips_mongo

router = APIRouter()


@router.get("/loading_tips")
async def usage_handler(
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        result = await get_coding_tips_mongo(mongo_db)
        return result
    except Exception as e:
        # dont do anything here
        return []
