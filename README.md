# Smart Helmet — 智能头盔语音助手系统

基于 Quectel EC800 模组的嵌入式智能头盔方案，支持语音唤醒对话、骑行导航、MQTT 远程监控。

## 项目结构

```
├── src/                    # 上位机 (QuecPython / EC800 模组)
│   ├── _main.py            # 主入口 + MCP 工具 + 导航 + MQTT
│   ├── mqtt_client.py      # MQTT 客户端
│   ├── protocol.py         # WebSocket 协议 (JSON-RPC + 音频)
│   ├── utils.py            # 音频/充电/网络/串口/UART 收发
│   ├── helmet_test.py      # 高德 API + 导航 (AmapAPI/Navigator)
│   ├── logging.py          # 日志系统
│   └── readme.md           # 📖 嵌入式端详细文档
├── G431/                   # 下位机 (STM32G431CB + Keil MDK)
│   ├── Core/               # HAL 初始化
│   ├── BSP/                # 传感器/OLED/W25Q128 字库驱动
│   ├── Drivers/            # CMSIS + HAL 库
│   └── MDK-ARM/            # Keil 工程文件
├── mqtt_server/            # MQTT Broker (Python asyncio)
│   ├── broker.py           # Broker 核心
│   ├── data_handler.py     # 数据处理管道 (validate→threshold→persist)
│   ├── config.py           # 配置中心 (设备密钥/阈值/主题路由)
│   └── run.py              # 启动入口
├── android_app/            # Android 监控 App (Kotlin + Compose)
│   └── app/src/main/java/com/helmet/monitor/
├── tests/                  # 测试工具
│   └── uart_slave_simulator.py  # 串口下位机模拟器 (Python)
├── fw/                     # EC800 固件
├── start_mqtt.bat          # Windows 一键启动 Broker
└── CHANGELOG.md            # 更新日志
```

## 系统架构

```mermaid
flowchart TB
    subgraph Cloud["☁ 云端"]
        XZ[小智 AI 服务<br/>WebSocket<br/>JSON-RPC + MCP]
    end

    subgraph Local["🏠 本地"]
        MQTT[MQTT Broker<br/>mqtt_server<br/>Python asyncio]
        ANDROID[Android App<br/>Kotlin + Compose<br/>实时数据 / 地图 / 告警]
    end

    subgraph EC800["EC800 上位机 — QuecPython"]
        subgraph SVC["服务层"]
            WS[WebSocket 客户端<br/>protocol.py<br/>MCP 工具调用 + 音频]
            MQTT_C[MqttClient<br/>属性上报 / 事件上报]
            AMAP[AmapAPI<br/>高德骑行路线 / 地理编码]
        end

        subgraph APP["Application 核心"]
            AUDIO[AudioMgr<br/>KWS / VAD / TTS]
            CHARGE[ChargeMgr]
            NET[NetMgr]
            NAV[NavigationMgr<br/>路段跟踪 / 偏航检测<br/>重规划 45s 冷却]
        end

        subgraph THREADS["6 类后台线程"]
            REC[Record 线程<br/>持续采集 Opus]
            WORK[Working 线程<br/>对话主控]
            CHAT[聊天子线程<br/>WS 音频收发]
            PARSE[后台解析线程<br/>异步路线解析]
            GPS_TH[GPS 后台线程<br/>轮询 2s/30s<br/>时间同步 1s<br/>MQTT 定时发布]
            TX_TH[UART TX 线程<br/>Queue 串行化<br/>tick_cb 后备时间]
        end
    end

    subgraph G431["G431 下位机 — STM32G431CB"]
        subgraph LOOP["主循环 — TIM2 驱动"]
            EVERY[sersor_data<br/>MAX30102 FIFO 快排]
            T10[每 10ms<br/>key_scan S1~S4]
            T100[每 100ms<br/>imu_read + 摔倒检测]
            T500[每 500ms<br/>BMP280 + 导航滚动]
            T5S[每 5s<br/>send_sensor_uart<br/>send_imu_uart]
            T5M[每 5min<br/>GPS 测试轨迹推进]
        end

        subgraph SENSORS["传感器"]
            MAX[MAX30102<br/>心率 / 血氧]
            BMP[BMP280<br/>温度 / 气压]
            MPU[MPU6050<br/>六轴 IMU]
            BH[BH1750<br/>光照]
        end

        subgraph DISPLAY["显示 & 存储"]
            OLED[OLED 128×32 I2C<br/>上行: 导航 UTF-8 滚动<br/>下行: 心率 + 时间 + 心情]
            W25Q[W25Q128 SPI Flash<br/>UTF-8 中文字库<br/>16×16 字模二分查表]
        end
    end

    XZ <-->|WebSocket| WS
    WS --> APP
    MQTT_C --> APP
    AMAP --> APP
    APP --> THREADS
    AUDIO --> REC
    AUDIO --> WORK
    WORK --> CHAT
    NAV --> PARSE

    MQTT_C <-->|MQTT| MQTT
    MQTT --> ANDROID

    TX_TH -->|UART g/i/t| G431
    G431 -->|UART b/s/m| TX_TH
    LOOP --> SENSORS
    LOOP --> DISPLAY
```

