from datetime import datetime, timezone
import json
from typing import List
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models import (
    CharAnalysis,
    CharAnalysisResponse,
    FactorAnalysis,
    FactorAnalysisResponse,
    IssueItemResponse,
)
from app.dependencies import SEVERITY_MAP, logger


async def insert_analysis_mongo(
    mongo_db: AsyncIOMotorDatabase,
    user_id: str,
    char_analysis_response_list: List[CharAnalysisResponse],
    factor: str,
    file_name: str,
    language: str,
    analysis_platform: str
):
    char_analysis_list = []
    char_analysis_ids = None
    try:
        for char_analysis_response in char_analysis_response_list:
            issue_items_list = char_analysis_response.get("issue_items", [])
            issue_items_list = [item for item in issue_items_list if item is not None] # Filter out None values
            issue_item_ids = []
            
            if issue_items_list:
                result = await mongo_db.get_collection("issue_items").insert_many(
                    issue_items_list
                )
                issue_item_ids = result.inserted_ids

                char_analysis = {
                    "characteristic": char_analysis_response["characteristic"],
                    "description_of_characteristic": char_analysis_response[
                        "description_of_characteristic"
                    ],
                    "issue_items": issue_item_ids,
                }

                char_analysis_list.append(char_analysis)
    except Exception as e:
        # json_data = [item.model_dump() for item in char_analysis_response_list]  # model_dump() for dict conversion

        # # Step 4: Save to a local JSON file
        # file_path = "error.json"
        # with open(file_path, "w", encoding="utf-8") as f:
        #     json.dump(json_data, f, indent=4)
        logger.error(
            "Error inserting issue items: %s", str(e), extra={"user_id": user_id}
        )
        raise Exception(
            "We're having trouble saving your analysis. Please try again later."
        )

    if char_analysis_list:
        try:
            factor_analysis_result = await mongo_db.get_collection(
                "char_analysis"
            ).insert_many(char_analysis_list)
            char_analysis_ids = factor_analysis_result.inserted_ids
        except Exception as e:
            logger.error(
                "Error inserting char analysis: %s", str(e), extra={"user_id": user_id}
            )
            raise Exception(
                "We're having trouble saving your analysis. Please try again later."
            )

    if char_analysis_ids:
        try:
            factor_analysis_result = await mongo_db.get_collection(
                "factor_analysis"
            ).insert_one(
                {
                    "user_id": user_id,
                    "factor": factor,
                    "created_at": (datetime.now(timezone.utc)),
                    "analysis": char_analysis_ids,
                    "file_name": file_name,
                    "feedback": "Not Responded",
                    "language": language,
                    "analysis_platform": analysis_platform,
                }
            )
        except Exception as e:
            logger.error(
                "Error inserting factor analysis: %s",
                str(e),
                extra={"user_id": user_id},
            )
            raise Exception(
                "We're having trouble saving your analysis. Please try again later."
            )

        analysis_id = factor_analysis_result.inserted_id
        logger.info("Analysis inserted in history.", extra={"user_id": str(user_id), "analysis_id": str(analysis_id)})
        return str(analysis_id)

    return None


async def get_analysis_mongo(
    mongo_db: AsyncIOMotorDatabase, user_id: str, analysis_id: str
):
    if not ObjectId.is_valid(analysis_id):
        raise Exception("Invalid analysis id.")

    analysis_id = ObjectId(analysis_id)
    try:
        query = {"_id": analysis_id, "user_id": user_id}
        projection = {"user_id": 1,"factor": 1, "created_at": 1, "file_name": 1, "language": 1, "analysis": 1, "feedback": 1}
        factor_analysis_result = await mongo_db.get_collection(
            "factor_analysis"
        ).find_one(query, projection)
        if not factor_analysis_result:
            logger.warning(
                "Analysis not found in MongoDB.",
                extra={"user_id": str(user_id), "analysis_id": str(analysis_id)},
            )
            return None

        if factor_analysis_result:
            factor_analysis_result["id"] = factor_analysis_result.pop("_id", None)
            char_analysis_ids = factor_analysis_result.pop("analysis", None)

            if char_analysis_ids:
                char_analysis_list = (
                    await mongo_db.get_collection("char_analysis")
                    .find({"_id": {"$in": char_analysis_ids}})
                    .to_list(length=len(char_analysis_ids))
                )

                if char_analysis_list:
                    for char_analysis in char_analysis_list:
                        char_analysis.pop("_id", None)
                        issue_item_ids = char_analysis.pop("issue_items", None)

                        if issue_item_ids:
                            issue_item_list = (
                                await mongo_db.get_collection("issue_items")
                                .find({"_id": {"$in": issue_item_ids}})
                                .to_list(length=len(issue_item_ids))
                            )

                            if issue_item_list:
                                for issue_item in issue_item_list:
                                    issue_item["id"] = str(issue_item.pop("_id", None))
                                    if not issue_item.get("severity_level", None):
                                        severity_text = issue_item.get("severity", None)
                                        if severity_text:
                                            severity_level = SEVERITY_MAP.get(severity_text.lower(), 1)
                                            issue_item["severity_level"] = severity_level

                                char_analysis["issue_items"] = issue_item_list

                    factor_analysis_result["analysis"] = char_analysis_list
        
        logger.info("Analysis %s retrieved for user", str(analysis_id), extra={"user_id": str(user_id)})
        return factor_analysis_result
    except Exception as e:
        logger.error(
            "Error fetching analysis %s for user: %s",
            str(analysis_id),
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading your analysis. Please try again later."
        )


async def get_history_mongo(mongo_db: AsyncIOMotorDatabase, user_id: str):
    try:
        query = {"user_id": user_id}
        projection = {"factor": 1, "created_at": 1, "file_name": 1}
        result = (
            await mongo_db.get_collection("factor_analysis")
            .find(query, projection)
            .sort("created_at", -1)
            .limit(5)
            .to_list(length=5)
        )
        for item in result:
            item["id"] = str(item.pop("_id", None))
            item.pop("analysis", None)
        logger.info("History retrieved for user", extra={"user_id": str(user_id)})
        return result
    except Exception as e:
        logger.error(
            "Error fetching history for user: %s",
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading your history. Please try again later."
        )
