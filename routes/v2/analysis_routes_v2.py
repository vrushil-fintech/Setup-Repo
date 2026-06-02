from datetime import timezone
from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.ext.asyncio import AsyncSession
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import AnalysisHistoryResponse, FactorAnalysisResponse
from app.dependencies import logger
from app.database import get_db, get_mongo_db
from app.crud.analyses import get_analysis, get_history, get_pr_history, get_pr_analysis
from app.crud.mongo.analyses import get_analysis_mongo, get_history_mongo

router = APIRouter()


@router.get("/analysis/{user_id}", response_model=AnalysisHistoryResponse)
async def history_handler(
    user_id: str,
    db_session: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    history_data = []
    try:
        mongo_history_data = await get_history_mongo(mongo_db, user_id)
        history_data += mongo_history_data

        if len(history_data) < 5:
            pg_history_data = await get_history(
                db_session, user_id, 5 - len(history_data)
            )
            history_data += pg_history_data

        for item in history_data:
            item["created_at"] = item["created_at"].replace(tzinfo=timezone.utc)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {"analysis_history": history_data}


@router.get("/pr-analysis/{user_id}")
async def pr_history_handler(
    user_id: str,
    db_session: AsyncSession = Depends(get_db),
):
    try:
        pr_history_data = await get_pr_history(db_session, user_id)

        for item in pr_history_data:
            item["created_at"] = item["created_at"].replace(tzinfo=timezone.utc)

        return {"analysis_history": pr_history_data}

    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/analysis/{user_id}/{analysis_id}", response_model=FactorAnalysisResponse)
async def get_analysis_handler(
    user_id: str,
    analysis_id: str,
    db_session: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        if ObjectId.is_valid(analysis_id):
            data = await get_analysis_mongo(mongo_db, user_id, analysis_id)
            data["analysis_type"] = "structured"
        else:
            data = await get_analysis(db_session, user_id, int(analysis_id))
            data["analysis_type"] = "markdown"

    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if data is None:
        raise HTTPException(
            status_code=404, detail="Whoops! Looks like we couldn't find that analysis."
        )

    return data


@router.get("/pr-analysis/{user_id}/{analysis_id}")
async def get_pr_analysis_handler(
    user_id: str,
    analysis_id: str,
    db_session: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        data = await get_pr_analysis(db_session, user_id, analysis_id)
        data["analysis_type"] = "markdown"

    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    if data is None:
        raise HTTPException(
            status_code=404,
            detail="Whoops! Looks like we couldn't find that PR analysis.",
        )

    return data
