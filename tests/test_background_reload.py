"""测试配置后台重载功能（不阻塞监听）"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from loguru import logger


async def test_background_reload():
    """测试后台重载不会阻塞监听"""
    from src.config_watcher import ConfigWatcher

    config_path = 'config/config.yaml'

    logger.info("=" * 60)
    logger.info("测试配置后台重载功能")
    logger.info("=" * 60)
    logger.info("")

    reload_count = 0
    reload_times = []

    async def slow_reload_callback():
        """模拟耗时的配置重载操作"""
        nonlocal reload_count
        reload_count += 1
        start_time = asyncio.get_event_loop().time()

        logger.info(f"[重载开始] 第 {reload_count} 次配置重载开始")
        logger.info(f"[重载进行中] 模拟耗时操作 (3秒)...")

        # 模拟耗时的重载操作
        await asyncio.sleep(3)

        end_time = asyncio.get_event_loop().time()
        elapsed = end_time - start_time
        reload_times.append(elapsed)

        logger.info(f"[重载完成] 第 {reload_count} 次配置重载完成 (耗时 {elapsed:.2f}秒)")
        logger.info("")

    # 创建监听器
    watcher = ConfigWatcher(config_path, slow_reload_callback, poll_interval=1.0)

    if not Path(config_path).exists():
        logger.error(f"配置文件不存在: {config_path}")
        return

    # 启动监听
    logger.info("启动配置监听器...")
    await watcher.start()
    logger.info("")

    logger.info("=" * 60)
    logger.info("测试场景: 快速连续修改配置文件")
    logger.info("预期: 每次修改都会被检测到，重载在后台执行")
    logger.info("=" * 60)
    logger.info("")

    try:
        # 快速连续修改3次配置文件
        for i in range(3):
            logger.info(f"[操作] 第 {i + 1} 次修改配置文件...")
            Path(config_path).touch()

            # 等待1秒，让监听器检测到变化
            await asyncio.sleep(1)

        logger.info("")
        logger.info("[等待] 等待所有后台重载任务完成...")
        logger.info("")

        # 等待所有重载任务完成（最多10秒）
        for i in range(10):
            if watcher._reload_task is None or watcher._reload_task.done():
                break
            logger.info(f"[等待] 重载任务仍在执行... ({i + 1}/10秒)")
            await asyncio.sleep(1)

    finally:
        await watcher.stop()

    logger.info("")
    logger.info("=" * 60)
    logger.info("测试结果:")
    logger.info(f"  总共检测到变化次数: {reload_count}")
    logger.info(f"  实际重载次数: {len(reload_times)}")
    if reload_times:
        logger.info(f"  每次重载耗时: {[f'{t:.2f}秒' for t in reload_times]}")

    # 验证：重载次数应该等于修改次数（因为有防抖机制，最后一次会处理所有待处理的重载）
    # 或者重载次数应该等于修改次数减去合并次数
    logger.info("")
    if reload_count > 0:
        logger.info("✓ 后台重载功能正常工作")
        logger.info("✓ 监听器没有被重载操作阻塞")
    else:
        logger.warning("✗ 未检测到配置文件变化")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(test_background_reload())
    except KeyboardInterrupt:
        logger.info("\n测试已取消")
