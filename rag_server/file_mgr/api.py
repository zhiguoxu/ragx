import asyncio
import json
from typing import cast, Annotated, Literal

import requests
from fastapi import APIRouter, Depends, UploadFile, Form, HTTPException
from rag_file_sdk.dir_api import DirMgr
from rag_file_sdk.file_api import Bucket
from rag_file_server.dir.model import UploadResponseOfDir

from sqlmodel import Session, select

from config.config import config
from db.database import get_session
from file_mgr.crud import FileMgrApi
from file_mgr.model import FileMgrConfig, ParseFileRequest, FilesRequest
from kb.crud import get_kb_dir_name, get_kb_config
from store_retriever_server.crud import get_kb_vecstore_name
from store_retriever_server.store_engine import StoreEngine

router = APIRouter(prefix="/file_mgr", tags=["file manager"])

dir_mgr = DirMgr(config.file_server_url)


@router.get("/dir_root_id_by_top_group")
def get_dir_root_id_by_top_group(top_group_id: int) -> str:
    return dir_mgr.get_by_name(FileMgrApi.get_top_group_dir_name(top_group_id), FileMgrApi.get_root_dir_id()).id


@router.get("/config/{top_group_id:path}", response_model=FileMgrConfig)
def get_file_mgr_config(top_group_id: int,
                        db: Session = Depends(get_session)) -> FileMgrConfig:
    stmt = select(FileMgrConfig).where(FileMgrConfig.top_group_id == top_group_id)
    return cast(FileMgrConfig, db.exec(stmt).one())


@router.post("/config")
def update_file_mgr_config(file_mgr_config: FileMgrConfig,
                           db: Session = Depends(get_session)):
    config_in_db = db.get_one(FileMgrConfig, file_mgr_config.id)
    config_in_db.sqlmodel_update(file_mgr_config)
    db.add(config_in_db)
    db.commit()


@router.put("/files", response_model=UploadResponseOfDir)
def add_files(files: list[UploadFile],
              top_group_id: Annotated[int, Form()],
              kb_id: Annotated[str | None, Form()] = None,
              parent_id: Annotated[str | None, Form()] = None,
              action: Annotated[Literal['override', 'ignore'], Form()] = 'ignore',
              db: Session = Depends(get_session)) -> UploadResponseOfDir:
    file_name_list = [file.filename for file in files]
    content_list = [asyncio.run(file.read()) for file in files]
    resp = dir_mgr.add_files(file_name_list, content_list, parent_id, action)
    if kb_id:
        kb_config = get_kb_config(kb_id, db)
        parse_after_upload = kb_config.parse_after_upload
    else:
        file_mgr_config = get_file_mgr_config(top_group_id, db)
        parse_after_upload = file_mgr_config.parse_after_upload
    if parse_after_upload:
        FileMgrApi.parse_files(resp.file_nodes, top_group_id, kb_id)
    return resp


@router.delete("/files")
def delete_files(request: FilesRequest) -> None:
    if request.kb_id:
        vector_store_mgr = StoreEngine(get_kb_vecstore_name(request.kb_id))
        for file_id in request.file_node_ids:
            vector_store_mgr.delete_doc(file_id)

    # 删除相关的其他文件
    if request.kb_id:
        dir_name = get_kb_dir_name(request.kb_id)
    else:
        dir_name = FileMgrApi.get_top_group_dir_name(request.top_group_id)
    bucket = Bucket(config.file_server_url, dir_name)
    all_files = dir_mgr.get_files_by_ids(request.file_node_ids)
    bucket.delete_files([file.storage_key + ".md.json" for file in all_files])
    bucket.delete_files([file.storage_key + ".md.split.json" for file in all_files])

    dir_mgr.delete_files(request.file_node_ids)


@router.post("/update_file")
def update_file(file: UploadFile,
                file_node_id: Annotated[str, Form()],
                top_group_id: Annotated[int, Form()],
                kb_id: Annotated[str | None, Form()] = None,
                db: Session = Depends(get_session)):
    if kb_id:
        dir_name = get_kb_dir_name(kb_id)
    else:
        dir_name = FileMgrApi.get_top_group_dir_name(top_group_id)
    bucket = Bucket(config.file_server_url, dir_name)
    content = asyncio.run(file.read())
    bucket.set_file(file.filename, content, True)

    # 删除旧 split 文件
    if file.filename.endswith(".md.json"):
        bucket.delete_file(f"{file_node_id}.md.split.json")
        dir_mgr.update_files([file_node_id], {'revision_not_in_vector_store': True})


@router.post("/parse_files")
def parse_files_api(request: ParseFileRequest) -> None:
    FileMgrApi.parse_files(dir_mgr.get_files_by_ids(request.file_node_ids), request.top_group_id, request.kb_id)


@router.get('/split_list')
def get_split_list(kb_id: str, file_node_id: str) -> list[str]:
    file_node = dir_mgr.get_files_by_ids([file_node_id])[0]
    bucket = Bucket(config.file_server_url, get_kb_dir_name(kb_id))
    try:
        split_data = json.loads(bucket.get_str(file_node.storage_key + ".md.split.json"))
    except HTTPException as e:
        assert e.status_code == 522
        md_list = cast(list[str], json.loads(bucket.get_str(file_node.storage_key + ".md.json")))
        resp = requests.post(config.default_splitter_url, json={"text": '\n'.join(md_list)})
        split_data = cast(list[str], resp.json())
        bucket.set_str(file_node.storage_key + ".md.split.json", json.dumps(split_data))
    return split_data
