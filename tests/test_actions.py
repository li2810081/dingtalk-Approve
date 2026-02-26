"""测试各种 Actions 的执行"""
import asyncio
import os
import sys
import json
import logging
import tempfile
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from src.config import load_config, Action
from src.spreadsheet_client import SpreadsheetClient
from src.stream_client import UnifiedEventHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


async def test_webhook_action():
    """测试 Webhook Action"""
    logger.info("\n" + "="*50)
    logger.info("测试 1: Webhook Action")
    logger.info("="*50)

    # 创建一个测试用的 webhook action
    webhook_action = Action(
        type="webhook",
        url="https://httpbin.org/post",  # 测试用的公共echo服务
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Custom-Header": "test-value"
        },
        body={
            "message": "测试消息",
            "test_field": "test_value"
        }
    )

    # 创建临时配置
    from src.config import Config, DingTalkConfig
    test_config = Config(
        dingtalk=DingTalkConfig(
            app_key="test",
            app_secret="test"
        )
    )

    # 创建事件处理器
    spreadsheet_client = None  # webhook 不需要 spreadsheet client
    handler = UnifiedEventHandler(test_config, spreadsheet_client)

    # 模拟表单数据
    form_data = {
        "staffId": "test_123",
        "changeType": 4,
        "name": "测试用户",
        "department": "技术部"
    }

    logger.info(f"表单数据: {json.dumps(form_data, ensure_ascii=False)}")

    try:
        await handler._send_webhook(webhook_action, form_data)
        logger.info("✓ Webhook 测试完成")
    except Exception as e:
        logger.error(f"✗ Webhook 测试失败: {e}")


async def test_shell_action():
    """测试 Shell Action"""
    logger.info("\n" + "="*50)
    logger.info("测试 2: Shell Action")
    logger.info("="*50)

    # 创建测试用的 shell action
    shell_action = Action(
        type="shell",
        command="echo",  # 跨平台的简单命令
        args=[
            "Hello from shell!",
            "Staff: {form_data:staffId}",
            "Name: {form_data:name}"
        ]
    )

    from src.config import Config, DingTalkConfig, Execution
    test_config = Config(
        dingtalk=DingTalkConfig(
            app_key="test",
            app_secret="test"
        ),
        execution=Execution(timeout=10)
    )

    spreadsheet_client = None
    handler = UnifiedEventHandler(test_config, spreadsheet_client)

    form_data = {
        "staffId": "test_456",
        "name": "测试用户2"
    }

    logger.info(f"表单数据: {json.dumps(form_data, ensure_ascii=False)}")

    try:
        await handler._execute_shell(shell_action, form_data)
        logger.info("✓ Shell 测试完成")
    except Exception as e:
        logger.error(f"✗ Shell 测试失败: {e}")


async def test_python_action():
    """测试 Python Action"""
    logger.info("\n" + "="*50)
    logger.info("测试 3: Python Action")
    logger.info("="*50)

    # 创建临时测试脚本
    test_script = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.py',
        delete=False,
        encoding='utf-8'
    )

    script_content = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import json

# 读取传递的表单数据
if len(sys.argv) > 1:
    form_data = json.loads(sys.argv[1])
    print(f"收到表单数据: {json.dumps(form_data, ensure_ascii=False)}")
    print(f"员工ID: {form_data.get('staffId', 'N/A')}")
    print(f"姓名: {form_data.get('name', 'N/A')}")
    print(f"变动类型: {form_data.get('changeType', 'N/A')}")
else:
    print("错误: 未收到表单数据")
    sys.exit(1)

