"""BLE protocol encoder/decoder for AXENT Smart Toilet."""

from __future__ import annotations

import logging

from .const import EVENT_OCCUPIED, EVENT_UNOCCUPIED

_LOGGER = logging.getLogger(__name__)


def parse_notification(data: bytes | bytearray) -> dict | None:
    """解析 Notify 回包，提取事件类型。

    Returns:
        dict with event info, or None if not recognized.
        Example: {"event": "occupancy", "occupied": True}
    """
    if len(data) < 4:
        return None

    # 扩展帧: 02-9F-30-XX-...
    if data[0] == 0x02 and data[1] == 0x9F:
        event_marker = bytes(data[2:4])

        if event_marker == EVENT_OCCUPIED:
            _LOGGER.debug("人体感应: 有人坐下")
            return {"event": "occupancy", "occupied": True}

        if event_marker == EVENT_UNOCCUPIED:
            _LOGGER.debug("人体感应: 无人")
            return {"event": "occupancy", "occupied": False}

        _LOGGER.debug("未知扩展帧事件: %s", data.hex("-"))
        return {"event": "unknown", "raw": data.hex("-")}

    _LOGGER.debug("收到未知通知数据: %s", data.hex("-"))
    return None
