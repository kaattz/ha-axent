"""BLE connection coordinator for AXENT Smart Toilet."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
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

# 工厂码（默认值 0x30 = 48）
FACTORY_CODE = 0x30

# 校验字节位置
_CHECKSUM_POS = 29


def _xor_checksum(frame: bytearray) -> int:
    """计算 XOR 校验: XOR(bytes[2:29])"""
    xor = 0
    for b in frame[2:29]:
        xor ^= b
    return xor


def _build_command(cmd_type: int, cmd_value: int) -> bytes:
    """构造 AXENT BLE 控制命令帧。

    帧结构 (32 bytes):
      [0]     帧头: 0x02
      [1]     帧类型: 0x0A (Write 命令) — 回传帧为 0x0E
      [2]     工厂码: 0x30
      [3]     命令类型
      [4]     命令参数
      [5]     命令校验: byte[3] + byte[4]
      [6-8]   固定 0x00
      [9]     工厂码: 0x30
      [10-23] 全部 0x00
      [24]    时间编码: (星期 << 5) + 小时
      [25]    分钟
      [26-28] 固定 0x00
      [29]    帧校验: XOR(bytes[2:29])
      [30]    帧尾1: 0x0B
      [31]    帧尾2: 0x04
    """
    now = datetime.now()
    weekday = now.isoweekday()  # 1=Monday ... 7=Sunday
    hour = now.hour
    minute = now.minute
    time_byte = (weekday << 5) + hour

    frame = bytearray(32)
    frame[0] = 0x02
    frame[1] = 0x0A
    frame[2] = FACTORY_CODE
    frame[3] = cmd_type
    frame[4] = cmd_value
    frame[5] = (cmd_type + cmd_value) & 0xFF
    # [6-8] = 0x00
    frame[9] = FACTORY_CODE
    # [10-23] = 0x00
    frame[24] = time_byte & 0xFF
    frame[25] = minute & 0xFF
    # [26-28] = 0x00
    frame[29] = _xor_checksum(frame)
    frame[30] = 0x0B
    frame[31] = 0x04
    return bytes(frame)


# 命令定义：(cmd_type, cmd_value)
COMMANDS = {
    # 动作类
    "stop":         (0x00, 0x00),
    "flush_small":  (0x09, 0x01),
    "flush_large":  (0x09, 0x02),
    "wash_rear":    (0x41, 0x34),
    "wash_front":   (0x42, 0x34),
    "dry":          (0x04, 0x25),
    "nozzle_clean": (0x43, 0x50),
    # 盖板
    "lid_close":    (0x07, 0x00),
    "lid_half":     (0x07, 0x01),
    "lid_full":     (0x07, 0x02),
    # 活水置换
    "fresh_start":  (0x2A, 0x02),
    "fresh_stop":   (0x2A, 0x01),
    # 夜灯
    "nightlight_off":   (0x06, 0x00),
    "nightlight_on":    (0x06, 0x01),
    "nightlight_smart": (0x06, 0x02),
    # 自动翻盖
    "auto_lid_off":     (0x08, 0x00),
    "auto_lid_half":    (0x08, 0x01),
    "auto_lid_full":    (0x08, 0x02),
    # 除臭
    "deodorize_on":     (0x05, 0x01),
    "deodorize_off":    (0x05, 0x00),
    # 自动关盖
    "auto_close_on":    (0x0A, 0x01),
    "auto_close_off":   (0x0A, 0x00),
    # 声波清洗
    "sonic_1d":   (0x15, 0x00),
    "sonic_2d":   (0x15, 0x0C),
    "sonic_3d":   (0x15, 0x03),
    # 感应距离
    "sensor_far":    (0x0B, 0x00),
    "sensor_medium": (0x0B, 0x01),
    "sensor_near":   (0x0B, 0x02),
    # 水温
    "water_temp_1": (0x01, 0x00),
    "water_temp_2": (0x01, 0x01),
    "water_temp_3": (0x01, 0x02),
    "water_temp_4": (0x01, 0x03),
    "water_temp_5": (0x01, 0x04),
    # 水量
    "water_vol_1": (0x02, 0x00),
    "water_vol_2": (0x02, 0x01),
    "water_vol_3": (0x02, 0x02),
    "water_vol_4": (0x02, 0x03),
    "water_vol_5": (0x02, 0x04),
    # 喷嘴位置
    "nozzle_1": (0x03, 0x00),
    "nozzle_2": (0x03, 0x01),
    "nozzle_3": (0x03, 0x02),
    "nozzle_4": (0x03, 0x03),
    "nozzle_5": (0x03, 0x04),
    # 座温
    "seat_temp_1": (0x10, 0x00),
    "seat_temp_2": (0x10, 0x01),
    "seat_temp_3": (0x10, 0x02),
    "seat_temp_4": (0x10, 0x03),
    "seat_temp_5": (0x10, 0x04),
    # 智能节电
    "power_save_on":  (0x0C, 0x01),
    "power_save_off": (0x0C, 0x00),
    # 自动冲水
    "auto_flush_on":  (0x0D, 0x01),
    "auto_flush_off": (0x0D, 0x00),
    # 关盖冲水
    "flush_on_close_on":  (0x0E, 0x01),
    "flush_on_close_off": (0x0E, 0x00),
    # 冲水延时
    "flush_delay_off": (0x0F, 0x00),
    "flush_delay_5s":  (0x0F, 0x01),
    "flush_delay_10s": (0x0F, 0x02),
    "flush_delay_15s": (0x0F, 0x03),
}


class AxentCoordinator:
    """管理与 AXENT 智能马桶的 BLE 连接和通信。"""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
    ) -> None:
        self.hass = hass
        self.address = address
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._occupancy_callbacks: list[Callable[[bool], None]] = []
        self._seated_callbacks: list[Callable[[bool], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []
        self._connected = False
        self._occupied: bool | None = None
        self._seated: bool | None = None

    @property
    def is_connected(self) -> bool:
        """Return True if BLE client is connected."""
        return self._client is not None and self._client.is_connected

    @property
    def is_occupied(self) -> bool | None:
        """Return True if proximity detected, None if unknown."""
        return self._occupied

    @property
    def is_seated(self) -> bool | None:
        """Return True if someone is seated, None if unknown."""
        return self._seated

    def register_occupancy_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """注册人体接近回调（毫米波雷达 02-9F 帧），返回取消注册的函数。"""
        self._occupancy_callbacks.append(callback_fn)

        def unregister() -> None:
            self._occupancy_callbacks.remove(callback_fn)

        return unregister

    def register_seated_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """注册就座状态回调（02-0E 帧 byte[20] bit 0），返回取消注册的函数。"""
        self._seated_callbacks.append(callback_fn)

        def unregister() -> None:
            self._seated_callbacks.remove(callback_fn)

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

            # 扫描并记录所有 GATT 服务和特征
            for service in self._client.services:
                _LOGGER.info(
                    "GATT 服务: %s", service.uuid
                )
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    _LOGGER.info(
                        "  特征: %s [%s] handle=%d",
                        char.uuid, props, char.handle
                    )

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

        parsed = parse_notification(data)
        if parsed is None:
            return

        event = parsed.get("event")

        # 毫米波雷达接近检测 (02-9F 帧)
        if event == "occupancy":
            occupied = parsed["occupied"]
            self._occupied = occupied
            for cb in self._occupancy_callbacks:
                try:
                    cb(occupied)
                except Exception:
                    _LOGGER.exception("人体感应回调执行失败")

        # 控制回传帧中的就座状态 (02-0E 帧, byte[20] bit 0)
        if event == "status" and "seated" in parsed:
            seated = parsed["seated"]
            if seated != self._seated:
                self._seated = seated
                _LOGGER.info("就座状态变化: %s", "已就座" if seated else "已离座")
                for cb in self._seated_callbacks:
                    try:
                        cb(seated)
                    except Exception:
                        _LOGGER.exception("就座状态回调执行失败")

    async def async_send_command(self, command: bytes | str) -> None:
        """发送控制命令到马桶。

        command 可以是:
        - str: 命令名（如 "flush_small"），会基于设备模板动态构建
        - bytes: 原始命令帧（向后兼容）
        """
        self._cancel_disconnect_timer()

        if not self.is_connected:
            await self.async_connect()

        if self._client is None:
            raise BleakError("BLE 客户端未初始化")

        if isinstance(command, str):
            cmd_def = COMMANDS.get(command)
            if cmd_def is None:
                _LOGGER.error("未知命令名: %s", command)
                return
            frame = _build_command(cmd_def[0], cmd_def[1])
        else:
            # 向后兼容：原始 bytes 命令
            frame = command

        _LOGGER.debug(
            "发送命令: %s → %s", frame.hex("-"), CHAR_WRITE_UUID
        )
        try:
            await self._client.write_gatt_char(
                CHAR_WRITE_UUID, frame, response=True
            )
            _LOGGER.debug("命令写入成功 (with response)")
        except Exception as err:
            _LOGGER.warning(
                "write_gatt_char(response=True) 失败: %s，尝试 response=False", err
            )
            await self._client.write_gatt_char(
                CHAR_WRITE_UUID, frame, response=False
            )
            _LOGGER.debug("命令写入成功 (without response)")

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
