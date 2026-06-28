"""PAD 3D 情绪模型 — Pleasure, Arousal, Dominance

每个维度 [-1.0, 1.0]:
  Pleasure:   痛苦↔愉悦
  Arousal:    平静↔兴奋
  Dominance:  被动↔主导
"""
import re
import math
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("laz-bot.pad")

# ── 基础情绪词 → PAD 映射（中文+英文）──
EMOTION_LEXICON = {
    # 积极高唤醒
    "开心":      (0.8,  0.7,  0.3),
    "兴奋":      (0.7,  0.9,  0.5),
    "激动":      (0.6,  0.9,  0.6),
    "惊喜":      (0.9,  0.8,  0.4),
    "快乐":      (0.9,  0.5,  0.3),
    "高兴":      (0.8,  0.5,  0.3),
    "喜欢":      (0.7,  0.6,  0.4),
    "爱":        (0.9,  0.5,  0.3),
    "赞":        (0.6,  0.4,  0.5),
    "太棒了":    (0.9,  0.8,  0.6),
    "happy":     (0.8,  0.6,  0.4),
    "excited":   (0.7,  0.9,  0.5),
    "amazing":   (0.9,  0.8,  0.6),
    "love":      (0.9,  0.5,  0.3),

    # 积极低唤醒
    "满足":      (0.7,  0.1,  0.2),
    "平静":      (0.5, -0.4,  0.0),
    "放松":      (0.6, -0.5, -0.1),
    "安心":      (0.6, -0.3, -0.2),
    "舒服":      (0.7, -0.3,  0.0),
    "满意":      (0.6,  0.0,  0.2),
    "calm":      (0.5, -0.4,  0.0),
    "relaxed":   (0.6, -0.5,  0.0),

    # 消极高唤醒
    "生气":      (-0.7,  0.8,  0.6),
    "愤怒":      (-0.8,  0.9,  0.7),
    "烦躁":      (-0.5,  0.7,  0.3),
    "焦虑":      (-0.4,  0.8, -0.3),
    "紧张":      (-0.3,  0.8, -0.4),
    "害怕":      (-0.7,  0.7, -0.6),
    "恐惧":      (-0.8,  0.8, -0.7),
    "失控":      (-0.6,  0.6, -0.8),
    "angry":     (-0.7,  0.8,  0.6),
    "anxious":   (-0.4,  0.8, -0.3),
    "scared":    (-0.7,  0.7, -0.6),

    # 消极低唤醒
    "悲伤":      (-0.7, -0.3, -0.3),
    "难过":      (-0.6, -0.2, -0.2),
    "失望":      (-0.5, -0.1, -0.4),
    "郁闷":      (-0.4, -0.5, -0.3),
    "累":        (-0.3, -0.7, -0.4),
    "疲惫":      (-0.4, -0.8, -0.5),
    "无聊":      (-0.3, -0.6, -0.2),
    "无奈":      (-0.3, -0.2, -0.5),
    "沮丧":      (-0.5, -0.3, -0.5),
    "sad":       (-0.7, -0.3, -0.3),
    "tired":     (-0.3, -0.7, -0.4),
    "bored":     (-0.3, -0.6, -0.3),

    # 中性
    "嗯":        (0.0, -0.2,  0.0),
    "哦":        (0.0, -0.3, -0.1),
    "好的":      (0.2,  0.0,  0.1),
    "知道":      (0.1,  0.0,  0.2),
    "ok":        (0.2,  0.0,  0.1),

    # 标点/表情暗示
    "!":         (0.1,  0.4,  0.2),
    "？":        (-0.1,  0.2, -0.1),
    "?":         (-0.1,  0.2, -0.1),
    "😂":        (0.8,  0.7,  0.3),
    "😭":        (-0.7,  0.3, -0.3),
    "😡":        (-0.8,  0.9,  0.6),
    "❤️":        (0.9,  0.4,  0.2),
    "👍":        (0.6,  0.3,  0.4),
    "😊":        (0.7,  0.3,  0.2),
    "😢":        (-0.6, -0.2, -0.3),
}


