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
    # 包含就座状态、清洗参数、设备设置等
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

        # 主状态帧（byte[3]=0x30, byte[4]=0x00）包含完整设备设置
        if data[3] == 0x30 and data[4] == 0x00:
            # byte[10-13]: 清洗参数
            water_temp = (data[11] >> 4) & 0x0F
            nozzle_pos = data[11] & 0x0F
            water_vol = (data[12] >> 4) & 0x0F
            seat_temp = data[12] & 0x0F

            # byte[14]: 除臭 / 冲水设置
            deodorize = (data[14] >> 6) == 1
            flush_setting = (data[14] & 0x03) == 1

            # byte[15]: 节电 / 夜灯
            eco_raw = (data[15] & 0xF0) >> 4
            nightlight_raw = (data[15] & 0x0C) >> 2
            power_save = eco_raw != 0
            # nightlight: raw 0→smart(2), 1→off(0), 2→on(1)
            nightlight = 2 if nightlight_raw == 0 else nightlight_raw - 1

            # byte[16]: 感应距离 / 自动翻盖 / 自动关盖
            sensor_distance = (data[16] & 0xE0) >> 5
            auto_lid_raw = (data[16] & 0x1C) >> 2
            # auto_lid: raw 0→off(2), others→raw-1
            auto_lid = 2 if auto_lid_raw == 0 else auto_lid_raw - 1
            auto_close = (data[16] & 0x03) == 1

            settings = {
                "water_temperature": str(water_temp) if water_temp > 0 else "1",
                "nozzle_position": str(nozzle_pos) if nozzle_pos > 0 else "1",
                "water_volume": str(water_vol) if water_vol > 0 else "1",
                "seat_temperature": str(seat_temp) if seat_temp > 0 else "1",
                "auto_deodorize": deodorize,
                "flush_on_lid_close": flush_setting,
                "smart_power_save": power_save,
                "nightlight_mode": ["off", "on", "smart"][nightlight],
                "sensor_range": ["far", "medium", "near"][min(sensor_distance, 2)],
                "auto_lid_mode": ["off", "half_open", "full_open"][min(auto_lid, 2)],
                "auto_close_lid": auto_close,
            }
            result["settings"] = settings

            _LOGGER.debug(
                "主状态帧: 水温=%s, 座温=%s, 夜灯=%s, 除臭=%s, 感应=%s, 翻盖=%s",
                settings["water_temperature"],
                settings["seat_temperature"],
                settings["nightlight_mode"],
                settings["auto_deodorize"],
                settings["sensor_range"],
                settings["auto_lid_mode"],
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
