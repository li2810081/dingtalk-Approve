"""测试获取推送失败的事件列表"""
import asyncio
import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.config import load_config
from src.spreadsheet_client import SpreadsheetClient
from loguru import logger


async def test_get_failed_events():
    """测试获取推送失败的事件列表"""
    logger.info("=" * 60)
    logger.info("测试获取推送失败的事件列表")
    logger.info("=" * 60)
    logger.info("")

    # 加载环境变量
    load_dotenv()

    # 加载配置
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        return

    # 初始化客户端
    app_key = os.getenv("DINGTALK_APP_KEY")
    app_secret = os.getenv("DINGTALK_APP_SECRET")

    if not app_key or not app_secret:
        logger.error("错误: 未在 .env 文件中找到 DINGTALK_APP_KEY 或 DINGTALK_APP_SECRET")
        return

    client = SpreadsheetClient(
        config=config.spreadsheet,
        app_key=app_key,
        app_secret=app_secret
    )

    logger.info("开始获取推送失败的事件列表...")
    logger.info("")

    try:
        result = await client.get_failed_events()

        logger.info("=" * 60)
        logger.info("获取结果:")
        logger.info(f"  企业ID: {result.get('corpid', 'N/A')}")
        logger.info(f"  失败事件数量: {len(result.get('failed_list', []))}")
        logger.info(f"  是否还有更多: {result.get('has_more', False)}")

        if "error" in result:
            logger.error(f"  错误: {result['error']}")
            return

        failed_list = result.get("failed_list", [])

        if not failed_list:
            logger.info("")
            logger.info("✓ 没有推送失败的事件")
            logger.info("")
            logger.info("说明:")
            logger.info("  - 可能所有事件都成功推送了")
            logger.info("  - 或者钉钉尚未重试推送失败的事件")
            logger.info("  - 钉钉会在推送失败后的 10秒、30秒 进行重试")
            logger.info("  - 重试失败后的 3-5 分钟内可通过此接口获取")
        else:
            logger.info("")
            logger.info("失败事件详情:")
            for i, failed_event in enumerate(failed_list, 1):
                event_type = list(failed_event.keys())[0] if failed_event else "unknown"
                event_data = list(failed_event.values())[0] if failed_event else {}

                logger.info(f"")
                logger.info(f"  [{i}] 事件类型: {event_type}")
                logger.info(f"      数据: {json.dumps(event_data, ensure_ascii=False)[:200]}")

        logger.info("")
        logger.info("=" * 60)

        # 如果有失败事件，询问是否需要处理
        if failed_list:
            logger.info("")
            logger.info("💡 提示: 可以手动处理这些失败的事件")
            logger.info("   例如: 将事件数据重新提交给事件处理器处理")

    except Exception as e:
        logger.exception(f"获取失败事件列表时发生错误: {e}")


async def main():
    try:
        await test_get_failed_events()
    except KeyboardInterrupt:
        logger.info("\n测试已取消")


if __name__ == "__main__":
    asyncio.run(main())
