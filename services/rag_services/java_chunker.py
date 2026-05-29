import asyncio
from collections import deque
from tree_sitter import Node
from tree_sitter_languages import get_parser


async def java_chunk_file(code: str, file_path: str, file_name: str):
    # removing .java from the end
    file_path = file_path.split(".")[0]
    parser = get_parser("java")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    chunks = []

    for child in root_node.children:
        if child.type == "class_declaration":
            chunk, class_name = extract_java_class_skeleton(child)
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": class_name,
                "chunk_type": "class_declaration",
            }
            chunks.append(chunk_obj)

        elif child.type == "method_declaration":
            chunk, method_name = extract_java_method_skeleton(child)
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": method_name,
                "chunk_type": "function_declaration",
            }
            chunks.append(chunk_obj)

        elif child.type in ["interface_declaration"]:
            chunk = child.text.decode()
            interface_name = child.child_by_field_name("name").text.decode()
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": interface_name,
                "chunk_type": "interface_declaration",
            }
            chunks.append(chunk_obj)

        elif child.type in ["local_variable_declaration"]:
            chunk = child.text.decode()
            chunk_obj = {
                "code_snippet": chunk,
                "file_name": file_name,
                "file_path": file_path,
                "chunk_name": "global_statements",
                "chunk_type": "general",
            }
            chunks.append(chunk_obj)

    return chunks

def extract_java_class_skeleton(class_node: Node):
    class_info = {"name": "", "variables": [], "methods": []}
    class_name_node = class_node.child_by_field_name("name")
    class_name = class_name_node.text.decode()
    class_info["name"] = "class " + class_name
    super_class_node = class_node.child_by_field_name("superclass")
    if super_class_node:
        class_info["name"] += " " + super_class_node.text.decode()

    for child in class_node.children:
        if child.type == "modifiers":
            class_info["name"] = child.text.decode() + " " + class_info["name"]
        elif child.type == "class_body":
            for grandchild in child.children:
                if grandchild.type == "method_declaration":
                    class_info["methods"].append(extract_java_method_skeleton(grandchild)[0])
                elif grandchild.type == "constructor_declaration":
                    class_info["methods"].append(extract_java_constructor_skeleton(grandchild)[0])
                elif grandchild.type == "field_declaration":
                    class_info["variables"].append(grandchild.text.decode())

    class_metadata = ""
    class_skeleton = ""
    if class_info["variables"]:
        class_metadata += "\n".join(class_info["variables"])
        class_metadata += "\n"

    class_metadata += "\n".join(class_info["methods"])
    class_skeleton = f"{class_info['name']} {{\n{class_metadata}\n}}"

    return class_skeleton, class_name

def extract_java_method_skeleton(method_node: Node):
    """Extracts method name and parameters (no body)."""
    name_node = method_node.child_by_field_name("name")
    name_text = name_node.text.decode()
    params_node = method_node.child_by_field_name("parameters")
    params = params_node.text.decode()
    method_prefix = ""
    # returns_node = method_node.child_by_field_name("returns")
    # returns = returns_node.text.decode()

    for child in method_node.children:
        if child.type in ["modifiers", "void_type", "type_identifier"]:
            method_prefix += child.text.decode() + " "
    
    method_skeleton = f"{method_prefix}{name_text}{params}{{...}}"

    return method_skeleton, name_text

def extract_java_constructor_skeleton(method_node: Node):
    """Extracts method name and parameters (no body)."""
    type_text = ""
    name_node = method_node.child_by_field_name("name")
    name_text = name_node.text.decode()
    params_node = method_node.child_by_field_name("parameters")
    params = params_node.text.decode()

    for child in method_node.children:
        if child.type == "modifiers":
            type_text += child.text.decode()
    
    method_skeleton = f"{type_text} {name_text}{params}{{...}}"

    return method_skeleton, name_text

def resolve_import(module_path: str) -> str:
    """
    Converts a Java import path to a relative file path.
    Eg: com.myapp.utils.Util → com/myapp/utils/Util
    Eg: com.myapp.utils.* → com/myapp/utils/
    """
    if module_path.endswith(".*"):
        module_path = module_path[:-2]  # remove trailing .*
        return "/".join(module_path.split(".")) + "/"  # folder path

    return "/".join(module_path.split("."))

async def java_imports_parse(code: str, file_path: str):
    parser = get_parser("java")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    imports = []
    queue = deque([root_node])

    while queue:
        current = queue.popleft()

        if current.type in ["program", "compilation_unit"]:
            queue.extend(current.children)

        elif current.type == "import_declaration":
            full_text = current.text.decode().strip()
            # Remove 'import', 'static', ';'
            clean_text = full_text.replace('import', '').replace('static', '').replace(';', '').strip()

            full_import_path = clean_text
            resolved_path = resolve_import(full_import_path)

            # chunk_name is last part or '*'
            if full_import_path.endswith(".*"):
                chunk_name = "*"
            else:
                chunk_name = full_import_path.split(".")[-1]

            imports.append({
                "chunk_name": chunk_name,
                "imported_from": resolved_path
            })

    return imports
