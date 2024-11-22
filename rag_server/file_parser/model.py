from pydantic import BaseModel


class ParseFileRequest(BaseModel):
    file_urls: list[str]
    file_node_ids: list[str]
    notify_url: str
