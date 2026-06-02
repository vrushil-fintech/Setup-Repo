import json
from typing import List

def json_to_md_issue_color_formatted(issue_item: dict, code_language: str = "", characteristic: str = "") -> str:
    """Converts a single issue dictionary into markdown format."""
    code_language = code_language.lower()
    issue_markdown = ""
    issue = issue_item["issue"]
    uid = issue_item["uid"]
    start_line = issue_item.get("start_line", "")
    end_line = issue_item.get("end_line", "")
    issue_code_snippet = issue_item.get("issue_code_snippet", "")
    severity = issue_item["severity"]
    solution = issue_item["solution"]
    solution_code_snippet = issue_item.get("solution_code_snippet", "")
    
    issue_markdown += f"**Severity:** {severity}\n\n"
    issue_markdown += f"**Issue:** {issue}\n\n"
    if characteristic and characteristic != "Comprehensive Power Analysis":
        issue_markdown += f"**Quality Aspect:** {characteristic}\n\n"
    if start_line and end_line:
        issue_markdown += f"**Lines:** ```{start_line}-{end_line}```\n\n"

    if issue_code_snippet:
        issue_markdown += f"```{code_language}\n{issue_code_snippet}\n```\n\n"

    issue_markdown += f"**Solution:** {solution}\n\n"

    if solution_code_snippet:
        issue_markdown += f"```{code_language}\n{solution_code_snippet}\n```\n\n"

    # Add GitHub alert formatting based on severity
    severity_lower = severity.lower()
    if severity_lower == "critical":
        issue_markdown = "> [!CAUTION]\n" + "\n".join(f"> {line}" if line else ">" for line in issue_markdown.rstrip("\n").split("\n")) + "\n\n"
    elif severity_lower == "high":
        issue_markdown = "> [!WARNING]\n" + "\n".join(f"> {line}" if line else ">" for line in issue_markdown.rstrip("\n").split("\n")) + "\n\n"
    
    return issue_markdown

def json_to_md_issue(issue_item: dict, code_language: str = "", characteristic: str = "") -> str:
    """Converts a single issue dictionary into markdown format."""
    code_language = code_language.lower()
    issue_markdown = ""
    issue = issue_item["issue"]
    uid = issue_item["uid"]
    start_line = issue_item.get("start_line", "")
    end_line = issue_item.get("end_line", "")
    issue_code_snippet = issue_item.get("issue_code_snippet", "")
    severity = issue_item["severity"]
    solution = issue_item["solution"]
    solution_code_snippet = issue_item.get("solution_code_snippet", "")
    
    issue_markdown += f"**Issue:** {issue}\n\n"
    if characteristic and characteristic != "Comprehensive Power Analysis":
        issue_markdown += f"**Quality Aspect:** {characteristic}\n\n"
    issue_markdown += f"**Severity:** {severity}\n\n"
    if start_line and end_line:
        issue_markdown += f"**Lines:** ```{start_line}-{end_line}```\n\n"

    if issue_code_snippet:
        issue_markdown += f"```{code_language}\n{issue_code_snippet}\n```\n\n"

    issue_markdown += f"**Solution:** {solution}\n\n"

    if solution_code_snippet:
        issue_markdown += f"```{code_language}\n{solution_code_snippet}\n```\n\n"

    return issue_markdown


def json_to_md_analysis(
    json_list: List[dict | str | None], code_language: str = ""
) -> str:
    """Processes a list of analysis characteristics into markdown format."""
    code_language = code_language.lower()
    analysis_markdown = ""
    for char_el in json_list:
        if char_el:
            char_markdown = ""
            characteristic = char_el["characteristic"]
            description_of_characteristic = char_el["description_of_characteristic"]
            issue_items = char_el.get("issue_items", [])
            char_markdown += f"## {characteristic}\n{description_of_characteristic}\n\n"

            # Separate issues by severity
            high_issues = []
            low_issues = []

            for issue_item in issue_items:
                severity = issue_item.get("severity", "").lower()
                if severity in ("critical", "high"):
                    high_issues.append(issue_item)
                elif severity in ("medium", "low"):
                    low_issues.append(issue_item)

            # Add high/critical severity issues directly
            if high_issues:
                # char_markdown += "> [!IMPORTANT]\n> Check out the below given Critical and High severity Issues.\n\n"
                for issue in high_issues:
                    char_markdown += json_to_md_issue(issue, code_language, characteristic)

            # Add medium/low severity issues inside a dropdown
            if low_issues:
                # char_markdown += "> [!TIP]\n> Additional Suggestions\n\n"
                char_markdown += "<details>\n"
                char_markdown += "<summary>Optional: Medium and Low Severity Issues</summary>\n\n"
                for issue in low_issues:
                    char_markdown += json_to_md_issue(issue, code_language, characteristic)
                char_markdown += "</details>\n\n"

            analysis_markdown += char_markdown

    return analysis_markdown


if __name__ == "__main__":
    with open("review_auth_routes.py.json", "r") as f:
        json_data = json.loads(f.read())

    analysis_markdown = json_to_md_analysis(json_data, "Python")
    with open("review_auth_routes.md", "w") as f:
        f.write(analysis_markdown)
