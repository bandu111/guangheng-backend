import re
from datetime import datetime, timezone

from app.modules.device_registry.services.device_discovery_service import (
    device_discovery_service,
)
from app.modules.home_assistant.services.home_assistant_service import (
    home_assistant_service,
)
from app.modules.solar_array.schemas.solar_array import (
    SolarArrayInsightSchema,
    SolarComponentSchema,
    SolarInputChannelSchema,
)


class SolarArrayNotFoundError(RuntimeError):
    pass


class SolarArrayService:
    _channel_pattern = re.compile(
        r"^(?:mppt_?(\d+)|pv_?(\d+)|solar_input_?(\d+))_(power|voltage|current|energy)$"
    )
    _component_pattern = re.compile(
        r"^(?:panel|module|component)_?(\d+)_(power|energy)$"
    )

    @staticmethod
    def _number(value: object) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def get_insight(self, device_id: str) -> SolarArrayInsightSchema:
        discovery = await device_discovery_service.discover_devices()
        runtime = next(
            (item for item in discovery.devices if item.device_id == device_id), None
        )
        if runtime is None or runtime.device_type != "storage":
            raise SolarArrayNotFoundError(f"Storage device not found: {device_id}")

        states = await home_assistant_service.get_states()
        prefix = runtime.entity_prefix or ""
        channel_values: dict[int, dict[str, tuple[float | None, str]]] = {}
        component_values: dict[int, dict[str, tuple[float | None, str]]] = {}
        for state in states:
            if "." not in state.entity_id:
                continue
            object_id = state.entity_id.split(".", 1)[1]
            marker = f"{prefix}_"
            if not prefix or not object_id.startswith(marker):
                continue
            suffix = object_id[len(marker):]
            channel_match = self._channel_pattern.match(suffix)
            if channel_match:
                index = int(next(value for value in channel_match.groups()[:3] if value))
                metric = channel_match.group(4)
                channel_values.setdefault(index, {})[metric] = (
                    self._number(state.state), state.entity_id
                )
                continue
            component_match = self._component_pattern.match(suffix)
            if component_match:
                index = int(component_match.group(1))
                metric = component_match.group(2)
                component_values.setdefault(index, {})[metric] = (
                    self._number(state.state), state.entity_id
                )

        channels = [
            SolarInputChannelSchema(
                key=f"mppt_{index}",
                label=f"MPPT {index}",
                available=any(value[0] is not None for value in metrics.values()),
                power_w=metrics.get("power", (None, ""))[0],
                voltage_v=metrics.get("voltage", (None, ""))[0],
                current_a=metrics.get("current", (None, ""))[0],
                energy_kwh=metrics.get("energy", (None, ""))[0],
                entity_ids=[value[1] for value in metrics.values()],
            )
            for index, metrics in sorted(channel_values.items())
        ]
        components = [
            SolarComponentSchema(
                key=f"component_{index}",
                label=f"组件 {index}",
                available=any(value[0] is not None for value in metrics.values()),
                power_w=metrics.get("power", (None, ""))[0],
                energy_kwh=metrics.get("energy", (None, ""))[0],
                entity_ids=[value[1] for value in metrics.values()],
            )
            for index, metrics in sorted(component_values.items())
        ]
        solar = next(
            (item for item in runtime.telemetry if item.name == "solar_power"), None
        )
        channel_available = any(item.available for item in channels)
        component_available = any(item.available for item in components)
        diagnostic = None
        if not channel_available and not component_available:
            diagnostic = "MPPT_CHANNELS_NOT_EXPOSED_BY_INTEGRATION"
        elif not component_available:
            diagnostic = "COMPONENT_CHANNELS_NOT_EXPOSED_BY_INTEGRATION"
        return SolarArrayInsightSchema(
            available=bool(runtime.online and (solar is not None or channel_available)),
            device_id=device_id,
            device_online=runtime.online,
            aggregate_power_w=self._number(solar.value) if solar else None,
            mppt_channels=channels,
            components=components,
            channel_data_available=channel_available,
            component_data_available=component_available,
            observed_at=datetime.now(timezone.utc),
            diagnostic=diagnostic,
        )


solar_array_service = SolarArrayService()