# 执行一些业务逻辑
print("正在执行业务逻辑...")
print("✓ Python 脚本执行成功")
'''

    test_script.write(script_content)
    test_script.close()

    logger.info(f"创建测试脚本: {test_script.name}")

    # 创建测试用的 python action
    python_action = Action(
        type="python",
        script=test_script.name
    )

    from src.config import Config, DingTalkConfig, Execution
    test_config = Config(
        dingtalk=DingTalkConfig(
            app_key="test",
            app_secret="test"
        ),
        execution=Execution(timeout=10)
    )

    spreadsheet_client = None
    handler = UnifiedEventHandler(test_config, spreadsheet_client)

    form_data = {
        "staffId": "test_789",
        "name": "测试用户3",
        "changeType": 1
    }

    logger.info(f"表单数据: {json.dumps(form_data, ensure_ascii=False)}")

    try:
        await handler._execute_python(python_action, form_data)
        logger.info("✓ Python 测试完成")
    except Exception as e:
        logger.error(f"✗ Python 测试失败: {e}")
    finally:
        # 清理临时文件
        try:
            os.unlink(test_script.name)
        except:
            pass


async def test_placeholder_replacement():
    """测试占位符替换功能"""
    logger.info("\n" + "="*50)
    logger.info("测试 4: 占位符替换")
    logger.info("="*50)

    from src.config import Config, DingTalkConfig
    test_config = Config(
        dingtalk=DingTalkConfig(
            app_key="test",
            app_secret="test"
        )
    )

    spreadsheet_client = None
    handler = UnifiedEventHandler(test_config, spreadsheet_client)

    # 测试数据
    form_data = {
        "staffId": "12345",
        "name": "张三",
        "department": {
            "name": "技术部",
            "code": "TECH"
        }
    }

    # 测试简单占位符
    text1 = "员工ID: {form_data:staffId}"
    result1 = handler._replace_placeholders(text1, form_data)
    logger.info(f"输入: {text1}")
    logger.info(f"输出: {result1}")
    assert result1 == "员工ID: 12345", f"预期: '员工ID: 12345', 实际: '{result1}'"

    # 测试嵌套占位符
    text2 = "部门: {form_data:department.name}"
    result2 = handler._replace_placeholders(text2, form_data)
    logger.info(f"输入: {text2}")
    logger.info(f"输出: {result2}")
    assert result2 == "部门: 技术部", f"预期: '部门: 技术部', 实际: '{result2}'"

    # 测试不存在的字段
    text3 = "不存在的字段: {form_data:notexist}"
    result3 = handler._replace_placeholders(text3, form_data)
    logger.info(f"输入: {text3}")
    logger.info(f"输出: {result3}")
    assert result3 == "不存在的字段: ", f"预期: '不存在的字段: ', 实际: '{result3}'"

    logger.info("✓ 占位符替换测试通过")


async def test_combined_actions():
    """测试组合多个 Actions"""
    logger.info("\n" + "="*50)
    logger.info("测试 5: 组合 Actions")
    logger.info("="*50)

    from src.config import Config, DingTalkConfig, Execution
    test_config = Config(
        dingtalk=DingTalkConfig(
            app_key="test",
            app_secret="test"
        ),
        execution=Execution(timeout=10)
    )

    spreadsheet_client = None
    handler = UnifiedEventHandler(test_config, spreadsheet_client)

    form_data = {
        "staffId": "test_combined",
        "name": "组合测试用户",
        "changeType": 4
    }

    # 创建多个 actions
    actions = [
        Action(
            type="shell",
            command="echo",
            args=["Step 1: Shell执行"]
        ),
        Action(
            type="webhook",
            url="https://httpbin.org/post",
            method="POST",
            body={"test": "combined"}
        )
    ]

    logger.info(f"表单数据: {json.dumps(form_data, ensure_ascii=False)}")
    logger.info(f"执行 {len(actions)} 个 actions")

    try:
        await handler._execute_actions(actions, "组合测试", form_data, None)
        logger.info("✓ 组合 Actions 测试完成")
    except Exception as e:
        logger.error(f"✗ 组合 Actions 测试失败: {e}")


async def main():
    """运行所有测试"""
    logger.info("=" * 50)
    logger.info("开始执行 Actions 测试")
    logger.info("=" * 50)

    # 加载环境变量（可选）
    load_dotenv()

    tests = [
        ("占位符替换", test_placeholder_replacement),
        ("Webhook Action", test_webhook_action),
        ("Shell Action", test_shell_action),
        ("Python Action", test_python_action),
        ("组合 Actions", test_combined_actions),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except AssertionError as e:
            logger.error(f"✗ {test_name} 断言失败: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"✗ {test_name} 异常: {e}")
            failed += 1

    # 输出测试结果
    logger.info("\n" + "=" * 50)
    logger.info("测试结果汇总")
    logger.info("=" * 50)
    logger.info(f"总计: {passed + failed} 个测试")
    logger.info(f"通过: {passed} 个")
    logger.info(f"失败: {failed} 个")

    if failed == 0:
        logger.info("\n✓ 所有测试通过！")
    else:
        logger.info(f"\n✗ 有 {failed} 个测试失败")


if __name__ == "__main__":
    asyncio.run(main())
