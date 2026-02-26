# 钉钉审批事件监听系统

监听钉钉审批事件，在审批通过后自动更新钉钉AI表格(Notable/多维表格)数据的自动化工具。

## 功能特点

- 监听钉钉审批通过事件（使用Stream模式，无需公网服务器）
- 根据审批表单数据查找AI表格中的匹配记录
- 自动更新指定字段的数据
- 支持多个审批流程配置
- 灵活的数据映射配置
- 完整的日志记录和错误处理

## 系统要求

- Python 3.13+
- 钉钉企业内部应用（需要AppKey和AppSecret）
- 钉钉AI表格/多维表格(Notable)

## 安装

1. 克隆项目到本地

2. 安装依赖
```bash
pip install -e .
```

或手动安装依赖：
```bash
pip install dingtalk-stream pyyaml loguru httpx pydantic
```

## 配置

1. 复制配置文件模板：
```bash
cp config/config.yaml config/config.yaml.local
```

2. 编辑配置文件 `config/config.yaml`：

```yaml
# 钉钉应用配置
dingtalk:
  app_key: "your_app_key"              # 在钉钉开放平台获取
  app_secret: "your_app_secret"        # 在钉钉开放平台获取

# AI表格配置
spreadsheet:
  default_operator_id: "your_operator_id"  # 操作者ID（必填，见下方获取方式）
  # base_id: "your_base_id"                  # (可选) AI表格(Notable)的Base ID
  default_sheet_id: "sheet1"                # (可选) 默认数据表ID或名称

# 审批流程配置
approvals:
  - name: "请假审批"
    template_id: "proc_leave_approval" # 审批流程的模板ID
    enabled: true
    actions:
      - type: "update_spreadsheet"
        base_id: "your_base_id"        # AI表格(Notable)的Base ID
        sheet_id: "sheet1"             # 数据表ID或名称
        # 查找条件：根据员工工号查找记录
        find_by:
          field_name: "员工工号"        # AI表格中的字段名
          form_field: "employee_id"    # 审批表单中的字段名
        # 更新内容
        updates:
          - field_name: "请假天数"      # AI表格中的字段名
            form_field: "leave_days"   # 使用审批表单中的值
          - field_name: "请假理由"      # AI表格中的字段名
            form_field: "leave_reason" # 使用审批表单中的值
          - field_name: "审批状态"      # AI表格中的字段名
            value: "已审批"             # 使用固定值
          - field_name: "审批时间"      # AI表格中的字段名
            timestamp: true            # 自动添加当前时间戳
```

## 获取必要信息

### 1. 获取AppKey和AppSecret

