import time
from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from db.database import get_session
from db.db_init import get_user_level
from .auth import get_current_user, get_password_hash
from .crud import UserApi
from .group_api import top_group_by_group_id
from .model import UserRoleLink, User, UserVo, UserUpdate, Role

router = APIRouter(prefix="/user", tags=["user"])


def get_role_ids_by(user_id: int, db: Session):
    return db.exec(select(UserRoleLink.role_id).where(UserRoleLink.user_id == user_id))


def db_user_to_vo(db_user: User, db: Session) -> UserVo:
    return UserVo(**{**db_user.model_dump()},
                  role_ids=get_role_ids_by(db_user.id, db),
                  level=get_user_level(db_user))


@router.get("/my_info", response_model=UserVo)
def get_user_info(user: User = Depends(get_current_user), db: Session = Depends(get_session)) -> UserVo:
    return db_user_to_vo(user, db)


@router.get("/list", response_model=list[UserVo])
def get_user_list(group_id: int | None = None,
                  cur_user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)) -> list[UserVo]:
    users = UserApi.get_user_list(group_id, db)
    if cur_user.level > 2:
        users = [user for user in users if user.top_group_id == cur_user.top_group_id]
    return [db_user_to_vo(user, db) for user in users]


@router.put('', response_model=UserVo)
def add_user(user: UserUpdate,
             db: Session = Depends(get_session)) -> UserVo:
    db_user = User(**user.model_dump())
    db_user.id = None
    db_user.create_time = time.time()
    db_user.hashed_password = get_password_hash(user.password)
    db_user.roles = db.exec(select(Role).where(Role.id.in_(user.role_ids))).all()

    if user.group_id:
        db_user.top_group_id = top_group_by_group_id(user.group_id, db).id

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user_to_vo(db_user, db)


@router.post('')
def update_user(user: UserUpdate, db: Session = Depends(get_session)) -> None:
    db_user = db.get(User, user.id)

    # update top group id
    # 只有在从租户外移动到租户内才可能，租户内的用户不能移动出来。
    if user.group_id and db_user.group_id != user.group_id:
        user.top_group_id = top_group_by_group_id(user.group_id, db).id

    update_data = user.model_dump(exclude_unset=True, exclude={'id', 'create_time'})
    db_user.sqlmodel_update(update_data)
    if 'role_ids' in update_data:
        db_user.roles = db.exec(select(Role).where(Role.id.in_(user.role_ids))).all()
    if user.password:
        db_user.hashed_password = get_password_hash(user.password)
    db.add(db_user)
    db.commit()


@router.delete('/{user_id:path}')
def delete_user(user_id: int, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if user:
        db.delete(user)
        db.commit()
