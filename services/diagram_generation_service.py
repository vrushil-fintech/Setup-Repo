import re
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

MERMAID_FENCE_PATTERN = re.compile(
    r"```\s*mermaid\s*\n(.*?)\n```", re.IGNORECASE | re.DOTALL
)

GRAPH_SPEC_PATTERN = re.compile(
    r"```\s*json\s*\n(.*?)\n```", re.IGNORECASE | re.DOTALL
)


# Graph-Spec System for ASCII Diagram Generation
@dataclass
class Node:
    id: str
    label: str
    attributes: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)


@dataclass
class Edge:
    source: str
    target: str
    label: Optional[str] = None


@dataclass
class Graph:
    diagram_type: str
    nodes: List[Node]
    edges: List[Edge]


def graph_from_json(data: Dict) -> Graph:
    """Parse Graph-Spec JSON into Graph object."""
    node_map = {}
    for n in data.get("nodes", []):
        node_map[n["id"]] = Node(
            id=n["id"], 
            label=n.get("label", n["id"]),
            attributes=n.get("attributes", []),
            methods=n.get("methods", [])
        )
    
    edges = []
    for e in data.get("edges", []):
        src, tgt = e.get("from") or e.get("source"), e.get("to") or e.get("target")
        if src and tgt:
            edges.append(Edge(src, tgt, e.get("label")))
            if src not in node_map:
                node_map[src] = Node(src, src)
            if tgt not in node_map:
                node_map[tgt] = Node(tgt, tgt)
    
    return Graph(
        diagram_type=data.get("diagram_type", "flow"),
        nodes=list(node_map.values()),
        edges=edges
    )


def make_box(label: str, width: Optional[int] = None) -> List[str]:
    """Create an ASCII box for a node label."""
    if width is None:
        width = max(4, len(label))
    else:
        width = max(width, len(label))
    
    top = "+" + "-" * (width + 2) + "+"
    mid = "| " + label.ljust(width) + " |"
    bot = "+" + "-" * (width + 2) + "+"
    return [top, mid, bot]


def render_edge_flow(src_label: str, tgt_label: str, edge_label: Optional[str] = None) -> str:
    """Render a single edge in flow diagram format."""
    src_box = make_box(src_label)
    tgt_box = make_box(tgt_label)
    
    gap = " " * 7
    if not edge_label:
        arrow = "-------->"
    else:
        arrow = f"-- {edge_label} --->"
    
    line1 = src_box[0] + gap + tgt_box[0]
    line2 = src_box[1] + "  " + arrow + "  " + tgt_box[1]
    line3 = src_box[2] + gap + tgt_box[2]
    
    return "\n".join([line1, line2, line3])


