from typing import TypeVar

from fastapi import APIRouter
from rag_file_sdk.dir_api import DirMgr

from celery_task.model import AcceptedNotifyRequest, ToVectorStoreNotify, ParseFileNotify, FileStatusNotify, \
    RevisionMdNotify

from fastapi import WebSocket, WebSocketDisconnect

from config.config import config

router = APIRouter(tags=["notify"])


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []  # 存储活动的 WebSocket 连接

    async def connect(self, websocket: WebSocket):
        await websocket.accept()  # 接受 WebSocket 连接
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)  # 移除断开的连接

    async def broadcast(self, message: dict):
        # 向所有活动连接广播消息
        for connection in self.active_connections:
            await connection.send_json(message)


manager = ConnectionManager()

# redis = redis.asyncio.Redis(host="localhost", port=6379, db=0)
# async def notify_consumer():
#     while True:
#         message = await redis.blpop(['ParseFileNotify'])
#         await manager.broadcast(message[1].decode('utf-8'))
# await redis.rpush(notify.type, json.dumps(notify.data))


FileProcessNotifyT = TypeVar('FileProcessNotifyT', bound='FileProcessNotify')


@router.post("/accept_notify")
async def accept_notify(notify: AcceptedNotifyRequest):
    dir_mgr = DirMgr(config.file_server_url)
    if notify.type == ParseFileNotify.__name__:
        data: ParseFileNotify = ParseFileNotify.model_validate(notify.data)
        dir_mgr.update_parse_percent(data.file_node_id, data.percent)
    elif notify.type == ToVectorStoreNotify.__name__:
        data: ToVectorStoreNotify = ToVectorStoreNotify.model_validate(notify.data)
        dir_mgr.update_to_vector_store_percent(data.file_node_id, data.percent)
    elif notify.type == FileStatusNotify.__name__:
        data: FileStatusNotify = FileStatusNotify.model_validate(notify.data)
        dir_mgr.update_files_status(data.file_node_ids, data.status)
    elif notify.type == RevisionMdNotify.__name__:
        data: RevisionMdNotify = RevisionMdNotify.model_validate(notify.data)
        dir_mgr.update_files(data.file_node_ids, {'revision_not_in_vector_store': data.not_in_vector_store})

    await manager.broadcast(notify.model_dump())


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()  # 接收来自客户端的消息
            print(f'websocket receive client message: {data}')
    except WebSocketDisconnect:
        manager.disconnect(websocket)  # 处理断开连接
