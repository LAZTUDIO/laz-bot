"""工具注册中心"""


class ToolRegistry:
    """工具注册中心：名称 → 描述 + JSON Schema + 处理函数"""

    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict, handler):
        """注册工具"""
        self._tools[name] = {
            "description": description,
            "parameters": parameters,
            "handler": handler
        }

    def get(self, name: str) -> dict:
        """获取工具"""
        return self._tools.get(name)

    def get_openai_tools(self) -> list[dict]:
        """返回 OpenAI 格式的工具定义列表"""
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": info["description"],
                    "parameters": info["parameters"]
                }
            }
            for name, info in self._tools.items()
        ]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def count(self) -> int:
        return len(self._tools)