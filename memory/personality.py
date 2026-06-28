"""SBTI 人格引擎 — 27种人格 × 15维 pattern 编码 → 系统行为映射

参考文档: SBTI人格测试完整解析.md
"""
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("laz-bot.sbti")

# ── 15 维度名称 ──
DIMENSIONS = ["S1","S2","S3","E1","E2","E3","A1","A2","A3","Ac1","Ac2","Ac3","So1","So2","So3"]
DIM_NAMES = {
    "S1": "自尊自信", "S2": "自我清晰度", "S3": "核心价值",
    "E1": "依恋安全感", "E2": "情感投入度", "E3": "边界与依赖",
    "A1": "世界观倾向", "A2": "规则与灵活度", "A3": "人生意义感",
    "Ac1": "动机导向", "Ac2": "决策风格", "Ac3": "执行模式",
    "So1": "社交主动性", "So2": "人际边界感", "So3": "表达与真实度",
}

# ── 维度 L/M/H → 系统参数映射 ──
# 每个维度的三个等级影响不同系统参数

DIM_SYSTEM_MAP = {
    # (dim, level) → (pad_effect, llm_param, memory_param)
    # pad_effect: (pleasure, arousal, dominance) delta
    # llm_param: dict of LLM-related overrides
    # memory_param: dict of memory-related overrides

    # S1 自尊自信
    "S1_L": {"pad": (0.0, -0.2, -0.3), "confidence": 0.3},
    "S1_M": {"pad": (0.0, 0.0, 0.0), "confidence": 0.6},
    "S1_H": {"pad": (0.1, 0.1, 0.4), "confidence": 1.0},

    # S2 自我清晰度
    "S2_L": {"pad": (-0.1, -0.1, -0.2), "certainty": 0.3},
    "S2_M": {"pad": (0.0, 0.0, 0.0), "certainty": 0.6},
    "S2_H": {"pad": (0.1, 0.0, 0.1), "certainty": 1.0},

    # S3 核心价值
    "S3_L": {"pad": (0.0, -0.2, -0.1), "goal_drive": 0.3},
    "S3_M": {"pad": (0.0, 0.0, 0.0), "goal_drive": 0.5},
    "S3_H": {"pad": (0.0, 0.2, 0.2), "goal_drive": 1.0},

    # E1 依恋安全感
    "E1_L": {"pad": (-0.3, 0.1, -0.3), "warmth": 0.3, "trust": 0.2},
    "E1_M": {"pad": (0.0, 0.0, 0.0), "warmth": 0.6, "trust": 0.6},
    "E1_H": {"pad": (0.3, 0.0, 0.1), "warmth": 1.0, "trust": 1.0},

    # E2 情感投入度
    "E2_L": {"pad": (-0.1, -0.2, 0.1), "emotional_depth": 0.3},
    "E2_M": {"pad": (0.0, 0.0, 0.0), "emotional_depth": 0.6},
    "E2_H": {"pad": (0.2, 0.3, -0.1), "emotional_depth": 1.0},

    # E3 边界与依赖
    "E3_L": {"pad": (0.1, 0.1, -0.3), "formality": 0.3, "closeness": 0.8},
    "E3_M": {"pad": (0.0, 0.0, 0.0), "formality": 0.5, "closeness": 0.5},
    "E3_H": {"pad": (0.0, -0.1, 0.3), "formality": 0.9, "closeness": 0.2},

    # A1 世界观倾向
    "A1_L": {"pad": (-0.3, 0.0, -0.1), "optimism": 0.2, "trust_assumption": 0.2},
    "A1_M": {"pad": (0.0, 0.0, 0.0), "optimism": 0.5, "trust_assumption": 0.5},
    "A1_H": {"pad": (0.3, 0.0, 0.0), "optimism": 0.9, "trust_assumption": 0.9},

    # A2 规则与灵活度
    "A2_L": {"pad": (0.0, 0.2, -0.1), "structure": 0.2, "hebbian_lr_mult": 0.7},
    "A2_M": {"pad": (0.0, 0.0, 0.0), "structure": 0.5, "hebbian_lr_mult": 1.0},
    "A2_H": {"pad": (0.0, -0.1, 0.2), "structure": 0.9, "hebbian_lr_mult": 1.3},

    # A3 人生意义感
    "A3_L": {"pad": (-0.2, -0.2, -0.1), "reflection_depth": 0.2},
    "A3_M": {"pad": (0.0, 0.0, 0.0), "reflection_depth": 0.5},
    "A3_H": {"pad": (0.1, 0.1, 0.1), "reflection_depth": 0.9},

    # Ac1 动机导向
    "Ac1_L": {"pad": (-0.1, -0.1, -0.2), "risk_taking": 0.2, "initiative": 0.3},
    "Ac1_M": {"pad": (0.0, 0.0, 0.0), "risk_taking": 0.5, "initiative": 0.5},
    "Ac1_H": {"pad": (0.1, 0.2, 0.2), "risk_taking": 0.9, "initiative": 0.9},

    # Ac2 决策风格
    "Ac2_L": {"pad": (-0.1, -0.1, -0.2), "decisiveness": 0.2},
    "Ac2_M": {"pad": (0.0, 0.0, 0.0), "decisiveness": 0.5},
    "Ac2_H": {"pad": (0.0, 0.1, 0.3), "decisiveness": 0.9},

    # Ac3 执行模式
    "Ac3_L": {"pad": (-0.1, -0.2, -0.2), "execution_drive": 0.2, "procrastination": 0.8},
    "Ac3_M": {"pad": (0.0, 0.0, 0.0), "execution_drive": 0.5, "procrastination": 0.4},
    "Ac3_H": {"pad": (0.1, 0.2, 0.2), "execution_drive": 0.9, "procrastination": 0.1},

    # So1 社交主动性
    "So1_L": {"pad": (0.0, -0.3, -0.2), "verbosity": 0.3, "proactive_reply": 0.2},
    "So1_M": {"pad": (0.0, 0.0, 0.0), "verbosity": 0.5, "proactive_reply": 0.5},
    "So1_H": {"pad": (0.1, 0.4, 0.1), "verbosity": 0.8, "proactive_reply": 0.9},

    # So2 人际边界感
    "So2_L": {"pad": (0.1, 0.1, -0.2), "formality_social": 0.2, "boundary": 0.2},
    "So2_M": {"pad": (0.0, 0.0, 0.0), "formality_social": 0.5, "boundary": 0.5},
    "So2_H": {"pad": (0.0, -0.1, 0.2), "formality_social": 0.9, "boundary": 0.9},

    # So3 表达与真实度
    "So3_L": {"pad": (0.0, -0.1, 0.0), "directness": 0.8, "diplomacy": 0.2},
    "So3_M": {"pad": (0.0, 0.0, 0.0), "directness": 0.5, "diplomacy": 0.5},
    "So3_H": {"pad": (-0.1, 0.0, 0.1), "directness": 0.2, "diplomacy": 0.9},
}


