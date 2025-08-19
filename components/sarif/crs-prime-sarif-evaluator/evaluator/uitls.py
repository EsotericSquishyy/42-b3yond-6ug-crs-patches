import re
import json


def is_valid_json(json_string: str) -> bool:
    """
    Check if the given string is a valid JSON string.
    """
    try:
        json.loads(json_string)
        return True
    except ValueError:
        return False


def process_result(result: str) -> dict:
    """
    Process the result string and return a dictionary with the relevant information.
    The result string can be a valid JSON string or text containing a JSON string,
    potentially within markdown code fences (```json ... ```).
    Extracts and parses the first valid JSON object found.
    """
    # 1. Check if the entire string is valid JSON
    if is_valid_json(result):
        try:
            # Attempt to parse directly, handle potential edge cases
            return json.loads(result)
        except json.JSONDecodeError:
            # This case should ideally not be reached if is_valid_json is accurate,
            # but proceed to extraction methods just in case.
            pass

    # 2. Try to extract JSON from ```json ... ``` markdown block
    match_md = re.search(r"```json\s*([\s\S]*?)\s*```", result, re.DOTALL)
    if match_md:
        content_in_fence = match_md.group(1).strip()
        # Check if the content within the fence looks like a JSON object
        if content_in_fence.startswith('{') and content_in_fence.endswith('}'):
            if is_valid_json(content_in_fence):
                try:
                    return json.loads(content_in_fence)
                except json.JSONDecodeError:
                    # If parsing fails despite is_valid_json, continue
                    pass

    # 3. Fallback: Try to find the first '{' and last '}' in the whole string
    try:
        start_index = result.find('{')
        end_index = result.rfind('}')
        # Ensure both braces are found and in the correct order
        if start_index != -1 and end_index != -1 and start_index < end_index:
            potential_json = result[start_index: end_index + 1]
            # Validate if the extracted substring is valid JSON
            if is_valid_json(potential_json):
                try:
                    # Attempt to parse the extracted substring
                    return json.loads(potential_json)
                except json.JSONDecodeError:
                    # If parsing fails, it wasn't the correct JSON block
                    pass
    except Exception:
        # Catch potential errors during string slicing (though unlikely here)
        pass

    # 4. If no valid JSON could be extracted and parsed
    # Consider logging a warning here if needed for debugging
    # print(f"Warning: Could not extract valid JSON from result: {result[:100]}...")
    return {}
