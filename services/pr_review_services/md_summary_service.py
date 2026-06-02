from collections import defaultdict

async def format_severity_data(severity_data):
    response = "### Issue Count by Severity\n\n"
    response += "| Severity | Count |\n"
    response += "|----------|-------|\n"

    for severity, count in severity_data.items():
        if count == 0:
            continue
        response += f"| {severity.capitalize()} | {count} |\n"

    response += "\n"
    return response

async def format_characteristic_data(file_characteristic_data):
    response = "### Issue Count by Characteristic\n\n"
    response += "| Characteristic | Count |\n"
    response += "|----------------|-------|\n"

    for characteristic, count in file_characteristic_data.items():
        if count == 0:
            continue
        response += f"| {characteristic.capitalize()} | {count} |\n"

    response += "\n"
    return response

async def format_severity_characteristic_data(characteristic_data):
    # Aggregate severity counts
    severity_totals = defaultdict(int)

    # Preprocess to compute severity totals
    for char_data in characteristic_data.values():
        for severity, count in char_data.items():
            severity_totals[severity] += count

    total_issues = sum(severity_totals.values())

    # Start building the markdown
    response = "### 🔍 Issue Breakdown by Severity and Quality Aspect\n\n"
    response += "| Severity | Quality Aspect     | Count |\n"
    response += "|----------|--------------------|-------|\n"

    # Sort for consistency
    for severity in sorted(severity_totals.keys(), key=lambda s: ["Critical", "High", "Medium", "Low"].index(s)):
        related_chars = [
            (char, char_data[severity])
            for char, char_data in characteristic_data.items()
            if severity in char_data and char_data[severity] > 0
        ]

        if related_chars:
            first_char, first_count = related_chars[0]
            response += f"| {severity} | {first_char} | {first_count} |\n"
            for char, count in related_chars[1:]:
                response += f"|          | {char} | {count} |\n"
        else:
            response += f"| {severity} | - | {severity_totals[severity]} |\n"

    response += f"| **Total** | - | **{total_issues}** |\n"
    return response