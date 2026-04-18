"""Config flow for AXENT Smart Toilet integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class AxentToiletConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AXENT Smart Toilet."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.debug(
            "发现蓝牙设备: %s (%s)",
            discovery_info.name,
            discovery_info.address,
        )

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovery_info = discovery_info
        self._address = discovery_info.address
        self._name = discovery_info.name or "AXENT Smart Toilet"

        self.context["title_placeholders"] = {"name": self._name}

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm bluetooth discovery."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or "AXENT Smart Toilet",
                data={
                    "address": self._address,
                    "name": self._name,
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._name},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated configuration (manual MAC input)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["address"].upper().strip()

            # 基本 MAC 地址格式验证
            if len(address.replace(":", "").replace("-", "")) != 12:
                errors["address"] = "invalid_mac"
            else:
                # 统一为冒号分隔格式
                clean = address.replace("-", "").replace(":", "")
                address = ":".join(
                    clean[i : i + 2] for i in range(0, 12, 2)
                )

                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=user_input.get("name", "AXENT Smart Toilet"),
                    data={
                        "address": address,
                        "name": user_input.get("name", "AXENT Smart Toilet"),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): str,
                    vol.Optional(
                        "name", default="AXENT Smart Toilet"
                    ): str,
                }
            ),
            errors=errors,
        )