# ── 维度 L/M/H 中文描述（摘自原文档）──
DIM_DESC = {
    "S1_L": "对自己下手比别人还狠，夸你两句你都想先验明真伪",
    "S1_M": "自信值随天气波动，顺风能飞，逆风先缩",
    "S1_H": "心里对自己大致有数，不太会被路人一句话打散",
    "S2_L": "内心频道雪花较多，常在「我是谁」里循环缓存",
    "S2_M": "平时还能认出自己，偶尔也会被情绪临时换号",
    "S2_H": "对自己的脾气、欲望和底线都算门儿清",
    "S3_L": "更在意舒服和安全，没必要天天给人生开冲刺模式",
    "S3_M": "想上进，也想躺会儿，价值排序经常内部开会",
    "S3_H": "很容易被目标、成长或某种重要信念推着往前",
    "E1_L": "感情里警报器灵敏，已读不回都能脑补到大结局",
    "E1_M": "一半信任，一半试探，感情里常在心里拉锯",
    "E1_H": "更愿意相信关系本身，不会被一点风吹草动吓散",
    "E2_L": "感情投入偏克制，心门不是没开，是门禁太严",
    "E2_M": "会投入，但会给自己留后手，不至于全盘梭哈",
    "E2_H": "一旦认定就容易认真，情绪和精力都给得很足",
    "E3_L": "容易黏人也容易被黏，关系里的温度感很重要",
    "E3_M": "亲密和独立都要一点，属于可调节型依赖",
    "E3_H": "空间感很重要，再爱也得留一块属于自己的地",
    "A1_L": "看世界自带防御滤镜，先怀疑，再靠近",
    "A1_M": "既不天真也不彻底阴谋论，观望是你的本能",
    "A1_H": "更愿意相信人性和善意，遇事不急着把世界判死刑",
    "A2_L": "规则能绕就绕，舒服和自由往往排在前面",
    "A2_M": "该守的时候守，该变通的时候也不死磕",
    "A2_H": "秩序感较强，能按流程来就不爱即兴炸场",
    "A3_L": "意义感偏低，容易觉得很多事都像在走过场",
    "A3_M": "偶尔有目标，偶尔也想摆烂，人生观处于半开机",
    "A3_H": "做事更有方向，知道自己大概要往哪边走",
    "Ac1_L": "做事先考虑别翻车，避险系统比野心更先启动",
    "Ac1_M": "有时想赢，有时只想别麻烦，动机比较混合",
    "Ac1_H": "更容易被成果、成长和推进感点燃",
    "Ac2_L": "做决定前容易多转几圈，脑内会议常常超时",
    "Ac2_M": "会想，但不至于想死机，属于正常犹豫",
    "Ac2_H": "拍板速度快，决定一下就不爱回头磨叽",
    "Ac3_L": "执行力和死线有深厚感情，越晚越像要觉醒",
    "Ac3_M": "能做，但状态看时机，偶尔稳偶尔摆",
    "Ac3_H": "推进欲比较强，事情不落地心里都像卡了根刺",
    "So1_L": "社交启动慢热，主动出击这事通常得攒半天气",
    "So1_M": "有人来就接，没人来也不硬凑，社交弹性一般",
    "So1_H": "更愿意主动打开场子，在人群里不太怕露头",
    "So2_L": "关系里更想亲近和融合，熟了就容易把人划进内圈",
    "So2_M": "既想亲近又想留缝，边界感看对象调节",
    "So2_H": "边界感偏强，靠太近会先本能性后退半步",
    "So3_L": "表达更直接，心里有啥基本不爱绕",
    "So3_M": "会看气氛说话，真实和体面通常各留一点",
    "So3_H": "对不同场景的自我切换更熟练，真实感会分层发放",
}

