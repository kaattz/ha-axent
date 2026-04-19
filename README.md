# AXENT Smart Toilet – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

通过 **蓝牙低功耗（BLE）** 将恩仕（AXENT）智能马桶接入 Home Assistant，实现全功能本地控制与状态监测。

---

## ✨ 功能特性

| 类型 | 功能 | HA 实体 |
|------|------|---------|
| 🚿 **冲洗** | 大冲 / 小冲 | Button |
| 🧼 **清洗** | 臀洗 / 妇洗（需入座） | Button |
| 💨 **烘干** | 暖风烘干（需入座） | Button |
| 🧹 **自洁** | 喷嘴自洁 | Button |
| ⏹ **停止** | 停止当前操作 | Button |
| 🚽 **盖板** | 全关 / 单开 / 全开 | Select |
| 🌙 **夜灯** | 关闭 / 常开 / 智能 | Select |
| 🔄 **自动翻盖** | 关闭 / 单开 / 全开 | Select |
| 🔊 **声波清洗** | 1D / 2D / 3D | Select |
| 📏 **感应距离** | 远 / 中 / 近 | Select |
| 🌡️ **水温** | 1~5 档 | Select |
| 💧 **水量** | 1~5 档 | Select |
| 🎯 **喷嘴位置** | 1~5 档 | Select |
| 🔥 **座温** | 1~5 档 | Select |
| ⏱️ **冲水延时** | 关闭 / 5s / 10s / 15s | Select |
| 💨 **自动除臭** | 开 / 关 | Switch |
| 🪑 **自动关盖** | 开 / 关 | Switch |
| 💦 **活水置换** | 启动 / 停止 | Switch |
| 🍃 **智能节电** | 开 / 关 | Switch |
| 🚽 **自动冲水** | 开 / 关 | Switch |
| 🔽 **关盖冲水** | 开 / 关 | Switch |
| 🪑 **就座状态** | 已就座 / 已离座（毫米波雷达） | Binary Sensor |
| 🔗 **BLE 连接** | 已连接 / 已断开 | Binary Sensor |

> **入座保护**：臀洗、妇洗、烘干功能仅在检测到用户入座时可用，防止误触发。

---

## 📦 安装

### 方式一：HACS（推荐）

1. 打开 HACS → **集成** → 右上角 **⋮** → **自定义存储库**
2. 输入 `https://github.com/kaattz/ha-axent`，类别选择 **Integration**
3. 搜索 **AXENT Smart Toilet** 并安装
4. 重启 Home Assistant

### 方式二：手动安装

```bash
# 将 custom_components/axent_toilet 复制到你的 HA 配置目录
cp -r custom_components/axent_toilet /config/custom_components/
```

重启 Home Assistant。

---

## ⚙️ 配置

### 自动发现

如果你的 Home Assistant 主机配有蓝牙适配器，集成会自动发现附近的 AXENT 智能马桶（基于 BLE Service UUID `0000FFF0` 或设备名称 `AXENT*`）。发现后确认即可完成配置。

### 手动配置

1. 进入 **设置** → **设备与服务** → **添加集成**
2. 搜索 **AXENT Smart Toilet**
3. 输入马桶的蓝牙 MAC 地址（如 `AA:BB:CC:DD:EE:FF`）
4. 可选填写设备名称

---

## 🏗️ 架构

```
custom_components/axent_toilet/
├── __init__.py          # 集成入口，生命周期管理
├── config_flow.py       # 配置流程（蓝牙发现 + 手动输入）
├── const.py             # 常量定义（BLE UUID、事件标识）
├── coordinator.py       # BLE 连接管理 + 命令帧构造
├── protocol.py          # Notify 回包解析（状态帧 + 传感器帧）
├── button.py            # 按钮实体（冲洗/清洗/烘干/自洁/停止）
├── select.py            # 选择器实体（盖板/夜灯/翻盖/声波/感应距离/水温/水量/位置/座温/冲水延时）
├── switch.py            # 开关实体（自动除臭/关盖/活水置换/节电/冲水/关盖冲水）
├── binary_sensor.py     # 二值传感器（就座状态 + BLE 连接）
├── manifest.json        # 集成清单
├── strings.json         # 英文翻译
└── translations/
    ├── en.json           # English
    └── zh-Hans.json      # 简体中文
```

