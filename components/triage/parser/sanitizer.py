from enum import StrEnum
from typing import Any, Dict, List, Tuple, Union


class Sanitizer(StrEnum):
    AddressSanitizer = "AddressSanitizer"
    MemorySanitizer = "MemorySanitizer"
    UndefinedBehaviorSanitizer = "UndefinedBehaviorSanitizer"
    ThreadSanitizer = "ThreadSanitizer"
    LeakSanitizer = "LeakSanitizer"
    LibFuzzer = "libFuzzer" # This is for timeout or strange signals that sanitizers couldn't catch
    Jazzer = "Jazzer"


class SanitizerReport:
    def __init__(
        self,
        sanitizer: Sanitizer,
        content: str,
        cwe: str,
        trigger_point: str,
        additional_info: Dict[str, Any] = {},
    ):

        self.sanitizer: Sanitizer = sanitizer
        self.content: str = content
        self.cwe: str = cwe
        self.trigger_point: str = trigger_point
        self.additional_info: Dict[str, Any] = additional_info

    def __getitem__(self, key: str) -> Any:
        return self.additional_info[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_info[key] = value

    @property
    def summary(self) -> str:
        raise NotImplementedError("summary method must be implemented in child class")

    @property
    def summary(self) -> str:
        return self.content

    @staticmethod
    def parse(content: str) -> Union[None, "SanitizerReport"]:
        raise NotImplementedError("parse method must be implemented in child class")
