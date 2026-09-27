from ..modbus.register_bank import (
    RegisterBank,
    ascii_registers,
    uint32_registers,
)
from ..profiles.catalog import PlugProductProfile
from ..world.household_world import HouseholdWorld


class SmartPlugDevice:
    def __init__(self, profile: PlugProductProfile, world: HouseholdWorld) -> None:
        self.profile = profile
        self.world = world
        self.bank = RegisterBank()
        self._seed()
        self.bank.holding.on_write = self._handle_write

    @property
    def context(self):
        return self.bank.context

    def _seed(self) -> None:
        self.bank.set_input(32768, ascii_registers(self.profile.device_pn, 5))
        self.bank.set_input(30005, ascii_registers(self.profile.serial_number, 12))
        self.bank.set_input(30017, ascii_registers("SIM-2.0.0", 6))
        self.bank.set_input(30023, ascii_registers("SIM-HW-1", 6))
        self.bank.set_holding(30047, 1 if self.world.plug_on else 0)
        self.update()

    def _handle_write(self, address: int, _: list[int]) -> None:
        if address == 30047:
            self.world.plug_on = self.bank.get_holding(30047)[0] == 1

    def update(self) -> None:
        power = self.world.plug_power_w
        self.bank.set_input(30029, 1 if self.world.plug_on else 0)
        self.bank.set_input(30030, round(power * 10))
        self.bank.set_input(30031, 2300)
        self.bank.set_input(30032, round(power / 230 * 100))
        self.bank.set_input(30033, uint32_registers(round(self.world.plug_energy_kwh * 1000)))
        self.bank.set_input(30037, 268)
