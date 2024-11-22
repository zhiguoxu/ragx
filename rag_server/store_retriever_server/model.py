from pydantic import BaseModel


class SplitTextRequest(BaseModel):
    text: str
    chunk_size: int = 512


class DocRequest(BaseModel):
    kb_id: str
    file_node_ids: list[str]


class SearchRequest(BaseModel):
    kb_id: str
    query: str
    limit: int = 3


class SearchResult(BaseModel):
    id: int
    text: str
    distance: float
    doc_id: str
