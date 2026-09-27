from collections.abc import Callable

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)


REGISTER_OFFSET = 1


def ascii_registers(value: str, count: int) -> list[int]:
    raw = value.encode("ascii", errors="ignore")[: count * 2].ljust(count * 2, b"\0")
    return [(raw[index] << 8) | raw[index + 1] for index in range(0, len(raw), 2)]


def uint32_registers(value: int) -> list[int]:
    value &= 0xFFFFFFFF
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def int32_registers(value: int) -> list[int]:
    return uint32_registers(value if value >= 0 else (1 << 32) + value)


def registers_int32(values: list[int]) -> int:
    value = ((values[0] & 0xFFFF) << 16) | (values[1] & 0xFFFF)
    return value - (1 << 32) if value & 0x80000000 else value


class CallbackDataBlock(ModbusSequentialDataBlock):
    def __init__(self) -> None:
        super().__init__(0, [0] * 65537)
        self.on_write: Callable[[int, list[int]], None] | None = None

    def setValues(self, address: int, values):  # noqa: N802 - pymodbus API
        normalized = list(values) if isinstance(values, (list, tuple)) else [values]
        super().setValues(address, normalized)
        if self.on_write is not None:
            self.on_write(address - REGISTER_OFFSET, normalized)


class RegisterBank:
    def __init__(self) -> None:
        self.input = ModbusSequentialDataBlock(0, [0] * 65537)
        self.holding = CallbackDataBlock()
        self.coils = ModbusSequentialDataBlock(0, [False] * 16)
        self.discrete = ModbusSequentialDataBlock(0, [False] * 16)
        device = ModbusDeviceContext(
            di=self.discrete,
            co=self.coils,
            hr=self.holding,
            ir=self.input,
        )
        self.context = ModbusServerContext(devices=device, single=True)

    def set_input(self, address: int, values: int | list[int]) -> None:
        normalized = values if isinstance(values, list) else [values]
        self.input.setValues(address + REGISTER_OFFSET, normalized)

    def set_holding(self, address: int, values: int | list[int]) -> None:
        normalized = values if isinstance(values, list) else [values]
        self.holding.setValues(address + REGISTER_OFFSET, normalized)

    def get_holding(self, address: int, count: int = 1) -> list[int]:
        return list(self.holding.getValues(address + REGISTER_OFFSET, count))


__all__ = [
    "RegisterBank",
    "ascii_registers",
    "int32_registers",
    "registers_int32",
    "uint32_registers",
]
