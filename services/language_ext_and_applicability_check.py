import json
from typing import List, Dict
from app.config import DEFAULT_LLM_MODEL
from app.dependencies import logger
from app.models import LLMUsage
from app.services.llm_endpoint_service import LLMRouterService


async def applicability_check(
    prompt: str, file_name: str, usage_data: LLMUsage, llm_service: LLMRouterService
) -> List[str]:
    output = ""

    async for chunk in llm_service.agenerate_streaming_response(
        prompt=prompt,
        model=DEFAULT_LLM_MODEL,
        usage_data=usage_data,
    ):
        output += chunk

    # TODO: Remove this log in prod
    logger.info(
        "Applicability check output: %s", output, extra={"file_name": file_name}
    )

    # Parse the output JSON
    if output: 
        try:
            json_obj = json.loads(output)
            return {
                "filtered_chars": (
                    [
                        obj["name"]
                        for obj in json_obj["characteristics"]
                        if obj["applicable"] and obj["require_changes"]
                    ]
                    if json_obj.get("characteristics")
                    else []
                ),
                "language": json_obj["language"],
            }
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse applicability check output, error: %s",
                str(e),
            )
            return {}

    return {}

async def impact_based_characteristic_pick(
    prompt: str, usage_data: LLMUsage, llm_service: LLMRouterService
) -> dict:
    """
    Runs a small LLM call that returns a JSON object with a new characteristic based on PR Impact,
    or 'NONE' if no new characteristic is needed.
    Returns a dict with the characteristic object or None.
    """
    output = ""

    async for chunk in llm_service.agenerate_streaming_response(
        prompt=prompt,
        model=DEFAULT_LLM_MODEL,
        usage_data=usage_data,
    ):
        output += chunk

    # Log raw output for observability
    logger.info("Impact-based characteristic pick: %s", output)

    output = (output or "").strip()
    
    # Check if it's "NONE"
    if output.upper() == "NONE" or output.upper().strip('"\'') == "NONE":
        return None
    
    # Try to parse as JSON
    try:
        char_obj = json.loads(output)
        # Validate required fields
        # Do not require 'example' for impact-based pick; we'll inject a dummy example later.
        required_fields = ["characteristic", "description", "abbreviation", "weight"]
        if all(field in char_obj for field in required_fields):
            return char_obj
        else:
            logger.warning("Impact-based characteristic missing required fields: %s", char_obj)
            return None
    except json.JSONDecodeError:
        logger.warning("Failed to parse impact-based characteristic as JSON: %s", output)
        return None

async def instruction_applicability_check(
    prompt: str, file_name: str, usage_data: LLMUsage, llm_service: LLMRouterService
) -> dict:
    """
    Runs an applicability check for additional user instructions.

    :param prompt: The formatted prompt to send to the LLM.
    :param file_name: The name of the file being analyzed (for logging).
    :param usage_data: Tracks usage for analytics/billing.
    :param llm_service: Service for communicating with the LLM.
    :return: Dictionary with applicable instructions and detected language, or None on error.
    """
    output = ""

    async for chunk in llm_service.agenerate_streaming_response(
        prompt=prompt,
        model=DEFAULT_LLM_MODEL,
        usage_data=usage_data,
    ):
        output += chunk

    if output:
        # TODO: Remove this log in prod
        logger.info(
            "Instruction applicability check output: %s",
            output,
            extra={"file_name": file_name},
        )
        try:
            json_obj = json.loads(output)
            return {
                "filtered_instructions": (
                    [
                        obj["instruction"]
                        for obj in json_obj["instructions"]
                        if obj["applicable"] and obj["require_changes"]
                    ]
                    if json_obj.get("instructions")
                    else []
                ),
                "language": json_obj.get("language"),
            }
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse instruction applicability check output: %s, error: %s",
                output,
                str(e),
            )
            return {}

    return {}


async def cwe_applicability_check(
    prompt: str, file_name: str, usage_data: LLMUsage, llm_service: LLMRouterService
) -> List[str]:
    output = ""
    # print("Cwe")

    async for chunk in llm_service.agenerate_streaming_response(
        prompt=prompt,
        model=DEFAULT_LLM_MODEL,
        usage_data=usage_data,
    ):
        output += chunk

    # TODO: Remove this log in prod
    logger.info(
        "Applicability check output: %s", output, extra={"file_name": file_name}
    )

    # Parse the output JSON
    if output: 
        try:
            json_obj = json.loads(output)
            return {
                "filtered_chars": (
                    [
                        obj["name"]
                        for obj in json_obj["characteristics"]
                        if obj["applicable"] and obj["require_changes"]
                    ]
                    if json_obj.get("characteristics")
                    else []
                ),
                "language": json_obj["language"],
            }
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse applicability check output, error: %s",
                str(e),
            )
            return {}

    return {}


def _clean_markdown_json(content: str) -> str:
    """
    Remove markdown code blocks from LLM response.
    
    LLM might return content wrapped in markdown code blocks:
        ```json
        {"status": 0, "missing_files": [...]}
        ```
    
    This helper extracts just the JSON content.
    
    Args:
        content: Raw LLM response text
        
    Returns:
        str: Cleaned JSON string without markdown formatting
        
    Example:
        >>> _clean_markdown_json('```json\\n{"status": 0}\\n```')
        '{"status": 0}'
    """
    content = content.strip()
    
    # Remove opening markdown code block
    if content.startswith("```json"):
        content = content[7:]  # Remove ```json
    elif content.startswith("```"):
        content = content[3:]  # Remove ```
    
    # Remove closing markdown code block
    if content.endswith("```"):
        content = content[:-3]  # Remove trailing ```
    
    return content.strip()


