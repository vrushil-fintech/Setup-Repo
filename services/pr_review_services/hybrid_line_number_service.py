from difflib import SequenceMatcher
from typing import List

def normalize_line(line: str) -> str:
    return line.expandtabs().strip()


def is_partial_match(snippet_line: str, full_line: str) -> bool:
    if snippet_line == full_line:
        return True
    # Use stripped versions for leading/trailing whitespace
    stripped_snippet = snippet_line.strip()
    stripped_full = full_line.strip()

    # Avoid matching short brackets/braces/etc. unless it's an exact match
    if len(stripped_snippet) <= 2 and stripped_snippet in "{}[]();":
        return False

    # Allow partial match only if it's a full clause inside
    return stripped_snippet in stripped_full


def non_contiguous_match(full_lines: List[str], snippet_lines: List[str]) -> tuple[int | None, int | None]:
    for snippet_search_start_index in range(len(snippet_lines)):
        snippet_index = snippet_search_start_index
        start_line = end_line = None

        for i, full_line in enumerate(full_lines):
            if snippet_index >= len(snippet_lines):
                break
            if is_partial_match(snippet_line=snippet_lines[snippet_index], full_line=full_line):
                if start_line is None:
                    start_line = i + 1
                end_line = i + 1
                snippet_index += 1

        # If we matched at least one snippet line starting from current index
        if snippet_index > snippet_search_start_index:
            return (start_line, end_line)

    return (None, None)

def fuzzy_non_contiguous_match(
    full_lines, snippet_lines, threshold=0.9
) -> tuple[int | None, int | None]:
    snippet_index = 0
    start_line = end_line = None

    for i, full_line in enumerate(full_lines):
        if snippet_index >= len(snippet_lines):
            break

        ratio = SequenceMatcher(None, full_line, snippet_lines[snippet_index]).ratio()
        if ratio >= threshold:
            if snippet_index == 0:
                start_line = i + 1
            end_line = i + 1
            snippet_index += 1

    return (start_line, end_line) if snippet_index > 0 else (None, None)


def hybrid_snippet_match(full_code: str, snippet: str, threshold: float = 0.9) -> int:
    full_lines = [normalize_line(line) for line in full_code.splitlines()]
    snippet_lines = [
        normalize_line(line) for line in snippet.splitlines() if line.strip()
    ]

    # Fast path: exact substring matching
    start_line, end_line = non_contiguous_match(full_lines, snippet_lines)
    if start_line and end_line:
        return (start_line, end_line)

    # Fallback: fuzzy matching
    return fuzzy_non_contiguous_match(full_lines, snippet_lines, threshold)


def char_issues_linenum_ext(json_data: List[dict], file_code: str):
    for item in json_data:
        for issue_item in item.get("issue_items", []):
            if issue_item.get("issue_code_snippet"):
                code_snippet = issue_item["issue_code_snippet"]

                # Call the function to process the code snippet and get start and end lines
                start_line, end_line = hybrid_snippet_match(file_code, code_snippet)

                if start_line and end_line:
                    # Add start and end line info to the issue item
                    issue_item["start_line"] = start_line
                    issue_item["end_line"] = end_line

    return json_data

if __name__ == "__main__":
    file_code = """
codeline1
codeline2
codeline3
codeline4
codeline5
codeline6
"""
    snippet_code = """
# comment
codeline2
codeline4
"""

    print(hybrid_snippet_match(file_code, snippet_code))
