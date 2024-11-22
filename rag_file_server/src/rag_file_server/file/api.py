import shutil
import time
import zipfile
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, Query, Depends, Form
from pathlib import Path
from pydantic import BaseModel, field_validator
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from rag_file_server.config.config import config
from rag_file_server.error_code import raise_exception, ErrorCode
from rag_file_server.file.model import UploadResponse, MetaData

# 定义根路径
BASE_DIR = Path(config.file.base_dir)


# 创建预设 buckets 目录
def init():
    for bucket in config.file.bucket_list:
        (BASE_DIR / bucket).mkdir(parents=True, exist_ok=True)


router = APIRouter(prefix="/api/file")


class CommonParams(BaseModel):
    bucket: str

    @property
    def dir(self):
        return BASE_DIR / self.bucket

    @field_validator('bucket')
    @classmethod
    def validate_bucket(cls, bucket: str) -> str:
        if (BASE_DIR / bucket).is_dir():
            return bucket
        raise_exception(ErrorCode.BUCKET_NOT_EXISTS, bucket)


@router.put("/bucket/{bucket:path}")
def create_bucket(bucket: str):
    if (BASE_DIR / bucket).is_dir():
        raise_exception(ErrorCode.BUCKET_ALREADY_EXIST, bucket)
    (BASE_DIR / bucket).mkdir(parents=True, exist_ok=True)


@router.delete("/bucket/{bucket:path}")
def delete_bucket(bucket: str):
    bucket_dir = (BASE_DIR / bucket)
    if bucket_dir.is_dir():
        for item in bucket_dir.iterdir():
            item.unlink()
        bucket_dir.rmdir()


@router.get("/file/{bucket:path}/{file_name:path}")
def get_file(file_name: str, common: CommonParams = Depends()) -> FileResponse:
    file_path = common.dir / file_name
    if not file_path.is_file():
        raise_exception(ErrorCode.FILE_NOT_EXISTS, file_name)

    return FileResponse(path=file_path, filename=file_name)


@router.post("/get_files/{bucket:path}")
def get_files(file_names: list[str], common: CommonParams = Depends()) -> FileResponse:
    zip_filename = f"files_{time.time()}.zip"
    zip_path = common.dir / zip_filename

    # 创建一个内存中的 zip 文件
    with zipfile.ZipFile(zip_path, "w") as zip_f:
        for file_name in file_names:
            file_path = common.dir / file_name
            if file_path.is_file():
                zip_f.write(file_path, file_name)
            else:
                raise_exception(ErrorCode.FILE_NOT_EXISTS, file_name)

    # 使用 BackgroundTask 来确保在响应结束后删除临时 zip 文件
    task = BackgroundTask(lambda _: zip_path.unlink(), zip_path)

    return FileResponse(path=zip_path,
                        filename=zip_filename,
                        background=task)


@router.put("/file/{bucket:path}")
def set_file(file: UploadFile = File(...),
             override: Annotated[bool, Form()] = False,
             common: CommonParams = Depends()):
    file_path = common.dir / file.filename
    if not override and file_path.exists():
        raise_exception(ErrorCode.FILE_EXISTS, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)


@router.put("/files/{bucket:path}", response_model=UploadResponse)
def set_files(files: list[UploadFile] = File(...),
              override: bool = False,
              common: CommonParams = Depends()):
    saved_files = []
    ignore_files = []
    for file in files:
        file_path = common.dir / file.filename
        if not override and file_path.exists():
            ignore_files.append(file.filename)
        else:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file.filename)
    return UploadResponse(saved_files=saved_files, ignore_files=ignore_files)


@router.get("/metadata/{bucket:path}/{file_name:path}", response_model=MetaData)
def get_metadata(file_name: str, common: CommonParams = Depends()):
    file_path = common.dir / file_name
    if not file_path.is_file():
        raise_exception(ErrorCode.FILE_NOT_EXISTS, file_name)
    stat = file_path.stat()
    return MetaData(upload_time=stat.st_ctime, size=stat.st_size)


@router.get("/metadatas/{bucket:path}", response_model=list[MetaData])
def get_metadatas(file_name_list: list[str] = Query(), common: CommonParams = Depends()):
    return [get_metadata(file_name, common) for file_name in file_name_list]


@router.delete("/file/{bucket:path}/{file_name:path}")
def delete_file(file_name: str, common: CommonParams = Depends()) -> None:
    (common.dir / file_name).unlink(missing_ok=True)


@router.delete("/files/{bucket:path}")
def delete_files(file_name_list: list[str], common: CommonParams = Depends()) -> None:
    for file_name in file_name_list:
        (common.dir / file_name).unlink(missing_ok=True)


@router.get("/strs/{bucket:path}")
def get_strs(key_list: list[str] = Query(), common: CommonParams = Depends()) -> list[str]:
    file_paths = [common.dir / key for key in key_list]
    for file_path in file_paths:
        if not file_path.is_file():
            raise_exception(ErrorCode.FILE_NOT_EXISTS, file_path.name)
    return [file_path.read_text('utf-8') for file_path in file_paths]
