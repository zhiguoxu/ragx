from enum import Enum

from fastapi import HTTPException


class ErrorCode(Enum):
    ERROR_CODE_NOT_EXISTS = (520, "Error code not exists")
    FILE_EXISTS = (521, "File already exists")
    FILE_NOT_EXISTS = (522, "File not exists")
    BUCKET_NOT_EXISTS = (523, "Bucket not exists")
    DIR_NOT_EXISTS = (524, "Dir not exists")
    UNIQUE_CONSTRAINT_FAILED = (542, "unique constraint failed")
    BUCKET_ALREADY_EXIST = (525, "bucket already exist")

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
        if desc.startswith(','):
            desc = desc[1:]
            desc = desc.strip()

    if error_code_:
        desc = error_code_.desc + (', ' + desc if desc else '')

    raise HTTPException(status_code=code_, detail=desc)