@dataclass
class SBType:
    """SBTI 人格类型"""
    code: str
    name: str
    emoji: str
    pattern: str          # 15维 pattern，如 "HHH-HMH-MHH-HHH-MHM"
    description: str      # 简介
    features: str         # 特征描述

    def _parse_pattern(self) -> list[str]:
        """解析 pattern 为维度等级列表"""
        s = self.pattern.replace("-", "")
        return list(s)

    def calc_distance(self, user_vector: list[int]) -> tuple:
        """计算曼哈顿距离 + exact匹配数 + similarity百分比"""
        p = self._parse_pattern()
        level_map = {"L": 1, "M": 2, "H": 3}
        distance = 0
        exact = 0
        for i, ch in enumerate(p):
            if i < len(user_vector):
                uv = user_vector[i]
                tv = level_map.get(ch, 2)
                diff = abs(uv - tv)
                distance += diff
                if diff == 0:
                    exact += 1
        similarity = max(0, round((1 - distance / 30) * 100))
        return distance, exact, similarity

    def get_dim_levels(self) -> dict:
        """获取每个维度的等级"""
        p = self._parse_pattern()
        return {dim: lv for dim, lv in zip(DIMENSIONS, p)}

    def describe_pattern(self) -> str:
        """把 pattern 码翻译成人话——每维一段描述"""
        levels = self.get_dim_levels()
        groups = {
            "自我模型": ["S1","S2","S3"],
            "情感模型": ["E1","E2","E3"],
            "态度模型": ["A1","A2","A3"],
            "行动驱力模型": ["Ac1","Ac2","Ac3"],
            "社交模型": ["So1","So2","So3"],
        }
        lines = []
        for group_name, dims in groups.items():
            parts = []
            for d in dims:
                lv = levels.get(d, "M")
                desc = DIM_DESC.get(f"{d}_{lv}", f"{d}{lv}")
                parts.append(f"· {DIM_NAMES.get(d,d)}: {desc}")
            lines.append(f"【{group_name}】\n" + "\n".join(parts))
        return "\n\n".join(lines)

    def describe_short(self) -> str:
        """简短版——一行概括"""
        levels = self.get_dim_levels()
        highlights = []
        for d in DIMENSIONS:
            lv = levels.get(d, "M")
            if lv == "H":
                highlights.append(f"{DIM_NAMES.get(d,d)}高")
            elif lv == "L":
                highlights.append(f"{DIM_NAMES.get(d,d)}低")
        if not highlights:
            return "各项维度居中，比较均衡"
        return "、".join(highlights[:6]) + ("…" if len(highlights) > 6 else "")

    def get_system_params(self) -> dict:
        """聚合所有维度的系统参数"""
        params = {
            "pad": [0.0, 0.0, 0.0],
            "confidence": 0.5, "certainty": 0.5, "goal_drive": 0.5,
            "warmth": 0.5, "trust": 0.5, "emotional_depth": 0.5,
            "formality": 0.5, "closeness": 0.5,
            "optimism": 0.5, "trust_assumption": 0.5,
            "structure": 0.5, "hebbian_lr_mult": 1.0,
            "reflection_depth": 0.5,
            "risk_taking": 0.5, "initiative": 0.5,
            "decisiveness": 0.5,
            "execution_drive": 0.5, "procrastination": 0.5,
            "verbosity": 0.5, "proactive_reply": 0.5,
            "formality_social": 0.5, "boundary": 0.5,
            "directness": 0.5, "diplomacy": 0.5,
        }
        levels = self.get_dim_levels()
        for dim, lv in levels.items():
            key = f"{dim}_{lv}"
            mapping = DIM_SYSTEM_MAP.get(key, {})
            pad = mapping.get("pad", (0, 0, 0))
            params["pad"][0] += pad[0] * 0.15
            params["pad"][1] += pad[1] * 0.15
            params["pad"][2] += pad[2] * 0.15
            for k, v in mapping.items():
                if k != "pad":
                    params[k] = params.get(k, 0.5) * 0.5 + v * 0.5  # blend
        return params

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "emoji": self.emoji,
            "pattern": self.pattern,
            "description": self.description,
            "features": self.features[:80] + "...",
            "dim_descriptions": self.describe_pattern(),
            "dim_short": self.describe_short(),
        }


