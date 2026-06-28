"""Orchestrator 路由 — HTTP + WebSocket + Admin API"""
import json
import os
import subprocess
import httpx
import yaml

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from memory.personality import TYPES

router = APIRouter()
CONFIG_PATH = os.environ.get("LAZ_CONFIG", os.path.join(os.path.dirname(__file__), "..", "config.yaml"))

# ── Pydantic models ──

class ChatRequest(BaseModel):
    text: str
    session_id: str = ""

class ChatResponse(BaseModel):
    response: str
    session_id: str

# ── Config helpers ──

def _load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

def _get_templates():
    """Return the list of provider templates, without Ollama-specific hacks."""
    return [
        {"id": "siliconflow", "name": "硅基流动",
         "base_url": "https://api.siliconflow.cn/v1",
         "models_url": "https://api.siliconflow.cn/v1/models",
         "list_model": True, "need_key": True,
         "notes": "DeepSeek / Qwen / LLaMA 等",
         "category": ["llm", "stt", "tts", "embedding"]},
        {"id": "deepseek", "name": "DeepSeek 官方",
         "base_url": "https://api.deepseek.com/v1",
         "models_url": "https://api.deepseek.com/v1/models",
         "list_model": True, "need_key": True,
         "notes": "OpenAI 兼容格式",
         "category": ["llm"]},
        {"id": "volcengine", "name": "火山引擎",
         "base_url": "https://ark.cn-beijing.volces.com/api/v3",
         "models_url": "", "list_model": False, "need_key": True,
         "notes": "豆包系列，需在控制台获取模型 endpoint",
         "category": ["llm", "embedding"]},
        {"id": "zhipu", "name": "智谱 AI",
         "base_url": "https://open.bigmodel.cn/api/paas/v4",
         "models_url": "https://open.bigmodel.cn/api/paas/v4/models",
         "list_model": True, "need_key": True,
         "notes": "GLM 系列",
         "category": ["llm", "embedding"]},
        {"id": "tongyi", "name": "通义千问",
         "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
         "models_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
         "list_model": True, "need_key": True,
         "notes": "阿里 Qwen/QwQ 系列",
         "category": ["llm", "embedding"]},
        {"id": "moonshot", "name": "Moonshot",
         "base_url": "https://api.moonshot.cn/v1",
         "models_url": "https://api.moonshot.cn/v1/models",
         "list_model": True, "need_key": True,
         "notes": "月之暗面 Kimi 系列",
         "category": ["llm"]},
        {"id": "baidu", "name": "百度千帆",
         "base_url": "https://qianfan.baidubce.com/v2",
         "models_url": "", "list_model": False, "need_key": True,
         "notes": "文心系列，需在千帆控制台配置",
         "category": ["llm"]},
        {"id": "openai", "name": "OpenAI",
         "base_url": "https://api.openai.com/v1",
         "models_url": "https://api.openai.com/v1/models",
         "list_model": True, "need_key": True,
         "notes": "GPT 系列",
         "category": ["llm", "stt", "tts", "embedding"]},
        {"id": "ollama", "name": "Ollama (本地)",
         "base_url": "http://localhost:11434/v1",
         "models_url": "http://localhost:11434/api/tags",
         "list_model": True, "need_key": False,
         "notes": "本地运行，无需 API Key",
         "category": ["llm", "embedding"]},
        {"id": "lmstudio", "name": "LM Studio (本地)",
         "base_url": "http://localhost:1234/v1",
         "models_url": "", "list_model": False, "need_key": False,
         "notes": "本地运行，需在 LM Studio 中加载模型",
         "category": ["llm"]},
        {"id": "custom", "name": "自定义",
         "base_url": "", "models_url": "",
         "list_model": False, "need_key": False,
         "notes": "手动配置",
         "category": ["llm", "stt", "tts", "embedding"]},
    ]


def _deep_merge(base, overlay):
    for key, val in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val

# ── Main page ──

@router.get("/")
async def root():
    return {"message": "LAZ-Bot is running. Use /ws/audio for voice or /docs for API docs."}

# ── Admin UI ──

