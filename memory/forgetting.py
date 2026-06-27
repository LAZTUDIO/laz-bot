"""Ebbinghaus 遗忘调度器"""
import asyncio
import time
import math
import logging

logger = logging.getLogger("laz-bot.forgetting")


class ForgettingScheduler:
    """基于 Ebbinghaus 遗忘曲线的定时归档调度器"""

    def __init__(self, long_term_memory, episodic_graph,
                 halflife_base: float = 7.0,
                 archive_threshold: float = 0.05,
                 cleanup_after_days: int = 90,
                 check_interval: int = 86400):
        self.ltm = long_term_memory
        self.graph = episodic_graph
        self.halflife_base = halflife_base
        self.archive_threshold = archive_threshold
        self.cleanup_after_days = cleanup_after_days
        self.check_interval = check_interval
        self._task: asyncio.Task = None
        self.running = False

    def _forget_weight(self, days_since: float, importance: float) -> float:
        halflife = self.halflife_base * (1 + importance * 3)
        return math.exp(-days_since / halflife)

    def start(self):
        if self.running: return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("[Forgetting] Scheduler started")

    async def _run_loop(self):
        while self.running:
            try:
                await self._check_and_forget()
            except Exception as e:
                logger.error(f"[Forgetting] Check failed: {e}")
            await asyncio.sleep(self.check_interval)

    async def _check_and_forget(self):
        now = time.time()
        memories = self.ltm.get_all_active()
        archived = 0
        for mem in memories:
            days = (now - mem.last_accessed) / 86400
            w = self._forget_weight(days, mem.importance)
            if w < self.archive_threshold:
                self.ltm.archive(mem.id)
                archived += 1
                logger.debug(f"Archived mem #{mem.id}: '{mem.content[:30]}...' weight={w:.4f}")
        self.ltm.archive_old(self.cleanup_after_days)
        self.graph.decay_edges(0.1)
        if archived:
            logger.info(f"[Forgetting] Archived {archived} memories")

    async def forget_now(self):
        await self._check_and_forget()

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("[Forgetting] Scheduler stopped")

    def get_memory_health(self, mem) -> dict:
        now = time.time()
        days = (now - mem.last_accessed) / 86400
        w = self._forget_weight(days, mem.importance)
        hl = self.halflife_base * (1 + mem.importance * 3)
        return {"id": mem.id, "forget_weight": round(w, 4),
                "halflife_days": round(hl, 1),
                "days_since_access": round(days, 1),
                "importance": mem.importance,
                "will_archive": w < self.archive_threshold}