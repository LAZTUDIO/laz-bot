"""LAZ-Bot factory"""
from fastapi import FastAPI
from .routes import router

def create_app(config: dict) -> FastAPI:
    app = FastAPI(title="LAZ-Bot", version="1.0.0")
    app.include_router(router)
    app.state.config = config
    app.state.model_router = None
    app.state.memory = None
    app.state.llm = None
    app.state.executor = None
    app.state.cycle = None
    app.state.initialized = False

    @app.on_event("startup")
    async def startup():
        print("[LAZ-Bot] Initializing...")
        from .model_router import ModelRouter
        mr = ModelRouter(config)
        app.state.model_router = mr
        from memory import MemoryService
        mem = MemoryService(config)
        await mem.initialize()
        app.state.memory = mem
        from .llm_router import LLMRouter
        llm = LLMRouter(config, mr)
        app.state.llm = llm
        from executor import Executor
        app.state.executor = Executor(config)
        from .cognitive_cycle import CognitiveCycle
        app.state.cycle = CognitiveCycle(config=config, memory_service=mem, llm_router=llm, executor=app.state.executor)
        app.state.initialized = True
        print("[LAZ-Bot] ALL SYSTEMS INITIALIZED")

    @app.on_event("shutdown")
    async def shutdown():
        if app.state.cycle:
            await app.state.cycle.shutdown()
        print("[LAZ-Bot] Shutdown")
    return app