async def identify_missing_dependencies_llm_call(
    prompt: str,
    file_path: str,
    llm_service: LLMRouterService,
    model: str = DEFAULT_LLM_MODEL
) -> Dict[str, any]:
    """
    Calls LLM to identify missing file dependencies for a single PR file.
    
    This function:
    1. Calls the load-balanced LLM with the provided prompt
    2. Parses the JSON response: {"status": 0|1, "missing_files": [...]}
    3. Returns graceful fallback on any errors (assumes all files present)
    
    The function uses non-streaming LLM calls for direct JSON responses,
    matching the pattern used in loadbalancer_latency_test.py.
    
    Args:
        prompt: Formatted prompt from _identify_missing_dependencies_prompt()
                in PromptService. Should include file imports, repo structure,
                and PR file paths.
        file_path: Path to the file being analyzed (e.g., "app/services/auth.py")
                   Used for logging and debugging purposes.
        llm_service: LLMRouterService instance for load-balanced LLM calls
                     across multiple deployments.
        model: LLM model to use. Defaults to DEFAULT_LLM_MODEL from config
               (currently "gpt-5-mini").
        
    Returns:
        dict: Response format based on LLM analysis:
            Success with missing files:
                {
                    "status": 0,
                    "missing_files": ["app/utils/helper.py", "app/models/user.py"]
                }
            
            Success with no missing files (all present):
                {
                    "status": 1,
                    "missing_files": []
                }
            
            Error/Failure (graceful fallback):
                {
                    "status": 1,
                    "missing_files": []
                }
    
    Raises:
        Does NOT raise exceptions. Returns safe fallback instead:
        {"status": 1, "missing_files": []} on any error.
    
    Example Usage:
        >>> # Step 1: Generate prompt
        >>> prompt = await prompt_service._identify_missing_dependencies_prompt(
        ...     file_path="app/services/auth.py",
        ...     extracted_imports={
        ...         "file_path": "app/services/auth.py",
        ...         "language": "python",
        ...         "import_lines": ["from app.utils import helper", "import os"]
        ...     },
        ...     repo_structure=["app/utils/helper.py", "app/models/user.py"],
        ...     pr_file_paths=["app/services/auth.py"]
        ... )
        >>> 
        >>> # Step 2: Call LLM
        >>> result = await identify_missing_dependencies_llm_call(
        ...     prompt=prompt,
        ...     file_path="app/services/auth.py",
        ...     llm_service=llm_service
        ... )
        >>> 
        >>> # Step 3: Use result
        >>> print(result)
        {"status": 0, "missing_files": ["app/utils/helper.py"]}
    
    Notes:
        - Uses router.acompletion() for direct, non-streaming responses
        - Automatically cleans markdown code blocks from LLM responses
        - Logs success at INFO level for debugging
        - Logs failures at ERROR level with full stack trace
        - Token usage tracking can be added later if needed
    """
    raw_content = ""
    
    try:
        # Call LLM using load-balanced router (non-streaming)
        response = await llm_service.router.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract response content
        raw_content = response.choices[0].message.content
        
        # Clean markdown formatting (LLM might wrap JSON in ```json...```)
        cleaned_content = _clean_markdown_json(raw_content)
        
        # Parse JSON response
        result = json.loads(cleaned_content)
        
        # Validate response structure
        if not isinstance(result, dict):
            raise ValueError(f"Expected dict, got {type(result).__name__}")
        
        if "status" not in result or "missing_files" not in result:
            raise ValueError(
                f"Missing required fields. Got keys: {list(result.keys())}"
            )
        
        # Validate status value
        if result["status"] not in [0, 1]:
            raise ValueError(f"Invalid status value: {result['status']}")
        
        # Validate missing_files is a list
        if not isinstance(result["missing_files"], list):
            raise ValueError(
                f"missing_files must be a list, got {type(result['missing_files']).__name__}"
            )
        
        # Log success at INFO level (helpful for debugging)
        logger.info(
            f"Missing dependencies identified for {file_path}",
            extra={
                "file_path": file_path,
                "status": result["status"],
                "missing_count": len(result["missing_files"]),
                "missing_files": result["missing_files"]
            }
        )
        
        return result
        
    except json.JSONDecodeError as e:
        # JSON parsing failed
        logger.error(
            f"Failed to parse LLM JSON response for {file_path}: {str(e)}",
            extra={
                "file_path": file_path,
                "error_type": "JSONDecodeError",
                "llm_response_preview": raw_content[:300] if raw_content else None,
                "error_details": str(e)
            },
            exc_info=True
        )
        return {"status": 1, "missing_files": []}
        
    except (ValueError, KeyError, AttributeError) as e:
        # Response validation failed
        logger.error(
            f"Invalid LLM response structure for {file_path}: {str(e)}",
            extra={
                "file_path": file_path,
                "error_type": type(e).__name__,
                "llm_response_preview": raw_content[:300] if raw_content else None,
                "error_details": str(e)
            },
            exc_info=True
        )
        return {"status": 1, "missing_files": []}
        
    except Exception as e:
        # Unexpected error (network, LLM service, etc.)
        logger.error(
            f"Unexpected error identifying missing deps for {file_path}: {str(e)}",
            extra={
                "file_path": file_path,
                "error_type": type(e).__name__,
                "error_details": str(e)
            },
            exc_info=True
        )
        return {"status": 1, "missing_files": []}