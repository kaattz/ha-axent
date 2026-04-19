"""The AXENT Smart Toilet integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import AxentCoordinator

_LOGGER = logging.getLogger(__name__)

type AxentConfigEntry = ConfigEntry[AxentCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: AxentConfigEntry
) -> bool:
    """Set up AXENT Smart Toilet from a config entry."""
    address = entry.data["address"]
    _LOGGER.info("正在设置 AXENT 智能马桶: %s", address)

    coordinator = AxentCoordinator(hass, address)

    # 启动常连模式（自动连接 + 断线重连）
    try:
        await coordinator.async_start()
    except Exception:
        _LOGGER.warning(
            "初始连接失败，将自动重连: %s", address, exc_info=True
        )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AxentConfigEntry
) -> bool:
    """Unload AXENT Smart Toilet config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        coordinator: AxentCoordinator = entry.runtime_data
        await coordinator.async_disconnect()

    return unload_ok