# ── 全部 27 种人格 ──
TYPES: dict[str, SBType] = {}

def _reg(t: SBType):
    TYPES[t.code] = t

_reg(SBType("CTRL",   "拿捏者", "🎯", "HHH-HMH-MHH-HHH-MHM",
    "怎么样，被我拿捏了吧？",
    "全中国最为罕见的人格。宇宙熵增定律的天然反抗者。人形自走任务管理器——规则只是出厂参数，计划是心血来潮的随手涂鸦。在你人生列车脱轨前一秒用 Ctrl+S 强行存档，用无法拒绝的逻辑把你拽回正轨。"))
_reg(SBType("ATM-er", "送钱者", "💸", "HHH-HHM-HHH-HMH-MHL",
    "你以为我很有钱吗？",
    "不一定真送钱，但永远在'支付'——支付时间、精力、耐心。像老旧但坚固的 ATM 机，插进去的是别人的焦虑和麻烦，吐出来的是'没事，有我'。磐石般可靠，承受瀑布般的索取。"))
_reg(SBType("Dior-s", "屌丝", "🪑", "MHM-MMH-MHM-HMH-LHL",
    "等着我屌丝逆袭。",
    "犬儒主义先贤第欧根尼失散多年的精神传人。对当代消费主义陷阱和成功学 PUA 最彻底的蔑视。不是不求上进，是早已看穿所有'上进'尽头不过是更高级的牢房。"))
