"""钉钉Stream事件监听客户端"""
import asyncio
import json
import os
import subprocess
import time
from typing import Any, Optional, Dict
from datetime import datetime
from pathlib import Path
import aiohttp
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

# 事件去重缓存过期时间（秒）
EVENT_DEDUP_TTL = 300  # 5分钟


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

        # 事件去重缓存：{event_key: timestamp}
        # event_key 格式："{event_type}:{process_instance_id}" 或 "{event_type}:{staff_id}:{change_type}"
        self._processed_events: Dict[str, float] = {}

        logger.info(f"已加载 {len(self.approvals_map)} 个审批流程配置")
        logger.info(f"已加载 {len(self.hrm_events_map)} 个人事变动事件配置")

    def _is_event_processed(self, event_key: str) -> bool:
        """检查事件是否已处理过"""
        if event_key in self._processed_events:
            # 检查是否在缓存期内
            if time.time() - self._processed_events[event_key] < EVENT_DEDUP_TTL:
                logger.info(f"事件已处理过，跳过: {event_key}")
                return True
            else:
                # 缓存过期，删除旧记录
                del self._processed_events[event_key]
        return False

    def _mark_event_processed(self, event_key: str):
        """标记事件已处理"""
        self._processed_events[event_key] = time.time()
        # 定期清理过期缓存
        if len(self._processed_events) > 1000:
            self._clean_expired_events()

    def _clean_expired_events(self):
        """清理过期的事件缓存"""
        current_time = time.time()
        expired_keys = [
            key for key, timestamp in self._processed_events.items()
            if current_time - timestamp > EVENT_DEDUP_TTL
        ]
        for key in expired_keys:
            del self._processed_events[key]
        if expired_keys:
            logger.debug(f"清理了 {len(expired_keys)} 条过期事件缓存")

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

            if not staff_id:
                logger.warning("人事变动事件中未找到staffId")
                return AckMessage.STATUS_OK, "OK"

            logger.info(f"收到人事变动事件: {HRM_CHANGE_TYPE_MAP.get(change_type, change_type)} (changeType={change_type})")
            logger.info(f"员工ID: {staff_id}")
            logger.debug(f"事件数据: {event_data}")

            # 事件去重：使用 staff_id + change_type 作为唯一标识
            event_key = f"hrm:{staff_id}:{change_type}"
            if self._is_event_processed(event_key):
                return AckMessage.STATUS_OK, "OK"
            self._mark_event_processed(event_key)

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

            # 获取用户详细信息
            try:
                logger.info(f"正在获取用户详细信息: {staff_id}")
                user_info = await self.spreadsheet.get_user_info(staff_id)

                if user_info:
                    # 将用户信息合并到表单数据中，使用 userInfo 前缀避免冲突
                    # 同时也将常用字段直接放在顶层，方便配置使用
                    form_data["userInfo"] = user_info

                    # 提取常用字段到顶层，方便配置中使用
                    # 用户基本信息
                    if "userid" in user_info:
                        form_data["userId"] = user_info["userid"]
                        form_data["userid"] = user_info["userid"]  # 兼容不同命名
                    if "unionid" in user_info:
                        form_data["unionId"] = user_info["unionid"]
                        form_data["unionid"] = user_info["unionid"]
                    if "name" in user_info:
                        form_data["name"] = user_info["name"]
                        form_data["userName"] = user_info["name"]
                    if "avatar" in user_info:
                        form_data["avatar"] = user_info["avatar"]
                    if "mobile" in user_info:
                        form_data["mobile"] = user_info["mobile"]
                        form_data["phone"] = user_info["mobile"]
                    if "email" in user_info:
                        form_data["email"] = user_info["email"]
                    if "position" in user_info:
                        form_data["position"] = user_info["position"]
                        form_data["jobTitle"] = user_info["position"]

                    # 部门信息
                    if "dept_id_list" in user_info:
                        form_data["deptIdList"] = user_info["dept_id_list"]
                        form_data["deptIds"] = ", ".join(user_info["dept_id_list"])
                    if "dept_list" in user_info and user_info["dept_list"]:
                        # 取第一个部门
                        first_dept = user_info["dept_list"][0]
                        if "dept_id" in first_dept:
                            form_data["deptId"] = first_dept["dept_id"]
                        if "name" in first_dept:
                            form_data["deptName"] = first_dept["name"]

                    # 工作信息
                    if "workPlace" in user_info:
                        form_data["workPlace"] = user_info["workPlace"]
                        form_data["location"] = user_info["workPlace"]

                    # 状态信息
                    if "active" in user_info:
                        form_data["active"] = user_info["active"]
                        form_data["isActive"] = user_info["active"]
                    if "statecode" in user_info:
                        form_data["stateCode"] = user_info["statecode"]

                    # 职务信息
                    if "boss" in user_info:
                        form_data["isBoss"] = user_info["boss"]
                    if "admin" in user_info:
                        form_data["isAdmin"] = user_info["admin"]
                    if "senior" in user_info:
                        form_data["isSenior"] = user_info["senior"]

                    logger.info(f"成功获取用户信息: 姓名={form_data.get('name')}, 部门={form_data.get('deptName')}")
                else:
                    logger.warning(f"未获取到用户信息: {staff_id}")

            except Exception as e:
                logger.warning(f"获取用户详细信息失败，继续使用事件数据: {e}")
                # 即使获取用户信息失败，也继续执行后续操作

            logger.debug(f"最终表单数据: {form_data}")

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

            # 事件去重：使用 processInstanceId 作为唯一标识
            # 注意：不使用 event_type，因为 bpms_task_change 和 bpms_instance_change 都应该去重
            event_key = f"approval:{process_instance_id}"
            if self._is_event_processed(event_key):
                return AckMessage.STATUS_OK, "OK"
            self._mark_event_processed(event_key)

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
                elif action.type == "webhook":
                    await self._send_webhook(action, form_data)
                elif action.type == "shell":
                    await self._execute_shell(action, form_data)
                elif action.type == "python":
                    await self._execute_python(action, form_data)
                else:
                    logger.warning(f"未知的操作类型: {action.type}")

            except Exception as e:
                logger.exception(f"执行操作失败: {action.type}, 错误: {e}")
                # 根据配置决定是否继续执行后续操作

    async def _update_spreadsheet(self, action, form_data: dict[str, Any], operator_id: Optional[str] = None):
        """更新或新增AI表格记录

        如果没有指定find_by，则执行新增操作
        如果指定了find_by，则执行更新操作

        Args:
            action: 操作配置
            form_data: 表单数据
            operator_id: 操作者ID（审批人的unionId）
        """
        if not action.updates:
            logger.warning("update_spreadsheet操作没有配置任何字段")
            return

        sheet_id = action.sheet_id or self.config.spreadsheet.default_sheet_id
        base_id = action.base_id or self.config.spreadsheet.base_id

        # 根据是否有find_by决定是新增还是更新
        if action.find_by:
            # 更新模式
            logger.info(f"开始更新表格: base={base_id}, sheet={sheet_id}, 查找条件={action.find_by.field_name}={action.find_by.form_field}")
        else:
            # 新增模式
            logger.info(f"开始新增记录: base={base_id}, sheet={sheet_id}")

        # 重试逻辑
        max_retries = self.config.execution.retry_times
        retry_interval = self.config.execution.retry_interval

        for attempt in range(max_retries + 1):
            try:
                if action.find_by:
                    # 更新现有记录
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
                    # 新增记录
                    success = await self.spreadsheet.process_add_actions(
                        sheet_id=sheet_id,
                        base_id=base_id,
                        updates=action.updates,
                        form_data=form_data,
                        operator_id=operator_id
                    )

                    if success:
                        logger.info(f"记录新增成功: {sheet_id}")
                        return

                # 操作失败，重试
                if attempt < max_retries:
                    logger.warning(f"操作失败，{retry_interval}秒后重试 ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_interval)
                else:
                    logger.error(f"操作失败，已达最大重试次数: {max_retries}")

            except Exception as e:
                logger.exception(f"操作表格时发生异常: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_interval)
                else:
                    raise

    async def _send_webhook(self, action, form_data: dict[str, Any]):
        """发送HTTP Webhook请求

        Args:
            action: 操作配置
            form_data: 表单数据
        """
        if not action.url:
            logger.error("webhook操作缺少url配置")
            return

        url = action.url
        method = action.method or "POST"
        headers = action.headers or {}
        body = action.body or {}

        logger.info(f"发送Webhook: {method} {url}")
        logger.debug(f"Webhook配置body: {body}")

        try:
            async with aiohttp.ClientSession() as session:
                # 设置默认headers
                default_headers = {"Content-Type": "application/json"}
                default_headers.update(headers)

                # 构建请求体
                request_body = None
                if method.upper() in ["POST", "PUT", "PATCH"]:
                    # 处理body配置，支持占位符替换
                    payload = {}

                    for key, value in body.items():
                        if isinstance(value, str):
                            # 字符串值：先替换占位符，然后尝试解析为JSON
                            replaced = self._replace_placeholders(value, form_data)
                            try:
                                # 尝试解析为JSON对象（处理配置中的JSON字符串）
                                parsed = json.loads(replaced)
                                payload[key] = parsed
                            except json.JSONDecodeError:
                                # 不是有效的JSON，直接使用字符串
                                payload[key] = replaced
                        elif isinstance(value, dict):
                            # 字典值：递归处理占位符替换
                            payload[key] = self._process_dict_placeholders(value, form_data)
                        elif isinstance(value, list):
                            # 列表值：递归处理
                            payload[key] = self._process_list_placeholders(value, form_data)
                        else:
                            # 其他类型直接使用
                            payload[key] = value

                    request_body = json.dumps(payload)
                    logger.debug(f"Webhook请求体: {request_body}")

                async with session.request(
                    method=method,
                    url=url,
                    headers=default_headers,
                    data=request_body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_text = await response.text()
                    logger.info(f"Webhook响应: {response.status} - {response_text[:200]}")

                    if response.status >= 400:
                        logger.warning(f"Webhook返回错误状态码: {response.status}")

        except asyncio.TimeoutError:
            logger.error("Webhook请求超时")
        except Exception as e:
            logger.exception(f"发送Webhook失败: {e}")

    async def _execute_shell(self, action, form_data: dict[str, Any]):
        """执行Shell命令

        Args:
            action: 操作配置
            form_data: 表单数据
        """
        if not action.command:
            logger.error("shell操作缺少command配置")
            return

        command = action.command
        args = action.args or []

        # 替换args中的占位符
        resolved_args = []
        for arg in args:
            resolved_args.append(self._replace_placeholders(arg, form_data))

        logger.info(f"执行Shell命令: {command} {' '.join(resolved_args)}")

        try:
            # 执行命令
            process = await asyncio.create_subprocess_exec(
                command,
                *resolved_args,
                cwd=action.cwd,
                env={**os.environ, **(action.env or {})},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.execution.timeout
            )

            if stdout:
                logger.info(f"Shell命令输出:\n{stdout.decode('utf-8', errors='replace')}")
            if stderr:
                logger.warning(f"Shell命令错误输出:\n{stderr.decode('utf-8', errors='replace')}")

            if process.returncode != 0:
                logger.error(f"Shell命令退出码: {process.returncode}")
            else:
                logger.info("Shell命令执行成功")

        except asyncio.TimeoutError:
            logger.error("Shell命令执行超时")
            try:
                process.kill()
            except:
                pass
        except Exception as e:
            logger.exception(f"执行Shell命令失败: {e}")

    async def _execute_python(self, action, form_data: dict[str, Any]):
        """执行Python脚本

        Args:
            action: 操作配置
            form_data: 表单数据
        """
        if not action.script:
            logger.error("python操作缺少script配置")
            return

        script_path = Path(action.script)
        if not script_path.exists():
            logger.error(f"Python脚本不存在: {script_path}")
            return

        logger.info(f"执行Python脚本: {script_path}")

        try:
            # 构建命令: python script.py '{"form_data": {...}}'
            import sys
            python_exe = sys.executable

            # 将form_data作为JSON字符串传递给脚本
            form_data_json = json.dumps(form_data, ensure_ascii=False)

            process = await asyncio.create_subprocess_exec(
                python_exe,
                str(script_path),
                form_data_json,
                cwd=action.cwd or script_path.parent,
                env={**os.environ, **(action.env or {})},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.execution.timeout
            )

            if stdout:
                logger.info(f"Python脚本输出:\n{stdout.decode('utf-8', errors='replace')}")
            if stderr:
                logger.warning(f"Python脚本错误输出:\n{stderr.decode('utf-8', errors='replace')}")

            if process.returncode != 0:
                logger.error(f"Python脚本退出码: {process.returncode}")
            else:
                logger.info("Python脚本执行成功")

        except asyncio.TimeoutError:
            logger.error("Python脚本执行超时")
        except Exception as e:
            logger.exception(f"执行Python脚本失败: {e}")

    def _replace_placeholders(self, text: str, form_data: dict[str, Any]) -> str:
        """替换字符串中的占位符

        支持格式: {form_data:field_name}

        Args:
            text: 包含占位符的字符串
            form_data: 表单数据

        Returns:
            替换后的字符串
        """
        import re

        def replace_match(match):
            field_path = match.group(1)
            # 支持嵌套访问，如 {form_data:user.name}
            value = form_data
            for key in field_path.split('.'):
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    return ""
            return str(value) if value is not None else ""

        # 匹配 {form_data:xxx} 格式
        pattern = r'\{form_data:([^}]+)\}'
        return re.sub(pattern, replace_match, text)

    def _process_dict_placeholders(self, data: dict, form_data: dict[str, Any]) -> dict:
        """递归处理字典中的占位符替换

        Args:
            data: 字典数据
            form_data: 表单数据

        Returns:
            处理后的字典
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self._replace_placeholders(value, form_data)
            elif isinstance(value, dict):
                result[key] = self._process_dict_placeholders(value, form_data)
            elif isinstance(value, list):
                result[key] = self._process_list_placeholders(value, form_data)
            else:
                result[key] = value
        return result

    def _process_list_placeholders(self, data: list, form_data: dict[str, Any]) -> list:
        """递归处理列表中的占位符替换

        Args:
            data: 列表数据
            form_data: 表单数据

        Returns:
            处理后的列表
        """
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self._replace_placeholders(item, form_data))
            elif isinstance(item, dict):
                result.append(self._process_dict_placeholders(item, form_data))
            elif isinstance(item, list):
                result.append(self._process_list_placeholders(item, form_data))
            else:
                result.append(item)
        return result


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
