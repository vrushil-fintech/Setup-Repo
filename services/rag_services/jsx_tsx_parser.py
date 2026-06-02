from tree_sitter_languages import get_parser
from collections import deque
from app.dependencies import logger

def remove_jsx_elements_js(code: str) -> str:
    try:
        parser = get_parser("javascript")
        tree = parser.parse(bytes(code, "utf8"))
        root_node = tree.root_node
    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        return code  # Return original code as a fallback

    nodes_to_remove = []

    queue = deque([root_node])
    while queue:
        node = queue.popleft()
        if node.type == "jsx_element" or node.type == "jsx_opening_element" or node.type == "jsx_closing_element" or node.type== "jsx_self_closing_element":
            # Climb parents until a statement node is found
            parent = node.parent
            removal_node = node  # Default removal is the JSX node itself
            while parent is not None:
                # Remove the whole statement that contains JSX
                if parent.type in (
                    "expression_statement",
                    "return_statement",
                    "lexical_declaration",  # for const/let with jsx inside arrow fn
                    "variable_declarator",
                    "statement_block",  # function body block
                    "function_declaration",
                ):
                    removal_node = parent
                    break
                parent = parent.parent

            # Record byte range to remove
            nodes_to_remove.append((removal_node.start_byte, removal_node.end_byte))
        queue.extend(node.children)

    # Remove duplicates & sort descending
    nodes_to_remove = list(set(nodes_to_remove))
    nodes_to_remove.sort(key=lambda x: x[0], reverse=True)

    modified_code = code
    for start, end in nodes_to_remove:
        modified_code = modified_code[:start] + modified_code[end:]

    return modified_code



def remove_jsx_elements_ts(code: str) -> str:
    try:
        parser = get_parser("tsx")
        tree = parser.parse(bytes(code, "utf8"))
        root_node = tree.root_node
    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        return code  # Return original code as a fallback


    nodes_to_remove = []

    queue = deque([root_node])
    while queue:
        node = queue.popleft()
        if node.type == "jsx_element" or node.type == "jsx_opening_element" or node.type == "jsx_closing_element":
            # Climb parents until a statement node is found
            parent = node.parent
            removal_node = node  # Default removal is the JSX node itself
            while parent is not None:
                # Remove the whole statement that contains JSX
                if parent.type in (
                    "expression_statement",
                    "return_statement",
                    "lexical_declaration",  # for const/let with jsx inside arrow fn
                    "variable_declarator",
                    "statement_block",  # function body block
                    "function_declaration",
                ):
                    removal_node = parent
                    break
                parent = parent.parent

            # Record byte range to remove
            nodes_to_remove.append((removal_node.start_byte, removal_node.end_byte))
        queue.extend(node.children)

    # Remove duplicates & sort descending
    nodes_to_remove = list(set(nodes_to_remove))
    nodes_to_remove.sort(key=lambda x: x[0], reverse=True)

    modified_code = code
    for start, end in nodes_to_remove:
        modified_code = modified_code[:start] + modified_code[end:]

    return modified_code


def remove_jsx_by_extension(code: str, file_path: str) -> str:
    extension = "." + file_path.split(".")[-1]
    if extension == ".jsx":
        return remove_jsx_elements_js(code)
    elif extension == ".tsx":
        return remove_jsx_elements_ts(code)
    else:
        return code