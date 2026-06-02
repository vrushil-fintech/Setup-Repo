import asyncio
from collections import deque
from tree_sitter_languages import get_parser

def safe_text(node):
    return node.text.decode("utf-8") if node else "anonymous"

# Traverse function parameters and return type for type_identifiers
def find_type_identifiers(node):
    found = []
    if node is None:
        return found  # Return empty list
    queue = deque([node])
    while queue:
        current = queue.popleft()

        if current.type == "type_identifier":
            type_name = safe_text(current)
            found.append(type_name)
        # elif current.type == "nested_type_identifier":
        #     name_node = current.child_by_field_name("name")
        #     if name_node and name_node.type == "type_identifier":
        #         found.append(safe_text(name_node))

        # # Generic types: generic_type with name and type_arguments
        # elif current.type == "generic_type":
        #     name_node = current.child_by_field_name("name")
        #     if name_node:
        #         found.extend(find_type_identifiers(name_node))
        #     type_args = current.child_by_field_name("type_arguments")
        #     if type_args:
        #         queue.extend(type_args.children)

        # # Type arguments, type annotations, type assertions
        # elif current.type in ("type_arguments", "type_annotation", "type_assertion", "object_type", "property_signature"):
        #     queue.extend(current.children)
        
        queue.extend(current.children)
    return found

