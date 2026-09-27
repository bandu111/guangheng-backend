# GuangHeng P1 发布说明

版本：Backend 1.1.0 / Flutter 1.1.0+3

## 动态多设备与 Profile Catalog

- Discovery 从固定 Entity ID 改为 Profile 后缀匹配，可在一次 HA Observation 中发现多台设备。
- 当前 Catalog 覆盖 SOLIX 储能系列、Smart Plug Gen 2 与 Smart Meter Gen 2。
- SOLIX Smart Plug Gen 1 按官方 Integration 当前状态标记为 `official_integration_coming_soon`，不会伪装成可控制设备。
- Smart Plug Gen 2 要求官方 Integration 支持的固件 `0.0.8.4+`。

## HA Area 家庭负载

- 通过 Home Assistant WebSocket Registry 获取 Area、Device 与 Entity 归属。
- 使用当前 HA State 聚合空间功率，服务器实时读取，不依赖手机保持打开。
- 光伏、储能充放电、电网流向和相位明细不会重复计入区域负载总功率。
- 未分配 Area 的功率实体单独返回，便于用户修正 HA 配置。

## Smart Plug Gen 2 控制闭环

- 用户开关请求先创建 `PENDING` Proposal。
- 用户确认后仍需经过设备权限、在线状态、能力可用、Profile 验证、Freshness 和范围检查。
- 执行使用 HA `switch.turn_on/turn_off`，HTTP 200 不代表成功。
- 最终以开关 Entity 状态回读作为成功依据。
- 当前 Profile 的 `power_switch.verified=false`，在真实 Smart Plug Gen 2 完成开/关和回读测试前，Safety 会主动阻断写入。

## Smart Meter Gen 2 分项计量

- 支持主/副 CT 总有功功率、无功功率、功率因数、正反向电量。
- 支持 L1/L2/L3 有功功率、电流和电压。
- 字段缺失时保持为空，不用 0 伪造数据。

## 新增接口

- `GET /api/v1/devices/profiles/catalog`
- `GET /api/v1/devices/discover/bound`
- `POST /api/v1/devices/{device_id}/switch-proposals`
- `GET /api/v1/areas/load-view`
- `GET /api/v1/meters/{device_id}/insight`

## 验收

- Backend：118 项 pytest 通过。
- Flutter：静态检查通过，8 项组件测试通过。
- 本地 HA：动态 Solarbank 发现成功；HA Area Registry 读取成功；能源中心负载聚合为 2.5 kW。
- Smart Plug Gen 2：模拟验证了 Proposal、Safety 阻断、`switch.turn_on` 与状态回读代码路径；真实设备验证仍是开放控制前置条件。
