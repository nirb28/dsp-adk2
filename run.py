import uvicorn
from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.auto_app_reload,
        log_level=settings.log_level.lower(),
        log_config=None
    )
