import requests 
import base64
import os
# from db import SanitizerEnum
import json

# sanitizer_map = {
#     SanitizerEnum.ASAN: "address",
#     SanitizerEnum.UBSAN: "undefined",
#     SanitizerEnum.MSAN: "memory",
#     SanitizerEnum.JAZZER: "jazzer",
#     SanitizerEnum.UNKNOWN: "unknown"
# }

def prepare_pov_submission_data(content):
    try:
        pov_data = open(content.poc, "rb").read()
    except FileNotFoundError:
        if os.getenv("AIXCC_LOCAL_DEBUG"):
            pov_data = b"aaaa"
        else:
            raise Exception(f"POV file {content.poc} not found")
    if len(pov_data) > 2097152:
        raise Exception("POV file is too large")
    return {
        "architecture": content.architecture,
        "fuzzer_name": content.harness_name,
        # "sanitizer": sanitizer_map[content.sanitizer],
        "sanitizer": content.sanitizer,
        "testcase": base64.b64encode(pov_data).decode(),
        # TODO: modify this to generalize engine, this is a workaround for now
        "engine": "libfuzzer",
    }

def prepare_patch_submission_data(content):
    patch_data = content.patch
    if len(patch_data) > 102400:
        raise Exception("Patch file is too large")
    return {
        # "patch": base64.b64encode(patch_data.encode()).decode()
        # assume patch_data is base64 encoded
        "patch": patch_data,
    }
    
def prepare_sarif_submission_data(content):
    description = content.description
    if len(description) > 131072:
        raise Exception("Description is too large")
    return {
        "assessment": "correct" if content.result else "incorrect",
        "description": description,
    }

def prepare_submission_data(typ, content):
    if typ == "pov":
        return prepare_pov_submission_data(content)
    elif typ == "patch":
        return prepare_patch_submission_data(content)
    elif typ == "sarif":
        return prepare_sarif_submission_data(content)
    
def submit_data(base_url, typ, task_id, data, sarif_id = None):
    
    if typ == "sarif":
        base_url = f"{base_url}/v1/task/{task_id}/broadcast-sarif-assessment/{sarif_id}/"
    else:
        base_url = f"{base_url}/v1/task/{task_id}/{typ}/"

    # make http request
    response = requests.post(base_url, json = json.loads(data), auth = requests.auth.HTTPBasicAuth(os.getenv("API_USER", "foo"), os.getenv("API_PASS", "bar")))
    # if os.getenv("AIXCC_LOCAL_DEBUG"):
    #     result = {f"{typ}_id": str(uuid.uuid4()), "status": "accepted"}
    #     return result
    if response.status_code != 200:
        raise Exception(f"Failed to submit data: {response.status_code}")
    result = response.json()
    return result

def confirm_submission(base_url, typ, task_id, submission_id):
    # typ = pov or patch
    base_url = f"{base_url}/v1/task/{task_id}/{typ}/{submission_id}/"

    # make http request
    response = requests.get(base_url, auth = requests.auth.HTTPBasicAuth(os.getenv("API_USER", "foo"), os.getenv("API_PASS", "bar")))
    # if os.getenv("AIXCC_LOCAL_DEBUG"):
    #     result = {"status": "accepted" if __import__("random").randint(0, 1) == 1 else "passed"}
    #     return result
    if response.status_code != 200:
        raise Exception(f"Failed to confirm submission: {response.status_code}")
    result = response.json()
    return result


# def submit_sarif_report(base_url, task_id, sarif_file):
#     url = f"{base_url}/v1/task/{task_id}/submitted-sarif"
#     data = open(sarif_file, "r").read()
#     logging.debug(f"Submitting sarif report to {url}, data: {data}")
#     response = requests.post(url, json = data)
#     if response.status_code != 200:
#         raise Exception(f"Failed to submit sarif report: {response.status_code} {response.json()}")
#     return response.json()