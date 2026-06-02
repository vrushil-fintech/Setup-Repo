from collections import deque
from tree_sitter_languages import get_parser


async def python_chunk_file(code: str, file_path: str, file_name: str):
    parser = get_parser("python")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    chunks = []
    global_statements = []
    queue = deque([root_node])

    while queue:
        node = queue.popleft()

        # 'module' is the global object. so iterate its children
        if node.type == "module":
            queue.extend(node.children)

        elif node.type == "decorated_definition":
            queue.append(node.child_by_field_name("definition"))

        elif node.type == "function_definition":
            chunk = code[node.start_byte : node.end_byte]
            chunk_name_node = node.child_by_field_name("name")
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": chunk_name_node.text.decode("utf-8"),
                "chunk_type": "function_definition",
            }
            chunks.append(chunk_obj)

        elif node.type == "class_definition":
            class_name_node = node.child_by_field_name("name")
            class_name = code[class_name_node.start_byte : class_name_node.end_byte]
            class_body_node = node.child_by_field_name("body")
            docstring = ""
            attributes = []
            for child in class_body_node.children:
                if child.type == "expression_statement" and child.children:
                    first_grandchild = child.children[0]
                    if first_grandchild.type == "string":
                        docstring = code[
                            first_grandchild.start_byte : first_grandchild.end_byte
                        ]
                    elif first_grandchild.type == "assignment":
                        attributes.append(
                            code[
                                first_grandchild.start_byte : first_grandchild.end_byte
                            ]
                        )

                elif child.type == "function_definition":
                    method_name_node = child.child_by_field_name("name")
                    function_name = code[
                        method_name_node.start_byte : method_name_node.end_byte
                    ]

                    params_node = child.child_by_field_name("parameters")
                    parameters = (
                        code[params_node.start_byte : params_node.end_byte]
                        if params_node
                        else "()"
                    )

                    function_signature = f"def {function_name}{parameters}: ..."
                    attributes.append(function_signature)

                    queue.append(child)

            class_metadata = docstring + "\n" + "\n".join(attributes)
            chunk = f"class {class_name}:\n{class_metadata}"
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": class_name,
                "chunk_type": "class_declaration",
            }
            chunks.append(chunk_obj)

        elif node.type not in ["comment", "import_from_statement", "import_statement"]:
            chunk = code[node.start_byte : node.end_byte]
            global_statements.append(chunk)

    chunk_obj = {
        "code_snippet": "\n".join(global_statements),
        "file_name": file_name,
        "file_path": file_path,
        "chunk_name": "global_statements",
        "chunk_type": "general",
    }
    chunks.append(chunk_obj)
    return chunks


def resolve_import(module_path: str) -> str:
    """
    Converts a Python module path to a file path
    eg: 'utils.helpers' to 'utils/helpers.py'
    """
    return module_path.replace(".", "/") + ".py"


def resolve_relative_import(module_path: str, current_file_path: str) -> str:
    """
    Convert relative import to a normal dotless path
    eg: '..utils.helpers' to 'app/utils/helpers.py'
    """
    parts = module_path.split(".")
    relative_parts = []
    level_ups = 0
    for part in parts:
        if part == "":
            level_ups += 1
        else:
            relative_parts.append(part)

    if level_ups == 0:
        return "/".join(relative_parts) + ".py"

    current_parts = current_file_path.strip("/").split("/")
    # Go up 'level_ups' levels
    base_parts = current_parts[:-level_ups]
    # Add the rest
    full_parts = base_parts + relative_parts

    return "/".join(full_parts) + ".py"


async def python_imports_parse(code: str, file_path: str):
    parser = get_parser("python")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    imports = []
    queue = deque([root_node])

    while queue:
        current = queue.popleft()

        if current.type == "module":
            queue.extend(current.children)

        elif current.type == "import_from_statement":
            import_file_path_node = current.child_by_field_name("module_name")
            import_el_nodes = current.children_by_field_name("name")

            if import_file_path_node is None or not import_el_nodes:
                continue

            import_file_path = import_file_path_node.text.decode("utf-8")
            if import_file_path_node.type == "relative_import":
                resolved_path = resolve_relative_import(import_file_path, file_path)
            elif import_file_path_node.type == "dotted_name":
                resolved_path = resolve_import(import_file_path)

            for el_node in import_el_nodes:
                import_el = el_node.text.decode("utf-8")
                imports.append(
                    {"chunk_name": import_el, "imported_from": resolved_path}
                )

        elif current.type == "import_statement":
            # handle plain 'import x.y.z' — each one is an entire module
            import_path_nodes = current.children_by_field_name("name")
            for path_node in import_path_nodes:
                module_path = path_node.text.decode("utf-8")
                resolved_path = resolve_import(module_path)
                # Treat the final module name as the "chunk"
                chunk_name = module_path.split(".")[-1]

                imports.append(
                    {"chunk_name": chunk_name, "imported_from": resolved_path}
                )

    return imports
