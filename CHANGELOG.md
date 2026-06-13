# CHANGELOG

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
