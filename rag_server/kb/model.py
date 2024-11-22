import uuid
from enum import Enum

from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field


class KbBase(SQLModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    top_group_id: int
    name: str
    description: str = ''
    create_time: float = 0
    create_user_id: int | None = None


class Kb(KbBase, table=True):
    __table_args__ = (UniqueConstraint("name", "top_group_id", name="unique_name"),)


class AccessBy(str, Enum):
    MEMBER = 'member'
    GROUP = 'group'
    ALL = 'all'


class KbConfig(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    kb_id: str | None = Field(default=None, unique=True)
    parse_after_upload: bool
    pdf_parser_url: str
    access_by: AccessBy = AccessBy.MEMBER


class KbPermission(str, Enum):
    READ = 'read'
    WRITE = 'write'
    MANAGE = 'manage'


class KbMemberBase(SQLModel):
    kb_id: str = Field(primary_key=True)
    user_id: int = Field(primary_key=True)
    permission: KbPermission


class KbMember(KbMemberBase, table=True):
    ...


class KbMemberVo(KbMemberBase):
    user_name: str