@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    html_path = os.path.join(os.path.dirname(__file__), "..", "admin", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@router.get("/admin/static/{file_path:path}")
async def admin_static(file_path: str):
    static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "admin", "static"))
    full_path = os.path.abspath(os.path.join(static_dir, file_path))
    if not full_path.startswith(static_dir):
        return {"error": "Forbidden"}
    if os.path.isfile(full_path):
        return FileResponse(full_path)
    return {"error": "Not found"}

# ── Voice / Audio ──

@router.get("/api/audio/devices")
async def list_audio_devices():
    """列出 ALSA 音频设备"""
    import subprocess
    devices = []
    try:
        # arecord -l 输出
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
        for line in out.stdout.splitlines():
            if "card" in line and "device" in line:
                # card X: NAME [DEVICE], device N: ...
                parts = line.split(":")
                if len(parts) >= 2:
                    name = parts[1].strip()
                    # 提取 card/device 号
                    import re
                    m = re.match(r"card\s+(\d+).*device\s+(\d+)", line)
                    if m:
                        card = int(m.group(1))
                        dev = int(m.group(2))
                        devices.append({
                            "index": len(devices),
                            "name": name,
                            "card": card,
                            "device_num": dev,
                            "channels_in": 1,
                            "channels_out": 1,
                            "sample_rate": 48000,
                            "alsa_device": f"plughw:{card},{dev}",
                        })
        # 如果 arecord 没找到，退回用 aplay -l
        if not devices:
            out = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
            for line in out.stdout.splitlines():
                if "card" in line:
                    devices.append({"index": len(devices), "name": line.strip(), "alsa_device": ""})
    except Exception as e:
        return {"devices": [], "error": str(e)}
    # 补充 USB Composite 设备（card 2）
    if not devices:
        devices.append({
            "index": 0,
            "name": "USB Composite Device (card 2)",
            "card": 2, "device_num": 0,
            "channels_in": 1, "channels_out": 1,
            "sample_rate": 48000,
            "alsa_device": "plughw:2,0",
        })
    return {"devices": devices}

@router.websocket("/ws/audio")
async def audio_websocket(ws: WebSocket):
    """语音管道 WebSocket"""
    await ws.accept()
    app = ws.app
    if not app.state.initialized:
        await ws.send_text(json.dumps({"type": "error", "data": "系统未初始化"}))
        await ws.close()
        return

    from voice_pipeline import VoicePipeline
    pipeline = VoicePipeline(
        config=app.state.config,
        model_router=app.state.model_router,
        llm_router=app.state.llm,
        memory_service=app.state.memory,
        cognitive_cycle=app.state.cycle,
    )

    try:
        await pipeline.run(ws)
    except WebSocketDisconnect:
        pipeline.stop()
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "data": str(e)}))
        except Exception:
            pass

# ── Health ──

@router.get("/health")
async def health(request: Request):
    app = request.app
    memory_count = app.state.memory.long_term.count() if app.state.memory else -1
    graph_stats = app.state.memory.graph.get_stats() if app.state.memory else {}
    return {
        "status": "ok" if app.state.initialized else "initializing",
        "memory_count": memory_count,
        "graph": graph_stats,
        "sessions": app.state.cycle.sessions.list_sessions() if app.state.cycle else []
    }

# ── Chat ──

@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: Request, req: ChatRequest):
    if not request.app.state.initialized:
        return ChatResponse(response="系统正在初始化，请稍后...", session_id=req.session_id)
    result = await request.app.state.cycle.process_text(req.text, req.session_id or None)
    sid = req.session_id
    if not sid:
        # Get the last session ID from the cycle's sessions
        sessions = request.app.state.cycle.sessions.list_sessions()
        sid = sessions[0]["id"] if sessions else "unknown"
    return ChatResponse(response=result, session_id=sid)

# ── Sessions (持久化) ──

@router.get("/api/sessions")
async def list_sessions(request: Request):
    if not request.app.state.cycle:
        return {"sessions": []}
    return {"sessions": request.app.state.cycle.sessions.list_sessions()}

@router.get("/api/session/{session_id}")
async def get_session(request: Request, session_id: str):
    if not request.app.state.cycle:
        return {"error": "Not initialized"}
    session = request.app.state.cycle.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "id": session.id,
        "title": session.title,
        "messages": [{"role": m.role, "content": m.content, "timestamp": m.timestamp}
                     for m in session.messages],
        "created_at": session.created_at,
        "last_active": session.last_active,
    }

