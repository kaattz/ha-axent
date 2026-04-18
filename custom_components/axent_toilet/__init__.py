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

    # 从 config entry 恢复已保存的设备标识
    saved_id_hex = entry.data.get("device_id")
    saved_device_id = bytes.fromhex(saved_id_hex) if saved_id_hex else None

    def _on_device_id_discovered(device_id: bytes) -> None:
        """设备标识首次发现时持久化保存到 config entry。"""
        if saved_id_hex == device_id.hex():
            return  # 已保存，无需更新
        _LOGGER.info("持久化设备标识: %s", device_id.hex("-"))
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, "device_id": device_id.hex()},
        )

    coordinator = AxentCoordinator(
        hass,
        address,
        device_id=saved_device_id,
        on_device_id_discovered=_on_device_id_discovered,
    )

    # 尝试初始连接（非阻塞性，失败不影响设置）
    try:
        await coordinator.async_connect()
    except Exception:
        _LOGGER.warning(
            "初始连接失败，将在首次命令时重试: %s", address, exc_info=True
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
