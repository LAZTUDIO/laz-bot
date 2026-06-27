"""安全沙箱 — AST 扫描 + 路径白名单 + 超时保护"""
import ast
import time
import threading
from pathlib import Path

# 禁止的 AST 节点类型
FORBIDDEN_NODES = {
    ast.Call: {"func": {"eval", "exec", "__import__", "compile"}},
}

# 禁止的模块导入
FORBIDDEN_IMPORTS = {"subprocess", "os", "shutil", "signal", "ctypes", "fcntl"}


class Sandbox:
    """工具执行安全沙箱"""

    def __init__(self, path_whitelist: list[str] = None):
        self.path_whitelist = [Path(p).resolve() for p in (path_whitelist or ["/tmp"])]

    def scan_code(self, code: str) -> tuple[bool, str]:
        """扫描代码是否安全，返回 (safe, reason)"""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        for node in ast.walk(tree):
            # 禁止 eval/exec/__import__/compile
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "__import__", "compile", "open"}:
                    return False, f"Forbidden function call: {node.func.id}"
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"system", "popen", "run", "call", "check_output"}:
                        return False, f"Forbidden method call: ...{node.func.attr}"

            # 禁止危险导入
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    root_mod = alias.name.split(".")[0]
                    if root_mod in FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {alias.name}"

        return True, "OK"

    def check_path(self, path_str: str) -> bool:
        """检查路径是否在白名单内"""
        try:
            p = Path(path_str).resolve()
            for allowed in self.path_whitelist:
                if str(p).startswith(str(allowed)):
                    return True
            return False
        except:
            return False

    def execute_with_timeout(self, handler, timeout: int = 30, **kwargs):
        """带超时保护的工具执行"""
        result = [None]
        error = [None]
        done = threading.Event()

        def runner():
            try:
                result[0] = handler(**kwargs)
            except Exception as e:
                error[0] = e
            finally:
                done.set()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

        if not done.wait(timeout=timeout):
            return {"error": f"Execution timed out after {timeout}s"}

        if error[0]:
            return {"error": str(error[0])}

        return {"result": result[0]}