import json
from pathlib import Path

from pydantic import BaseModel


class FileConfig(BaseModel):
    base_dir: str
    bucket_list: list[str]


class DirConfig(BaseModel):
    sql_url: str
    tmp_path: str


class Config(BaseModel):
    port: int
    file: FileConfig
    dir: DirConfig
    tenants_files_root_dir: str


config_path = Path(__file__).parent / 'config.json'
with open(config_path) as f:
    config = Config(**json.load(f))
