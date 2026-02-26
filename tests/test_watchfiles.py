"""测试 watchfiles 在 Windows 上的文件监听功能"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from watchfiles import awatch
from pathlib import Path
from loguru import logger


async def test_watchfiles():
    """测试 watchfiles 是否能检测到文件变化"""
    config_path = Path('config/config.yaml').resolve()

    logger.info("=" * 50)
    logger.info("测试 watchfiles 文件监听")
    logger.info(f"监听文件: {config_path}")
    logger.info("=" * 50)
    logger.info("")
    logger.info("监听中... (15秒后自动结束)")
    logger.info("请现在修改 config.yaml 文件...")
    logger.info("")

    detected = False

    try:
        async for changes in awatch(config_path):
            logger.info(f"✓ 检测到文件变化!")
            for change_type, path in changes:
                logger.info(f"  类型: {change_type.value}")
                logger.info(f"  路径: {path}")
            detected = True
            break

    except Exception as e:
        logger.error(f"监听异常: {e}")
    finally:
        logger.info("")
        logger.info("=" * 50)
        if detected:
            logger.info("✓ watchfiles 工作正常")
        else:
            logger.warning("✗ watchfiles 未检测到文件变化")
            logger.info("建议: 将强制使用轮询模式")
        logger.info("=" * 50)


async def main():
    try:
        await asyncio.wait_for(test_watchfiles(), timeout=15.0)
    except asyncio.TimeoutError:
        logger.warning("")
        logger.warning("15秒内未检测到文件变化")
        logger.info("这可能是正常的，如果文件编辑器使用了特殊方式保存文件")


if __name__ == "__main__":
    asyncio.run(main())
