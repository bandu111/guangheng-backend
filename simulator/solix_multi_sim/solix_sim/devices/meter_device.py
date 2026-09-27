from ..modbus.register_bank import (
    RegisterBank,
    ascii_registers,
    int32_registers,
    uint32_registers,
)
from ..profiles.catalog import MeterProductProfile
from ..world.household_world import HouseholdWorld


class SmartMeterDevice:
    def __init__(self, profile: MeterProductProfile, world: HouseholdWorld) -> None:
        self.profile = profile
        self.world = world
        self.bank = RegisterBank()
        self._seed()

    @property
    def context(self):
        return self.bank.context

    def _seed(self) -> None:
        # Config flow always probes the common device-PN register first. The
        # meter profile then reads the same PN again from its native 10620 map.
        self.bank.set_input(32768, ascii_registers(self.profile.device_pn, 5))
        self.bank.set_input(10620, ascii_registers(self.profile.device_pn, 10))
        self.bank.set_input(10630, 2)
        self.bank.set_input(10702, ascii_registers(self.profile.serial_number, 10))
        self.bank.set_input(10696, [0x0200, 0])
        self.update()

    def update(self) -> None:
        snapshot = self.world.snapshot
        grid = snapshot.grid_w
        phases = [round(grid * 0.34), round(grid * 0.33)]
        phases.append(grid - sum(phases))
        voltage_raw = 2300
        for index, power in enumerate(phases):
            self.bank.set_input(10632 + index, voltage_raw)
            self.bank.set_input(10635 + index, round(abs(power) / 230 * 100))
            self.bank.set_input(10638 + index * 2, int32_registers(power))
        self.bank.set_input(10644, int32_registers(grid))
        self.bank.set_input(10646, int32_registers(round(abs(grid) * 0.08)))
        self.bank.set_input(10648, 980)

        import_raw = round(self.world.grid_import_kwh * 10)
        export_raw = round(self.world.grid_export_kwh * 10)
        for address in (10650, 10652, 10654):
            self.bank.set_input(address, uint32_registers(round(import_raw / 3)))
        self.bank.set_input(10656, uint32_registers(import_raw))
        for address in (10658, 10660, 10662):
            self.bank.set_input(address, uint32_registers(round(export_raw / 3)))
        self.bank.set_input(10664, uint32_registers(export_raw))

        secondary = snapshot.secondary_ct_w
        secondary_phases = [round(secondary * 0.34), round(secondary * 0.33)]
        secondary_phases.append(secondary - sum(secondary_phases))
        for index, power in enumerate(secondary_phases):
            self.bank.set_input(10666 + index, round(abs(power) / 230 * 100))
            self.bank.set_input(10669 + index * 2, int32_registers(power))
        self.bank.set_input(10675, int32_registers(secondary))
        self.bank.set_input(10677, int32_registers(round(abs(secondary) * 0.05)))
        self.bank.set_input(10679, 990)
        for address in (10680, 10682, 10684, 10686):
            self.bank.set_input(address, uint32_registers(round(sum(s.solar_kwh for s in self.world.storages.values()) * 10)))
        for address in (10688, 10690, 10692, 10694):
            self.bank.set_input(address, uint32_registers(round(self.world.grid_export_kwh * 10)))