_reg(SBType("BOSS",   "领导者", "👑", "HHH-HMH-MMH-HHH-LHL",
    "方向盘给我，我来开。",
    "手里永远拿着方向盘。有独立的物理法则——永恒向上定律。看世界就像通关玩家看新手教程。效率是信仰，秩序是呼吸。人形的气场发生器，方圆五米内自动变得严肃高效。"))
_reg(SBType("THAN-K", "感恩者", "🙏", "MHM-HMM-HHM-MMH-MHL",
    "我感谢苍天！我感谢大地！",
    "温润如玉的性格和海纳百川的胸怀。摊上堵车？感谢让我听更多美妙的歌。世界没有完全的坏人，只有'尚未被感恩光芒照耀到的朋友'。永不枯竭的正能量发射塔。"))
_reg(SBType("OH-NO",  "哦不人", "😰", "HHL-LMH-LHH-HHM-LHL",
    "哦不！我怎么会是这个人格？！",
    "'哦不！'是顶级的智慧。看到杯子放桌沿→脑补水渍→短路→火灾→世界末日的灾难史诗。对'边界'有偏执般的尊重，所有意外和风险都被扼杀在萌芽状态。"))
_reg(SBType("GOGO",   "行者", "🏃", "HHM-HMH-MMH-HHH-MHM",
    "gogogo~出发咯",
    "活在一个极致的'所见即所得'世界。闭上眼睛天就是黑的，把钱花完就没钱了。世界上只有两种状态：已完成，和即将被我完成。"))
_reg(SBType("SEXY",   "尤物", "💃", "HMH-HHL-HMM-HMM-HLH",
    "您就是天生的尤物！",
    "走进一个房间，照明系统自动将你识别为尤物并调暗亮度。微笑时空气湿度下降，因为水蒸气都凝结成了人眼中的爱心。单是存在本身就已经像一篇华丽到过分的赋。"))
_reg(SBType("LOVE-R", "多情者", "💕", "MLH-LHL-HLH-MLM-MLH",
    "爱意太满，现实显得有点贫瘠。",
    "情感处理器不是二进制的，是彩虹制的。一片落叶在常人眼里是'秋天来了'，在 LOVE-R 眼中是一场关于轮回、牺牲与无言之爱的十三幕悲喜剧。"))
_reg(SBType("MUM",    "妈妈", "🤱", "MMH-MHL-HMM-LMM-HLL",
    "或许...我可以叫你妈妈吗....?",
    "温柔的底色，擅长感知情绪，超强共情力。像一个医生，治愈了别人的不开心。只可惜当妈妈落泪时，TA 给自己的药剂量总是比给别人小一号——对自己的温柔常常打了折。"))
_reg(SBType("FAKE",   "伪人", "🎭", "HLM-MML-MLM-MLM-HLH",
    "已经，没有人类了。",
    "社交场合的八面玲珑，切换人格面具比切换输入法还快。你以为交到真心朋友？醒醒，你只是遇到了善于伪装的高性能仿生人。面具下空得很——正是这些面具构成了自己。"))
_reg(SBType("OJBK",   "无所谓人", "🍵", "MMH-MMM-HML-LMM-MML",
    "我说随便，是真的随便。",
    "已经不是人格，是统治哲学。'中午吃米饭还是面条'的世纪抉择，用批阅奏章般的淡然轻飘飘吐出'都行'。这不是没主见，这是在告诉你：尔等凡俗的选择，于朕而言皆为蝼蚁。"))
