import time
import uuid
from enum import Enum

from pydantic import BaseModel
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel, Relationship


class ChatRequest(BaseModel):
    app_id: str
    session_id: str | None
    input_text: str


class ChatSessionType(str, Enum):
    NORMAL = 'normal'
    TEST = 'test'


class ChatSession(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    app_id: str
    user_id: int
    name: str = "新会话"
    create_time: float = Field(default_factory=time.time)
    records: list['ChatRecord'] = Relationship(back_populates="session", passive_deletes="all")
    type: ChatSessionType

    def model_dump(self, *args, include=None, exclude=None, **kwargs):
        # 调用父类的 model_dump 方法获取默认字典
        ret_dict = super().model_dump(*args, include=include, exclude=exclude, **kwargs)
        # 将属性添加到字典中
        ret_dict['records'] = self.records
        return ret_dict


class ChatRecord(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    timestamp: float = Field(default_factory=time.time)
    message: dict = Field(sa_column=Column(JSON))  # ChatMessage

    session_id: str | None = Field(foreign_key="chatsession.id", ondelete="CASCADE")
    session: ChatSession = Relationship(back_populates="records")
