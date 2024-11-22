import json
import celery
import requests
from celery import Celery
from celery.signals import task_failure, task_success
from rag_file_sdk.dir_api import DirMgr
from rag_file_sdk.file_api import Bucket
from rag_file_server.dir.model import FileStatus

from celery_task.model import ToVectorStoreNotify, ParseFileNotify, send_process_notify, send_file_status_notify, \
    send_revision_md_notify
from config.config import config
from file_mgr.api import get_split_list
from file_parser.model import ParseFileRequest
from store_retriever_server.crud import get_kb_vecstore_name
from store_retriever_server.store_engine import StoreEngine
from util import check_response

app = Celery('tasks')
app.config_from_object('celery_task.celery_config')

notify_url = config.accept_nodify_url
dir_mgr = DirMgr(config.file_server_url)


@app.task(bind=True,
          acks_late=True,
          # autoretry_for=(Exception,),
          # retry_kwargs={'max_retries': 2, 'countdown': 10},
          # reject_on_worker_lost=True # 为 celery 崩溃恢复正在执行的任务，但是不起作用
          )
def parse_pdf(self: celery.Task, bucket_name: str, file_key_list: list[str], file_node_ids: list[str]):
    for file_node_id in file_node_ids:
        send_process_notify(notify_url, ParseFileNotify, file_node_id, 1)

    file_urls = [f"{config.file_server_url}/api/file/file/{bucket_name}/{file_key}"
                 for file_key in file_key_list]
    request = ParseFileRequest(file_urls=file_urls,
                               file_node_ids=file_node_ids,
                               notify_url=config.accept_nodify_url)
    response = requests.post(config.default_pdf_parser_url, json=request.model_dump())
    check_response(response)

    bucket = Bucket(config.file_server_url, bucket_name)
    for file_key, md_list in zip(file_key_list, response.json()):
        key = file_key + '.md.json'
        bucket.delete_str(key)
        bucket.set_str(key, json.dumps(md_list))

    send_file_status_notify(notify_url, file_node_ids, FileStatus.PARSED)
    dir_mgr.update_celery_task(file_node_ids, None, None)


@app.task(bind=True,
          acks_late=True,
          # autoretry_for=(Exception,),
          # retry_kwargs={'max_retries': 2, 'countdown': 10},
          # reject_on_worker_lost=True # 为 celery 崩溃恢复正在执行的任务，但是不起作用
          )
def to_vector_store(self, kb_id: str, store_name: str, file_node_ids: list[str]):
    for file_node_id in file_node_ids:
        send_process_notify(notify_url, ToVectorStoreNotify, file_node_id, 1)

    file_nodes = dir_mgr.get_files_by_ids(file_node_ids)
    for file_node in file_nodes:
        send_revision_md_notify(notify_url, [file_node.id], False)
        # 因为下面修改数据需要快速执行，避免副作用，所以直接调用
        dir_mgr.update_files([file_node.id], {'revision_not_in_vector_store': False})
        split_list = get_split_list(kb_id, file_node.id)
        vector_store_mgr = StoreEngine(store_name)
        vector_store_mgr.add_doc(split_list, str(file_node.id))
        send_file_status_notify(notify_url, file_node_ids, FileStatus.IN_VECTOR_STORE)
        dir_mgr.update_celery_task([file_node.id], None, None)


@app.task(bind=True, acks_late=True)
def reset_vector_store(self, kb_id: str):
    StoreEngine(get_kb_vecstore_name(kb_id)).reset_store()


@task_failure.connect
def task_failure_handler(sender=None,
                         task_id=None,
                         exception=None,
                         args=None,
                         kwargs=None,
                         traceback=None,
                         einfo=None,
                         **kw):
    file_nodes = dir_mgr.on_celery_task_failed(task_id)
    status = file_nodes[0].status
    send_file_status_notify(notify_url, [str(file_node.id) for file_node in file_nodes], status)


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    ...
