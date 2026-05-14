from workOrderAI.app.api import classify, reply_suggest
from fastapi import FastAPI
from workOrderAI.utils.config import config

app = FastAPI()
app.include_router(classify.api)
app.include_router(reply_suggest.api)

@app.get("/health")
def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "workorder-ai"}

@app.get("/")
def root():
    """根路径，返回服务信息"""
    return {
        "service": "工单系统AI服务",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "workOrderAI.main:app",
        host=config['FastAPI']['host'],                     # 监听地址
        port=config['FastAPI']['port'],                     # 监听端口(默认8003)
        reload=False,                            # 生产模式关闭自动重载
        log_level=config['FastAPI']['log_level'],           # 日志级别
        access_log=True                         # 记录访问日志
    )

