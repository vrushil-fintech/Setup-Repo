"""
Unified Import Line Extraction Service

This service provides a unified interface for extracting raw import lines
from multiple programming languages. It routes requests to language-specific
extractors and processes multiple files in parallel.
"""

import asyncio
from typing import List, Dict, Any
from app.dependencies import logger
from .models import FileImportLines, PRImportLinesSummary, ImportLineExtractionError
from . import python_import_line_extractor
from . import js_ts_import_line_extractor
from . import java_import_line_extractor
from . import csharp_import_line_extractor


# Supported languages
SUPPORTED_LANGUAGES = {
    "python": python_import_line_extractor,
    "javascript": js_ts_import_line_extractor,
    "typescript": js_ts_import_line_extractor,
    "java": java_import_line_extractor,
    "csharp": csharp_import_line_extractor,
    "c#": csharp_import_line_extractor,  # Alias
}


async def extract_import_lines_from_file(
    code: str,
    file_path: str,
    language: str
) -> FileImportLines:
    """
    Extract raw import lines from a single file.
    
    This is the main entry point for single file extraction. It routes to the
    appropriate language-specific extractor and returns raw import lines.
    
    Args:
        code: Source code as string
        file_path: Path to the file (for metadata)
        language: Programming language (python, javascript, typescript, java, csharp)
        
    Returns:
        FileImportLines object containing raw import lines
        
    Raises:
        ImportLineExtractionError: If language is unsupported or extraction fails
        
    Example:
        >>> code = '''
        ... import os
        ... from app.utils import helper
        ... '''
        >>> result = await extract_import_lines_from_file(code, "main.py", "python")
        >>> print(result.import_lines)
        ['import os', 'from app.utils import helper']
    """
    # Normalize language name
    language = language.lower()
    
    # Check if language is supported
    if language not in SUPPORTED_LANGUAGES:
        raise ImportLineExtractionError(
            f"Unsupported language: {language}",
            file_path,
            language
        )
    
    try:
        # Get the appropriate extractor
        extractor = SUPPORTED_LANGUAGES[language]
        
        # Extract import lines (pass language for JS/TS)
        if language in ["javascript", "typescript"]:
            import_lines = extractor.extract_import_lines(code, language)
        else:
            import_lines = extractor.extract_import_lines(code)
        
        # Return structured result
        return FileImportLines(
            file_path=file_path,
            language=language,
            import_lines=import_lines
        )
        
    except Exception as e:
        # Log the error before raising
        logger.error(
            f"Import extraction failed for {file_path}: {str(e)}",
            extra={
                "file_path": file_path,
                "language": language,
                "error_type": type(e).__name__,
                "code_length": len(code) if code else 0,
            },
            exc_info=True,
        )
        # Wrap any errors in our custom exception
        raise ImportLineExtractionError(
            f"Failed to extract imports: {str(e)}",
            file_path,
            language
        )


async def extract_import_lines_from_pr_files(
    pr_files: List[Dict[str, str]]
) -> PRImportLinesSummary:
    """
    Extract raw import lines from multiple PR files in parallel.
    
    This function processes all files concurrently for better performance.
    It's the main entry point for batch processing.
    
    Args:
        pr_files: List of file dictionaries, each containing:
            - path: str - File path
            - content: str - File content
            - language: str (optional) - Programming language (auto-detected from path if not provided)
            
    Returns:
        PRImportLinesSummary with aggregated results
        
    Example:
        >>> pr_files = [
        ...     {
        ...         "path": "main.py",
        ...         "content": "import os\\nfrom app import utils",
        ...         "language": "python"
        ...     },
        ...     {
        ...         "path": "App.java",
        ...         "content": "import java.util.List;",
        ...         "language": "java"
        ...     }
        ... ]
        >>> result = await extract_import_lines_from_pr_files(pr_files)
        >>> print(result.summary)
        {'total_files': 2, 'total_imports': 3, 'languages': ['python', 'java']}
    """
    # Create tasks for parallel processing
    tasks = []
    for file_info in pr_files:
        # Auto-detect language if not provided
        language = file_info.get("language")
        if not language:
            language = detect_language_from_filename(file_info["path"])
            logger.info(
                f"Auto-detected language '{language}' for {file_info['path']}",
                extra={
                    "file_path": file_info["path"],
                    "detected_language": language
                }
            )
        
        task = extract_import_lines_from_file(
            code=file_info["content"],
            file_path=file_info["path"],
            language=language
        )
        tasks.append(task)
    
    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out errors and collect successful results
    successful_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(
                f"Failed to extract imports from file: {str(result)}",
                extra={
                    "file_path": pr_files[i].get("path", "unknown"),
                    "language": pr_files[i].get("language", "unknown"),
                    "error_type": type(result).__name__,
                },
            )
        else:
            successful_results.append(result)
    
    # Calculate summary statistics
    total_files = len(successful_results)
    total_imports = sum(len(r.import_lines) for r in successful_results)
    languages = list(set(r.language for r in successful_results))
    
    # Return aggregated results
    return PRImportLinesSummary(
        summary={
            "total_files": total_files,
            "total_imports": total_imports,
            "languages": sorted(languages)
        },
        files=successful_results
    )


