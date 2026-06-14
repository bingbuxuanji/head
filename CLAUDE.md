# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 **Quectel EC800 模组** 的智能头盔语音助手系统，包含嵌入式端、MQTT Broker、Android 监控 App、PC 测试工具四部分。

| 组件 | 目录 | 技术栈 |
|------|------|--------|
| 嵌入式 | `src/` | QuecPython (MicroPython) + EC800 |
| MQTT Broker | `mqtt_server/` | Python 3 asyncio (自研) |
| Android App | `android_app/` | Kotlin + Jetpack Compose + Paho MQTT |
| 测试工具 | `tests/` | Python 3 + pyserial |

详细嵌入式文档见 [src/readme.md](src/readme.md)。

---

## 嵌入式端 (src/)

### 运行环境约束

- **平台**：QuecPython（MicroPython），无 CPython 标准库
- **编码**：仅 `utf-8`、`ascii`，**不支持** GB2312/GBK
- **并发**：`threading.py` 实现 Lock、Condition、Event、Queue、Thread 等原语
- **导入**：QuecPython 内置模块（`audio`、`record`、`net`、`uwebsocket`、`sys_bus`、`modem` 等）仅在模组上可用，PC 不可导入

### 核心文件

| 文件 | 职责 |
|------|------|
| `_main.py` | 主入口，Application 类（6 类线程 + 导航 + MQTT + MCP） |
| `mqtt_client.py` | MQTT 客户端 `MqttClient`（自建 Broker, 用户名密码认证, 保活线程） |
| `protocol.py` | WebSocket 协议 `WebSocketClient`（JSON-RPC + MCP + 音频收发） |
| `utils.py` | AudioManager / ChargeManager / NetManager / Massage / CommandDispatcher |
| `helmet_test.py` | AmapAPI / Navigator / NavigationManager（骑行导航 + 球面几何） |
| `threading.py` | 并发原语（Thread, Lock, Condition, Event, Queue 等） |

### 线程模型（6 类 + 1）

| 线程 | 职责 | 生命周期 |
|------|------|---------|
| `__record_thread` | 持续采集 Opus 音频喂给 KWS/VAD | `start_kws()` → `stop_kws()` |
| `__working_thread` | 一次完整对话流程 | 唤醒触发 → 对话结束销毁 |
| 聊天子线程 | WebSocket 连接 + 音频收发 | 随对话创建/销毁 |
| `__tc_gps_thread` | GPS 定时请求（导航 2s / 待机 30s） | `_start_tc_gps_thread()` → 关机 |
| UART TX 线程 | 从队列取数据写硬件，串行化写请求 | 常驻 |
| 后台解析线程 | 异步解析高德 polyline 数据 | 单次用完销毁 |
| **MQTT 保活线程** | `check_msg()` 发 PINGREQ + 收下行 | `connect()` → `disconnect()` |

### 导航事件链路

```
GPS 更新 → _gps_default_handler (UART 回调线程)
  → _on_gps_for_navigation → NavigationManager.update_position()
    → on_step_changed / on_off_course / on_arrived 回调
      → _notify_nav_text(text)                          # 回调直接处理，不中转 chat
        ├── uartWrite(b't' + text)                      # 串口下发（始终执行）
        └── tts_play(text)                              # 本地播报（svr_tts 空闲时）
```

导航与对话完全解耦，GPS 由 `__tc_gps_thread` 独立维护，chat 循环仅负责语音对话。

### TTS 架构（回调队列，非阻塞）

- `tts_play(text)` 入队，空闲时立即开始
- `_tts_start_next()` 从队列取字、关闭 opus、调用硬件播放
- 硬件播完 → `_tts_cb(event=4)` → `_tts_active=False` → `_tts_start_next()` 取下一条
- 队列空则 `open_opus()` 恢复音频通路

**绝对不要**改成阻塞式等待或加额外线程。

### 串口协议

所有报文由 **1 字节模块简写 + N 字节载荷** 组成。写 UART 走 `Massage.uartWrite()`，**已线程安全**（Queue + 独立线程）。

| 简写 | 方向 | 用途 |
|------|------|------|
| `b` | 从机→主机 | 按键事件 (`b1`~`b4`) |
| `g` | 双向 | GPS 请求 (`g`) / 响应 (`g<lng>,<lat>`) |
| `s` | 从机→主机 | 传感器数据 (`s<temp>,<hr>,<vel>`)，每 5 秒推送 |
| `t` | 主机→从机 | 导航文字下发 |

