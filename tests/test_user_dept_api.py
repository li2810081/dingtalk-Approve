"""测试用户信息和部门信息获取API"""
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


async def test_get_user_info(client: SpreadsheetClient, userid: str):
    """测试获取用户详细信息

    Args:
        client: SpreadsheetClient 实例
        userid: 用户ID
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"测试 1: 获取用户详细信息 (userid={userid})")
    logger.info(f"{'='*50}")

    try:
        user_info = await client.get_user_info(userid, fetch_dept_details=True)

        if not user_info:
            logger.error(f"✗ 未获取到用户信息")
            return

        logger.info("\n✓ 成功获取用户信息:")
        logger.info(f"  用户ID: {user_info.get('userid')}")
        logger.info(f"  姓名: {user_info.get('name')}")
        logger.info(f"  手机: {user_info.get('mobile')}")
        logger.info(f"  邮箱: {user_info.get('email')}")
        logger.info(f"  职位: {user_info.get('position')}")
        logger.info(f"  工作地点: {user_info.get('workPlace')}")
        logger.info(f"  状态: {'激活' if user_info.get('active') else '未激活'}")
        logger.info(f"  是否管理员: {'是' if user_info.get('admin') else '否'}")
        logger.info(f"  是否高管: {'是' if user_info.get('senior') else '否'}")

        # 显示部门信息
        dept_id_list = user_info.get('dept_id_list', [])
        logger.info(f"\n  所属部门ID列表: {dept_id_list}")

        dept_list = user_info.get('dept_list', [])
        if dept_list:
            logger.info(f"\n  部门详细信息 ({len(dept_list)} 个部门):")
            for i, dept in enumerate(dept_list, 1):
                logger.info(f"    部门 {i}:")
                logger.info(f"      ID: {dept.get('dept_id')}")
                logger.info(f"      名称: {dept.get('name')}")
                logger.info(f"      父部门ID: {dept.get('parent_id')}")
        else:
            logger.warning(f"  ⚠ 未获取到部门详细信息")

        return user_info

    except Exception as e:
        logger.error(f"✗ 获取用户信息失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_get_dept_info(client: SpreadsheetClient, dept_id: str):
    """测试获取部门详细信息

    Args:
        client: SpreadsheetClient 实例
        dept_id: 部门ID
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"测试 2: 获取部门详细信息 (dept_id={dept_id})")
    logger.info(f"{'='*50}")

    try:
        # 获取 access_token
        access_token = await client._get_access_token()

        # 获取 HTTP 客户端
        http_client = await client._get_client()

        # 调用获取部门信息的方法
        dept_info = await client._get_dept_info(dept_id, access_token, http_client)

        if not dept_info:
            logger.error(f"✗ 未获取到部门信息")
            return

        logger.info("\n✓ 成功获取部门信息:")
        logger.info(f"  部门ID: {dept_info.get('dept_id')}")
        logger.info(f"  部门名称: {dept_info.get('name')}")
        logger.info(f"  父部门ID: {dept_info.get('parent_id')}")
        logger.info(f"  是否自动加入部门群: {dept_info.get('auto_add_user')}")
        logger.info(f"  是否创建部门群: {dept_info.get('create_dept_group')}")
        logger.info(f"  部门主管: {dept_info.get('org_dept_owner')}")

        return dept_info

    except Exception as e:
        logger.error(f"✗ 获取部门信息失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_user_with_multiple_departments(client: SpreadsheetClient, userid: str):
    """测试获取属于多个部门的用户信息

    Args:
        client: SpreadsheetClient 实例
        userid: 用户ID
    """
    logger.info(f"\n{'='*50}")
    logger.info(f"测试 3: 测试多部门用户信息")
    logger.info(f"{'='*50}")

    try:
        user_info = await client.get_user_info(userid, fetch_dept_details=True)

        if not user_info:
            logger.error(f"✗ 未获取到用户信息")
            return

        dept_id_list = user_info.get('dept_id_list', [])
        dept_list = user_info.get('dept_list', [])

        logger.info(f"\n用户 {user_info.get('name')} 属于 {len(dept_id_list)} 个部门:")
        logger.info(f"  部门ID列表: {dept_id_list}")

        if dept_list:
            logger.info(f"\n获取到的部门详情:")
            for i, dept in enumerate(dept_list, 1):
                logger.info(f"  {i}. {dept.get('name')} (ID: {dept.get('dept_id')})")
        else:
            logger.warning(f"  ⚠ 未获取到部门详情，可能是API调用失败")

    except Exception as e:
        logger.error(f"✗ 测试失败: {e}")


async def test_form_data_extraction():
    """测试表单数据提取（模拟人事事件处理）"""
    logger.info(f"\n{'='*50}")
    logger.info(f"测试 4: 模拟表单数据提取")
    logger.info(f"{'='*50}")

    # 模拟用户信息返回结果
    mock_user_info = {
        "userid": "123456",
        "unionid": "union789",
        "name": "张三",
        "mobile": "13800138000",
        "email": "zhangsan@example.com",
        "position": "软件工程师",
        "workPlace": "北京",
        "active": True,
        "admin": False,
        "senior": False,
        "dept_id_list": ["111", "222"],
        "dept_list": [
            {"dept_id": "111", "name": "技术部", "parent_id": "1"},
            {"dept_id": "222", "name": "研发中心", "parent_id": "1"}
        ]
    }

    logger.info("\n模拟提取用户信息到表单数据:")

    # 模拟 stream_client.py 中的字段提取逻辑
    form_data = {
        "staffId": mock_user_info.get("userid"),
        "changeType": 4,
        "changeTypeName": "离职",
    }

    # 提取常用字段
    if "userid" in mock_user_info:
        form_data["userId"] = mock_user_info["userid"]
    if "name" in mock_user_info:
        form_data["name"] = mock_user_info["name"]
        form_data["userName"] = mock_user_info["name"]
    if "mobile" in mock_user_info:
        form_data["mobile"] = mock_user_info["mobile"]
        form_data["phone"] = mock_user_info["mobile"]
    if "position" in mock_user_info:
        form_data["position"] = mock_user_info["position"]
        form_data["jobTitle"] = mock_user_info["position"]

    # 提取部门信息
    if "dept_list" in mock_user_info and mock_user_info["dept_list"]:
        first_dept = mock_user_info["dept_list"][0]
        if "dept_id" in first_dept:
            form_data["deptId"] = first_dept["dept_id"]
        if "name" in first_dept:
            form_data["deptName"] = first_dept["name"]

    logger.info("\n提取后的表单数据:")
    for key, value in form_data.items():
        logger.info(f"  {key}: {value}")

    logger.info("\n✓ 表单数据提取测试完成")


async def main():
    """主测试函数"""
    logger.info("=" * 50)
    logger.info("开始测试用户和部门信息获取API")
    logger.info("=" * 50)

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
        logger.info("\n请确保 .env 文件包含以下内容:")
        logger.info("  DINGTALK_APP_KEY=your_app_key")
        logger.info("  DINGTALK_APP_SECRET=your_app_secret")
        return

    client = SpreadsheetClient(
        config=config.spreadsheet,
        app_key=app_key,
        app_secret=app_secret
    )

    # ===== 测试配置 =====
    # 请修改为实际的用户ID和部门ID进行测试
    # 可以通过钉钉管理后台或调用其他API获取这些ID
    TEST_USER_ID = os.getenv("TEST_USER_ID", "")  # 从环境变量读取测试用户ID
    TEST_DEPT_ID = os.getenv("TEST_DEPT_ID", "1")  # 默认测试根部门(ID=1)

    # ===== 执行测试 =====
    test_results = []

    # 测试 1: 获取用户信息
    if TEST_USER_ID:
        result = await test_get_user_info(client, TEST_USER_ID)
        test_results.append(("获取用户信息", result is not None))

        if result:
            # 测试 3: 多部门用户（使用同一个用户）
            await test_user_with_multiple_departments(client, TEST_USER_ID)

            # 获取用户的第一个部门ID，用于部门信息测试
            dept_id_list = result.get('dept_id_list', [])
            if dept_id_list:
                TEST_DEPT_ID = dept_id_list[0]
                logger.info(f"\n使用用户的部门ID进行测试: {TEST_DEPT_ID}")
    else:
        logger.warning("\n跳过用户信息测试（未设置 TEST_USER_ID）")
        logger.info("提示: 可以在 .env 文件中添加 TEST_USER_ID=你的用户ID 来测试")
        test_results.append(("获取用户信息", None))

    # 测试 2: 获取部门信息
    result = await test_get_dept_info(client, TEST_DEPT_ID)
    test_results.append(("获取部门信息", result is not None))

    # 测试 4: 表单数据提取（不需要API调用）
    await test_form_data_extraction()
    test_results.append(("表单数据提取", True))

    # ===== 测试结果汇总 =====
    logger.info(f"\n{'='*50}")
    logger.info("测试结果汇总")
    logger.info(f"{'='*50}")

    passed = sum(1 for _, result in test_results if result is True)
    failed = sum(1 for _, result in test_results if result is False)
    skipped = sum(1 for _, result in test_results if result is None)

    for test_name, result in test_results:
        if result is True:
            logger.info(f"  ✓ {test_name}")
        elif result is False:
            logger.info(f"  ✗ {test_name}")
        else:
            logger.info(f"  ⊘ {test_name} (跳过)")

    logger.info(f"\n总计: {len(test_results)} 个测试")
    logger.info(f"通过: {passed} 个")
    logger.info(f"失败: {failed} 个")
    logger.info(f"跳过: {skipped} 个")

    if failed == 0:
        logger.info("\n✓ 所有执行的测试都通过！")
    else:
        logger.info(f"\n✗ 有 {failed} 个测试失败")


if __name__ == "__main__":
    print("""
    ╔════════════════════════════════════════════════════════════╗
    ║      钉钉用户和部门信息API测试                            ║
    ╠════════════════════════════════════════════════════════════╣
    ║  此测试将验证以下功能:                                     ║
    ║  1. 获取用户详细信息（包括部门信息）                       ║
    ║  2. 获取部门详细信息                                       ║
    ║  3. 多部门用户信息处理                                     ║
    ║  4. 表单数据提取模拟                                       ║
    ╠════════════════════════════════════════════════════════════╣
    ║  提示: 可在 .env 文件中设置以下变量:                       ║
    ║  - TEST_USER_ID: 要测试的用户ID                            ║
    ║  - TEST_DEPT_ID: 要测试的部门ID（默认为1）                  ║
    ╚════════════════════════════════════════════════════════════╝
    """)

    asyncio.run(main())
