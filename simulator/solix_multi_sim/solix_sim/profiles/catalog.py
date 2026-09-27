from dataclasses import dataclass


@dataclass(frozen=True)
class StorageProductProfile:
    key: str
    ip_address: str
    product_code: str
    device_pn: str
    model: str
    serial_number: str
    capacity_kwh: float
    max_charge_w: int
    max_discharge_w: int
    initial_soc: float
    pv_share_w: int


@dataclass(frozen=True)
class MeterProductProfile:
    ip_address: str = "127.0.0.15"
    product_code: str = "DNSL"
    device_pn: str = "AE1X0"
    model: str = "Anker SOLIX Smart Meter Gen 2"
    # Official integration extracts four-character product codes from indexes
    # 3..6 of a 17-character serial number.
    serial_number: str = "123DNSL4567890123"


@dataclass(frozen=True)
class PlugProductProfile:
    key: str = "water_heater"
    ip_address: str = "127.0.0.16"
    product_code: str = "QNA"
    device_pn: str = "A17X8"
    model: str = "Anker SOLIX Smart Plug Gen 2"
    # Three-character product codes use indexes 3..5 of a 16-character SN.
    serial_number: str = "123QNA4567890123"
    rated_power_w: int = 800


STORAGE_PROFILES = (
    StorageProductProfile(
        key="solarbank_4",
        ip_address="127.0.0.1",
        product_code="DPM4",
        device_pn="DPM4",
        model="Anker SOLIX Solarbank 4 E5000 Pro",
        serial_number="123DPM44567890123",
        capacity_kwh=10.0,
        max_charge_w=6000,
        max_discharge_w=6000,
        initial_soc=77,
        pv_share_w=1800,
    ),
    StorageProductProfile(
        key="max_ac",
        ip_address="127.0.0.11",
        product_code="DMWH",
        device_pn="A17E2",
        model="Anker SOLIX Solarbank Max AC",
        serial_number="123DMWH4567890123",
        capacity_kwh=7.0,
        max_charge_w=3500,
        max_discharge_w=3500,
        initial_soc=48,
        pv_share_w=0,
    ),
    StorageProductProfile(
        key="xe_ac",
        ip_address="127.0.0.12",
        product_code="DNMS",
        device_pn="A17E2",
        model="Anker SOLIX XE AC",
        serial_number="123DNMS4567890123",
        capacity_kwh=7.0,
        max_charge_w=3500,
        max_discharge_w=3500,
        initial_soc=62,
        pv_share_w=0,
    ),
    StorageProductProfile(
        key="max",
        ip_address="127.0.0.13",
        product_code="DMY6",
        device_pn="AE111",
        model="Anker SOLIX Solarbank Max",
        serial_number="123DMY64567890123",
        capacity_kwh=7.0,
        max_charge_w=5000,
        max_discharge_w=5000,
        initial_soc=35,
        pv_share_w=1600,
    ),
    StorageProductProfile(
        key="xe",
        ip_address="127.0.0.14",
        product_code="DNN4",
        device_pn="AE113",
        model="Anker SOLIX XE",
        serial_number="123DNN44567890123",
        capacity_kwh=7.0,
        max_charge_w=5000,
        max_discharge_w=5000,
        initial_soc=55,
        pv_share_w=800,
    ),
)

METER_PROFILE = MeterProductProfile()
PLUG_PROFILE = PlugProductProfile()
