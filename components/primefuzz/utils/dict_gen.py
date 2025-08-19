import os
import re
import zipfile
import struct  # For more precise class file parsing
import logging
import random
import threading
from difflib import SequenceMatcher
from functools import wraps

RE_STRINGS = rb'[\x20-\x7E]{3,}'
MIN_LENGTH = 4
MAX_LENGTH = 16
JAZZER_INTERNAL_KEYWORDS = [
    "jazzer_coverage",
    "jazzer_fuzz",
    "jazzer_",
    "jazzer_debug",
    "jazzer_internal",
    "jazzer_version",
    "jazzerinternal",
    "jazzersubpackage",
    "jazzer_driver",
    "jazzeragentpath",
    "parsejazzerargs",
    "jazzer_preload",
]

JAVA_USEFUL_KEYWORDS = [
    '"../"',
    '"%20"',
    '"http"',
    '"https"',
    '"file"',
    '"://"',
    '"\\xff\\xff"',
    '"\\x7f\\xff"',
    '"<!"',
    '"<![INCLUDE["',
    '"]]>"',
    '"<?xml?>"',
    '"tcp:"',
    '"file:"',
    '"localhost"',
    '"ftp"',
    '"ENTITY"',
    '"SYSTEM"',
    '".zip"'
]


def timeout_wrapper(timeout_seconds=60):
    """
    Decorator to add timeout functionality to any function using threading.
    Returns [] if timeout occurs or function fails.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout_seconds)

            if thread.is_alive():
                logging.warning(
                    f"Function {func.__name__} timed out after {timeout_seconds} seconds")
                return []

            if exception[0]:
                logging.warning(f"Error in {func.__name__}: {exception[0]}")
                return []

            return result[0] if result[0] is not None else []

        return wrapper
    return decorator


def is_excluded_java_string(s):
    if not isinstance(s, str) or not s:
        return False

    # Rule 0: No spaces allowed in these identifiers/descriptors
    if ' ' in s or len(str(s).strip()) < MIN_LENGTH or len(str(s).strip()) > MAX_LENGTH:
        return True

    # Rule 1: Exclude strings starting or ending with common Java prefixes/suffixes
    start_exclusions = ["!", "#", "(", "xLjava", "d(Ljava", "](L", "+", "-", "=",
                        "[Ljava", "TLjava", "Ljava/", "J(L", "?", "*"]
    end_exclusions = ["@", ".java", "T;", ")", ":", ";", "!", "$", "?", "-", "+",
                      "];", "\"", "=", "*", ",", ")V"]

    if any(s.startswith(prefix) for prefix in start_exclusions) or any(s.endswith(suffix) for suffix in end_exclusions):
        return True

    # Rule 2: Fully qualified class names or package names (dot-separated)
    # e.g., "java.vm.version", "org.apache.commons.logging.Log"
    if re.fullmatch(r'[a-zA-Z_$][\w$]*(\.[a-zA-Z_$][\w$]*)+', s):
        return True

    # Rule 3: Internal form of class names (slash-separated)
    # e.g., "java/io/BufferedInputStream", "org/apache/commons/Foo"
    if re.fullmatch(r'[a-zA-Z_$][\w$]*(\/[a-zA-Z_$][\w$]*)+', s):
        return True

    # Rule 4: Type descriptors (standalone)
    # e.g., "Ljava/lang/String;", "[I", "[Ljava/net/URL;"
    # Pattern for L...; : L + internal form + ;
    if re.fullmatch(r'L[a-zA-Z_$][\w$]*(\/[a-zA-Z_$][\w$]*)*;', s):
        return True
    # Pattern for array descriptors: '['+ type or '['+ L...;
    if re.fullmatch(r'\[+(?:[BCDFIJSZ]|L[a-zA-Z_$][\w$]*(\/[a-zA-Z_$][\w$]*)*;)', s):
        return True

    # Rule 5: Method descriptors, potentially prefixed with a name
    # e.g., "(Ljava/lang/String;I)V"
    # e.g., from prompt: "l(Lorg/apache/tools/ant/Project;...;)L...;"
    if '(' in s and ')' in s:
        # This complex regex defines a type descriptor (primitive, object, or array)
        type_desc_regex_segment = r'(?:[BCDFIJSZ]|L[a-zA-Z_$][\w$]*(\/[a-zA-Z_$][\w$]*)*;|\[(?:[BCDFIJSZ]|L[a-zA-Z_$][\w$]*(\/[a-zA-Z_$][\w$]*)*;))'

        # Pattern for method descriptor without a name prefix: (params)return
        method_desc_pattern_no_name = r'^\((?:' + type_desc_regex_segment + \
            r')*\)(?:V|' + type_desc_regex_segment + r')$'
        if re.fullmatch(method_desc_pattern_no_name, s):
            return True

        # Pattern for method descriptor with an optional name prefix: name(params)return
        method_desc_pattern_with_name = r'^[a-zA-Z_$][\w$]*\((?:' + \
            type_desc_regex_segment + \
            r')*\)(?:V|' + type_desc_regex_segment + r')$'
        if re.fullmatch(method_desc_pattern_with_name, s):
            return True

    return False


def get_top_unique_strings(strings_list, top_n=30, similarity_threshold=0.6):
    """
    Returns the top N unique strings from the input list after filtering out 
    Java-specific patterns, using approximate string matching.
    Important keywords are prioritized to be included.

    Args:
        strings_list: List of strings to filter
        top_n: Number of unique strings to return (default: 30)
        similarity_threshold: Threshold for determining string similarity (default: 0.6)

    Returns:
        List containing at most top_n unique strings
    """
    # Keywords that must be preserved
    important_keywords = ["aixcc", "jazzer", "zilairese"]

    # Initialize list to store unique strings and their normalized versions
    unique_strings = []
    normalized_unique = []

    # First process strings with important keywords
    important_strings = []
    other_strings = []

    for s in strings_list:
        clear_s = s.lower().strip().strip("\"").replace("=", "\\x3d")
        contains_important_keyword = any(
            keyword in clear_s for keyword in important_keywords)

        if contains_important_keyword and \
                (not clear_s in important_strings) and \
                (not clear_s in JAZZER_INTERNAL_KEYWORDS) and \
                (not "code_intelligence" in clear_s):
            important_strings.append(clear_s)
        else:
            other_strings.append(s)

    # Shuffle other strings for randomness
    random.shuffle(other_strings)

    # Process all strings, with important ones first
    all_strings_prioritized = important_strings + other_strings

    for s in all_strings_prioritized:
        clear_s = s.lower().strip().replace("=", "\\x3d").replace("\"", "\\x22").replace("\\", "\\\\").strip("\"")
        if is_excluded_java_string(clear_s):
            continue

        normalized_s = clear_s.lower().strip()
        contains_important_keyword = any(
            keyword in clear_s for keyword in important_keywords)

        # Check for similarity with already selected strings
        is_similar = False
        if not contains_important_keyword:  # Skip similarity check for important strings
            for existing_norm in normalized_unique:
                similarity = SequenceMatcher(
                    None, normalized_s, existing_norm).ratio()
                if similarity > similarity_threshold:
                    is_similar = True
                    break

        # If string is unique enough or contains important keywords, add it
        if not is_similar or contains_important_keyword:
            unique_strings.append(f'"{clear_s}"')
            normalized_unique.append(normalized_s)

            # Only break if we've reached the limit AND processed all important strings
            if len(unique_strings) >= top_n and s in other_strings:
                break

    return unique_strings


def extract_strings_from_class_bytes(class_bytes):
    potential_strings = set()

    # Method 1: General printable strings using RE_STRINGS
    for match in re.finditer(RE_STRINGS, class_bytes):
        try:
            # Try decoding as UTF-8 first, as it's common
            s = match.group(0).decode('utf-8', errors='ignore')
            potential_strings.add(s)
        except UnicodeDecodeError:  # Should be caught by errors='ignore' but as a fallback
            try:
                s = match.group(0).decode(
                    'ascii', errors='ignore')  # Fallback to ASCII
                potential_strings.add(s)
            except UnicodeDecodeError:
                pass  # Ignore if undecodable by both

    # Method 2: Parse constant pool for CONSTANT_Utf8 entries
    try:
        # Check for magic number
        if class_bytes[:4] != b'\xCA\xFE\xBA\xBE':
            # Not a valid class file, or not one we can parse constant pool for.
            # Filter what we got from RE_STRINGS and return.
            final_strings = {
                s_cand for s_cand in potential_strings if s_cand and not is_excluded_java_string(s_cand)}
            return sorted(list(final_strings))

        constant_pool_count = struct.unpack('>H', class_bytes[8:10])[0]
        offset = 10  # Start of the constant pool

        for _ in range(constant_pool_count - 1):
            if offset >= len(class_bytes):
                break
            tag = class_bytes[offset]
            offset += 1

            if tag == 1:  # CONSTANT_Utf8
                if offset + 2 > len(class_bytes):
                    break
                length = struct.unpack('>H', class_bytes[offset:offset+2])[0]
                offset += 2
                if offset + length > len(class_bytes):
                    break
                utf8_bytes = class_bytes[offset:offset+length]
                try:
                    s = utf8_bytes.decode('utf-8')
                    # Add to the common set for later filtering
                    potential_strings.add(s)
                except UnicodeDecodeError:
                    # This might happen if a non-string Utf8 entry is encountered,
                    # or if the string is not valid UTF-8.
                    pass
                offset += length
            # CONSTANT_Class, CONSTANT_String, CONSTANT_MethodType, CONSTANT_Module, CONSTANT_Package
            elif tag in [7, 8, 16, 19, 20]:
                offset += 2
            elif tag in [3, 4]:  # CONSTANT_Integer, CONSTANT_Float
                offset += 4
            # CONSTANT_Fieldref, CONSTANT_Methodref, CONSTANT_InterfaceMethodref, CONSTANT_NameAndType, CONSTANT_InvokeDynamic
            elif tag in [9, 10, 11, 12, 18]:
                offset += 4
            elif tag in [5, 6]:  # CONSTANT_Long, CONSTANT_Double
                offset += 8
                # _ += 1 # Consume an extra slot (constant_pool_count is for entries, long/double take 2)
            elif tag == 15:  # CONSTANT_MethodHandle
                offset += 3
            elif tag == 17:  # CONSTANT_Dynamic
                offset += 4
            else:
                # Unknown or unhandled tag
                break
    except struct.error:
        # print(f"Struct unpacking error, likely malformed or truncated class file.")
        pass  # Fallback to strings found so far if detailed parsing fails
    except Exception:
        # print(f"An unexpected error occurred during detailed class parsing: {e}")
        pass

    # Ensure string is not empty or None before filtering
    final_strings = {
        s_cand for s_cand in potential_strings if s_cand and not is_excluded_java_string(s_cand)}
    return sorted(list(final_strings))


@timeout_wrapper(timeout_seconds=30)
def process_class_file(file_path):
    """Processes a single .class file and extracts strings."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        return extract_strings_from_class_bytes(content)
    except Exception as e:
        print(f"Error processing class file {file_path}: {e}")
        return []


