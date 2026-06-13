# CHANGELOG

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
