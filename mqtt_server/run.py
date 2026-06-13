#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
智能头盔 MQTT 服务器 — 启动入口

用法:
    python -m mqtt_server.run
    python run.py

环境变量:
    MQTT_HOST           监听地址 (默认 0.0.0.0)
    MQTT_PORT           监听端口 (默认 1883)
    MQTT_AUTH_ENABLED   是否启用认证 (默认 true)
    MQTT_DATA_LOG_DIR   数据日志目录 (默认 ./data_logs)
    MQTT_LOG_LEVEL      日志级别 (默认 INFO)
"""

import asyncio
import logging
import signal
import sys
import os

# 确保 mqtt_server 在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mqtt_server.broker import MQTTBroker
from mqtt_server.config import LOG_LEVEL, LOG_FORMAT

# ---------- 日志配置 ----------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def main():
    """主入口"""
    broker = MQTTBroker()

    # 优雅退出处理
    loop = asyncio.get_event_loop()

    def shutdown():
        logging.info("收到退出信号，正在关闭...")
        asyncio.ensure_future(broker.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            signal.signal(sig, lambda s, f: shutdown())

    await broker.start()

    # 服务端状态打印定时器
    async def status_reporter():
        while broker._running:
            await asyncio.sleep(60)
            logging.info(
                "状态: 活跃连接=%d 订阅数=%d",
                broker.sessions.active_count,
                broker.router.total_subscriptions,
            )

    status_task = asyncio.create_task(status_reporter())

    try:
        # 保持运行
        while broker._running:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        status_task.cancel()
        await broker.stop()


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║       智能头盔 MQTT 服务器 v1.0                          ║
║       Smart Helmet MQTT Server                          ║
║                                                        ║
║  主题结构:                                              ║
║    设备上行: helmet/{device_id}/attributes              ║
║             helmet/{device_id}/events                  ║
║             helmet/{device_id}/sensor                  ║
║    服务端下行: helmet/{device_id}/data/processed       ║
║              helmet/{device_id}/alerts                 ║
║              helmet/{device_id}/commands               ║
║                                                        ║
║  数据处理管道: validate → threshold_check →            ║
║               gps_geofence → persist                   ║
╚══════════════════════════════════════════════════════════╝
    """)
    asyncio.run(main())