@timeout_wrapper(timeout_seconds=30)
def process_jar_file(file_path):
    """Processes a .jar file, extracting strings from .class files within it."""
    all_jar_strings = set()
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            for member_name in zf.namelist():
                if member_name.endswith('.class'):
                    try:
                        with zf.open(member_name) as class_file_in_jar:
                            class_bytes = class_file_in_jar.read()
                            strings_in_class = extract_strings_from_class_bytes(
                                class_bytes)
                            for s in strings_in_class:
                                if any(ord(char) > 127 for char in s):
                                    continue
                                all_jar_strings.add(s)
                    except Exception as e:
                        print(
                            f"  Error reading class {member_name} from jar {file_path}: {e}")
    except zipfile.BadZipFile:
        print(f"Error: Bad ZIP file (corrupted JAR?): {file_path}")
    except Exception as e:
        print(f"Error processing jar file {file_path}: {e}")
    return sorted(list(all_jar_strings))


@timeout_wrapper(timeout_seconds=60)
def extract_strings_from_path(target_path: str, harness_name: str = ""):
    """
    Extracts strings from all .class and .jar files under the given path.
    Returns a dictionary where keys are file paths and values are lists of strings.
    """
    extracted_data = {}

    if not os.path.exists(target_path):
        print(f"Error: Path '{target_path}' does not exist.")
        return extracted_data

    for root, _, files in os.walk(target_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            if filename.endswith('.class') and harness_name in filename:
                strings = process_class_file(file_path)
                if strings:  # Only add if non-empty list of strings
                    extracted_data[file_path] = strings
            elif filename.endswith('.jar'):
                # Skip Jazzer-related JAR files
                if any(pattern in filename for pattern in ['jazzer-', 'jazzer_agent_deploy.jar']):
                    logging.debug(f"Skipping Jazzer-related JAR file: {file_path}")
                    continue
                # skip maven m2 repository jars
                if 'mvn/' in root or '/m2/' in root:
                    logging.debug(f"Skipping Maven repository JAR file: {file_path}")
                    continue
                # Skip files larger than 4MB
                if os.path.getsize(file_path) > 4 * 1024 * 1024:
                    logging.debug(
                        f"Skipping large JAR file (>4MB): {file_path}")
                    continue
                strings = process_jar_file(file_path)
                if strings:  # Only add if non-empty list of strings
                    extracted_data[file_path] = strings
    return extracted_data


def gen_dict_java(artifact_path: str, output_dir: str, harnesses: list = []):
    """
    Generates a dictionary of strings from a Java class file or JAR.
    If harnesses are provided, generates a separate dictionary file for each harness.
    """
    if not os.path.exists(artifact_path):
        logging.error(f"File {artifact_path} does not exist.")
        return None

    # If no harnesses specified, process all jars as before
    if not harnesses:
        all_found_strings = extract_strings_from_path(artifact_path)
        if not all_found_strings:
            logging.warning(
                "No relevant strings found or no .class/.jar files encountered.")
        else:
            logging.debug(
                "--- Extracted Strings (excluding package/class names) ---")

            # Collect all strings first
            all_strings = []
            for file_path, strings in all_found_strings.items():
                logging.info(f"Saving extracted dict from file: {file_path}")
                if not strings:
                    logging.debug("  <No non-excluded strings found>")
                    continue
                all_strings.extend(strings)

            all_strings = get_top_unique_strings(all_strings)

            # Write all strings at once if output path provided
            if output_dir and all_strings:
                try:
                    with open(os.path.join(output_dir, "all.dict"), 'a') as output_file:

                        logging.info(f"Writing dictionary to {output_dir}")
                        output_file.write(
                            "\n".join(JAVA_USEFUL_KEYWORDS) + "\n" + "\n".join(all_strings) + "\n")
                except Exception as e:
                    logging.error(
                        f"Error writing to output file {output_dir}: {e}")
    else:
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Process each harness individually
        for harness in harnesses:
            logging.debug(f"Processing harness: {harness}")

            # Extract strings specific to this harness
            harness_strings = extract_strings_from_path(artifact_path, harness)

            if not harness_strings:
                logging.warning(
                    f"No relevant strings found for harness: {harness}")
                continue

            # Collect all strings for this harness
            all_strings = []
            for file_path, strings in harness_strings.items():
                logging.debug(f"Extracting dict from file: {file_path}")
                if not strings:
                    logging.debug("  <No non-excluded strings found>")
                    continue
                all_strings.extend(strings)

            # Filter for top unique strings
            all_strings = get_top_unique_strings(all_strings)

            # Create file path for this harness's dictionary
            harness_dict_path = os.path.join(output_dir, f"{harness}.dict")

            # Save to harness-specific dictionary file
            if all_strings:
                try:
                    with open(harness_dict_path, 'a') as output_file:
                        logging.info(
                            f"Writing dictionary to {harness_dict_path}")
                        output_file.write(
                            "\n".join(JAVA_USEFUL_KEYWORDS) + "\n" + "\n".join(all_strings) + "\n")
                except Exception as e:
                    logging.error(
                        f"Error writing to output file {harness_dict_path}: {e}")


def main():
    # script_dir = os.path.dirname(os.path.abspath(__file__))
    # Default to current directory. You can change this to use input() or sys.argv for flexibility.
    target_directory = "."
    # Example to take from command line:
    # import sys
    # if len(sys.argv) > 1:
    #     target_directory = sys.argv[1]
    # else:
    #     print(f"Usage: python {sys.argv[0]} <target_directory>")
    #     print(f"Defaulting to current directory: {script_dir}")
    #     target_directory = script_dir

    logging.info(
        f"Scanning directory to generate dictionaries: {os.path.abspath(target_directory)}")
    all_found_strings = extract_strings_from_path(target_directory)

    if not all_found_strings:
        logging.warning(
            "No relevant strings found or no .class/.jar files encountered.")
    else:
        print("\n--- Extracted Strings (excluding package/class names) ---")
        for file_path, strings in all_found_strings.items():
            try:
                # Attempt to make path relative to the initial target for cleaner output
                relative_path = os.path.relpath(
                    file_path, os.path.abspath(target_directory))
            # Can happen if target_directory is relative and file_path becomes absolute on a different drive (Windows)
            except ValueError:
                relative_path = file_path

            print(f"\nFile: {relative_path}")
            if not strings:
                print("  <No non-excluded strings found>")
                continue
            for s in strings:
                print(f"  - \"{s}\"")
        print("\n--- Scan Complete ---")