async def ts_chunk_file(code: str, file_path: str, file_name: str):
    file_path = file_path.rsplit(".", 1)[0]
    parser = get_parser("tsx")
     # or "typescript" if that's what your parser expects
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    chunks = []
    global_statements = []

    queue = deque([root_node])
    decalaration_types = {}

    while queue:
        node = queue.popleft()

        if node.type == "program":
            queue.extend(node.children)
        
        else:
            child = node
            processed_node = child

            # Handle exported declarations
            if child.type == "export_statement":
                exported_node = next(
                    (c for c in child.children if c.type in {
                        "function_declaration", "class_declaration", "variable_declaration", "abstract_class_declaration","interface_declaration","enum_declaration" ,"type_alias_declaration"
                    }), None
                )
                if not exported_node:
                    continue
                processed_node = exported_node

            if processed_node.type in ["interface_declaration","enum_declaration" ,"type_alias_declaration"]:
                name_node = processed_node.child_by_field_name("name")
                name = safe_text(name_node)
                chunk = code[processed_node.start_byte : processed_node.end_byte]
                chunks.append({
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": name,
                    "chunk_type": "interface_declaration",
                })
                decalaration_types[name] = {"node": processed_node, "code_snippet": chunk, "chunk_name": name}
                # decalaration_types.append({
                #     "code_snippet": chunk,
                #     "chunk_name" : name
                # })
                # decl_names.add(name)

            # Function Declarations
            if processed_node.type == "function_declaration":
                name_node = processed_node.child_by_field_name("name")
                name = safe_text(name_node)
                chunk = code[processed_node.start_byte : processed_node.end_byte]

                # Check in parameters and return_type fields
                params_node = processed_node.child_by_field_name("parameters")
                return_type_node = processed_node.child_by_field_name("return_type")

                referenced_types = find_type_identifiers(processed_node)
                # if params_node:
                #     referenced_types.extend(find_type_identifiers(params_node))
                # if return_type_node:
                #     referenced_types.extend(find_type_identifiers(return_type_node))

                # Append matching declaration code snippets
                for type_name in set(referenced_types):  # set() to avoid duplicates
                    if type_name in decalaration_types:
                        chunk += "\n\n" + decalaration_types[type_name]["code_snippet"]

                chunks.append({
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": name,
                    "chunk_type": "function_definition",
                })

            # Variable declarations (e.g., arrow functions, function expressions)
            elif processed_node.type in ("variable_declaration", "lexical_declaration"):
                for declarator in processed_node.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        name = safe_text(name_node)
                        init_node = declarator.child_by_field_name("value")
                        if init_node and init_node.type in (
                            "arrow_function", "function_expression", "type_annotation", "function"
                        ):
                            chunk = code[declarator.start_byte : declarator.end_byte]

                            referenced_types = find_type_identifiers(processed_node)
                            # if params_node:
                            #     referenced_types.extend(find_type_identifiers(params_node))
                            # if return_type_node:
                            #     referenced_types.extend(find_type_identifiers(return_type_node))

                            # Append matching declaration code snippets
                            for type_name in set(referenced_types):  # set() to avoid duplicates
                                if type_name in decalaration_types:
                                    chunk += "\n\n" + decalaration_types[type_name]["code_snippet"]

                            chunks.append({
                                "code_snippet": chunk,
                                "file_name": file_name,
                                "file_path": file_path,
                                "chunk_name": name,
                                "chunk_type": "function_definition",
                            })

            # Assignment-based expressions (e.g., exports.getAll = () => {})
            elif processed_node.type == "expression_statement":
                assignment_node = next(
                    (c for c in processed_node.children if c.type == "assignment_expression"),
                    None
                )
                if assignment_node:
                    left_node = assignment_node.child_by_field_name("left")
                    right_node = assignment_node.child_by_field_name("right")

                    if left_node and right_node and right_node.type in ("arrow_function", "function_expression", "function"):
                        name = left_node.text.decode("utf-8").replace("exports.", "")
                        chunk = code[assignment_node.start_byte : assignment_node.end_byte]

                        referenced_types = find_type_identifiers(processed_node)
                        # if params_node:
                        #     referenced_types.extend(find_type_identifiers(params_node))
                        # if return_type_node:
                        #     referenced_types.extend(find_type_identifiers(return_type_node))

                        # Append matching declaration code snippets
                        for type_name in set(referenced_types):  # set() to avoid duplicates
                            if type_name in decalaration_types:
                                chunk += "\n\n" + decalaration_types[type_name]["code_snippet"]

                        chunks.append({
                            "code_snippet": chunk,
                            "file_name": file_name,
                            "file_path": file_path,
                            "chunk_name": name,
                            "chunk_type": "function_definition",
                        })
                    
                    elif left_node and right_node and right_node.type in ["class", "class_declaration"]:
                        queue.append(right_node)

            # Class Declarations
            elif processed_node.type in ["class_declaration", "abstract_class_declaration", "class"]:
                name_node = processed_node.child_by_field_name("name")
                class_name = name_node.text.decode("utf-8") if name_node else "UnnamedClass"
                body_node = processed_node.child_by_field_name("body")

                methods = []
                attributes = []
                class_metadata = ""
                docstring = ""

                if body_node:
                    for method in body_node.children:
                        if method.type in ("method_definition", "method_signature"):
                            method_name_node = method.child_by_field_name("name")
                            method_name = (
                                method_name_node.text.decode("utf-8") if method_name_node else "UnnamedMethod"
                            )
                            params_node = method.child_by_field_name("parameters")
                            params_text = (
                                code[params_node.start_byte : params_node.end_byte]
                                if params_node else "()"
                            )
                            method_signature = f"function {method_name}{params_text} {{ ... }}"
                            methods.append(method_signature)
                        
                        elif method.type == "public_field_definition":
                            field_text = code[method.start_byte : method.end_byte]
                            attributes.append(field_text)

                if attributes:
                    class_metadata += "\n".join(attributes)
                    class_metadata += "\n"
                class_metadata += "\n".join(methods)
                chunk = f"class {class_name} {{\n{class_metadata}\n}}"

                referenced_types = find_type_identifiers(processed_node)
                # if params_node:
                #     referenced_types.extend(find_type_identifiers(params_node))
                # if return_type_node:
                #     referenced_types.extend(find_type_identifiers(return_type_node))

                # Append matching declaration code snippets
                for type_name in set(referenced_types):  # set() to avoid duplicates
                    if type_name in decalaration_types:
                        chunk += "\n\n" + decalaration_types[type_name]["code_snippet"]

                chunks.append({
                    "code_snippet": chunk,
                    "file_name": file_name,
                    "file_path": file_path,
                    "chunk_name": class_name,
                    "chunk_type": "class_declaration",
                })

            

            elif processed_node.type not in ["import_statement", "comment","interface_declaration","enum_declaration" ,"type_alias_declaration"]:
                chunk = code[child.start_byte : child.end_byte]
                global_statements.append(chunk)


    if global_statements:
        chunks.append({
            "code_snippet": "\n".join(global_statements),
            "file_name": file_name,
            "file_path": file_path,
            "chunk_name": "global_statements",
            "chunk_type": "general",
        })


    return chunks

# ---------------------------- #


