"""测试操作并行执行功能"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from loguru import logger


async def test_parallel_actions():
    """测试多个操作并行执行"""
    from src.stream_client import UnifiedEventHandler
    from src.config import Config, Action, UpdateField, Approval
    from src.spreadsheet_client import SpreadsheetClient

    logger.info("=" * 60)
    logger.info("测试操作并行执行功能")
    logger.info("=" * 60)
    logger.info("")

    # 创建模拟的 handler
    class MockSpreadsheetClient:
        """模拟的 AI 表格客户端"""
        async def _update_spreadsheet(self, action, form_data, operator_id):
            logger.info(f"[表格操作 {action.sheet_id}] 开始更新 ({len(action.updates)} 个字段)")
            await asyncio.sleep(2)  # 模拟耗时操作
            logger.info(f"[表格操作 {action.sheet_id}] 更新完成")

        async def get_user_info(self, userid):
            return {}

        async def get_process_instance(self, process_instance_id):
            return {}

        async def process_add_actions(self, sheet_id, base_id, updates, form_data, operator_id=None):
            """模拟新增操作"""
            logger.info(f"[表格操作 {sheet_id}] 新增 {len(updates)} 条记录")
            await asyncio.sleep(2)  # 模拟耗时操作
            logger.info(f"[表格操作 {sheet_id}] 新增完成")

        async def process_update_actions(self, sheet_id, base_id, find_by, updates, form_data, operator_id=None):
            """模拟更新操作"""
            logger.info(f"[表格操作 {sheet_id}] 更新 {len(updates)} 个字段")
            await asyncio.sleep(2)  # 模拟耗时操作
            logger.info(f"[表格操作 {sheet_id}] 更新完成")

    class MockConfig:
        """模拟配置"""
        class Execution:
            timeout = 300
            retry_times = 2
            retry_interval = 5

        execution = Execution()

    # 创建 handler
    handler = UnifiedEventHandler.__new__(UnifiedEventHandler)
    handler.config = MockConfig()
    handler.spreadsheet = MockSpreadsheetClient()
    handler.approvals_map = {}
    handler.hrm_events_map = {}
    handler._processed_events = {}

    # 创建多个模拟 actions
    actions = [
        Action(type="update_spreadsheet", sheet_id="Sheet1", base_id="Base1", updates=[
            UpdateField(field_name="字段1", value="值1"),
            UpdateField(field_name="时间", timestamp=True),
        ]),
        Action(type="update_spreadsheet", sheet_id="Sheet2", base_id="Base1", updates=[
            UpdateField(field_name="字段2", value="值2"),
            UpdateField(field_name="时间", timestamp=True),
        ]),
        Action(type="update_spreadsheet", sheet_id="Sheet3", base_id="Base1", updates=[
            UpdateField(field_name="字段3", value="值3"),
            UpdateField(field_name="时间", timestamp=True),
        ]),
    ]

    # 模拟表单数据
    form_data = {"test": "data"}

    logger.info("测试场景: 3个表格更新操作")
    logger.info("  - 每个操作耗时 2 秒")
    logger.info("  - 串行执行需要 6 秒")
    logger.info("  - 并行执行只需 2 秒")
    logger.info("")
    logger.info("=" * 60)
    logger.info("开始测试...")
    logger.info("=" * 60)
    logger.info("")

    start_time = asyncio.get_event_loop().time()

    # 执行操作
    await handler._execute_actions(actions, "测试事件", form_data, None)

    end_time = asyncio.get_event_loop().time()
    elapsed = end_time - start_time

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"测试完成，总耗时: {elapsed:.2f}秒")
    logger.info("")
    if elapsed < 3:
        logger.info("✓ 并行执行成功！耗时明显少于串行执行")
    else:
        logger.warning("✗ 可能不是并行执行")
    logger.info("=" * 60)


async def main():
    try:
        await test_parallel_actions()
    except KeyboardInterrupt:
        logger.info("\n测试已取消")


if __name__ == "__main__":
    asyncio.run(main())
