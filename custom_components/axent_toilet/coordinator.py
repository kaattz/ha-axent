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

# 设备标识字节在帧中的位置 [11:16]（5 字节）
_DEVICE_ID_SLICE = slice(11, 16)
# 校验字节位置
_CHECKSUM_POS = 29


def _patch_command(command: bytes, device_id: bytes) -> bytes:
    """用实际设备标识替换命令帧中的硬编码字节，并重算校验。

    帧结构:
      [0-1]  头部: 02-0E 或 02-9F
      [2-10] 命令区
      [11-15] 设备标识（5 字节，因设备而异）
      [16-28] 参数区
      [29]   校验: XOR(bytes[2:29])
      [30-31] 尾部: 0F-04
    """
    frame = bytearray(command)
    # 注入设备标识
    frame[_DEVICE_ID_SLICE] = device_id
    # 重算校验: XOR bytes[2] 到 bytes[28]
    xor = 0
    for b in frame[2:29]:
        xor ^= b
    frame[_CHECKSUM_POS] = xor
    return bytes(frame)


class AxentCoordinator:
    """管理与 AXENT 智能马桶的 BLE 连接和通信。"""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        device_id: bytes | None = None,
        on_device_id_discovered: Callable[[bytes], None] | None = None,
    ) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._occupancy_callbacks: list[Callable[[bool], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []
        self._connected = False
        self._occupied: bool | None = None
        self._device_id: bytes | None = device_id
        self._on_device_id_discovered = on_device_id_discovered

        if device_id is not None:
            _LOGGER.info(
                "使用已保存的设备标识: %s", device_id.hex("-")
            )

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

    def register_connection_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """注册连接状态回调，返回取消注册的函数。"""
        self._connection_callbacks.append(callback_fn)

        def unregister() -> None:
            self._connection_callbacks.remove(callback_fn)

        return unregister

    def _notify_connection_state(self, connected: bool) -> None:
        """通知所有连接状态回调。"""
        self._connected = connected
        for cb in self._connection_callbacks:
            try:
                cb(connected)
            except Exception:
                _LOGGER.exception("连接状态回调执行失败")

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
            self._notify_connection_state(True)

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """BLE 断开回调。"""
        _LOGGER.warning("AXENT 马桶 BLE 连接已断开: %s", self.address)
        self._notify_connection_state(False)

    def _on_notification(
        self, sender: Any, data: bytearray
    ) -> None:
        """处理 Notify 回包。"""
        _LOGGER.debug(
            "收到 Notify 数据 (sender=%s): %s", sender, data.hex("-")
        )

        # 从任意控制帧中提取设备标识（仅首次）
        if self._device_id is None and len(data) >= 16:
            if data[0] == 0x02 and data[1] in (0x0E, 0x9F):
                self._device_id = bytes(data[_DEVICE_ID_SLICE])
                _LOGGER.info(
                    "已提取设备标识: %s", self._device_id.hex("-")
                )
                # 通知上层持久化保存
                if self._on_device_id_discovered is not None:
                    self._on_device_id_discovered(self._device_id)

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

        # 用设备实际标识替换命令帧中的硬编码字节
        if self._device_id is not None:
            patched = _patch_command(command, self._device_id)
        else:
            patched = command
            _LOGGER.warning("设备标识未获取，使用原始命令帧")

        _LOGGER.debug(
            "发送命令: %s → %s", patched.hex("-"), CHAR_WRITE_UUID
        )
        await self._client.write_gatt_char(
            CHAR_WRITE_UUID, patched, response=False
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
                self._notify_connection_state(False)
                _LOGGER.info("已断开 AXENT 马桶连接: %s", self.address)