1. 登录 [钉钉开放平台](https://open.dingtalk.com/)
2. 进入"应用开发" > "企业内部应用"
3. 创建或选择已有应用
4. 在"应用信息"页面查看AppKey和AppSecret

### 2. 获取操作者ID (operator_id)

**重要**：AI表格 API 要求提供操作者ID。有以下获取方式：

1. **获取自己的 unionId**：
   - 登录 [钉钉开放平台](https://open.dingtalk.com/)
   - 使用 [获取用户信息 API](https://open.dingtalk.com/document/orgapp-server/query-users-in-user-group) 或通过事件数据获取
   - 在审批事件中通常为 `operatorUnionId` 字段

2. **通过事件自动获取**：
   - 系统会自动从审批事件中提取 `operatorUnionId`、`operator` 或 `originatorUnionId`
   - 如果事件中包含操作者ID，将优先使用事件中的ID

3. **配置默认值**：
   - 在 `.env` 文件中设置 `DINGTALK_OPERATOR_ID` 作为后备
   - 或直接在 `config.yaml` 中的 `spreadsheet.default_operator_id` 设置

### 3. 获取审批流程模板ID

审批通过后，事件数据中会包含 `process_code` 字段，这就是审批流程的模板ID。

### 4. 获取AI表格base_id

AI表格的base_id可以从URL中获取：
```
https://sbjfpdctc8c.o.dingtalk.com/notable/base/[base_id]/...
```

或者在钉钉AI表格中，通过浏览器开发者工具查看网络请求找到base_id。

### 5. 获取数据表ID和字段名

- 数据表ID或名称：在AI表格界面中，每个数据表都有唯一的ID，也可以直接使用数据表名称
- 字段名：在AI表格中显示的列标题，如"员工工号"、"请假天数"等

### 5. 获取表单字段名

审批表单的字段名可以通过事件日志查看，或者在钉钉管理后台的审批表单设计器中查看字段标识。

## 运行

```bash
python main.py
```

程序将：
1. 加载配置文件
2. 初始化日志系统
3. 连接到钉钉Stream服务
4. 开始监听审批事件

## 日志

日志文件位置：`logs/app.log`

日志会记录：
- 收到的审批事件
- 表单数据提取结果
- AI表格查找和更新操作
- 错误和异常信息

## 配置说明

### AI表格(Notable)数据结构

AI表格使用记录式结构，类似于数据库表：
- **Base**: 一个AI表格文档
- **Sheet**: 数据表
- **Field**: 字段(列)
- **Record**: 记录(行)

每条记录包含：
- `recordId`: 记录唯一标识
- `fields`: 字段值映射 (Map<String, Any>)

### 审批事件类型

系统监听以下事件：
- `bpms_task_change`: 审批任务状态变更
- `bpms_instance_change`: 审批实例状态变更

只有当 `result=agree`（审批通过）时才会触发更新操作。

### find_by 配置

指定如何在AI表格中查找要更新的记录：

```yaml
find_by:
  field_name: "员工工号"      # AI表格中的字段名
  form_field: "employee_id"   # 审批表单中的字段名
```

系统会：
1. 从审批表单中获取 `employee_id` 字段的值
2. 在AI表格的"员工工号"字段中查找匹配的记录
3. 找到后更新该记录的其他字段

### updates 配置

指定要更新的字段：

```yaml
updates:
  - field_name: "请假天数"     # AI表格中的字段名
    form_field: "leave_days"  # 使用审批表单中的值
  - field_name: "审批状态"     # AI表格中的字段名
    value: "已审批"            # 使用固定值
  - field_name: "审批时间"     # AI表格中的字段名
    timestamp: true           # 使用当前时间戳
```

## API 参考

### 使用的钉钉API

- **列出多行记录**: `POST /v1.0/notable/bases/{baseId}/sheets/{sheetId}/records/list`
  - 文档: https://open.dingtalk.com/document/development/api-notable-listrecords

- **更新多行记录**: `POST /v1.0/notable/bases/{baseId}/sheets/{sheetId}/records/batchUpdate`
  - 文档: https://open.dingtalk.com/document/development/api-noatable-updaterecords

## 目录结构

```
dingtalk-approve/
├── main.py                    # 程序入口
├── pyproject.toml             # 项目配置
├── README.md                  # 说明文档
├── config/
│   └── config.yaml            # 配置文件
├── src/
│   ├── __init__.py
│   ├── config.py              # 配置管理
│   ├── stream_client.py       # Stream客户端
│   └── spreadsheet_client.py  # AI表格操作
├── scripts/                   # 自定义脚本目录
└── logs/                      # 日志目录
```

## 常见问题

### 1. 程序启动后没有反应？

检查：
- AppKey和AppSecret是否正确
- 网络连接是否正常
- 查看日志文件中的错误信息

### 2. 收到审批事件但没有更新表格？

检查：
- 审批流程的template_id是否配置正确
- AI表格的base_id和sheet_id是否正确
- 字段名是否与AI表格中的实际字段名一致
- 查看日志中的详细错误信息

### 3. 如何调试？

将日志级别改为DEBUG：
```yaml
logging:
  level: "DEBUG"
```

### 4. 支持哪些操作类型？

目前支持：
- `update_spreadsheet`: 更新AI表格记录

未来计划支持：
- `webhook`: 发送HTTP请求
- `shell`: 执行Shell命令
- `python`: 执行Python脚本

### 5. AI表格和传统表格有什么区别？

- **传统表格**: 使用单元格定位，如 A1, B1, C2
- **AI表格(Notable)**: 使用记录式结构，类似于数据库表，通过字段名和记录ID操作

本项目专门针对AI表格(Notable/多维表格)设计，不支持传统电子表格。

## 许可证

MIT License
