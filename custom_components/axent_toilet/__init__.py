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

    # 从 config entry 恢复已保存的设备模板
    saved_hex = entry.data.get("device_template")
    saved_template = bytes.fromhex(saved_hex) if saved_hex else None

    def _on_template_discovered(template: bytes) -> None:
        """设备模板首次发现时持久化保存到 config entry。"""
        new_hex = template.hex()
        if saved_hex == new_hex:
            return
        _LOGGER.info("持久化设备模板: %s", template.hex("-"))
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, "device_template": new_hex},
        )

    coordinator = AxentCoordinator(
        hass,
        address,
        device_template=saved_template,
        on_template_discovered=_on_template_discovered,
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
