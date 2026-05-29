from collections import deque
import os
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import EXTENSION_TO_LANGUAGE, logger
from app.services.rag_services.chunking_pipeline import LANGUAGE_HANDLER_CLASSES


def _strip_ext(path: str) -> str:
    return os.path.splitext(path)[0]


def _find_best_suffix_match(
    normalized_noext: str, all_filenames: List[str]
) -> Optional[str]:
    best = None
    best_score = -1
    for fname in all_filenames:
        base_noext = _strip_ext(fname)
        if base_noext.endswith(normalized_noext):
            score = len(normalized_noext)
            if score > best_score:
                best_score = score
                best = fname
    return best


def resolve_imported_path(all_filenames, imported_from, code_language):
    code_language = (code_language or "").lower()
    if imported_from in all_filenames:
        return imported_from
    return _find_best_suffix_match(imported_from, all_filenames)


async def build_adjacency(relevant_files: List[Dict[str, Any]]):
    all_filenames = [f.get("filename") for f in relevant_files if "filename" in f]
    adjacency: Dict[str, List[Optional[str]]] = {}
    file_imports_map: Dict[str, List[Dict[str, Any]]] = {}

    logger.info(
        f"Building adjacency for {len(relevant_files)} files.",
    )

    try:
        for f in relevant_files:
            filename = f.get("filename")
            if not filename:
                logger.warning(
                    "Skipping file without 'filename' key.", extra={"file": f}
                )
                continue

            extension = "." + filename.split(".")[-1]
            code_language = EXTENSION_TO_LANGUAGE.get(extension, "none")

            handler_class = (
                LANGUAGE_HANDLER_CLASSES.get(code_language.lower())
                if code_language != "none"
                else None
            )

            if not handler_class:
                logger.warning(
                    f"No handler found for file {filename}.",
                    extra={"file_name": filename, "language": code_language},
                )
                file_imports_map[filename] = []
                adjacency[filename] = []
                continue

            imports: List[Dict[str, Any]] = []
            try:
                handler = handler_class()
                imports = await handler.parse_imports(
                    code=f.get("new_content", ""), file_path=filename
                )
                logger.info(f"Parsed {len(imports)} imports for {filename}.")
            except Exception as e:
                logger.error(
                    f"Error parsing imports for {filename}: {str(e)}",
                    extra={"file_name": filename, "language": code_language},
                )

            file_imports_map[filename] = imports or []

            imported_paths: List[Optional[str]] = []
            for imp in imports or []:
                imported_from = imp.get("imported_from")
                if imported_from:
                    resolved = resolve_imported_path(
                        all_filenames, imported_from, code_language
                    )
                    if resolved:
                        imported_paths.append(resolved)

            adjacency[filename] = list(dict.fromkeys(imported_paths))

        logger.info(
            "Finished building adjacency map.",
            extra={
                "relevant_files": len(relevant_files),
                "adjacency": len(adjacency),
                "file_imports_map": len(file_imports_map),
            },
        )

    except Exception as e:
        logger.error(
            f"Error building adjacency map: {str(e)}",
            extra={
                "relevant_files": len(relevant_files),
                "adjacency": len(adjacency),
                "file_imports_map": len(file_imports_map),
            },
        )

    return adjacency, file_imports_map


async def traverse_dependencies_and_retrieve_chunks(
    mongo_db: AsyncIOMotorDatabase,
    file: Dict[str, Any],
    adjacency: Dict[str, List[str]],
    file_imports_map: Dict[str, List[Dict[str, Any]]],
    max_depth: int,
    pr_number: int = None,
    commit_id: str = None,
    user_id: str = None,
    repo_name: str = None,
):
    filename = file.get("filename")
    if not filename:
        logger.error(
            "No filename provided in file object, cannot traverse dependencies."
        )
        return []

    if not file_imports_map:
        logger.error(
            "No file_imports_map provided, cannot traverse dependencies."
        )
        return []

    logger.info(
        f"Traversing dependencies for {filename} (max_depth={max_depth}).",
        extra={
            "pr_number": pr_number,
            "commit_id": commit_id,
            "user_id": user_id,
            "repo_name": repo_name,
        },
    )

    visited = set([filename])
    q = deque([(filename, 0)])

    while q:
        node, depth = q.popleft()
        if depth >= max_depth:
            continue
        for dep in adjacency.get(node, []):
            if dep and dep not in visited:
                visited.add(dep)
                q.append((dep, depth + 1))

    extension = "." + filename.split(".")[-1]
    code_language = EXTENSION_TO_LANGUAGE.get(extension, "none")

    handler_class = (
        LANGUAGE_HANDLER_CLASSES.get(code_language.lower())
        if code_language != "none"
        else None
    )

    if not handler_class:
        logger.warning(
            f"No handler found for {filename}. Returning empty chunks.",
            extra={"file_name": filename, "language": code_language},
        )
        return []

    handler = handler_class()
    chunks_list: List[Any] = []
    seen_chunks = set()

    for dep in visited:
        imports_objs = file_imports_map.get(dep, [])
        unique_imports_objs = []
        for imp in imports_objs:
            key = (imp.get("chunk_name"), imp.get("imported_from"))
            if key not in seen_chunks:
                unique_imports_objs.append(imp)
                seen_chunks.add(key)

        try:
            chunks = await handler.retrieve_relevant_chunks(
                mongo_db=mongo_db,
                imports=unique_imports_objs,
                pr_number=pr_number,
                commit_id=commit_id,
                file_path=filename,
                user_id=user_id,
                repo_name=repo_name,
            )
            chunks_list += chunks
        except Exception as e:
            logger.error(
                f"Error retrieving chunks for {dep}: {str(e)}",
                extra={"file_name": filename, "dep": dep, "language": code_language},
            )

    logger.info(
        f"Traversal complete for {filename}. Total context chunks: {len(chunks_list)}.",
        extra={
            "pr_number": pr_number,
            "commit_id": commit_id,
            "user_id": user_id,
            "repo_name": repo_name,
            "chunk_count": len(chunks_list),
        },
    )

    return chunks_list
