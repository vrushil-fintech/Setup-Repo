from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.crud.mongo.code_chunks import get_code_chunks
from app.dependencies import logger

def _choose_pr_or_commit(pr_number, commit_id):
    return pr_number if pr_number is not None else commit_id

async def search_imports_in_db(mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
    """
    Search imports in database and return chunks.
    Appropriate for Python, Javascript, and Typescript.
    """
    chunks = []
    if imports:
        for imp in imports:
            chunk = await get_code_chunks(
                mongo_db=mongo_db,
                chunk_name=imp["chunk_name"],
                file_path=imp["imported_from"],
                user_id=user_id,
                pr_number=pr_number,
                commit_id=commit_id,
                repo_name=repo_name
            )
            if chunk:
                chunks.extend(chunk)
    else:
        logger.info(f"No imports found file: {file_path}.")

    return chunks

async def search_imports_java(mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
    chunks = await get_code_chunks(mongo_db=mongo_db, user_id=user_id, pr_number=pr_number, commit_id=commit_id, repo_name=repo_name)
    if not chunks:
        logger.warning("No chunks found from db.", extra={"file_path": file_path, "pr_number": pr_number, "commit_id": commit_id, "user_id": user_id, "repo_name": repo_name})
        return []
    
    matched_chunks = []
    for imp in imports:
        imported_from = imp["imported_from"]
        chunk_name = imp["chunk_name"]

        for chunk in chunks:
            chunk_path = chunk['file_path']

            if chunk_name == '*':
                # Wildcard import: check if imported_from is a directory in chunk_path
                if imported_from in chunk_path:
                    matched_chunks.append(chunk)

            else:
                # Exact class import: check if chunk_path ends with imported_from
                if chunk_path.endswith(imported_from):
                    matched_chunks.append(chunk)

    return matched_chunks

async def search_imports_csharp(mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
    chunks = await get_code_chunks(mongo_db=mongo_db, user_id=user_id, pr_number=pr_number, commit_id=commit_id, repo_name=repo_name)
    if not chunks:
        return []

    matched_chunks = []
    # Build a lookup map of namespace → list of chunks
    namespace_to_chunks = {}
    for chunk in chunks:
        ns = chunk.get("namespace")
        if ns not in namespace_to_chunks:
            namespace_to_chunks[ns] = []
        namespace_to_chunks[ns].append(chunk)

    for imp in imports:
        imported_from = imp["imported_from"]
        import_type = imp["import_type"]
        alias_name = imp["alias_name"]

        # Simple match: exact namespace
        if imported_from in namespace_to_chunks:
            matched_chunks.extend(namespace_to_chunks[imported_from])

        # Optional (advanced): fuzzy match — namespaces that start with imported_from
        for ns, chunks_list in namespace_to_chunks.items():
            if ns and ns.startswith(imported_from + ".") and chunks_list not in matched_chunks:
                matched_chunks.extend(chunks_list)

    return matched_chunks