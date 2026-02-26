"""钉钉AI表格(Notable/多维表格)操作模块

使用记录式API，而非传统的单元格(A1/B1)操作方式
"""
import json
import re
from datetime import datetime
from typing import Any, Optional
import httpx
from loguru import logger
from src.config import SpreadsheetConfig, FindBy, UpdateField
from src.cache import get_access_token_cache, get_user_info_cache, get_dept_info_cache


def _replace_placeholders(text: str, form_data: dict[str, Any]) -> str:
    """替换字符串中的占位符

    支持格式: {form_data:field_name} 或 {form_data:nested.field}

    Args:
        text: 包含占位符的字符串
        form_data: 表单数据

    Returns:
        替换后的字符串
    """
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


class SpreadsheetClient:
    """钉钉AI表格(Notable)客户端

    API文档:
    - 列出多行记录: https://open.dingtalk.com/document/development/api-notable-listrecords
    - 更新多行记录: https://open.dingtalk.com/document/development/api-noatable-updaterecords
    """

    def __init__(self, config: SpreadsheetConfig, app_key: str, app_secret: str):
        self.config = config
        self.app_key = app_key
        self.app_secret = app_secret
        self.operator_id = config.default_operator_id
        self.base_url = "https://api.dingtalk.com"
        self._access_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    async def get_process_instance(self, process_instance_id: str) -> dict[str, Any]:
        """获取审批实例详情
        
        API: https://open.dingtalk.com/document/development/obtains-the-details-of-a-single-approval-instance-pop
        
        Args:
            process_instance_id: 审批实例ID
            
        Returns:
            审批实例详情数据，包含表单组件值
        """
        access_token = await self._get_access_token()
        client = await self._get_client()
        
        # 策略1: 优先尝试 New API (v1.0)
        # 路径: /v1.0/workflow/processInstances/{processInstanceId}
        url_new = f"https://api.dingtalk.com/v1.0/workflow/processInstances"
        headers_new = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json"
        }
        params = {
            "processInstanceId": process_instance_id
        }
        
        try:
            response = await client.get(url_new, headers=headers_new, params=params)
            data= response.json()
            if data.get("success"):
                logger.info(f"成功获取审批实例详情: {data['result']}")
                return data["result"]
            logger.error(f"New API (v1.0) 获取审批实例详情失败: {data}")
            return data

        except Exception as e:
            logger.error(f"New API (v1.0) 请求异常: {e}")

    async def get_user_info(self, userid: str, language: str = "zh_CN", fetch_dept_details: bool = True) -> dict[str, Any]:
        """获取用户详细信息（带缓存）

        API: https://open.dingtalk.com/document/orgapp-server/query-user-details

        Args:
            userid: 用户的userId
            language: 通讯录语言，zh_CN（默认）或 en_US
            fetch_dept_details: 是否获取部门详细信息（默认true）

        Returns:
            用户详细信息，包含：
            - userid: 用户ID
            - unionid: 用户统一ID
            - name: 姓名
            - avatar: 头像URL
            - statecode: 状态码
            - mobile: 手机号
            - email: 邮箱
            - dept_order_list: 部门排序列表
            - dept_id_list: 部门ID列表
            - dept_list: 部门详细信息列表（如果 fetch_dept_details=true）
            - position: 职位
            - telephone: 座机
            - workPlace: 工作地点
            - remark: 备注
            - org_email_type: 企业邮箱类型
            - senior: 是否是高管
            - boss: 是否是管理员
            - admin: 是否是超级管理员
            - real_authed: 是否实名认证
            - active: 是否激活
            - exclusive: 是否专属帐号
            - extattr: 扩展属性
        """
        # 尝试从缓存获取
        cache = get_user_info_cache()
        cache_key = f"user:{userid}:lang:{language}"
        cached_info = cache.get(cache_key)

        if cached_info:
            logger.info(f"从缓存获取用户信息: userid={userid}, name={cached_info.get('name')}")
            return cached_info

        # 缓存未命中，调用API获取
        logger.debug(f"缓存未命中，调用API获取用户信息: userid={userid}")
        access_token = await self._get_access_token()
        client = await self._get_client()

        # 获取用户基本信息
        url = "https://oapi.dingtalk.com/topapi/v2/user/get"
        params = {"access_token": access_token}
        data = {"userid": userid, "language": language}

        try:
            response = await client.post(url, params=params, json=data)
            result = response.json()

            if result.get("errcode") != 0:
                logger.error(f"获取用户信息失败: {result}")
                return {}

            user_info = result.get("result", {})
            logger.info(f"成功获取用户信息: userid={userid}, name={user_info.get('name')}")

            # 如果需要获取部门详细信息
            if fetch_dept_details and user_info.get("dept_id_list"):
                dept_list = []
                for dept_id in user_info.get("dept_id_list", []):
                    dept_info = await self._get_dept_info(dept_id, access_token, client)
                    if dept_info:
                        dept_list.append(dept_info)
                user_info["dept_list"] = dept_list

            # 存入缓存
            cache.set(cache_key, user_info)
            logger.debug(f"用户信息已缓存: userid={userid}")

            return user_info

        except Exception as e:
            logger.error(f"获取用户信息异常: {e}")
            return {}

    async def _get_dept_info(self, dept_id: str, access_token: str, client: httpx.AsyncClient) -> dict[str, Any]:
        """获取部门详细信息（带缓存）

        API: https://open.dingtalk.com/document/orgapp-server/query-department-details0

        Args:
            dept_id: 部门ID
            access_token: 访问令牌
            client: HTTP客户端

        Returns:
            部门详细信息，包含：
            - dept_id: 部门ID
            - name: 部门名称
            - parent_id: 父部门ID
            - create_dept_group: 是否创建部门群
            - auto_add_user: 是否自动加入部门群
            - auto_approve_apply: 是否自动批准加入
            - source_identifier: 来源标识
        """
        # 尝试从缓存获取
        cache = get_dept_info_cache()
        cache_key = f"dept:{dept_id}"
        cached_info = cache.get(cache_key)

        if cached_info:
            logger.debug(f"从缓存获取部门信息: dept_id={dept_id}, name={cached_info.get('name')}")
            return cached_info

        # 缓存未命中，调用API获取
        logger.debug(f"缓存未命中，调用API获取部门信息: dept_id={dept_id}")

        # 优先尝试新版API
        url_new = f"https://api.dingtalk.com/v1.0/contact/departments/{dept_id}"
        headers_new = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json"
        }

        try:
            response = await client.get(url_new, headers=headers_new)
            result = response.json()

            if result.get("success"):
                result_data = result.get("result", {})
                dept_info = {
                    "dept_id": dept_id,
                    "name": result_data.get("name"),
                    "parent_id": result_data.get("parent_id"),
                }
                logger.debug(f"成功获取部门信息(新版API): dept_id={dept_id}, name={dept_info.get('name')}")

                # 存入缓存
                cache.set(cache_key, dept_info)
                return dept_info

        except Exception as e:
            logger.debug(f"新版API获取部门信息失败，尝试旧版API: {e}")

        # 降级到旧版API
        url_legacy = "https://oapi.dingtalk.com/topapi/v2/department/get"
        params = {"access_token": access_token}
        # 注意：dept_id 需要转换为数字类型
        try:
            dept_id_number = int(dept_id)
        except (ValueError, TypeError):
            logger.warning(f"部门ID格式错误: {dept_id}")
            return {}

        data = {
            "dept_id": dept_id_number,
            "language": "zh_CN"  # 明确指定中文，获取中文名称
        }

        try:
            response = await client.post(url_legacy, params=params, json=data)
            result = response.json()

            if result.get("errcode") == 0:
                dept_result = result.get("result", {})
                dept_info = {
                    "dept_id": dept_id,
                    "name": dept_result.get("name"),
                    "parent_id": dept_result.get("parent_id"),
                    "auto_add_user": dept_result.get("auto_add_user"),
                    "create_dept_group": dept_result.get("create_dept_group"),
                    "org_dept_owner": dept_result.get("org_dept_owner"),
                }
                logger.debug(f"成功获取部门信息(旧版API): dept_id={dept_id}, name={dept_info.get('name')}")

                # 存入缓存
                cache.set(cache_key, dept_info)
                return dept_info
            else:
                errcode = result.get("errcode")
                errmsg = result.get("errmsg", "未知错误")
                logger.warning(f"获取部门信息失败: dept_id={dept_id}, errcode={errcode}, errmsg={errmsg}")
                return {}

        except Exception as e:
            logger.warning(f"获取部门信息异常: dept_id={dept_id}, error={e}")
            return {}


    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _get_access_token(self) -> str:
        """获取access_token（带缓存）"""
        # 尝试从缓存获取
        cache = get_access_token_cache()
        cached_token = cache.get("access_token")

        if cached_token:
            logger.debug("从缓存获取access_token")
            return cached_token

        # 缓存未命中，调用API获取
        logger.debug("缓存未命中，调用API获取access_token")
        client = await self._get_client()
        url = f"{self.base_url}/v1.0/oauth2/accessToken"
        data = {
            "appKey": self.app_key,
            "appSecret": self.app_secret,
        }

        response = await client.post(url, json=data)
        result = response.json()

        # 新版API成功时直接返回accessToken，不一定有errcode
        # 或者 errcode 为 0
        if "accessToken" in result:
             token = result["accessToken"]
             # 存入缓存
             cache.set("access_token", token)
             logger.debug("成功获取并缓存access_token")
             return token

        if result.get("errcode") != 0:
            logger.error(f"获取access_token失败: {result}")
            raise Exception(f"获取access_token失败: {result}")

        token = result["accessToken"]
        cache.set("access_token", token)
        logger.debug("成功获取并缓存access_token")
        return token

    async def list_records(
        self,
        sheet_id: Optional[str] = None,
        base_id: Optional[str] = None,
        filter_field: Optional[str] = None,
        filter_value: Optional[Any] = None,
        max_results: int = 100
    ) -> list[dict[str, Any]]:
        """列出多行记录

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选，覆盖默认配置)
            filter_field: 筛选字段名（可选）
            filter_value: 筛选值（可选，与filter_field配合使用）
            max_results: 最大返回数量

        Returns:
            记录列表，每条记录包含 recordId 和 fields
        """
        access_token = await self._get_access_token()
        target_sheet = sheet_id or self.config.default_sheet_id
        target_base = base_id or self.config.base_id

        if not target_base:
            raise ValueError("未配置base_id，且未在调用中指定")

        url = f"{self.base_url}/v1.0/notable/bases/{target_base}/sheets/{target_sheet}/records/list"

        headers = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json",
        }
        params = {
            "operatorId": self.operator_id,
        }
        # 构建请求体
        body: dict[str, Any] = {
            "maxResults": max_results,
        }

        # 添加筛选条件
        if filter_field and filter_value is not None:
            body["filter"] = {
                "combination": "and",
                "conditions": [
                    {
                        "field": filter_field,
                        "operator": "equal",
                        "value": [filter_value],
                    }
                ],
            }

        client = await self._get_client()
        response = await client.post(url, headers=headers, json=body, params=params)
        result = response.json()

        if result.get("records", None) is None:
            logger.error(f"列出记录失败: {result}")
            raise Exception(f"列出记录失败: {result}")

        records = result.get("records", [])
        logger.info(f"成功获取 {len(records)} 条记录 (sheet={target_sheet})")
        return records

    async def find_record_by_value(
        self,
        sheet_id: Optional[str],
        base_id: Optional[str],
        field_name: str,
        search_value: Any
    ) -> Optional[dict[str, Any]]:
        """根据字段值查找记录

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选)
            field_name: 字段名
            search_value: 要查找的值

        Returns:
            找到的记录（包含recordId和fields），未找到返回None
        """
        # 使用filter参数直接筛选
        records = await self.list_records(sheet_id, base_id=base_id, filter_field=field_name, filter_value=search_value)

        if not records:
            logger.warning(f"未找到匹配记录: 字段={field_name}, 值={search_value}")
            return None

        # 返回第一条匹配记录
        record = records[0]
        logger.info(f"找到匹配记录: recordId={record.get('recordId')}, 字段={field_name}, 值={search_value}")
        return record

    async def update_records(
        self,
        sheet_id: Optional[str],
        base_id: Optional[str],
        records: list[dict[str, Any]],
        operator_id: Optional[str] = None
    ) -> bool:
        """更新多行记录

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选)
            records: 要更新的记录列表
                [{
                    "recordId": "xxx",
                    "fields": {
                        "字段名1": "值1",
                        "字段名2": "值2"
                    }
                }]
            operator_id: 操作者ID（优先使用此值，如果为None则使用配置中的默认值）

        Returns:
            是否成功
        """
        access_token = await self._get_access_token()
        target_sheet = sheet_id or self.config.default_sheet_id
        target_base = base_id or self.config.base_id

        if not target_base:
            raise ValueError("未配置base_id，且未在调用中指定")

        url = f"{self.base_url}/v1.0/notable/bases/{target_base}/sheets/{target_sheet}/records"

        headers = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json",
        }

        body = {
            "records": records,
        }

        # 构建查询参数：优先使用传入的operator_id，否则使用配置中的默认值
        final_operator_id = operator_id or self.config.default_operator_id
        params = {
            "operatorId": self.operator_id,
        }
        if final_operator_id:
            params["operatorId"] = final_operator_id

        client = await self._get_client()
        response = await client.put(url, headers=headers, json=body, params=params)
        result = response.json()

        # 检查错误：只有明确存在 errcode 且不为 0 时才认为是错误
        if result.get("value") is None:
            logger.error(f"批量更新记录失败: {result}")
            return False

        # 成功响应格式: {"value": [{"id": "xxx"}, ...]}
        updated_ids = [item.get("id") for item in result.get("value", [])]
        logger.info(f"成功更新 {len(updated_ids)} 条记录")
        return True

    async def add_records(
        self,
        sheet_id: Optional[str],
        base_id: Optional[str],
        records: list[dict[str, Any]],
        operator_id: Optional[str] = None
    ) -> list[str]:
        """添加多行记录

        API: https://open.dingtalk.com/document/development/api-notable-insertrecords

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选)
            records: 要添加的记录列表
                [{
                    "fields": {
                        "字段名1": "值1",
                        "字段名2": "值2"
                    }
                }]
            operator_id: 操作者ID（优先使用此值，如果为None则使用配置中的默认值）

        Returns:
            添加成功的记录ID列表
        """
        access_token = await self._get_access_token()
        target_sheet = sheet_id or self.config.default_sheet_id
        target_base = base_id or self.config.base_id

        if not target_base:
            raise ValueError("未配置base_id，且未在调用中指定")

        url = f"{self.base_url}/v1.0/notable/bases/{target_base}/sheets/{target_sheet}/records"

        headers = {
            "x-acs-dingtalk-access-token": access_token,
            "Content-Type": "application/json",
        }

        body = {
            "records": records,
        }

        # 调试：显示将要发送的数据
        logger.debug(f"添加记录请求体: {json.dumps(body, ensure_ascii=False)}")

        # 构建查询参数：优先使用传入的operator_id，否则使用配置中的默认值
        final_operator_id = operator_id or self.config.default_operator_id
        params = {
            "operatorId": self.operator_id,
        }
        if final_operator_id:
            params["operatorId"] = final_operator_id

        client = await self._get_client()
        response = await client.post(url, headers=headers, json=body, params=params)
        result = response.json()

        # 详细的错误日志
        logger.debug(f"添加记录 API 响应: {result}")

        # 检查错误：只有明确存在 errcode 且不为 0 时才认为是错误
        if "errcode" in result and result.get("errcode") != 0:
            logger.error(f"添加记录失败: {result}")
            raise Exception(f"添加记录失败: {result}")

        # 检查 HTTP 状态码
        if response.status_code >= 400:
            logger.error(f"添加记录 HTTP 错误: {response.status_code}, 响应: {result}")
            raise Exception(f"添加记录 HTTP 错误 {response.status_code}: {result}")

        # 成功响应格式: {"value": [{"id": "xxx"}, ...]}
        added_ids = [item.get("id") for item in result.get("value", [])]
        logger.info(f"成功添加 {len(added_ids)} 条记录")
        return added_ids

    async def process_add_actions(
        self,
        sheet_id: Optional[str],
        base_id: Optional[str],
        updates: list[UpdateField],
        form_data: dict[str, Any],
        operator_id: Optional[str] = None
    ) -> bool:
        """执行新增操作

        根据配置添加一条新记录

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选)
            updates: 字段配置列表
            form_data: 审批表单数据
            operator_id: 操作者ID（可选，用于AI表格API）

        Returns:
            是否成功
        """
        # 构建新增字段
        add_fields: dict[str, Any] = {}
        for update in updates:
            # 确定字段值
            if update.timestamp:
                value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif update.value:
                # 支持 value 中的占位符替换
                value = _replace_placeholders(update.value, form_data)
            elif update.form_field:
                # 检查 form_field 是否包含占位符
                if "{form_data:" in update.form_field:
                    # 包含占位符，进行替换
                    value = _replace_placeholders(update.form_field, form_data)
                else:
                    # 直接从表单数据中获取
                    value = form_data.get(update.form_field, "")
            else:
                logger.warning(f"字段配置缺少value或form_field: {update}")
                continue

            add_fields[update.field_name] = value

        if not add_fields:
            logger.warning("没有有效的新增字段")
            return False

        # 执行新增
        try:
            added_ids = await self.add_records(sheet_id, base_id, [
                {
                    "fields": add_fields,
                }
            ], operator_id=operator_id)

            if added_ids:
                logger.info(f"记录新增成功: recordId={added_ids[0]}, 字段={list(add_fields.keys())}")
                return True
            return False

        except Exception as e:
            logger.error(f"新增记录失败: {e}")
            return False

    async def process_update_actions(
        self,
        sheet_id: Optional[str],
        base_id: Optional[str],
        find_by: FindBy,
        updates: list[UpdateField],
        form_data: dict[str, Any],
        operator_id: Optional[str] = None
    ) -> bool:
        """执行更新操作

        根据配置查找记录并更新指定的字段

        Args:
            sheet_id: 数据表ID或名称
            base_id: 基础表格ID (可选)
            find_by: 查找条件
            updates: 更新配置列表
            form_data: 审批表单数据
            operator_id: 操作者ID（可选，用于AI表格API）

        Returns:
            是否成功
        """
        # 从表单数据中获取查找值
        search_value = form_data.get(find_by.form_field)
        if not search_value:
            logger.error(f"表单数据中未找到查找字段: {find_by.form_field}")
            return False

        # 查找匹配记录
        record = await self.find_record_by_value(sheet_id, base_id, find_by.field_name, search_value)
        if record is None:
            logger.error(f"未找到匹配的记录: 字段={find_by.field_name}, 值={search_value}")
            return False

        record_id = record.get("id")
        original_fields = record.get("fields", {})

        # 构建更新字段
        update_fields: dict[str, Any] = {}
        for update in updates:
            # 确定更新值
            if update.timestamp:
                value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            elif update.value:
                # 支持 value 中的占位符替换
                value = _replace_placeholders(update.value, form_data)
            elif update.form_field:
                # 检查 form_field 是否包含占位符
                if "{form_data:" in update.form_field:
                    # 包含占位符，进行替换
                    value = _replace_placeholders(update.form_field, form_data)
                else:
                    # 直接从表单数据中获取
                    value = form_data.get(update.form_field, "")
            else:
                logger.warning(f"更新配置缺少value或form_field: {update}")
                continue

            update_fields[update.field_name] = value

        if not update_fields:
            logger.warning("没有有效的更新字段")
            return False

        # 执行更新
        success = await self.update_records(sheet_id, base_id, [
            {
                "id": record_id,
                "fields": update_fields,
            }
        ], operator_id=operator_id)

        if success:
            logger.info(f"记录更新成功: recordId={record_id}, 更新字段={list(update_fields.keys())}")
        return success

    async def get_failed_events(self) -> dict[str, Any]:
        """获取推送失败的事件列表

        API: https://open.dingtalk.com/document/call_back/get_call_back_failed_result

        用于获取钉钉推送失败到回调地址的事件。当网络故障或服务不可用时，
        钉钉会重试推送，但也可以通过此接口主动拉取失败的事件。

        Returns:
            失败事件列表，包含：
            - failed_list: 失败事件列表
            - has_more: 是否还有更多失败事件
            - corpid: 企业ID
        """
        access_token = await self._get_access_token()
        client = await self._get_client()

        url = "https://oapi.dingtalk.com/call_back/get_call_back_failed_result"
        params = {"access_token": access_token}

        logger.debug("获取推送失败的事件列表...")

        try:
            response = await client.get(url, params=params)
            result = response.json()

            if result.get("errcode") != 0:
                logger.error(f"获取失败事件列表失败: {result}")
                return {
                    "failed_list": [],
                    "has_more": False,
                    "error": result.get("errmsg", "Unknown error")
                }

            failed_list = result.get("failed_list", [])
            has_more = result.get("has_more", False)
            corpid = result.get("corpid", "")

            logger.info(f"获取到 {len(failed_list)} 个推送失败的事件, has_more={has_more}")

            # 详细日志
            for i, failed_event in enumerate(failed_list):
                event_type = list(failed_event.keys())[0] if failed_event else "unknown"
                logger.debug(f"  [{i + 1}] 事件类型: {event_type}")

            return {
                "failed_list": failed_list,
                "has_more": has_more,
                "corpid": corpid,
                "errcode": result.get("errcode"),
                "errmsg": result.get("errmsg"),
            }

        except Exception as e:
            logger.error(f"获取失败事件列表异常: {e}")
            return {
                "failed_list": [],
                "has_more": False,
                "error": str(e)
            }

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            logger.debug("HTTP客户端已关闭")
