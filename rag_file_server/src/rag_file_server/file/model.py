from pydantic import BaseModel


class MetaData(BaseModel):
    upload_time: float = 0
    size: int = 0


class UploadResponse(BaseModel):
    saved_files: list[str]
    ignore_files: list[str]
