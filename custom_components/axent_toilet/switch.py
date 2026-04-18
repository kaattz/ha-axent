"""Switch platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_AUTO_CLOSE_OFF,
    CMD_AUTO_CLOSE_ON,
    CMD_AUTO_FLUSH_OFF,
    CMD_AUTO_FLUSH_ON,
    CMD_DEODORIZE_OFF,
    CMD_DEODORIZE_ON,
    CMD_FLUSH_ON_CLOSE_OFF,
    CMD_FLUSH_ON_CLOSE_ON,
    CMD_FRESH_WATER_START,
    CMD_FRESH_WATER_STOP,
    CMD_POWER_SAVE_OFF,
    CMD_POWER_SAVE_ON,
    DOMAIN,
)
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

SWITCH_DESCRIPTIONS: list[dict] = [
    {
        "key": "auto_deodorize",
        "name": "自动除臭",
        "icon": "mdi:air-filter",
        "command_on": CMD_DEODORIZE_ON,
        "command_off": CMD_DEODORIZE_OFF,
    },
    {
        "key": "auto_close_lid",
        "name": "自动关盖",
        "icon": "mdi:seat-outline",
        "command_on": CMD_AUTO_CLOSE_ON,
        "command_off": CMD_AUTO_CLOSE_OFF,
    },
    {
        "key": "fresh_water_exchange",
        "name": "活水置换",
        "icon": "mdi:water-sync",
        "command_on": CMD_FRESH_WATER_START,
        "command_off": CMD_FRESH_WATER_STOP,
    },
    {
        "key": "smart_power_save",
        "name": "智能节电",
        "icon": "mdi:leaf",
        "command_on": CMD_POWER_SAVE_ON,
        "command_off": CMD_POWER_SAVE_OFF,
    },
    {
        "key": "auto_flush",
        "name": "自动冲水",
        "icon": "mdi:toilet",
        "command_on": CMD_AUTO_FLUSH_ON,
        "command_off": CMD_AUTO_FLUSH_OFF,
    },
    {
        "key": "flush_on_lid_close",
        "name": "关盖冲水",
        "icon": "mdi:arrow-down-bold-box-outline",
        "command_on": CMD_FLUSH_ON_CLOSE_ON,
        "command_off": CMD_FLUSH_ON_CLOSE_OFF,
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


class AxentSwitch(SwitchEntity):
    """Representation of an AXENT toilet switch."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
        description: dict,
    ) -> None:
        self._coordinator = coordinator
        self._command_on = description["command_on"]
        self._command_off = description["command_off"]

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        _LOGGER.debug("开启: %s", self._attr_translation_key)
        await self._coordinator.async_send_command(self._command_on)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        _LOGGER.debug("关闭: %s", self._attr_translation_key)
        await self._coordinator.async_send_command(self._command_off)
        self._attr_is_on = False
        self.async_write_ha_state()