@router.delete("/api/session/{session_id}")
async def delete_session(request: Request, session_id: str):
    if not request.app.state.cycle:
        return {"error": "Not initialized"}
    request.app.state.cycle.sessions.delete(session_id)
    return {"status": "deleted", "session_id": session_id}

@router.patch("/api/session/{session_id}")
async def rename_session(request: Request, session_id: str):
    if not request.app.state.cycle:
        return {"error": "Not initialized"}
    body = await request.json()
    new_title = body.get("title", "").strip()
    if new_title:
        request.app.state.cycle.sessions.rename(session_id, new_title)
    return {"status": "renamed", "session_id": session_id, "title": new_title}

# ── Personality ──

@router.get("/api/personality")
async def get_personality(request: Request):
    if not request.app.state.cycle or not request.app.state.cycle.memory:
        return {"error": "Not initialized"}
    mem = request.app.state.cycle.memory
    return {
        "personality": mem.personality.to_dict(),
        "emotional_state": mem.pad.get_emotional_state(),
        "history": mem.pad.get_history(20),
        "personalities": {code: tmpl.to_dict() for code, tmpl in TYPES.items()},
    }

@router.post("/api/personality/switch")
async def switch_personality(request: Request):
    if not request.app.state.cycle or not request.app.state.cycle.memory:
        return {"error": "Not initialized"}
    body = await request.json()
    code = body.get("code", "OJBK")
    mem = request.app.state.cycle.memory
    mem.personality.set_type(code)
    mem._sync_pad_baseline()
    # Update config
    cfg = _load_config()
    cfg.setdefault("personality", {})["active"] = code
    _save_config(cfg)
    return {"status": "switched", "code": code}

@router.post("/api/personality/evolution")
async def toggle_evolution(request: Request):
    if not request.app.state.cycle or not request.app.state.cycle.memory:
        return {"error": "Not initialized"}
    body = await request.json()
    enabled = body.get("enabled", False)
    rate = body.get("rate", 0.02)
    mem = request.app.state.cycle.memory
    mem.personality.evolution_enabled = enabled
    mem.personality.evolution_rate = rate
    cfg = _load_config()
    cfg.setdefault("personality", {})["evolution"] = enabled
    cfg.setdefault("personality", {})["evolution_rate"] = rate
    _save_config(cfg)
    return {"status": "updated", "evolution": enabled, "rate": rate}

@router.post("/api/personality/impacts")
async def set_personality_impacts(request: Request):
    if not request.app.state.cycle or not request.app.state.cycle.memory:
        return {"error": "Not initialized"}
    body = await request.json()
    impacts = body.get("impacts", {})
    mem = request.app.state.cycle.memory
    mem.personality.set_impacts(impacts)
    # 重新同步PAD和遗忘
    mem._sync_pad_baseline()
    mem._sync_forgetting()
    # 保存到配置
    cfg = _load_config()
    cfg.setdefault("personality", {})["impacts"] = mem.personality.impacts
    _save_config(cfg)
    return {"status": "updated", "impacts": mem.personality.impacts}

# ── Memory ──

@router.get("/api/memory/stats")
async def memory_stats(request: Request):
    if not request.app.state.memory:
        return {"error": "Memory not initialized"}
    return {
        "initialized": request.app.state.memory.initialized,
        "long_term_count": request.app.state.memory.long_term.count(),
        "graph": request.app.state.memory.graph.get_stats(),
    }

@router.get("/api/memory/search")
async def memory_search(request: Request, q: str = "", top_k: int = 5):
    if not request.app.state.memory or not q:
        return {"results": []}
    results = request.app.state.memory.long_term.search(q, top_k=top_k)
    return {"results": results}

@router.post("/api/memory/forget/{memory_id}")
async def forget_memory(request: Request, memory_id: int):
    if not request.app.state.memory:
        return {"error": "Memory not initialized"}
    request.app.state.memory.long_term.delete(memory_id)
    return {"status": "deleted", "memory_id": memory_id}

# ── Tools ──

@router.get("/api/tools")
async def list_tools(request: Request):
    if not request.app.state.executor:
        return {"tools": []}
    return {"tools": request.app.state.executor.registry.list_tools()}

# ── Config ──

@router.get("/api/config")
async def get_config():
    return _load_config()

