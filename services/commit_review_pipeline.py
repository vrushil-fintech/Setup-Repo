import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from app.dependencies import logger
from app.services.check_code_file import is_code_file
from app.services.rag_services.context_traversal_service import build_adjacency
from app.services.prompt_service import PromptService
from app.services.rag_services.chunking_pipeline import chunk_code_and_save_to_db
from app.services.json_to_md_service import json_to_md_issue
from app.services.check_valid_pr_line_numbers import validate_comment_line_numbers
from app.database import get_mongo_db
from app.models import CharAnalysisResponse, ResponseClass, FactorAnalysisResponse, IssueItemResponse
from app.services.pr_review_pipeline import process_file
from app.config import DEFAULT_LLM_MODEL


def _duration_seconds(start_time: datetime, end_time: datetime) -> float:
    return round((end_time - start_time).total_seconds(), 3)


async def process_commit_file(
    file,
    factor: str,
    prompt_service: PromptService,
    mongo_db,
    username: str,
    repo_name: str,
    commit_id: str,
    file_patch,
    adjacency,
    file_imports_map
):
    """
    Wrapper function for commit file processing that uses the common process_file function.
    This function maintains the same interface for commit reviews while leveraging the shared logic.
    
    Args:
        file: File object with filename, status, new_content, patch
        factor: Analysis factor (e.g., 'power_analysis', 'owasp')
        prompt_service: PromptService instance
        mongo_db: MongoDB database instance
        username: GitHub username
        repo_name: Repository name
        commit_id: Commit hash
        file_patch: List of file patches
        adjacency: Dictionary of file dependencies
        file_imports_map: Dictionary of file imports
    
    Returns:
        dict: Analysis results with file info, response, code language, and usage data
    """
    logger.info(
        f"Starting to process commit file: {file['filename']}",
        extra={
            "file_name": file["filename"],
            "status": file["status"],
            "factor": factor,
            "commit_id": commit_id
        }
    )
    
    # Use the common process_file function with commit-specific parameters
    # For commit pipeline, additional_instructions is empty and preferred_characteristics is None
    # Set temperature to 1.0 for OWASP factor as the model only supports default temperature value
    temperature = 1.0 if factor == "owasp" else 0.9
    return await process_file(
        file=file,
        factor=factor,
        model=DEFAULT_LLM_MODEL,
        temperature=temperature,
        prompt_service=prompt_service,
        mongo_db=mongo_db,
        github_login=username,
        repo_name=repo_name,
        commit_id=commit_id,  # Use commit_id instead of pr_number
        file_patch=file_patch,
        preferred_characteristics=None,  # No preferred characteristics for commit reviews
        additional_instructions="",  # No additional instructions for commit reviews
        adjacency=adjacency,
        file_imports_map=file_imports_map,
        max_depth=2,
    )

