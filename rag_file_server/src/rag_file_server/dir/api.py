import asyncio
import io
import mimetypes
import time
import urllib
import uuid
import zipfile
from itertools import chain
from pathlib import Path
from typing import cast, Annotated, Literal, Sequence

from fastapi import APIRouter, Depends, UploadFile, Form, Query
from sqlalchemy.exc import NoResultFound
from sqlmodel import Session, select
from sqlalchemy import delete, update
from starlette.background import BackgroundTask
from starlette.responses import Response, FileResponse, PlainTextResponse

from rag_file_server.config.config import config
from rag_file_server.dir.database import engine, create_db_and_tables
from rag_file_server.dir.model import FileNode, FileType, FileNodeVo, AddDirRequest, UpdateFileRequest, \
    UploadResponseOfDir, CeleryTaskFailedRequest, FileStatus, CeleryTaskType
from rag_file_server.error_code import raise_exception, ErrorCode
from rag_file_server.file.model import MetaData
from rag_file_sdk.file_api import Bucket

router = APIRouter(prefix="/api/dir")


def get_bucket(file_id: str, session: Session):
    file_node = get_top_dir_node(file_id, session)
    endpoint = f'http://localhost:{config.port}'
    return Bucket(endpoint, file_node.name)


def init():
    create_db_and_tables()
    Path(config.dir.tmp_path).mkdir(parents=True, exist_ok=True)


def get_session():
    with Session(engine) as session:
        yield session


def get_file_list(parent_id: str | None = None,
                  session: Session = Depends(get_session),
                  file_type: FileType | None = None) -> list[FileNode]:
    stmt = select(FileNode).where(FileNode.parent_id == parent_id)
    if file_type:
        stmt = stmt.where(FileNode.type == file_type)
    return cast(list[FileNode], session.exec(stmt).all())


@router.get("/bucket_name", response_class=PlainTextResponse)
def get_bucket_name(file_id: str, session: Session = Depends(get_session)) -> str:
    return get_bucket(file_id, session).bucket_name


@router.get("/top_dir_node", response_model=FileNode)
def get_top_dir_node(file_id: str, session: Session = Depends(get_session)):
    file_node = session.get_one(FileNode, file_id)
    if file_node.parent_id is None:
        return file_node

    parent_node = session.get_one(FileNode, file_node.parent_id)
    while parent_node.name != config.tenants_files_root_dir:
        if parent_node.parent_id is None:
            return parent_node

        file_node = parent_node
        parent_node = session.get_one(FileNode, file_node.parent_id)
    return file_node


@router.get("/list", response_model=list[FileNodeVo])
def list_files(parent_id: str | None = None,
               session: Session = Depends(get_session),
               file_type: FileType | None = None) -> list[FileNodeVo]:
    file_nodes = get_file_list(parent_id, session, file_type)
    key_list = [node.storage_key for node in file_nodes if node.type == FileType.FILE]

    metadata_list_ = []
    if parent_id:
        bucket = get_bucket(parent_id, session)
        metadata_list = bucket.get_metadatas(key_list)
        index = 0
        for node in file_nodes:
            if node.type == FileType.FILE:
                metadata_list_.append(metadata_list[index])
                index += 1
            else:
                metadata_list_.append(MetaData())
    else:
        metadata_list_ = [MetaData() for _ in range(len(file_nodes))]

    return [FileNodeVo(**node.model_dump(), **metadata.model_dump())
            for node, metadata in zip(file_nodes, metadata_list_)][::-1]


@router.get("/files_by_ids", response_model=list[FileNode])
def get_files_by_ids(file_node_ids: list[str] = Query(),
                     session: Session = Depends(get_session)) -> list[FileNode]:
    stmt = select(FileNode).where(FileNode.id.in_(file_node_ids))
    return cast(list[FileNode], session.exec(stmt).all())


@router.put("/dir", response_model=FileNode)
def add_dir(request: AddDirRequest, session: Session = Depends(get_session)) -> FileNode:
    # 如果不是根目录，先检查目录是否存在。
    if request.parent_id:
        try:
            session.exec(select(FileNode).where(FileNode.id == request.parent_id)).one()
        except NoResultFound as e:
            raise_exception(ErrorCode.DIR_NOT_EXISTS)

    file = FileNode(type=FileType.DIR, name=request.name, parent_id=request.parent_id)
    session.add(file)
    session.commit()
    session.refresh(file)
    return file