@router.put("/api/config")
async def update_config(request: Request):
    body = await request.json()
    cfg = _load_config()
    _deep_merge(cfg, body)
    _save_config(cfg)
    return {"status": "saved", "config": cfg}

# ── Model Templates ──

@router.get("/api/models/templates")
async def model_templates():
    return {"templates": _get_templates()}

# ── Model CRUD ──

@router.post("/api/models/test-connection")
async def test_connection(request: Request):
    body = await request.json()
    url = body.get("base_url", "").rstrip("/")
    key = body.get("api_key", "")
    need_key = body.get("need_key", True)
    if not url:
        return {"ok": False, "error": "Base URL 为空"}
    if need_key and not key:
        return {"ok": False, "error": "该提供商需要 API 密钥"}
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{url}/models", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("id", m.get("name", "")) for m in data.get("data", []) if m.get("id") or m.get("name")]
                return {"ok": True, "models_count": len(models),
                        "models": models[:200], "elapsed": "<1s"}
            elif resp.status_code == 401 or resp.status_code == 403:
                return {"ok": False, "error": f"认证失败 (HTTP {resp.status_code})，请检查 API 密钥"}
            return {"ok": True, "status": resp.status_code, "elapsed": "<2s"}
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接到服务器，请检查 Base URL"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

@router.get("/api/models/{category}")
async def list_models(category: str):
    cfg = _load_config()
    models = cfg.get("models", {}).get(category, {})
    return {"category": category, "active": models.get("active", ""),
            "entries": models.get("entries", [])}

@router.post("/api/models/{category}")
async def add_model(category: str, request: Request):
    body = await request.json()
    cfg = _load_config()
    entries = cfg.setdefault("models", {}).setdefault(category, {}).setdefault("entries", [])
    entries.append(body)
    if not cfg["models"][category].get("active"):
        cfg["models"][category]["active"] = body.get("name", "")
    _save_config(cfg)
    return {"status": "added", "entries": entries}

@router.put("/api/models/{category}/{name}")
async def update_model(category: str, name: str, request: Request):
    body = await request.json()
    cfg = _load_config()
    entries = cfg.get("models", {}).get(category, {}).get("entries", [])
    for i, e in enumerate(entries):
        if e.get("name") == name:
            entries[i] = body
            _save_config(cfg)
            return {"status": "updated", "entry": body}
    return {"error": "not found"}

@router.delete("/api/models/{category}/{name}")
async def delete_model(category: str, name: str):
    cfg = _load_config()
    entries = cfg.get("models", {}).get(category, {}).get("entries", [])
    cfg["models"][category]["entries"] = [e for e in entries if e.get("name") != name]
    if cfg["models"][category].get("active") == name:
        cfg["models"][category]["active"] = ""
    _save_config(cfg)
    return {"status": "deleted"}

@router.post("/api/models/{category}/activate/{name}")
async def activate_model(category: str, name: str):
    cfg = _load_config()
    entries = cfg.get("models", {}).get(category, {}).get("entries", [])
    if not any(e.get("name") == name for e in entries):
        return {"error": "model not found"}
    cfg["models"][category]["active"] = name
    _save_config(cfg)
    return {"status": "activated", "category": category, "active": name}

@router.post("/api/models/search/{provider}")
async def search_provider_models(provider: str, request: Request):
    """Proxy to search provider's models list."""
    body = await request.json()
    templates = _get_templates()
    tmpl = next((t for t in templates if t["id"] == provider), None)
    if not tmpl or not tmpl.get("models_url"):
        return {"ok": False, "error": "该提供商不支持自动搜索"}
    models_url = tmpl["models_url"]
    key = body.get("api_key", "")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(models_url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                # Handle both OpenAI format (data[].id) and Ollama format (models[].name)
                models = []
                if "data" in data and isinstance(data["data"], list):
                    models = [m.get("id", "") for m in data["data"] if m.get("id")]
                elif "models" in data and isinstance(data["models"], list):
                    models = [m.get("name", "") for m in data["models"] if m.get("name")]
                return {"ok": True, "models": models[:300]}
            elif resp.status_code == 401:
                return {"ok": False, "error": "认证失败，请检查 API 密钥"}
            else:
                return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "error": "无法连接，请检查 Base URL"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

# ── System ──

@router.get("/api/system")
async def system_info():
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=0.5)
        disk = psutil.disk_usage("/")
        return {
            "cpu": {"percent": cpu_percent, "count": psutil.cpu_count()},
            "memory": {"total": mem.total, "available": mem.available,
                        "percent": mem.percent, "used": mem.used},
            "disk": {"total": disk.total, "free": disk.free, "percent": disk.percent},
            "hostname": os.uname().nodename,
            "platform": f"{os.uname().sysname} {os.uname().release}",
            "python": os.sys.version.split()[0],
            "uptime": open("/proc/uptime").read().split()[0]
        }
    except ImportError:
        return {"error": "psutil not available"}

