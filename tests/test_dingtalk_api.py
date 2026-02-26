import asyncio
import os
import sys
import logging
import json
from datetime import datetime

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

async def test_get_process_instance(client: SpreadsheetClient, process_instance_id: str):
    """测试获取审批实例详情"""
    logger.info(f"--- 开始测试: 获取审批实例详情 (ID={process_instance_id}) ---")
    try:
        result = await client.get_process_instance(process_instance_id)
        logger.info(f"成功获取详情: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception as e:
        logger.error(f"获取详情失败: {e}")
        return None

async def test_spreadsheet_operations(client: SpreadsheetClient, base_id: str, sheet_id: str):
    """测试表格操作：添加记录 -> 查找记录 -> 更新记录"""
    logger.info("--- 开始测试: 表格操作 ---")
    logger.info(f"Base ID: {base_id}")
    logger.info(f"Sheet ID: {sheet_id}")
    
    # 1. 准备测试数据 - 使用配置中的实际字段名
    test_data = {
        "fields": {
            "人员": f"测试人员_{datetime.now().strftime('%H%M%S')}",
            "部门": "测试部门",
            "事件": "自动化测试"
        }
    }
    
    logger.info(f"1. 尝试添加记录: {test_data}")
    try:
        # 添加记录 (operator_id 可选，用于测试)
        added_ids = await client.add_records(
            sheet_id=sheet_id,
            base_id=base_id,
            records=[test_data],
            operator_id=None  # 测试时可以不指定
        )
        logger.info(f"添加成功，记录ID: {added_ids}")
        
        if not added_ids:
            logger.error("未返回记录ID，停止后续测试")
            return

        record_id = added_ids[0]
        
        # 2. 查找刚刚添加的记录
        search_value = test_data["fields"]["人员"]
        logger.info(f"2. 尝试查找记录: 人员={search_value}")
        
        found_record = await client.find_record_by_value(
            sheet_id=sheet_id,
            base_id=base_id,
            field_name="人员",
            search_value=search_value
        )
        
        if found_record:
            logger.info(f"查找成功: {found_record}")
        else:
            logger.warning("查找失败或未找到记录")
            
        # 3. 更新记录
        update_data = {
            "records": [
                {
                    "id": record_id,
                    "fields": {
                        "事件": "自动化测试更新"
                    }
                }
            ]
        }
        logger.info(f"3. 尝试更新记录: {update_data}")
        
        update_result = await client.update_records(
            sheet_id=sheet_id,
            base_id=base_id,
            records=update_data["records"],
            operator_id=None  # 测试时可以不指定
        )
        
        if update_result:
             logger.info("更新成功")
        else:
             logger.warning("更新可能失败")

    except Exception as e:
        logger.error(f"表格操作测试失败: {e}")

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
    
    # --- 测试用例 1: 获取审批实例 ---
    # 示例ID
    process_instance_id = "3B3154FE-C04D-7B2E-83B6-5A2A9A4A17AD" 
    
    # 尝试调用，但允许失败
    await test_get_process_instance(client, process_instance_id)
    
    # --- 测试用例 2: 表格操作 (新增/查找/更新) ---
    # 从配置中自动获取 base_id 和 sheet_id
    test_base_id = None
    test_sheet_id = None
    
    if config.approvals:
        for approval in config.approvals:
            if approval.actions:
                for action in approval.actions:
                    if action.type == "update_spreadsheet" and action.base_id:
                        test_base_id = action.base_id
                        test_sheet_id = action.sheet_id
                        logger.info(f"从配置中找到 base_id: {test_base_id}, sheet_id: {test_sheet_id} (审批: {approval.name})")
                        break
            if test_base_id:
                break
    
    if not test_base_id:
        # 如果配置中没找到，尝试使用 SpreadsheetConfig 中的默认值
        test_base_id = config.spreadsheet.base_id
        test_sheet_id = config.spreadsheet.default_sheet_id
        if test_base_id:
             logger.warning(f"使用默认配置 base_id: {test_base_id}")
        else:
             logger.error("未在配置中找到有效的 base_id，无法进行表格操作测试")
             return

    print("\n" + "="*50)
    print("警告: 接下来的测试将向钉钉表格写入数据。")
    print(f"Base ID: {test_base_id}")
    print(f"Sheet ID: {test_sheet_id}")
    print("请确认 `test_spreadsheet_operations` 函数中的字段名与你的表格一致。")
    print("按 Enter 继续，或按 Ctrl+C 取消...")
    # input() # 在自动化环境中注释掉，实际运行时可以打开
    
    await test_spreadsheet_operations(client, test_base_id, test_sheet_id)

if __name__ == "__main__":
    asyncio.run(main())
