"""
Simplified data models for direct import line extraction.

These models store raw import lines without path resolution or complex processing.
The import lines are passed directly to LLM for analysis.
"""

from typing import List, Dict, Any
from pydantic import BaseModel, Field


class FileImportLines(BaseModel):
    """
    Represents raw import lines from a single file.
    
    Example:
        {
            "file_path": "app/services/auth.py",
            "language": "python",
            "import_lines": [
                "import os",
                "from app.utils import helper"
            ]
        }
    """
    file_path: str = Field(
        description="Path to the file being analyzed"
    )
    language: str = Field(
        description="Programming language (python, javascript, typescript, java, csharp)"
    )
    import_lines: List[str] = Field(
        description="List of raw import lines as they appear in code (no duplicates, no comments)"
    )


class PRImportLinesSummary(BaseModel):
    """
    Summary of raw import lines across all files in a Pull Request.
    
    Example:
        {
            "summary": {
                "total_files": 5,
                "total_imports": 25,
                "languages": ["python", "javascript"]
            },
            "files": [...]
        }
    """
    summary: Dict[str, Any] = Field(
        description="Overall statistics about imports in the PR"
    )
    files: List[FileImportLines] = Field(
        description="Import lines for each file"
    )


class ImportLineExtractionError(Exception):
    """Custom exception for import line extraction errors."""
    
    def __init__(self, message: str, file_path: str, language: str):
        self.message = message
        self.file_path = file_path
        self.language = language
        super().__init__(f"{message} (file: {file_path}, language: {language})")
