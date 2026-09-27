from sqlalchemy.orm import Session

from app.modules.energy_state.schemas.energy_balance import (
    EnergyBalanceResponseSchema,
    EnergySinkPowerSchema,
    EnergySourcePowerSchema,
)
from app.modules.energy_state.services.energy_state_service import (
    energy_state_service,
)


class EnergyBalanceService:

    @staticmethod
    def _sum_if_complete(
        *values: float | None,
    ) -> float | None:

        if any(value is None for value in values):
            return None

        return sum(values)

    async def get_energy_balance(
        self,
        db: Session,
    ) -> EnergyBalanceResponseSchema:

        # 1. 获取已经归一化的家庭能源状态
        state = await energy_state_service.get_energy_state(
            db=db,
        )

        power = state.power

        # 2. 计算能源输入
        source_total = self._sum_if_complete(
            power.solar_w,
            power.battery_discharging_w,
            power.grid_import_w,
        )

        # 3. 计算能源输出
        sink_total = self._sum_if_complete(
            power.home_load_w,
            power.battery_charging_w,
            power.grid_export_w,
        )

        sources = EnergySourcePowerSchema(
            solar_w=power.solar_w,
            battery_discharging_w=(
                power.battery_discharging_w
            ),
            grid_import_w=power.grid_import_w,
            total_w=source_total,
        )

        sinks = EnergySinkPowerSchema(
            home_load_w=power.home_load_w,
            battery_charging_w=(
                power.battery_charging_w
            ),
            grid_export_w=power.grid_export_w,
            total_w=sink_total,
        )

        # 4. 数据不完整时，不伪造 Balance
        if (
            source_total is None
            or sink_total is None
        ):
            return EnergyBalanceResponseSchema(
                available=False,
                online=state.online,
                sources=sources,
                sinks=sinks,
                balance_error_w=None,
                balanced=None,
            )

        # 5. 输入 - 输出
        balance_error = (
            source_total - sink_total
        )

        return EnergyBalanceResponseSchema(
            available=state.available,
            online=state.online,
            sources=sources,
            sinks=sinks,
            balance_error_w=balance_error,

            # 当前第一版只判断理论功率关系
            balanced=abs(balance_error) < 1.0,
        )


energy_balance_service = EnergyBalanceService()