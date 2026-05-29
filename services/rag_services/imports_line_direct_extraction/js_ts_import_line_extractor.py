"""
JavaScript/TypeScript Import Line Extractor

Extracts raw import lines from JS/TS code using Tree-sitter AST parsing.
Returns lines as-is without path resolution or processing.
"""

from typing import List
from app.dependencies import logger
from tree_sitter_languages import get_parser, get_language

# Initialize Tree-sitter for JavaScript and TypeScript
js_parser = get_parser("javascript")
ts_parser = get_parser("typescript")
javascript_language = get_language("javascript")
typescript_language = get_language("typescript")


def extract_import_lines(code: str, language: str = "javascript") -> List[str]:
    """
    Extract raw import lines from JavaScript or TypeScript code.
    
    Args:
        code: JS/TS source code as string
        language: "javascript" or "typescript"
        
    Returns:
        List of raw import lines (no duplicates, no comments)
        
    Example:
        >>> code = '''
        ... import React from 'react';
        ... import { useState } from 'react';
        ... // import lodash from 'lodash';  (commented, will be skipped)
        ... import React from 'react';  (duplicate, will be skipped)
        ... '''
        >>> extract_import_lines(code, "javascript")
        ["import React from 'react';", "import { useState } from 'react';"]
    """
    try:
        # Select appropriate parser
        parser = ts_parser if language == "typescript" else js_parser
        lang = typescript_language if language == "typescript" else javascript_language
        
        # Parse code into AST
        tree = parser.parse(bytes(code, "utf8"))
        root = tree.root_node
        
        import_lines = []
        seen_lines = set()  # Track duplicates
        
        # Query for import statements
        query = lang.query("""
            (import_statement) @import
        """)
        
        captures = query.captures(root)
        
        for node, tag in captures:
            # Extract the raw import line (preserve formatting)
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
            f"Failed to parse {language} code: {str(e)}",
            extra={
                "language": language,
                "error_type": type(e).__name__,
                "code_length": len(code) if code else 0,
            },
            exc_info=True,
        )
        return []
