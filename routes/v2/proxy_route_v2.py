from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import JSONResponse

from app.config import DEFAULT_LLM_MODEL
from app.services.analysis_generation_pipeline import analysis_generation_pipeline
from app.services.llm_endpoint_service import LLMRouterService, get_router_service
from app.services.get_code_content import NoContentError, get_code_content
from app.services.websocket_manager import WebSocketManager, get_websocket_manager
from app.dependencies import logger
from app.database import get_mongo_db

router = APIRouter()


@router.post("/analysis/{factor}")
async def proxy_and_loadbalancer(
    factor: str,
    background_tasks: BackgroundTasks,
    llm: str = Form(),
    model: str = Form(),
    user_id: str = Form(),
    organization_name: str = Form(default=None),
    repo_name: str = Form(default=None),
    mongo_db=Depends(get_mongo_db),
    llm_service: LLMRouterService = Depends(get_router_service),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager),
    pasted_code: str = Form(default=None),
    codefile: UploadFile = File(default=None),
    temperature: float = Form(default=0.9),
):
    websocket = websocket_manager.active_connections.get(user_id)
    if not websocket:
        logger.warning(
            "No active WebSocket connection for user.", extra={"user_id": user_id}
        )
        raise HTTPException(
            status_code=404,
            detail="We're having trouble processing your request. Please try again later.",
        )

    try:
        code_content, file_name = await get_code_content(codefile, pasted_code)
    except NoContentError as e:
        await websocket_manager.send_error(
            user_id=user_id, status_code=422, error_message=str(e)
        )
        return HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="This file format is not supported. Upload a valid code file.",
        )
        logger.warning(
            "Error reading file content: %s", str(e), extra={"user_id": str(user_id)}
        )
        return JSONResponse(
            status_code=422,
            content="This file format is not supported. Upload a valid code file.",
        )

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
        "ide",
        organization_name,
        repo_name,
    )

    # modify the return response message
    return JSONResponse(
        status_code=202, content="Request received. Processing in the background."
    )


@router.post("/context_analysis")
async def proxy_and_loadbalancer(
    background_tasks: BackgroundTasks,
    llm: str = Form(),
    model: str = Form(),
    user_id: str = Form(),
    organization_name: str = Form(default=None),
    repo_name: str = Form(default=None),
    mongo_db=Depends(get_mongo_db),
    llm_service: LLMRouterService = Depends(get_router_service),
    websocket_manager: WebSocketManager = Depends(get_websocket_manager),
    analysis_code: str = Form(),
    analysis_code_name: str = Form(),
    context_code: UploadFile = File(default=None),
    temperature: float = Form(default=0.9),
):
    websocket = websocket_manager.active_connections.get(user_id)
    if not websocket:
        logger.warning(
            "No active WebSocket connection for user.", extra={"user_id": user_id}
        )
        raise HTTPException(
            status_code=404,
            detail="We're having trouble processing your request. Please try again later.",
        )

    try:
        context_code_content, file_name = await get_code_content(codefile=context_code)
        analysis_code_content, red_file_name = await get_code_content(
            pasted_code=analysis_code
        )
        file_name += " - " + analysis_code_name
    except NoContentError as e:
        await websocket_manager.send_error(
            user_id=user_id, status_code=422, error_message=str(e)
        )
        return HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="This file format is not supported. Upload a valid code file.",
        )
        logger.warning(
            "Error reading file content: %s", str(e), extra={"user_id": str(user_id)}
        )
        return JSONResponse(
            status_code=422,
            content="This file format is not supported. Upload a valid code file.",
        )

    background_tasks.add_task(
        analysis_generation_pipeline,
        "power_analysis",
        llm,
        DEFAULT_LLM_MODEL,
        user_id,
        analysis_code_content,
        file_name,
        temperature,
        websocket_manager,
        mongo_db,
        llm_service,
        context_code_content,
        "ide",
        organization_name,
        repo_name,
    )

    # modify the return response message
    return JSONResponse(
        status_code=202, content="Request received. Processing in the background."
    )
