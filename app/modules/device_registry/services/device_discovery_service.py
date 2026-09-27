from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.modules.device_registry.schemas.device_registry import (
    DeviceCapabilitySchema,
    DeviceDiscoveryResponseSchema,
    DeviceProfileCatalogSchema,
    DeviceProfileSummarySchema,
    DiscoveredDeviceSchema,
)
from app.modules.home_assistant.schemas.home_assistant import HomeAssistantStateSchema
from app.modules.home_assistant.services.home_assistant_service import home_assistant_service


BASE_DIR = Path(__file__).resolve().parents[4]
CAPABILITY_MATRIX_PATH = BASE_DIR / "config" / "solix_capability_matrix.yaml"
PROFILE_CATALOG_PATH = BASE_DIR / "config" / "device_profiles.yaml"


class DeviceDiscoveryService:
    """Discover supported devices from one current HA observation."""

    def load_capability_matrix(self) -> dict[str, Any]:
        with CAPABILITY_MATRIX_PATH.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def load_profile_catalog(self) -> dict[str, Any]:
        with PROFILE_CATALOG_PATH.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)

    def get_profile(self, profile_id: str | None) -> dict[str, Any] | None:
        if not profile_id:
            return None
        return self.load_profile_catalog().get("profiles", {}).get(profile_id)

    def get_control_config(
        self,
        profile_id: str | None,
        capability: str,
        source_mode: str | None = None,
    ) -> dict[str, Any] | None:
        profile = self.get_profile(profile_id)
        if profile is not None:
            config = profile.get("controls", {}).get(capability)
            if config is None:
                return None
            result = dict(config)
            allowed_modes = profile.get("verification_source_modes", [])
            verification_allowed = not allowed_modes or source_mode in allowed_modes
            override = (
                profile.get("verification_overrides", {}).get(capability)
                if verification_allowed
                else None
            )
            if override is not None:
                result["verified"] = override
            return result
        return self.load_capability_matrix().get("controls", {}).get(capability)

    def get_safety_policy(self) -> dict[str, Any]:
        return self.load_profile_catalog().get("safety", {})

    async def resolve_storage_telemetry_entity_ids(
        self, capabilities: dict[str, str]
    ) -> dict[str, str]:
        """Resolve current recorder entities from the matched storage profile.

        History consumers must not stay pinned to the original simulator entity
        IDs after another supported SOLIX model is discovered.
        """
        discovery = await self.discover_devices()
        storage = next(
            (
                device
                for device in discovery.devices
                if device.device_type == "storage" and device.online
            ),
            None,
        )
        if storage is None:
            storage = next(
                (
                    device
                    for device in discovery.devices
                    if device.device_type == "storage"
                ),
                None,
            )
        if storage is None:
            return {}
        telemetry = {item.name: item.entity_id for item in storage.telemetry}
        return {
            key: telemetry[capability]
            for key, capability in capabilities.items()
            if capability in telemetry
        }

    def get_catalog(self) -> DeviceProfileCatalogSchema:
        catalog = self.load_profile_catalog()
        profiles = []
        for profile_id, profile in catalog.get("profiles", {}).items():
            controls = profile.get("controls", {})
            # Source-scoped simulator verification is a runtime fact, not a
            # blanket promise that every real device of this model is verified.
            overrides = (
                {}
                if profile.get("verification_source_modes")
                else profile.get("verification_overrides", {})
            )
            profiles.append(
                DeviceProfileSummarySchema(
                    profile_id=profile_id,
                    display_name=profile["display_name"],
                    vendor=profile.get("vendor", "anker_solix"),
                    device_type=profile["device_type"],
                    topology_role=profile["topology_role"],
                    model_patterns=profile.get("model_patterns", []),
                    telemetry=list(profile.get("telemetry", {})),
                    controls=list(controls),
                    verified_controls=[
                        name
                        for name, config in controls.items()
                        if overrides.get(name, config.get("verified")) is True
                    ],
                    support_status=profile.get("support_status", "supported"),
                    firmware_requirement=profile.get("firmware_requirement"),
                )
            )
        return DeviceProfileCatalogSchema(
            schema_version=str(catalog.get("schema_version", "1.0")),
            integration=catalog.get("integration", "anker_solix_official"),
            count=len(profiles),
            profiles=profiles,
        )

    @staticmethod
    def _convert_state_value(value: str):
        if value in ("unknown", "unavailable", ""):
            return None
        try:
            number = float(value)
            return int(number) if number.is_integer() else number
        except (TypeError, ValueError):
            return value

    @staticmethod
    def _entity_matches(entity_id: str, domain: str, suffix: str) -> bool:
        return entity_id.startswith(f"{domain}.") and entity_id.split(".", 1)[1].endswith(
            f"_{suffix}"
        )

    @staticmethod
    def _prefix(entity_id: str, suffix: str) -> str:
        object_id = entity_id.split(".", 1)[1]
        return object_id[: -(len(suffix) + 1)]

    @staticmethod
    def _state_text(state: HomeAssistantStateSchema) -> str:
        friendly = state.attributes.get("friendly_name", "")
        return f"{state.state} {friendly} {state.entity_id}".lower()

    def _find_state(
        self,
        state_map: dict[str, HomeAssistantStateSchema],
        prefix: str,
        spec: dict[str, Any] | None,
    ) -> HomeAssistantStateSchema | None:
        if not spec:
            return None
        domain = spec.get("domain", "sensor")
        for suffix in spec.get("suffixes", []):
            state = state_map.get(f"{domain}.{prefix}_{suffix}")
            if state is not None:
                return state
        return None

    def _capabilities(
        self,
        state_map: dict[str, HomeAssistantStateSchema],
        prefix: str,
        definitions: dict[str, Any],
        observed_at: str,
        *,
        controls: bool,
        verification_overrides: dict[str, bool] | None = None,
        verification_details: dict[str, dict[str, Any]] | None = None,
    ) -> list[DeviceCapabilitySchema]:
        result = []
        for name, definition in definitions.items():
            state = self._find_state(state_map, prefix, definition)
            if state is None:
                continue
            value = self._convert_state_value(state.state)
            verified = (
                (verification_overrides or {}).get(name, definition.get("verified"))
                if controls
                else None
            )
            verification = (verification_details or {}).get(name, {})
            result.append(
                DeviceCapabilitySchema(
                    name=name,
                    entity_id=state.entity_id,
                    access=definition.get(
                        "access", "read_write" if controls else "read"
                    ),
                    value=value,
                    unit=definition.get("unit")
                    or state.attributes.get("unit_of_measurement"),
                    available=value is not None,
                    verified=verified,
                    verification_status=(
                        verification.get("status")
                        or ("verified" if verified else "pending_hardware_verification")
                        if controls
                        else None
                    ),
                    verification_method=verification.get("method") if controls else None,
                    verification_note=(
                        verification.get("note")
                        or definition.get("verification_note")
                        if controls
                        else None
                    ),
                    readback_reliable=(
                        verification.get(
                            "readback_reliable",
                            definition.get("readback_reliable", True),
                        )
                        if controls
                        else None
                    ),
                    min=definition.get("min"),
                    max=definition.get("max"),
                    step=definition.get("step"),
                    last_changed=state.last_changed,
                    last_reported=state.last_reported,
                    last_updated=state.last_updated,
                    observed_at=observed_at,
                )
            )
        return result

    async def discover_devices(self) -> DeviceDiscoveryResponseSchema:
        catalog = self.load_profile_catalog()
        states = await home_assistant_service.get_states()
        observed_at = datetime.now(timezone.utc).isoformat()
        state_map = {state.entity_id: state for state in states}
        devices: list[DiscoveredDeviceSchema] = []
        consumed_anchors: set[str] = set()

        for profile_id, profile in catalog.get("profiles", {}).items():
            if profile.get("discoverable", True) is False:
                continue
            model_spec = profile.get("identity", {}).get("model", {})
            for suffix in model_spec.get("suffixes", []):
                anchors = [
                    state
                    for state in states
                    if self._entity_matches(
                        state.entity_id, model_spec.get("domain", "sensor"), suffix
                    )
                ]
                for model_state in anchors:
                    if model_state.entity_id in consumed_anchors:
                        continue
                    searchable = self._state_text(model_state)
                    patterns = [
                        str(pattern).lower()
                        for pattern in profile.get("model_patterns", [])
                    ]
                    if patterns and not any(pattern in searchable for pattern in patterns):
                        continue
                    prefix = self._prefix(model_state.entity_id, suffix)
                    identity = profile.get("identity", {})
                    serial_state = self._find_state(
                        state_map, prefix, identity.get("serial_number")
                    )
                    firmware_state = self._find_state(
                        state_map, prefix, identity.get("firmware_version")
                    )
                    model = self._convert_state_value(model_state.state)
                    serial = (
                        self._convert_state_value(serial_state.state)
                        if serial_state is not None
                        else None
                    )
                    firmware = (
                        self._convert_state_value(firmware_state.state)
                        if firmware_state is not None
                        else None
                    )
                    serial_text = str(serial) if serial is not None else None
                    simulator_serials = {
                        str(item).upper()
                        for item in catalog.get("simulator_serial_numbers", [])
                    }
                    source_mode = (
                        "simulator"
                        if serial_text
                        and (
                            serial_text.upper().startswith("SIM-")
                            or serial_text.upper() in simulator_serials
                        )
                        else "home_assistant"
                    )
                    allowed_modes = profile.get("verification_source_modes", [])
                    verification_allowed = (
                        not allowed_modes or source_mode in allowed_modes
                    )
                    telemetry = self._capabilities(
                        state_map,
                        prefix,
                        profile.get("telemetry", {}),
                        observed_at,
                        controls=False,
                    )
                    controls = self._capabilities(
                        state_map,
                        prefix,
                        profile.get("controls", {}),
                        observed_at,
                        controls=True,
                        verification_overrides=(
                            profile.get("verification_overrides", {})
                            if verification_allowed
                            else {}
                        ),
                        verification_details=(
                            profile.get("verification_details", {})
                            if verification_allowed
                            else {}
                        ),
                    )
                    telemetry_map = {item.name: item for item in telemetry}
                    required = profile.get("online_required", [])
                    online = bool(required) and all(
                        name in telemetry_map and telemetry_map[name].available
                        for name in required
                    )
                    device_key = serial_text or prefix
                    devices.append(
                        DiscoveredDeviceSchema(
                            device_id=f"anker_solix_{device_key}",
                            vendor=profile.get("vendor", "anker_solix"),
                            model=str(model or profile["display_name"]),
                            serial_number=serial_text,
                            firmware_version=str(firmware)
                            if firmware is not None
                            else None,
                            device_type=profile["device_type"],
                            topology_role=profile["topology_role"],
                            integration=catalog.get(
                                "integration", "anker_solix_official"
                            ),
                            source_mode=source_mode,
                            online=online,
                            observed_at=observed_at,
                            profile_id=profile_id,
                            profile_name=profile["display_name"],
                            entity_prefix=prefix,
                            telemetry=telemetry,
                            controls=controls,
                        )
                    )
                    consumed_anchors.add(model_state.entity_id)

        return DeviceDiscoveryResponseSchema(count=len(devices), devices=devices)


device_discovery_service = DeviceDiscoveryService()
