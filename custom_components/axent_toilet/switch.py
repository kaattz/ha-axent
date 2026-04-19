"""Switch platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS: list[dict] = [
    {
        "key": "auto_deodorize",
        "icon": "mdi:air-filter",
        "command_on": "deodorize_on",
        "command_off": "deodorize_off",
        "default": False,
    },
    {
        "key": "auto_close_lid",
        "icon": "mdi:seat-outline",
        "command_on": "auto_close_on",
        "command_off": "auto_close_off",
        "default": False,
    },
    {
        "key": "fresh_water_exchange",
        "icon": "mdi:water-sync",
        "command_on": "fresh_start",
        "command_off": "fresh_stop",
        "default": False,
    },
    {
        "key": "smart_power_save",
        "icon": "mdi:leaf",
        "command_on": "power_save_on",
        "command_off": "power_save_off",
        "default": False,
    },
    {
        "key": "auto_flush",
        "icon": "mdi:toilet",
        "command_on": "auto_flush_on",
        "command_off": "auto_flush_off",
        "default": False,
    },
    {
        "key": "flush_on_lid_close",
        "icon": "mdi:arrow-down-bold-box-outline",
        "command_on": "flush_on_close_on",
        "command_off": "flush_on_close_off",
        "default": False,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AXENT toilet switch entities."""
    coordinator: AxentCoordinator = entry.runtime_data

    entities = [
        AxentSwitch(coordinator, entry, desc)
        for desc in SWITCH_DESCRIPTIONS
    ]
    async_add_entities(entities)


class AxentSwitch(SwitchEntity, RestoreEntity):
    """Representation of an AXENT toilet switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
        description: dict,
    ) -> None:
        self._coordinator = coordinator
        self._command_on: str = description["command_on"]
        self._command_off: str = description["command_off"]
        self._default_state: bool = description["default"]
        self._settings_key: str = description["key"]
        self._unregister_settings: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_{description['key']}"
        self._attr_translation_key = description["key"]
        self._attr_icon = description["icon"]
        self._attr_is_on = None
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_added_to_hass(self) -> None:
        """Restore last known state and register settings callback."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"
        else:
            self._attr_is_on = self._default_state

        # 注册设备设置回调
        self._unregister_settings = self._coordinator.register_settings_callback(
            self._on_settings_update
        )

    async def async_will_remove_from_hass(self) -> None:
        """Unregister settings callback."""
        if self._unregister_settings is not None:
            self._unregister_settings()
            self._unregister_settings = None

    @callback
    def _on_settings_update(self, settings: dict) -> None:
        """通过 02-0E 回传帧同步设备实际状态。"""
        if self._settings_key in settings:
            new_value = bool(settings[self._settings_key])
            if new_value != self._attr_is_on:
                _LOGGER.debug("同步 %s: %s → %s", self._settings_key, self._attr_is_on, new_value)
                self._attr_is_on = new_value
                self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("开启: %s", self._command_on)
        await self._coordinator.async_send_command(self._command_on)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("关闭: %s", self._command_off)
        await self._coordinator.async_send_command(self._command_off)
        self._attr_is_on = False
        self.async_write_ha_state()
