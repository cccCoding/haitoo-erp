"""在请求解析前限制矩阵JSON与发布包的实际输入字节数。"""
from fastapi import HTTPException
from starlette.responses import JSONResponse


class MatrixRequestLimit:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not (scope.get('path','').startswith('/hub-v5/') or scope.get('path','').startswith('/admin/connector-releases')):
            return await self.app(scope,receive,send)
        limit=510*1024*1024 if scope['path']=='/admin/connector-releases' and scope['method']=='POST' else 260*1024*1024 if scope['path']=='/hub-v5/releases' and scope['method']=='POST' else 4*1024*1024
        headers=dict(scope.get('headers',[]))
        try:length=int(headers.get(b'content-length',b'0'))
        except ValueError:return await JSONResponse({'detail':'请求长度无效'},status_code=400)(scope,receive,send)
        if length>limit:return await JSONResponse({'detail':'矩阵请求超过大小上限'},status_code=413)(scope,receive,send)
        received=0
        async def bounded():
            nonlocal received
            message=await receive()
            if message['type']=='http.request':
                received+=len(message.get('body',b''))
                if received>limit:raise HTTPException(413,'矩阵请求超过大小上限')
            return message
        await self.app(scope,bounded,send)
