# Smart Helmet — 智能头盔语音助手系统

基于 Quectel EC800 模组的嵌入式智能头盔方案，支持语音唤醒对话、骑行导航、MQTT 远程监控。

## 项目结构

```
├── src/                    # 嵌入式端 (QuecPython / EC800 模组)
│   ├── _main.py            # 主程序入口
│   ├── thingscloud.py      # MQTT 客户端
│   ├── protocol.py         # WebSocket 协议
│   ├── utils.py            # 音频/充电/网络/串口管理
│   ├── helmet_test.py      # 高德地图 API + 导航
│   ├── threading.py        # 并发原语 (MicroPython)
│   └── readme.md           # 嵌入式端详细文档
├── mqtt_server/            # MQTT Broker (Python asyncio)
│   ├── broker.py           # Broker 核心
│   ├── data_handler.py     # 数据处理管道
│   ├── config.py           # 配置中心
│   └── run.py              # 启动入口
├── android_app/            # Android 监控 App (Kotlin + Compose)
│   └── app/src/main/java/com/helmet/monitor/
├── tests/                  # 测试工具
│   └── uart_slave_simulator.py  # 串口下位机模拟器
├── start_mqtt.bat          # Windows 一键启动 Broker
└── CHANGELOG.md            # 更新日志
```

## 快速开始

### 1. 启动 MQTT Broker

```bash
# Windows: 双击 start_mqtt.bat
# Linux/macOS:
cd mqtt_server && python run.py
```

### 2. 模拟设备数据

```bash
pip install paho-mqtt
python tests/uart_slave_simulator.py COM3
# 按 r 开始 GPS 轨迹，按 d 开始传感器上报
```

### 3. Android App

用 Android Studio 打开 `android_app/`，Sync → Run。

连接地址见 `MqttManager.kt`：
- 本地模拟器: `tcp://10.0.2.2:1883`
- 内网穿透: `tcp://frp-run.com:18830`

## MQTT 主题

| 主题 | 方向 | 用途 |
|------|------|------|
| `helmet/{id}/attributes` | 设备→服务器 | 属性上报 (GPS/体温/心率) |
| `helmet/{id}/events` | 设备→服务器 | 事件上报 (上线/离线) |
| `helmet/{id}/data/processed` | 服务器→App | 管道处理后数据 |
| `helmet/{id}/alerts` | 服务器→App | 告警消息 |
| `helmet/{id}/commands` | App→设备 | 下行指令 |

## 技术栈

| 层 | 方案 |
|----|------|
| 嵌入式 | QuecPython + EC800 |
| MQTT Broker | Python asyncio (自研) |
| Android | Kotlin + Jetpack Compose + Paho MQTT |
| 地图 | 高德 3D Map SDK (原生 GL) |
| 穿透 | frp (内网穿透) |
