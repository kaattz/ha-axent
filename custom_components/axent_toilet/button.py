"""Button platform for AXENT Smart Toilet."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_DRY,
    CMD_FLUSH_LARGE,
    CMD_FLUSH_SMALL,
    CMD_NOZZLE_CLEAN_ON,
    CMD_STOP,
    CMD_WASH_FRONT,
    CMD_WASH_REAR,
    DOMAIN,
)
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

BUTTON_DESCRIPTIONS: list[dict] = [
    {
        "key": "stop",
        "name": "停止",
        "icon": "mdi:stop-circle-outline",
        "command": CMD_STOP,
    },
    {
        "key": "flush_small",
        "name": "小冲",
        "icon": "mdi:water-outline",
        "command": CMD_FLUSH_SMALL,
    },
    {
        "key": "flush_large",
        "name": "大冲",
        "icon": "mdi:water",
        "command": CMD_FLUSH_LARGE,
    },
    # 以下三个功能需要人坐在马桶上才能运行
    {
        "key": "wash_rear",
        "name": "臀洗",
        "icon": "mdi:shower-head",
        "command": CMD_WASH_REAR,
        "requires_occupancy": True,
    },
    {
        "key": "wash_front",
        "name": "妇洗",
        "icon": "mdi:shower",
        "command": CMD_WASH_FRONT,
        "requires_occupancy": True,
    },
    {
        "key": "dry",
        "name": "烘干",
        "icon": "mdi:hair-dryer",
        "command": CMD_DRY,
        "requires_occupancy": True,
    },
    {
        "key": "nozzle_clean",
        "name": "喷嘴自洁",
        "icon": "mdi:spray",
        "command": CMD_NOZZLE_CLEAN_ON,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up AXENT toilet button entities."""
    coordinator: AxentCoordinator = entry.runtime_data

    entities = [
        AxentButton(coordinator, entry, desc)
        for desc in BUTTON_DESCRIPTIONS
    ]
    async_add_entities(entities)


class AxentButton(ButtonEntity):
    """Representation of an AXENT toilet action button."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AxentCoordinator,
        entry: ConfigEntry,
        description: dict,
    ) -> None:
        self._coordinator = coordinator
        self._command = description["command"]
        self._requires_occupancy = description.get("requires_occupancy", False)

        self._attr_unique_id = f"{entry.data['address']}_{description['key']}"
        self._attr_translation_key = description["key"]
        self._attr_icon = description["icon"]
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.data["address"])},
            "name": entry.data.get("name", "AXENT Smart Toilet"),
            "manufacturer": "AXENT",
            "model": "Smart Toilet",
        }

    async def async_press(self) -> None:
        """Handle the button press."""
        if self._requires_occupancy and not self._coordinator.is_occupied:
            raise HomeAssistantError(
                f"{self._attr_translation_key} 需要人坐在马桶上才能使用"
            )

        _LOGGER.debug(
            "按下按钮: %s", self._attr_translation_key
        )
        await self._coordinator.async_send_command(self._command)
