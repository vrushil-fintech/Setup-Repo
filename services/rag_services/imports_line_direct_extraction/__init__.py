"""
Import Line Direct Extraction Module

This module provides simplified import extraction that returns raw import lines
without path resolution or complex processing. The lines are passed directly to LLM
for dependency analysis.

Supported Languages:
- Python
- JavaScript
- TypeScript
- Java
- C#
"""

from .import_line_service import (
    extract_import_lines_from_file,
    extract_import_lines_from_pr_files,
    extract_import_lines_from_pr_files_as_dict,
    detect_language_from_filename,
)
from .models import FileImportLines, PRImportLinesSummary

__all__ = [
    "extract_import_lines_from_file",
    "extract_import_lines_from_pr_files",
    "extract_import_lines_from_pr_files_as_dict",
    "detect_language_from_filename",
    "FileImportLines",
    "PRImportLinesSummary",
]
