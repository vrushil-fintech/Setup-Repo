from datetime import datetime
import json
import re
from markdown_it import MarkdownIt
from app.dependencies import SEVERITY_MAP, logger
 
def check_description_and_snippet(md_content, issue_data):
    if ((issue_data["issue"]=="" and issue_data["issue_code_snippet"]=="")
        or  (issue_data["solution"]=="" and issue_data["solution_code_snippet"]=="")):
        logger.warning(f"No description and code snippet found. Markdown: {md_content}")
        return False
    else:
        return True
    
def is_valid_uid(uid_text):
    return re.match(r"^(?:[A-Z]{3}(?:_\d+)?-\d{3})(\.?)$", uid_text) is not None

 
def md_to_json(md_content, file_name, factor):
    try:
        # Write markdown content to file
        # file_path = f"./temp_{file_name}_{factor}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.md"
        # with open(file_path, "w") as f:
        #     f.write(md_content)

        md = MarkdownIt()
        tokens = md.parse(md_content)
        json_output = {"analysis": []}
        characteristic_data = None
        issue_data = None
        level = None  # Initialize level to avoid reference issues
 
        last_h3_type = None  # Initialize outside the loop
 
        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                level = int(token.tag[1])  # Extract heading level (h1, h2, etc.)
 
            elif token.type == "inline":
                text = token.content.strip()
 
                if level == 1:
                    if characteristic_data:
                        if issue_data and check_description_and_snippet(md_content, issue_data):
                            characteristic_data["issue_items"].append(issue_data)
                        json_output["analysis"].append(characteristic_data)
                        issue_data = None
 
                    characteristic_data = {
                        "characteristic": text,
                        "description_of_characteristic": "",
                        "issue_items": []
                    }
 
                elif level == 2 and characteristic_data:
                    if not characteristic_data["description_of_characteristic"]:
                        characteristic_data["description_of_characteristic"] = text
 
                elif level == 3 and characteristic_data:
                    if text.lower().startswith("issue:"):
                        if issue_data and check_description_and_snippet(md_content, issue_data):
                            characteristic_data["issue_items"].append(issue_data)
 
                        issue_data = {
                            "issue": text.replace("Issue:", "").strip(),
                            "uid": "",
                            "issue_code_snippet": "",
                            "severity": "",
                            "severity_level": 1,
                            "solution": "",
                            "solution_code_snippet": ""
                        }
                        last_h3_type = "issue"  # Track last h3 type
 
                    elif is_valid_uid(text) and issue_data:
                        issue_data["uid"] = text.strip()
 
                    elif text.lower().startswith("severity:") and issue_data:
                        severity_text = text.replace("Severity:", "").strip()
                        severity_level = SEVERITY_MAP.get(severity_text.lower(), 1)
 
                        issue_data["severity"] = severity_text
                        issue_data["severity_level"] = severity_level
 
                    elif text.lower().startswith("solution:") and issue_data:
                        issue_data["solution"] = text.replace("Solution:", "").strip()
                        last_h3_type = "solution"  # Track last h3 type
 
            elif token.type == "paragraph_open" and i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                next_text = tokens[i + 1].content.strip()
 
                if last_h3_type == "issue" and issue_data and not issue_data["issue"]:
                    issue_data["issue"] = next_text  # Capture issue description
 
                elif last_h3_type == "solution" and issue_data and not issue_data["solution"]:
                    issue_data["solution"] = next_text  # Capture solution description
 
            elif token.type == "fence" and issue_data:  # Code Block
                if issue_data["solution"]:
                    issue_data["solution_code_snippet"] = token.content.strip()
                else:
                    issue_data["issue_code_snippet"] = token.content.strip()
 
        # Finalizing last characteristic
        if characteristic_data:
            if issue_data and check_description_and_snippet(md_content, issue_data):
                characteristic_data["issue_items"].append(issue_data)
            json_output["analysis"].append(characteristic_data)
 
        if json_output["analysis"]:
            if json_output["analysis"][0]["issue_items"]:
                json_output = sort_issue_items(json_output)
                return json_output["analysis"]
 
        logger.error(f"Empty json output.\n Markdown: {md_content}")
        return {}  # Return an empty dictionary if no data was parsed
 
    except Exception as e:
        logger.error(f"Error in md_to_json: {e}", extra={"markdown_text": md_content})
        return None  # Indicate failure

def sort_issue_items(json_output):
    for characteristic_data in json_output["analysis"]:
        if characteristic_data["issue_items"]:
            characteristic_data["issue_items"].sort(key=lambda x: x["severity_level"], reverse=True)

    return json_output

if __name__ == "__main__":
    file_path = "test.md"
    with open(file_path, "r") as f:
        md_content = f.read()
 
    json_output = md_to_json(md_content, "temp", "factor")
    print("here")
    print(json.dumps(json_output, indent=4))