@router.put("/files", response_model=UploadResponseOfDir)
def add_files(files: list[UploadFile],
              parent_id: Annotated[str | None, Form()] = None,
              action: Annotated[Literal['override', 'ignore'], Form()] = 'ignore',
              session: Session = Depends(get_session)) -> UploadResponseOfDir:
    bucket = get_bucket(parent_id, session)
    file_node_map: dict[str, FileNode] = {}

    # save to dir
    saved_list = []
    exist_file_node_dict: dict[str, FileNode] = {node.name: node for node in get_file_list(parent_id, session)}
    for file in files:
        exist_node = exist_file_node_dict.get(file.filename)
        if exist_node:
            if action == 'override':
                saved_list.append(file.filename)
                file_node_map[exist_node.name] = exist_node
        else:
            saved_list.append(file.filename)
            file_po = FileNode(type=FileType.FILE, name=file.filename, parent_id=parent_id)
            session.add(file_po)
            file_node_map[file_po.name] = file_po

    session.commit()
    for file_name, file_node in file_node_map.items():
        session.refresh(file_node)

    key_list = []
    content_list = []
    for file in files:
        if file.filename in file_node_map:
            key_list.append(file_node_map[file.filename].storage_key)
            content_list.append(asyncio.run(file.read()))
    if key_list:
        bucket.set_files(key_list, content_list)

    ignore_list = [file.filename for file in files if file.filename not in saved_list]
    return UploadResponseOfDir(saved_files=saved_list,
                               ignore_files=ignore_list,
                               file_nodes=file_node_map.values())


def get_descendant_dfs(file_id: str | None, session: Session) -> list[FileNodeVo]:
    ret = list_files(file_id, session)
    rest = []
    for child in ret:
        rest.extend(get_descendant_dfs(child.id, session))
    return ret + rest


@router.delete("/files")
def delete_files(file_id_list: list[str], session: Session = Depends(get_session)) -> None:
    bucket = get_bucket(file_id_list[0], session)
    cur_files = cast(Sequence[FileNode], session.exec(select(FileNode).where(FileNode.id.in_(file_id_list))).all())
    descendants = [FileNode(**file.model_dump()) for file_id in file_id_list for file in
                   get_descendant_dfs(file_id, session)]
    all_files = list(chain(cur_files, descendants))
    all_ids = [file.id for file in all_files]
    stmt = delete(FileNode).where(FileNode.id.in_(all_ids))
    session.exec(stmt)
    session.commit()
    bucket.delete_files([file.storage_key for file in all_files])


@router.get("/parents", response_model=list[FileNode])
def parents(file_id: str, session: Session = Depends(get_session)) -> list[FileNode]:
    files = []
    file = cast(FileNode, session.get_one(FileNode, file_id))
    if file.type == FileType.DIR:
        files.append(file)

    while file.parent_id:
        file = cast(FileNode, session.get_one(FileNode, file.parent_id))
        files.append(file)
    return files[::-1]


def list_files_tree_dfs(file_vo: FileNodeVo,
                        session: Session = Depends(get_session),
                        file_type: FileType | None = None) -> None:
    file_vo.children = list_files(file_vo.id, session, file_type)
    for child in file_vo.children:
        list_files_tree_dfs(child, session, file_type)


@router.get("/tree", response_model=FileNodeVo)
def get_tree(root_id: str | None = None,
             file_type: FileType | None = None,
             session: Session = Depends(get_session)) -> FileNodeVo:
    if root_id:
        root = FileNodeVo(**cast(FileNode, session.get_one(FileNode, root_id)).model_dump())
    else:
        root = FileNodeVo(id=None, type=FileType.DIR, name='ROOT', parent_id=None)

    list_files_tree_dfs(root, session, file_type)
    return root