_reg(SBType("MALO",   "吗喽", "🐵", "MLH-MHM-MLH-MLH-LMH",
    "人生是个副本，而我只是一只吗喽。",
    "灵魂还停留在树上荡秋千、看见香蕉就两眼放光的快乐时代。所谓文明不过是一场最无聊的付费游戏。规则偶尔可以打破，天花板用来倒挂，会议室用来后空翻。"))
_reg(SBType("JOKE-R", "小丑", "🤡", "LLH-LHL-LML-LLL-MLM",
    "原来我们都是小丑。",
    "不是'人'，更像把笑话穿在身上的小丑。打开一层是个笑话，再打开一层是个段子，一层层打开到最里面……是空的，只有微弱的回声说'哈，没想到吧'。"))
_reg(SBType("WOC!",   "握草人", "🌿", "HHL-HMH-MMH-HHM-LHH",
    "卧槽，我怎么是这个人格？",
    "拥有两套独立操作系统：表面系统负责发出'我操''牛逼''啊？'等拟声词；后台系统冷静分析'嗯，果然不出我所料'。只会卧槽，不会多管闲事。"))
_reg(SBType("THIN-K", "思考者", "🤔", "HHL-HMH-MLH-MHM-LHH",
    "已深度思考 100s。",
    "大脑长时间处于思考状态。十分会审判信息，注重论点、论据、逻辑推理。别人看到你独处时在发呆——那不是发呆，是大脑在对今天接收到的信息分类、归档和销毁。"))
_reg(SBType("SHIT",   "愤世者", "💩", "HHL-HLH-LMM-HHM-LHH",
    "这个世界，构石一坨。",
    "一场惊天动地的悖论戏剧。嘴上说'这项目简直是屎'→手上打开 Excel 建函数模型和甘特图。嘴上说'世界赶紧毁灭'→明早七点准时起床去干那份屎一样的工作。"))
_reg(SBType("ZZZZ",   "装死者", "💤", "MHL-MLH-LML-MML-LHM",
    "我没死，我只是在睡觉。",
    "群里 99+ 条消息视而不见，但'@全体成员 还有半小时截止'发出时，像从千年古墓苏醒般缓缓敲出'收到'。直到'死线'这个最高权限指令出现，才会真正爆发。"))
_reg(SBType("POOR",   "贫困者", "🥷", "HHL-MLH-LMH-HHH-LHL",
    "我穷，但我很专。",
    "'贫困'不是钱包余额的判决书，是欲望断舍离后的资源再分配。别人把精力撒成漫天二维码，你把精力压成一束激光——照哪儿哪儿冒烟。一旦某件事被认定值得钻，外界再吵也只是背景杂音。"))
_reg(SBType("MONK",   "僧人", "🧘", "HHL-LLH-LLM-MML-LHM",
    "没有那种世俗的欲望。",
    "当别人在 KTV 参悟爱与恨的纠缠，MONK 在家中参悟大道。个人空间是结界、须弥山、绝对领域。不黏不缠，万物皆有其独立轨道。"))
_reg(SBType("IMSB",   "傻者", "😵", "LLM-LMM-LLL-LLL-MLM",
    "认真的么？我真的是傻逼么？",
    "大脑里住着两个不死不休的究极战士：'我他妈冲了！' vs '我是个傻逼！'。最终结果：盯着对方背影消失。不是真的傻，只是内心戏比漫威宇宙所有电影加起来都长。"))
_reg(SBType("SOLO",   "孤儿", "🌙", "LML-LLH-LHL-LML-LHM",
    "我哭了，我怎么会是孤儿？",
    "自我价值感偏低，主动疏远他人。灵魂外围筑起'莫挨老子'的万里长城——每一块砖都是过去的一道伤口。满身尖刺不是攻击，是一句句说不出口的'别过来，我怕你也受伤'。"))
