import io
import json

import requests
from pydantic import BaseModel
from rag_file_server.file.model import MetaData, UploadResponse
from rag_file_sdk.common import check_response


class Bucket(BaseModel):
    endpoint: str
    bucket_name: str | None

    @property
    def url_prefix(self):
        return self.endpoint + '/api/file'

    def __init__(self, endpoint: str, bucket_name: str):
        super().__init__(endpoint=endpoint, bucket_name=bucket_name)

    def create_bucket(self):
        response = requests.put(f"{self.url_prefix}/bucket/{self.bucket_name}")
        check_response(response)

    def delete_bucket(self):
        response = requests.delete(f"{self.url_prefix}/bucket/{self.bucket_name}")
        check_response(response)
        self.bucket_name = None

    def get_file(self, file_name: str) -> bytes:
        response = requests.get(f"{self.url_prefix}/file/{self.bucket_name}/{file_name}")
        check_response(response)
        return response.content

    def get_files(self, file_names: list[str]) -> bytes:
        response = requests.post(f"{self.url_prefix}/get_files/{self.bucket_name}", json=file_names)
        check_response(response)
        return response.content  # .zip data for dir or multiple files.

    def set_file(self, file_name: str, content: bytes, override: bool = False) -> None:
        response = requests.put(f"{self.url_prefix}/file/{self.bucket_name}",
                                data={"override": override},
                                files={"file": (file_name, io.BytesIO(content))})
        check_response(response)

    def set_files(self, file_name_list: list[str], content_list: list[bytes], override: bool = False) -> UploadResponse:
        assert len(file_name_list) == len(content_list)
        files = [("files", (file_name, io.BytesIO(content))) for (file_name, content) in
                 zip(file_name_list, content_list)]
        response = requests.put(f"{self.url_prefix}/files/{self.bucket_name}",
                                data={"override": override},
                                files=files)
        check_response(response)
        return UploadResponse(**response.json())

    def get_metadata(self, file_name: str) -> MetaData:
        response = requests.get(f"{self.url_prefix}/metadata/{self.bucket_name}/{file_name}")
        check_response(response)
        return MetaData(**response.json())

    def get_metadatas(self, file_name_list: list[str]) -> list[MetaData]:
        if not file_name_list:
            return []

        response = requests.get(f"{self.url_prefix}/metadatas/{self.bucket_name}",
                                params={"file_name_list": file_name_list})
        check_response(response)
        return [MetaData(**data) for data in response.json()]

    def delete_file(self, file_name: str) -> None:
        response = requests.delete(f"{self.url_prefix}/file/{self.bucket_name}/{file_name}")
        check_response(response)

    def delete_files(self, file_name_list: list[str]) -> None:
        response = requests.delete(f"{self.url_prefix}/files/{self.bucket_name}", data=json.dumps(file_name_list))
        check_response(response)

    def set_str(self, key: str, value: str):
        self.set_file(key, value.encode('utf-8'))

    def set_strs(self, key_list: list[str], value_list: list[str]):
        self.set_files(key_list, [value.encode('utf-8') for value in value_list])

    def get_str(self, key: str) -> str:
        return self.get_file(key).decode('utf-8')

    def get_strs(self, key_list: str) -> list[str]:
        response = requests.get(f"{self.url_prefix}/strs/{self.bucket_name}", params={"key_list": key_list})
        check_response(response)
        return response.json()

    def delete_str(self, key: str):
        self.delete_file(key)

    def delete_strs(self, key_list: list[str]):
        self.delete_files(key_list)
