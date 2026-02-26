# 使用官方 Python 3.13 slim 镜像
FROM python:3.13-slim

# 设置工作目录
WORKDIR /app

# 安装 uv 包管理器（使用 RUN 而非 CMD）
RUN pip install uv --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 先复制依赖文件，利用 Docker 缓存
COPY pyproject.toml uv.lock ./

# 安装项目依赖（--no-dev 表示不安装开发依赖）
RUN uv sync --frozen --no-dev

# 复制项目源码和配置文件
COPY src/ ./src/
COPY main.py ./
COPY config/ ./config/

# 设置环境变量（推荐合并 ENV 指令）
ENV PYTHONUNBUFFERED=1

# 创建日志目录
RUN mkdir -p /app/logs

# 暴露端口（可选，用于健康检查或调试）
EXPOSE 8080

# 使用非 root 用户运行应用（安全最佳实践）
RUN useradd --create-home appuser
USER appuser

# 启动命令：直接运行 main.py（uv 会自动处理虚拟环境）
CMD ["uv", "run", "main.py"]