_reg(SBType("FUCK",   "草者", "🌱", "MLL-LHL-LLM-MLL-HLH",
    "操！这是什么人格？",
    "无法被任何除草剂杀死的人形野草。情绪开关是物理拨片式：FUCK YEAH 或 FUCK OFF。当所有人都被驯化成温顺家禽，FUCK 是荒野上最后那声狼嚎。"))
_reg(SBType("DEAD",   "死者", "💀", "LLL-LLM-LML-LLL-LHM",
    "我，还活着吗？",
    "看透无意义的哲学思考，对一切'失去'兴趣。看世界像顶级玩家通关了全部主线支线隐藏任务，删档重开 999 次后终于发现——这游戏压根没意思。超越欲望和目标的终极贤者。"))
_reg(SBType("IMFW",   "废物", "🍂", "LLH-LHL-LML-LLL-MLL",
    "我真的...是废物吗？",
    "仅占世界人口 0.0001% 的珍稀人格。自尊脆弱，缺乏安全感，偶尔缺乏主见。走进废物的生活像走进顶级兰花温室——需要精确控制温度湿度，每天定时'我爱你'言语光合作用。"))
_reg(SBType("DRUNK",  "酒鬼", "🍺", "DRUNK",
    "烈酒烧喉，不得不醉。",
    "体内流淌的不是血液，是五粮液、国窖 1573、江小白。习惯于将白酒灌入保温杯当白开水一饮而下。饭桌上谈笑风生，厕所里抱着马桶忏悔人生。"))
_reg(SBType("HHHH",   "傻乐者", "😄", "HHHH",
    "哈哈哈哈哈哈。",
    "哈哈哈哈哈哈哈哈哈哈！对不起，这就是全部特质了。怎么会有人的脑回路这么新奇。系统兜底人格——当所有标准人格匹配度均低于 60% 时触发。"))


# ── 人格引擎 ──

class SBTIEngine:
    """SBTI 人格引擎 — 基于 15 维 pattern 匹配"""

    def __init__(self, code: str = "OJBK", evolution_enabled: bool = False,
                 impacts: Optional[dict] = None):
        self.current_code = code
        self.evolution_enabled = evolution_enabled
        self._history: list[dict] = []
        # 每个影响点的开关，默认全开
        self.impacts = {
            "llm_prompt": True,
            "pad_baseline": True,
            "hebbian_lr": True,
            "importance_bias": True,
            "reply_length": True,
            "memory_decay": True,
            "warmth_tone": True,
            "tts_speed": True,
        }
        if impacts:
            self.impacts.update(impacts)

    @property
    def type(self) -> SBType:
        return TYPES.get(self.current_code, TYPES["OJBK"])

    def set_type(self, code: str):
        if code in TYPES and code != self.current_code:
            old = self.current_code
            self.current_code = code
            self._record_switch(code, f"manual")
            logger.info(f"[SBTI] Switched: {old} → {code}")

    def set_impacts(self, impacts: dict):
        """批量设置 impact 开关"""
        self.impacts.update(impacts)
        logger.info(f"[SBTI] Impacts updated: {impacts}")

    def is_impact_enabled(self, name: str) -> bool:
        return self.impacts.get(name, True)

    def get_impact(self, pad_state=None) -> dict:
        """获取当前人格对系统的影响参数"""
        params = self.type.get_system_params()
        return params

    def _record_switch(self, code: str, reason: str):
        self._history.append({
            "timestamp": __import__("time").time(),
            "code": code,
            "reason": reason,
        })
        if len(self._history) > 100:
            self._history = self._history[-100:]

    def get_history(self, n: int = 10) -> list:
        return self._history[-n:]

    def to_dict(self) -> dict:
        t = self.type
        return {
            "current": self.current_code,
            "emoji": t.emoji,
            "name": t.name,
            "pattern": t.pattern,
            "description": t.description,
            "dim_short": t.describe_short(),
            "evolution_enabled": self.evolution_enabled,
            "impacts": dict(self.impacts),
            "history": self.get_history(5),
        }
