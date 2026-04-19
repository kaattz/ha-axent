"""BLE protocol encoder/decoder for AXENT Smart Toilet."""

from __future__ import annotations

import logging

from .const import EVENT_OCCUPIED, EVENT_UNOCCUPIED

_LOGGER = logging.getLogger(__name__)


def parse_notification(data: bytes | bytearray) -> dict | None:
    """解析 Notify 回包，提取事件类型。

    Returns:
        dict with event info, or None if not recognized.
    """
    if len(data) < 4:
        return None

    # 控制回传帧: 02-0E-30-... (32 bytes)
    # 包含就座状态、清洗参数、设备状态等
    if (
        len(data) == 32
        and data[0] == 0x02
        and data[1] == 0x0E
        and data[2] == 0x30
    ):
        seated = bool(data[20] & 0x01)
        _LOGGER.debug("控制回传帧: 就座=%s, byte[3]=%02X", seated, data[3])

        result = {
            "event": "status",
            "seated": seated,
        }

        # 解析清洗参数（byte[3]=0x30, byte[4]=0x00 时为主状态帧）
        if data[3] == 0x30 and data[4] == 0x00:
            wash_mode = data[10] & 0x03  # 0=无, 1=后洗, 2=妇洗, 3=强力洗
            water_temp = (data[11] >> 4) & 0x0F
            nozzle_pos = data[11] & 0x0F
            water_vol = (data[12] >> 4) & 0x0F
            seat_temp = data[12] & 0x0F
            wind_temp = (data[13] >> 4) & 0x0F

            result.update({
                "wash_mode": wash_mode,
                "water_temp": water_temp,
                "nozzle_pos": nozzle_pos,
                "water_vol": water_vol,
                "seat_temp": seat_temp,
                "wind_temp": wind_temp,
            })
            _LOGGER.debug(
                "主状态帧: 清洗=%d, 水温=%d, 座温=%d",
                wash_mode, water_temp, seat_temp,
            )

        return result

    # 扩展帧: 02-9F-30-XX-... (人体接近/传感器帧)
    if data[0] == 0x02 and data[1] == 0x9F:
        event_marker = bytes(data[2:4])

        if event_marker == EVENT_OCCUPIED:
            _LOGGER.debug("人体感应: 有人接近")
            return {"event": "occupancy", "occupied": True}

        if event_marker == EVENT_UNOCCUPIED:
            _LOGGER.debug("人体感应: 无人")
            return {"event": "occupancy", "occupied": False}

        _LOGGER.debug("未知扩展帧事件: %s", data.hex("-"))
        return {"event": "unknown", "raw": data.hex("-")}

    return None
