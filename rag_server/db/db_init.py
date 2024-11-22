from sqlmodel import Session, select

from db.database import engine
from user_role_group_mgr.auth import get_password_hash
from user_role_group_mgr.group_api import add_group
from user_role_group_mgr.model import User, Role, default_role_level, Group, GroupVo


def add_admin_role(name: str, desc: str, level: int, db: Session) -> Role:
    role = db.exec(select(Role).where(Role.name == name)).first()
    if role is None:
        role = Role(name=name, description=desc, level=level)
        db.add(role)
    return role


def add_user(name: str, password: str, role: Role | None, db: Session) -> User:
    user = db.exec(select(User).where(User.name == name)).first()
    if user is None:
        user = User(name=name, hashed_password=get_password_hash(password), roles=[role] if role else [])
        db.add(user)
    return user


def add_top_group(name: str, db: Session, user: User) -> GroupVo:
    group = db.exec(select(Group).where(Group.name == name)).first()
    if group is None:
        group = add_group(Group(name=name), db, user)
    return group


root_user_id: int


def init_db():
    global root_user_id

    with Session(engine) as db:
        root_user = add_user('root', 'root', None, db)
        super_admin = add_admin_role('系统超级管理员', "系统超级管理员", 1, db)
        add_admin_role('系统管理员', "系统管理员", 2, db)
        add_admin_role('组超级管理员', "组超级管理员", 3, db)
        add_admin_role('组管理员', "组管理员", 4, db)
        add_user('zhiguo', 'zhi', super_admin, db)
        add_user('admin', 'admin', super_admin, db)
        db.commit()
        db.refresh(root_user)
        root_user_id = root_user.id
        assert root_user_id == 1

        add_top_group('租户一', db, root_user)
        add_top_group('租户二', db, root_user)
        db.commit()


def get_user_level(user: User) -> int:
    if user.id == root_user_id:
        return 0

    level = default_role_level
    for role in user.roles:
        level = min(level, role.level)
    return level


"""
角色和权限设计：
内置一个 root 账号，4个管理角色，其权限范围依次严格递减，并且不可编辑（即使root也不可以）。
Level-0,【root】账号拥有所有权限；
Level-1,【系统超级管理员】角色，和 Level-0 的区别是没有给用户增加【系统超级管理员】角色的能力；
Level-2,【系统管理员】角色，和 Level-1 的区别是没有给用户增加【系统管理员】角色的能力；
Level-3,【组超级管理员】角色，只能看到属于自己租户的用户，并且不能给用户增加除【组管理员】的任何其他管理权限；
Level-4,【组管理员】角色，和Level-3的区别是不能给用户增加任何管理权限；
Level-0 ~ 2 不属于任何租户，Level-3，Level-4 必须属于某个租户，并且只能看见和管理组内用户。
管理员 = 有管理角色的用户，他们的职责是：
    1、管理普通用户，包括创建、删除、设置组、修改密码、设置角色；
    2、管理角色（除管理角色），包括创建、删除角色，配置角色权限；
    3、管理组（Level-3 以上），组是租户内的用户组织结构，一个用户只属于一个组。
    4、管理租户（Level-2 以上）

管理员创建的角色一般属于某个租户，并且相互隔离，租户内的角色和租户的成员是对应的。
Level-2 以上的管理员可创建不属于租户的角色，对租户不可见，只能应用在租户外的用户（一般是管理员）
"""
