import asyncio
from collections import deque
from tree_sitter import Node
from tree_sitter_languages import get_parser


async def csharp_chunk_file(code: str, file_path: str, file_name: str):
    parser = get_parser("c_sharp")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    chunks = []

    queue = deque([(root_node, None)])  # Store (node, current_namespace)

    while queue:
        node, current_namespace = queue.popleft()

        for child in node.children:
            if child.type == "namespace_declaration":
                # Extract namespace name
                namespace_name_node = child.child_by_field_name("name")
                namespace_name = namespace_name_node.text.decode() if namespace_name_node else None
                for grandchild in child.children:
                    queue.append((grandchild, namespace_name))  # Update current_namespace

            elif child.type == "class_declaration":
                chunk, class_name = extract_csharp_class_skeleton(child)
                chunk_obj = {
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": class_name,
                    "chunk_type": "class_declaration",
                    "namespace": current_namespace,  # Track namespace
                }
                chunks.append(chunk_obj)

            elif child.type == "interface_declaration":
                chunk = child.text.decode()
                chunk_name = child.child_by_field_name("name").text.decode()
                chunk_obj = {
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": chunk_name,
                    "chunk_type": "interface_declaration",
                    "namespace": current_namespace,  # Track namespace
                }
                chunks.append(chunk_obj)

            elif child.type == "method_declaration":
                chunk, method_name = extract_csharp_method_skeleton(child)
                chunk_obj = {
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": method_name,
                    "chunk_type": "function_declaration",
                    "namespace": current_namespace,  # Track namespace
                }
                chunks.append(chunk_obj)

    return chunks

def extract_csharp_class_skeleton(class_node: Node):
    class_info = {"name": "", "variables": [], "methods": []}
    class_name_node = class_node.child_by_field_name("name")
    class_name = class_name_node.text.decode()
    class_info["name"] = "class " + class_name
    class_body_node = class_node.child_by_field_name("body")

    for child in class_node.children:
        if child.type == "modifier":
            class_info["name"] = child.text.decode() + " " + class_info["name"]
        # parent class
        elif child.type == "base_list":
            class_info["name"] = class_info["name"] + " " + child.text.decode()

    for child in class_body_node.children:
        if child.type in ["method_declaration", "constructor_declaration"]:
            class_info["methods"].append(extract_csharp_method_skeleton(child)[0])
        elif child.type == "field_declaration":
            class_info["variables"].append(child.text.decode())

    class_metadata = ""
    class_skeleton = ""
    if class_info["variables"]:
        class_metadata += "\n".join(class_info["variables"]) + "\n"
    class_metadata += "\n".join(class_info["methods"])

    class_skeleton = f"{class_info['name']} {{\n{class_metadata}\n}}"
    return class_skeleton, class_name

def extract_csharp_method_skeleton(method_node: Node):
    """Extracts method name and parameters (no body)."""
    type_text = ""
    type_node = method_node.child_by_field_name("type")
    if type_node:
        type_text = type_node.text.decode()
    name_node = method_node.child_by_field_name("name")
    name_text = name_node.text.decode()
    params_node = method_node.child_by_field_name("parameters")
    params = params_node.text.decode()

    for child in method_node.children:
        if child.type == "modifier":
            type_text = child.text.decode() + " " + type_text

    method_skeleton = f"{type_text} {name_text}{params}{{...}}"
    return method_skeleton, name_text

async def csharp_imports_parse(code: str):
    parser = get_parser("c_sharp")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    usings = []

    queue = deque([root_node])
    while queue:
        node = queue.popleft()

        for child in node.children:
            if child.type == "using_directive":
                import_info = {
                    "import_type": "namespace",
                    "imported_from": None,
                    "alias_name": None
                }
                imported_path_node = child.child_by_field_name("name")
                import_info["imported_from"] = imported_path_node.text.decode()
                alias_node = child.child_by_field_name("alias_name")
                if alias_node:
                    import_info["alias_name"] = alias_node.text.decode().split(" ")[0]
                
                usings.append(import_info)


    return usings


if __name__ == "__main__":
    code = ""
    with open("C:/GitHub/CodeNeuPrompts/rag/temp_dir/temp1.cs", "r") as f:
        code = f.read()
    
    # chunks = asyncio.run(csharp_chunk_file(code=code, file_path="my/dir/temp1.cs", file_name="temp1.cs"))
    # for c in chunks:
    #     print("---")
    #     print(c)
    imports = asyncio.run(csharp_imports_parse(code=code))
    for i in imports:
        print("---")
        print(i)