async def commit_review_pipeline(files, repo_name, commit_id, username, factor, websocket_manager=None, user_id=None):
    """
    Analyze a commit by running code review on a list of file objects.
    Args:
        files (list): List of file objects with keys: filename, status, new_content, patch (optional)
        repo_name (str): Name of the repository
        commit_id (str): Commit hash
        username (str): Username of the committer
        factor (str): Analysis factor (e.g., 'power_analysis', 'owasp')
        websocket_manager: WebSocket manager for sending real-time updates
        user_id: User ID for WebSocket communication
    Returns:
        dict: {
            'summary': str (markdown),
            'full': str (markdown),
            'line_comments': list,
            'results': list (per-file results)
        }
    """

    pipeline_start_time = datetime.now(timezone.utc)
    timing_metrics = {}

    logger.info(
        f"Starting commit review pipeline for {commit_id} in {repo_name}",
        extra={
            "user_id": user_id,
            "username": username,
            "factor": factor,
            "total_files": len(files)
        }
    )
    
    # Prepare context and chunking
    mongo_db = get_mongo_db()
    prompt_service = PromptService()

    logger.info(f"Initialized services for commit review pipeline", extra={"user_id": user_id})

    # Separate files to analyze from context files (missing deps fetched by VS Code)
    files_to_analyze = [
        file for file in files
        if is_code_file(file["filename"]) and file["status"] in ("added", "modified", "untracked")
    ]
    context_files = [
        file for file in files
        if is_code_file(file["filename"]) and file["status"] == "context"
    ]

    logger.info(
        f"Found {len(files_to_analyze)} files to analyze, {len(context_files)} context (dependency) files",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "total_files": len(files),
            "files_to_analyze": len(files_to_analyze),
            "context_files": len(context_files),
            "context_file_names": [f["filename"] for f in context_files],
        }
    )

    # Chunk ALL files (both analyzed + context) into DB.
    # Context file chunks are used by traverse_dependencies_and_retrieve_chunks
    # when building code context for files that import the context files.
    all_files_for_chunking = files_to_analyze + context_files
    chunking_start_time = datetime.now(timezone.utc)
    for file in all_files_for_chunking:
        await chunk_code_and_save_to_db(
            file["new_content"],
            mongo_db,
            username,
            file["filename"],
            repo_name,
            pr_number=None,
            commit_id=commit_id,
        )
    chunking_end_time = datetime.now(timezone.utc)

    timing_metrics["chunking_seconds"] = _duration_seconds(
        chunking_start_time, chunking_end_time
    )

    # Build adjacency graph over ALL files (analyzed + context) so that when
    # traverse_dependencies_and_retrieve_chunks walks a file's imports, it can
    # reach context file nodes and pull their chunks as LLM context.
    adjacency_start_time = datetime.now(timezone.utc)
    adjacency, file_imports_map = await build_adjacency(all_files_for_chunking)
    adjacency_end_time = datetime.now(timezone.utc)
    timing_metrics["adjacency_build_seconds"] = _duration_seconds(
        adjacency_start_time, adjacency_end_time
    )

    # Rename for clarity: only analyzed files go through process_commit_file
    relevant_files = files_to_analyze

    logger.info(
        f"Starting file processing phase for {len(relevant_files)} files",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "file_count": len(relevant_files),
        }
    )

    # Process each file
    files_processing_start_time = datetime.now(timezone.utc)
    results = await asyncio.gather(*[
        process_commit_file(
            file=file,
            factor=factor,
            prompt_service=prompt_service,
            mongo_db=mongo_db,
            username=username,
            repo_name=repo_name,
            commit_id=commit_id,
            file_patch=files,
            adjacency=adjacency,
            file_imports_map=file_imports_map
        )
        for file in relevant_files
    ])
    files_processing_end_time = datetime.now(timezone.utc)
    timing_metrics["file_processing_seconds"] = _duration_seconds(
        files_processing_start_time, files_processing_end_time
    )
    
    # Aggregate results
    summary = ""
    full = ""
    line_comments = []
    
    logger.info(
        f"File processing completed for all files",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "results_count": len(results)
        }
    )

    for i, result in enumerate(results):
        if not result:
            logger.warning(
                f"No result for file {i+1}",
                extra={
                    "user_id": user_id,
                    "commit_id": commit_id,
                    "file_index": i+1
                }
            )
            continue
            
        response = result.get("response", [])
        file = result.get("file", {})
        code_language = result.get("code_language", "")
        
        if response:
            summary += f"## File Name: {file['filename']}\n\n"
            full += f"## File Name: {file['filename']}\n\n"
            if type(response) == str:
                summary += f"{response}\n\n"
                full += f"{response}\n\n"
                continue
            
            # Log initial response structure for debugging
            print(f"[OWASP_PROCESSING] ========== Starting OWASP processing for file: {file['filename']} ==========")
            print(f"[OWASP_PROCESSING] Factor: {factor}")
            print(f"[OWASP_PROCESSING] Response type: {type(response).__name__}")
            print(f"[OWASP_PROCESSING] Response length: {len(response) if isinstance(response, list) else 'N/A'}")
            print(f"[OWASP_PROCESSING] Has patch: {bool(file.get('patch'))}")
            print(f"[OWASP_PROCESSING] Patch length: {len(file.get('patch', '')) if file.get('patch') else 0}")
            
            logger.info(
                f"Processing response for file: {file['filename']}",
                extra={
                    "user_id": user_id,
                    "commit_id": commit_id,
                    "file_name": file["filename"],
                    "response_type": type(response).__name__,
                    "response_length": len(response) if isinstance(response, list) else "N/A",
                    "has_patch": bool(file.get("patch")),
                    "patch_length": len(file.get("patch", "")) if file.get("patch") else 0,
                }
            )
            
            file_characteristic_data = defaultdict(dict)
            valid_response = []
            file_line_comments = {
                "filename": file["filename"],
                "line_comments": [],
            }
            
            # Track filtering statistics
            total_characteristics = 0
            total_issue_items = 0
            filtered_no_markdown = 0
            filtered_no_start_line = 0
            filtered_invalid_line_numbers = 0
            
            for char_el in response:
                if not char_el:
                    continue
                total_characteristics += 1
                issue_items = char_el.get("issue_items", [])
                total_issue_items += len(issue_items)
                print(f"[OWASP_PROCESSING] Processing characteristic: {char_el.get('characteristic', 'Unknown')}")
                print(f"[OWASP_PROCESSING] Found {len(issue_items)} issue items in this characteristic")
                valid_issue_items = []
                
                logger.debug(
                    f"Processing characteristic: {char_el.get('characteristic', 'Unknown')}",
                    extra={
                        "user_id": user_id,
                        "commit_id": commit_id,
                        "file_name": file["filename"],
                        "characteristic": char_el.get("characteristic", "Unknown"),
                        "issue_items_count": len(issue_items),
                    }
                )
                
                for issue_item in issue_items:
                    issue_markdown = json_to_md_issue(
                        issue_item,
                        code_language,
                        char_el.get("characteristic"),
                    )
                    if not issue_markdown:
                        filtered_no_markdown += 1
                        continue
                    line_comment = {
                        "start_line": issue_item.get("start_line"),
                        "end_line": issue_item.get("end_line"),
                        "comment": issue_markdown,
                        "valid": True,
                    }
                    if line_comment.get("start_line"):
                        print(f"[OWASP_LINE_VERIFICATION] Processing issue item for factor={factor}")
                        print(f"[OWASP_LINE_VERIFICATION] File: {file['filename']}")
                        print(f"[OWASP_LINE_VERIFICATION] Issue - start_line: {issue_item.get('start_line')}, end_line: {issue_item.get('end_line')}")
                        print(f"[OWASP_LINE_VERIFICATION] Characteristic: {char_el.get('characteristic')}")
                        print(f"[OWASP_LINE_VERIFICATION] Severity: {issue_item.get('severity')}")
                        print(f"[OWASP_LINE_VERIFICATION] Has patch: {bool(file.get('patch'))}")
                        print(f"[OWASP_LINE_VERIFICATION] Patch preview: {file.get('patch', '')[:200] if file.get('patch') else 'None'}...")
                        
                        file_line_comments["line_comments"].append(line_comment)
                        print(f"[OWASP_LINE_VERIFICATION] Calling validate_comment_line_numbers...")
                        validate_comment_line_numbers(
                            file.get("patch"),
                            file["filename"],
                            line_comment,
                        )
                        print(f"[OWASP_LINE_VERIFICATION] Validation result - valid: {line_comment.get('valid')}, start_line: {line_comment.get('start_line')}, end_line: {line_comment.get('end_line')}")
                        
                        if line_comment["valid"]:
                            print(f"[OWASP_LINE_VERIFICATION] ✓ Issue item is VALID - adding to valid_issue_items")
                            valid_issue_items.append(issue_item)
                            file_characteristic_data[
                                char_el["characteristic"]
                            ][issue_item["severity"]] = (
                                file_characteristic_data[
                                    char_el["characteristic"]
                                ].get(issue_item["severity"], 0)
                                + 1
                            )
                        else:
                            print(f"[OWASP_LINE_VERIFICATION] ✗ Issue item is INVALID - incrementing filtered_invalid_line_numbers")
                            filtered_invalid_line_numbers += 1
                    else:
                        filtered_no_start_line += 1
                if valid_issue_items:
                    print(f"[OWASP_PROCESSING] ✓ Adding characteristic '{char_el.get('characteristic')}' with {len(valid_issue_items)} valid issue items to valid_response")
                    valid_char_el = {
                        **char_el,
                        "issue_items": valid_issue_items,
                    }
                    valid_response.append(valid_char_el)
                else:
                    print(f"[OWASP_PROCESSING] ✗ Skipping characteristic '{char_el.get('characteristic')}' - no valid issue items")
            
            print(f"[OWASP_SUMMARY] File: {file['filename']}")
            print(f"[OWASP_SUMMARY] Factor: {factor}")
            print(f"[OWASP_SUMMARY] Total characteristics: {total_characteristics}")
            print(f"[OWASP_SUMMARY] Total issue items: {total_issue_items}")
            print(f"[OWASP_SUMMARY] Valid response count: {len(valid_response)}")
            print(f"[OWASP_SUMMARY] Valid issue items count: {sum(len(char.get('issue_items', [])) for char in valid_response)}")
            print(f"[OWASP_SUMMARY] Filtered - no markdown: {filtered_no_markdown}")
            print(f"[OWASP_SUMMARY] Filtered - no start_line: {filtered_no_start_line}")
            print(f"[OWASP_SUMMARY] Filtered - invalid line numbers: {filtered_invalid_line_numbers}")
            print(f"[OWASP_SUMMARY] Has patch: {bool(file.get('patch'))}")
            
            logger.info(
                f"Processed valid response for file: {file['filename']}",
                extra={
                    "user_id": user_id,
                    "commit_id": commit_id,
                    "file_name": file["filename"],
                    "total_characteristics": total_characteristics,
                    "total_issue_items": total_issue_items,
                    "valid_response_count": len(valid_response),
                    "issue_items_count": sum(len(char.get("issue_items", [])) for char in valid_response),
                    "filtered_no_markdown": filtered_no_markdown,
                    "filtered_no_start_line": filtered_no_start_line,
                    "filtered_invalid_line_numbers": filtered_invalid_line_numbers,
                    "has_patch": bool(file.get("patch")),
                }
            )
            
            # Send file response via WebSocket instead of adding to full
            if websocket_manager and user_id and valid_response:
                logger.info(
                    f"Sending WebSocket response for file: {file['filename']}",
                    extra={
                        "user_id": user_id,
                        "commit_id": commit_id,
                        "file_name": file["filename"],
                        "valid_response_count": len(valid_response)
                    }
                )
                # Convert to proper Pydantic models to ensure validation
                char_analysis_list = []
                for char_data in valid_response:
                    # Convert issue_items to IssueItemResponse objects
                    issue_items = []
                    for issue in char_data.get("issue_items", []):
                        issue_items.append(IssueItemResponse(**issue))
                    
                    # Create CharAnalysisResponse object
                    char_analysis = CharAnalysisResponse(
                        characteristic=char_data.get("characteristic"),
                        description_of_characteristic=char_data.get("description_of_characteristic"),
                        issue_items=issue_items
                    )
                    char_analysis_list.append(char_analysis)
                
                ws_response = ResponseClass(
                    status_code=200,
                    content=FactorAnalysisResponse(
                        factor=factor,
                        file_name=file["filename"],
                        analysis=char_analysis_list,
                        language=code_language,
                        analysis_type="commit_review",
                        user_id=user_id,
                    ),
                )
                sent = await websocket_manager.send_json(user_id, ws_response)
                if sent:
                    logger.info(
                        f"WebSocket response sent successfully for file: {file['filename']}",
                        extra={
                            "user_id": user_id,
                            "commit_id": commit_id,
                            "file_name": file["filename"],
                        },
                    )
                else:
                    logger.warning(
                        f"WebSocket connection lost while sending result for file: {file['filename']}. "
                        f"Stopping pipeline — remaining files will not be processed.",
                        extra={
                            "user_id": user_id,
                            "commit_id": commit_id,
                            "file_name": file["filename"],
                        },
                    )
                    break

    timing_metrics["total_pipeline_seconds"] = _duration_seconds(
        pipeline_start_time, datetime.now(timezone.utc)
    )
    logger.info(
        "Commit review pipeline timing metrics",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "repo_name": repo_name,
            "files_to_analyze_count": len(relevant_files),
            "context_files_count": len(context_files),
            "total_chunked_files_count": len(all_files_for_chunking),
            **timing_metrics,
        },
    )

    logger.info(
        f"Commit review pipeline completed successfully",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "repo_name": repo_name,
            "total_files_processed": len(results),
            "files_with_results": len([r for r in results if r])
        }
    )

    return {
        "summary": summary,
        "full": full,
        "line_comments": line_comments,
        "results": results,
    } 


