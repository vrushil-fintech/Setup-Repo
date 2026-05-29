from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import logger

# from app.dependencies import logger

async def add_code_chunks(mongo_db: AsyncIOMotorDatabase, code_chunks: List, pr_number=None, commit_id=None, user_id=None, repo_name=None):
    try:
        for code_chunk in code_chunks:
            if pr_number is not None:
                code_chunk["pr_number"] = pr_number
            if commit_id is not None:
                code_chunk["commit_id"] = commit_id
            code_chunk["user_id"] = user_id
            code_chunk["repo_name"] = repo_name

        result = await mongo_db.get_collection("code_chunks").insert_many(code_chunks)
        return result.inserted_ids
    except Exception as e:
        logger.error(f"Error inserting code chunks: {str(e)}", extra={"pr_number": pr_number, "commit_id": commit_id, "user_id": user_id, "repo_name": repo_name})

async def get_code_chunks(mongo_db: AsyncIOMotorDatabase, chunk_name=None, file_path=None, file_name=None, user_id=None, pr_number=None, commit_id=None, repo_name=None):
    try:
        # Build query dynamically, ignoring None values
        query = {
            key: value for key, value in {
                "user_id": user_id,
                "chunk_name": chunk_name,
                "file_name": file_name,
                "file_path": file_path,
                "repo_name": repo_name
            }.items() if value is not None
        }
        # Prefer pr_number if provided, else use commit_id
        if pr_number is not None:
            query["pr_number"] = pr_number
        elif commit_id is not None:
            query["commit_id"] = commit_id

        result = await mongo_db.get_collection("code_chunks").find(query).to_list()
        return result
    except Exception as e:
        logger.error(f"Error fetching code chunks: {str(e)}", extra={"pr_number": pr_number, "commit_id": commit_id, "user_id": user_id, "repo_name": repo_name})

async def delete_code_chunks(mongo_db: AsyncIOMotorDatabase, user_id: str, repo_name: str, pr_number=None, commit_id=None):
    try:
        query = {
            "user_id": user_id,
            "repo_name": repo_name
        }
        if pr_number is not None:
            query["pr_number"] = int(pr_number)
        elif commit_id is not None:
            query["commit_id"] = commit_id

        result = await mongo_db.get_collection("code_chunks").delete_many(query)
        return result.deleted_count
    except Exception as e:
        logger.error(f"Error deleting code chunks: {str(e)}", extra={"pr_number": pr_number, "commit_id": commit_id, "user_id": user_id, "repo_name": repo_name})