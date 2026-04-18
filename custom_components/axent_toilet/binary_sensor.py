"""Binary sensor platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AXENT toilet binary sensor entities."""
    coordinator: AxentCoordinator = entry.runtime_data

    async_add_entities([AxentOccupancySensor(coordinator, entry)])


class AxentOccupancySensor(BinarySensorEntity):
    """座圈人体感应传感器。"""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_translation_key = "seat_occupancy"

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._unregister: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_seat_occupancy"
        self._attr_icon = "mdi:seat"
        self._attr_is_on = False  # 默认无人，等待设备事件更新
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_added_to_hass(self) -> None:
        """注册人体感应事件回调。"""
        self._unregister = self._coordinator.register_occupancy_callback(
            self._on_occupancy_event
        )

    async def async_will_remove_from_hass(self) -> None:
        """取消注册回调。"""
        if self._unregister is not None:
            self._unregister()
            self._unregister = None

    @callback
    def _on_occupancy_event(self, occupied: bool) -> None:
        """处理座圈感应事件。"""
        _LOGGER.debug("座圈感应状态: %s", "有人" if occupied else "无人")
        self._attr_is_on = occupied
        self.async_write_ha_state()
