# GuangHeng P0.5 部署说明

版本：Backend 1.0.2 / Flutter 1.0.1+2

## 本次新增

- 系统健康诊断：检查 Home Assistant、Anker SOLIX Integration、设备在线状态、能力可用性与控制验证状态。
- 恢复建议：异常时给出可执行的排查顺序；未验证控制能力保持只读，不降低 Safety 要求。
- 关键负载配置：支持新增、启停和删除关键负载，并汇总启用负载的额定功率。
- 电池洞察：使用关键负载总功率计算关键负载预计支撑时长；未配置时明确返回空值，不伪造结果。

## 新增接口

- `GET /api/v1/health/summary`
- `GET /api/v1/critical-loads`
- `POST /api/v1/critical-loads`
- `PATCH /api/v1/critical-loads/{id}`
- `DELETE /api/v1/critical-loads/{id}`

## 部署

1. 上传 `guangheng-server-1.0.2.tar`、`docker-compose.yml` 和服务器本地 `.env`。
2. 执行 `docker load -i guangheng-server-1.0.2.tar`。
3. 执行 `docker compose up -d --force-recreate`。
4. 检查 `/health`、`/api/v1/health/summary` 和 `/api/v1/critical-loads`。

数据库目录继续挂载到 `./storage`，升级不会主动删除原有 SQLite 数据。请勿把 `.env` 或 Home Assistant Token 放入部署包。

## 验收结果

- Backend：112 项 pytest 通过。
- Flutter：静态检查通过，8 项测试通过。
- 健康诊断、关键负载与电池洞察接口已完成真实请求冒烟检查。
