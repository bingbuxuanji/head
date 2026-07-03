# CHANGELOG

## [0.5.0] — 2026-07-03

### 新增 — G431 下位机

- **STM32G431 从机 MCU 固件**：新增 `G431/` 目录，基于 STM32CubeMX + Keil MDK
  - 传感器驱动：BH1750（光照）、BMP280（温度/气压）、MPU6050（六轴 IMU）、MAX30102（心率/血氧）
  - OLED 128×32 显示：SSD1306 I2C 驱动 + UTF-8 中文字库（W25Q128 SPI Flash）
  - 导航文字显示：EC800 下发 `t` 报文 → OLED 单行像素宽度滚动
  - 串口协议：USART2 接 EC800，USART1 接 GPS 模块，按 `\r\n` 分行解析防粘包
  - 按键检测：4 键扫描（开关机/对话/音量±），每 10ms 上报 `b1`~`b4`
  - 摔倒/碰撞检测：合加速度 > 3g + 角速度 > 300°/s 即时告警上报
- **双机初始化握手**：G431 周期性发送 `i<hex>` 传感器就绪位掩码，EC800 回复 `i` 启动采集
- **测试模式**（默认开启）：模拟 GPS 轨迹（成都郫都→天府广场）+ 模拟传感器数据

### 新增 — OLED 显示

- **固定双行布局**：上行导航文字（UTF-8 滚动），下行时间+心率+心情
- **导航文字滚动**：超长文字按像素宽度截窗，每 500ms 推进一个 UTF-8 字符，到头回绕
- **时间显示**：EC800 每秒发送 `tHH:MM:SS`，G431 OLED 固定下半区显示
- **心情显示**：LLM 返回 `emotion` 字段映射为 ASCII 表情（`:), >:(, B), ~?`），附在时间行

### 修复 — 粘包问题

- **EC800 → G431 粘包**：所有 UART 消息统一加 `\r\n` 终止符，G431 USART2 回调按行解析
- **G431 → EC800 粘包**：Massage.uartRead 按 `\r\n` 分行派发，修复 `i` 触发采集指令丢失
- **SPI Flash 读取偏移**：W25Q128 改用 `HAL_SPI_Transmit`/`HAL_SPI_Receive`，修复手写 DR 导致的 2 字节错位
- **EC800 TX 线程健壮性**：`uartWrite` 统一 bytes 类型 + TX 线程 try/except 防崩溃

### 修复 — 重复日志

- **日志系统**：`logging.py` 关闭 `debug: True` 全局开关，默认只显示 INFO 及以上
- **GPS 解析日志**：`INFO` → `DEBUG`，不再刷屏
- **Unknown message type**：`WARN` → `DEBUG`
- **传感器/IMU 数据日志**：`INFO` → `DEBUG`
- **EC800 重复发送 `i`**：`_collection_started` 标志防重复，G431 复位自动重新握手

### 变更 — 温度阈值

- 温度传感器从"体温"改为"环境温度"：告警 35~37.5°C → -10~45°C，大屏红色 >37.5°C → >40°C，图表 Y 轴 35~42 → -10~50
- Android/readme/MQTT Broker 全部同步更新

### 变更 — 导航重规划

- **冷却期限制**：偏航重规划后 45 秒冷却，避免频繁 HTTP 阻塞系统
- **失败提示**：重规划各环节失败时通过 `t` 报文通知 OLED（"重规划失败：GPS未就绪" 等）
- **急停保护**：`stop_navigation` 后重规划不再复活导航

### 移除 MCP 工具

- 移除 `self.setvolume()` 工具（inputSchema 格式错误导致 LLM 400 报错）

## [0.4.2] — 2026-06-14

### 修复

- **MQTT 保活缺失**：新增保活后台线程，周期调用 `check_msg()` 发送 PINGREQ + 接收下行消息，解决 broker 超时断开和下行指令无法接收的问题
- **WebSocket 接收线程静默死亡**：`recv()` 内 `json.loads` 遇到非 JSON 文本时不再崩溃整条接收线程
- **日志级别修复**：WebSocket 接收线程异常、JSON 消息处理异常、聊天线程异常的日志从 `info`/`debug` 提至 `error`，避免关键错误静默丢失
- **TTS 消息伪异常**：移除 `handle_tts_message` 中残留的 `raise NotImplementedError`，TTS 状态管理本身已完整
- **导航启动静默失败**：`get_bicycle_route` 和 `start_navigation` 的异步路线解析失败时增加错误日志和语音通知
- **无效 GPS 坐标污染缓存**：`NavigationManager.update_position` 坐标校验前置，防止无效坐标写入 `last_lng/last_lat` 导致 `get_status()` 返回错误距离
- **导航路段切换 MQTT 上报**：路段切换时主动上报 GPS + 导航状态快照到 MQTT

### 变更

- **UART 模拟器 GPS 协议修正**：GPS 从盲推改为请求-应答模式（上位机发 `g` → 从机回 `g<lat>,<lng>`），与真实协议一致；轨迹推进限频 5 秒，不足时发旧坐标；移除 `r` 键自动 GPS 功能
- **MQTT 客户端重命名**：文件 `thingscloud.py` → `mqtt_client.py`，类 `ThingsCloudMQTT` → `MqttClient`，实例 `self.thingscloud` → `self.mqtt`，方法 `_upload_gps_to_thingscloud` → `_upload_gps_to_mqtt`

