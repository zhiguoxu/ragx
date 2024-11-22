from fastapi import APIRouter, Depends
from rag_file_sdk.dir_api import DirMgr
from rag_file_server.dir.model import CeleryTaskType, FileStatus

from celery_task.celery_app import to_vector_store
from config.config import config
from store_retriever_server.crud import get_kb_vecstore_name
from store_retriever_server.store_engine import StoreEngine
from user_role_group_mgr.auth import get_current_user
from user_role_group_mgr.model import User
from store_retriever_server.model import SplitTextRequest, DocRequest, SearchRequest, SearchResult
from store_retriever_server.text_splitter import TextSplitter

router = APIRouter(prefix="/vector_store", tags=["vector store"])
dir_mgr = DirMgr(config.file_server_url)


@router.post('/split_text')
def split_text(request: SplitTextRequest) -> list[str]:
    return TextSplitter().split_text(request.text, request.chunk_size)


@router.post('/add_docs')
def add_docs(request: DocRequest,
             user: User = Depends(get_current_user)):
    file_node_ids = [str(file_node_id) for file_node_id in request.file_node_ids]

    dir_mgr.update_to_vector_store_percent(file_node_ids, 0)
    dir_mgr.update_files_status(file_node_ids, FileStatus.TO_VECTOR_STORE_ING)
    task_id = to_vector_store.delay(request.kb_id,
                                    get_kb_vecstore_name(request.kb_id),
                                    file_node_ids).id
    dir_mgr.update_celery_task(file_node_ids, task_id, CeleryTaskType.TO_VECTOR_STORE)


@router.post('/search', response_model=list[SearchResult])
def search(request: SearchRequest) -> list[SearchResult]:
    vector_store_mgr = StoreEngine(get_kb_vecstore_name(request.kb_id))
    return vector_store_mgr.search(request.query, request.limit)
