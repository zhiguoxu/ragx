from pydantic import BaseModel
from rag_file_server.dir.model import FileStatus


class AcceptedNotifyRequest(BaseModel):
    type: str
    data: dict


class FileProcessNotify(BaseModel):
    file_node_id: str
    percent: float


class ParseFileNotify(FileProcessNotify):
    ...


class ToVectorStoreNotify(FileProcessNotify):
    ...


class FileStatusNotify(BaseModel):
    file_node_ids: list[str]
    status: FileStatus


class RevisionMdNotify(BaseModel):
    file_node_ids: list[str]
    not_in_vector_store: bool


def send_process_notify(notify_url: str, notify_type: type[FileProcessNotify], file_node_id: str, percent: float):
    import requests
    notify_request = AcceptedNotifyRequest(type=notify_type.__name__,
                                           data=dict(file_node_id=file_node_id,
                                                     percent=percent))
    requests.post(notify_url, json=notify_request.model_dump())


def send_file_status_notify(notify_url: str, file_node_ids: list[str], status: FileStatus):
    import requests
    notify_request = AcceptedNotifyRequest(type=FileStatusNotify.__name__,
                                           data=dict(file_node_ids=file_node_ids, status=status))
    requests.post(notify_url, json=notify_request.model_dump())


def send_revision_md_notify(notify_url: str, file_node_ids: list[str], not_in_vector_store: bool):
    import requests
    notify_request = AcceptedNotifyRequest(type=RevisionMdNotify.__name__,
                                           data=dict(file_node_ids=file_node_ids,
                                                     not_in_vector_store=not_in_vector_store))
    requests.post(notify_url, json=notify_request.model_dump())
