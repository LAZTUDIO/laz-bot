# LAZ-Bot — SBTI 人格伴侣 · 树莓派语音交互终端

（测试版）

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPLv3-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.com/)

**LAZ-Bot** 不是一个普通聊天机器人——它是一个**有性格的树莓派融合智能体**。

基于 SBTI 人格体系（27 种人格类型 × 15 维度评分 × PAD 三维情绪模型），LAZ-Bot 不只是"回答问题"，而是**以某种人格的身份与你对话**。CTRL 拿捏者冷静克制，LOVE-R 多情者热情温暖，IMSB 傻者充满内心戏——你的人格伴侣，你说了算。

---

## ✨ 为什么是 LAZ-Bot？

| 常规聊天机器人 | LAZ-Bot |
|:---|:---|
| 标准化的回答风格 | 人格驱动的语气、节奏、情绪 |
| 无记忆的对话 | 三级记忆 + 艾宾浩斯遗忘 + Hebbian 突触学习 |
| 冷冰冰的文本交互 | PAD 三维情绪状态影响每一次回复 |
| 人格只是角色设定 | 人格直接映射到 PAD 基线、回复长度、温暖度、信任假设 |

---

## 🧬 核心特性

### SBTI 人格引擎

- 🎭 **27 种人格类型** — 25 种标准人格（CTRL 拿捏者、BOSS 领导者、SEXY 尤物……）+ 2 种隐藏人格（DRUNK 酒鬼、HHHH 傻乐者）
- 📐 **15 维度评分体系** — 5 大模型（自我 / 情感 / 态度 / 行动驱力 / 社交）各 3 维度
- 🔀 **人格 → 系统行为映射** — 人格不再只是标签，而是实打实影响 8 个系统层面：
  - **PAD 情绪基线** — S1 自尊高 → 支配感 +0.4；E1 安全感低 → 愉悦感 -0.3
  - **LLM 提示词注入** — 人格描述、特质、关联概念写进 system prompt
  - **回复长度** — 外向者更健谈，MONK 僧人言简意赅
  - **语气冷暖** — MUM 妈妈温柔共情，SHIT 愤世者距离感十足
  - **信任假设** — E1 安全感高的给予信任，安全感低的保持警觉
  - **直白程度** — FUCK 草者直来直去，FAKE 伪人绕弯子
  - **记忆衰减速度** — Hebbian 学习率 × 人格因子，不同人格忘性不同
  - **TTS 语速** — THIN-K 思考者语速偏慢（在思考），GOGO 行者语速偏快
- 🎛️ **8 个独立开关** — 每项人格影响都可以单独开关，像调音台一样控制人格对系统的干预程度

### PAD 三维情绪模型

- 😊 **愉悦度 (Pleasure)** — 从低落到愉快
- ⚡ **唤醒度 (Arousal)** — 从平静到兴奋
- 🎮 **支配感 (Dominance)** — 从被动到掌控

每次对话后根据文本分析 PAD 值并平滑衰减回人格基线。这意味着：

> 你骂了他一句 → 他愉悦度下降 → 下轮对话会带着情绪回应
> 你夸了他 → 他愉悦度上升 → 对话氛围变轻松

### 认知与记忆

- 🧠 **7 阶段认知循环** — 感知 → 注意 → 记忆检索 → 推理 → 决策 → 执行 → 学习
- 📝 **三级记忆系统**
  - **短期记忆** (deque) — 最近 10 轮对话上下文
  - **长期记忆** (sqlite-vec) — 向量化语义检索，你提过的事情他会记得
  - **情节图谱** (EpisodicGraph) — 概念之间的关联网络，越常共现越紧密
- ⏳ **Ebbinghaus 遗忘调度** — 模拟人类记忆衰减曲线，无关紧要的事自动淡忘
- 🔗 **Hebbian 突触学习** — "猫"和"可爱"经常一起出现 → 自动强化关联

### 语音交互

- 🎤 **ALSA 原生采集/播放** — 无需额外音频框架
- 📢 **VU 表实时显示** — WebSocket 推流，看到语音电平
- 🔔 **唤醒词检测** — 支持 openWakeWord，自定义唤醒词（上传 ONNX 即可）
- 🗣️ **STT/TTS 可替换** — 支持 OpenAI / 硅基流动等多家语音接口

### LLM 网关

- 🔄 **多模型模板式管理** — 11 家提供商开箱即用（DeepSeek / 智谱 / 通义 / OpenAI / Ollama 等）
- 🧩 **Open WebUI 中转代理** — 支持 RAG 知识库增强
- 🛠️ **工具调用框架** — LLM 可以执行系统命令、查天气、控制 GPIO

### Web 管理界面

- 📊 **仪表盘** — 系统状态一目了然
- 💬 **聊天面板** — Web 端文本对话，带人格/情绪标注
- 🎭 **人格切换** — 下拉选择 27 种人格，实时生效
- 🎛️ **人格影响调音台** — 8 个拨动开关精细控制
- 🧠 **记忆检索** — 搜索、遗忘、查看记忆统计
- 🎤 **音频配置** — 设备选择、唤醒词上传、STT/TTS 模型切换

