import time
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy import update, delete
from sqlmodel import Session, select

from db.database import get_session
from error_code import raise_exception, ErrorCode
from file_mgr.crud import FileMgrApi
from kb.api import delete_kb
from kb.model import Kb
from .auth import get_current_user
from .model import Group, User, GroupVo, Status, GroupBase, Role

router = APIRouter(prefix="/group", tags=["group"])


def list_groups(parent_id: int | None, db: Session) -> list[GroupVo]:
    stmt = select(Group).where((Group.parent_id == parent_id) & (Group.status != Status.DELETED))
    groups = cast(list[Group], db.exec(stmt).all())
    user_ids = [group.create_user_id for group in groups]
    users = db.exec(select(User).where(User.id.in_(user_ids)))
    user_map: dict[int, User] = {user.id: user for user in users}

    def get_user_name(user_id: int) -> str:
        return user_map[user_id].name if user_id in user_map else None

    groups_vo = [GroupVo.model_validate(group) for group in groups][::-1]
    for group_vo in groups_vo:
        group_vo.create_user_name = get_user_name(group_vo.create_user_id)
    return groups_vo


def top_group_by_group_id(group_id: int, db: Session):
    group = db.get_one(Group, group_id)
    while group.parent_id:
        group = db.get(Group, group.parent_id)
    return group


@router.get("/list_top", response_model=list[GroupVo])
def list_top_group(user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> list[GroupVo]:
    groups = list_groups(None, db)
    if user.level <= 2:
        return groups

    return [group for group in groups if group.id == user.top_group_id]


def list_group_tree_dfs(group_vo: GroupVo, db: Session, deep: int, with_user: bool = False) -> None:
    group_vo.children = list_groups(group_vo.id, db)
    for child in group_vo.children:
        child.deep = deep
        list_group_tree_dfs(child, db, deep + 1)


@router.get("/tree", response_model=GroupVo)
def get_group_tree(root_id: int | None = None,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_session)) -> GroupVo:
    if root_id:
        if user.top_group_id != root_id:
            raise_exception(ErrorCode.NO_PERMISSION)

        root_group = cast(Group, db.get_one(Group, root_id))
        root = GroupVo.model_validate(root_group)
        list_group_tree_dfs(root, db, 1)
    else:
        root = GroupVo(id=None, name='ROOT')
        root.children = list_top_group(user, db)
        for child in root.children:
            child.deep = 1
            list_group_tree_dfs(child, db, 2)

    return root


def check_permission(user: User, group: GroupBase, db: Session):
    if user.level > 4:
        raise_exception(ErrorCode.NO_PERMISSION)
    elif user.level > 2:
        # 非系统管理员，不能操作顶层group
        if group.parent_id is None:
            raise_exception(ErrorCode.NO_PERMISSION)
        # 组管理员，只能操作所在租户的组
        if user.top_group_id != top_group_by_group_id(group.parent_id, db):
            raise_exception(ErrorCode.NO_PERMISSION)


@router.put('', response_model=GroupVo)
def add_group(group: Group,
              db: Session = Depends(get_session),
              user: User = Depends(get_current_user)) -> GroupVo:
    check_permission(user, group, db)
    group.id = None
    group.create_time = time.time()
    group.create_user_id = user.id
    db.add(group)
    db.commit()
    db.refresh(group)
    #
    group_dict = {**group.model_dump(), 'create_user_name': user.name}
    group_vo = GroupVo.model_validate(group_dict)

    # 如果是顶层，要增加对应的文件根目录
    if group.parent_id is None:
        assert group.id is not None
        FileMgrApi.add_tenant_dir(group.id)
        FileMgrApi.add_file_mgr_config(group.id, db)

    return group_vo


@router.post('')
def update_group(group: Group,
                 db: Session = Depends(get_session),
                 user: User = Depends(get_current_user)) -> None:
    check_permission(user, group, db)
    group_ = group.model_dump(exclude_unset=True, exclude={'id', 'create_time', 'create_user_id'})
    stmt = update(Group).where(Group.id == group.id).values(**group_)
    db.execute(stmt)
    db.commit()


def collect_group_ids_dfs(group: GroupVo, db: Session = Depends(get_session)) -> list[int]:
    ret = [group.id]
    for child in group.children:
        ret.extend(collect_group_ids_dfs(child, db))
    return ret


@router.delete('/{group_id:path}')
def delete_group(group_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    group = GroupVo(**cast(Group, db.get_one(Group, group_id)).model_dump())

    check_permission(user, group, db)

    list_group_tree_dfs(group, db, 1)
    ids = collect_group_ids_dfs(group, db)
    groups = cast(list[Group], db.exec(select(Group).where(Group.id.in_(ids))))

    # 因为 ondelete="CASCADE" 不太靠谱，所以只能手动删除关联用户和角色。
    # for group in groups:
    #     db.delete(group)

    group_ids = [group.id for group in groups]
    user_ids = db.exec(select(User.id).where(User.group_id.in_(group_ids)))
    role_ids = db.exec(select(Role.id).where(Role.group_id.in_(group_ids)))
    db.exec(delete(User).where(User.id.in_(user_ids)))
    db.exec(delete(Role).where(Role.id.in_(role_ids)))
    db.exec(delete(Group).where(Group.id.in_(group_ids)))
    db.commit()

    # if is top group, delete file manager dir, config and kb list
    if group.parent_id is None:
        FileMgrApi.delete_tenant_dir(group_id)
        FileMgrApi.delete_file_mgr_config(group_id, db)

        kb_ids = db.exec(select(Kb.id).where(Kb.top_group_id == group_id)).all()
        for kb_id in kb_ids:
            delete_kb(kb_id, user, db)


@router.get("/tree_with_user", response_model=GroupVo)
def get_group_tree_with_user(top_group_id: int,
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_session)) -> GroupVo:
    root_group = cast(Group, db.get_one(Group, top_group_id))
    root_vo = GroupVo.model_validate(root_group)
    list_group_tree_dfs(root_vo, db, 1)
    return root_vo
