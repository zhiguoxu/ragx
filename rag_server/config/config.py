import json
from pathlib import Path

from pydantic import BaseModel


class Config(BaseModel):
    host: str
    port: int
    celery_port: int
    sql_url: str
    file_server_url: str
    tenants_files_root_dir: str
    default_pdf_parser_url: str
    default_splitter_url: str
    milvus_uri: str
    embedding_model_name_or_path: str
    docling_model_path: str

    @property
    def accept_nodify_url(self):
        return f'http://localhost:{self.port}/notify/accept_notify'


config_path = Path(__file__).parent / 'config.json'
with open(config_path) as f:
    config = Config(**json.load(f))