---

## 🧭 架构

```
                     ┌──────────────────────────────┐
                     │      SBTI 人格引擎           │
                     │  27 种人格 × 15 维 × PAD    │
                     └──────────────┬───────────────┘
                                    │ 人格参数（PAD基线、语气、回复长度...）
                                    ▼
用户 ─→ [唤醒词/VAD] ─→ STT ─→ LLM 推理 ─→ TTS ─→ 播放
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                     短期记忆   长期向量   情节图谱
                   (对话上下文) (语义检索) (概念关联)
                          │         │         │
                          └─────────┼─────────┘
                                    ▼
                        Ebbinghaus 遗忘 + Hebbian 学习
```

---

## 🚀 快速开始

### 前置条件

- Python 3.10+
- 树莓派 5（或其他 Linux 设备，macOS/Windows 也支持，但音频管道依赖 ALSA）
- 可选：USB 麦克风/音箱（用于语音交互）

### 安装

```bash
# 1. 克隆
git clone https://github.com/LAZTUDIO/laz-bot.git
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
# http://你的树莓派IP:8765/admin
```

### 首次上手：体验人格切换

1. 启动后在浏览器打开管理界面
2. 默认人格是 CTRL（拿捏者）
3. 进入「人格管理」标签，换一个人格试试，比如 LOVE-R（多情者）
4. 回到聊天面板，观察他的语气和回复风格变化
5. 进入「人格影响」调音台，调整哪些人格维度影响系统行为

### 可选：语音管线

```bash
# 安装音频依赖
sudo apt install alsa-utils ffmpeg

# 上传唤醒词 ONNX 模型到 wake_words/ 目录
# 在管理界面 → 音频管道 → 唤醒词管理 上传
```

### 可选：Open WebUI（RAG 知识库）

```bash
docker run -d --network host \
  -v openwebui:/app/backend/data \
  -e WEBUI_SECRET_KEY=your-secret \
  ghcr.io/open-webui/open-webui:main
```

然后在 LAZ-Bot 管理界面 → 模型配置中添加 Open WebUI 作为 LLM 代理。

---

## ⚙️ 配置说明

`config.yaml` 核心结构：

```yaml
personality:
  type: "CTRL"              # 初始人格（27 种可选）
  evolution_enabled: false  # 人格演化（开发中）
  impacts:                  # 人格影响开关（8 个独立控制）
    pad_baseline: true      # PAD 情绪基线
    llm_prompt: true        # 人格注入 system prompt
    warmth_tone: true       # 语气冷暖
    reply_length: true      # 回复长度
    memory_decay: true      # 记忆衰减速度
    hebbian_lr: true        # Hebbian 学习率
    importance_bias: true   # 记忆重要性偏差
    tts_speed: true         # TTS 语速

models:
  llm:
    active: "my-llm"
    entries:
      - name: my-llm
        provider: siliconflow
        base_url: https://api.siliconflow.cn/v1
        api_key: YOUR_API_KEY
        model_id: deepseek-ai/DeepSeek-V3
  embedding: {...}
  stt: {...}
  tts: {...}

voice:
  input_device: "plughw:2,0"
  wake_words: ["jiweisi"]
  wake_model_path: "wake_words/jiweisi.onnx"
  speech_threshold: 0.02
  silence_threshold: 0.008
```

详细配置见 `config.yaml.example`。

---

## 📂 项目结构

```
laz-bot/
├── orchestrator/              # 核心编排
│   ├── main.py                # FastAPI 入口
│   ├── cognitive_cycle.py     # 7 阶段认知循环
│   ├── llm_router.py          # LLM 请求路由
│   ├── model_router.py        # 多模型模板管理
│   ├── routes.py              # HTTP/WS API 路由
│   └── session_manager.py     # 会话管理
├── memory/                    # 记忆系统
│   ├── personality.py         # SBTI 人格引擎 ★
│   ├── pad_model.py           # PAD 三维情绪模型
│   ├── memory_service.py      # 记忆服务总入口
│   ├── short_term.py          # 短期记忆（对话上下文）
│   ├── long_term.py           # 长期记忆（向量检索）
│   ├── episodic_graph.py      # 情节图谱（概念关联）
│   └── forgetting.py          # Ebbinghaus 遗忘调度
├── voice_pipeline/            # 语音管线
├── admin/                     # Web 管理界面（SPA）
├── scripts/                   # 部署/安装脚本
├── config.yaml.example        # 配置模板
└── requirements.txt           # Python 依赖
```

---

## 🎭 可用人格一览

