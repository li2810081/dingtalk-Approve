"""配置文件热重载模块"""
import asyncio
import os
import sys
from pathlib import Path
from typing import Callable, Optional
from loguru import logger

# 检测是否在 Windows 平台
IS_WINDOWS = sys.platform == 'win32'

# Windows 上默认使用轮询模式，因为 watchfiles 在 Windows 上可能不稳定
USE_WATCHFILES = not IS_WINDOWS

if USE_WATCHFILES:
    try:
        from watchfiles import awatch
        WATCHFILES_AVAILABLE = True
    except ImportError:
        WATCHFILES_AVAILABLE = False
        logger.info("watchfiles 库未安装，将使用轮询方式进行配置监听")
else:
    WATCHFILES_AVAILABLE = False
    if IS_WINDOWS:
        logger.info("Windows 平台：使用轮询模式进行配置监听（更稳定）")


class ConfigWatcher:
    """配置文件监听器，支持热重载"""

    def __init__(self, config_path: str, reload_callback: Callable, poll_interval: float = 2.0):
        """初始化配置监听器

        Args:
            config_path: 配置文件路径
            reload_callback: 配置变更时的回调函数
            poll_interval: 轮询间隔（秒），仅在使用轮询模式时有效
        """
        self.config_path = Path(config_path)
        self.reload_callback = reload_callback
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_mtime = 0
        self._reload_task: Optional[asyncio.Task] = None  # 当前正在执行的重载任务
        self._reload_pending = False  # 是否有等待执行的重载

    async def _watch_loop(self):
        """监听文件变化的循环"""
        logger.info(f"开始监听配置文件: {self.config_path}")

        if WATCHFILES_AVAILABLE:
            await self._watch_with_watchfiles()
        else:
            await self._watch_with_polling()

    async def _watch_with_watchfiles(self):
        """使用 watchfiles 库监听文件变化"""
        logger.debug("使用 watchfiles 模式监听配置文件")

        try:
            async for changes in awatch(self.config_path):
                for change_type, changed_path in changes:
                    changed_path = Path(changed_path)

                    # 只处理配置文件的修改
                    if changed_path == self.config_path and change_type.value == "modified":
                        logger.info(f"检测到配置文件变更: {self.config_path}")
                        # 触发后台重载任务，不阻塞监听
                        self._trigger_reload()

        except Exception as e:
            logger.error(f"配置监听异常: {e}")

    async def _watch_with_polling(self):
        """使用轮询方式监听文件变化"""
        logger.debug(f"使用轮询模式监听配置文件 (间隔: {self.poll_interval}秒)")

        # 初始化文件修改时间
        self._last_mtime = self._get_file_mtime()

        try:
            while self._running:
                await asyncio.sleep(self.poll_interval)

                current_mtime = self._get_file_mtime()
                if current_mtime > self._last_mtime:
                    logger.info(f"检测到配置文件变更: {self.config_path}")
                    self._last_mtime = current_mtime
                    # 触发后台重载任务，不阻塞监听
                    self._trigger_reload()

        except Exception as e:
            logger.error(f"配置监听异常: {e}")

    def _get_file_mtime(self) -> float:
        """获取文件修改时间"""
        try:
            return self.config_path.stat().st_mtime
        except FileNotFoundError:
            logger.warning(f"配置文件不存在: {self.config_path}")
            return 0
        except Exception as e:
            logger.error(f"获取文件修改时间失败: {e}")
            return 0

    def _trigger_reload(self):
        """触发后台重载任务"""
        # 如果已有重载任务在运行，标记为待处理
        if self._reload_task is not None and not self._reload_task.done():
            logger.debug("配置重载任务正在执行，标记为待处理")
            self._reload_pending = True
            return

        # 创建新的后台重载任务
        logger.debug("创建后台配置重载任务")
        self._reload_pending = False
        self._reload_task = asyncio.create_task(self._execute_reload())

    async def _execute_reload(self):
        """执行配置重载（在后台任务中运行）"""
        try:
            logger.info("开始执行配置重载...")
            await self.reload_callback()
            logger.info("配置重载成功")
        except Exception as e:
            logger.error(f"配置重载失败: {e}")
        finally:
            # 检查是否有待处理的重载（防抖）
            if self._reload_pending:
                logger.info("检测到新的配置变更，继续重载...")
                self._reload_pending = False
                # 递归调用以处理待处理的重载
                await self._execute_reload()
            else:
                self._reload_task = None

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

        mode = "watchfiles" if WATCHFILES_AVAILABLE else "轮询"
        logger.info(f"配置监听器已启动 ({mode}模式)")

    async def stop(self):
        """停止配置监听"""
        if not self._running:
            return

        self._running = False

        # 取消监听任务
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # 取消正在执行的重载任务
        if self._reload_task and not self._reload_task.done():
            logger.debug("取消正在执行的配置重载任务")
            self._reload_task.cancel()
            try:
                await self._reload_task
            except asyncio.CancelledError:
                pass

        logger.info("配置监听器已停止")
