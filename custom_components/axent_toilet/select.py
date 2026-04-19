"""Select platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging
from typing import Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

SELECT_DESCRIPTIONS: list[dict] = [
    {
        "key": "lid_position",
        "icon": "mdi:seat-outline",
        "options": ["closed", "half_open", "full_open"],
        "default": "closed",
        "commands": {
            "closed": "lid_close",
            "half_open": "lid_half",
            "full_open": "lid_full",
        },
    },
    {
        "key": "nightlight_mode",
        "icon": "mdi:lightbulb-night-outline",
        "options": ["off", "on", "smart"],
        "default": "off",
        "commands": {
            "off": "nightlight_off",
            "on": "nightlight_on",
            "smart": "nightlight_smart",
        },
    },
    {
        "key": "auto_lid_mode",
        "icon": "mdi:arrow-up-down",
        "options": ["off", "half_open", "full_open"],
        "default": "off",
        "commands": {
            "off": "auto_lid_off",
            "half_open": "auto_lid_half",
            "full_open": "auto_lid_full",
        },
    },
    {
        "key": "sonic_wash_mode",
        "icon": "mdi:sine-wave",
        "options": ["1d", "2d", "3d"],
        "default": "1d",
        "commands": {
            "1d": "sonic_1d",
            "2d": "sonic_2d",
            "3d": "sonic_3d",
        },
    },
    {
        "key": "sensor_range",
        "icon": "mdi:signal-distance-variant",
        "options": ["far", "medium", "near"],
        "default": "medium",
        "commands": {
            "far": "sensor_far",
            "medium": "sensor_medium",
            "near": "sensor_near",
        },
    },
    {
        "key": "water_temperature",
        "icon": "mdi:thermometer-water",
        "options": ["1", "2", "3", "4", "5"],
        "default": "3",
        "commands": {
            "1": "water_temp_1",
            "2": "water_temp_2",
            "3": "water_temp_3",
            "4": "water_temp_4",
            "5": "water_temp_5",
        },
    },
    {
        "key": "water_volume",
        "icon": "mdi:water-plus-outline",
        "options": ["1", "2", "3", "4", "5"],
        "default": "3",
        "commands": {
            "1": "water_vol_1",
            "2": "water_vol_2",
            "3": "water_vol_3",
            "4": "water_vol_4",
            "5": "water_vol_5",
        },
    },
    {
        "key": "nozzle_position",
        "icon": "mdi:spray",
        "options": ["1", "2", "3", "4", "5"],
        "default": "3",
        "commands": {
            "1": "nozzle_1",
            "2": "nozzle_2",
            "3": "nozzle_3",
            "4": "nozzle_4",
            "5": "nozzle_5",
        },
    },
    {
        "key": "seat_temperature",
        "icon": "mdi:seat-recline-normal",
        "options": ["1", "2", "3", "4", "5"],
        "default": "3",
        "commands": {
            "1": "seat_temp_1",
            "2": "seat_temp_2",
            "3": "seat_temp_3",
            "4": "seat_temp_4",
            "5": "seat_temp_5",
        },
    },
    {
        "key": "flush_delay",
        "icon": "mdi:timer-outline",
        "options": ["off", "5s", "10s", "15s"],
        "default": "off",
        "commands": {
            "off": "flush_delay_off",
            "5s": "flush_delay_5s",
            "10s": "flush_delay_10s",
            "15s": "flush_delay_15s",
        },
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AXENT toilet select entities."""
    coordinator: AxentCoordinator = entry.runtime_data

    entities = [
        AxentSelect(coordinator, entry, desc)
        for desc in SELECT_DESCRIPTIONS
    ]
    async_add_entities(entities)


class AxentSelect(SelectEntity, RestoreEntity):
    """Representation of an AXENT toilet select entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
        description: dict,
    ) -> None:
        self._coordinator = coordinator
        self._commands: dict[str, str] = description["commands"]
        self._default_option: str = description["default"]
        self._settings_key: str = description["key"]
        self._unregister_settings: Callable[[], None] | None = None

        self._attr_unique_id = f"{entry.data['address']}_{description['key']}"
        self._attr_translation_key = description["key"]
        self._attr_icon = description["icon"]
        self._attr_options = description["options"]
        self._attr_current_option = None
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
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
        else:
            self._attr_current_option = self._default_option

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
            new_value = settings[self._settings_key]
            if new_value in self._attr_options and new_value != self._attr_current_option:
                _LOGGER.debug("同步 %s: %s → %s", self._settings_key, self._attr_current_option, new_value)
                self._attr_current_option = new_value
                self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        command = self._commands.get(option)
        if command is None:
            _LOGGER.error("未知选项: %s", option)
            return

        _LOGGER.debug("选择 %s = %s", self._attr_translation_key, option)
        await self._coordinator.async_send_command(command)
        self._attr_current_option = option
        self.async_write_ha_state()
