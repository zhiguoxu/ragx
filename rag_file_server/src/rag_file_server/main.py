from contextlib import asynccontextmanager
from sqlalchemy.exc import IntegrityError

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request

from rag_file_server.config.config import config
from rag_file_server.file.api import init as init_file, router as file_router
from rag_file_server.dir.api import init as init_dir, router as dir_router

from error_code import ErrorCode


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_file()
    init_dir()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(file_router, tags=['file'])
app.include_router(dir_router, tags=['dir'])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 或者指定特定的域名
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"]  # 允许所有请求头
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(request.url, exc)


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    raise HTTPException(status_code=ErrorCode.UNIQUE_CONSTRAINT_FAILED.code,
                        detail=ErrorCode.UNIQUE_CONSTRAINT_FAILED.desc)


if __name__ == "__main__":
    uvicorn.run(app='main:app', host='0.0.0.0', port=config.port, reload=True)
