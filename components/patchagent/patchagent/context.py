import time
from typing import Any, Dict, List

from patchagent.logger import logger


class Context:
    def __init__(self, data: Dict = {}) -> None:
        self.patch = data.get("patch", None)
        self.messages = data.get("messages", [])
        self.elapsed_time = data.get("elapsed_time", None)

    def __enter__(self) -> "Context":
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type: str, exc_value: Exception, traceback: Any) -> None:
        self.elapsed_time = time.time() - self.start_time

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        return [message["message"] for message in self.messages if message["role"] == "tool"]

    def add_tool_call(self, name: str, args: Dict, result: str) -> None:
        data = {
            "role": "tool",
            "message": {
                "name": name,
                "args": args,
                "result": result,
            },
        }
        self.messages.append(data)
        logger.debug(f"[📞] Tool call: {data}")

    def add_llm_response(self, response: str) -> None:
        if len(response) > 0:
            data = {
                "role": "llm",
                "message": response,
            }
            self.messages.append(data)
            logger.debug(f"[🤖] LLM response: {data}")

    def add_system_message(self, message: str) -> None:
        if len(message) > 0:
            data = {
                "role": "system",
                "message": message,
            }
            self.messages.append(data)
            logger.debug(f"[🧑‍💻] System message: {data}")

    def add_user_message(self, message: str) -> None:
        if len(message) > 0:
            data = {
                "role": "user",
                "message": message,
            }
            self.messages.append(data)
            logger.debug(f"[👤] User message: {data}")

    def dump(self) -> Dict[str, Any]:
        return {
            "patch": self.patch,
            "elapsed_time": self.elapsed_time,
            "messages": self.messages,
        }
