"""将当前文档的店铺身份观察与旧导航响应隔离。"""
from plugins.tiktok import allowed,identity_payload


class IdentityGuard:
    def __init__(self,page,site):
        self.page,self.site=page,site
        self.generation=0;self.requests={};self.identities=set()
        self.handlers={'request':self.request,'response':self.response,'framenavigated':self.navigated}
        for name,handler in self.handlers.items():page.on(name,handler)

    def navigated(self,frame):
        if frame==self.page.main_frame:
            self.generation+=1;self.requests.clear();self.identities.clear()

    def request(self,request):
        if len(self.requests)<2000:self.requests[request]=self.generation

    async def response(self,response):
        generation=self.requests.pop(response.request,None)
        if generation!=self.generation or not allowed(response.url,self.site):return
        try:
            if int(response.headers.get('content-length','0'))>2*1024*1024:return
            identity=identity_payload(await response.json(),self.site)
        except Exception:return
        if identity and generation==self.generation:self.identities.add((identity['site'],identity['external_id']))

    def verify(self,expected):
        if not allowed(self.page.url,self.site) or self.identities!={(expected['site'],expected['external_id'])}:
            raise RuntimeError('当前上传文档的店铺身份不能唯一确认，尚未提交；请核对店铺或更新站点适配')

    def close(self):
        for name,handler in self.handlers.items():self.page.remove_listener(name,handler)
        self.requests.clear()
