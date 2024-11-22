from typing import cast

from rag_file_sdk.dir_api import DirMgr
from rag_file_sdk.file_api import Bucket
from sqlmodel import Session, select

from config.config import config
from file_mgr.crud import FileMgrApi
from kb.model import KbConfig

dir_mgr = DirMgr(config.file_server_url)


def get_kb_dir_name(kb_id: str) -> str:
    return f"__kb_dir_{kb_id}__"


def get_bucket_by_kb(kb_id: str) -> Bucket:
    kb_dir_name = get_kb_dir_name(kb_id)
    return Bucket(config.file_server_url, kb_dir_name)


def add_kb_dir(kb_id: str):
    dir_mgr.add_dir(get_kb_dir_name(kb_id), FileMgrApi.get_root_dir_id())
    get_bucket_by_kb(kb_id).create_bucket()


def delete_kb_dir(kb_id: str):
    kb_dir_name = get_kb_dir_name(kb_id)
    file_id = dir_mgr.get_by_name(kb_dir_name, FileMgrApi.get_root_dir_id()).id
    dir_mgr.delete_files([file_id])
    get_bucket_by_kb(kb_id).delete_bucket()


def add_config(kb_id: str, db: Session):
    db.add(KbConfig(kb_id=kb_id,
                    parse_after_upload=True,
                    pdf_parser_url=config.default_pdf_parser_url))
    db.commit()


def delete_config(kb_id: str, db: Session):
    stmt = select(KbConfig).where(KbConfig.kb_id == kb_id)
    item = db.exec(stmt).one()
    db.delete(item)
    db.commit()


def get_kb_config(kb_id: str, db: Session) -> KbConfig:
    stmt = select(KbConfig).where(KbConfig.kb_id == kb_id)
    return cast(KbConfig, db.exec(stmt).one())
