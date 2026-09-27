from datetime import datetime, timezone

from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DiscoveredDeviceSchema,
)
from app.modules.household_graph.services.household_graph_service import (
    household_graph_service,
)


def capability(name: str, value, *, access: str = "read_only", maximum=None):
    return DeviceCapabilitySchema(
        name=name,
        entity_id=f"sensor.{name}",
        access=access,
        value=value,
        max=maximum,
        available=True,
        verified=True,
    )


def device(
    device_id: str,
    device_type: str,
    telemetry: list[DeviceCapabilitySchema],
    controls: list[DeviceCapabilitySchema] | None = None,
):
    return DiscoveredDeviceSchema(
        device_id=device_id,
        vendor="Anker",
        model=device_id,
        device_type=device_type,
        topology_role={
            "storage": "energy_buffer",
            "smart_meter": "observer_verifier",
            "smart_plug": "load_actuator",
        }[device_type],
        integration="anker_solix",
        source_mode="simulator",
        online=True,
        observed_at="2026-09-24T10:00:00Z",
        telemetry=telemetry,
        controls=controls or [],
    )


def storage(device_id: str):
    return device(
        device_id,
        "storage",
        [
            capability("battery_soc", 50),
            capability("battery_charging_power", 0),
            capability("battery_discharging_power", 0),
            capability("home_load", 1900),
        ],
        [
            capability(
                "battery_power_direction", 0, access="read_write", maximum=1
            ),
            capability(
                "battery_power_setpoint", 0, access="read_write", maximum=3500
            ),
        ],
    )


def test_household_opportunity_builds_multi_device_ordered_action_set():
    graph = household_graph_service.compose(
        [
            device(
                "meter",
                "smart_meter",
                [
                    capability("primary_total_active_power", -2300),
                    capability("secondary_total_active_power", 4200),
                ],
            ),
            storage("storage-a"),
            storage("storage-b"),
        ],
        datetime.now(timezone.utc),
    )

    assert graph.meter_ground_truth is True
    assert graph.energy_balance_error_w == 0
    assert len(graph.opportunities) == 1
    opportunity = graph.opportunities[0]
    assert opportunity.code == "SOLAR_SURPLUS_SELF_CONSUMPTION"
    assert opportunity.expected_grid_delta_w == 2300
    assert [item.device_id for item in opportunity.actions] == [
        "storage-a",
        "storage-a",
        "storage-b",
        "storage-b",
    ]
    assert [item.target_value for item in opportunity.actions] == [0, 1200, 0, 1100]


def test_household_opportunity_prefers_idle_flexible_load_then_storage():
    graph = household_graph_service.compose(
        [
            device(
                "meter",
                "smart_meter",
                [
                    capability("primary_total_active_power", -1500),
                    capability("secondary_total_active_power", 3400),
                ],
            ),
            storage("storage-a"),
            device(
                "plug",
                "smart_plug",
                [capability("real_time_power", 0), capability("switch_status", "off")],
                [capability("power_switch", "off", access="read_write", maximum=1)],
            ),
        ],
        datetime.now(timezone.utc),
    )

    actions = graph.opportunities[0].actions
    assert actions[0].device_id == "plug"
    assert actions[0].capability == "power_switch"
    assert actions[0].expected_delta_w == 800
    assert actions[-1].expected_delta_w == 700


def test_meter_secondary_ct_is_net_supply_and_does_not_double_count_storage():
    charging = storage("storage-a")
    charging.telemetry = [
        capability("battery_soc", 50),
        capability("battery_charging_power", 2300),
        capability("battery_discharging_power", 0),
        capability("home_load", 1900),
    ]
    graph = household_graph_service.compose(
        [
            device(
                "meter",
                "smart_meter",
                [
                    capability("primary_total_active_power", 0),
                    capability("secondary_total_active_power", 1900),
                ],
            ),
            charging,
        ],
        datetime.now(timezone.utc),
    )

    assert graph.energy_balance_error_w == 0
