import asyncio
import logging
import time

from pymodbus.server import ModbusTcpServer

from .devices import SmartMeterDevice, SmartPlugDevice, StorageDevice
from .profiles import METER_PROFILE, PLUG_PROFILE, STORAGE_PROFILES
from .world import HouseholdWorld


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SOLIX-MULTI-SIM] %(levelname)s %(message)s",
)


async def run() -> None:
    world = HouseholdWorld()
    devices = [StorageDevice(profile, world) for profile in STORAGE_PROFILES]
    devices.extend(
        [SmartMeterDevice(METER_PROFILE, world), SmartPlugDevice(PLUG_PROFILE, world)]
    )
    endpoints = [profile.ip_address for profile in STORAGE_PROFILES]
    endpoints.extend([METER_PROFILE.ip_address, PLUG_PROFILE.ip_address])
    servers = [
        ModbusTcpServer(device.context, address=(ip_address, 502))
        for device, ip_address in zip(devices, endpoints, strict=True)
    ]
    for server in servers:
        await server.serve_forever(background=True)

    logging.info("Shared HouseholdWorld started; TCP 502 is bound only on loopback")
    for device, ip_address in zip(devices, endpoints, strict=True):
        logging.info("%s -> %s:502", device.profile.model, ip_address)

    last_tick = time.monotonic()
    last_log = 0.0
    while True:
        await asyncio.sleep(1)
        now = time.monotonic()
        snapshot = world.tick(now - last_tick)
        last_tick = now
        for device in devices:
            device.update()
        if now - last_log >= 30:
            logging.info(
                "PV=%dW load=%dW battery=%dW grid=%dW plug=%dW residual=%dW",
                snapshot.pv_w,
                snapshot.home_load_w,
                snapshot.battery_w,
                snapshot.grid_w,
                snapshot.controllable_load_w,
                snapshot.balance_residual_w,
            )
            last_log = now


if __name__ == "__main__":
    asyncio.run(run())
