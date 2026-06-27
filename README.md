# LAZ-Bot — 融合智能体

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

**LAZ-Bot** 是一个运行在树莓派上的融合智能体，实现完整的 7 阶段认知循环：

```
感知 → 注意 → 记忆检索 → 推理 → 决策 → 执行 → 学习
```

核心特性：
- 🧠 **Sovyx 风格三级记忆** — 短期 (deque) + 长期向量 (sqlite-vec) + 脑图 (EpisodicGraph)
- ⏳ **Ebbinghaus 遗忘调度** — 模拟人类记忆衰减曲线
- 🔗 **Hebbian 突触学习** — 概念共现自动强化关联
- 🎤 **语音交互** — ALSA 原生采集/播放，智能 VAD，唤醒词检测
- 🔄 **LLM 网关** — 多模型模板式管理，支持 Open WebUI 中转代理
- 📊 **Web 管理界面** — 仪表盘/聊天/音频/模型/记忆/设置

## 架构

```
用户 → [唤醒词/VAD] → STT → LLM(Open WebUI 中转/RAG) → TTS → 播放
                          ↕
                    记忆融合引擎
                  (短期+长期+脑图+遗忘)
```

## 快速开始

### 前置条件

- Python 3.10+
- 树莓派 (或其他 Linux 设备)
- 可选: USB 麦克风/音箱 (用于语音)

### 安装

```bash
# 1. 克隆
git clone https://github.com/yourname/laz-bot.git
cd laz-bot

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入你的 API Key 和模型配置

# 5. 初始化数据库
python3 -c "from memory.memory_service import MemoryService; import yaml; cfg=yaml.safe_load(open('config.yaml')); MemoryService(cfg)"

# 6. 启动
python -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8765

# 7. 打开管理界面
# http://your-ip:8765/admin
```

### 可选：语音管线

```bash
# 安装音频依赖
sudo apt install alsa-utils ffmpeg

# 上传唤醒词 ONNX 模型到 wake_words/ 目录
# 在管理界面 → 音频管道 → 唤醒词管理 上传
```

### 可选：Open WebUI (RAG 知识库)

```bash
docker run -d --network host \
  -v openwebui:/app/backend/data \
  -e WEBUI_SECRET_KEY=your-secret \
  ghcr.io/open-webui/open-webui:main
```

然后在 LAZ-Bot 管理界面 → 模型配置 中添加 Open WebUI 作为 LLM 代理。

## 配置说明

`config.yaml` 结构：

```yaml
models:
  llm:
    active: "my-llm"          # 当前活跃的 LLM 模型名
    entries:                  # 模型列表，每项独立 API Key
      - name: my-llm
        provider: siliconflow
        base_url: https://api.siliconflow.cn/v1
        api_key: YOUR_API_KEY
        model_id: deepseek-ai/DeepSeek-V3
  embedding: {...}            # 嵌入模型
  stt: {...}                  # 语音识别
  tts: {...}                  # 语音合成

voice:
  input_device: "plughw:2,0"  # ALSA 设备
  wake_words: ["jiweisi"]      # 唤醒词列表
  wake_model_path: "wake_words/jiweisi.onnx"
  speech_threshold: 0.02       # VAD 高阈值
  silence_threshold: 0.008     # VAD 低阈值
  ...
```

详细配置见 `config.yaml.example`。

## 项目结构

```
laz-bot/
├── orchestrator/          # 核心编排 (路由/认知循环/LLM网关)
├── memory/                # 记忆系统 (短期/长期/脑图/遗忘)
├── voice_pipeline/        # 语音管线 (ALSA采集/VAD/唤醒词/STT/TTS)
├── admin/                 # Web 管理界面 (SPA)
├── scripts/               # 部署/安装脚本
├── config.yaml.example    # 配置模板
└── requirements.txt       # Python 依赖
```

## 唤醒词训练

使用 [openWakeWord](https://github.com/dscripka/openWakeWord) 训练自定义唤醒词：

1. 录制 100+ 个正样本音频 (你的唤醒词)
2. 在 PC 上训练，导出 ONNX 模型
3. 在管理界面上传或直接放到 `wake_words/` 目录
4. 勾选激活即可使用

## License

Apache 2.0 — 详见 [LICENSE](LICENSE)