| 代号 | 名称 | 印象 | 对话风格 |
|:---|:---|:---|:---|
| CTRL | 拿捏者 | 怎么样，被我拿捏了吧？ | 冷静精准，掌控全场 |
| BOSS | 领导者 | 方向盘给我，我来开。 | 自信果断，自带气场 |
| THIN-K | 思考者 | 已深度思考 100s。 | 审慎分析，注重逻辑 |
| MUM | 妈妈 | 或许……我可以叫你妈妈吗？ | 温柔共情，治愈人心 |
| LOVE-R | 多情者 | 爱意太满，现实显得有点贫瘠。 | 热情投入，浪漫满溢 |
| SEXY | 尤物 | 您就是天生的尤物！ | 魅力四射，自信从容 |
| GOGO | 行者 | gogogo~出发咯 | 简单直接，干了再说 |
| JOKE-R | 小丑 | 原来我们都是小丑。 | 搞笑活跃，强颜欢笑 |
| OH-NO | 哦不人 | 哦不！我怎么会是这个人格？！ | 警惕性高，风险预判 |
| SHIT | 愤世者 | 这个世界，构石一坨。 | 嘴上不满，手上靠谱 |
| ATM-er | 送钱者 | 你以为我很有钱吗？ | 默默付出，有事找我 |
| MONK | 僧人 | 没有那种世俗的欲望。 | 清心寡欲，保持距离 |
| SOLO | 孤儿 | 我哭了，我怎么会是孤儿？ | 疏离自保，刺猬外壳 |
| ZZZZ | 装死者 | 我没死，我只是在睡觉。 | 能躺就躺，死线战神 |
| POOR | 贫困者 | 我穷，但我很专。 | 极度专注，不凑热闹 |
| MALO | 吗喽 | 人生是个副本，我只是吗喽。 | 松弛幽默，打破常规 |
| WOC! | 握草人 | 卧槽，我怎么是这个人格？ | 外表震惊，内心清醒 |
| OJBK | 无所谓人 | 我说随便，是真的随便。 | 事事都行，帝王淡然 |
| FAKE | 伪人 | 已经，没有人类了。 | 面具切换自如 |
| Dior-s | 屌丝 | 等着我屌丝逆袭。 | 佛系躺平，看破红尘 |
| IMSB | 傻者 | 我真的是傻逼么？ | 内心戏丰富，行动犹豫 |
| IMFW | 废物 | 我真的……是废物吗？ | 需要认可，容易信任 |
| FUCK | 草者 | 操！这是什么人格？ | 野性十足，不按套路 |
| DEAD | 死者 | 我，还活着吗？ | 超越欲望，无欲则刚 |
| THAN-K | 感恩者 | 我感谢苍天！我感谢大地！ | 积极乐观，正能量满满 |
| DRUNK | 酒鬼 | 烈酒烧喉，不得不醉。 | 🔞 隐藏人格 |
| HHHH | 傻乐者 | 哈哈哈哈哈哈。 | ⚡ 系统兜底 |

---

## 🏗️ 技术栈

| 模块 | 技术选型 |
|:---|:---|
| Web 框架 | FastAPI + WebSocket |
| LLM 网关 | OpenAI 兼容协议 (httpx) |
| 向量存储 | sqlite-vec |
| 音频采集 | ALSA (arecord/aplay) |
| VAD / 唤醒词 | webrtcvad + openWakeWord (ONNX) |
| 前端管理 | 原生 SPA (HTML/CSS/JS) |
| 配置管理 | YAML |
| 平台 | Raspberry Pi 5 (Raspberry Pi OS) |

---

## 🤝 致谢

### SBTI 人格体系

LAZ-Bot 的灵魂——27 种人格类型、15 维度评分框架、PAD 情绪映射——其人格类型体系灵感来源于 B站 [**@Q肉儿串儿**](https://www.bilibili.com/video/BV1LpDHByET6/) 创作的 SBTI 人格测试。

> 人格名称、编码和概念体系归属原作者 @Q肉儿串儿。
> 本项目的算法实现（15 维向量匹配、PAD 情绪模型、人格→系统行为映射、记忆引擎、语音管线）为独立原创工作。
> 
> 原作者说过"好玩为主，还请不要用于盈利"。LAZ-Bot 是一个个人开源项目，不涉及任何商业行为。如果你喜欢 SBTI 测试，请去 B站关注原作者！

### 开源组件

- [openWakeWord](https://github.com/dscripka/openWakeWord) — 唤醒词检测引擎
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — SQLite 向量扩展
- [FastAPI](https://fastapi.tiangolo.com/) — Python Web 框架

---

## 📜 许可证

本项目采用 **[GNU General Public License v3.0](LICENSE)** 许可证。

这意味着：
- ✅ 你可以自由使用、修改、分发本项目代码
- ✅ 你可以用于商业目的
- ❌ 如果你发布修改后的版本，**必须同样以 GPLv3 开源**
- ❌ 不能将本项目封闭源代码后分发

人格类型体系归属于原作者 @Q肉儿串儿，其名称、编码和概念的授权状态以原作者声明为准。

---

> *"已深度思考 100s……这个问题嘛，我们得从几个维度来看——"* — THIN-K 人格的 LAZ-Bot
