# GuangHeng P2 发布说明

版本：Backend 1.2.0 / Flutter 1.2.0+4

## 本次范围

- 新增 Solarbank 4 E5000 Pro、Solarbank Max AC / XE AC、Solarbank Max / XE 独立 Profile。
- 对齐 Anker SOLIX Official Integration 的正式实体后缀和储能控制能力。
- 新增通用储能控制方案接口；继续使用 Proposal、Approval、Safety、Execution、Readback Verification 完整闭环。
- 数字、选择和开关三类 Home Assistant 写服务均已具备统一执行与回读能力。
- 新增光伏阵列接口与移动端 MPPT / 组件级视图。
- 当前官方集成只提供聚合光伏功率时，接口返回明确诊断，不伪造 MPPT 或组件数据；未来 HA 暴露匹配实体后自动展示。

## 安全边界

- 新型号控制默认保持未验证并锁定；只有完成对应硬件实机回读验证后，才能在 Profile 中逐项标记为 verified。
- Solarbank 4 E5000 Pro 的 backup_reserve 保留既有已验证状态。
- battery_power_setpoint 被标记为回读不可靠，当前不开放执行。
- 控制权限、读写能力、范围、步进、实时观察、设备在线、用户审批和回读验证均未降低。

## 不在本次范围

- 厂商工单、售后流转和厂商远程诊断闭环。
- 在官方 Integration 未提供数据时推算或伪造组件级发电量。

## 验证结果

- Backend：123 tests passed。
- Flutter：`flutter analyze` 无问题，8 tests passed。