async def js_chunk_file(code: str, file_path: str, file_name: str):
    file_path = file_path.rsplit(".", 1)[0]
    parser = get_parser("javascript")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node

    chunks = []
    global_statements = []
    queue = deque([root_node])

    while queue:
        node = queue.popleft()

        if node.type == "program":
            queue.extend(node.children)
        
        else:
            child = node
            processed_node = child
        
            # Handle exported declarations
            if child.type == "export_statement":
                exported_node = next(
                    (c for c in child.children if c.type in {
                        "function_declaration", "class_declaration", "variable_declaration"
                    }), None
                )
                if not exported_node:
                    continue
                processed_node = exported_node

            # === Handle function_declaration ===
            elif processed_node.type == "function_declaration":
                chunk = safe_text(node)
                chunk_name_node = node.child_by_field_name("name")
                chunk_obj = {
                    "code_snippet": chunk,
                    "file_path": file_path,
                    "file_name": file_name,
                    "chunk_name": safe_text(chunk_name_node),
                    "chunk_type": "function_definition",
                }
                chunks.append(chunk_obj)

            # === Handle variable_declaration with arrow functions / function expressions ===
            elif processed_node.type in ["variable_declaration", "lexical_declaration"]:
                for declarator in node.children:
                    if declarator.type == "variable_declarator":
                        name_node = declarator.child_by_field_name("name")
                        value_node = declarator.child_by_field_name("value")
                        if value_node and value_node.type in [
                            "arrow_function",
                            "function_expression",
                            "function"
                        ]:
                            chunk = safe_text(declarator)
                            chunk_obj = {
                                "code_snippet": chunk,
                                "file_path": file_path,
                                "file_name": file_name,
                                "chunk_name": safe_text(name_node),
                                "chunk_type": "function_definition",
                            }
                            chunks.append(chunk_obj)

            # === Handle expression_statement with assignment_expression (e.g., exports.* = () => {}) ===
            elif processed_node.type == "expression_statement":
                assignment_node = next(
                    (c for c in node.children if c.type == "assignment_expression"), None
                )
                if assignment_node:
                    left_node = assignment_node.child_by_field_name("left")
                    right_node = assignment_node.child_by_field_name("right")
                    if right_node and right_node.type in [
                        "arrow_function",
                        "function_expression",
                        "function"
                    ]:
                        function_name = safe_text(left_node).replace("exports.", "")
                        chunk = safe_text(assignment_node)
                        chunk_obj = {
                            "code_snippet": chunk,
                            "file_path": file_path,
                            "file_name": file_name,
                            "chunk_name": function_name,
                            "chunk_type": "function_definition",
                        }
                        chunks.append(chunk_obj)
                    
                    elif left_node and right_node and right_node.type in ["class", "class_declaration"]:
                        queue.append(right_node)

            # === Handle class_declaration ===
            elif processed_node.type in ["class_declaration", "class"]:
                class_name_node = node.child_by_field_name("name")
                class_name = class_name_node.text.decode("utf-8") if class_name_node else "UnnamedClass"
                class_body_node = node.child_by_field_name("body")

                methods = []
                attributes = []
                class_metadata = ""
                members = (
                    class_body_node.children_by_field_name("member")
                    if class_body_node
                    else []
                )
                for member in members:
                    if member.type == "method_definition":
                        method_name_node = member.child_by_field_name("name")
                        function_name = safe_text(method_name_node)
                        params_node = member.child_by_field_name("parameters")
                        parameters = safe_text(params_node) if params_node else "()"
                        function_signature = f"function {function_name}{parameters} {{...}}"
                        methods.append(function_signature)

                    elif member.type == "public_field_definition":
                            field_text = code[member.start_byte : member.end_byte]
                            attributes.append(field_text)

                if attributes:
                    class_metadata += "\n".join(attributes)
                    class_metadata += "\n"
                class_metadata += "\n".join(methods)
                chunk = f"class {class_name} {{\n {class_metadata} \n}}"
                chunk_obj = {
                    "code_snippet": chunk,
                    "file_path": file_path,
                    "file_name": file_name,
                    "chunk_name": class_name,
                    "chunk_type": "class_declaration",
                }
                chunks.append(chunk_obj)

            elif processed_node.type not in ["import_statement", "comment"]:
                chunk = safe_text(node)
                global_statements.append(chunk)

    # Final chunk for global statements
    if global_statements:
        chunk_obj = {
            "code_snippet": "\n".join(global_statements),
            "file_path": file_path,
            "file_name": file_name,
            "chunk_name": "global_statements",
            "chunk_type": "general",
        }
        chunks.append(chunk_obj)

    return chunks


