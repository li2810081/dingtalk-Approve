"""配置管理模块"""
import os
import re
from pathlib import Path
from typing import Optional
import yaml
from pydantic import BaseModel, Field
from loguru import logger
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class DingTalkConfig(BaseModel):
    """钉钉应用配置"""
    app_key: str
    app_secret: str


class SpreadsheetConfig(BaseModel):
    """AI表格(Notable/多维表格)配置"""
    base_id: Optional[str] = None
    default_sheet_id: Optional[str] = None
    default_operator_id: Optional[str] = None  # 默认操作者ID（用于AI表格API）


class FindBy(BaseModel):
    """查找条件配置

    用于在AI表格中查找匹配的记录
    """
    field_name: str  # AI表格中的字段名
    form_field: str  # 审批表单中的字段名


class UpdateField(BaseModel):
    """更新字段配置

    用于更新AI表格中的字段值
    """
    field_name: str  # AI表格中的字段名
    form_field: Optional[str] = None  # 从审批表单中取值
    value: Optional[str] = None  # 使用固定值
    timestamp: bool = False  # 自动添加时间戳


class Action(BaseModel):
    """操作配置"""
    type: str
    base_id: Optional[str] = None
    sheet_id: Optional[str] = None
    find_by: Optional[FindBy] = None
    updates: list[UpdateField] = Field(default_factory=list)


class Approval(BaseModel):
    """审批流程配置"""
    name: str
    template_id: str
    enabled: bool = True
    actions: list[Action] = Field(default_factory=list)


class HrmEvent(BaseModel):
    """人事变动事件配置"""
    name: str  # 事件名称，如：离职事件、入职事件等
    change_type: int  # 人事变动类型：1:入职 2:转正 3:调岗 4:离职 8:晋升
    enabled: bool = True
    actions: list[Action] = Field(default_factory=list)


class Execution(BaseModel):
    """执行配置"""
    timeout: int = 300
    retry_times: int = 2
    retry_interval: int = 5


class LoggingConfig(BaseModel):
    """日志配置"""
    level: str = "INFO"
    file: str = "./logs/app.log"
    rotation: str = "100 MB"
    retention: str = "30 days"


class Config(BaseModel):
    """总配置"""
    dingtalk: DingTalkConfig
    spreadsheet: SpreadsheetConfig = Field(default_factory=SpreadsheetConfig)
    approvals: list[Approval] = Field(default_factory=list)
    hrm_events: list[HrmEvent] = Field(default_factory=list)  # 人事变动事件配置
    execution: Execution = Field(default_factory=Execution)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _replace_env_vars(content: str) -> str:
    """替换配置中的环境变量占位符 ${VAR}"""
    # 匹配 ${VAR} 格式
    pattern = re.compile(r'\$\{([A-Z0-9_]+)\}')
    
    def replace(match):
        env_var = match.group(1)
        value = os.getenv(env_var)
        if value is None:
            logger.warning(f"未找到环境变量: {env_var}")
            return match.group(0)  # 保持原样
        return value
        
    return pattern.sub(replace, content)


def load_config(config_path: str = "config/config.yaml") -> Config:
    """加载配置文件"""
    config_file = Path(config_path)

    if not config_file.exists():
        logger.error(f"配置文件不存在: {config_path}")
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 替换环境变量
    content = _replace_env_vars(content)
    
    config_data = yaml.safe_load(content)

    return Config(**config_data)


def setup_logging(config: LoggingConfig):
    """配置日志系统"""
    logger.remove()  # 移除默认处理器

    log_file = Path(config.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # 控制台输出
    logger.add(
        sink=lambda msg: print(msg, end=""),
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=config.level,
    )

    # 文件输出
    logger.add(
        sink=config.file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=config.level,
        rotation=config.rotation,
        retention=config.retention,
        encoding="utf-8",
    )

    logger.info("日志系统初始化完成")
