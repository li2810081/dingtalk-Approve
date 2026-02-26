"""测试新增记录功能（无find_by时执行新增）"""
import asyncio
import os
import sys
import logging

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.config import load_config, Action, UpdateField
from src.spreadsheet_client import SpreadsheetClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_add_without_findby(client: SpreadsheetClient, base_id: str, sheet_id: str):
    """测试没有find_by时执行新增操作"""
    logger.info("--- 测试: 无find_by时执行新增操作 ---")
    logger.info(f"Base ID: {base_id}")
    logger.info(f"Sheet ID: {sheet_id}")

    # 模拟form_data
    form_data = {
        "name": "测试员工",
        "department": "技术部",
        "position": "工程师",
        "mobile": "13800138000"
    }

    # 创建action配置（没有find_by）
    action = Action(
        type="update_spreadsheet",
        sheet_id=sheet_id,
        base_id=base_id,
        find_by=None,  # 关键：没有find_by
        updates=[
            UpdateField(field_name="姓名", form_field="name"),
            UpdateField(field_name="部门", form_field="department"),
            UpdateField(field_name="职位", form_field="position"),
            UpdateField(field_name="手机", form_field="mobile"),
            UpdateField(field_name="入职时间", timestamp=True),
        ]
    )

    try:
        # 执行新增操作
        success = await client.process_add_actions(
            sheet_id=action.sheet_id,
            base_id=action.base_id,
            updates=action.updates,
            form_data=form_data,
            operator_id=None
        )

        if success:
            logger.info("✓ 新增记录测试成功！")
        else:
            logger.error("✗ 新增记录测试失败")

    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")


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

    # 获取测试用的 base_id 和 sheet_id
    test_base_id = None
    test_sheet_id = None

    if config.approvals:
        for approval in config.approvals:
            if approval.actions:
                for action in approval.actions:
                    if action.type == "update_spreadsheet" and action.base_id:
                        test_base_id = action.base_id
                        test_sheet_id = action.sheet_id
                        logger.info(f"从配置中找到 base_id: {test_base_id}, sheet_id: {test_sheet_id}")
                        break
            if test_base_id:
                break

    if not test_base_id:
        test_base_id = config.spreadsheet.base_id
        test_sheet_id = config.spreadsheet.default_sheet_id
        if test_base_id:
            logger.warning(f"使用默认配置 base_id: {test_base_id}")
        else:
            logger.error("未在配置中找到有效的 base_id，无法进行测试")
            return

    print("\n" + "="*50)
    print("警告: 接下来的测试将向钉钉表格写入新数据。")
    print(f"Base ID: {test_base_id}")
    print(f"Sheet ID: {test_sheet_id}")
    print("请确认配置中的字段名与你的表格一致。")
    print("="*50 + "\n")

    await test_add_without_findby(client, test_base_id, test_sheet_id)


if __name__ == "__main__":
    asyncio.run(main())
