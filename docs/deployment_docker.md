# GuangHeng Backend Docker 部署

本文档用于将 GuangHeng FastAPI Backend 1.3.1 部署到 Ubuntu 服务器
`43.155.204.194`。本阶段只部署核心 API，不部署 Hermes、不公开 MCP、不启用
Autonomy Scheduler，也不配置域名、HTTPS 或 Nginx。

## 1. 部署边界

- 对外临时测试地址：`http://43.155.204.194:8000`
- 容器：`guangheng-api`
- 镜像：`guangheng-server:1.3.1`
- API 进程：单个 Uvicorn worker
- SQLite：宿主机 `/opt/guangheng/server/storage/guangheng.db`
- Scheduler：继续使用 `config/autonomy_policy.yaml` 中的 `enabled: false`
- Hermes：本阶段不部署，相关端点允许返回不可用
- MCP：本阶段不启动，也不开放 8001

## 2. 服务器准备

确认 Ubuntu 已安装 Docker Engine 与 Docker Compose Plugin：

```bash
docker version
docker compose version
uname -m
```

本机导出的首版镜像平台为 `linux/amd64`；服务器应显示 `x86_64`。如果目标服务器
是 ARM64，必须重新构建对应平台镜像，不能直接使用本 tar。

创建部署目录，并让镜像内固定 UID/GID `10001:10001` 的非 root 用户能够写入
SQLite 目录：

```bash
sudo mkdir -p /opt/guangheng/server/storage
sudo chown -R 10001:10001 /opt/guangheng/server/storage
cd /opt/guangheng/server
```

## 3. 需要上传的文件

将以下文件上传到 `/opt/guangheng/server`：

```text
guangheng-server-1.3.1.tar
docker-compose.yml
.env
```

不要上传开发机的 `storage/guangheng.db`，除非后续明确安排数据迁移。首次启动时，
应用会通过 `Base.metadata.create_all` 创建空数据库和表。

`.env` 必须只在服务器本地创建或通过安全通道上传，权限建议设为仅部署用户可读：

```bash
chmod 600 .env
```

至少检查以下实际配置：

```dotenv
APP_NAME=GuangHeng Server
APP_VERSION=1.3.1
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
RELOAD=false

HA_URL=http://host.docker.internal:8123
HA_TOKEN=replace-with-home-assistant-long-lived-access-token

WEATHER_PROVIDER=open_meteo
WEATHER_BASE_URL=https://api.open-meteo.com/v1/forecast
WEATHER_TIMEOUT_SECONDS=10
WEATHER_CACHE_SECONDS=300

HERMES_BASE_URL=http://host.docker.internal:8642
HERMES_API_KEY=
HERMES_MODEL=hermes-agent
HERMES_TIMEOUT_SECONDS=120
```

不要把 Token 写入 Dockerfile、Compose、YAML 或镜像。Hermes 当前未部署，空的
`HERMES_API_KEY` 不会阻止核心 Backend 启动。

## 4. Home Assistant 网络

Compose 已配置：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

如果 Home Assistant 作为宿主机服务或使用 host network，服务器 `.env` 使用：

```dotenv
HA_URL=http://host.docker.internal:8123
```

容器中的 `127.0.0.1` 只代表容器自身，不能用来访问宿主机的 Home Assistant。

如果 Home Assistant 是普通 Docker bridge 容器，更推荐后续创建共享的私有 Docker
network，让 GuangHeng 通过 Home Assistant 的容器名访问；实施前应先核实现有 HA
Compose 和网络名称，不要猜测或硬编码。

## 5. 导入与启动

```bash
cd /opt/guangheng/server
docker load -i guangheng-server-1.3.1.tar
docker image inspect guangheng-server:1.3.1 --format '{{.RepoTags}} {{.Size}}'
docker compose up -d
docker compose ps
```

查看日志：

```bash
docker compose logs --tail=200 guangheng-api
docker compose logs -f guangheng-api
```

## 6. 验收

先在服务器本机检查健康和 OpenAPI：

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/openapi.json
```

再检查只读业务接口：

```bash
curl --fail http://127.0.0.1:8000/api/v1/energy/state
curl --fail http://127.0.0.1:8000/api/v1/strategy
curl --fail http://127.0.0.1:8000/api/v1/autonomy/status
```

最后从允许的外部测试终端检查：

```bash
curl --fail http://43.155.204.194:8000/health
curl --fail http://43.155.204.194:8000/openapi.json
```

这些验收请求都是只读操作，不会修改 Energy Runtime、Proposal、Approval 或
Execution。

## 7. 云安全组

腾讯云安全组临时允许：

- TCP 8000：Phase 3 开发测试使用，建议限制来源 IP。

不要开放：

- TCP 8001：MCP
- TCP 8642：Hermes Gateway
- TCP 8123：除非 Home Assistant 自身已有明确且安全的访问方案
- SQLite 文件或任何数据库端口
- Docker daemon 端口（2375/2376）

8000 是临时开发暴露。正式环境应改为通过 443 HTTPS 访问。

## 8. Flutter 开发测试

不要把服务器地址写死在 Dart 源码中。Android/iOS 开发测试使用：

```bash
flutter run --dart-define=GUANGHENG_API_BASE_URL=http://43.155.204.194:8000
```

公网明文 HTTP 只适用于当前开发阶段。iOS ATS 和 Android cleartext 限制应采用
最小范围的开发配置；不要永久开启全局 `NSAllowsArbitraryLoads=true`。正式
TestFlight/发布前必须启用 HTTPS。

## 9. 运维命令

```bash
cd /opt/guangheng/server
docker compose restart guangheng-api
docker compose stop
docker compose up -d
docker compose ps
docker compose logs --tail=200 guangheng-api
```

更新镜像时先导入新 tar，再执行 `docker compose up -d --force-recreate`。SQLite
数据位于宿主机挂载目录，重建容器不会删除数据库。执行任何数据库备份、恢复或
迁移前，应先停止 API 并单独制定数据操作方案。

## 10. 当前限制

- 没有域名、HTTPS、反向代理或访问限流。
- SQLite 与 Scheduler 的并发边界要求仅运行一个 API worker。
- Hermes 与 MCP 尚未服务器化，Agent 对话端点可能不可用。
- Home Assistant 实际部署网络仍需在服务器上核实。
- 生产发布前需要完成 HTTPS、最小暴露面、备份恢复与监控方案。

