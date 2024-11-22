import json
import uuid
from enum import Enum

from pydantic import BaseModel
from sqlmodel import SQLModel, Field
from sqlalchemy import JSON, Column, UniqueConstraint


class AppType(str, Enum):
    SIMPLE = 'simple'


class LLMConfig(BaseModel):
    temperature: float = 0.01
    greedy: bool = False
    max_new_tokens: int = 1024
    top_p: float | None = None
    repetition_penalty: float | None = None


class AppBase(SQLModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    type: AppType
    top_group_id: int
    name: str
    description: str = ''
    create_time: float = 0
    create_user_id: int | None = None
    llm_id: int = 1
    llm_config: dict = Field(default=LLMConfig().model_dump(), sa_column=Column(JSON))
    kb_ids_str: str = '[]'

    def __init__(self, **kwargs):
        if 'kb_ids' in kwargs and 'kb_ids_str' not in kwargs:
            kwargs['kb_ids_str'] = json.dumps(kwargs.get('kb_ids'))
        super().__init__(**kwargs)

    @property
    def kb_ids(self) -> list[str]:
        return json.loads(self.kb_ids_str)

    @kb_ids.setter
    def kb_ids(self, value: list[str]):
        self.kb_ids_str = json.dumps(value)

    def model_dump(self, *args, include=None, exclude=None, **kwargs):
        # 调用父类的 model_dump 方法获取默认字典
        ret_dict = super().model_dump(*args, include=include, exclude=exclude, **kwargs)
        # 将属性添加到字典中
        ret_dict['kb_ids'] = self.kb_ids
        return ret_dict


class App(AppBase, table=True):
    __table_args__ = (UniqueConstraint("name", "top_group_id", name="unique_name"),)
