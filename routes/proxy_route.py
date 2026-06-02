from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Request,
)
from fastapi.responses import JSONResponse

from app.config import DEFAULT_LLM_MODEL
from app.middleware.cookie_verification import cookie_verification
from app.services.get_code_content import get_code_content, NoContentError
from app.dependencies import logger
from app.database import get_mongo_db
from app.services.analysis_generation_pipeline import analysis_generation_pipeline
from app.services.llm_endpoint_service import get_router_service, LLMRouterService
from app.services.websocket_manager import WebSocketManager, get_websocket_manager

router = APIRouter()

@router.post("/analysis/{factor}")
async def proxy_and_loadbalancer(
    request: Request,
    factor: str,
    background_tasks: BackgroundTasks,
    llm: str = Form(),
    model: str = Form(),
    user_id: str = Form(),
    email: str = Depends(cookie_verification),
    mongo_db = Depends(get_mongo_db),
    llm_service: LLMRouterService = Depends(get_router_service),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager),
    pasted_code: str = Form(default=None),
    codefile: UploadFile = File(default=None),
    temperature: float = Form(default=0.9),
):
    websocket = websocket_manager.active_connections.get(user_id)
    if not websocket:
        logger.warning("No active WebSocket connection for user.", extra={"user_id": user_id})
        raise HTTPException(status_code=404, detail="We're having trouble processing your request. Please try again later.")
    
    try:
        code_content, file_name = await get_code_content(codefile, pasted_code)
    except NoContentError as e:
        await websocket_manager.send_error(user_id=user_id, status_code=422, error_message=str(e))
        return HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        await websocket_manager.send_error(user_id=user_id, status_code=422, error_message="This file format is not supported. Upload a valid code file.")
        logger.warning("Error reading file content: %s", str(e), extra={"user_id": str(user_id)})
        return JSONResponse(status_code=422, content="This file format is not supported. Upload a valid code file.")
    
    background_tasks.add_task(
        analysis_generation_pipeline,
        factor,
        llm,
        DEFAULT_LLM_MODEL,
        user_id,
        code_content,
        file_name,
        temperature,
        websocket_manager,
        mongo_db,
        llm_service,
        "",
        "website",
    )

    # modify the return response message
    return JSONResponse(
        status_code=202, content="Request received. Processing in the background."
    )
