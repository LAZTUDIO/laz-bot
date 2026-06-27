"""执行引擎 — 函数调用网关 + 工具路由"""
import json
import asyncio
import logging
from .registry import ToolRegistry
from .sandbox import Sandbox

logger = logging.getLogger("laz-bot.executor")


class Executor:
    """执行引擎：解析 tool_calls → 路由到注册工具 → 返回结果"""

    def __init__(self, config: dict):
        self.registry = ToolRegistry()
        self.sandbox = Sandbox(
            path_whitelist=config.get("executor", {}).get("path_whitelist", [])
        )
        self.tool_timeout = config.get("executor", {}).get("tool_timeout", 30)
        self.max_rounds = config.get("executor", {}).get("max_tool_rounds", 3)

        # 注册默认工具
        self._register_default_tools()

    def _register_default_tools(self):
        """注册内建工具"""
        from .tools.knowledge_query import query_knowledge
        from .tools.web_search import search_web
        from .tools.device_control import control_device

        self.registry.register(
            name="query_knowledge",
            description="查询内部知识库中的相关信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "查询内容"}
                },
                "required": ["query"]
            },
            handler=query_knowledge
        )
        self.registry.register(
            name="search_web",
            description="搜索互联网获取最新信息",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"]
            },
            handler=search_web
        )
        self.registry.register(
            name="control_device",
            description="控制连接的 IoT 设备",
            parameters={
                "type": "object",
                "properties": {
                    "device": {"type": "string", "description": "设备名称"},
                    "command": {"type": "string", "description": "控制命令"}
                },
                "required": ["device", "command"]
            },
            handler=control_device
        )

    async def execute_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """执行一组工具调用"""
        results = []
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError as e:
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Error parsing arguments: {e}"
                })
                continue

            tool_info = self.registry.get(func_name)
            if not tool_info:
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Unknown tool: {func_name}"
                })
                continue

            logger.info(f"[Executor] Running tool: {func_name}({args})")

            try:
                handler = tool_info["handler"]
                # 如果是异步处理函数
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(**args)
                else:
                    # 同步函数放入线程执行
                    import asyncio
                    result = await asyncio.to_thread(handler, **args)

                content = str(result) if result is not None else "Done (no result)"
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content
                })
                logger.info(f"[Executor] Tool {func_name} -> OK")
            except Exception as e:
                logger.error(f"[Executor] Tool {func_name} failed: {e}")
                results.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Execution error: {str(e)}"
                })

        return results

    def get_tool_definitions(self) -> list[dict]:
        """获取 OpenAI 格式的工具定义"""
        return self.registry.get_openai_tools()