def resolve_js_ts_import_path(import_path: str, current_file_path: str) -> str:
    code_extensions = (".js", ".jsx", ".ts", ".tsx")

    # If the path has an extension and it's not a code file (e.g., .css, .svg) — skip it
    if "." in import_path.split("/")[-1]:
        if not import_path.endswith(code_extensions):
            return ""

    # is_jsx_file = current_file_path.endswith(".jsx") or current_file_path.endswith(".tsx")

    if import_path.startswith((".", "/")):
        current_parts = current_file_path.strip("/").split("/")[:-1]
        import_parts = import_path.strip("/").split("/")
        # removing extension from the import path (if present)
        if "." in import_parts[-1]:
            import_parts[-1] = import_parts[-1].split(".")[0]

        resolved_parts = []
        for part in import_parts:
            if part == "..":
                if current_parts:
                    current_parts.pop()
            elif part != ".":
                resolved_parts.append(part)

        full_parts = current_parts + resolved_parts
        resolved_path = "/".join(full_parts)

        # if not (resolved_path.endswith(code_extensions)):
        #     resolved_path += ".jsx" if is_jsx_file else ".js"

        return resolved_path
    # Else it's a node_modules import
    else:
        # return f"node_modules/{import_path}.jsx" if is_jsx_file else f"node_modules/{import_path}.js"
        return ""


def safe_text_imports(node):
    return node.text.decode("utf-8") if node else ""


async def js_ts_imports_parse(code: str, file_path: str):
    parser = get_parser("javascript")
    tree = parser.parse(bytes(code, "utf8"))
    root_node = tree.root_node
    imports = []
    queue = deque([root_node])

    while queue:
        current = queue.popleft()

        if current.type == "program":
            queue.extend(current.children)

        # --- ES6 import ---
        elif current.type == "import_statement":
            source_node = current.child_by_field_name("source")
            if not source_node:
                continue

            import_path = safe_text_imports(source_node).strip("\"'")
            resolved_path = resolve_js_ts_import_path(import_path, file_path)

            # if it's a node_modules import skip
            if not resolved_path:
                continue

            imported_el = []
            imported_el.extend(current.children_by_field_name("name"))
            if not imported_el:
                for child in current.children:
                    if child.type == "import_clause":
                        for grandchild in child.children:
                            if grandchild.type == "identifier":
                                imported_el.append(
                                    code[grandchild.start_byte : grandchild.end_byte]
                                )
                            elif grandchild.type == "named_imports":
                                for grandgrandchild in grandchild.children:
                                    if grandgrandchild.type == "import_specifier":
                                        import_el_node = (
                                            grandgrandchild.child_by_field_name("name")
                                        )
                                        imported_el.append(
                                            code[
                                                import_el_node.start_byte : import_el_node.end_byte
                                            ]
                                        )

            if imported_el:
                for chunk_name in imported_el:
                    imports.append(
                        {"chunk_name": chunk_name, "imported_from": resolved_path}
                    )
            else:
                imports.append(
                    {
                        "chunk_name": "(side_effect_import)",
                        "imported_from": resolved_path,
                    }
                )

        # --- CommonJS require() ---
        elif current.type == "lexical_declaration":
            for child in current.children:
                if child.type == "variable_declarator":
                    init_node = child.child_by_field_name("value")
                    name_node = child.child_by_field_name("name")
                    imported_el = []
                    if name_node.type == "identifier":
                        imported_el.append(safe_text_imports(name_node))
                    elif name_node.type == "object_pattern":
                        for import_child in name_node.children:
                            if import_child.type == 'shorthand_property_identifier_pattern':
                                imported_el.append(
                                    safe_text_imports(import_child)
                                )

                    if (
                        init_node
                        and init_node.type == "call_expression"
                        and safe_text_imports(init_node.child_by_field_name("function"))
                        == "require"
                    ):
                        arg_node = init_node.child_by_field_name("arguments")
                        if arg_node and arg_node.child_count > 0:
                            required_path_node = arg_node.children[1]
                            import_path = safe_text_imports(required_path_node).strip(
                                "\"'"
                            )
                            resolved_path = resolve_js_ts_import_path(
                                import_path, file_path
                            )

                            # if it's not a node_modules import
                            if resolved_path:
                                for chunk_name in imported_el:
                                    imports.append(
                                        {
                                            "chunk_name": chunk_name,
                                            "imported_from": resolved_path,
                                        }
                                    )

        # Also handle `const x = require(...)` outside `lexical_declaration`
        elif current.type == "expression_statement":
            call_node = current.child_by_field_name("expression") or current.children[0]

            # Unwrap if it's a chained call: e.g., require("x").config();
            if call_node.type == "call_expression":
                inner_func = call_node.child_by_field_name("function")

                # Case: require("x")(); → inner_func is a call_expression
                if inner_func and inner_func.type == "call_expression":
                    func_id = inner_func.child_by_field_name("function")
                    if (
                        func_id
                        and func_id.type == "identifier"
                        and func_id.text.decode() == "require"
                    ):
                        arg_node = inner_func.child_by_field_name("arguments").children[
                            1
                        ]
                        if arg_node.type == "string":
                            import_path = arg_node.text.decode("utf-8").strip("\"'")
                            resolved_path = resolve_js_ts_import_path(
                                import_path, file_path
                            )

                            # if it's not a node_modules import
                            if resolved_path:
                                imports.append(
                                    {
                                        "chunk_name": "anonymous",
                                        "imported_from": resolved_path,
                                    }
                                )

                # Case: require("x").config(); → inner_func is a member_expression
                elif inner_func and inner_func.type == "member_expression":
                    object_node = inner_func.child_by_field_name("object")
                    property_node = inner_func.child_by_field_name("property")
                    if object_node and object_node.type == "call_expression":
                        func_id = object_node.child_by_field_name("function")
                        if (
                            func_id
                            and func_id.type == "identifier"
                            and func_id.text.decode() == "require"
                        ):
                            arg_node = object_node.child_by_field_name(
                                "arguments"
                            ).children[1]
                            if arg_node.type == "string":
                                import_path = arg_node.text.decode("utf-8").strip("\"'")
                                resolved_path = resolve_js_ts_import_path(
                                    import_path, file_path
                                )

                                # if it's not a node_modules import
                                if resolved_path:
                                    chunk_name = safe_text_imports(property_node)
                                    imports.append(
                                        {
                                            "chunk_name": (
                                                chunk_name
                                                if chunk_name
                                                else "anonymous"
                                            ),
                                            "imported_from": resolved_path,
                                        }
                                    )

    return imports