完整协议规范见 [src/readme.md §9](src/readme.md#9-附录串口通信协议规范)。

### MCP 工具注册

新增工具需触达三处：`mcp_tools_list` 声明 → `handle_mcp_message` 处理 → `mcp_tools_call` 响应 payload。

已注册工具：音量控制 ×4、唤醒词改名、骑行路线查询、导航启停、导航状态查询。

### 导航偏航逻辑

```
当前位置 → 计算到当前路段 polyline 的最短球面距离 (point_to_segment_distance)
  ├─ 距路段终点 ≤ 20m → 到达，推进下一步
  └─ 距路段 > 50m → 初步偏航
       └─ 扫描全部 step 找任一在阈值内的路段 → 跳转（不算偏航）
            └─ 找不到 → 确认偏航 → on_off_course → 后台重规划
```

详见 [src/helmet_test.py](src/helmet_test.py) `Navigator.update()`.

### 问题排查

- **MCP 请求无效** → 检查 WebSocket 接收线程是否死亡（`logger.error` 级别日志），常见原因：服务端发非 JSON 文本导致 `json.loads` 崩溃
- **MQTT 断连** → 检查保活线程是否运行，`check_msg()` 是否正常调用
- **导航不启动** → 检查异步路线解析日志，`parse_bicycle_route` 返回 None 会有 error 日志 + 语音通知
- **TTS 播报异常** → 检查 `_svr_tts_active` 状态，服务端 TTS 期间本地导航播报会被跳过

---

## MQTT Broker (mqtt_server/)

纯 Python asyncio 实现的 MQTT 3.1.1 Broker：

- `broker.py` — 核心：CONNECT/PUBLISH/SUBSCRIBE/PING 处理
- `data_handler.py` — 数据处理管道：validate → threshold_check → console_report → persist
- `config.py` — 配置中心（设备密钥、阈值、主题路由）
- `run.py` — 启动入口

启动：`cd mqtt_server && python run.py` 或双击 `start_mqtt.bat`

---

## Android App (android_app/)

Kotlin + Jetpack Compose 实现的监控 App：

- Paho MQTT 客户端 + 协程
- 高德原生 3D MapView（OpenGL 渲染）
- 实时数据卡片（体温/心率/速度/GPS）
- 告警通知栏推送 + 系统闹铃剧响
- 前台服务保活 + 断线退避重连

连接地址配置见 `MqttManager.kt`。

---

## 测试工具 (tests/)

### UART 下位机模拟器 (`uart_slave_simulator.py`)

模拟从机 MCU 串口行为，用于 PC 端调试：

```bash
pip install pyserial
python tests/uart_slave_simulator.py COM3
```

**协议行为**（v0.4.2 修正）：
- GPS：纯请求-应答模式，收到上位机 `g` 请求后回复 `g<lat>,<lng>`
- 轨迹推进限频 5 秒，不足时发旧坐标
- 传感器：每 5 秒主动推送 `s<temp>,<hr>,<vel>`（随机值）
- 按键：`1`~`4` 发送 `b1`~`b4`；`a` 发送告警数据

启动后默认开启传感器自动上报，GPS 无需手动操作（由上位机请求驱动）。

---

## 代码风格（嵌入式端）

- 中文注释，解释业务意图而非代码字面含义
- 类名 PascalCase，方法/函数 snake_case，私有方法双下划线 `__xxx`
- 分隔块：`# ---------- 标题 ----------`
- 方法 docstring 中文，标明参数和返回值
- 全局可变状态用 `global` 声明
- 失败返回 `-1` 或 `None`，成功返回 `0`
- `close_opus` / `open_opus` 必须 `hasattr` + `try/except` 防重入
- Logger 方法是 `warn()` 不是 `warning()`

## 不要做的事

- 不要假设 GB2312/GBK 可用，文本编码统一用 UTF-8
- 不要在 TTS 回调外直接调 `open_opus()`
- 不要用 PC Python 标准库（`asyncio`、`requests`、`threading` 标准版等）
- 不要改 `Massage.uartWrite` 回直接写硬件
- 导航偏航回调不要设为可能重复触发（已有 `_off_course_notified` 去重和 `_replanning` 防重入）
- 不要在 `_tts_cb` 中阻塞或加耗时操作
- 不要假设 MQTT 会自动保活，`check_msg()` 由 `MqttClient` 后台线程维护
- 传感器数据不要限频上传（与 GPS 的 30s 限频不同）