@dataclass
class PADState:
    pleasure: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0

    def clamp(self):
        self.pleasure = max(-1.0, min(1.0, self.pleasure))
        self.arousal = max(-1.0, min(1.0, self.arousal))
        self.dominance = max(-1.0, min(1.0, self.dominance))

    def to_dict(self) -> dict:
        return {"pleasure": round(self.pleasure, 3),
                "arousal": round(self.arousal, 3),
                "dominance": round(self.dominance, 3)}

    def magnitude(self) -> float:
        """情绪强度（向量的模长）"""
        return math.sqrt(self.pleasure**2 + self.arousal**2 + self.dominance**2) / math.sqrt(3)

    def valence_label(self) -> str:
        """情绪定性标签"""
        if self.pleasure > 0.3 and self.arousal > 0.3:
            return "兴奋"
        elif self.pleasure > 0.3 and self.arousal <= 0.3:
            return "愉悦"
        elif self.pleasure < -0.3 and self.arousal > 0.3:
            return "焦躁"
        elif self.pleasure < -0.3 and self.arousal <= 0.3:
            return "低落"
        else:
            return "平静"


class PADEmotionModel:
    """PAD 情绪模型 — 分析文本 + 平滑更新 + 基线漂移"""

    def __init__(self, baseline: Optional[PADState] = None,
                 decay_rate: float = 0.3,   # 情绪自然衰减回基线速度
                 lr: float = 0.15):         # 单次文本影响的学习率
        self.baseline = baseline or PADState()
        self.current = PADState(
            self.baseline.pleasure,
            self.baseline.arousal,
            self.baseline.dominance,
        )
        self.decay_rate = decay_rate
        self.lr = lr
        self.history: list[dict] = []  # 情绪历史记录

    def set_baseline(self, p: float, a: float, d: float):
        self.baseline = PADState(p, a, d)
        # 逐渐拉向新基线
        self.current.pleasure += (p - self.current.pleasure) * 0.3
        self.current.arousal += (a - self.current.arousal) * 0.3
        self.current.dominance += (d - self.current.dominance) * 0.3
        self.current.clamp()

    def analyze_text(self, text: str) -> PADState:
        """从文本中提取情绪偏移"""
        if not text:
            return PADState()

        pad = PADState()
        matched = 0
        text_lower = text.lower()

        for word, (p, a, d) in EMOTION_LEXICON.items():
            if word in text or word in text_lower:
                pad.pleasure += p
                pad.arousal += a
                pad.dominance += d
                matched += 1

        # 表情符号检测
        emoji_positive = text.count("😊") + text.count("👍") + text.count("😂") + text.count("❤️")
        emoji_negative = text.count("😭") + text.count("😡") + text.count("😢")
        if emoji_positive > emoji_negative:
            pad.pleasure += 0.2 * (emoji_positive - emoji_negative)
            matched += 1
        elif emoji_negative > emoji_positive:
            pad.pleasure -= 0.2 * (emoji_negative - emoji_positive)
            matched += 1

        if matched:
            pad.pleasure /= matched
            pad.arousal /= matched
            pad.dominance /= matched

        return pad

    def update(self, text: str):
        """输入对话文本，更新当前情绪状态"""
        delta = self.analyze_text(text)
        if abs(delta.pleasure) < 0.01 and abs(delta.arousal) < 0.01 and abs(delta.dominance) < 0.01:
            return  # 无情绪信号

        # 平滑更新
        self.current.pleasure += (delta.pleasure - self.current.pleasure) * self.lr
        self.current.arousal += (delta.arousal - self.current.arousal) * self.lr
        self.current.dominance += (delta.dominance - self.current.dominance) * self.lr
        self.current.clamp()

    def decay(self):
        """情绪自然衰减——朝基线收敛"""
        self.current.pleasure += (self.baseline.pleasure - self.current.pleasure) * self.decay_rate
        self.current.arousal += (self.baseline.arousal - self.current.arousal) * self.decay_rate
        self.current.dominance += (self.baseline.dominance - self.current.dominance) * self.decay_rate
        self.current.clamp()

    def record_history(self):
        """记录当前情绪快照"""
        self.history.append({
            "timestamp": __import__("time").time(),
            **self.current.to_dict(),
            "label": self.current.valence_label(),
        })
        # 保留最近1000条
        if len(self.history) > 1000:
            self.history = self.history[-1000:]

    def get_emotional_state(self) -> dict:
        return {
            **self.current.to_dict(),
            "label": self.current.valence_label(),
            "magnitude": round(self.current.magnitude(), 3),
            "baseline": self.baseline.to_dict(),
        }

    def get_history(self, n: int = 50) -> list:
        return self.history[-n:] if self.history else []
