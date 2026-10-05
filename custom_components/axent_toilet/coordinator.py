"""BLE connection coordinator for AXENT Smart Toilet."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from typing import Any, Callable

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    CHAR_NOTIFY_UUID,
    CHAR_WRITE_UUID,
    CONNECT_TIMEOUT,
    CONNECTION_WATCHDOG,
    RECONNECT_INTERVAL,
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
    """管理与 AXENT 智能马桶的 BLE 连接和通信。

    采用常连模式：启动后保持 BLE 连接，持续接收 Notify 帧，
    断线后自动重连。
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.address: str = entry.data["address"]
        self._client: BleakClient | None = None
        self._connect_lock = asyncio.Lock()
        self._connect_task: asyncio.Task | None = None
        self._disconnected = asyncio.Event()
        self._closing = False
        self._occupancy_callbacks: list[Callable[[bool], None]] = []
        self._seated_callbacks: list[Callable[[bool], None]] = []
        self._connection_callbacks: list[Callable[[bool], None]] = []
        self._settings_callbacks: list[Callable[[dict], None]] = []
        self._connected = False
        self._occupied: bool | None = None
        self._seated: bool | None = None
        self._settings: dict | None = None

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
        """注册人体接近回调（02-0E 帧 byte[20]），返回取消注册的函数。"""
        self._occupancy_callbacks.append(callback_fn)

        def unregister() -> None:
            self._occupancy_callbacks.remove(callback_fn)

        return unregister

    def register_seated_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """注册就座状态回调（02-9F 帧），返回取消注册的函数。"""
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

    def register_settings_callback(
        self, callback_fn: Callable[[dict], None]
    ) -> Callable[[], None]:
        """注册设备设置回调（02-0E 主状态帧解析），返回取消注册的函数。"""
        self._settings_callbacks.append(callback_fn)

        def unregister() -> None:
            self._settings_callbacks.remove(callback_fn)

        return unregister

    def _notify_connection_state(self, connected: bool) -> None:
        """通知所有连接状态回调。"""
        self._connected = connected
        for cb in self._connection_callbacks:
            try:
                cb(connected)
            except Exception:
                _LOGGER.exception("连接状态回调执行失败")

    async def async_start(self) -> None:
        """启动常连模式：后台连接 + 断线自动重连。

        本方法必须立即返回：连接与重连都在后台任务中进行。
        若在此处 await 连接，Home Assistant 的启动阶段会等待该任务，
        从而拖长甚至超时 bootstrap（Setup timed out for bootstrap）。
        """
        self._closing = False
        self._schedule_connect()

    async def _try_connect(self) -> None:
        """尝试连接一次，失败后等待下一次重连。"""
        try:
            await self.async_connect()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            # 常连模式下设备离线是常态，warning 保持简洁以免刷屏，
            # 完整堆栈仅在 debug 级别输出。
            _LOGGER.warning(
                "连接 AXENT 马桶失败，%d 秒后重试: %s",
                RECONNECT_INTERVAL,
                err,
            )
            _LOGGER.debug("连接失败详情", exc_info=True)
            await asyncio.sleep(RECONNECT_INTERVAL)

    def _schedule_connect(self) -> None:
        """调度后台连接／重连任务。

        使用 ConfigEntry 的后台任务：它不会阻塞 HA 启动，
        也不会被 async_block_till_done() 等待，并且会在
        config entry 卸载时自动取消。切勿改用 hass.async_create_task，
        那会让 HA 启动一直等到任务结束（本集成因此卡住过 bootstrap）。
        """
        if self._connect_task is not None and not self._connect_task.done():
            return  # 已有连接任务在进行
        self._connect_task = self.entry.async_create_background_task(
            self.hass, self._connect_loop(), "axent_toilet_connect"
        )

    async def _connect_loop(self) -> None:
        """常连主循环：连接 → 等待断线 → 重连，直到集成被卸载。

        与旧实现不同，这里不会在连接失败时退出：循环本身即重连机制，
        因此该任务在集成卸载前始终存活。
        """
        while not self._closing:
            await self._try_connect()
            if not self.is_connected:
                continue  # 连接失败（已 sleep）或立刻掉线，直接重试

            # 连接成功：阻塞等待断线事件，避免空转占用 CPU。
            # 先 clear 再检查，保证“clear 与 wait 之间掉线”也能被捕获。
            self._disconnected.clear()
            if not self.is_connected:
                continue

            # 超时仅作看门狗：若链路静默失效而底层未回调，
            # 超时后回到循环顶部复查 is_connected 并自动重连。
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._disconnected.wait(), timeout=CONNECTION_WATCHDOG
                )

    async def async_connect(self) -> None:
        """建立 BLE 连接并订阅 Notify。"""
        async with self._connect_lock:
            if self.is_connected:
                return

            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                raise BleakError(f"找不到 BLE 设备: {self.address}")

            client = BleakClient(
                ble_device,
                disconnected_callback=self._on_disconnect,
            )
            # 连接+订阅加超时，避免底层 BLE 调用挂死把重连循环永久卡住
            try:
                async with asyncio.timeout(CONNECT_TIMEOUT):
                    await client.connect()
                    _LOGGER.info("已连接到 AXENT 马桶: %s", self.address)

                    # 订阅 Notify 特征
                    await client.start_notify(
                        CHAR_NOTIFY_UUID, self._on_notification
                    )
            except Exception:
                with suppress(Exception):
                    await client.disconnect()
                raise

            _LOGGER.info("已订阅 Notify，持续监听状态帧")
            # 先发布 client 再通知回调，保证回调里读到的是已连接状态
            self._client = client
            self._notify_connection_state(True)

    def _on_disconnect(self, client: BleakClient) -> None:
        """BLE 断开回调 — 自动重连。

        bleak 的断开回调可能由其它线程触发（WinRT / BlueZ 后端均如此），
        因此这里不做任何事件循环操作，统一转回事件循环线程执行，
        避免跨线程修改 asyncio 对象或写入实体状态。
        """
        try:
            self.hass.loop.call_soon_threadsafe(self._handle_disconnect)
        except RuntimeError:
            # 事件循环已关闭（HA 正在退出），无需再重连
            _LOGGER.debug("事件循环已关闭，忽略断开回调")

    @callback
    def _handle_disconnect(self) -> None:
        """在事件循环线程内处理断开：通知实体并唤醒重连循环。"""
        _LOGGER.warning("AXENT 马桶 BLE 连接已断开: %s", self.address)
        self._notify_connection_state(False)
        if not self._closing:
            # 唤醒常连主循环去重连；任务若已存在则仅为兜底
            self._disconnected.set()
            self._schedule_connect()

    def _on_notification(
        self, sender: Any, data: bytearray
    ) -> None:
        """处理 Notify 回包。"""
        _LOGGER.debug(
            "收到 Notify: %s", data.hex("-")
        )

        parsed = parse_notification(data)
        if parsed is None:
            return

        event = parsed.get("event")

        # 02-9F 帧：就座检测（坐下/离座事件）
        if event == "occupancy":
            seated = parsed["occupied"]
            if seated != self._seated:
                self._seated = seated
                _LOGGER.info("就座事件: %s", "坐下" if seated else "离座")
                for cb in self._seated_callbacks:
                    try:
                        cb(seated)
                    except Exception:
                        _LOGGER.exception("就座回调执行失败")

        # 02-0E 帧：就座状态 (byte[20] bit 0)
        if event == "status" and "seated" in parsed:
            occupied = parsed["seated"]
            if occupied != self._occupied:
                self._occupied = occupied
                _LOGGER.info("就座状态(0E帧): %s", "有人" if occupied else "无人")
                for cb in self._occupancy_callbacks:
                    try:
                        cb(occupied)
                    except Exception:
                        _LOGGER.exception("就座回调执行失败")

        # 02-0E 主状态帧：设备设置同步
        if event == "status" and "settings" in parsed:
            self._settings = parsed["settings"]
            _LOGGER.info("收到设备设置: %s", self._settings)
            for cb in self._settings_callbacks:
                try:
                    cb(self._settings)
                except Exception:
                    _LOGGER.exception("设置同步回调执行失败")

    async def async_send_command(self, command: bytes | str) -> None:
        """发送控制命令到马桶。

        command 可以是:
        - str: 命令名（如 "flush_small"），动态构建帧
        - bytes: 原始命令帧（向后兼容）
        """
        if not self.is_connected:
            await self.async_connect()
            # 手动建立连接后，确保断线仍有后台任务负责重连
            self._schedule_connect()

        client = self._client
        if client is None:
            raise BleakError("BLE 客户端未初始化")

        if isinstance(command, str):
            cmd_def = COMMANDS.get(command)
            if cmd_def is None:
                _LOGGER.error("未知命令名: %s", command)
                return
            frame = _build_command(cmd_def[0], cmd_def[1])
        else:
            frame = command

        _LOGGER.debug(
            "发送命令: %s → %s", frame.hex("-"), CHAR_WRITE_UUID
        )
        try:
            await client.write_gatt_char(
                CHAR_WRITE_UUID, frame, response=True
            )
            _LOGGER.debug("命令写入成功 (with response)")
        except Exception as err:
            _LOGGER.warning(
                "write_gatt_char(response=True) 失败: %s，尝试 response=False", err
            )
            await client.write_gatt_char(
                CHAR_WRITE_UUID, frame, response=False
            )
            _LOGGER.debug("命令写入成功 (without response)")

    async def async_disconnect(self) -> None:
        """断开 BLE 连接（仅卸载时调用）。"""
        self._closing = True
        if self._connect_task is not None:
            self._connect_task.cancel()
            self._connect_task = None
        client = self._client
        self._client = None
        if client is not None and client.is_connected:
            with suppress(Exception):
                await client.disconnect()
        self._notify_connection_state(False)
        _LOGGER.info("已断开 AXENT 马桶连接: %s", self.address)
