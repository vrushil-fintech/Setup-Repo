import asyncio
from abc import ABC, abstractmethod
from typing import List, Type
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorClient

from app.crud.mongo.code_chunks import add_code_chunks
from app.services.rag_services.chunk_finder import search_imports_csharp, search_imports_in_db, search_imports_java
from app.services.rag_services.csharp_chunker import csharp_chunk_file, csharp_imports_parse
from app.services.rag_services.java_chunker import java_chunk_file, java_imports_parse
from app.services.rag_services.js_chunker import (
    js_chunk_file,
    js_ts_imports_parse,
    ts_chunk_file,
)
from app.services.rag_services.python_chunker import (
    python_chunk_file,
    python_imports_parse,
)
from app.config import MONGODB_CONFIG
from app.dependencies import EXTENSION_TO_LANGUAGE, logger


class LanguageHandler(ABC):
    @abstractmethod
    async def chunk_file(self, code: str, file_path: str):
        pass

    @abstractmethod
    async def parse_imports(self, code: str, file_path: str):
        pass

    @abstractmethod
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        pass


class PythonHandler(LanguageHandler):
    async def chunk_file(self, code: str, file_path: str, file_name: str):
        return await python_chunk_file(
            code=code, file_path=file_path, file_name=file_name
        )

    async def parse_imports(self, code: str, file_path: str):
        return await python_imports_parse(code=code, file_path=file_path)
    
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        return await search_imports_in_db(mongo_db, imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name)


class JavaScriptHandler(LanguageHandler):
    async def chunk_file(self, code: str, file_path: str, file_name: str):
        return await js_chunk_file(code=code, file_path=file_path, file_name=file_name)

    async def parse_imports(self, code: str, file_path: str):
        return await js_ts_imports_parse(code=code, file_path=file_path)
    
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        return await search_imports_in_db(mongo_db, imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name)


class TypescriptHandler(LanguageHandler):
    async def chunk_file(self, code: str, file_path: str, file_name: str):
        return await ts_chunk_file(code=code, file_path=file_path, file_name=file_name)

    async def parse_imports(self, code: str, file_path: str):
        return await js_ts_imports_parse(code=code, file_path=file_path)
    
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        return await search_imports_in_db(mongo_db, imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name)


class JavaHandler(LanguageHandler):
    async def chunk_file(self, code: str, file_path: str, file_name: str):
        return await java_chunk_file(code=code, file_path=file_path, file_name=file_name)

    async def parse_imports(self, code: str, file_path: str):
        return await java_imports_parse(code=code, file_path=file_path)
    
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        return await search_imports_java(mongo_db, imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name)


class CSharpHandler(LanguageHandler):
    async def chunk_file(self, code: str, file_path: str, file_name: str):
        return await csharp_chunk_file(code=code, file_path=file_path, file_name=file_name)

    async def parse_imports(self, code: str, file_path: str):
        return await csharp_imports_parse(code=code)
    
    async def retrieve_relevant_chunks(self, mongo_db: AsyncIOMotorDatabase, imports: List, pr_number: int = None, commit_id: str = None, file_path: str = None, user_id: str = None, repo_name: str = None):
        return await search_imports_csharp(mongo_db, imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name)

# 3. Language to handler registry
LANGUAGE_HANDLER_CLASSES: dict[str, Type[LanguageHandler]] = {
    "python": PythonHandler,
    "javascript": JavaScriptHandler,
    "typescript": TypescriptHandler,
    "java": JavaHandler,
    "csharp": CSharpHandler
}


# 4. The generic router functions
async def chunk_code_and_save_to_db(
    code: str,
    mongo_db: AsyncIOMotorDatabase,
    user_id: str,
    file_path: str,
    repo_name: str,
    pr_number: int = None,
    commit_id: str = None,
):
    file_name = file_path.split("/")[-1]
    extension = "." + file_path.split(".")[-1]
    code_language = EXTENSION_TO_LANGUAGE.get(extension, "none")
    if code_language == "none":
        logger.warning(f"Unknown file extension: {extension}, file_path: {file_path}")
        return []
    handler_class = LANGUAGE_HANDLER_CLASSES.get(code_language.lower())
    if not handler_class:
        logger.warning(f"Unsupported language: {code_language}, file_path: {file_path}")
        return []

    try:
        handler = handler_class()
        chunks = await handler.chunk_file(code=code, file_path=file_path, file_name=file_name)
        logger.info(f"{len(chunks)} chunks extracted from file: {file_path}.")

        if chunks:
            chunk_ids = await add_code_chunks(
                mongo_db=mongo_db, code_chunks=chunks, pr_number=pr_number, commit_id=commit_id, user_id=user_id, repo_name=repo_name
            )
            return chunk_ids
        else:
            logger.info(f"No chunks created from file: {file_path}.")
            return []
    except Exception as e:
        logger.error(f"Error chunking file: {file_path}. Error: {str(e)}")
        return []


async def parse_code_and_extract_chunks(
    code: str,
    mongo_db: AsyncIOMotorDatabase,
    user_id: str,
    file_path: str,
    repo_name: str,
    pr_number: int = None,
    commit_id: str = None,
):
    file_name = file_path.split("/")[-1]
    extension = "." + file_path.split(".")[-1]
    print(file_name , extension)
    code_language = EXTENSION_TO_LANGUAGE.get(extension, "none")
    print(code_language)
    if code_language == "none":
        logger.warning(f"Unknown file extension: {extension}, file_path: {file_path}")
        return []
    handler_class = LANGUAGE_HANDLER_CLASSES.get(code_language.lower())
    if not handler_class:
        logger.warning(f"Unsupported language: {code_language}, file_path: {file_path}")
        return []
    try:
        print(f"🔍 Parsing code and extracting chunks for {file_path}")
        handler = handler_class()
        imports = await handler.parse_imports(code=code, file_path=file_path)
        logger.info(f"{len(imports)} imports extracted from file: {file_path}.")
    except Exception as e:
        logger.error(f"Error parsing imports for file: {file_path}. Error: {str(e)}")
        return []
    try:
        # Pass both pr_number and commit_id to handler
        chunks = await handler.retrieve_relevant_chunks(
            mongo_db=mongo_db, imports=imports, pr_number=pr_number, commit_id=commit_id, file_path=file_path, user_id=user_id, repo_name=repo_name
        )
        logger.info(f"{len(chunks)} chunks found relevant for file: {file_path}.")
        return chunks
    except Exception as e:
        logger.error(f"Error retrieving relevant chunks for file: {file_path}. Error: {str(e)}")
        return []

if __name__ == "__main__":
    code = ""
    with open("app/services/websocket_manager.py", "r") as f:
        code = f.read()

    client = AsyncIOMotorClient(MONGODB_CONFIG["conn_url"])
    mongo_db = client.get_database(MONGODB_CONFIG["database"])
    # chunk_task = chunk_code_and_save_to_db(code, mongo_db, "1234", "app/services/websocket_manager.py", 1)
    # chunk_ids = asyncio.run(chunk_task)
    # print(chunk_ids)

    import_task = parse_code_and_extract_chunks(
        code, mongo_db, "1234", "app/services/websocket_manager.py", 1
    )
    imports = asyncio.run(import_task)
    print(imports)