# ── Audio devices ──

@router.get("/api/devices/audio")
async def list_audio_devices():
    devices = {"input": [], "output": []}
    try:
        inp = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
        outp = subprocess.run(["aplay", "-l"], capture_output=True, text=True, timeout=5)
        for line in inp.stdout.split("\n"):
            if "card" in line.lower():
                devices["input"].append(line.strip())
        for line in outp.stdout.split("\n"):
            if "card" in line.lower() and line.strip() not in devices["input"]:
                devices["output"].append(line.strip())
    except Exception:
        pass
    try:
        pactl = subprocess.run(["pactl", "list", "sources", "short"],
                               capture_output=True, text=True, timeout=5)
        for line in pactl.stdout.split("\n"):
            if line.strip():
                devices["input"].append(f"[Pulse] {line.strip()}")
        pactl_out = subprocess.run(["pactl", "list", "sinks", "short"],
                                   capture_output=True, text=True, timeout=5)
        for line in pactl_out.stdout.split("\n"):
            if line.strip():
                devices["output"].append(f"[Pulse] {line.strip()}")
    except Exception:
        pass
    return devices

# ── Wake Word Management ──

WAKE_WORDS_DIR = os.environ.get("LAZ_WAKE_WORDS", os.path.join(os.path.dirname(__file__), "..", "wake_words"))


@router.get("/api/audio/wakewords")
async def list_wake_words():
    """列出所有已上传的 ONNX 唤醒词文件"""
    import os
    import os.path
    models = []
    if os.path.isdir(WAKE_WORDS_DIR):
        for fname in sorted(os.listdir(WAKE_WORDS_DIR)):
            if fname.endswith(".onnx"):
                fpath = os.path.join(WAKE_WORDS_DIR, fname)
                name = fname[:-5]  # strip .onnx
                fsize = os.path.getsize(fpath)
                models.append({
                    "filename": fname,
                    "name": name,
                    "size": fsize,
                    "size_str": f"{fsize/1024:.1f} KB" if fsize >= 1024 else f"{fsize} B",
                })
    # Read active wake words from config
    cfg = _load_config()
    active = cfg.get("voice", {}).get("wake_words", [])
    wake_threshold = cfg.get("voice", {}).get("wake_threshold", 0.5)
    return {"models": models, "active": active, "wake_threshold": wake_threshold}


@router.post("/api/audio/wakewords/upload")
async def upload_wake_words(request: Request):
    """上传一个或多个 .onnx 唤醒词文件"""
    import os
    import shutil

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return {"error": "需要 multipart/form-data"}

    form = await request.form()
    files_uploaded = []
    errors = []

    for field_name, upload in form.items():
        # Only accept .onnx files
        if not upload.filename or not upload.filename.endswith(".onnx"):
            continue
        fname = upload.filename
        # Sanitize filename — keep only safe chars
        safe_name = "".join(c for c in fname if c.isalnum() or c in "._-")
        if not safe_name.endswith(".onnx"):
            errors.append(f"{fname}: invalid filename")
            continue

        fpath = os.path.join(WAKE_WORDS_DIR, safe_name)
        content = await upload.read()

        # Basic validation — ONNX starts with protobuf tag 0x08 (ir_version field)
        if len(content) < 4 or content[0] != 0x08:
            errors.append(f"{fname}: not a valid ONNX file")
            continue

        with open(fpath, "wb") as f:
            f.write(content)
        files_uploaded.append({
            "filename": safe_name,
            "name": safe_name[:-5],
            "size": len(content),
        })

    if not files_uploaded and not errors:
        return {"error": "未收到有效的 .onnx 文件"}
    return {"uploaded": files_uploaded, "errors": errors}


