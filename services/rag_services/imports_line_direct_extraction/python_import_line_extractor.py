"""
Python Import Line Extractor

Extracts raw import lines from Python code using Tree-sitter AST parsing.
Returns lines as-is without path resolution or processing.
"""

from typing import List
from app.dependencies import logger
from tree_sitter_languages import get_parser, get_language

# Initialize Tree-sitter for Python
parser = get_parser("python")
python_language = get_language("python")
 

def extract_import_lines(code: str) -> List[str]:
    """
    Extract raw import lines from Python code.
    
    Args:
        code: Python source code as string
        
    Returns:
        List of raw import lines (no duplicates, no comments)
        
    Example:
        >>> code = '''
        ... import os
        ... from app.utils import helper
        ... # import sys  (this will be skipped - it's a comment)
        ... import os  (duplicate, will be skipped)
        ... '''
        >>> extract_import_lines(code)
        ['import os', 'from app.utils import helper']
    """
    try:
        # Parse code into AST
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        
        import_lines = []
        seen_lines = set()  # Track duplicates
        
        # Query for import statements
        query = python_language.query("""
            (import_statement) @import
            (import_from_statement) @import_from
        """)
        
        captures = query.captures(root)
        
        for node, tag in captures:
            # Extract the raw import line
            import_line = code[node.start_byte:node.end_byte].strip()
            
            # Skip if duplicate
            if import_line in seen_lines:
                continue
            
            # Skip if empty
            if not import_line:
                continue
            
            # Add to results
            import_lines.append(import_line)
            seen_lines.add(import_line)
        
        return import_lines
        
    except Exception as e:
        # If parsing fails, log and return empty list
        logger.warning(
            f"Failed to parse Python code: {str(e)}",
            extra={
                "language": "python",
                "error_type": type(e).__name__,
                "code_length": len(code) if code else 0,
            },
            exc_info=True,
        )
        return []


def is_commented_import(code: str, node) -> bool:
    """
    Check if an import is commented out.
    Note: Tree-sitter automatically excludes comments from the AST,
    so this is typically not needed, but kept for edge cases.
    """
    # Tree-sitter AST doesn't include commented code
    # This is a safety check
    return False