if __name__ == "__main__":
    code = """
import React from "react";
import { formatUser } from './utils';

// Enum declaration
enum Status {
    Active = "ACTIVE",
    Inactive = "INACTIVE",
    Pending = "PENDING",
    Deleted = "DELETED",
}

// Type declaration
type UserRole = "admin" | "editor" | "viewer";

// Interface declaration
interface User {
    id: number;
    name: string;
    role: UserRole;
    status: Status;
}

// Sample function that accepts a User and returns a message
function getUserStatusMessage(user: User): string {
    switch (user.status) {
        case Status.Active:
            return `${user.name} is active and working as ${user.role}.`;
        case Status.Inactive:
            return `${user.name} is currently inactive.`;
        case Status.Pending:
            return `${user.name} has a pending status, awaiting approval.`;
        case Status.Deleted:
            return `${user.name}'s account has been deleted.`;
        default:
            return "Unknown status.";
    }
}

// React Functional Component using the above types
const UserCard: React.FC<{ user: User }> = ({ user }) => {
    const message = getUserStatusMessage(user);
    const cardStyle: React.CSSProperties = {
        border: "1px solid #ccc",
        padding: "16px",
        margin: "16px",
        borderRadius: "8px",
        backgroundColor:
            user.status === Status.Active
                ? "#e0ffe0"
                : user.status === Status.Inactive
                ? "#ffe0e0"
                : "#f0f0f0",
    };

    return (
        <div style={cardStyle}>
            <h2>{user.name}</h2>
            <p>Role: {user.role}</p>
            <p>Status: {user.status}</p>
            <p>{message}</p>
        </div>
    );
};

// Example usage in another component
const App: React.FC = () => {
    const users: User[] = [
        { id: 1, name: "Alice", role: "admin", status: Status.Active },
        { id: 2, name: "Bob", role: "viewer", status: Status.Inactive },
        { id: 3, name: "Charlie", role: "editor", status: Status.Pending },
    ];

    return (
        <div>
            <h1>User List</h1>
            {users.map((user) => (
                <UserCard key={user.id} user={user} />
            ))}
        </div>
    );
};

export default App;

export interface User {
  id: number;
  name: string;
  email: string;
}

export type UserRole = 'admin' | 'editor' | 'viewer';

export function formatUser(user: User, role: UserRole): string {
  return `${user.name} (${role}) - ${user.email}`;
}

"""

    # with open("D:/GitHub/CodeNeuPrompts/rag/temp_dir/js_ts_imports.js", "r") as f:
    #     code = f.read()

    # imports = asyncio.run(js_ts_imports_parse(code, "rag/temp_dir/js_ts_imports.js"))
    # for imp in imports:
    #     print(imp)

    # chunks = asyncio.run(ts_chunk_file(code, "my/dir/ts_sample_code.ts", "ts_sample_code.ts"))
    # for c in chunks:
    #     print(c)
    # chunks = asyncio.run(ts_chunk_file(code, "my/dir/ts_sample_code.ts","ts_sample_code.ts"))
    # for c in chunks:
    #     print("\n--- CHUNK ---")
    #     for key, value in c.items():
    #         print(f"{key}: {value}")