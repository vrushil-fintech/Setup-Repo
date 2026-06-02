from collections import deque
from difflib import SequenceMatcher
import re

from tree_sitter import Node
from tree_sitter_languages import get_parser

from app.dependencies import logger


def extract_tokens(node, source_code):
    """Recursively extract tokens from AST nodes."""
    tokens = []
    queue = deque([node])

    while queue:
        curr_node = queue.popleft()
        text = (
            source_code[curr_node.start_byte : curr_node.end_byte]
            .decode("utf-8")
            .strip()
        )
        if text:
            tokens.append(text)
        queue.extend(curr_node.children)

    return tokens


def similarity_ratio(seq1, seq2):
    """Compute similarity between two token lists."""
    return SequenceMatcher(None, seq1, seq2).ratio()


def normalize_text(text: str) -> str:
    """Normalize text by removing extra whitespace to improve matching."""
    # Replace multiple spaces with a single space
    text = re.sub(r"\s+", " ", text)
    # Remove spaces around certain operators and punctuation
    text = re.sub(r"\s*(=|\(|\)|\{|\}|;|,|\+|-|\*|\/|:|<|>)\s*", r"\1", text)
    return text.strip()


def serialize_node(node: Node, source_code: bytes) -> str:
    raw_text = source_code[node.start_byte : node.end_byte].decode("utf-8").strip()
    return normalize_text(
        raw_text
    )  # Apply normalization to handle whitespace differences


def match_snippet_in_file(file_code: str, snippet_code: str, language: str):
    try:
        parser = get_parser(language)
    except Exception as e:
        logger.error(f"Parser for language '{language}' could not be loaded: {e}")
        return None

    file_bytes = file_code.encode("utf-8")
    snippet_bytes = snippet_code.encode("utf-8")

    file_tree = parser.parse(file_bytes)
    snippet_tree = parser.parse(snippet_bytes)

    queue = deque([file_tree.root_node])
    snippet_roots = (
        snippet_tree.root_node.children
        if snippet_tree.root_node.children
        else [snippet_tree.root_node]
    )

    # Apply normalization to snippet texts
    snippet_texts = {
        serialize_node(snippet_node, snippet_bytes) for snippet_node in snippet_roots
    }

    start_line, end_line = float("inf"), float("-inf")
    found = False

    while queue:
        node = queue.popleft()
        node_text = serialize_node(node, file_bytes)

        if node_text in snippet_texts:
            found = True
            start_line = min(start_line, node.start_point[0])
            end_line = max(end_line, node.end_point[0])

        for child in node.children:
            queue.append(child)

    if found:
        logger.info(
            f"Snippet matched from line {start_line} to {end_line} in {language} file"
        )
        return {
            "start_line": start_line,
            "end_line": end_line,
            "match_text": snippet_code,  # Returning the original snippet code
        }

    return None  # No match found


def iterate_and_process(json_data, file_code, language):
    for item in json_data:
        for issue_item in item.get("issue_items", []):
            if issue_item.get("issue_code_snippet"):
                code_snippet = issue_item["issue_code_snippet"]

                # Call the function to process the code snippet and get start and end lines
                snippet_info = match_snippet_in_file(file_code, code_snippet, language)

                if snippet_info:
                    # Add start and end line info to the issue item
                    issue_item["start_line"] = snippet_info["start_line"]
                    issue_item["end_line"] = snippet_info["end_line"]
                    issue_item["match_text"] = snippet_info["match_text"]

    return json_data
