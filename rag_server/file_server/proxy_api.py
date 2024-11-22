from typing import cast, Sequence, Tuple

from fastapi import APIRouter, Request, FastAPI, Depends, HTTPException
import httpx
from fastapi.openapi.utils import get_openapi
from starlette.responses import StreamingResponse


# 获取原服务的 OpenAPI 文档并合并
def add_proxy(app: FastAPI,
              source_url: str,
              prefix: str = '/',
              dependencies: list[Depends] | None = None,
              prefix_without_dep: str | None = None,
              no_dep_method_paths: Sequence[Tuple[str, str]] = ()):
    prefix_without_dep = prefix_without_dep or prefix + '_no_dep'
    router = APIRouter(prefix=prefix, dependencies=dependencies)
    router_without_dep = APIRouter(prefix=prefix_without_dep)

    def has_no_dep_method_path(method: str, path: str):
        for method_, path_ in no_dep_method_paths:
            if method_.lower() == method.lower() and path.startswith(path_):
                return True

        return False

    async def proxy_request(prefix_: str, request: Request):
        async with httpx.AsyncClient() as client:
            path = request.url.path[len(prefix_):]
            response = await client.request(request.method,
                                            f"{source_url}{path}",
                                            headers=request.headers.raw,
                                            data=await request.body(),
                                            params=request.query_params)

        return StreamingResponse(response.aiter_bytes(),  # 异步迭代字节流
                                 headers=response.headers,
                                 status_code=response.status_code)

    # 代理所有请求
    @router.api_route("/{__proxy_path__:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy(__proxy_path__: str, request: Request):
        return await proxy_request(prefix, request)

    @router_without_dep.api_route("/{__proxy_path__:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def proxy(__proxy_path__: str, request: Request):
        if has_no_dep_method_path(request.method, '/' + __proxy_path__):
            return await proxy_request(prefix_without_dep, request)

        raise HTTPException(status_code=404, detail="Item not found")

    app.include_router(router)
    app.include_router(router_without_dep)

    def custom_openapi():
        if not app.openapi_schema:
            original_openapi = httpx.get(f"{source_url}/openapi.json").json()

            app.openapi_schema = get_openapi(
                title="RAG API",
                version="1.0.1",
                description="RAG API",
                routes=app.routes
            )

            paths = cast(dict[str, dict], app.openapi_schema['paths'])
            security = paths[prefix + '/{__proxy_path__}']['get'].get('security')
            paths = {path: methods for path, methods in paths.items() if '__proxy_path__' not in path}

            # 将原服务的路由添加到 FastAPI 的 OpenAPI 文档中
            for path, methods in original_openapi["paths"].items():
                # path 不能重复，dep 和 no dep 必须分开
                remove_methods = []
                for method, method_value in methods.items():
                    if has_no_dep_method_path(method, path):
                        paths[prefix_without_dep + path] = {method: method_value}
                        remove_methods.append(method)
                for method in remove_methods:
                    methods.pop(method)

                paths[prefix + path] = methods
                if security:
                    for value in cast(dict[str, dict], methods).values():
                        value['security'] = security
            app.openapi_schema['paths'] = paths

            # 合并 components
            cast(dict, app.openapi_schema['components']['schemas']).update(original_openapi['components']['schemas'])

        return app.openapi_schema

    app.openapi = custom_openapi
