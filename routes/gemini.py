import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
import google.generativeai as genai
from fastapi import APIRouter, File, UploadFile, HTTPException, WebSocket

from app.services.gemini_service import call_gemini
from app.services.get_code_content import get_code_content
from app.config import GEMINI_COST
from app.crud.analyses import insert_analysis
from app.crud.usage import insert_usage, insert_characteristic_usage
from app.services.calculate_tokens import calculate_tokens
from app.services.prompt_service import PromptService

router = APIRouter()


def validate_model_name(model):
    if model not in ["gemini-1.0-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
        raise HTTPException(
            status_code=404,
            detail="Model not found. Please provide a valid model name.",
        )

# async def response_gemini(
#     factor: str,
#     model: str = Form(),
#     # websocket: WebSocket,
#     pasted_code: str = Form(default=None),
#     codefile: UploadFile = File(default=None),
#     temperature: float = 0.9,
# ):
async def response_gemini(db_session: AsyncSession, factor: str, model: str, websocket: WebSocket, pasted_code: str, codefile: UploadFile, temperature: float, user_id: str):
    req_start_time = datetime.now(timezone.utc)
    validate_model_name(model)

    try:
        code_content, file_name = await get_code_content(codefile, pasted_code)
    except HTTPException as e:
        raise e

    prompts = PromptService().get_prompt
    prompts_dict = await prompts(factor)

    generation_config = {"temperature": temperature, "top_p": 1, "top_k": 1}
    llm_model = genai.GenerativeModel(model_name=model, generation_config=generation_config)

    # print statement for debugging
    print("Calling the model API...")
    usage_data = []
    content = ""
    language = ""
    input_tokens = 0
    response_tokens = 0
    handler_name = "GEMINI"

    for index, (characteristic, prompt) in enumerate(prompts_dict.items()):
        char_start_time = datetime.now(timezone.utc)
        input_tokens = calculate_tokens(prompt+code_content)
        char_response = ""
        try:
            async for response in call_gemini(
                index, characteristic, prompt, code_content, llm_model
            ):
                content += response
                char_response += response
                await websocket.send_text(response)
                await asyncio.sleep(0)
        except Exception as e:
            print(str(e))
            raise HTTPException(
                status_code=503, detail=f"Something went wrong while analysing your code. Please try again."
            )

        response_tokens = calculate_tokens(char_response)
        cost = input_tokens/1000*GEMINI_COST[model]["input_tokens"] + response_tokens/1000*GEMINI_COST[model]["response_tokens"]
        created_at = datetime.now(timezone.utc) # type: ignore
        usage_data.append([characteristic, handler_name, input_tokens, response_tokens, cost, created_at])
        char_end_time = datetime.now(timezone.utc)
        print(f"Characteristic {characteristic} took {char_end_time - char_start_time} to complete.")
        extracted_language = None
        if extracted_language is not None and extracted_language != "":
            language = extracted_language

    usage_ids = await insert_usage(db_session, usage_data, user_id, model)
    await insert_characteristic_usage(db_session, usage_data, usage_ids, user_id)
    analysis_id = await insert_analysis(db_session, user_id, content, factor, file_name, language)
    await db_session.commit()
    await websocket.close()
    req_end_time = datetime.now(timezone.utc)
    print(f"Request took {req_end_time - req_start_time} to complete.")

    if analysis_id:
        return {"content": content, "analysis_id": analysis_id}
    else:
        return {"content": content, "analysis_id": None}