@router.delete("/api/audio/wakewords/{filename}")
async def delete_wake_word(filename: str):
    """删除指定唤醒词文件"""
    import os
    # Sanitize
    safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
    fpath = os.path.join(WAKE_WORDS_DIR, safe_name)
    if not os.path.isfile(fpath) or not fpath.endswith(".onnx"):
        return {"error": "文件不存在"}
    os.remove(fpath)
    # If this was the active model, clear it from config
    name = safe_name[:-5] if safe_name.endswith(".onnx") else safe_name
    cfg = _load_config()
    wake_words = cfg.get("voice", {}).get("wake_words", [])
    if name in wake_words:
        wake_words.remove(name)
        cfg.setdefault("voice", {})["wake_words"] = wake_words
        if cfg["voice"].get("wake_model_path", "").endswith(safe_name):
            cfg["voice"]["wake_model_path"] = ""
        _save_config(cfg)
    return {"status": "deleted", "name": name}


@router.post("/api/audio/wakewords/activate")
async def activate_wake_words(request: Request):
    """设置活跃的唤醒词列表"""
    body = await request.json()
    active = body.get("active", [])
    threshold = body.get("wake_threshold", 0.5)
    wake_model_path = body.get("wake_model_path", "")

    if not isinstance(active, list):
        return {"error": "active 必须是数组"}

    cfg = _load_config()
    cfg.setdefault("voice", {})["wake_words"] = active
    cfg["voice"]["wake_threshold"] = float(threshold)
    if wake_model_path:
        cfg["voice"]["wake_model_path"] = wake_model_path
    _save_config(cfg)
    return {"status": "saved", "active": active, "wake_threshold": threshold}

@router.get("/api/service/status")
async def service_status():
    try:
        result = subprocess.run(["systemctl", "is-active", "laz-bot"],
                                capture_output=True, text=True, timeout=5)
        return {"service": "laz-bot", "status": result.stdout.strip()}
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/service/restart")
async def service_restart():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "laz-bot"],
                       capture_output=True, text=True, timeout=30)
        return {"status": "restarting"}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/service/logs")
async def get_logs(lines: int = 50):
    try:
        result = subprocess.run(["journalctl", "-u", "laz-bot", "-n", str(lines),
                                 "--no-pager", "-o", "short-precise"],
                                capture_output=True, text=True, timeout=10)
        return {"logs": result.stdout}
    except Exception as e:
        return {"error": str(e)}

# ── VU Meter WebSocket (独立于语音管线，实时显示电平) ──

@router.websocket("/ws/vu")
async def vu_meter_websocket(ws: WebSocket):
    await ws.accept()
    import asyncio, time, numpy as np
    from voice_pipeline.alsa_capture import AlsaCapture

    # 从配置读取设备
    cfg = _load_config()
    vc = cfg.get("voice", {})
    device = vc.get("input_device", "plughw:2,0")

    cap = AlsaCapture(device=device, sample_rate=48000, channels=1, frame_size=1024)
    try:
        # 用 arecord -l 先验证设备存在
        import subprocess as sp
        r = sp.run(["arecord", "-l"], capture_output=True, text=True, timeout=3)
        if "card" not in r.stdout and device != "plughw:2,0":
            await ws.send_json({"type": "vu_error", "data": f"设备 {device} 可能不可用"})

        cap.start()
        # 预热：丢弃前几帧避免启动噪音
        for _ in range(5):
            cap.read()
            await asyncio.sleep(0.001)

        await ws.send_json({"type": "vu_ready", "data": f"VU 表已启动 ({device})"})

        while True:
            arr = cap.read()
            rms = float(np.sqrt(np.mean(arr ** 2)))
            peak = float(np.max(np.abs(arr)))
            db = 20 * np.log10(max(rms, 1e-6))
            await ws.send_json({
                "type": "vu_input",
                "data": {
                    "rms": round(rms, 5),
                    "db": round(db, 1),
                    "peak": round(peak, 4),
                }
            })
            await asyncio.sleep(0.08)  # 约 12Hz 刷新
    except asyncio.CancelledError:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "vu_error", "data": str(e)})
        except Exception:
            pass
    finally:
        cap.stop()