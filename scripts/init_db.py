#!/usr/bin/env python3
"""数据库初始化脚本 — 创建并初始化 LAZ-Bot 记忆数据库"""
import os
import sys
import yaml

# 确保在项目根目录
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from memory.long_term import LongTermMemory
from memory.episodic_graph import EpisodicGraph


def main():
    # 加载配置
    with open(os.path.join(project_root, "config.yaml")) as f:
        config = yaml.safe_load(f)

    db_path = config.get("memory", {}).get("db_path", "data/fusion_memory.db")
    embedding_dim = config.get("memory", {}).get("embedding_dim", 384)

    print(f"[InitDB] Initializing database at: {db_path}")
    print(f"[InitDB] Embedding dimension: {embedding_dim}")

    # 初始化长期记忆表
    ltm = LongTermMemory(db_path=db_path, embedding_dim=embedding_dim)
    ltm.initialize()
    print(f"[InitDB] Long-term memory table created")

    # 初始化脑图表
    graph = EpisodicGraph(db_path=db_path)
    graph.initialize()
    print(f"[InitDB] Episodic graph tables created")

    # 验证
    print(f"\n=== Database initialized successfully ===")
    print(f"  Path: {os.path.abspath(db_path)}")
    print(f"  Size: {os.path.getsize(db_path) if os.path.exists(db_path) else 0} bytes")

    ltm.close()
    graph.close()


if __name__ == "__main__":
    main()