async def extract_import_lines_from_pr_files_as_dict(
    pr_files: List[Dict[str, str]]
) -> Dict[str, Dict[str, Any]]:
    """
    Extract raw import lines from multiple PR files and return as dictionary.
    
    This is a convenience wrapper that returns results keyed by file_path for
    easy access. The values are dictionaries ready to pass to the LLM prompt.
    
    Args:
        pr_files: List of file dictionaries, each containing:
            - path: str - File path
            - content: str - File content
            - language: str (optional) - Programming language (auto-detected from path if not provided)
            
    Returns:
        Dictionary mapping file_path -> extracted imports dict
        Each value contains: file_path, language, import_lines
        
    Example:
        >>> pr_files = [
        ...     {
        ...         "path": "main.py",
        ...         "content": "import os\\nfrom app import utils",
        ...         "language": "python"
        ...     }
        ... ]
        >>> result = await extract_import_lines_from_pr_files_as_dict(pr_files)
        >>> print(result["main.py"])
        {
            "file_path": "main.py",
            "language": "python",
            "import_lines": ["import os", "from app import utils"]
        }
        
    Usage in pipeline:
        >>> # Get imports as dict
        >>> pr_imports_dict = await extract_import_lines_from_pr_files_as_dict(pr_files)
        >>> 
        >>> # Access specific file
        >>> file_imports = pr_imports_dict["app/services/auth.py"]
        >>> 
        >>> # Pass to prompt function
        >>> prompt = await prompt_service._identify_missing_dependencies_prompt(
        ...     file_path="app/services/auth.py",
        ...     extracted_imports=file_imports,  # Already a dict!
        ...     repo_structure=repo_structure,
        ...     pr_file_paths=pr_file_paths
        ... )
    """
    # Use existing function to get results
    summary = await extract_import_lines_from_pr_files(pr_files)
    
    # Convert to dictionary keyed by file_path
    # Each value is the dict representation ready for LLM prompt
    return {
        file_result.file_path: file_result.dict()
        for file_result in summary.files
    }


def detect_language_from_filename(filename: str) -> str:
    """
    Auto-detect programming language from file extension.
    
    This helper function maps file extensions to language names required
    by the import extraction functions. Use this when processing PR files
    that don't have language metadata.
    
    Args:
        filename: File name or path (e.g., "main.py", "src/App.tsx")
        
    Returns:
        Language name: "python", "javascript", "typescript", "java", "csharp"
        Returns "unknown" if extension is not recognized
        
    Example:
        >>> detect_language_from_filename("main.py")
        'python'
        >>> detect_language_from_filename("src/App.tsx")
        'typescript'
        >>> detect_language_from_filename("Service.java")
        'java'
        >>> detect_language_from_filename("Program.cs")
        'csharp'
        >>> detect_language_from_filename("README.md")
        'unknown'
        
    Supported extensions:
        - Python: .py
        - JavaScript: .js, .jsx, .mjs
        - TypeScript: .ts, .tsx
        - Java: .java
        - C#: .cs
    """
    # Extract extension from filename
    ext = filename.split(".")[-1].lower()
    
    # Map extensions to language names
    mapping = {
        "py": "python",
        "js": "javascript",
        "jsx": "javascript",
        "mjs": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "java": "java",
        "cs": "csharp",
    }
    
    return mapping.get(ext, "unknown")
