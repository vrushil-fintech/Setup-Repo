from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Form,
    File,
    UploadFile,
    Request,
)
from io import BytesIO
import zipfile
from fastapi.responses import JSONResponse
import json

from app.services.commit_review_pipeline_service import commit_review_pipeline_service
from app.services.websocket_manager import WebSocketManager, get_websocket_manager
from app.services.user_id_dependency import get_user_id, get_username
from app.dependencies import logger
from app.database import get_mongo_db
from app.services.check_code_file import is_code_file

router = APIRouter()


@router.post("/commit-review/{factor}")
async def commit_review_endpoint(
    request: Request,
    factor: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    repo_name: str = Form(default=None),
    commit_id: str = Form(...),
    username: str = Depends(get_username),
    files_zip: UploadFile = File(...),
    organization_name: str = Form(default=None),
    mongo_db=Depends(get_mongo_db),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager),
):
    logger.info(
        f"Received commit review request",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "repo_name": repo_name,
            "username": username,
            "factor": factor,
            "organization_name": organization_name,
        },
    )

    websocket = websocket_manager.active_connections.get(user_id)
    if not websocket:
        logger.warning("No active WebSocket connection.", extra={"user_id": user_id})
        raise HTTPException(status_code=404, detail="WebSocket not active for user.")

    try:
        contents = await files_zip.read()
        zip_bytes = BytesIO(contents)

        with zipfile.ZipFile(zip_bytes, "r") as zip_file:
            if "files.json" not in zip_file.namelist():
                raise ValueError("Zip file must contain 'files.json'")

            # Read files.json safely
            json_data = zip_file.read("files.json")
            try:
                json_str = json_data.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(status_code=422, detail="files.json is not valid UTF-8 text")

            try:
                files = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse JSON from files.json", extra={"error": str(e)})
                raise HTTPException(status_code=422, detail="Invalid JSON format in files.json")

        # ✅ Validation
        if not isinstance(files, list):
            raise ValueError(f"files.json must be a list, got {type(files).__name__}")

        for i, file in enumerate(files):
            if not isinstance(file, dict):
                raise ValueError(f"File at index {i} must be a dictionary")
            required_keys = ["filename", "status", "new_content"]
            missing = [key for key in required_keys if key not in file]
            if missing:
                raise ValueError(f"Missing keys in file[{i}]: {missing}")

        valid_files = []
        ignored_files = []

        for file in files:
            filename = file.get("filename")
            if not filename:
                continue
            if is_code_file(filename):
                valid_files.append(file)
            else:
                ignored_files.append(filename)

        logger.info(
            f"Accepted {len(valid_files)} code files. Ignored {len(ignored_files)} non-code files: {ignored_files[:5]}",
            extra={"user_id": user_id, "commit_id": commit_id, "factor": factor},
        )

        if not valid_files:
            await websocket_manager.send_error(user_id=user_id, status_code=422, error_message="No valid code files found")
            return

        files = valid_files  # continue processing only valid code files

    except ValueError as e:
        logger.error("Validation error", extra={"user_id": user_id, "error": str(e)})
        await websocket_manager.send_error(user_id=user_id, status_code=422, error_message=str(e))
        return

    except Exception as e:
        logger.exception(f"Internal error during commit review setup {str(e)}", extra={"user_id": user_id})
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=500,
            error_message="Internal server error while processing commit review.",
        )
        return

    # ✅ Add background task
    logger.info("Starting commit review task", extra={"user_id": user_id})
    background_tasks.add_task(
        commit_review_pipeline_service,
        files=files,
        repo_name=repo_name,
        commit_id=commit_id,
        username=username,
        factor=factor,
        user_id=user_id,
        websocket_manager=websocket_manager,
        mongo_db=mongo_db,
        organization_name=organization_name,
    )

    return JSONResponse(
        status_code=202,
        content="Commit review request received. Processing in the background.",
    )
