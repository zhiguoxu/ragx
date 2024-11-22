from contextlib import asynccontextmanager
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

import uvicorn
from fastapi import FastAPI, Depends
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.middleware.cors import CORSMiddleware

from file_mgr.api import router as file_mgr_router
from kb.api import router as kb_router
from file_parser.api import router as file_parser_router
from celery_task.notify import router as notify_router
from store_retriever_server.api import router as vector_store_router
from app.api import router as app_router
from chat.api import router as chat_router
from config.config import config
from db.database import create_db_and_tables
from db.db_init import init_db
from error_code import ErrorCode
from file_server.proxy_api import add_proxy
from user_role_group_mgr import auth_api, user_api, group_api, role_api
from data_server import api as data_api
from user_role_group_mgr.auth import get_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_api.router, prefix='/api')
app.include_router(user_api.router, prefix='/api')
app.include_router(role_api.router, prefix='/api')
app.include_router(group_api.router, prefix='/api')
app.include_router(data_api.router, prefix='/api')
app.include_router(file_mgr_router, prefix='/api')
app.include_router(kb_router, prefix='/api')
app.include_router(file_parser_router, prefix='/api')
app.include_router(notify_router, prefix='/notify')
app.include_router(vector_store_router, prefix='/api')
app.include_router(app_router, prefix='/api')
app.include_router(chat_router, prefix='/api')

add_proxy(app,
          config.file_server_url,
          '/file_server',
          dependencies=[Depends(get_current_user)],
          no_dep_method_paths=[('GET', '/api/file/file')])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 或者指定特定的域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"]  # 允许所有请求头
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    print(request, exc)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    print(exc)
    raise HTTPException(status_code=ErrorCode.UNIQUE_CONSTRAINT_FAILED.code,
                        detail=ErrorCode.UNIQUE_CONSTRAINT_FAILED.desc)


if __name__ == "__main__":
    uvicorn.run(app='main:app', host=config.host, port=config.port, reload=True)
