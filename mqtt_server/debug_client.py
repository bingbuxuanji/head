#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
本地 MQTT 设备模拟器 — 用于在不烧录硬件的情况下调试服务器

用法:
    1. 先启动 mqtt_server:  python mqtt_server/run.py
    2. 再运行本脚本:        python mqtt_server/debug_client.py

模拟行为:
    - 以 helmet_001 身份连接本地 Broker
    - 上报 GPS 坐标、温度、心率
    - 订阅下行 commands 和服务器发布的 alerts
    - 持续运行，按 Ctrl+C 退出
"""

import sys
import os
import time
import json
import random
import threading

# 尝试导入 paho-mqtt，没有则提示安装
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("需要安装 paho-mqtt:")
    print("  pip install paho-mqtt")
    sys.exit(1)

# ---------- 配置 ----------
# 本地直连测试（不走穿透）:
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883

# 走 frp 穿透测试（确认 frpc 在跑后取消下行注释）:
# BROKER_HOST = "frp-run.com"
# BROKER_PORT = 18830

DEVICE_ID = "helmet_001"
DEVICE_KEY = "helmet_key_001"

# Topic
TOPIC_ATTR = f"helmet/{DEVICE_ID}/attributes"
TOPIC_EVENT = f"helmet/{DEVICE_ID}/events"
TOPIC_CMD = f"helmet/{DEVICE_ID}/commands"
TOPIC_ALERTS = f"helmet/{DEVICE_ID}/alerts"
TOPIC_PROCESSED = f"helmet/{DEVICE_ID}/data/processed"


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[✓] 已连接到 {BROKER_HOST}:{BROKER_PORT}")
        # 订阅下行指令和告警
        client.subscribe(TOPIC_CMD, qos=1)
        client.subscribe(TOPIC_ALERTS, qos=0)
        client.subscribe(TOPIC_PROCESSED, qos=0)
        print(f"[✓] 已订阅: {TOPIC_CMD}, {TOPIC_ALERTS}, {TOPIC_PROCESSED}")

        # 发送上线事件
        client.publish(TOPIC_EVENT, json.dumps({
            "event": "device_online",
            "params": {"version": "1.0.0", "mode": "helmet"}
        }))
        print(f"[✓] 已发送上线事件")
    else:
        print(f"[✗] 连接失败, rc={rc}")


def on_message(client, userdata, msg):
    print(f"\n[↓] {msg.topic}")
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        print(f"    {json.dumps(data, ensure_ascii=False, indent=2)}")
    except Exception:
        print(f"    (binary) {len(msg.payload)} bytes")


def on_disconnect(client, userdata, rc):
    print(f"[!] 断开连接, rc={rc}")


def simulate_gps_report(client):
    """模拟 GPS 定时上报（每 5 秒一次）"""
    # 成都市坐标附近
    base_lng, base_lat = 104.07572, 30.65089

    while True:
        # 模拟移动（小幅随机偏移）
        lng = base_lng + random.uniform(-0.0005, 0.0005)
        lat = base_lat + random.uniform(-0.0005, 0.0005)
        temp = round(36.0 + random.uniform(-0.5, 1.5), 1)  # 模拟体温
        hr = int(random.gauss(75, 10))                      # 模拟心率

        payload = {
            "longitude": round(lng, 6),
            "latitude": round(lat, 6),
            "temperature": temp,
            "heart_rate": hr,
        }

        client.publish(TOPIC_ATTR, json.dumps(payload))
        print(f"[↑] {TOPIC_ATTR}: lng={lng:.6f} lat={lat:.6f} temp={temp} hr={hr}")

        # 每 30 次有 1 次故意发异常心率，触发告警
        if random.randint(1, 30) == 1:
            alert_payload = {"heart_rate": 200, "temperature": 38.5}
            client.publish(TOPIC_ATTR, json.dumps(alert_payload))
            print(f"[↑] 触发告警测试: hr=200")

        time.sleep(5)


def main():
    print("=" * 55)
    print("  智能头盔 MQTT 调试客户端")
    print(f"  Broker: {BROKER_HOST}:{BROKER_PORT}")
    print(f"  设备: {DEVICE_ID}")
    print("  按 Ctrl+C 退出")
    print("=" * 55)

    client = mqtt.Client(client_id=DEVICE_ID, clean_session=True)
    client.username_pw_set(DEVICE_ID, DEVICE_KEY)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # 连接
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
    client.loop_start()

    # 启模拟线程
    gps_thread = threading.Thread(target=simulate_gps_report, args=(client,), daemon=True)
    gps_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n退出...")
        client.publish(TOPIC_EVENT, json.dumps({"event": "device_offline"}))
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
