"""
C# Import Line Extractor

Extracts raw using directives from C# code using Tree-sitter AST parsing.
Returns lines as-is without path resolution or processing.
"""

from typing import List
from app.dependencies import logger
from tree_sitter_languages import get_parser, get_language

# Initialize Tree-sitter for C#
parser = get_parser("c_sharp")
csharp_language = get_language("c_sharp")


def extract_import_lines(code: str) -> List[str]:
    """
    Extract raw using directives from C# code.
    
    Args:
        code: C# source code as string
        
    Returns:
        List of raw using directives (no duplicates, no comments)
        
    Example:
        >>> code = '''
        ... using System;
        ... using System.Collections.Generic;
        ... // using System.Linq;  (commented, will be skipped)
        ... using System;  (duplicate, will be skipped)
        ... '''
        >>> extract_import_lines(code)
        ['using System;', 'using System.Collections.Generic;']
    """
    try:
        # Parse code into AST
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        
        import_lines = []
        seen_lines = set()  # Track duplicates
        
        # Query for using directives
        query = csharp_language.query("""
            (using_directive) @using
        """)
        
        captures = query.captures(root)
        
        for node, tag in captures:
            # Extract the raw using directive
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
            f"Failed to parse C# code: {str(e)}",
            extra={
                "language": "csharp",
                "error_type": type(e).__name__,
                "code_length": len(code) if code else 0,
            },
            exc_info=True,
        )
        return []
