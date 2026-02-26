# Docker 部署指南

本文档介绍如何使用 Docker 部署钉钉审批事件监听系统。

## 前置要求

- Docker (版本 20.10 或以上)
- Docker Compose (版本 2.0 或以上)

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 文件并重命名为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入您的钉钉应用信息：

```env
DINGTALK_APP_KEY=your_app_key_here
DINGTALK_APP_SECRET=your_app_secret_here
DINGTALK_OPERATOR_ID=your_operator_id_here
```

### 2. 配置审批流程

编辑 `config/config.yaml` 文件，配置您需要监听的审批流程和人事变动事件。

### 3. 构建并启动服务

```bash
# 构建镜像
docker-compose build

# 启动服务（后台运行）
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 4. 停止服务

```bash
# 停止服务
docker-compose stop

# 停止并删除容器
docker-compose down
```

## 常用命令

```bash
# 查看运行状态
docker-compose ps

# 查看实时日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 进入容器
docker-compose exec dingtalk-approve bash

# 重新构建镜像（代码更新后）
docker-compose up -d --build
```

## 目录结构

```
.
├── Dockerfile              # Docker 镜像构建文件
├── docker-compose.yml      # Docker Compose 配置文件
├── .env                    # 环境变量文件（需自行创建）
├── .env.example            # 环境变量示例文件
├── config/                 # 配置文件目录（挂载到容器）
│   └── config.yaml
├── logs/                   # 日志文件目录（挂载到容器）
├── src/                    # 源代码
├── main.py                 # 程序入口
└── pyproject.toml          # 项目依赖
```

## 配置热重载

配置文件 `config/config.yaml` 已挂载到容器中，修改后会自动生效（程序会监听文件变化并自动重载配置）。

## 故障排查

### 查看容器日志

```bash
docker-compose logs -f dingtalk-approve
```

### 进入容器调试

```bash
docker-compose exec dingtalk-approve bash
```

### 检查环境变量

```bash
docker-compose exec dingtalk-approve env | grep DINGTALK
```

### 重新构建镜像

如果代码有更新，需要重新构建镜像：

```bash
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 资源限制

如果需要限制容器资源使用，可以在 `docker-compose.yml` 中取消注释 `resources` 部分：

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
    reservations:
      cpus: '0.5'
      memory: 256M
```

## 生产环境建议

1. **使用 secrets 管理敏感信息**：不要将 `.env` 文件提交到版本控制
2. **设置日志轮转**：已配置日志文件最大为 10MB，保留 3 个文件
3. **配置健康检查**：已启用健康检查，每 30 秒检查一次
4. **使用外部日志收集**：建议使用 ELK 或其他日志收集方案
5. **配置重启策略**：默认为 `unless-stopped`，容器异常退出会自动重启
