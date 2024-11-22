from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field

from rag_file_server.file.model import MetaData, UploadResponse


class FileType(str, Enum):
    FILE = 'file'
    DIR = 'dir'


class FileStatus(str, Enum):
    UPLOADED = 'uploaded'
    PARSING = 'parsing'
    PARSED = 'parsed'
    PARSE_FAILED = 'parse_failed'
    TO_VECTOR_STORE_ING = 'to_vector_store_ing'
    IN_VECTOR_STORE = 'in_vector_store'
    TO_VECTOR_STORE_FAILED = 'to_vector_store_failed'


class CeleryTaskType(str, Enum):
    PARSE = 'parse'
    TO_VECTOR_STORE = 'to_vector_store'


class FileNodeBase(SQLModel):
    id: str | None = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    type: FileType
    parent_id: str | None = Field(index=True)
    name: str = Field(index=True)
    status: FileStatus = FileStatus.UPLOADED
    parse_percent: float = -1
    to_vector_store_percent: float = -1
    celery_task_id: str | None = None
    celery_task_type: CeleryTaskType | None = None
    revision_not_in_vector_store: bool | None = None

    @property
    def storage_key(self):
        index = self.name.rfind('.')
        return f"{self.id}{self.name[index:]}"


class FileNode(FileNodeBase, table=True):
    __table_args__ = (
        UniqueConstraint('name', 'parent_id'),
    )


class FileNodeVo(FileNodeBase, MetaData):
    children: list[FileNodeVo] = Field(default_factory=list)


class AddDirRequest(BaseModel):
    name: str
    parent_id: str | None = None


class UpdateFileRequest(BaseModel):
    id_list: list[str]
    name: str | None = None
    parent_id: str | None = None
    status: FileStatus | None = None
    parse_percent: float | None = None
    to_vector_store_percent: float | None = None
    celery_task_id: str | None = None
    celery_task_type: CeleryTaskType | None = None
    revision_not_in_vector_store: bool = False


class UploadResponseOfDir(UploadResponse):
    file_nodes: list[FileNode]


class CeleryTaskFailedRequest(BaseModel):
    task_id: str
