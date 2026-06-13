# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 **Quectel EC800 模组** 的嵌入式智能头盔语音助手，运行 QuecPython（MicroPython）环境。支持离线 KWS 唤醒、云端 WebSocket 语音对话、骑行导航、本地 TTS、按键交互、串口通信。

## 运行环境约束

- **平台**：QuecPython（MicroPython），无 CPython 标准库
- **编码支持**：仅 `utf-8`、`ascii`，**不支持** GB2312/GBK
- **并发**：项目自带 `usr/threading.py` 实现了 Lock、Condition、Event、Queue、Thread 等原语
- **导入**：QuecPython 内置模块（`audio`、`record`、`net`、`uwebsocket`、`sys_bus`、`modem` 等）在 PC 上不可用，仅能在模组上验证

## 核心架构

### 线程模型（6 类）

| 线程 | 职责 | 生命周期 |
|------|------|---------|
| `__record_thread` | 持续采集 Opus 音频喂给 KWS/VAD | `start_kws()` → `stop_kws()` |
| `__working_thread` | 一次完整对话流程 | 唤醒触发 → 对话结束销毁 |
| 聊天子线程 | WebSocket 连接 + 音频收发 | 随对话创建/销毁 |
| `__tc_gps_thread` | 统一 GPS 定时请求（导航 2s / 待机 30s） | `_start_tc_gps_thread()` → `_stop_tc_gps_thread()` |
| UART TX 线程 | 从队列取数据写硬件，串行化所有写请求 | `Massage.__init__` → 常驻 |
| 后台解析线程 | 异步解析高德 polyline 数据 | 单次用完销毁 |

### 导航事件链路

```
GPS 更新 → _gps_default_handler (UART 回调线程)
  → _on_gps_for_navigation → NavigationManager.update_position()
    → on_step_changed / on_off_course / on_arrived 回调
      → _notify_nav_text(text)                          # 回调直接处理，不中转 chat
        ├── uartWrite(b't' + text.encode('utf-8'))      # 串口下发（始终执行）
        └── tts_play(text)                              # 本地播报（svr_tts 空闲时）
```

导航与对话完全解耦，不再依赖 `_nav_notify_pending` 和 chat 循环中转。
GPS 由 `__tc_gps_thread` 后台线程独立维护，chat 循环仅负责语音对话。

### TTS 架构（回调队列，非阻塞）

- `tts_play(text)` 入队，空闲时立即开始
- `_tts_start_next()` 从队列取字、关闭 opus、调用硬件播放
- 硬件播完 → `_tts_cb(event=4)` → `_tts_active=False` → `_tts_start_next()` 取下一条
- 队列空则 `open_opus()` 恢复音频通路

**绝对不要**改成阻塞式等待或加额外线程，回调驱动是刻意设计。

### 串口协议

所有报文由 **1 字节模块简写 + N 字节载荷** 组成（见 readme.md §9.2）。写 UART 走 `Massage.uartWrite()`，**已线程安全**（Queue + 独立线程），不要回退到直接写。

| 简写 | 方向 | 用途 |
|------|------|------|
| `b` | 从机→主机 | 按键事件 |
| `g` | 双向 | GPS 请求/响应 |
| `t` | 主机→从机 | 导航文字下发 |

### MCP 工具注册

新增工具有三个触达点：`mcp_tools_list` 声明 → `handle_mcp_message` 处理 → `mcp_tools_call` 响应 payload（见 readme.md §5.1）。

## 代码风格

- 中文注释，解释业务意图而非代码字面含义
- 类名 PascalCase，方法/函数 snake_case，私有方法双下划线 `__xxx`
- 分隔块：`# ---------- 标题 ----------`
- 方法 docstring 中文，标明参数和返回值
- 全局可变状态用 `global` 声明（`volume`、`name`、`enable_flag`）
- 失败返回 `-1` 或 `None`，成功返回 `0`
- `close_opus` / `open_opus` 必须 `hasattr` + `try/except` 防重入
- Logger 方法是 `warn()` 不是 `warning()`

## 不要做的事

- 不要假设 GB2312/GBK 可用，文本编码统一用 UTF-8
- 不要在 TTS 回调外直接调 `open_opus()`，TTS 资源恢复由队列机制管理
- 不要用 PC Python 标准库（`asyncio`、`requests`、`threading` 标准版等）
- 不要改 `Massage.uartWrite` 回直接写硬件
- 导航偏航回调不要设为可能重复触发，已有 `_off_course_notified` 去重和 `_replanning` 防重入
- 不要在 `_tts_cb` 中阻塞或加耗时操作
