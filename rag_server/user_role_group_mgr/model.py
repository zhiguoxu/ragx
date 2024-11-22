from enum import Enum
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship

default_role_level = 999


class Status(str, Enum):
    NORMAL = 'normal'
    DISABLED = 'disabled'
    DELETED = 'deleted'


class RolePermissionLink(SQLModel, table=True):
    role_id: int | None = Field(default=None, foreign_key="role.id", primary_key=True)
    permission_id: int | None = Field(default=None, foreign_key="permission.id", primary_key=True)


class UserRoleLink(SQLModel, table=True):
    user_id: int | None = Field(default=None, foreign_key="user.id", primary_key=True)
    role_id: int | None = Field(default=None, foreign_key="role.id", primary_key=True)


class RoleBase(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    create_user_id: int | None = None
    create_time: float = 0
    level: int = default_role_level
    group_id: int | None = Field(default=None, foreign_key="group.id", ondelete="CASCADE")


class Role(RoleBase, table=True):
    permissions: list["Permission"] = Relationship(back_populates="roles", link_model=RolePermissionLink)
    users: list["User"] = Relationship(back_populates="roles", link_model=UserRoleLink)
    group: Optional["Group"] = Relationship(back_populates="roles")

    __table_args__ = (UniqueConstraint("name", "group_id", name="unique_name"),)


class RoleVo(RoleBase):
    permissions: list["Permission"] = Field(default_factory=list)
    create_user_name: str | None = None


class Permission(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    description: str | None = None
    roles: list[Role] = Relationship(back_populates="permissions", link_model=RolePermissionLink)


class GroupBase(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str | None = None
    parent_id: int | None = Field(default=None, index=True)
    create_time: float = 0
    create_user_id: int | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    status: Status = Status.NORMAL

    __table_args__ = (UniqueConstraint("name", "parent_id", name="unique_name"),)


class Group(GroupBase, table=True):
    users: list['User'] = Relationship(back_populates="group", passive_deletes="all")
    roles: list['Role'] = Relationship(back_populates="group", passive_deletes="all")


class GroupVo(GroupBase):
    users: list['UserVo'] = Field(default_factory=list)
    create_user_name: str | None = None
    children: list['GroupVo'] = Field(default_factory=list)
    deep: int = 0


class UserBase(SQLModel):
    id: int | None = Field(default=None, primary_key=True)
    group_id: int | None = Field(default=None, foreign_key="group.id", ondelete="CASCADE")
    top_group_id: int | None = None
    create_time: float = 0


class User(UserBase, table=True):
    name: str = Field(index=True, unique=True)
    hashed_password: str | None = None
    roles: list[Role] = Relationship(back_populates="users", link_model=UserRoleLink)
    group: Group | None = Relationship(back_populates="users")

    @property
    def level(self) -> int:
        if self.id == 1:
            return 0

        level = default_role_level
        for role in self.roles:
            level = min(level, role.level)
        return level


class UserVo(UserBase):
    name: str | None = None
    role_ids: list[int] = Field(default_factory=list)
    level: int = default_role_level


class UserUpdate(UserVo):
    password: str | None = None
