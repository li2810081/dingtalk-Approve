"""钉钉AI表格(Notable/多维表格)操作模块

使用记录式API，而非传统的单元格(A1/B1)操作方式
"""
from datetime import datetime
from typing import Any, Optional
import httpx
from loguru import logger
from src.config import SpreadsheetConfig, FindBy, UpdateField


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


    async def _get_client(self) -> httpx.AsyncClient:
        """获取HTTP客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _get_access_token(self) -> str:
        """获取access_token"""
        if self._access_token:
            return self._access_token

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
             self._access_token = result["accessToken"]
             logger.debug("成功获取access_token")
             return self._access_token
             
        if result.get("errcode") != 0:
            logger.error(f"获取access_token失败: {result}")
            raise Exception(f"获取access_token失败: {result}")

        self._access_token = result["accessToken"]
        logger.debug("成功获取access_token")
        return self._access_token

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

        # 检查错误：只有明确存在 errcode 且不为 0 时才认为是错误
        if "errcode" in result and result.get("errcode") != 0:
            logger.error(f"添加记录失败: {result}")
            raise Exception(f"添加记录失败: {result}")

        # 成功响应格式: {"value": [{"id": "xxx"}, ...]}
        added_ids = [item.get("id") for item in result.get("value", [])]
        logger.info(f"成功添加 {len(added_ids)} 条记录")
        return added_ids

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
                value = update.value
            elif update.form_field:
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

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            logger.debug("HTTP客户端已关闭")
