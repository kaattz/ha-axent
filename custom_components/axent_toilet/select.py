"""Select platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_AUTO_LID_FULL,
    CMD_AUTO_LID_HALF,
    CMD_AUTO_LID_OFF,
    CMD_FLUSH_DELAY_5S,
    CMD_FLUSH_DELAY_10S,
    CMD_FLUSH_DELAY_15S,
    CMD_FLUSH_DELAY_OFF,
    CMD_LID_CLOSE,
    CMD_LID_FULL_OPEN,
    CMD_LID_HALF_OPEN,
    CMD_NIGHTLIGHT_OFF,
    CMD_NIGHTLIGHT_ON,
    CMD_NIGHTLIGHT_SMART,
    CMD_NOZZLE_POS_1,
    CMD_NOZZLE_POS_2,
    CMD_NOZZLE_POS_3,
    CMD_NOZZLE_POS_4,
    CMD_NOZZLE_POS_5,
    CMD_SEAT_TEMP_1,
    CMD_SEAT_TEMP_2,
    CMD_SEAT_TEMP_3,
    CMD_SEAT_TEMP_4,
    CMD_SEAT_TEMP_5,
    CMD_SENSOR_RANGE_FAR,
    CMD_SENSOR_RANGE_MEDIUM,
    CMD_SENSOR_RANGE_NEAR,
    CMD_SONIC_1D,
    CMD_SONIC_2D,
    CMD_SONIC_3D,
    CMD_WATER_TEMP_1,
    CMD_WATER_TEMP_2,
    CMD_WATER_TEMP_3,
    CMD_WATER_TEMP_4,
    CMD_WATER_TEMP_5,
    CMD_WATER_VOLUME_1,
    CMD_WATER_VOLUME_2,
    CMD_WATER_VOLUME_3,
    CMD_WATER_VOLUME_4,
    CMD_WATER_VOLUME_5,
    DOMAIN,
)
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

SELECT_DESCRIPTIONS: list[dict] = [
    {
        "key": "lid_position",
        "name": "盖板控制",
        "icon": "mdi:seat-outline",
        "options": ["closed", "half_open", "full_open"],
        "option_labels": {
            "closed": "全关",
            "half_open": "单开",
            "full_open": "全开",
        },
        "commands": {
            "closed": CMD_LID_CLOSE,
            "half_open": CMD_LID_HALF_OPEN,
            "full_open": CMD_LID_FULL_OPEN,
        },
    },
    {
        "key": "nightlight_mode",
        "name": "夜灯模式",
        "icon": "mdi:lightbulb-night-outline",
        "options": ["off", "on", "smart"],
        "option_labels": {
            "off": "关闭",
            "on": "常开",
            "smart": "智能",
        },
        "commands": {
            "off": CMD_NIGHTLIGHT_OFF,
            "on": CMD_NIGHTLIGHT_ON,
            "smart": CMD_NIGHTLIGHT_SMART,
        },
    },
    {
        "key": "auto_lid_mode",
        "name": "自动翻盖",
        "icon": "mdi:arrow-up-down",
        "options": ["off", "half_open", "full_open"],
        "option_labels": {
            "off": "关闭",
            "half_open": "单开",
            "full_open": "全开",
        },
        "commands": {
            "off": CMD_AUTO_LID_OFF,
            "half_open": CMD_AUTO_LID_HALF,
            "full_open": CMD_AUTO_LID_FULL,
        },
    },
    {
        "key": "sonic_wash_mode",
        "name": "声波清洗模式",
        "icon": "mdi:sine-wave",
        "options": ["1d", "2d", "3d"],
        "option_labels": {
            "1d": "1D",
            "2d": "2D",
            "3d": "3D",
        },
        "commands": {
            "1d": CMD_SONIC_1D,
            "2d": CMD_SONIC_2D,
            "3d": CMD_SONIC_3D,
        },
    },
    {
        "key": "sensor_range",
        "name": "感应距离",
        "icon": "mdi:signal-distance-variant",
        "options": ["far", "medium", "near"],
        "option_labels": {
            "far": "远",
            "medium": "中",
            "near": "近",
        },
        "commands": {
            "far": CMD_SENSOR_RANGE_FAR,
            "medium": CMD_SENSOR_RANGE_MEDIUM,
            "near": CMD_SENSOR_RANGE_NEAR,
        },
    },
    {
        "key": "water_temperature",
        "name": "水温",
        "icon": "mdi:thermometer-water",
        "options": ["1", "2", "3", "4", "5"],
        "option_labels": {
            "1": "1档",
            "2": "2档",
            "3": "3档",
            "4": "4档",
            "5": "5档",
        },
        "commands": {
            "1": CMD_WATER_TEMP_1,
            "2": CMD_WATER_TEMP_2,
            "3": CMD_WATER_TEMP_3,
            "4": CMD_WATER_TEMP_4,
            "5": CMD_WATER_TEMP_5,
        },
    },
    {
        "key": "water_volume",
        "name": "水量",
        "icon": "mdi:water-plus-outline",
        "options": ["1", "2", "3", "4", "5"],
        "option_labels": {
            "1": "1档",
            "2": "2档",
            "3": "3档",
            "4": "4档",
            "5": "5档",
        },
        "commands": {
            "1": CMD_WATER_VOLUME_1,
            "2": CMD_WATER_VOLUME_2,
            "3": CMD_WATER_VOLUME_3,
            "4": CMD_WATER_VOLUME_4,
            "5": CMD_WATER_VOLUME_5,
        },
    },
    {
        "key": "nozzle_position",
        "name": "喷嘴位置",
        "icon": "mdi:spray",
        "options": ["1", "2", "3", "4", "5"],
        "option_labels": {
            "1": "1档",
            "2": "2档",
            "3": "3档",
            "4": "4档",
            "5": "5档",
        },
        "commands": {
            "1": CMD_NOZZLE_POS_1,
            "2": CMD_NOZZLE_POS_2,
            "3": CMD_NOZZLE_POS_3,
            "4": CMD_NOZZLE_POS_4,
            "5": CMD_NOZZLE_POS_5,
        },
    },
    {
        "key": "seat_temperature",
        "name": "座温",
        "icon": "mdi:seat-recline-normal",
        "options": ["1", "2", "3", "4", "5"],
        "option_labels": {
            "1": "1档",
            "2": "2档",
            "3": "3档",
            "4": "4档",
            "5": "5档",
        },
        "commands": {
            "1": CMD_SEAT_TEMP_1,
            "2": CMD_SEAT_TEMP_2,
            "3": CMD_SEAT_TEMP_3,
            "4": CMD_SEAT_TEMP_4,
            "5": CMD_SEAT_TEMP_5,
        },
    },
    {
        "key": "flush_delay",
        "name": "自动冲水延时",
        "icon": "mdi:timer-outline",
        "options": ["off", "5s", "10s", "15s"],
        "option_labels": {
            "off": "关闭",
            "5s": "5秒",
            "10s": "10秒",
            "15s": "15秒",
        },
        "commands": {
            "off": CMD_FLUSH_DELAY_OFF,
            "5s": CMD_FLUSH_DELAY_5S,
            "10s": CMD_FLUSH_DELAY_10S,
            "15s": CMD_FLUSH_DELAY_15S,
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


class AxentSelect(SelectEntity):
    """Representation of an AXENT toilet select entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
        description: dict,
    ) -> None:
        self._coordinator = coordinator
        self._commands: dict[str, bytes] = description["commands"]

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

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        command = self._commands.get(option)
        if command is None:
            _LOGGER.error("未知选项: %s", option)
            return

        _LOGGER.debug(
            "选择 %s = %s", self._attr_translation_key, option
        )
        await self._coordinator.async_send_command(command)
        self._attr_current_option = option
        self.async_write_ha_state()
