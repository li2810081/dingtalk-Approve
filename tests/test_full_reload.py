"""验证配置文件热重载功能"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from loguru import logger


async def test_full_reload():
    """完整测试配置热重载"""
    from src.config_watcher import ConfigWatcher
    from src.config import load_config

    config_path = 'config/config.yaml'

    logger.info("=" * 60)
    logger.info("配置文件热重载完整测试")
    logger.info("=" * 60)
    logger.info(f"配置文件: {config_path}")
    logger.info("")

    reload_count = 0
    original_approvals_count = 0

    async def reload_callback():
        nonlocal reload_count
        reload_count += 1
        logger.info("")
        logger.info("=" * 40)
        logger.info(f"🔄 第 {reload_count} 次配置重载")
        logger.info("=" * 40)

        try:
            # 重新加载配置
            new_config = load_config(config_path)
            logger.info(f"审批流程数量: {len(new_config.approvals)}")
            logger.info(f"人事事件数量: {len(new_config.hrm_events)}")
            logger.info("✓ 配置重载成功")
        except Exception as e:
            logger.error(f"✗ 配置重载失败: {e}")

        logger.info("")

    # 创建监听器
    watcher = ConfigWatcher(config_path, reload_callback, poll_interval=1.0)

    if not Path(config_path).exists():
        logger.error(f"配置文件不存在: {config_path}")
        return

    # 获取原始配置
    try:
        original_config = load_config(config_path)
        original_approvals_count = len(original_config.approvals)
        logger.info(f"原始配置:")
        logger.info(f"  审批流程数量: {original_approvals_count}")
        logger.info(f"  人事事件数量: {len(original_config.hrm_events)}")
    except Exception as e:
        logger.error(f"加载原始配置失败: {e}")
        return

    # 启动监听
    logger.info("")
    logger.info("启动配置监听器...")
    await watcher.start()
    logger.info("")

    logger.info("=" * 60)
    logger.info("监听器运行中...")
    logger.info("测试将在 20 秒后自动结束")
    logger.info("")
    logger.info("💡 提示: 现在可以修改 config/config.yaml 文件")
    logger.info("=" * 60)
    logger.info("")

    try:
        # 运行 20 秒，每 5 秒显示一次状态
        for i in range(20):
            await asyncio.sleep(1)
            if (i + 1) % 5 == 0:
                logger.info(f"⏱ 运行中... ({i + 1}/20秒), 已检测到 {reload_count} 次配置变更")

    except KeyboardInterrupt:
        logger.info("\n接收到中断信号")
    finally:
        logger.info("")
        logger.info("=" * 60)
        logger.info("停止配置监听器...")
        await watcher.stop()
        logger.info(f"测试结束: 总共检测到 {reload_count} 次配置变更")
        logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(test_full_reload())
    except KeyboardInterrupt:
        logger.info("\n测试已取消")
