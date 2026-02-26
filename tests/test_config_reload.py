"""测试配置文件热重载功能"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config_watcher import ConfigWatcher
from loguru import logger


async def test_config_watcher():
    """测试配置文件监听器"""
    config_path = "config/config.yaml"

    logger.info("=" * 50)
    logger.info("配置文件热重载测试")
    logger.info(f"监听文件: {config_path}")
    logger.info("=" * 50)

    reload_count = 0

    async def reload_callback():
        nonlocal reload_count
        reload_count += 1
        logger.info(f"🔄 配置重载触发 (第 {reload_count} 次)")

    # 创建监听器
    watcher = ConfigWatcher(config_path, reload_callback)

    # 检查文件是否存在
    if not Path(config_path).exists():
        logger.error(f"❌ 配置文件不存在: {config_path}")
        return

    logger.info("✓ 配置文件存在")

    # 启动监听
    logger.info("启动配置监听器...")
    await watcher.start()
    logger.info("✓ 配置监听器已启动")

    logger.info("")
    logger.info("=" * 50)
    logger.info("监听器正在运行...")
    logger.info("请修改 config/config.yaml 文件来测试热重载")
    logger.info("测试将持续 60 秒，或按 Ctrl+C 提前结束")
    logger.info("=" * 50)
    logger.info("")

    try:
        # 运行 60 秒
        for i in range(60):
            await asyncio.sleep(1)
            # 每 10 秒显示一次状态
            if (i + 1) % 10 == 0:
                logger.info(f"⏱ 运行中... ({i + 1}/60秒), 已检测到 {reload_count} 次配置变更")

    except KeyboardInterrupt:
        logger.info("接收到中断信号")
    finally:
        logger.info("")
        logger.info("=" * 50)
        logger.info("停止配置监听器...")
        await watcher.stop()
        logger.info(f"✓ 总共检测到 {reload_count} 次配置变更")
        logger.info("=" * 50)


if __name__ == "__main__":
    try:
        asyncio.run(test_config_watcher())
    except KeyboardInterrupt:
        logger.info("测试结束")
