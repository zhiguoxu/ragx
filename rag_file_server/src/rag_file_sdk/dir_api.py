import io
import uuid
from typing import Literal

import requests
from pydantic import BaseModel

from rag_file_sdk.common import check_response
from rag_file_server.dir.model import FileNode, FileType, FileNodeVo, UploadResponseOfDir, FileStatus, CeleryTaskType


def get_bucket_name(endpoint: str, file_id: str) -> str:
    response = requests.get(endpoint + "/api/dir/bucket_name", params={"file_id": file_id})
    check_response(response)
    return response.json()


class DirMgr(BaseModel):
    endpoint: str

    def __init__(self, endpoint: str):
        super().__init__(endpoint=endpoint)

    @property
    def url_prefix(self):
        return self.endpoint + '/api/dir'

    def get_top_dir_node(self, file_id: str) -> FileNode:
        response = requests.get(f"{self.url_prefix}/top_dir_node", params={"file_id": file_id})
        check_response(response)
        return FileNode.model_validate(response.json())

    def add_dir(self, name: str, parent_id: str | None = None) -> FileNode:
        response = requests.put(f"{self.url_prefix}/dir",
                                json={"parent_id": parent_id, "name": name})
        check_response(response)
        return FileNode(**response.json())

    def list_files(self, parent_id: str | None = None,
                   file_type: FileType | None = None) -> list[FileNodeVo]:
        response = requests.get(f"{self.url_prefix}/list", params={"parent_id": parent_id, "file_type": file_type})
        check_response(response)
        return [FileNodeVo(**item) for item in response.json()]

    @staticmethod
    def make_file_node_ids(id_list: list[str] | str):
        return id_list if isinstance(id_list, list) else [id_list]

    def get_files_by_ids(self, file_node_ids: list[str]):
        response = requests.get(f"{self.url_prefix}/files_by_ids", params={"file_node_ids": file_node_ids})
        check_response(response)
        return [FileNode.model_validate(item) for item in response.json()]

    def update_file_name(self, file_id: str, name: str) -> None:
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": [file_id], "name": name})
        check_response(response)

    def update_files_parent(self, id_list: list[str], parent_id: str | None):
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": id_list,
                                       "parent_id": parent_id})
        check_response(response)

    def update_files_status(self, id_list: list[str], status: FileStatus):
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": id_list,
                                       "status": status})
        check_response(response)

    def update_parse_percent(self, id_list: list[str] | str, parse_percent: float) -> None:
        id_list = self.make_file_node_ids(id_list)
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": id_list, "parse_percent": parse_percent})
        check_response(response)

    def update_to_vector_store_percent(self,
                                       id_list: list[str] | str,
                                       to_vector_store_percent: float) -> None:
        id_list = self.make_file_node_ids(id_list)
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": id_list, "to_vector_store_percent": to_vector_store_percent})
        check_response(response)

    def update_celery_task(self, id_list: list[str] | str,
                           celery_task_id: str | None,
                           celery_task_type: CeleryTaskType | None) -> None:
        id_list = self.make_file_node_ids(id_list)
        response = requests.post(f"{self.url_prefix}/files",
                                 json={
                                     "id_list": id_list,
                                     "celery_task_id": celery_task_id,
                                     "celery_task_type": celery_task_type
                                 })
        check_response(response)

    def update_files(self, id_list: list[str], data: dict):
        response = requests.post(f"{self.url_prefix}/files",
                                 json={"id_list": id_list, **data})
        check_response(response)

    def delete_files(self, file_id_list: list[str]):
        file_ids = [str(file_id) for file_id in file_id_list]
        response = requests.delete(f"{self.url_prefix}/files", json=file_ids)
        check_response(response)

    def get_tree(self, root_id: str | None = None, file_type: FileType | None = None) -> FileNodeVo:
        response = requests.get(f"{self.url_prefix}/tree", params={"root_id": root_id, "file_type": file_type})
        check_response(response)
        return FileNodeVo(**response.json())

    def get_parents(self, file_id: str) -> list[FileNode]:
        response = requests.get(f"{self.url_prefix}/parents", params={"file_id": file_id})
        check_response(response)
        return [FileNode(**item) for item in response.json()]

    def get_by_name(self, name: str, parent_id: str | None = None):
        response = requests.get(f"{self.url_prefix}/by_name", params={"name": name, "parent_id": parent_id})
        check_response(response)
        data = response.json()
        return FileNode(**data) if data else None

    def add_files(self,
                  file_name_list: list[str],
                  content_list: list[bytes],
                  parent_id: str,
                  action: Literal['override', 'ignore'] = 'ignore') -> UploadResponseOfDir:
        files = [("files", (file_name, io.BytesIO(content))) for (file_name, content) in
                 zip(file_name_list, content_list)]
        response = requests.put(f"{self.url_prefix}/files",
                                data={"parent_id": parent_id, "action": action},
                                files=files)
        check_response(response)
        return UploadResponseOfDir(**response.json())

    def on_celery_task_failed(self, celery_task_id: str) -> list[FileNode]:
        response = requests.post(f"{self.url_prefix}/celery_task_failed",
                                 json={"task_id": celery_task_id})
        check_response(response)
        return [FileNode.validate(item) for item in response.json()]

    def get_total_files(self, parent_id: str) -> int:
        response = requests.get(f"{self.url_prefix}/total_files", params={"parent_id": parent_id})
        check_response(response)
        return int(response.json())