def render_ascii_flow(graph: Graph) -> str:
    """Render Graph-Spec as ASCII flow diagram with vertical flow layout."""
    label_map = {n.id: n.label for n in graph.nodes}
    
    if not graph.edges:
        return ""
    
    # Build adjacency list
    from collections import defaultdict
    adj = defaultdict(list)
    incoming = defaultdict(int)
    
    for e in graph.edges:
        adj[e.source].append((e.target, e.label))
        incoming[e.target] += 1
    
    # Find starting nodes (nodes with no incoming edges)
    start_nodes = [n.id for n in graph.nodes if incoming[n.id] == 0]
    if not start_nodes:
        start_nodes = [graph.nodes[0].id] if graph.nodes else []
    
    output = []
    visited = set()
    
    def render_flow_path(node_id: str, depth: int = 0):
        """Render a flow path starting from a node."""
        if node_id in visited or node_id not in label_map:
            return
        
        visited.add(node_id)
        label = label_map[node_id]
        box = make_box(label)
        
        # Add box
        for line in box:
            output.append(line)
        
        # Check for outgoing edges
        if node_id in adj and adj[node_id]:
            # Arrow down
            arrow_width = len(box[0])
            arrow_line = " " * (arrow_width // 2 - 1) + "│"
            output.append(arrow_line)
            
            # Edge label if present
            if len(adj[node_id]) == 1:
                target_id, edge_label = adj[node_id][0]
                if edge_label:
                    label_line = " " * (arrow_width // 2 - len(edge_label) // 2 - 1) + "▼ " + edge_label
                    output.append(label_line)
                else:
                    output.append(" " * (arrow_width // 2 - 1) + "▼")
                output.append("")  # Spacing
                render_flow_path(target_id, depth + 1)
            else:
                # Multiple branches
                output.append(" " * (arrow_width // 2 - 1) + "▼")
                output.append("")  # Spacing
                for i, (target_id, edge_label) in enumerate(adj[node_id]):
                    if i > 0:
                        output.append("")  # Spacing between branches
                    if edge_label:
                        branch_label = f"├─ {edge_label} ─►"
                        output.append(branch_label)
                    render_flow_path(target_id, depth + 1)
        else:
            output.append("")  # Final spacing
    
    # Render from each start node
    for i, start in enumerate(start_nodes):
        if i > 0:
            output.append("")  # Spacing between parallel flows
        render_flow_path(start)
    
    return "\n".join(output)


def render_ascii_sequence(graph: Graph) -> str:
    """Render Graph-Spec as ASCII sequence diagram with enhanced visual formatting."""
    if not graph.nodes:
        return ""
    
    # Order nodes by their appearance in edges (chronological order)
    label_map = {n.id: n.label for n in graph.nodes}
    node_order = []
    seen_nodes = set()
    
    # First, add nodes in the order they appear in edges
    for e in graph.edges:
        if e.source not in seen_nodes:
            node_order.append(e.source)
            seen_nodes.add(e.source)
        if e.target not in seen_nodes:
            node_order.append(e.target)
            seen_nodes.add(e.target)
    
    # Add any remaining nodes
    for node in graph.nodes:
        if node.id not in seen_nodes:
            node_order.append(node.id)
    
    if not node_order:
        node_order = [n.id for n in graph.nodes]
    
    # Enhanced column width for better readability
    col_width = 24
    participants = [label_map.get(nid, nid) for nid in node_order]
    node_positions = {nid: idx for idx, nid in enumerate(node_order)}
    
    output = []
    
    # Create participant boxes (top)
    box_top = "".join("┌" + "─" * (col_width - 2) + "┐" + " " for _ in participants)
    output.append(box_top.rstrip())
    
    # Participant names (centered in boxes)
    participant_line = ""
    for p in participants:
        # Truncate if too long
        display_name = p[:col_width - 4] if len(p) > col_width - 4 else p
        centered = display_name.center(col_width - 2)
        participant_line += "│" + centered + "│ "
    output.append(participant_line.rstrip())
    
    # Box bottom
    box_bottom = "".join("└" + "─" * (col_width - 2) + "┘" + " " for _ in participants)
    output.append(box_bottom.rstrip())
    
    # Lifeline starts
    lifeline = ""
    for _ in participants:
        lifeline += " " * ((col_width - 1) // 2) + "│" + " " * ((col_width - 1) // 2) + " "
    output.append(lifeline.rstrip())
    
    # Render interactions with step numbers
    step_num = 1
    for e in graph.edges:
        src_id = e.source
        tgt_id = e.target
        
        if src_id not in node_positions or tgt_id not in node_positions:
            continue
        
        src_pos = node_positions[src_id]
        tgt_pos = node_positions[tgt_id]
        
        # Calculate positions for centering
        center_offset = (col_width - 1) // 2
        
        # Create interaction line with better arrows
        interaction_line = ""
        
        if src_pos < tgt_pos:
            # Forward message (left to right)
            for i in range(len(participants)):
                if i < src_pos:
                    interaction_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
                elif i == src_pos:
                    interaction_line += " " * center_offset + "├"
                    interaction_line += "─" * (col_width - center_offset - 1)
                elif i < tgt_pos:
                    interaction_line += "─" * col_width
                elif i == tgt_pos:
                    interaction_line += "─" * center_offset + "▶│" + " " * (col_width - center_offset - 2)
                else:
                    interaction_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
        
        elif src_pos > tgt_pos:
            # Return message (right to left)
            for i in range(len(participants)):
                if i < tgt_pos:
                    interaction_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
                elif i == tgt_pos:
                    interaction_line += " " * center_offset + "│◀"
                    interaction_line += "─" * (col_width - center_offset - 2)
                elif i < src_pos:
                    interaction_line += "─" * col_width
                elif i == src_pos:
                    interaction_line += "─" * center_offset + "┤" + " " * (col_width - center_offset - 1)
                else:
                    interaction_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
        else:
            # Self-call
            interaction_line = ""
            for i in range(len(participants)):
                if i == src_pos:
                    interaction_line += " " * center_offset + "│" + "─┐" + " " * (col_width - center_offset - 3)
                else:
                    interaction_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
        
        output.append(interaction_line.rstrip())
        
        # Add label with step number
        if e.label:
            label_text = f"({step_num}) {e.label}"
            # Position label near the arrow
            if src_pos < tgt_pos:
                label_pos = src_pos * col_width + col_width
            elif src_pos > tgt_pos:
                label_pos = tgt_pos * col_width + col_width
            else:
                label_pos = src_pos * col_width + col_width
            
            label_line = " " * min(label_pos, len(interaction_line)) + label_text
            output.append(label_line)
        
        # Add self-call return arrow
        if src_pos == tgt_pos:
            return_line = ""
            for i in range(len(participants)):
                if i == src_pos:
                    return_line += " " * center_offset + "│" + "◀┘" + " " * (col_width - center_offset - 3)
                else:
                    return_line += " " * center_offset + "│" + " " * (col_width - center_offset - 1)
            output.append(return_line.rstrip())
        
        # Add lifeline continuation
        output.append(lifeline.rstrip())
        step_num += 1
    
    # Add bottom participant boxes
    output.append("")
    output.append(box_top.rstrip())
    output.append(participant_line.rstrip())
    output.append(box_bottom.rstrip())
    
    return "\n".join(output)


def render_ascii_class(graph: Graph) -> str:
    """Render Graph-Spec as ASCII class diagram with enhanced UML-like structure."""
    label_map = {n.id: n.label for n in graph.nodes}
    output = []
    
    # Calculate optimal width for each class box
    def calculate_box_width(node: Node) -> int:
        """Calculate optimal width for a class box."""
        min_width = 30
        name_width = len(node.label) + 6
        
        attr_width = max([len(a) for a in node.attributes] + [0]) + 4
        method_width = max([len(m) for m in node.methods] + [0]) + 4
        
        return max(min_width, name_width, attr_width, method_width)
    
    # Create a UML-style class box
    def create_class_box(node: Node) -> list:
        """Create a UML-style class box with proper formatting."""
        width = calculate_box_width(node)
        box = []
        
        # Top border with double line for class name section
        box.append("╔" + "═" * (width - 2) + "╗")
        
        # Class name (centered and prominent)
        class_name = node.label
        name_padding = (width - 2 - len(class_name)) // 2
        name_line = "║" + " " * name_padding + class_name + " " * (width - 2 - name_padding - len(class_name)) + "║"
        box.append(name_line)
        
        # Separator between class name and attributes
        box.append("╠" + "═" * (width - 2) + "╣")
        
        # Attributes section
        if node.attributes:
            for attr in node.attributes:
                attr_line = "║ " + attr.ljust(width - 4) + " ║"
                box.append(attr_line)
        else:
            box.append("║" + " " * (width - 2) + "║")
        
        # Separator between attributes and methods
        box.append("╟" + "─" * (width - 2) + "╢")
        
        # Methods section
        if node.methods:
            for method in node.methods:
                method_line = "║ " + method.ljust(width - 4) + " ║"
                box.append(method_line)
        else:
            box.append("║" + " " * (width - 2) + "║")
        
        # Bottom border
        box.append("╚" + "═" * (width - 2) + "╝")
        
        return box
    
    # Build class boxes
    class_boxes = []
    max_box_width = 0
    
    for node in graph.nodes:
        box_lines = create_class_box(node)
        box_width = len(box_lines[0])
        max_box_width = max(max_box_width, box_width)
        class_boxes.append((node.id, node.label, box_lines, box_width))
    
    # Determine layout: side-by-side or stacked
    max_classes_per_row = 3
    
    if len(class_boxes) <= max_classes_per_row:
        # Render side by side
        lines_per_box = len(class_boxes[0][2]) if class_boxes else 0
        
        for line_idx in range(lines_per_box):
            line_parts = []
            for _, _, box_lines, box_width in class_boxes:
                if line_idx < len(box_lines):
                    # Pad to max width for alignment
                    padded_line = box_lines[line_idx].ljust(max_box_width)
                    line_parts.append(padded_line)
                else:
                    line_parts.append(" " * max_box_width)
            
            output.append("    ".join(line_parts))
    else:
        # Stack vertically with better spacing
        for idx, (_, class_name, box_lines, _) in enumerate(class_boxes):
            if idx > 0:
                output.append("")  # Spacing between classes
            
            for line in box_lines:
                output.append(line)
    
    # Enhanced relationships section
    if graph.edges:
        output.append("")
        output.append("")
        output.append("═" * 60)
        output.append("RELATIONSHIPS")
        output.append("═" * 60)
        output.append("")
        
        # Group relationships by type
        inheritance_edges = []
        composition_edges = []
        association_edges = []
        
        for e in graph.edges:
            if e.label:
                label_lower = e.label.lower()
                if any(keyword in label_lower for keyword in ["extends", "inherits", "inheritance"]):
                    inheritance_edges.append(e)
                elif any(keyword in label_lower for keyword in ["has", "contains", "composition", "owns"]):
                    composition_edges.append(e)
                else:
                    association_edges.append(e)
            else:
                association_edges.append(e)
        
        # Render inheritance relationships
        if inheritance_edges:
            output.append("  Inheritance:")
            output.append("")
            for e in inheritance_edges:
                src_label = label_map.get(e.source, e.source)
                tgt_label = label_map.get(e.target, e.target)
                rel_label = e.label if e.label else "extends"
                
                # UML inheritance arrow: ◁───
                output.append(f"    {src_label}")
                output.append(f"         │")
                output.append(f"         │ {rel_label}")
                output.append(f"         ▽")
                output.append(f"    {tgt_label}")
                output.append("")
        
        # Render composition relationships
        if composition_edges:
            if inheritance_edges:
                output.append("")
            output.append("  Composition:")
            output.append("")
            for e in composition_edges:
                src_label = label_map.get(e.source, e.source)
                tgt_label = label_map.get(e.target, e.target)
                rel_label = e.label if e.label else "contains"
                
                # UML composition: ◆───
                output.append(f"    {src_label}  ◆─────({rel_label})─────>  {tgt_label}")
                output.append("")
        
        # Render association relationships
        if association_edges:
            if inheritance_edges or composition_edges:
                output.append("")
            output.append("  Associations:")
            output.append("")
            for e in association_edges:
                src_label = label_map.get(e.source, e.source)
                tgt_label = label_map.get(e.target, e.target)
                rel_label = e.label if e.label else "uses"
                
                # UML association: ───>
                output.append(f"    {src_label}  ─────({rel_label})─────>  {tgt_label}")
                output.append("")
    
    return "\n".join(output)


def render_ascii_diagram(graph_spec_json: Dict) -> str:
    """Main function to render Graph-Spec JSON as ASCII diagram."""
    try:
        graph = graph_from_json(graph_spec_json)
        diagram_type = graph.diagram_type.lower()
        
        if diagram_type in ["flow", "flowchart", "graph"]:
            return render_ascii_flow(graph)
        elif diagram_type in ["sequence", "sequencediagram"]:
            return render_ascii_sequence(graph)
        elif diagram_type in ["class", "classdiagram"]:
            return render_ascii_class(graph)
        else:
            # Default to flow
            return render_ascii_flow(graph)
    except Exception as e:
        logger.error(f"Error rendering ASCII diagram: {e}")
        return ""


def render_mermaid_flow(graph: Graph) -> str:
    """Render Graph-Spec as Mermaid flowchart."""
    lines = ["graph TD"]
    
    # Add nodes with labels
    # Mermaid syntax: id["label"]
    for node in graph.nodes:
        # Escape quotes in label
        safe_label = node.label.replace('"', '&quot;')
        lines.append(f'    {node.id}["{safe_label}"]')
    
    # Add edges
    # Mermaid syntax: id1 -->|label| id2
    for edge in graph.edges:
        if edge.label:
            safe_label = edge.label.replace('"', '&quot;')
            lines.append(f'    {edge.source} -->|"{safe_label}"| {edge.target}')
        else:
            lines.append(f'    {edge.source} --> {edge.target}')
            
    return "\n".join(lines)


def render_mermaid_sequence(graph: Graph) -> str:
    """Render Graph-Spec as Mermaid sequence diagram."""
    lines = ["sequenceDiagram"]
    lines.append("    autonumber")
    
    # Add participants to ensure order (optional but good for control)
    # Graph-Spec for sequence usually implies order by edge appearance, 
    # but let's just let Mermaid handle it or define if needed.
    # For now, we'll just define participants if we want specific labels.
    for node in graph.nodes:
        safe_label = node.label.replace('"', '&quot;')
        lines.append(f'    participant {node.id} as {safe_label}')
        
    for edge in graph.edges:
        # Sequence edges: source->>target: label
        safe_label = edge.label.replace('"', '&quot;') if edge.label else ""
        lines.append(f'    {edge.source}->>{edge.target}: {safe_label}')
        
    return "\n".join(lines)


def render_mermaid_class(graph: Graph) -> str:
    """Render Graph-Spec as Mermaid class diagram."""
    lines = ["classDiagram"]
    
    for node in graph.nodes:
        safe_label = node.label.replace('"', '&quot;')
        # Use class ID and add members if present
        lines.append(f'    class {node.id}["{safe_label}"]')
        
        if node.attributes or node.methods:
            lines.append(f'    class {node.id} {{')
            for attr in node.attributes:
                lines.append(f'        +{attr}')
            for method in node.methods:
                lines.append(f'        +{method}')
            lines.append('    }')
        
    for edge in graph.edges:
        # Class relationships: ID1 <|-- ID2 (Inheritance) or ID1 --> ID2 (Association)
        # Graph-Spec is generic, so we'll default to association `-->`
        # unless label suggests otherwise.
        rel = "-->"
        if edge.label:
            lbl = edge.label.lower()
            if "extends" in lbl or "inherits" in lbl:
                rel = "<|--"
            elif "implements" in lbl:
                rel = "<|.."
            elif "has" in lbl or "contains" in lbl:
                rel = "*--"
        
        safe_label = f' : {edge.label}' if edge.label else ""
        lines.append(f'    {edge.source} {rel} {edge.target}{safe_label}')
        
    return "\n".join(lines)


def render_mermaid_diagram(graph_spec_json: Dict) -> str:
    """Main function to render Graph-Spec JSON as Mermaid diagram."""
    try:
        graph = graph_from_json(graph_spec_json)
        diagram_type = graph.diagram_type.lower()
        
        if diagram_type in ["flow", "flowchart", "graph"]:
            return render_mermaid_flow(graph)
        elif diagram_type in ["sequence", "sequencediagram"]:
            return render_mermaid_sequence(graph)
        elif diagram_type in ["class", "classdiagram"]:
            return render_mermaid_class(graph)
        else:
            return render_mermaid_flow(graph)
    except Exception as e:
        logger.error(f"Error rendering Mermaid diagram: {e}")
        return ""


def extract_graph_spec_body(markdown: str) -> Dict:
    """Extract Graph-Spec JSON from markdown code block."""
    if not markdown:
        return {}
    
    # Try to find JSON in code block (```json ... ```)
    match = GRAPH_SPEC_PATTERN.search(markdown)
    if match:
        try:
            json_str = match.group(1).strip()
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from code block: {e}")
    
    # Try to find JSON object in the text (look for { ... })
    json_obj_pattern = re.compile(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', re.DOTALL)
    json_match = json_obj_pattern.search(markdown)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON object from text: {e}")
    
    # Try to parse entire markdown as raw JSON
    try:
        return json.loads(markdown.strip())
    except json.JSONDecodeError:
        pass
    
    logger.warning(f"No JSON object found in text. Raw text preview: {markdown[:200] if markdown else 'None'}")
    return {}


def extract_mermaid_body(markdown: str) -> str:
    if not markdown:
        return ""
    match = MERMAID_FENCE_PATTERN.search(markdown)
    if match:
        return match.group(1).strip()
    return markdown.strip()


def sanitize_mermaid_diagram(markdown: str) -> str:
    """
    Best-effort sanitizer for Mermaid diagrams embedded in Markdown bound for GitHub.

    - Ensures fenced code block with "```mermaid" ... "```" exists around the diagram.
    - Normalizes diagram header to a supported form (graph/flowchart/sequenceDiagram/classDiagram).
    - Adds a default direction (TD) for graph/flowchart when missing or invalid.
    - Strips invisible control characters and non-ASCII punctuation that commonly break parsing.
    - Normalizes identifiers to be Mermaid-safe in simple edge statements (id -> id[label]).
    - Fixes invalid mixed-shape syntax like I[{"label"}] → I["label"].
    """

    if not isinstance(markdown, str) or not markdown.strip():
        return markdown

    text = markdown.replace("\r\n", "\n").replace("\r", "\n")

    # Remove invisible control chars that can break code fences or Mermaid parsing
    text = re.sub(r"[\u0000-\u001F\u007F]", "", text)

    # Try to find an existing mermaid block
    fence_pattern = re.compile(
        r"```\s*mermaid\s*\n(.*?)\n```",
        re.IGNORECASE | re.DOTALL,
    )
    match = fence_pattern.search(text)

    if match:
        diagram = match.group(1)
    else:
        # Heuristically detect a Mermaid body
        body_candidates = [
            r"(^|\n)\s*flowchart(?!\w)",
            r"(^|\n)\s*graph(?!\w)",
            r"(^|\n)\s*sequenceDiagram(?!\w)",
            r"(^|\n)\s*classDiagram(?!\w)",
        ]
        if any(re.search(p, text, re.IGNORECASE) for p in body_candidates):
            diagram = text.strip()
            text = ""
        else:
            return markdown

    diagram = diagram.strip("\n")

    # Normalize header
    lines = [ln.rstrip() for ln in diagram.split("\n")]
    if not lines:
        return markdown

    header = lines[0].strip()
    normalized_header = header

    # Normalize header direction
    header_lower = header.lower()
    if header_lower.startswith("flowchart"):
        parts = header.split()
        direction = parts[1] if len(parts) > 1 else "TD"
        if direction.upper() not in {"TD", "TB", "LR", "RL", "BT"}:
            direction = "TD"
        normalized_header = f"flowchart {direction}"
    elif header_lower.startswith("graph"):
        parts = header.split()
        direction = parts[1] if len(parts) > 1 else "TD"
        if direction.upper() not in {"TD", "TB", "LR", "RL", "BT"}:
            direction = "TD"
        normalized_header = f"graph {direction}"
    elif header_lower.startswith("sequencediagram"):
        normalized_header = "sequenceDiagram"
    elif header_lower.startswith("classdiagram"):
        normalized_header = "classDiagram"

    if normalized_header != header:
        lines[0] = normalized_header

    # Sanitize flowchart/graph edge lines
    if normalized_header.startswith(("flowchart", "graph")):
        sanitized_lines: List[str] = []
        edge_pattern = re.compile(
            r"^(\s*)([\w\-:.]+)(\[[^\]]*\])?\s*([-.=]{1,4}>|-->|==>|-\.->|==\|[^|]*\|==>)\s*([\w\-:.]+)(\[[^\]]*\])?(.*)$"
        )
        node_pattern = re.compile(r"^[A-Za-z0-9_:.\-]+$")
        label_with_special_chars = re.compile(r'\[([^\]]*[()"\'<>{}][^\]]*)\]')

        def fix_label_quotes(label: str) -> str:
            """Fix labels with special characters and prevent invalid mixed-shape syntax."""
            if not label:
                return label

            # --- Rectangle node ---
            if label.startswith("[") and label.endswith("]"):
                content = label[1:-1].strip()
                # Remove accidental nested braces like {"..."} → "..."
                if (content.startswith("{") and content.endswith("}")) or (
                    content.startswith("{{") and content.endswith("}}")
                ):
                    content = content.lstrip("{").rstrip("}").strip()

                # Remove redundant quotes
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]

                # Escape internal quotes if needed
                if re.search(r'[()"\'<>{}]', content):
                    content = content.replace('"', '\\"')
                    return f'["{content}"]'
                return f"[{content}]"

            # --- Diamond node ---
            elif label.startswith("{{") and label.endswith("}}"):
                content = label[2:-2].strip()
                # Remove redundant nested braces
                if content.startswith("{") and content.endswith("}"):
                    content = content[1:-1].strip()
                if content.startswith('"') and content.endswith('"'):
                    content = content[1:-1]
                if re.search(r'[()"\'<>]', content):
                    content = content.replace('"', '\\"')
                    return f'{{{{"{content}"}}}}'
                return f"{{{{{content}}}}}"

            return label

        for ln in lines:
            m = edge_pattern.match(ln)
            if not m:
                # Fix loose labels with special chars
                if "[" in ln and "]" in ln:
                    fixed_line = label_with_special_chars.sub(
                        lambda match: fix_label_quotes(match.group(0)), ln
                    )
                    sanitized_lines.append(fixed_line)
                else:
                    sanitized_lines.append(ln)
                continue

            indent, left_id, left_label, arrow, right_id, right_label, tail = m.groups()

            def make_safe(node_id: str) -> str:
                safe = re.sub(r"[^A-Za-z0-9_:.\-]", "_", node_id)
                if not node_pattern.match(safe):
                    safe = re.sub(r"[^A-Za-z0-9_]", "_", safe)
                return safe

            left_id_safe = make_safe(left_id)
            right_id_safe = make_safe(right_id)
            left_label_fixed = fix_label_quotes(left_label) if left_label else ""
            right_label_fixed = fix_label_quotes(right_label) if right_label else ""

            sanitized_lines.append(
                f"{indent}{left_id_safe}{left_label_fixed} {arrow} {right_id_safe}{right_label_fixed}{tail or ''}"
            )

        lines = sanitized_lines

    # Reassemble sanitized diagram
    diagram = "\n".join(lines).strip("\n")

    fenced = f"```mermaid\n{diagram}\n```"
    if match:
        start, end = match.span()
        sanitized = text[:start] + fenced + text[end:]
    else:
        sanitized = fenced if not text else f"{text.strip()}\n\n{fenced}"

    if not diagram.strip():
        return markdown

    return sanitized
