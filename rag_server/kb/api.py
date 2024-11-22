import time
from typing import cast

from fastapi import APIRouter, Depends
from rag_file_sdk.dir_api import DirMgr
from sqlalchemy import delete
from sqlmodel import Session, select

from app.crud import get_app_list_by_top_group_id
from celery_task.celery_app import reset_vector_store
from config.config import config
from db.database import get_session
from error_code import raise_exception, ErrorCode
from file_mgr.crud import FileMgrApi
from kb.crud import add_kb_dir, delete_kb_dir, get_kb_dir_name, get_kb_config
from kb.crud import add_config, delete_config
from kb.model import Kb, KbConfig, KbMemberVo, KbMember
from store_retriever_server.store_engine import StoreEngine
from user_role_group_mgr.auth import get_current_user
from user_role_group_mgr.model import User
from store_retriever_server.api import get_kb_vecstore_name
from util import check_permission

router = APIRouter(prefix="/kb", tags=["knowledge base"])


@router.get("/dir_root_id_by_kb")
def get_dir_root_id_by_kb(kb_id: str) -> str:
    return DirMgr(config.file_server_url).get_by_name(get_kb_dir_name(kb_id), FileMgrApi.get_root_dir_id()).id


@router.get('/list', response_model=list[Kb])
def get_kb_list(top_group_id: int,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_session)) -> list[Kb]:
    check_permission(top_group_id, user)
    return cast(list[Kb], db.exec(select(Kb).where(Kb.top_group_id == top_group_id)).all())


@router.put('', response_model=Kb)
def add_kb(kb: Kb,
           user: User = Depends(get_current_user),
           db: Session = Depends(get_session)) -> Kb:
    check_permission(kb.top_group_id, user)

    kb.id = None
    kb.create_user_id = user.id
    kb.create_time = time.time()
    db.add(kb)
    db.commit()
    db.refresh(kb)
    assert kb.id is not None
    add_kb_dir(kb.id)
    add_config(kb.id, db)
    reset_vector_store.delay(kb.id)
    return kb


@router.post('')
def update_kb(kb: Kb,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_session)):
    check_permission(kb.top_group_id, user)
    db_kb = db.get_one(Kb, kb.id)
    db_kb.sqlmodel_update(kb.model_dump(exclude={'create_user_id', 'create_time', 'top_group_id'}, exclude_unset=True))
    db.add(db_kb)
    db.commit()


@router.delete('/{kb_id:path}')
def delete_kb(kb_id: str,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_session)):
    kb = db.get(Kb, kb_id)
    check_permission(kb.top_group_id, user)

    # 查看引用，被引用的知识库无法删除
    for app in get_app_list_by_top_group_id(kb.top_group_id, db):
        if kb_id in app.kb_ids:
            raise_exception(ErrorCode.KB_USED_BY_APP, app.name)

    db.delete(kb)
    db.commit()
    delete_kb_dir(kb.id)
    delete_config(kb.id, db)
    StoreEngine(get_kb_vecstore_name(kb.id)).delete_store()


@router.get('/kb/{kb_id:path}', response_model=Kb)
def get_kb_by_id(kb_id: str,
                 user: User = Depends(get_current_user),
                 db: Session = Depends(get_session)) -> Kb:
    kb = db.get_one(Kb, kb_id)
    check_permission(kb.top_group_id, user)
    return cast(Kb, kb)


@router.post('/list_by_ids', response_model=list[Kb])
def get_kb_by_ids(kb_ids: list[str],
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_session)) -> list[Kb]:
    kb_list = cast(list[Kb], db.exec(select(Kb).where(Kb.id.in_(kb_ids))).all())
    for kb in kb_list:
        check_permission(kb.top_group_id, user)
    return kb_list


@router.get('/total_files')
def get_total_files(kb_id: str) -> int:
    dir_id = get_dir_root_id_by_kb(kb_id)
    dir_mgr = DirMgr(config.file_server_url)
    return dir_mgr.get_total_files(dir_id)


@router.get("/config/{kb_id:path}", response_model=KbConfig)
def get_kb_config_api(kb_id: str,
                      db: Session = Depends(get_session)) -> KbConfig:
    return get_kb_config(kb_id, db)


@router.post("/config")
def update_kb_config(kb_config: KbConfig,
                     db: Session = Depends(get_session)):
    config_in_db = db.get_one(KbConfig, kb_config.id)
    config_in_db.sqlmodel_update(kb_config)
    db.add(config_in_db)
    db.commit()


@router.get("/members/{kb_id:path}", response_model=list[KbMemberVo])
def get_kb_members(kb_id: str, db: Session = Depends(get_session)) -> list[KbMemberVo]:
    stmt = select(KbMember).where(KbMember.kb_id == kb_id)
    members = cast(list[KbMember], db.exec(stmt).all())
    member_ids = [member.user_id for member in members]
    stmt = select(User.id, User.name).where(User.id.in_(member_ids))
    users = cast(list[User], db.exec(stmt).all())
    user_map = {user.id: user.name for user in users}
    return [KbMemberVo(**member.model_dump(), user_name=user_map.get(member.user_id)) for member in members]


@router.post("/members/{kb_id:path}")
def update_kb_members(kb_id: str,
                      members: list[KbMember],
                      db: Session = Depends(get_session)):
    stmt = delete(KbMember).where(KbMember.kb_id == kb_id)
    db.exec(stmt)
    db.add_all(members)
    db.commit()