@router.get("/by_name", response_model=FileNode | None)
def get_by_name(name: str,
                parent_id: str | None = None,
                session: Session = Depends(get_session)) -> FileNode | None:
    stmt = select(FileNode).where((FileNode.name == name) & (FileNode.parent_id == parent_id))
    return session.exec(stmt).first()


@router.post("/download_files")
def download_files(file_id_list: list[str], session: Session = Depends(get_session)):
    bucket = get_bucket(file_id_list[0], session)
    assert len(file_id_list) > 0
    stmt = select(FileNode).where(FileNode.id.in_(file_id_list))
    file_nodes = cast(list[FileNode], session.exec(stmt).all())

    # 单文件
    if len(file_nodes) == 1 and file_nodes[0].type == FileType.FILE:
        media_type, _ = mimetypes.guess_type(file_nodes[0].name)
        quoted_filename = urllib.parse.quote(file_nodes[0].name)
        return Response(content=bucket.get_file(file_nodes[0].storage_key),
                        media_type=media_type,
                        headers={"Content-Disposition": f"attachment; filename*=utf-8''{quoted_filename}"})

    # 多文件返回 zip
    file_node_vos = [get_tree(node.id, session=session)
                     if node.type == FileType.DIR else FileNodeVo(**node.model_dump())
                     for node in file_nodes]
    file_md5s = []

    def collect_files_dfs(file_node_vo: FileNodeVo):
        if file_node_vo.type == FileType.FILE:
            file_md5s.append(file_node_vo.storage_key)
        for child in file_node_vo.children:
            collect_files_dfs(child)

    for node_vo in file_node_vos:
        collect_files_dfs(node_vo)

    zip_content = bucket.get_files(file_md5s)
    file_contents = {}

    with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_ref:
        for file_info in zip_ref.infolist():
            # 读取文件的二进制内容
            with zip_ref.open(file_info) as file:
                file_contents[file_info.filename] = file.read()

    zip_path = Path(config.dir.tmp_path) / f"files_{time.time()}.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_f:

        def write_zip_dfs(file_path: Path, node_vos: list[FileNodeVo]):
            for node_vo_ in node_vos:
                if node_vo_.type == FileType.FILE:
                    p = str(file_path / node_vo_.name)
                    zip_f.writestr(p, file_contents[node_vo_.storage_key])
                else:
                    write_zip_dfs(file_path / node_vo_.name, node_vo_.children)

        write_zip_dfs(Path(''), file_node_vos)

    file_name = file_nodes[0].name + '.zip' if len(file_nodes) == 1 else f"docs_of_{len(file_md5s)}.zip"
    task = BackgroundTask(lambda _: zip_path.unlink(), zip_path)
    return FileResponse(path=zip_path, filename=file_name, background=task)


@router.post("/files")
def update_files(request: UpdateFileRequest, session: Session = Depends(get_session)) -> None:
    update_dict = request.model_dump(exclude={'id_list'}, exclude_unset=True)
    stmt = update(FileNode).where(FileNode.id.in_(request.id_list)).values(**update_dict)
    session.execute(stmt)
    session.commit()


@router.post("/celery_task_failed", response_model=list[FileNode])
def on_celery_task_failed(request: CeleryTaskFailedRequest,
                          session: Session = Depends(get_session)) -> list[FileNode]:
    stmt = select(FileNode).where(FileNode.celery_task_id == request.task_id)
    file_nodes = cast(list[FileNode], session.exec(stmt).all())
    for file_node in file_nodes:
        if file_node.celery_task_type == CeleryTaskType.PARSE:
            file_node.status = FileStatus.PARSE_FAILED
        elif file_node.celery_task_type == CeleryTaskType.TO_VECTOR_STORE:
            file_node.status = FileStatus.TO_VECTOR_STORE_FAILED
        file_node.celery_task_id = None
        file_node.celery_task_type = None
        session.add(file_node)
    session.commit()
    for file_node in file_nodes:
        session.refresh(file_node)
    return file_nodes


@router.get("/total_files")
def get_total_files(parent_id: str | None = None,
                    session: Session = Depends(get_session)) -> int:
    total = get_descendant_dfs(parent_id, session)
    files = [file for file in total if file.type == FileType.FILE]
    return len(files)
