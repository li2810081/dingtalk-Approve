"""列出AI表格中的所有数据表，帮助确认正确的sheet_id"""
import asyncio
import os
import sys
import logging

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.config import load_config
from src.spreadsheet_client import SpreadsheetClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def list_all_sheets(client: SpreadsheetClient, base_id: str):
    """列出指定base中的所有数据表

    注意：钉钉API没有直接列出sheets的接口，这里通过尝试列出记录来判断sheet是否存在
    """
    logger.info(f"--- 测试 Base ID: {base_id} ---")

    # 常见的 sheet_id 可能的值
    # 用户可以尝试不同的值来找到正确的sheet_id
    possible_sheet_ids = [
        "R5i0kXZ",      # 用户配置中的值
        "sheet1",       # 常见默认值
        "Sheet1",
        " Sheet",
        "tblxxxxxxx",   # 钉钉通常使用的格式
    ]

    logger.info("提示：请从你的钉钉多维表格中获取正确的 Sheet ID")
    logger.info("获取方法：")
    logger.info("1. 打开多维表格")
    logger.info("2. 点击数据表名称")
    logger.info("3. 从浏览器URL中获取，格式类似: /sheets/SHEET_ID/records")
    logger.info("")

    # 尝试列出记录来验证 sheet_id
    for sheet_id in possible_sheet_ids:
        logger.info(f"尝试访问 Sheet: {sheet_id}")
        try:
            records = await client.list_records(
                sheet_id=sheet_id,
                base_id=base_id,
                max_results=1
            )
            logger.info(f"✓ Sheet ID 有效: {sheet_id} (包含 {len(records)} 条记录)")
        except Exception as e:
            logger.warning(f"✗ Sheet ID 无效: {sheet_id} - {str(e)[:100]}")


async def main():
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

    # 获取测试用的 base_id
    test_base_id = None

    if config.approvals:
        for approval in config.approvals:
            if approval.actions:
                for action in approval.actions:
                    if action.type == "update_spreadsheet" and action.base_id:
                        test_base_id = action.base_id
                        logger.info(f"从配置中找到 base_id: {test_base_id}")
                        break
            if test_base_id:
                break

    if not test_base_id:
        test_base_id = config.spreadsheet.base_id
        if test_base_id:
            logger.warning(f"使用默认配置 base_id: {test_base_id}")
        else:
            logger.error("未在配置中找到有效的 base_id")
            return

    await list_all_sheets(client, test_base_id)


if __name__ == "__main__":
    asyncio.run(main())
