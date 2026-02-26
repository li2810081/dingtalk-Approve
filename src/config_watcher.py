"""配置文件热重载模块"""
import asyncio
from pathlib import Path
from typing import Callable, Optional
from loguru import logger
from watchfiles import awatch


class ConfigWatcher:
    """配置文件监听器，支持热重载"""

    def __init__(self, config_path: str, reload_callback: Callable):
        """初始化配置监听器

        Args:
            config_path: 配置文件路径
            reload_callback: 配置变更时的回调函数
        """
        self.config_path = Path(config_path)
        self.reload_callback = reload_callback
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def _watch_loop(self):
        """监听文件变化的循环"""
        logger.info(f"开始监听配置文件: {self.config_path}")

        try:
            async for changes in awatch(self.config_path):
                for change_type, changed_path in changes:
                    changed_path = Path(changed_path)

                    # 只处理配置文件的修改
                    if changed_path == self.config_path and change_type.value == "modified":
                        logger.info(f"检测到配置文件变更: {self.config_path}")
                        try:
                            await self.reload_callback()
                            logger.info("配置重载成功")
                        except Exception as e:
                            logger.error(f"配置重载失败: {e}")

        except Exception as e:
            logger.error(f"配置监听异常: {e}")

    async def start(self):
        """启动配置监听"""
        if self._running:
            logger.warning("配置监听器已在运行")
            return

        if not self.config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_path}")
            return

        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("配置监听器已启动")

    async def stop(self):
        """停止配置监听"""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("配置监听器已停止")
