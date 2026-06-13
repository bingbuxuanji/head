# CHANGELOG

## [0.3.0] — 2026-06-09

### 重构

- **导航与对话完全解耦**：GPS 请求、导航事件通知、对话管理三者彻底分离。
  - GPS 轮询从 `__chat_process` 移至独立后台线程 `__tc_gps_thread`，导航期间每 2 秒、非导航期间每 30 秒主动请求一次 GPS。
  - 导航事件（路段切换 / 偏航 / 到达）不再通过 `_nav_notify_pending` 标志在 chat 循环中转，改为在导航回调中直接调用 `_notify_nav_text()` 发送 UART + TTS。
  - 移除导航期间的 WebSocket keepalive 保活（chat 循环不再因导航而保持连接）。
  - 移除 `__chat_process` 退出时的导航自动重连逻辑。
  - 清理废弃状态变量 `_nav_notify_pending`、`_nav_notify_event`。
- **GPS 请求互斥机制**：`_gps_request_pending` 标志 + 2 秒超时保护，确保后台线程、`_request_gps_position`（导航启动 / 偏航重规划阻塞调用）三种 GPS 请求源互不冲突。
- **ThingsCloud 位置上报提取**：`_upload_gps_to_thingscloud(latitude, longitude)` 从 `_gps_default_handler` 中提取为独立函数，内部自行限频 30 秒 + 断线重连。

### 新增

- 后台 GPS 定时器 `__tc_gps_thread_handler`：始终运行，根据 `is_navigating` 动态切换轮询间隔（2 秒 / 30 秒）。
- `_notify_nav_text(inject_text)` 辅助方法：导航回调直接调用，不依赖 chat 循环上下文。
- `_last_bg_gps_request`、`_nav_gps_interval`、`_gps_request_time` 状态变量。

### 文档

- 更新 `CLAUDE.md`：线程模型从 5 类扩展为 6 类，导航事件链路更新为直接回调模式。
- 更新 `readme.md`：线程模型、GPS 管理、导航注入章节同步架构变更。

## [0.2.1] — 2026-06-09

### 新增

- **ThingsCloud MQTT 云平台集成**：新增 `thingscloud.py` 模块，基于 QuecPython `umqtt` 实现 ThingsCloud 云平台的 MQTT 客户端。支持 AccessToken + ProjectKey 认证、属性上报（`publish_attributes`）、事件上报（`publish_event`）、下行指令接收（`set_downlink_callback`）、断线自动重连、内部属性缓存与合并更新。
- **GPS 经纬度定时上报云平台**：`_gps_default_handler` 中新增 ThingsCloud 经纬度上报逻辑，每 30 秒限频上传一次（`longitude`、`latitude`），含断线自动重连。同时注册 `temperature`、`heart_rate`、`velocity` 等属性预留后续传感器接入。
- **设备上线事件**：ThingsCloud 连接成功后自动发布 `device_online` 事件（含固件版本和产品模式），供云端监控设备在线状态。
- **ThingsCloud 下行指令回调**：`set_downlink_callback` 支持注册云端下行指令处理函数，由 MQTT 内部线程回调驱动。

### 文档

- 新增 `readme.md` §10 参与贡献指南。
- 新增 `CLAUDE.md` 项目架构与开发指南。
- 新增 `readme.md` §11 致谢章节（移远通信、小智 AI）。
- 更新 `readme.md`：目录结构加入 `thingscloud.py`，类关系图加入 `ThingsCloudMQTT`，新增 §4.15 ThingsCloud MQTT 章节。


## [0.2.0] — 2026-06-03

### 新增

- **导航文字串口下发**：导航事件（路段切换 / 偏航 / 到达）除 TTS 播报外，同步通过串口 `t` 报文向从机 MCU 推送 UTF-8 文字，供从机屏幕显示。串口发送独立于 TTS 防冲突机制，且不因 TTS 重试而重复发送。
- **偏航自动重规划**：偏航时除通知用户外，后台线程自动调用高德 API 基于当前位置重新请求路线至原目的地，覆盖旧导航并播报新路线第一步指令。`_replanning` 防重入。
- **偏航去重**：`NavigationManager` 新增 `_off_course_notified` 标志，同一次偏航事件不再重复触发通知。
- **UART TX 队列**：`Massage` 类新增 `Queue` + 独立 TX 线程，`uartWrite()` 改为入队，由 TX 线程串行化写入硬件，消除多线程（导航文字 / GPS 请求 / 对话）写 UART 的竞争。
- **TTS 回调驱动队列**：`AudioManager` 本地 TTS 改为 `Queue` + `_tts_cb` 回调驱动架构。`tts_play(text)` 入队非阻塞，回调完成后自动取队列下一条或恢复 opus。彻底解决多条 TTS 重叠导致的 `pcm open write fail`。
- **导航期间 WebSocket 保活**：`WebSocketClient` 新增 `keepalive()` 方法，导航中非上传音频时每 15 秒发送一次保活帧，防止 TTS 播报期间服务端超时断开。
- **导航断线自动重连**：`__chat_process` 退出时若导航仍活跃（`is_navigating == True`），自动重启对话线程建立新 WebSocket 连接，确保导航事件处理不中断。

### 修复

- 修复 `CommandDispatcher` 和 `Application` 中 `logger.warning()` → `logger.warn()`（共 9 处），消除 `AttributeError`。
- `open_opus()` / `close_opus()` 加入防重入保护（`hasattr` + `try/except`），避免 TTS 回调中 PCM 资源未释放时崩溃。

### 文档

- 更新 `readme.md`：新增 `t` 模块协议规范（§9.6），更新模块简写表、线程模型、音频/TTS、串口、导航等章节。
- 新增 `CHANGELOG.md`。
