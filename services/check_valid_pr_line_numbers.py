from typing import Dict
from unidiff import PatchSet
from app.dependencies import logger


def validate_comment_line_numbers(raw_patch: str, filename: str, line_comment: Dict):
    try:
        
        patch = f"--- a/{filename}\n+++ b/{filename}\n{raw_patch}"
        patch = PatchSet(patch)

        # Extract all lines from the patch that are part of the new file
        matched = False
        hunk_count = 0
        for file in patch:
            start_line = line_comment["start_line"]
            end_line = line_comment["end_line"]

            for hunk in file:
                hunk_count += 1
                hunk_start = hunk.target_start
                hunk_end = hunk_start + hunk.target_length - 1
                overlap_start = max(hunk_start, start_line)
                overlap_end = min(hunk_end, end_line)
                

                if overlap_start <= overlap_end:
                    matched = True
                    line_comment["start_line"] = overlap_start
                    line_comment["end_line"] = overlap_end
                    print(f"[LINE_NUMBER_VALIDATION] ✓ MATCH FOUND in hunk {hunk_count}! Adjusted to start_line={overlap_start}, end_line={overlap_end}")
                    break
                else:
                    print(f"[LINE_NUMBER_VALIDATION] ✗ No overlap in hunk {hunk_count}")
            
            # Only check if matched after processing all hunks for this file
            if matched:
                break

        # If no match found after checking all files and hunks, mark as invalid
        if not matched:
            line_comment["valid"] = False
            logger.info(
                "Out of range line numbers (start_line=%d, end_line=%d).",
                line_comment.get("start_line"),
                line_comment.get("end_line"),
            )
        else:
            print(f"[LINE_NUMBER_VALIDATION] ✓✓✓ VALIDATION SUCCESSFUL. Final state - start_line: {line_comment.get('start_line')}, end_line: {line_comment.get('end_line')}, valid: {line_comment.get('valid')}")

    except Exception as e:
        import traceback

        logger.error(
            f"Error occured while validating review comment line numbers. {str(e)}"
        )
        # Mark as invalid if validation fails due to exception
        line_comment["valid"] = False


def extract_changed_code_as_string(raw_patch: str, filename: str) -> str:
    patch_text = f"--- a/{filename}\n+++ b/{filename}\n{raw_patch}"
    patch = PatchSet(patch_text)
    code_str_lines = []

    for patched_file in patch:
        for hunk in patched_file:
            for line in hunk:
                if line.is_added or line.is_removed:
                    code_str_lines.append(line.value)

    return "\n".join(code_str_lines)


def clean_raw_patch(raw_patch: str, filename: str) -> str:
    """
    Removes hunks where the only added lines are pure whitespace.
    Keeps whitespace additions if they appear alongside meaningful changes.
    """
    patch_text = f"--- a/{filename}\n+++ b/{filename}\n{raw_patch}"
    patch = PatchSet(patch_text)
    cleaned_lines = []

    for file in patch:
        file_lines = []

        for hunk in file:
            added_lines = [line for line in hunk if line.is_added]
            removed_lines = [line for line in hunk if line.is_removed]
            has_meaningful_additions = any(
                line.value.strip() != "" for line in added_lines
            )

            if not has_meaningful_additions and not any(
                line.is_removed for line in hunk
            ):
                # Skip hunk — it only added blank lines
                continue

            if not has_meaningful_additions and removed_lines:
                continue

            # Keep all lines if hunk has meaningful additions or is a real modification
            hunk_header = f"@@ -{hunk.source_start},{hunk.source_length} +{hunk.target_start},{hunk.target_length} @@"
            file_lines.append(hunk_header)
            for line in hunk:
                file_lines.append(f"{line.line_type}{line.value.rstrip()}")

        if file_lines:
            cleaned_lines.extend(file_lines)

    return "\n".join(cleaned_lines)


if __name__ == "__main__":
    sample_patch = """\
diff --git a/7195-EventDBHandler.cs b/7195-EventDBHandler.cs
new file mode 100644
index 0000000..e78fbc4
--- /dev/null
+++ b/7195-EventDBHandler.cs
@@ -0,0 +1,8 @@
+using CAAPS.Enums;
+using CAAPS.Swift.MT564;
+using CAAPS.SwiftDbHandler;
+using Caaps_Models.Display;
+using Caaps_Models.Notifications;
+using CaapsWebServer.AccessLayer.Implementation;
+using CaapsWebServer.AccessLayer.Interfaces;
+using CaapsWebServer.Config;
"""
    filename = "temp.py"
    line_comments = [
        {
            "start_line": 2,
            "end_line": 5,
        }
    ]

    cleaned_patch = validate_comment_line_numbers(sample_patch, filename, line_comments)
    print(cleaned_patch)
