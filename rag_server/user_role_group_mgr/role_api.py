import time
from typing import cast

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import update
from sqlmodel import Session, select

from db.database import get_session
from db.db_init import get_user_level
from .auth import get_current_user
from .model import RoleVo, User, Role, Group, Status

router = APIRouter(prefix="/role", tags=["role"])


@router.get("/list", response_model=list[RoleVo])
def get_role_list(user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> list[RoleVo]:
    roles = cast(list[Role], db.exec(select(Role)).all())
    user_ids = {role.create_user_id for role in roles if role.create_user_id}
    users = cast(list[User], db.exec(select(User).where(User.id.in_(user_ids))).all())
    user_name_map = {user.id: user.name for user in users}
    return [RoleVo(**{**role.model_dump(), 'create_user_name': user_name_map.get(role.create_user_id)})
            for role in roles]


class GroupRolesResp(BaseModel):
    group_id: int | None
    group_name: str
    roles: list[RoleVo]


@router.get("/list_in_group", response_model=list[GroupRolesResp])
def get_group_roles_list(user: User = Depends(get_current_user),
                         db: Session = Depends(get_session)) -> list[GroupRolesResp]:
    level = get_user_level(user)
    if level <= 2:  # 系统管理员级别
        stmt = select(Group).where((Group.parent_id == None) & (Group.status != Status.DELETED))
        groups = cast(list[Group], db.exec(stmt).all())
        roles = cast(list[Role], db.exec(select(Role).where(Role.group_id == None)).all())
        groups.insert(0, Group(name='ROOT', roles=roles))
    elif user.top_group_id and level <= 4:  # 组内管理员级别
        groups = [db.get(Group, user.top_group_id)]
    else:  # 非管理员，或组管理员不再组内
        groups = []

    user_ids = {role.create_user_id for group in groups for role in group.roles if role.create_user_id}
    users = cast(list[User], db.exec(select(User).where(User.id.in_(user_ids))).all())
    user_name_map = {user.id: user.name for user in users}

    return [GroupRolesResp(group_id=group.id,
                           group_name=group.name,
                           roles=[RoleVo(
                               **{**role.model_dump(), 'create_user_name': user_name_map.get(role.create_user_id)})
                               for role in group.roles]
                           ) for group in groups]


@router.put('', response_model=RoleVo)
def add_role(role: Role,
             db: Session = Depends(get_session),
             user: User = Depends(get_current_user)) -> RoleVo:
    role.id = None
    role.create_time = time.time()
    role.create_user_id = user.id
    db.add(role)
    db.commit()
    db.refresh(role)
    return RoleVo(**{**role.model_dump(), 'create_user_name': user.name})


@router.post('')
def update_role(role: Role,
                db: Session = Depends(get_session),
                user: User = Depends(get_current_user)) -> None:
    role_ = role.model_dump(exclude_unset=True, exclude={'id', 'create_time', 'create_user_id'})
    stmt = (
        update(Role)
        .where(Role.id == role.id)
        .values(**role_)
    )
    db.execute(stmt)
    db.commit()


@router.delete('/{role_id:path}')
def delete_role(role_id: int, db: Session = Depends(get_session)):
    role = db.get(Role, role_id)
    if role:
        db.delete(role)
        db.commit()
