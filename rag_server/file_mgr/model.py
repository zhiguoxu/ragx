from pydantic import BaseModel
from sqlmodel import SQLModel, Field


class FileMgrConfig(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    top_group_id: int
    parse_after_upload: bool
    pdf_parser_url: str


class ParseFileRequest(BaseModel):
    file_node_ids: list[str]
    top_group_id: int
    kb_id: str | None


class FilesRequest(BaseModel):
    top_group_id: int
    kb_id: str | None = None
    file_node_ids: list[str]
