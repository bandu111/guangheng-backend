from datetime import datetime

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeviceCapabilitySchema(BaseModel):
    name: str
    entity_id: str

    access: str

    value: Any | None = None
    unit: str | None = None

    available: bool = True
    verified: bool | None = None
    verification_status: str | None = None
    verification_method: str | None = None
    verification_note: str | None = None
    readback_reliable: bool | None = None

    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    last_changed: str | None = None
    last_reported: str | None = None
    last_updated: str | None = None
    observed_at: str | None = None

class DiscoveredDeviceSchema(BaseModel):
    device_id: str

    vendor: str
    model: str
    serial_number: str | None = None
    firmware_version: str | None = None

    device_type: str
    topology_role: str

    integration: str
    source_mode: str

    online: bool
    observed_at: str
    profile_id: str | None = None
    profile_name: str | None = None
    entity_prefix: str | None = None
    bound_device_id: int | None = None
    control_enabled: bool = False
    telemetry: list[DeviceCapabilitySchema] = Field(default_factory=list)
    controls: list[DeviceCapabilitySchema] = Field(default_factory=list)

class DeviceDiscoveryResponseSchema(BaseModel):
    count: int
    devices: list[DiscoveredDeviceSchema]


class DeviceProfileSummarySchema(BaseModel):
    profile_id: str
    display_name: str
    vendor: str
    device_type: str
    topology_role: str
    model_patterns: list[str] = Field(default_factory=list)
    telemetry: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    verified_controls: list[str] = Field(default_factory=list)
    support_status: str = "supported"
    firmware_requirement: str | None = None


class DeviceProfileCatalogSchema(BaseModel):
    schema_version: str
    integration: str
    count: int
    profiles: list[DeviceProfileSummarySchema]


class SmartPlugProposalRequestSchema(BaseModel):
    target_on: bool


class DeviceControlProposalRequestSchema(BaseModel):
    capability: str
    target_value: float

class DeviceBindRequestSchema(BaseModel):
    display_name: str | None = None

    observe_enabled: bool = True
    propose_enabled: bool = True
    control_enabled: bool = False
    scene_enabled: bool = True


class DeviceUpdateRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    observe_enabled: bool | None = None
    propose_enabled: bool | None = None
    control_enabled: bool | None = None
    scene_enabled: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required.")
        return self


class DeviceResponseSchema(BaseModel):
    id: int

    source_device_id: str

    vendor: str
    model: str
    serial_number: str | None = None

    device_type: str
    topology_role: str

    integration: str
    source_mode: str

    display_name: str | None = None

    observe_enabled: bool
    propose_enabled: bool
    control_enabled: bool
    scene_enabled: bool

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }

class DeviceListResponseSchema(BaseModel):
    count: int
    devices: list[DeviceResponseSchema]

class DeviceRuntimeStateSchema(BaseModel):
    online: bool
    observed_at: str | None = None

    telemetry: list[DeviceCapabilitySchema] = Field(
        default_factory=list
    )

    controls: list[DeviceCapabilitySchema] = Field(
        default_factory=list
    )


class DeviceStateResponseSchema(BaseModel):
    device: DeviceResponseSchema
    runtime: DeviceRuntimeStateSchema


class BatteryInsightSchema(BaseModel):
    available: bool
    device_id: int
    source_mode: str
    soc_percent: float | None = None
    capacity_kwh: float | None = None
    current_energy_kwh: float | None = None
    reserve_percent: float | None = None
    protected_energy_kwh: float | None = None
    discharge_limit_percent: float | None = None
    usable_energy_kwh: float | None = None
    whole_home_load_w: float | None = None
    whole_home_backup_hours: float | None = None
    critical_load_backup_hours: float | None = None
    discharge_efficiency: float = 0.92
    status: str | None = None
    observed_at: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    diagnostic: str | None = None
