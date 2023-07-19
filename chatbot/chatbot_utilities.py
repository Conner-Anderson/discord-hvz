from dataclasses import dataclass, field
from typing import Any


class ResponseError(ValueError):
    def __init__(self, message=None):
        if message is not None:
            super().__init__(message)


@dataclass
class Response:
    raw_response: str
    processed_response: Any