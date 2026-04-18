"""BLE connection coordinator for AXENT Smart Toilet."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback

from .const import (
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    DISCONNECT_DELAY,
)
from .protocol import parse_notification

_LOGGER = logging.getLogger(__name__)


class AxentCoordinator:
    """管理与 AXENT 智能马桶的 BLE 连接和通信。"""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._occupancy_callbacks: list[Callable[[bool], None]] = []
        self._connected = False
        self._occupied: bool | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if BLE client is connected."""
        return self._client is not None and self._client.is_connected

    @property
    def is_occupied(self) -> bool | None:
        """Return True if seat is occupied, None if unknown."""
        return self._occupied

    def register_occupancy_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """注册人体感应回调，返回取消注册的函数。"""
        self._occupancy_callbacks.append(callback_fn)

        def unregister() -> None:
            self._occupancy_callbacks.remove(callback_fn)

        return unregister

    async def async_connect(self) -> None:
        """建立 BLE 连接并订阅 Notify。"""
        async with self._connect_lock:
            if self.is_connected:
                return

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise BleakError(
                    f"找不到 BLE 设备: {self.address}"
                )

            self._client = BleakClient(
                ble_device,
                disconnected_callback=self._on_disconnect,
            )
            await self._client.connect()
            _LOGGER.info("已连接到 AXENT 马桶: %s", self.address)

            # 订阅 Notify 特征
            await self._client.start_notify(
                CHAR_NOTIFY_UUID, self._on_notification
            )
            _LOGGER.debug("已订阅 Notify 特征: %s", CHAR_NOTIFY_UUID)
            self._connected = True

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """BLE 断开回调。"""
        _LOGGER.warning("AXENT 马桶 BLE 连接已断开: %s", self.address)
        self._connected = False

    def _on_notification(
        self, sender: Any, data: bytearray
    ) -> None:
        """处理 Notify 回包。"""
        _LOGGER.debug(
            "收到 Notify 数据 (sender=%s): %s", sender, data.hex("-")
        )

        parsed = parse_notification(data)
        if parsed is None:
            return

        if parsed.get("event") == "occupancy":
            occupied = parsed["occupied"]
            self._occupied = occupied
            for cb in self._occupancy_callbacks:
                try:
                    cb(occupied)
                except Exception:
                    _LOGGER.exception("人体感应回调执行失败")

    async def async_send_command(self, command: bytes) -> None:
        """发送控制命令到马桶。"""
        self._cancel_disconnect_timer()

        if not self.is_connected:
            await self.async_connect()

        if self._client is None:
            raise BleakError("BLE 客户端未初始化")

        _LOGGER.debug(
            "发送命令: %s → %s", command.hex("-"), CHAR_WRITE_UUID
        )
        await self._client.write_gatt_char(
            CHAR_WRITE_UUID, command, response=False
        )

        # 命令发送后启动自动断开计时器
        self._schedule_disconnect()

    def _schedule_disconnect(self) -> None:
        """在空闲一段时间后自动断开连接以节省资源。"""
        self._cancel_disconnect_timer()

        self._disconnect_timer = self.hass.loop.call_later(
            DISCONNECT_DELAY, lambda: asyncio.ensure_future(self.async_disconnect())
        )

    def _cancel_disconnect_timer(self) -> None:
        """取消自动断开计时器。"""
        if self._disconnect_timer is not None:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None

    async def async_disconnect(self) -> None:
        """断开 BLE 连接。"""
        self._cancel_disconnect_timer()
        if self._client is not None and self._client.is_connected:
            try:
                await self._client.disconnect()
            except BleakError:
                _LOGGER.debug("断开连接时出错（忽略）", exc_info=True)
            finally:
                self._client = None
                self._connected = False
                _LOGGER.info("已断开 AXENT 马桶连接: %s", self.address)
