"""钉钉审批事件监听系统 - 主程序入口"""
import asyncio
import signal
import sys
from loguru import logger

from src.config import load_config, setup_logging
from src.spreadsheet_client import SpreadsheetClient
from src.stream_client import create_stream_client
from src.config_watcher import ConfigWatcher


class Application:
    """应用程序主类 - 支持配置热重载"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path
        self.config = self._load_config()

        # 设置日志
        setup_logging(self.config.logging)

        # 创建AI表格客户端
        self.spreadsheet_client = SpreadsheetClient(
            config=self.config.spreadsheet,
            app_key=self.config.dingtalk.app_key,
            app_secret=self.config.dingtalk.app_secret,
        )

        # Stream客户端
        self.stream_client = None

        # 配置监听器
        self.config_watcher = None

        # 运行标志
        self._running = False
        self._stream_started = False

    def _load_config(self):
        """加载配置"""
        return load_config(self.config_path)

    async def _reload_config(self):
        """重载配置"""
        logger.info("正在重载配置...")
        try:
            # 重新加载配置
            new_config = self._load_config()

            # 更新日志配置
            setup_logging(new_config.logging)

            # 检查审批流程配置是否变化
            old_approvals = {a.template_id: a for a in self.config.approvals}
            new_approvals = {a.template_id: a for a in new_config.approvals}

            # 检查人事事件配置是否变化
            old_hrm_events = {e.change_type: e for e in self.config.hrm_events}
            new_hrm_events = {e.change_type: e for e in new_config.hrm_events}

            if old_approvals != new_approvals or old_hrm_events != new_hrm_events:
                logger.info("检测到配置变化，需要重启 Stream 客户端")
                await self._restart_stream_client(new_config)
            else:
                logger.info("配置未变化")

            # 更新配置
            self.config = new_config
            logger.info("配置重载完成")

        except Exception as e:
            logger.error(f"重载配置失败: {e}")
            raise

    async def _restart_stream_client(self, new_config):
        """重启 Stream 客户端"""
        if not self._stream_started:
            return

        logger.info("正在重启 Stream 客户端...")

        # 停止旧的 Stream 客户端
        if self.stream_client:
            try:
                # dingtalk_stream 没有 stop 方法，直接替换
                pass
            except Exception as e:
                logger.warning(f"停止 Stream 客户端时出错: {e}")

        # 创建新的 Stream 客户端
        self.stream_client = create_stream_client(new_config, self.spreadsheet_client)
        logger.info("Stream 客户端已重新创建")

    async def start(self):
        """启动应用程序"""
        logger.info("=" * 50)
        logger.info("钉钉事件监听系统启动中...")
        logger.info(f"配置文件: {self.config_path}")
        logger.info("=" * 50)

        # 显示配置信息
        enabled_approvals = [a for a in self.config.approvals if a.enabled]
        logger.info(f"配置的审批流程数量: {len(self.config.approvals)} (启用: {len(enabled_approvals)})")
        for approval in self.config.approvals:
            status = "✓ 启用" if approval.enabled else "✗ 禁用"
            logger.info(f"  [{status}] {approval.name}: {len(approval.actions)} 个操作")

        # 显示人事事件配置
        enabled_hrm_events = [e for e in self.config.hrm_events if e.enabled]
        logger.info(f"配置的人事变动事件数量: {len(self.config.hrm_events)} (启用: {len(enabled_hrm_events)})")
        for hrm_event in self.config.hrm_events:
            status = "✓ 启用" if hrm_event.enabled else "✗ 禁用"
            change_type_name = {
                1: "入职", 2: "转正", 3: "调岗", 4: "离职", 8: "晋升"
            }.get(hrm_event.change_type, f"类型{hrm_event.change_type}")
            logger.info(f"  [{status}] {hrm_event.name} ({change_type_name}): {len(hrm_event.actions)} 个操作")

        # 创建Stream客户端
        self.stream_client = create_stream_client(self.config, self.spreadsheet_client)

        # 启动配置监听器
        self.config_watcher = ConfigWatcher(self.config_path, self._reload_config)
        await self.config_watcher.start()

        self._running = True
        self._stream_started = True

        try:
            # 启动监听（阻塞运行）
            logger.info("=" * 50)
            logger.info("开始监听钉钉事件（审批事件 + 人事变动事件）...")
            logger.info("配置文件已开启热重载，修改 config/config.yaml 后自动生效")
            logger.info("按 Ctrl+C 停止程序")
            logger.info("=" * 50)

            await self.stream_client.start()

        except KeyboardInterrupt:
            logger.info("接收到中断信号，正在停止...")
        except Exception as e:
            logger.exception(f"运行时发生错误: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """停止应用程序"""
        if not self._running:
            return

        logger.info("正在停止应用程序...")
        self._running = False
        self._stream_started = False

        # 停止配置监听器
        if self.config_watcher:
            await self.config_watcher.stop()

        # 关闭AI表格客户端
        await self.spreadsheet_client.close()

        logger.info("应用程序已停止")


def signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"接收到信号: {signum}")
    sys.exit(0)


def main():
    """主函数"""
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 创建并启动应用
    app = Application()

    # 运行
    asyncio.run(app.start())


if __name__ == "__main__":
    main()
