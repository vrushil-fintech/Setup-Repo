import copy
from typing import Any, Dict, List, Optional, Union
from app.config import MIN_ISSUE_LIMIT
from app.services.data import (
    Factors,
    char_factor_map,
    OWASP_GROUPS,
    CWE_GROUPS,
    IMPACT_DUMMY_EXAMPLE,
)
from app.dependencies import logger
import json
from app.services.diagram_examples import DIAGRAM_EXAMPLES


class PromptService:
    def __init__(self):
        """
        Initialize the service with predefined prompts.
        """
        self.prompts = {
            "factor_analysis_prompt": self._factor_analysis_prompt,
            "applicability_check_prompt": self._applicability_check_prompt,
            "applicability_check_small_prompt": self._applicability_check_small_prompt,
            "applicability_check_prompt_cwe_soc2": self._applicability_check_prompt_cwe_soc2,
            "md_to_json_prompt": self._md_to_json_prompt,
            "power_analysis_prompt": self._power_analysis_prompt,
            "power_analysis_small_prompt": self._power_analysis_small_prompt,
            "owasp_analysis_prompt": self._owasp_analysis_prompt,
            "generate_pr_summary": self.generate_pr_summary,
            "generate_pr_diagram": self.generate_pr_diagram,
            "cwe_analysis_prompt": self._cwe_analysis_prompt,
            "applicability_check_prompt_additional_instructions": self._applicability_check_prompt_additional_instructions,
            "impact_based_characteristic_prompt": self._impact_based_characteristic_prompt,
            "identify_missing_dependencies_prompt": self._identify_missing_dependencies_prompt,
        }

    async def get_prompt(
        self, prompt_name: str, **kwargs: Any
    ) -> Union[str, Dict[str, str]]:
        """
        Retrieve a prompt by its name and process it with parameters if required.

        :param prompt_name: The name of the prompt to retrieve.
        :param kwargs: Parameters for the prompt, if applicable.
        :return: The processed prompt, which could be a string or a list of strings.
        """
        if prompt_name not in self.prompts:
            raise Exception(f"Prompt '{prompt_name}' does not exist.")

        # Call the appropriate prompt handler
        return await self.prompts[prompt_name](**kwargs)

    async def _impact_based_characteristic_prompt(
        self, factor_name: str, pr_summary: str
    ) -> str:
        """
        Return a prompt that asks the model to CREATE a new characteristic based on the PR Impact.
        The characteristic should cover issues described in the Impact that are NOT already covered
        by existing characteristics. If the characteristic already exists or no new one is needed, return NONE.
        """

        char_objects = Factors[factor_name]
        all_characteristic_names = [obj["characteristic"] for obj in char_objects]

        return f"""
You are creating a new analysis characteristic based on a PR's Impact description.

Instructions:
- Read the PR Summary below, focusing on the "Impact" section.
- Analyze what issues or concerns are described in the Impact.
- If the Impact describes positive changes (improvements, hardening, fixes, reduced risk, better performance) with no new risks/regressions, return 'NONE'.
- Only CREATE a characteristic when the Impact indicates negative impact, regressions, or introduces a new risk not covered by existing characteristics.
- Create a NEW characteristic that covers issues NOT already addressed by existing characteristics.
- If the characteristic you want to create already exists in the list below, or if all issues are already covered, return 'NONE'.

Existing Characteristics (do not create duplicates):
{', '.join(all_characteristic_names)}

PR Summary:
{pr_summary}

Output Format:
If creating a new characteristic, return JSON (no backticks):
{{
    "characteristic": "<Name of the new characteristic>",
    "description": "<Detailed description of what this characteristic analyzes>",
    "abbreviation": "<3-letter abbreviation>",
    "weight": 1
}}

If no new characteristic is needed, return only:
NONE

Output Rules (STRICT):
- Return valid JSON with all required fields if creating a new characteristic.
- Return only the word 'NONE' (no quotes, no JSON) if no new characteristic is needed.
- The characteristic name must be DIFFERENT from all existing characteristics listed above.
- Do NOT include any example field or examples in the output.
"""

    async def _applicability_check_prompt_additional_instructions(
        self, code: str, additional_instructions: list[str]
    ) -> str:
        """
        Return an applicability check prompt for additional user instructions.
        :param code: Code to be analyzed.
        :param instructions: List of additional user instructions (strings).
        :return: A formatted applicability check prompt for the LLM.
        """
        instr_lines = [f"- {i.strip()}" for i in additional_instructions if i.strip()]
        instrs = "\n".join(instr_lines)

        return f"""
I am performing a code analysis on a given code file using a set of user-defined instructions. 
Before proceeding with the analysis, please determine the programming language of the code file. 
Once the language has been identified, assess whether each instruction is applicable to the code. 
If applicable, determine whether the code requires changes to meet the instruction.

For each instruction:
- Indicate if it is applicable (i.e., relevant for evaluating this code).
- Indicate if it requires changes (i.e., if the code currently violates the instruction).
- Provide a reason for your decision for each field.

Code:
{code}

User-Defined Instructions:
{instrs}

Output Format: Please provide the output in the following JSON format without backticks:
{{
    "language": "<Identified programming language>",
    "instructions": [
        {{
            "instruction": "<Instruction 1>",
            "applicable": <true/false>,
            "require_changes": <true/false>,
            "reason": "<Explanation for why the instruction is applicable or not and why changes are or aren't needed>"
        }},
        {{
            "instruction": "<Instruction 2>",
            "applicable": <true/false>,
            "require_changes": <true/false>,
            "reason": "<Explanation>"
        }},
        ...
    ]
}}
"""

    async def _applicability_check_prompt(
        self, code: str, factor: str = None, local_factors: dict = None
    ) -> str:
        """
        Return the applicability check prompt.
        :param code: Code to be analyzed.
        :param factor: The factor of analysis. A valid factor must exist in the Factors mapping.
        :param local_factors: Optional local copy of Factors (used when impact-based characteristics are added).
        :raises ValueError: If the provided factor does not exist in the Factors mapping.
        :return: A formatted applicability check prompt.
        """
        # Use local_factors if provided, otherwise use global Factors
        factors_to_use = local_factors if local_factors is not None else Factors

        # Validate that factor is a string
        if not isinstance(factor, str):
            raise ValueError(f"Factor must be a string, got {type(factor)}")

        # Check if factor exists in the factors mapping
        if factor not in factors_to_use:
            raise ValueError(f"Factor '{factor}' is not defined in Factors mapping.")

        char_objects = factors_to_use[factor]
        char_lines = [
            f"- {obj['characteristic']} ({obj['description']})" for obj in char_objects
        ]
        chars = "\n".join(char_lines) + "\n"
        # if (
        #         isinstance(additional_instructions, str)
        #         and additional_instructions.strip()
        #     ):
        #     chars += f"- Additional User Instructions: {additional_instructions}\n"

        return f"""
I am performing code analysis on a given code file using a set of characteristics on the aspect of {factor}. Before proceeding with the characteristic analysis, please determine the programming language of the code file. Once the language has been identified, assess whether each characteristic is applicable to the code, and if applicable, determine whether it requires changes.

For each characteristic:
- Indicate if it is applicable (i.e., if the characteristic is relevant for evaluating the given code).
- Indicate if it requires changes (i.e., if modifications are needed in the code to address the characteristic).
- Provide a reason for your decision for each field.

Code:
{code}

Characteristics:
{chars}

Output Format: Please provide the output in the following JSON format without backticks:
{{
    "language": "<Identified programming language>",
    "characteristics": [
        {{
            "name": "<Characteristic 1>",
            "applicable": <true/false>,
            "require_changes": <true/false>,
            "reason": "<Explanation for why the characteristic is applicable or not and why changes are or aren't needed>"
        }},
        {{
            "name": "<Characteristic 2>",
            "applicable": <true/false>,
            "require_changes": <true/false>,
            "reason": "<Explanation for why the characteristic is applicable or not and why changes are or aren't needed>"
        }},
        ...
    ]
}}
"""

    async def _applicability_check_prompt_cwe_soc2(self, code: str, factor: str) -> str:
        if factor not in Factors:
            raise ValueError(f"Factor '{factor}' is not defined in Factors mapping.")
        char_objects = Factors[factor]
        char_lines = [
            f"- {obj['characteristic']} ({obj['description']})" for obj in char_objects
        ]
        chars = "\n".join(char_lines) + "\n"

        return f"""
    You are analyzing source code for vulnerabilities.

    ⚠️ Rules:
    - Consider ONLY given characteristics.
    - A characteristic is applicable only if the risky pattern is directly visible in the provided code snippet itself.
    - Do NOT assume or speculate about how the code might be used elsewhere.
    - Do NOT suggest mitigations that require assumptions about the broader system unless they are explicitly handled in the snippet.
    - If a violation is clearly present, mark "applicable": true and "require_changes": true.
    - If no violation is directly visible, mark "applicable": false and "require_changes": false.
    - Never recommend generic fixes if the snippet does not deal with that given characteristic.

    Steps:
    1. Identify the programming language of the code.
    2. For each  characteristic:
    - Set `applicable: true` ONLY if the pattern appears in this code.
    - Set `require_changes: true` ONLY if a change is required to fix the violation.
    - Always provide a concise reason tied strictly to the snippet.

    Code under review:
    {code}

    Characteristics to check:
    {chars}

    🚨 Output Rules (STRICT):
    - Output MUST be a **single valid JSON object only**.
    - Do not include explanations, notes, markdown, or text outside the JSON.
    - Do not include trailing commas.
    - Commas must always appear at the end of a line, never at the beginning of a line.
    - If uncertain, return empty string values but keep JSON valid.
    - Escape quotes inside JSON strings if needed.

    Output Format (JSON, no backticks):
    {{
        "language": "<Identified programming language>",
        "characteristics": [
            {{
                "name": "<Characteristic 1>",
                "applicable": <true/false>,
                "require_changes": <true/false>,
                "reason": "<Strictly based on visible code. No assumptions.>"
            }},
            {{
                "name": "<Characteristic 2>",
                "applicable": <true/false>,
                "require_changes": <true/false>,
                "reason": "<Strictly based on visible code. No assumptions.>"
            }},
            ...
        ]
    }}
    """

    async def _applicability_check_small_prompt(self, code: str, factor: str) -> str:
        """
        Return the applicability check prompt.
        :param code: Code to be analyzed.
        :param factor: The factor of analysis.
        :return: A formatted applicability check prompt.
        """

        return f"""
I am performing code analysis on a given code file. Before proceeding with any further analysis, please determine the **programming language** of the code.

**Code:**
{code}

**Output Format:** Please provide the output in the following JSON format without backticks:
{{
    "language": "<Identified programming language>"
}}
"""

    async def _md_to_json_prompt(self, md: str) -> str:
        return f"""
Below is a markdown structured in the format:
- # Name of characteristic
- A concise explanation of the characteristic.

List of Issues in the format:
- Issue: (Description of the identified issue.)
- Identifier for Issue (an abbreviation).
- Severity: ([Critical, High, Medium, Low])
- (The code snippet where the issue is found)
- Solution: (Description of the solution.)
- (Improved code snippet that resolves the issue.)

You need to convert this markdown into structured JSON output as given below:
```json
{{
  "characteristic": "string",  // just write the name of the characteristic.
  "description_of_characteristic": "string", // concise explanation of the characteristic.
  "issue_items": [
    {{
      "id": "string",  // Unique identifier for the issue (the abbreviation).
      "issue": "string",  // description of the identified issue.
      "issue_code_snippet": "string",  // the code snippet where the issue is found, formatted with proper indentation and line breaks.
      "severity": "string",  // The severity of the issue. choose from: [Critical, High, Medium, or Low].
      "solution": "string",  // Description of the solution.
      "solution_code_snippet": "string"  // The improved code snippet that resolves the issue, formatted with proper indentation and line breaks.
    }}
  ]
}}

Markdown:
{md}
"""

    async def _factor_analysis_prompt(
        self, factor_name: str, applicable_chars: List[str] = None
    ) -> Dict[str, str]:
        """
        Generate an array of prompts for the factor.

        :param factor_name: The name of the factor.
        :param applicable_chars: Characteristics to filter.
        :return: A dictionary of prompts keyed by characteristic.
        """
        prompt_dict = {}
        char_objects = Factors[factor_name]

        if applicable_chars:
            filtered_char_objects = [
                obj for obj in char_objects if obj["characteristic"] in applicable_chars
            ]
        else:
            filtered_char_objects = char_objects

        results = await self._process_factors(factor_name, filtered_char_objects)

        for characteristic, prompt in results:
            prompt_dict[characteristic] = prompt

        return prompt_dict

    async def _process_factors(
        self, factor_name: str, char_objects: List[Dict[str, Any]]
    ) -> List[tuple]:
        """
        Process a list of factors to generate prompts.

        :param factor_name: The name of the factor.
        :param char_objects: A list of factor objects to process.
        :return: A list of tuples containing characteristic names and their corresponding prompt templates.
        """
        results = []
        for obj in char_objects:
            characteristic = obj["characteristic"]
            description = obj["description"]
            abbreviation = obj["abbreviation"]
            example = obj["example"]

            # Generate the prompt for each factor object
            prompt_template = f"""
Consider yourself a senior software engineer. Perform a code analysis on the given code, focusing on {characteristic}.
{description}

CRITICAL POINT : Every identified Issue must follow the structure below in attached example only. Do not skip, or omit any part.

1. Thorough Examination: Before presenting the analysis, examine the entire code carefully. Take your time to understand the context and functionality.

2. Relevant Issues Only: Identify issues strictly related to {characteristic} that have a real impact on the code's quality or functionality.

3. No Forced Issues: Avoid creating issues that do not exist. Give code examples from existing code instead of generic examples from outside the given code set.

4. Detailed Solutions: For each identified issue, provide a clear and detailed solution with code snippets. Ensure that the solution code snippet is an improved version that resolves the identified issue and is not a repetition of the original code snippet.

5. Sequential Numbering: For each issue, create an alphanumeric number starting with the first three letters of {characteristic} and append to that a number with a hyphen, starting from 100 and increasing sequentially for each issue. Numbering should start from a new line.

6. Plain Text Response: Only apply the H2, H3 tags for the response. Dont't forget to add the hashes for H2 H3.

## Format of output:

## A concise explanation of what {characteristic} is and its significance in software {factor_name}.
### Issue: (Description of the identified issue.)
### {abbreviation} (or the appropriate numbering).
### Severity: (judge the severity of issue: [Critical, High, Medium, Low].)
(The code snippet where the issue is found)
### Solution: (description of the solution.)
(If applicable, provide an improved code snippet that resolves the issue.)

## Examples
{example}

[Note: Please follow the example format given consistently. This example is provided to illustrate the expected format only.]
"""
            results.append((characteristic, prompt_template))
        return results

    async def _power_analysis_prompt(
        self,
        factor_name: str,
        context: str,
        applicable_chars: List[str] = None,
        additional_instructions: str = None,
        impact_based_characteristic: Dict[str, Any] = None,
        pr_summary=None,
    ) -> Dict[str, str]:
        """
        Generate an array of prompts for the power analysis.

        :param factor_name: The name of the factor.
        :param applicable_chars: Characteristics to filter (may include impact-based characteristic).
        :param impact_based_characteristic: Impact-based characteristic object (if created at PR level).
        :return: A dictionary of prompts keyed by characteristic.
        """
        prompt_dict = {}
        try:
            char_objects = Factors[factor_name]

            if applicable_chars is not None:
                filtered_char_objects = [
                    obj
                    for obj in char_objects
                    if obj["characteristic"] in applicable_chars
                ]
                # If impact-based characteristic is in applicable_chars but not in Factors, add it
                if impact_based_characteristic and isinstance(
                    impact_based_characteristic, dict
                ):
                    impact_char_name = impact_based_characteristic.get(
                        "characteristic", ""
                    )
                    if impact_char_name in applicable_chars:
                        # Check if it's already in filtered_char_objects
                        if not any(
                            obj.get("characteristic") == impact_char_name
                            for obj in filtered_char_objects
                        ):
                            filtered_char_objects.append(impact_based_characteristic)
            else:
                filtered_char_objects = copy.deepcopy(Factors[factor_name])

            results = await self._process_power_analysis_factor(
                factor_name, context, filtered_char_objects, pr_summary
            )

            for characteristic, prompt in results:
                prompt_dict[characteristic] = prompt

            # add a check if additional instructions has spaces
            if (
                isinstance(additional_instructions, str)
                and additional_instructions.strip()
            ):
                additional_char_obj = await self._create_custom_characteristic(
                    user_instructions=additional_instructions
                )
                additional_characteristic, prompt = (
                    await self._create_custom_characteristic_prompt(
                        custom_char_object=additional_char_obj, context=context
                    )
                )
                prompt_dict[additional_characteristic] = prompt

            return prompt_dict

        except Exception as e:
            # Handle any unexpected errors
            logger.error(f"Unexpected error in _power_analysis_prompt: {str(e)}")
            return {}

    async def _create_custom_characteristic(self, user_instructions: str):
        return {
            "characteristic": "Additional User Instructions",
            "description": user_instructions,
            "abbreviation": "AUI",
            "example": "## Compliance with user-defined instructions ensures that the code meets custom project or team requirements.\n\n### Issue: Console logging left in production (violation of user instruction).\n\n### AUI-100\n\n### Severity: Medium\n\n```js\nconsole.log('Debug info');\n```\n\n### Solution: Remove or replace with proper logging.\n\n```js\n// logger.debug('Debug info');\n```",
        }

    async def _create_custom_characteristic_prompt(
        self, custom_char_object: Dict[str, Any], context: str
    ):
        characteristic = custom_char_object["characteristic"]
        user_instructions = custom_char_object["description"]
        abbreviation = custom_char_object["abbreviation"]
        example = custom_char_object["example"]

        prompt_template = f"""
Consider yourself a senior software engineer. Perform a detailed code compliance check on the above given code, focusing strictly on the user-defined instructions below.

## **User-Defined Instructions:**  
{user_instructions}

### **Analysis Guidelines:**

1. **Strict Instruction Compliance:**  
   - Check the code **only** against the given user-defined instructions.  
   - Treat each instruction as a requirement that must be met.  

2. **Relevant Issues Only:**  
   - Report an issue **only if the code clearly violates a user-defined instruction**.  
   - If the code complies fully, respond only with: "No issues found".  
   - Do not expand or explain correctly implemented instructions.  

3. **No Forced Issues:**  
   - Avoid generating issues that do not exist.  
   - Always provide examples **directly from the given code**.  

4. **Detailed Solutions:**  
   - For each identified issue, offer a **clear and detailed solution** with an improved code snippet.  

5. **Sequential Numbering:**  
   - Each issue should follow a **structured numbering format**, starting with **AUI** and appending a sequential number (e.g., **AUI-100**).  

6. **Plain Text Response Format:**  
   - Use **H2 (`##`) and H3 (`###`) headings** to structure your response.  
   - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points).  

### **Format of Output:**  

## A concise explanation of why compliance with user-defined instructions is important.
### Issue: (Description of the identified violation.)
### {abbreviation} (or sequential numbering).
### Severity: (judge the severity of violation: [Critical, High, Medium, Low].)
(The code snippet where the violation is found)
### Solution: (description of the fix.)
(If applicable, provide an improved code snippet that resolves the issue.)

## Examples
{example}

[**Note:** Follow the response structure given in the example strictly.]

## **Context:** Use the **context only for understanding the code snippet** if required.  
   - **DO NOT analyze, critique, or suggest improvements for the context itself.**  
   - Use the context **ONLY** to interpret the behavior, dependencies, or functionality of the provided code snippet.  
   - {context}
"""
        return characteristic, prompt_template

    async def _create_impact_based_characteristic_prompt(
        self, impact_char_object: Dict[str, Any], context: str, pr_summary: str = None
    ):
        """
        Create a prompt for impact-based characteristic analysis.
        This characteristic covers issues identified from PR Impact that weren't covered by applicability check.
        """
        characteristic = impact_char_object["characteristic"]
        description = impact_char_object.get("description", "")
        abbreviation = impact_char_object["abbreviation"]
        # Always use a single curated dummy example for impact-based prompts
        example = IMPACT_DUMMY_EXAMPLE
        weight = impact_char_object.get("weight", 1)

        # Add PR summary line if available
        pr_line = (
            f"\n\nAlso, Here is a concise summary of the PR, providing context for the file (which is part of this PR) that you are going to analyze: \n{pr_summary}\n"
            if pr_summary
            else ""
        )

        prompt_template = f"""
Consider yourself a senior software engineer. Perform a **detailed code analysis** on the above given **Code To Analyze**, focusing specifically on {characteristic}. This characteristic was identified from the PR Impact to cover issues that may not have been addressed by other analysis characteristics.

{description}

{pr_line}

### **Analysis Guidelines:**

1. **Thorough Examination:**  
   - Examine only the **Code To Analyze** and fully understand its functionality, constraints, and intended behavior.  
   - Focus on issues related to {characteristic} that are relevant to the PR Impact described above.

2. **Impact-Focused Issues:**  
   - Identify critical or high issues related to {characteristic} that align with the PR Impact.  
   - These issues should represent gaps or concerns that weren't covered by other characteristics.  
   - Consider how the provided **Context** influences issue identification and solutions.  

3. **No Forced Issues:**  
   - Avoid creating issues that do not exist. Always provide examples **directly from the given code** instead of generic examples.  
   - If no relevant issues are found related to {characteristic} in the context of the PR Impact, respond only with: "No issues found related to {characteristic} based on PR Impact."

4. **Detailed Solutions:**  
   - For each identified issue, offer a **clear and detailed solution** with an improved code snippet. Ensure the solution is an enhancement, not a repetition.  

5. **Sequential Numbering:**  
   - Each issue should follow a **structured numbering format**, starting with the first three letters of {characteristic} and appending a sequential number (e.g., **{abbreviation}**).  

6. **Plain Text Response Format:**  
   - Use **H2 (`##`) and H3 (`###`) headings** to structure your response.  
   - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points).  

### **Format of Output:**  

## A concise explanation of what {characteristic} is and its significance, especially in the context of the PR Impact.
### Issue: (Description of the identified issue related to {characteristic} and PR Impact.)
### {abbreviation} (or the appropriate numbering).
### Severity: (judge the severity of issue: [Critical, High, Medium, Low].)
(The code snippet where the issue is found)
### Solution: (Description of the solution.)
(If applicable, provide an improved code snippet that resolves the issue.)

## Examples
{example}

## **Note:** 
    - Follow the response structure given in the example strictly.
    - ***Issue description and Solution description should not be short it should be long and descriptive.*** 

## **Context:** Use the **context only for understanding the code snippet** if required.  
   - **DO NOT analyze, critique, or suggest improvements for the context itself.**  
   - Use the context **ONLY** to interpret the behavior, dependencies, or functionality of the provided code snippet.  
   - {context}
"""
        return characteristic, prompt_template

    async def _process_power_analysis_factor(
        self,
        factor_name: str,
        context: str,
        char_objects: List[Dict[str, Any]],
        pr_summary=None,
    ) -> List[tuple]:
        """
        Process a list of characteristics to generate prompts.

        :param factor_name: The name of the factor.
        :param char_objects: A list of factor objects to process.
        :return: A list of tuples containing characteristic names and their corresponding prompt templates.
        """
        results = []
        for obj in char_objects:
            characteristic = obj["characteristic"]
            description = obj["description"]
            abbreviation = obj["abbreviation"]
            example = obj["example"]
            weight = obj["weight"]

            # Add PR summary line if available
            pr_line = (
                f"\n\nAlso, Here is a concise summary of the PR, providing context for the file (which is part of this PR) that you are going to analyze: \n{pr_summary}\n"
                if pr_summary
                else ""
            )

            # Generate the prompt for each factor object
            prompt_template = f"""
Consider yourself a senior software engineer. Perform a detailed code analysis on the above given code, focusing on {characteristic}. {description}. {pr_line}

### **Analysis Guidelines:**

1. **Thorough Examination:**  
   - Examine only the **Code To Anlayze** and fully understand its functionality, constraints, and intended behavior.  

2. **Relevant Issues Only:**  
   - Identify maximum {weight} critical or high issues. Avoid speculative, trivial, or low-impact concerns. Focus only on problems that can cause critical to high damage or consequences.
   - Consider how the provided **Context** influences issue identification and solutions.  

3. **No Forced Issues:**  
   - Avoid creating issues that do not exist. Always provide examples **directly from the given code** instead of generic examples.  

4. **Detailed Solutions:**  
   - For each identified issue, offer a **clear and detailed solution** with an improved code snippet. Ensure the solution is an enhancement, not a repetition.  

5. **Sequential Numbering:**  
   - Each issue should follow a **structured numbering format**, starting with the first three letters of {characteristic} and appending a sequential number (e.g., **{abbreviation}**).  

6. **Plain Text Response Format:**  
   - Use **H2 (`##`) and H3 (`###`) headings** to structure your response.  
   - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points).  

### **Format of Output:**  

## A concise explanation of what {characteristic} is and its significance.
### Issue: (Description of the identified issue.)
### {abbreviation} (or the appropriate numbering).
### Severity: (judge the severity of issue: [Critical, High, Medium, Low].)
(The code snippet where the issue is found)
### Solution: (description of the solution.)
(If applicable, provide an improved code snippet that resolves the issue.)

## Examples
{example}

[**Note:** Follow the response structure given in the example strictly.]

## **Context:** Use the **context only for understanding the code snippet** if required.  
   - **DO NOT analyze, critique, or suggest improvements for the context itself.**  
   - Use the context **ONLY** to interpret the behavior, dependencies, or functionality of the provided code snippet.  
   - {context}

"""
            results.append((characteristic, prompt_template))
        return results

    async def _power_analysis_small_prompt(
        self,
        factor_name: str,
        context: str,
        additional_instructions: str = None,
        pr_summary=None,
    ) -> Dict[str, str]:
        """
        Generate an array of prompts for the power analysis.

        :param factor_name: The name of the factor.
        :param applicable_chars: Characteristics to filter.
        :return: A dictionary of prompts keyed by characteristic.
        """
        prompt_dict = {}
        results = await self._power_analysis_small(factor_name, context, pr_summary)

        for characteristic, prompt in results:
            prompt_dict[characteristic] = prompt

        # add a check if addiional instructions has spaces
        if isinstance(additional_instructions, str) and additional_instructions.strip():
            additional_char_obj = await self._create_custom_characteristic(
                user_instructions=additional_instructions
            )
            additional_characteristic, prompt = (
                await self._create_custom_characteristic_prompt(
                    custom_char_object=additional_char_obj, context=context
                )
            )
            prompt_dict[additional_characteristic] = prompt

        return prompt_dict

    async def _power_analysis_small(
        self, factor_name: str, context: str, pr_summary=None
    ) -> List[tuple]:
        """
        Process a list of characteristics to generate prompts.

        :param factor_name: The name of the factor.
        :param char_objects: A list of factor objects to process.
        :return: A list of tuples containing characteristic names and their corresponding prompt templates.
        """
        char_objects = Factors[factor_name]

        results = []
        issue_limit = MIN_ISSUE_LIMIT

        # Add PR summary line if available
        pr_line = (
            f"\n\nAlso, Here is a concise summary of the PR, providing context for the file (which is part of this PR) that you are going to analyze: \n{pr_summary}\n"
            if pr_summary
            else ""
        )

        for obj in char_objects:
            characteristic = obj["characteristic"]
            description = obj["description"]
            abbreviation = obj["abbreviation"]
            example = obj["example"]

            # Generate the prompt for each factor object
            prompt_template = f"""
Consider yourself a senior software engineer. Perform a **detailed code analysis** on the above given **Code To Anlayze**
Focusing on identifying maximum {issue_limit} key issues related to readability, maintainability, and naming convention improvements. Identify maximum {issue_limit} critical runtime issues that have a significant impact or damage. Remember Do Not analyze the context code that is just for your understanding only.

{pr_line}

### **Analysis Guidelines:**

1. **Thorough Examination:**  
   - Examine only the **code** and fully understand its functionality, constraints, and intended behavior.  

2. **Detailed and Clear Explanations:**  
    -  For each identified issue, provide a **detailed explanation**.
    -  For each proposed solution
    -  Provide a clear and **detailed explanation** that describes the problem.

3. **No Forced Issues:**  
   - If no significant issues are identified in the provided code snippet, do not analyze the context code to create issues forcefully. Only report valid concerns directly related to the provided code snippet. 

4. **Sequential Numbering:**  
   - Each issue should follow a **structured numbering format**, starting with the first three letters of {characteristic} and appending a sequential number (e.g., **{abbreviation}**). 

5. **Plain Text Response Format:**  
   - Use **H2 (`##`) and H3 (`###`) headings** to structure your response.  
   - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points).  

### **Format of Output:**  

##  {description}.
### Issue: (Description of the issue.)
### {abbreviation} (or the appropriate numbering).
### Severity: (judge the severity of issue: [Critical, High, Medium, Low].)
(The code snippet where the issue is found)
### Solution: (Description  of the solution.)
(If applicable, provide an improved code snippet that resolves the issue.)

## Examples
{example}

## **Note:** 
    - Follow the response structure given in the example strictly.
    - ***Issue description and Solution description shoul'd not be short it should be long and descriptive.*** 

## **Context:** Use the **context only for understanding the code snippet** if required.  
   - **DO NOT analyze, critique, or suggest improvements for the context itself.**  
   - Use the context **ONLY** to interpret the behavior, dependencies, or functionality of the provided code snippet.  
   - {context}

"""
            results.append((characteristic, prompt_template))
        return results

    async def _owasp_analysis_prompt(
        self,
        factor_name: str,
        context: str,
        applicable_chars: List[str] = None,
        pr_summary=None,
    ) -> Dict[str, str]:
        """
        Generate an array of prompts for the owasp analysis.

        :param factor_name: The name of the factor.
        :param applicable_chars: Characteristics to filter.
        :return: A dictionary of prompts keyed by characteristic.
        """
        prompt_dict = {}
        char_objects = Factors[factor_name]

        if applicable_chars:
            # Normalize applicable_chars by removing trailing " ()" that LLM sometimes adds
            # The LLM returns names like "OWASP A01:2021 Broken Access Control ()"
            # but Factors["owasp"] has "OWASP A01:2021 Broken Access Control" (no parentheses)
            normalized_applicable_chars = [
                char.rstrip(" ()") if char.endswith(" ()") else char
                for char in applicable_chars
            ]

            # Create sets for faster lookup - check both normalized and original
            applicable_chars_set = set(normalized_applicable_chars)
            original_applicable_chars_set = set(applicable_chars)

            filtered_char_objects = [
                obj
                for obj in char_objects
                if obj["characteristic"] in applicable_chars_set
                or obj["characteristic"] in original_applicable_chars_set
            ]

            logger.info(
                f"OWASP prompt generation: {len(applicable_chars)} applicable chars provided, "
                f"{len(normalized_applicable_chars)} after normalization, "
                f"{len(filtered_char_objects)} matched from {len(char_objects)} total characteristics",
                extra={"factor": factor_name},
            )
        else:
            filtered_char_objects = char_objects

        # **Group applicable characteristics**
        grouped_characteristics = {}
        for group_name, characteristics in OWASP_GROUPS.items():
            group_filtered = [
                obj
                for obj in filtered_char_objects
                if obj["characteristic"] in characteristics
            ]
            if group_filtered:  # Only add groups that have applicable characteristics
                grouped_characteristics[group_name] = group_filtered

        logger.info(
            f"OWASP prompt generation: Created {len(grouped_characteristics)} groups from {len(filtered_char_objects)} filtered characteristics",
            extra={
                "factor": factor_name,
                "groups": list(grouped_characteristics.keys()),
            },
        )

        for group_name, char_list in grouped_characteristics.items():
            results = await self._process_owasp_analysis_factor(
                factor_name, char_list, group_name, context, pr_summary
            )
            prompt_dict[group_name] = results

        return prompt_dict

    async def _process_owasp_analysis_factor(
        self,
        factor_name: str,
        char_objects: List[Dict[str, Any]],
        group_name: str,
        context: str = "",
        pr_summary=None,
    ) -> str:
        """
        Process a list of characteristics within a specific OWASP group.

        :param factor_name: The name of the factor.
        :param context: The code context.
        :param char_objects: A list of factor objects to process.
        :param group_name: The OWASP group this belongs to.
        :return: A formatted prompt string.
        """
        characteristics_list = [obj["characteristic"] for obj in char_objects]
        abbreviation_list = [obj["abbreviation"] for obj in char_objects]
        example_list = [obj["example"] for obj in char_objects]
        context_section = (
            f"2. **Context:** Additional code from the other files which are imported.\n"
            f"   **IMPORTANT: This context is provided ONLY for understanding the code snippet above. DO NOT analyze, critique, or suggest improvements for the context itself. Use the context ONLY to interpret the behavior, dependencies, or functionality of the code to analyze.\n"
            f"{context}\n"
            if context
            else ""
        )
        pr_line = (
            f"\n\nAlso, Here is a concise summary of the PR, providing context for the file (which is part of this PR) that you are going to analyze: \n{pr_summary}\n"
            if pr_summary
            else ""
        )

        # Construct a single prompt for the entire group
        prompt_template = f"""
Consider yourself a senior security engineer capable of performing security analysis. 
Your task is to analyze the above given code for vulnerabilities related to the following OWASP risks:

{', '.join(characteristics_list)}
{pr_line}

### **Input Structure:**  
1. **Code:** The code provided above (Code To Analyze section).

2. This context is provided ONLY for understanding the code snippet above.
{context_section}

### **Guidelines:**  
1️. **Prioritize Higher-Ranked OWASP Risks:**  
   - Focus **70% of the analysis effort** on the **highest-ranked OWASP vulnerabilities** in this set.  
   - Lower-ranked risks should only be analyzed if they contain **critical security concerns**.  
2. **Thorough Examination:** Review the full code, with referencing the context if provided, before providing the analysis.  
3. **Relevant Issues Only:** Identify only security issues **directly related** to the above OWASP risks.  
4. **No Redundant Issues:**  
   - If an issue affects multiple risks within this group, report it **under the most relevant category only** and **do not duplicate it**.   
5. **Detailed Solutions with Code Fixes:** Ensure the **improved code snippet fully resolves the issue**.  
6. **Plain Text Response Format:**  
   - Use ** H1 (`#`) H2 (`##`) and H3 (`###`) headings** to structure your response.  
   - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points). 
7. 7. **Sequential Numbering:**  
   - Each issue should use a **structured numbering format**, starting with the OWASP abbreviation and a sequential number (e.g., `A01-100`).

## **Output Format:**  
# (OWASP Characteristic Name with Code) (e.g. A01:2021 Broken Access Control)
## (A concise explanation of what the characteristic is and its significance.)
### Issue: (Description of the vulnerability.)
### (appropriate abbreviation based on the characteristic, with a sequesntial number starting from 100) (e.g. A01-100)
### Severity: (Critical, High, Medium, Low)  
(The code snippet where the issue is found.)  
### Solution: (Description of the fix.)  
(Improved code snippet resolving the issue.) 

## Examples
{chr(10).join(example_list)}

[**Note:** Follow the response structure given in the examples strictly.]
"""
        return prompt_template

    async def generate_pr_summary(
        self, pr_full_data: Dict[str, Any], pr_file_details: List[Dict[str, Any]]
    ) -> str:
        """
        Generates a PR summary using AI by combining high-level PR metadata and file-level changes.
        """

        # --- Step 1: Extract high-level info ---
        title = pr_full_data.get("title", "")
        description = pr_full_data.get(
            "body", ""
        )  # GitHub API uses 'body' not 'description'
        author = pr_full_data.get("user", {}).get("login", "unknown")
        labels = [label.get("name", "") for label in pr_full_data.get("labels", [])]
        commits = [
            commit.get("commit", {}).get("message", "")
            for commit in pr_full_data.get("commits", [])
        ]

        # --- Step 2: Extract file-level info ---
        file_summaries = []
        for f in pr_file_details:
            file_summary = {
                "filename": f.get("filename", ""),
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "changes": f.get("changes", 0),
                "patch": f.get("patch", ""),
            }
            file_summaries.append(file_summary)

        # --- Step 3: Build prompt for AI ---
        prompt = f"""
    You are an expert senior engineer and code reviewer. Summarize the Pull Request **concisely**, with an objective and clear explanation. The purpose of the summarization is so that a Pull Request reviewer can understand the Pull Request changes better, and it can be used as context for further review of this same Pull Request.

    ### PR Metadata
    - **Title:** {title}
    - **Description:** {description}
    - **Author:** {author}
    - **Labels:** {', '.join(labels) if labels else 'None'}
    - **Commits:** {len(commits)} commits
    {chr(20).join([f"  - {msg}" for msg in commits])}

    ### File Changes (metadata + patch for context)
    {json.dumps(file_summaries, indent=2)}

    ---

    ### Response Format
    ## PR Summary
    - A **broad overview** of what this PR does (new features, fixes, refactors, optimizations, etc.). Limit to 1-2 lines maximum.

    ## File-wise Changes
    Provide a table that explains **what changed in each file and why**, along with the **impact** of those changes.  
    Avoid listing just line additions/removals. Instead, focus on the logic, purpose, and consequences. Limit to 1-2 lines maximum.

    | File Name   | Summary of Modifications |
    |-------------|---------------------------------------|
    | file1.py    | Refactored authentication logic to use token-based validation, improving security and reducing dependency on sessions. |
    | file2.js    | Updated UI form validation to handle edge cases, enhancing user experience and reducing input errors. |

    ### Impact
    If applicable, provide a short paragraph explaining the **overall impact** of these changes:
    - Mention how they affect performance, security, reliability, stability, or maintainability.
    - Keep it objective and concise (1–2 lines maximum).
    - Provide only the impact of the PR changes — do not include any summary, description, or overview of the PR itself.
    - If there is **no significant impact**, omit this section entirely. 

    Note: Strictly follow the Response Format. Do not include any extra commentary, explanations, or sections outside the specified format.
"""

        return prompt

    async def generate_pr_diagram(self, pr_summary: str, pr_file_details: list) -> str:
        """
        Generates a prompt for creating a Graph-Spec JSON diagram based on PR summary
        and FULL file details (including complete patches).

        :param pr_summary: Summary text of the PR.
        :param pr_file_details: List of full file details including patch, status, additions, deletions, etc.
        :return: A formatted prompt string for the LLM.
        """

        # Prepare full file details section
        file_details_text = ""
        if pr_file_details:
            # Keep all fields provided by GitHub's API — dynamic, not hardcoded
            full_details = []
            for f in pr_file_details:
                file_entry = dict(f)  # clone original full file dictionary

                # Ensure patch is included fully (no truncation)
                patch = f.get("patch")
                if patch is not None:
                    file_entry["full_patch"] = patch

                full_details.append(file_entry)

            file_details_text = f"""
## FULL PR FILE DETAILS  
The following is the *complete* list of files modified in this PR, including **full patches and metadata**.  
Use these file contents as the primary source of truth for class names, functions, methods, flows, or relationships.

{json.dumps(full_details, indent=2)}
"""

        # Final prompt
        prompt = f"""
You are an expert at creating Graph-Spec JSON diagrams that depict code changes and architectural flows.

You are provided with:
- **Full file details**, including complete patches of a files from the Pull Request.
- A **PR Summary** describing the overview of the changes.

Use *both* resources to produce an accurate Graph-Spec JSON diagram.

---

## FULL PR FILE DETAILS
{file_details_text}

## PR SUMMARY
{pr_summary}

---

# CRITICAL RULES FOR SELECTING THE DIAGRAM TYPE

Analyze the full file patches and pr summary to determine the correct diagram type:

## 1. Use `"sequence"` when:
- The PR shows interactions between modules, components, or services over time.
- There are method/function calls, API interactions, request/response operations, or event flows.
- Examples: “Controller → Service → Repository”.

## 2. Use `"class"` when:
- The PR introduces or modifies classes, interfaces, inheritance, or composition.
- The PR affects Classes with attributes and methods.
- **CRITICAL: Only include classes that are DEFINED or MODIFIED in the PR patches themselves.**
- **EXCLUDE all imported classes** from:
  - Third-party libraries and frameworks
  - External dependencies
  - Any classes that appear only in import statements but are not defined in the patches
- Only extract what is explicitly present in the patches. **Never infer relationships based on naming or assumed architecture.**
- Extract only the top-level class skeleton: the real attributes and real methods declared directly inside the class—nothing additional.

## 3. Use `"flow"` when:
- The PR implements or modifies multi-step logic or processes.
- The code shows workflows, pipelines, branching logic, or decision paths.
- Examples: “Authentication process”, “Pipeline stages”, “Error-handling sequence”.

---

## Diagram Requirements
1. When to generate a diagram
Produce a Graph-Spec only if the PR changes or adds:
- Logic  
- Architecture  
- Data flow  
- Class structure  
- Functional behavior  

If changes are purely cosmetic (formatting, docs, comments), return nothing.

2. **Graph-Spec JSON Format**:
   - Must be valid JSON
   - Wrap in ```json code blocks
   - Structure:
     {{
       "diagram_type": "flow" | "sequence" | "class",
       "nodes": [
         {{"id": "unique_id", "label": "Human Readable Label"}},
         ...
       ],
       "edges": [
         {{"from": "node_id", "to": "node_id", "label": "optional relationship description"}},
         ...
       ]
     }}
3. **Node Guidelines**:
    - Each node must have a unique `id` and a descriptive `label`.
    - Do **not** invent classes or functions not present in the patches.
    - **For class diagrams:** Only include nodes for classes that are **defined or modified** in the PR patches. **Exclude all imported classes** from standard libraries (e.g., java.*, javax.*) and third-party packages.

4. **Edge Rules**:
    - Edges must reference correct node IDs.
    - Add `"label"` when needed for clarity.
    - **Sequence diagrams:** edges must follow chronological call order.
    - **Class diagrams:** 
      - Use labels like `"extends"`, `"implements"`, `"contains"`, `"uses"` when appropriate.
      - **Only create edges between classes that are defined in the PR patches.** Do not create edges to imported/third-party classes.

---

# Examples
{DIAGRAM_EXAMPLES['sequence']}

{DIAGRAM_EXAMPLES['class']}

{DIAGRAM_EXAMPLES['flow']}

---

Return **ONLY** the Graph-Spec JSON inside ```json code fences.  
Do **not** include any explanation or commentary.
"""

        return prompt

    async def _cwe_analysis_prompt(
        self,
        factor_name: str,
        context: str,
        applicable_chars: List[str] = None,
        pr_summary=None,
    ) -> Dict[str, str]:
        """
        Generate an array of prompts for the OWASP analysis,
        with each characteristic handled independently (no grouping).

        :param factor_name: The name of the factor.
        :param context: The code context.
        :param applicable_chars: Characteristics to filter.
        :return: A dictionary of prompts keyed by characteristic.
        """
        prompt_dict = {}
        char_objects = Factors[factor_name]

        # Filter applicable characteristics if provided
        if applicable_chars:
            filtered_char_objects = [
                obj for obj in char_objects if obj["characteristic"] in applicable_chars
            ]
        else:
            filtered_char_objects = char_objects

        # Process each characteristic independently
        for obj in filtered_char_objects:
            characteristic = obj["characteristic"]
            result = await self._process_cwe_analysis_characteristic(
                factor_name, obj, context, pr_summary
            )

            prompt_dict[characteristic] = result

        return prompt_dict

    async def _process_cwe_analysis_characteristic(
        self,
        factor_name: str,
        char_object: Dict[str, Any],
        context: str = "",
        pr_summary: str = None,
    ) -> str:
        """
        Process a single characteristic independently for CWE analysis.

        :param factor_name: The name of the factor.
        :param char_object: A single factor object to process.
        :param context: The code context.
        :return: A formatted prompt string.
        """
        characteristic = char_object["characteristic"]
        abbreviation = char_object["abbreviation"]
        example = char_object.get("example", "")
        owasp_mapping = char_object.get("owasp_mapping", "")
        cwe_mapping = char_object.get("cwe_mapping", "")

        context_section = (
            f"2. **Context:** Additional code from the other files which are imported.\n"
            f"   **IMPORTANT: This context is provided ONLY for understanding the code snippet above. DO NOT analyze, critique, or suggest improvements for the context itself. Use the context ONLY to interpret the behavior, dependencies, or functionality of the code to analyze.\n"
            f"{context}\n"
            if context
            else ""
        )

        # Construct a prompt for this single characteristic
        prompt_template = f"""
    Consider yourself a senior security engineer capable of performing security analysis. 
    Your task is to analyze the above given code for vulnerabilities related to the following CWE risk:
    {characteristic}


    ### **Input Structure:**  
    1. **Code:** The code provided above (Code To Analyze section).
    {context_section}

    ### **Guidelines:**  
    1️. **Thorough Examination:** Review the full code, referencing the context if provided.  
    2. **Relevant Issues Only:** Identify only security issues **directly related** to {characteristic}.  
    3. **No Redundant Issues:** Each issue should only appear once under this CWE.   
    4. **Detailed Solutions with Code Fixes:** Ensure the **improved code snippet fully resolves the issue**.  
    5. **Plain Text Response Format:**  
    - Use ** H1 (`#`) H2 (`##`) and H3 (`###`) headings** to structure your response.  
    - Do **not** use any other formatting (e.g., tables, markdown lists, or bullet points). 
    6. **Sequential Numbering:**  
    - Each issue should use a **structured numbering format**, starting with the CWE abbreviation and a sequential number (e.g., `{abbreviation}-100`).  

    ## **Output Format:**   
    # (CWE Characteristic Name with Code) (e.g. {characteristic})
    ## (A concise explanation of what this CWE means and its significance.)  
    ### Issue: (Description of the vulnerability. Additional CWE Mapping: {cwe_mapping} , OWASP Maping: {owasp_mapping})  
    ### {abbreviation}-100  
    ### Severity: (Critical, High, Medium, Low)  
    (The code snippet where the issue is found.)  
    ### Solution: (Description of the fix.)  
    (Improved code snippet resolving the issue.)  


    ## Examples
    {example}

    """
        return prompt_template

    async def _identify_missing_dependencies_prompt(
        self,
        file_path: str,
        extracted_imports: Dict[str, Any],
        repo_structure: List[str],
        pr_file_paths: List[str],
    ) -> str:
        """
        Generates a prompt for identifying missing file dependencies.
        
        This function uses extracted import lines (not full file content) to minimize
        token usage by 80-95%, resulting in faster responses and lower costs.
        
        Args:
            file_path: Path to the file being analyzed (e.g., "app/services/auth.py")
            extracted_imports: Dictionary with extracted import data:
                {
                    "file_path": str,
                    "language": str,
                    "import_lines": ["import os", "from app.utils import helper", ...]
                }
            repo_structure: List of all file paths in the repository
            pr_file_paths: List of file paths already in the PR
            
        Returns:
            Prompt string for the LLM
            
        Example:
            # Step 1: Prepare and extract imports (DONE BEFORE calling this function)
            from app.services.rag_services.imports_line_direct_extraction import (
                extract_import_lines_from_pr_files_as_dict,
                detect_language_from_filename
            )
            
            pr_files = [
                {
                    "path": file["filename"],
                    "content": file["new_content"],
                    "language": detect_language_from_filename(file["filename"])
                }
                for file in relevant_files
            ]
            
            # Extract imports from all PR files (returns dictionary)
            pr_imports_dict = await extract_import_lines_from_pr_files_as_dict(pr_files)
            # Result: {"app/services/auth.py": {"file_path": "...", "language": "...", "import_lines": [...]}}
            
            # Step 2: Use this function to generate prompt for each file
            file_imports = pr_imports_dict.get(file["filename"])
            
            if file_imports and file_imports.get("import_lines"):
                # Generate missing dependencies prompt
                prompt = await prompt_service._identify_missing_dependencies_prompt(
                    file_path=file["filename"],        # GitHub API field (full path)
                    extracted_imports=file_imports,     # Already a dict
                    repo_structure=repo_structure,      # List of all repo file paths
                    pr_file_paths=pr_file_paths         # List of PR file paths
                )
                
                # Use prompt with LLM to identify missing files
                # llm_response = await llm_service.call(prompt)
                
        Note:
            - Step 1 is for reference only - it shows preparatory work done BEFORE calling this function
            - This function only generates the prompt; import extraction happens separately
            - file["filename"] from GitHub API contains the full path (e.g., "app/services/auth.py")
            - extracted_imports comes from extract_import_lines_from_pr_files_as_dict()
        """
        
        language = extracted_imports.get("language", "unknown")
        import_lines = extracted_imports.get("import_lines", [])
        
        # Format import lines for the prompt (simple numbered list)
        if import_lines:
            imports_text = "\n".join([f"{i+1}. {line}" for i, line in enumerate(import_lines)])
        else:
            imports_text = "(No imports found)"
        
        prompt = f"""
You are a senior software architect analyzing Pull Request dependencies.

**Task:** Identify internal repository files that are imported in the current file but are NOT included in the PR.

### **INPUT**

**Current File:** `{file_path}`  
**Language:** `{language}`

**Import Statements:**
{imports_text}

**PR Files (already included):**
{json.dumps(pr_file_paths, indent=2)}

**Repository Structure (ALL files in repository):**
{json.dumps(repo_structure, indent=2)}

### **CRITICAL PRINCIPLE**

**USE REPOSITORY STRUCTURE AS THE SOURCE OF TRUTH!**

For EACH import statement, follow this decision tree:

**Step 1: Resolve import to potential file paths**
- Example: `from app.models import User` → `["app/models/__init__.py", "app/models.py", "app/models/user.py"]`
- Example: `import utils` → `["utils.py", "utils/__init__.py"]`
- Example: `from . import helper` → Resolve relative to current file's directory
- Example: `using MyApp.Services;` (C#) → `["MyApp/Services/__init__.cs", "MyApp/Services.cs"]`

**Step 2: Check if ANY resolved path exists in Repository Structure**
- If **YES** → This is an **INTERNAL** import (proceed to Step 3)
- If **NO** → This is an **EXTERNAL** import (IGNORE IT - stop here)

**Step 3: For INTERNAL imports, check if file is in PR**
- If file is in **PR Files** → Skip (already included)
- If file is in **Repository Structure** but NOT in **PR Files** → **ADD TO MISSING**

### **INSTRUCTIONS**

1. **Resolve each import statement to potential file paths**
   - Consider common Python/JavaScript/Java/C# import patterns
   - Handle both absolute and relative imports
   - Generate multiple potential paths (e.g., `__init__.py`, direct file)

2. **Determine if imports are INTERNAL or EXTERNAL**
   - Check if ANY resolved path exists in Repository Structure
   - If found in Repository Structure → INTERNAL (continue analysis)
   - If NOT found in Repository Structure → EXTERNAL (ignore it)
   - **DO NOT use pattern matching or guess based on common names!**
   - Even names like "utils", "helper", "common", "constants" can be internal files

3. **For each INTERNAL import, check against PR Files**
   - Verify it exists in Repository Structure (already done in step 2)
   - Check if it's included in PR Files
   - If missing from PR → Add to missing_files list

4. **Return results based on findings**
   - If **all internal files are present** in PR → return empty list with status 1
   - If **no internal imports** found (only external) → return empty list with status 1
   - If **some files are missing** from PR but present in Repository → return those files with status 0
   - **Important:** Only return files that exist in Repository Structure but NOT in PR Files

### **COMMON PITFALLS TO AVOID**

**DO NOT make these assumptions:**
- ❌ "utils" is probably external → **WRONG!** Check Repository Structure first
- ❌ "requests" is a library → **WRONG!** Could be internal "requests.py"
- ❌ "helper" is a common name → **WRONG!** Check Repository Structure first
- ❌ "common" is generic → **WRONG!** Check Repository Structure first
- ✅ **ALWAYS verify against Repository Structure before deciding internal vs external**

### **OUTPUT FORMAT**

Return **ONLY** valid JSON (no markdown, no explanations, no code blocks):

{{
  "status": 0 | 1,
  "missing_files": ["path1", "path2", ...]
}}

**Rules:**
- `status: 0` → Internal dependencies are missing (list them in missing_files)
- `status: 1` → All dependencies present OR no internal imports (empty missing_files)
- `missing_files` → Exact repository file paths (only files in Repository but NOT in PR)
- Do NOT include explanations, comments, markdown code blocks, or extra fields
- Return raw JSON only

### **EXAMPLES**

**Example 1: Missing Dependencies**
{{
  "status": 0,
  "missing_files": [
    "app/services/auth_service.py",
    "app/models/user_model.py"
  ]
}}

**Example 2: All Present (All internal imports are in PR)**
{{
  "status": 1,
  "missing_files": []
}}

**Example 3: No Internal Imports (Only external libraries)**
{{
  "status": 1,
  "missing_files": []
}}

**Example 4: Edge Case - "utils" is INTERNAL**
If import is `from utils import validator` and Repository Structure contains "utils.py" or "utils/__init__.py":
- Check Repository Structure → Found "utils.py" → INTERNAL
- Check PR Files → NOT found → Missing!
- Return:
{{
  "status": 0,
  "missing_files": [
    "utils.py"
  ]
}}

"""
        
        return prompt
