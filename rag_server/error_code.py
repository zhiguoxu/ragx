from enum import Enum

from fastapi import HTTPException


class ErrorCode(Enum):
    LOGIN_FAILED = (540, "login failed")
    INVALID_TOKEN = (541, "invalid token")
    UNIQUE_CONSTRAINT_FAILED = (542, "unique constraint failed")
    NO_PERMISSION = (543, "no permission")
    KB_USED_BY_APP = (544, "kb used by app")

    def __init__(self, code, desc):
        self.code = code
        self.desc = desc


def raise_exception(error_code: ErrorCode | int, desc: str | None = None):
    error_code_ = None
    if isinstance(error_code, int):
        code_ = error_code
        for code in ErrorCode:
            if code.code == error_code:
                error_code_ = code
                break
    else:
        error_code_ = error_code
        code_ = error_code.code

    # remove redundant desc
    if error_code_ and desc and desc.startswith(error_code_.desc):
        desc = desc[len(error_code_.desc):]

    if error_code_:
        desc = error_code_.desc + (', ' + desc if desc else '')

    raise HTTPException(status_code=code_, detail=desc)
