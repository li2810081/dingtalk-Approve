"""简单的添加记录测试 - 使用英文字段名验证功能"""
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


async def test_add_simple():
    """测试添加记录 - 使用实际存在的字段"""
    load_dotenv()
    config = load_config()
    client = SpreadsheetClient(
        config.spreadsheet,
        os.getenv("DINGTALK_APP_KEY"),
        os.getenv("DINGTALK_APP_SECRET")
    )

    # 先获取现有记录查看字段名
    logger.info("步骤1: 获取现有记录查看字段...")
    records = await client.list_records(
        sheet_id="R5i0kXZ",
        base_id="o14dA3GK8gxNA0Gdf5rkjEx5W9ekBD76",
        max_results=1
    )

    if not records:
        logger.error("表格为空，无法获取字段信息")
        return

    # 获取字段名
    field_name = list(records[0]["fields"].keys())[0]
    logger.info(f"表格中的字段名: {field_name}")

    # 使用相同的字段名添加新记录
    logger.info(f"步骤2: 使用字段 '{field_name}' 添加新记录...")

    # 直接构建字段字典，避免编码问题
    test_fields = {field_name: "新测试记录"}

    logger.info(f"添加数据: {test_fields}")

    try:
        result = await client.add_records(
            sheet_id="R5i0kXZ",
            base_id="o14dA3GK8gxNA0Gdf5rkjEx5W9ekBD76",
            records=[{"fields": test_fields}],
            operator_id=None
        )

        if result:
            logger.info(f"✓ 添加成功! 记录ID: {result}")
        else:
            logger.error("✗ 添加失败 - 返回空列表")

    except Exception as e:
        logger.error(f"✗ 添加失败: {e}")


async def main():
    await test_add_simple()


if __name__ == "__main__":
    asyncio.run(main())
