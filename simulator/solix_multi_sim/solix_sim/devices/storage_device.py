from ..modbus.register_bank import (
    RegisterBank,
    ascii_registers,
    int32_registers,
    registers_int32,
    uint32_registers,
)
from ..profiles.catalog import StorageProductProfile
from ..world.household_world import HouseholdWorld


class StorageDevice:
    def __init__(self, profile: StorageProductProfile, world: HouseholdWorld) -> None:
        self.profile = profile
        self.world = world
        self.bank = RegisterBank()
        self._seed()
        self.bank.holding.on_write = self._handle_write

    @property
    def context(self):
        return self.bank.context

    def _seed(self) -> None:
        state = self.world.storages[self.profile.key]
        self.bank.set_input(32768, ascii_registers(self.profile.device_pn, 5))
        self.bank.set_input(10100, ascii_registers(self.profile.serial_number, 12))
        self.bank.set_input(10112, ascii_registers("SIM-2.0.0", 6))
        self.bank.set_input(32774, 0x007F)
        self.bank.set_input(32775, 0x000F)
        self.bank.set_input(10036, int32_registers(self.profile.max_charge_w))
        self.bank.set_input(10038, int32_registers(self.profile.max_discharge_w))
        self.bank.set_input(10250, uint32_registers(round(self.profile.capacity_kwh * 10)))
        self.bank.set_holding(10064, state.operating_mode)
        self.bank.set_holding(10071, int32_registers(state.requested_battery_w))
        self.bank.set_holding(60000, state.charging_limit)
        self.bank.set_holding(60001, state.discharge_limit)
        self.bank.set_holding(60002, state.backup_reserve)
        self.bank.set_holding(60003, 1)
        self.update()

    def _handle_write(self, address: int, _: list[int]) -> None:
        state = self.world.storages[self.profile.key]
        if address == 10064:
            state.operating_mode = self.bank.get_holding(10064)[0]
        elif address in {10071, 10072}:
            state.requested_battery_w = registers_int32(self.bank.get_holding(10071, 2))
        elif address == 60000:
            state.charging_limit = self.bank.get_holding(60000)[0]
        elif address == 60001:
            state.discharge_limit = self.bank.get_holding(60001)[0]
        elif address == 60002:
            state.backup_reserve = self.bank.get_holding(60002)[0]

    def update(self) -> None:
        state = self.world.storages[self.profile.key]
        snapshot = self.world.snapshot
        status = 1 if state.battery_w < 0 else 2 if state.battery_w > 0 else 0
        self.bank.set_input(10001, status)
        self.bank.set_input(10002, int32_registers(self.profile.pv_share_w))
        self.bank.set_input(10004, int32_registers(0))
        self.bank.set_input(10008, int32_registers(state.battery_w))
        self.bank.set_input(10010, int32_registers(snapshot.home_load_w))
        self.bank.set_input(10012, int32_registers(snapshot.grid_w))
        self.bank.set_input(10014, round(state.soc))
        self.bank.set_input(10018, uint32_registers(round(state.solar_kwh * 10)))
        self.bank.set_input(10208, int32_registers(max(0, state.battery_w)))
        self.bank.set_input(10262, uint32_registers(round(state.charged_kwh * 10)))
        self.bank.set_input(10264, uint32_registers(round(state.discharged_kwh * 10)))
