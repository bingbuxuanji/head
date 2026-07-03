#!/usr/bin/env python3
"""生成系统架构 Mermaid 图 — GitHub 原生渲染，零依赖"""

MERMAID = '''```mermaid
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
            OLED[OLED 128x32 I2C<br/>上行: 导航 UTF-8 滚动<br/>下行: 心率 + 时间 + 心情]
            W25Q[W25Q128 SPI Flash<br/>UTF-8 中文字库<br/>16x16 字模二分查表]
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
```'''

if __name__ == '__main__':
    print(MERMAID)
