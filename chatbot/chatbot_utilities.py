from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class ResponseError(ValueError):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass
class Response:
    raw_response: str
    processed_response: Any

class ChatbotState(Enum):
    BEGINNING = 1
    QUESTIONING = 2
    REVIEWING = 3
    MODIFYING_SELECTION = 4
    MODIFYING = 5