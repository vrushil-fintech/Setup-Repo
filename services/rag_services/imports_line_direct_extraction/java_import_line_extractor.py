"""
Java Import Line Extractor

Extracts raw import lines from Java code using Tree-sitter AST parsing.
Returns lines as-is without path resolution or processing.
"""

from typing import List
from app.dependencies import logger
from tree_sitter_languages import get_parser, get_language

# Initialize Tree-sitter for Java
parser = get_parser("java")
java_language = get_language("java")


def extract_import_lines(code: str) -> List[str]:
    """
    Extract raw import lines from Java code.
    
    Args:
        code: Java source code as string
        
    Returns:
        List of raw import lines (no duplicates, no comments)
        
    Example:
        >>> code = '''
        ... import java.util.List;
        ... import com.app.models.User;
        ... // import java.util.Map;  (commented, will be skipped)
        ... import java.util.List;  (duplicate, will be skipped)
        ... '''
        >>> extract_import_lines(code)
        ['import java.util.List;', 'import com.app.models.User;']
    """
    try:
        # Parse code into AST
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        
        import_lines = []
        seen_lines = set()  # Track duplicates
        
        # Query for import declarations
        query = java_language.query("""
            (import_declaration) @import
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
            f"Failed to parse Java code: {str(e)}",
            extra={
                "language": "java",
                "error_type": type(e).__name__,
                "code_length": len(code) if code else 0,
            },
            exc_info=True,
        )
        return []
