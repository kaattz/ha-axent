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
        AxentSeatedSensor(coordinator, entry),
        AxentConnectivitySensor(coordinator, entry),
    ])


class AxentSeatedSensor(BinarySensorEntity):
    """就座状态传感器。

    数据来源：
    - 02-9F 传感器帧（坐下/离座事件）
    - 02-0E 控制帧 byte[20] bit 0（状态同步）
    两种来源共同驱动同一个传感器。

    注：人体接近（走近马桶时翻盖）由马桶固件内部处理，
    不通过 BLE 发送 Notify 帧，无法在 HA 中检测。
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
        self._unsub_seated: Callable[[], None] | None = None
        self._unsub_status: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_seat_occupancy"
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
        """注册 02-9F + 02-0E 两种来源的回调。"""
        self._unsub_seated = self._coordinator.register_seated_callback(
            self._on_state_change
        )
        self._unsub_status = self._coordinator.register_occupancy_callback(
            self._on_state_change
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_seated is not None:
            self._unsub_seated()
            self._unsub_seated = None
        if self._unsub_status is not None:
            self._unsub_status()
            self._unsub_status = None

    @callback
    def _on_state_change(self, seated: bool) -> None:
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
