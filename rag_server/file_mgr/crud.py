import json
from typing import cast, Tuple

import requests
from fastapi import HTTPException
from rag_file_sdk.dir_api import DirMgr
from rag_file_sdk.file_api import Bucket
from rag_file_server.dir.model import FileNode, FileStatus, CeleryTaskType
from sqlmodel import Session, select

from config.config import config
from file_mgr.model import FileMgrConfig

dir_mgr = DirMgr(config.file_server_url)


class FileMgrApi:
    @staticmethod
    def get_root_dir_id() -> str:
        return dir_mgr.get_by_name(config.tenants_files_root_dir).id

    @staticmethod
    def get_top_group_dir_name(top_group_id: int) -> str:
        return f"__top_group_dir_{top_group_id}__"

    @staticmethod
    def add_tenant_dir(top_group_id: int):
        try:
            dir_mgr.add_dir(config.tenants_files_root_dir)
        except Exception as e:
            ...
        file_node = dir_mgr.add_dir(FileMgrApi.get_top_group_dir_name(top_group_id), FileMgrApi.get_root_dir_id())
        Bucket(config.file_server_url, file_node.name).create_bucket()

    @staticmethod
    def delete_tenant_dir(top_group_id: int):
        top_group_dir = FileMgrApi.get_top_group_dir_name(top_group_id)
        file_id = dir_mgr.get_by_name(top_group_dir, FileMgrApi.get_root_dir_id()).id
        dir_mgr.delete_files([file_id])
        Bucket(config.file_server_url, top_group_dir).delete_bucket()

    @staticmethod
    def add_file_mgr_config(top_group_id: int, db: Session):
        db.add(FileMgrConfig(top_group_id=top_group_id,
                             parse_after_upload=True,
                             pdf_parser_url=config.default_pdf_parser_url))
        db.commit()

    @staticmethod
    def delete_file_mgr_config(top_group_id: int, db: Session):
        stmt = select(FileMgrConfig).where(FileMgrConfig.top_group_id == top_group_id)
        item = db.exec(stmt).one()
        db.delete(item)
        db.commit()

    @staticmethod
    def parse_files(file_nodes: list[FileNode], top_group_id: int, kb_id: str | None) -> None:
        from kb.crud import get_kb_dir_name

        from celery_task.celery_app import parse_pdf
        bucket_name = get_kb_dir_name(kb_id) if kb_id else FileMgrApi.get_top_group_dir_name(top_group_id)
        file_key_list = [file_node.storage_key for file_node in file_nodes]
        file_node_ids = [str(file_node.id) for file_node in file_nodes]

        # 所有文件一个任务
        # task_id = parse_pdf.delay(bucket_name, file_key_list, file_node_ids).id
        # dir_mgr.update_files_status(file_node_ids, FileStatus.PARSING)
        # dir_mgr.update_celery_task(file_node_ids, task_id, CeleryTaskType.PARSE)

        # 每个文件独立任务
        dir_mgr.update_parse_percent(file_node_ids, 0)
        for file_key, file_node_id in zip(file_key_list, file_node_ids):
            dir_mgr.update_files_status([file_node_id], FileStatus.PARSING)
            task_id = parse_pdf.delay(bucket_name, [file_key], [file_node_id]).id
            dir_mgr.update_celery_task([file_node_id], task_id, CeleryTaskType.PARSE)