> 架构图源码见 `tools/gen_arch_diagram.py`（Mermaid 格式，GitHub 原生渲染）

## 快速开始

### 1. 启动 MQTT Broker

```bash
# Windows: 双击 start_mqtt.bat
# Linux/macOS:
cd mqtt_server && python run.py
```

### 2. 模拟设备数据

```bash
pip install pyserial
python tests/uart_slave_simulator.py COM3
# GPS 由上位机请求驱动（无需手动操作），按 d 开始传感器上报
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
| 上位机 | QuecPython + EC800 4G 模组 |
| 下位机 | STM32G431CB + HAL 库 (Keil MDK) |
| MQTT Broker | Python asyncio (自研) |
| Android | Kotlin + Jetpack Compose + Paho MQTT |
| 地图 | 高德 3D Map SDK (原生 GL) |
| 保活 | Android Foreground Service |
| 穿透 | frp (内网穿透) |

## Android App 功能

- 实时数据卡片（温度 / 心率 / 气压 / GPS 坐标）
- 高德 3D 地图 + 蓝点定位 + 轨迹折线 + 自动跟随
- 告警通知栏推送 + **系统闹铃剧响**（10 秒循环）
- **前台服务保活**，退到后台不杀进程
- MQTT 断线自动退避重连（2s→4s→8s→60s）
- 传感器数据 JSONL 本地持久化 + 趋势图表
- 温度 > 40°C 红色预警（环境温度检测）

## G431 下位机功能

- **传感器采集**：BH1750（光照）、BMP280（温度/气压）、MPU6050（六轴 IMU）、MAX30102（心率/血氧）
- **OLED 128×32 显示**：双行布局（导航文字滚动 + 时间/心率/心情），UTF-8 中文字库（W25Q128 SPI Flash）
- **摔倒/碰撞检测**：合加速度 > 3g 或 角速度 > 300°/s 即时告警
- **双机握手协议**：上电 `i<hex>` 传感器状态上报，EC800 回复 `i` 启动采集
- **测试模式**（默认开启）：模拟 GPS 轨迹 + 模拟传感器数据
- **4 键输入**：开关机 / 对话 / 音量 ±，每 10ms 扫描

## 更多文档

嵌入式端（EC800 模组）的完整技术文档见 **[src/readme.md](src/readme.md)**，涵盖：

- 核心线程模型（6 类线程协作）
- MCP 工具扩展指南
- 串口通信协议规范（报文帧格式、模块简写表、交互模式）
- GPS 定位与实时导航（偏航检测、路段跟踪、自动重规划）
- MQTT 云平台集成（保活、上报链路）
- 音频管理（KWS/VAD/TTS 回调队列）
