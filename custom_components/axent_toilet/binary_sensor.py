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

    async_add_entities([
        AxentOccupancySensor(coordinator, entry),
        AxentSeatedSensor(coordinator, entry),
        AxentConnectivitySensor(coordinator, entry),
    ])


class AxentOccupancySensor(BinarySensorEntity):
    """人体接近传感器。

    数据来源：02-0E 控制帧 byte[20] bit 0
    需要 BLE 常连才能持续接收状态帧。
    当毫米波雷达检测到有人走近时 byte[20] 从 0→1。
    """

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
        self._attr_name = "人体接近"
        self._attr_icon = "mdi:motion-sensor"
        self._attr_is_on = False
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_added_to_hass(self) -> None:
        """注册人体接近回调。"""
        self._unregister = self._coordinator.register_occupancy_callback(
            self._on_event
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister is not None:
            self._unregister()
            self._unregister = None

    @callback
    def _on_event(self, occupied: bool) -> None:
        _LOGGER.debug("人体接近: %s", "有人" if occupied else "无人")
        self._attr_is_on = occupied
        self.async_write_ha_state()


class AxentSeatedSensor(BinarySensorEntity):
    """就座状态传感器。

    数据来源：02-9F 传感器帧（毫米波雷达事件帧）
    坐下/离座时由马桶主动推送。
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY
    _attr_translation_key = "seat_seated"

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._unregister: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_seat_seated"
        self._attr_name = "就座状态"
        self._attr_icon = "mdi:seat"
        self._attr_is_on = False
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_added_to_hass(self) -> None:
        """注册就座状态回调。"""
        self._unregister = self._coordinator.register_seated_callback(
            self._on_event
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister is not None:
            self._unregister()
            self._unregister = None

    @callback
    def _on_event(self, seated: bool) -> None:
        _LOGGER.debug("就座状态: %s", "已就座" if seated else "已离座")
        self._attr_is_on = seated
        self.async_write_ha_state()


class AxentConnectivitySensor(BinarySensorEntity):
    """BLE 连接状态传感器。"""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "ble_connection"

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._coordinator = coordinator
        self._unregister: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_ble_connection"
        self._attr_name = "BLE 连接"
        self._attr_icon = "mdi:bluetooth-connect"
        self._attr_is_on = False
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_added_to_hass(self) -> None:
        self._unregister = self._coordinator.register_connection_callback(
            self._on_connection_change
        )
        self._attr_is_on = self._coordinator.is_connected
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        if self._unregister is not None:
            self._unregister()
            self._unregister = None

    @callback
    def _on_connection_change(self, connected: bool) -> None:
        _LOGGER.debug("BLE 连接: %s", "已连接" if connected else "已断开")
        self._attr_is_on = connected
        self.async_write_ha_state()