## [0.4.1] — 2026-06-13

### 新增

- **前台服务保活**：`MonitorService` 前台服务，通知栏常驻，App 退到后台不杀进程
- **告警剧响**：收到告警 → 音量拉最大 → 系统闹铃循环播放 10 秒
- **断线自动重连**：Paho 自带重连换协程退避重连（2s→4s→8s→最大 60s）
- **数据持久化**：SharedPreferences 缓存最新传感器数据，杀进程重启不丢
- **串口模拟器告警命令**：`a` / `a1`（体温） / `a2`（心率） / `a3`（双重）
- **串口模拟器 GPS 终点驻留**：到达终点后坐标不变，继续定时发送
- **App 启动图标**：自适应分辨率 launcher icon

### 修复

- **告警阈值修正**：体温上限 42°C → 37.5°C，心率上限 180 → 150 BPM
- **MCP HTTP 阻塞修复**：`get_bicycle_route` 和 `start_navigation` 的 HTTP 请求移至后台线程
- **MQTT 属性合并**：`publish_attributes` 不再清空缓存，GPS + 传感器合并上报
- **通知权限兜底**：权限未就绪时用 Toast 代替静默丢失

### 变更

- `MqttManager` 支持多 clientId 后缀，UI 和 Service 使用独立 MQTT 连接
- `MapViewComposable` 改用原生 `MapView`（FrameLayout + OpenGL），废弃 WebView 方案

## [0.4.0] — 2026-06-13

### 新增

- **自建 MQTT 服务器**：新增 `mqtt_server/`，纯 Python asyncio 实现的 MQTT 3.1.1 Broker。
  - 支持 CONNECT/PUBLISH/SUBSCRIBE/PING 等标准 MQTT 操作
  - 主题通配符匹配（`+` / `#`）
  - 数据处理管道：validate → threshold_check → console_report → persist
  - 实时控制台输出（彩色日志 + 告警高亮）
  - 内网穿透适配（TCP keepalive + keepalive 参数对齐 frp）
  - 启动脚本 `start_mqtt.bat`（Windows GBK 编码）
- **Android 监控 App**：新增 `android_app/`，Kotlin + Jetpack Compose。
  - MQTT 实时数据展示（体温 / 心率 / 速度 / GPS 坐标）
  - 高德原生 3D 地图 SDK 集成（MapView，OpenGL 渲染）
  - 蓝色位置标记 + GPS 轨迹折线 + 地图自动跟随
  - 告警通知栏推送（温度 / 心率 / 速度超阈值）
  - Paho MQTT 客户端 + 协程（不依赖 Android Service）
  - 点击 GPS 卡片打开高德导航
- **嵌入式 MQTT 客户端重构**：`src/thingscloud.py` 改为连接自建服务器。
  - 用户名密码认证（兼容旧版 access_token / project_key 参数）
  - Topic 结构化层级：`helmet/{device_id}/attributes|events|sensor`
  - 下行指令订阅 `helmet/{device_id}/commands`
  - 默认 keepalive 30s（穿透场景适配）
- **串口模拟器增强**：`tests/uart_slave_simulator.py` 新增传感器自动上报（温度 / 心率 / 速度每 5 秒随机模拟）。

### 变更

- `_main.py` 中 ThingsCloud 连接配置替换为自建 MQTT 服务器地址（支持 frp 穿透）
- `_main.py` 后台 GPS 线程增加传感器轮询（后根据协议规范撤销，传感器由从机事件上报）
- `data_handler.py` 时区修复：`datetime.utcnow()` → `datetime.now()`

### 文档

- 新增项目根级 `README.md`（项目总览、快速开始、架构说明）
- 新增 `android_app/README.md`（Android 开发指南）
- 新增 `CHANGELOG.md`（项目根级，本文件）

## [0.3.0] — 2026-06-09

### 重构

- **导航与对话完全解耦**：GPS 请求、导航事件通知、对话管理三者彻底分离
- **GPS 请求互斥机制**：`_gps_request_pending` 标志 + 2 秒超时保护
- **ThingsCloud 位置上报提取**：`_upload_gps_to_mqtt` 独立函数，内部自行限频

### 新增

- 后台 GPS 定时器 `__tc_gps_thread_handler`：动态切换轮询间隔（2s / 30s）
- `_notify_nav_text(inject_text)` 辅助方法

## [0.2.1] — 2026-06-09

### 新增

- **MQTT 云平台集成**：`mqtt_client.py` 模块，属性上报、事件上报、下行指令接收
- **GPS 经纬度定时上报**：每 30 秒限频上传
- **设备上线事件**：连接成功后发布 `device_online`

## [0.2.0] — 2026-06-03

### 新增

- 导航文字串口下发（`t` 报文）
- 偏航自动重规划 + 去重
- UART TX 队列（Queue + 独立线程）
- TTS 回调驱动队列
- 导航期间 WebSocket 保活

### 修复

- `logger.warning()` → `logger.warn()` 共 9 处
- `open_opus()`/`close_opus()` 防重入保护
