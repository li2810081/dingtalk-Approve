"""钉钉Stream事件监听客户端"""
import asyncio
from typing import Any, Optional
import dingtalk_stream
from dingtalk_stream import AckMessage
from loguru import logger

from src.config import Config
from src.spreadsheet_client import SpreadsheetClient


# 人事变动类型映射
HRM_CHANGE_TYPE_MAP = {
    1: "入职",
    2: "转正",
    3: "调岗",
    4: "离职",
    8: "晋升",
}


class UnifiedEventHandler(dingtalk_stream.EventHandler):
    """统一事件处理器 - 处理审批事件和人事变动事件"""

    def __init__(self, config: Config, spreadsheet_client: SpreadsheetClient):
        self.config = config
        self.spreadsheet = spreadsheet_client

        # 构建审批流程映射
        self.approvals_map = {
            approval.template_id: approval
            for approval in config.approvals
            if approval.enabled
        }

        # 构建人事变动事件映射
        self.hrm_events_map = {
            hrm_event.change_type: hrm_event
            for hrm_event in config.hrm_events
            if hrm_event.enabled
        }

        logger.info(f"已加载 {len(self.approvals_map)} 个审批流程配置")
        logger.info(f"已加载 {len(self.hrm_events_map)} 个人事变动事件配置")

    async def process(self, event: dingtalk_stream.EventMessage) -> tuple[str, str]:
        """处理事件"""
        try:
            event_type = event.headers.event_type

            # 处理人事变动事件
            if event_type == "hrm_mdm_user_change":
                return await self._process_hrm_event(event)

            # 处理审批事件
            if event_type in ["bpms_task_change", "bpms_instance_change"]:
                return await self._process_approval_event(event)

            # 未知事件类型
            logger.debug(f"跳过未处理的事件类型: {event_type}")
            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.exception(f"处理事件时发生错误: {e}")
            return AckMessage.STATUS_SYSTEM_EXCEPTION, str(e)

    async def _process_hrm_event(self, event: dingtalk_stream.EventMessage) -> tuple[str, str]:
        """处理人事变动事件"""
        try:
            event_data = event.data
            change_type = event_data.get("changeType")
            staff_id = event_data.get("staffId")

            if change_type is None:
                logger.warning("人事变动事件中未找到changeType")
                return AckMessage.STATUS_OK, "OK"

            logger.info(f"收到人事变动事件: {HRM_CHANGE_TYPE_MAP.get(change_type, change_type)} (changeType={change_type})")
            logger.info(f"员工ID: {staff_id}")
            logger.debug(f"事件数据: {event_data}")

            # 查找匹配的人事变动配置
            hrm_event = self.hrm_events_map.get(change_type)
            if not hrm_event:
                logger.info(f"未配置的人事变动类型: {change_type}")
                return AckMessage.STATUS_OK, "OK"

            logger.info(f"匹配到人事变动配置: {hrm_event.name}")

            # 构建表单数据（从事件数据中提取）
            form_data = {
                "staffId": staff_id,
                "changeType": change_type,
                "changeTypeName": HRM_CHANGE_TYPE_MAP.get(change_type, str(change_type)),
            }

            # 添加事件中的其他字段
            for key, value in event_data.items():
                if key not in form_data:
                    form_data[key] = value

            logger.debug(f"提取的表单数据: {form_data}")

            # 执行配置的操作
            await self._execute_actions(hrm_event.actions, hrm_event.name, form_data, None)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.exception(f"处理人事变动事件时发生错误: {e}")
            return AckMessage.STATUS_SYSTEM_EXCEPTION, str(e)

    async def _process_approval_event(self, event: dingtalk_stream.EventMessage) -> tuple[str, str]:
        """处理审批事件"""
        try:
            event_data = event.data
            logger.info(f"事件标题: {event_data.get("title")}")
            logger.debug(f"事件数据: {event_data}")

            # 检查审批状态
            result = event_data.get("result")
            if result != "agree":
                logger.info(f"审批未通过，状态: {result}，跳过处理")
                return AckMessage.STATUS_OK, "OK"

            # 获取审批模板ID
            process_code = event_data.get("processCode")

            if not process_code:
                logger.warning("事件数据中未找到processCode")
                return AckMessage.STATUS_OK, "OK"

            # 查找匹配的审批配置
            approval = self.approvals_map.get(process_code)
            if not approval:
                logger.info(f"未配置的审批流程: {process_code}")
                return AckMessage.STATUS_OK, "OK"

            logger.info(f"匹配到审批配置: {approval.name}")
            logger.info(f"审批数据: {event_data}")
            # 获取审批实例ID
            process_instance_id = event_data.get("processInstanceId")
            if not process_instance_id:
                logger.warning("事件数据中未找到processInstanceId")
                return AckMessage.STATUS_OK, "OK"

            # 获取审批实例详情
            try:
                instance_details = await self.spreadsheet.get_process_instance(process_instance_id)
                logger.debug(f"审批实例详情: {instance_details}")

                # 合并事件数据和详情数据
                event_data.update(instance_details)

            except Exception as e:
                logger.error(f"获取审批实例详情失败: {e}")
                # 即使获取详情失败，也尝试使用已有数据继续处理

            # 获取表单数据
            form_data = self._extract_form_data(event_data)

            # 获取操作者ID（用于AI表格API）
            # 优先使用操作者的unionId，如果没有则使用userid
            operator_id = (
                event_data.get("operatorUnionId") or
                event_data.get("operator") or
                event_data.get("userid") or
                event_data.get("originatorUnionId")
            )
            if operator_id:
                logger.debug(f"操作者ID: {operator_id}")

            # 执行配置的操作
            await self._execute_actions(approval.actions, approval.name, form_data, operator_id)

            return AckMessage.STATUS_OK, "OK"

        except Exception as e:
            logger.exception(f"处理审批事件时发生错误: {e}")
            return AckMessage.STATUS_SYSTEM_EXCEPTION, str(e)

    def _extract_form_data(self, event_data: dict[str, Any]) -> dict[str, Any]:
        """从事件数据中提取表单数据"""
        form_data = {}

        # 尝试从不同的字段提取表单数据
        if "formComponentValues" in event_data:
            # 处理表单组件值 (列表形式)
            # 格式: [{"name": "组件名", "value": "值", "extValue": "扩展值"}, ...]
            for component in event_data["formComponentValues"]:
                name = component.get("name")
                value = component.get("value")
                
                # 有些组件可能没有name，只有id，但这通常不是我们要找的业务字段
                if name:
                    form_data[name] = value
                    
                    # 尝试处理扩展值 (如人员选择组件的工号等)
                    ext_value = component.get("extValue")
                    if ext_value:
                         form_data[f"{name}_ext"] = ext_value

        # 同时也保留原始 event_data 中的扁平字段，以防万一
        for key, value in event_data.items():
            if key not in ["process_code", "result", "instance_id", "task_id", "formComponentValues"]:
                 # 如果formComponentValues中已经有了，就不覆盖
                 if key not in form_data:
                     form_data[key] = value

        logger.debug(f"提取的表单数据: {form_data}")
        return form_data

    async def _execute_actions(self, actions: list, event_name: str, form_data: dict[str, Any], operator_id: Optional[str] = None):
        """执行事件后的操作

        Args:
            actions: 操作配置列表
            event_name: 事件名称
            form_data: 表单数据
            operator_id: 操作者ID（审批人的unionId）
        """
        for action in actions:
            try:
                if action.type == "update_spreadsheet":
                    await self._update_spreadsheet(action, form_data, operator_id)
                else:
                    logger.warning(f"未知的操作类型: {action.type}")

            except Exception as e:
                logger.exception(f"执行操作失败: {action.type}, 错误: {e}")
                # 根据配置决定是否继续执行后续操作

    async def _update_spreadsheet(self, action, form_data: dict[str, Any], operator_id: Optional[str] = None):
        """更新AI表格

        Args:
            action: 操作配置
            form_data: 表单数据
            operator_id: 操作者ID（审批人的unionId）
        """
        if not action.find_by:
            logger.error("update_spreadsheet操作缺少find_by配置")
            return

        if not action.updates:
            logger.warning("update_spreadsheet操作没有配置任何更新字段")
            return

        sheet_id = action.sheet_id or self.config.spreadsheet.default_sheet_id
        base_id = action.base_id or self.config.spreadsheet.base_id

        logger.info(f"开始更新表格: base={base_id}, sheet={sheet_id}, 查找条件={action.find_by.field_name}={action.find_by.form_field}")

        # 重试逻辑
        max_retries = self.config.execution.retry_times
        retry_interval = self.config.execution.retry_interval

        for attempt in range(max_retries + 1):
            try:
                success = await self.spreadsheet.process_update_actions(
                    sheet_id=sheet_id,
                    base_id=base_id,
                    find_by=action.find_by,
                    updates=action.updates,
                    form_data=form_data,
                    operator_id=operator_id
                )

                if success:
                    logger.info(f"表格更新成功: {sheet_id}")
                    return
                else:
                    if attempt < max_retries:
                        logger.warning(f"表格更新失败，{retry_interval}秒后重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_interval)
                    else:
                        logger.error(f"表格更新失败，已达最大重试次数: {max_retries}")

            except Exception as e:
                logger.exception(f"更新表格时发生异常: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_interval)
                else:
                    raise


def create_stream_client(config: Config, spreadsheet_client: SpreadsheetClient) -> dingtalk_stream.DingTalkStreamClient:
    """创建钉钉Stream客户端

    Args:
        config: 应用配置
        spreadsheet_client: AI表格客户端

    Returns:
        Stream客户端实例
    """
    credential = dingtalk_stream.Credential(
        config.dingtalk.app_key,
        config.dingtalk.app_secret
    )

    client = dingtalk_stream.DingTalkStreamClient(credential)

    # 注册统一事件处理器（处理审批事件和人事变动事件）
    handler = UnifiedEventHandler(config, spreadsheet_client)
    client.register_all_event_handler(handler)

    logger.info("钉钉Stream客户端创建成功")
    return client