async def main():
    dummy_files = [
    {
        "filename": "app/processor.py",
        "status": "added",
        "new_content": """\
import json
from datetime import datetime

class DataProcessor:
    def __init__(self, source):
        self.source = source
        self.data = []

    def load_data(self):
        try:
            with open(self.source, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            print(f"File {self.source} not found.")
        except json.JSONDecodeError:
            print("Error decoding JSON.")

    def process_data(self):
        processed = []
        for item in self.data:
            try:
                processed_item = {
                    'id': item.get('id', 'N/A'),
                    'timestamp': datetime.now().isoformat(),
                    'value': float(item['value']) * 1.1
                }
                processed.append(processed_item)
            except (KeyError, ValueError) as e:
                print(f"Error processing item: {e}")
        return processed

    def save_data(self, destination):
        try:
            with open(destination, 'w') as f:
                json.dump(self.process_data(), f, indent=4)
        except IOError as e:
            print(f"Error saving file: {e}")
""",
        "patch": "@@ -0,0 +1,38 @@\n+" + "\n+".join([
            "import json",
            "from datetime import datetime",
            "",
            "class DataProcessor:",
            "    def __init__(self, source):",
            "        self.source = source",
            "        self.data = []",
            "",
            "    def load_data(self):",
            "        try:",
            "            with open(self.source, 'r') as f:",
            "                self.data = json.load(f)",
            "        except FileNotFoundError:",
            "            print(f\"File {self.source} not found.\")",
            "        except json.JSONDecodeError:",
            "            print(\"Error decoding JSON.\")",
            "",
            "    def process_data(self):",
            "        processed = []",
            "        for item in self.data:",
            "            try:",
            "                processed_item = {",
            "                    'id': item.get('id', 'N/A'),",
            "                    'timestamp': datetime.now().isoformat(),",
            "                    'value': float(item['value']) * 1.1",
            "                }",
            "                processed.append(processed_item)",
            "            except (KeyError, ValueError) as e:",
            "                print(f\"Error processing item: {e}\")",
            "        return processed",
            "",
            "    def save_data(self, destination):",
            "        try:",
            "            with open(destination, 'w') as f:",
            "                json.dump(self.process_data(), f, indent=4)",
            "        except IOError as e:",
            "            print(f\"Error saving file: {e}\")"
        ])
    },
    {
        "filename": "app/main.py",
        "status": "modified",
        "new_content": """\
import sys
from app.processor import DataProcessor

def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <input.json> <output.json>")
        return

    processor = DataProcessor(sys.argv[1])
    processor.load_data()
    processor.save_data(sys.argv[2])

if __name__ == "__main__":
    main()
""",
        "patch": """\
@@ -1,6 +1,8 @@
-import os
-import sys
-import json
-from datetime import datetime
+import sys
+from app.processor import DataProcessor

-class DataProcessor:
-    ...
+def main():
+    if len(sys.argv) < 3:
+        print("Usage: python main.py <input.json> <output.json>")
+        return
+
+    processor = DataProcessor(sys.argv[1])
+    processor.load_data()
+    processor.save_data(sys.argv[2])
+
+if __name__ == "__main__":
+    main()
"""
    }
]

    result = await commit_review_pipeline(
        files=dummy_files,
        repo_name="dummy-repo",
        commit_id="abc1234",
        username="test_user",
        factor="power_analysis"
    )

    with open("commit_review_output.md", "w", encoding="utf-8") as f:
        f.write("# Summary\n\n")
        f.write(result["summary"])
        f.write("\n\n# Full Review\n\n")
        f.write(result["full"])

# Run
if __name__ == "__main__":
    asyncio.run(main())