### 连接管理策略

- **常驻连接**：启动后保持 BLE 连接，持续接收 Notify 状态帧
- **自动重连**：断线后每 **30 秒** 自动尝试重连
- **Notify 订阅**：连接后立即订阅 `FFF1` 特征，实时接收就座状态推送

> **注意**：BLE 常连期间手机 AXENT Remote APP 无法同时连接马桶。

---

## 📡 BLE 协议概述

通信基于 BLE GATT，使用自定义 Service `0000FFF0`：

| 通道 | UUID | 方向 | 用途 |
|------|------|------|------|
| Write | `0000FFF2` | HA → 马桶 | 发送控制命令 |
| Notify | `0000FFF1` | 马桶 → HA | 状态事件上报 |

### 帧结构

所有帧均为 **32 字节**，帧头帧尾区分方向：

| 方向 | 帧头 | 帧尾 | 说明 |
|------|------|------|------|
| 手机→马桶（Write） | `02-0A` | `0B-04` | 控制命令帧 |
| 马桶→手机（Notify） | `02-0E` | `0F-04` | 控制回传 / 状态帧 |
| 马桶→手机（Notify） | `02-9F` | `0B-04` | 传感器事件帧（就座检测） |

### 命令帧构造

```text
[0]  0x02          帧头
[1]  0x0A          Write 帧类型
[2]  0x30          工厂码
[3]  CMD_TYPE      命令类型
[4]  CMD_VALUE     命令参数
[5]  CMD_TYPE + CMD_VALUE  命令校验
[6-8]  0x00        固定零
[9]  0x30          工厂码
[10-23] 0x00       固定零
[24] TIME_BYTE     (星期 << 5) + 小时
[25] MINUTE        当前分钟
[26-28] 0x00       固定零
[29] XOR_CHECKSUM  XOR(bytes[2:29])
[30] 0x0B          帧尾1
[31] 0x04          帧尾2
```

### 就座检测

设备搭载 **毫米波雷达**，就座状态由两种帧共同驱动：

| 数据来源 | 说明 |
|---------|------|
| `02-9F` 传感器帧 | 坐下/离座事件（毫米波雷达检测） |
| `02-0E` 控制帧 byte[20] bit 0 | 状态同步（1=就座，0=无人） |

> **关于人体接近**：人走近马桶时翻盖由马桶固件内部驱动，不通过 BLE 发送 Notify，因此无法在 HA 端检测接近状态。如需接近检测，建议外接独立 mmWave 传感器（如 LD2410）。

详细协议文档请参阅 [axent_toilet_full_protocol.md](axent_toilet_full_protocol.md)。

---

## 🤖 自动化示例

### 离座自动冲水

```yaml
automation:
  - alias: "离座自动小冲"
    trigger:
      - platform: state
        entity_id: binary_sensor.axent_smart_toilet_seat_seated
        from: "on"
        to: "off"
        for: "00:00:05"
    action:
      - service: button.press
        target:
          entity_id: button.axent_smart_toilet_small_flush
```

### 夜间智能夜灯

```yaml
automation:
  - alias: "夜间启用智能夜灯"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.axent_smart_toilet_night_light
        data:
          option: "smart"
```


---

## 🔧 已知限制

- **设置类命令无状态回报**：Write 控制命令没有确认回包，Select 和 Switch 实体状态仅反映最近一次操作
- **人体接近不可检测**：人走近马桶时的翻盖动作由固件内部完成，不通过 BLE 通知
- **BLE 独占**：常连模式下手机 APP 无法同时连接马桶
- 需要 Home Assistant 主机配备蓝牙适配器（内置或外接 USB）
- BLE 通信距离受环境影响，建议马桶与 HA 主机距离不超过 10 米

---

## 📄 许可证

MIT License

---

## 🙏 致谢

- [Home Assistant](https://www.home-assistant.io/) — 开源智能家居平台
- [Bleak](https://github.com/hbldh/bleak) — 跨平台 BLE 通信库
- AXENT（恩仕） — 智能卫浴产品
