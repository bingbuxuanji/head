# -*- coding: UTF-8 -*-
"""
智能头盔 MQTT 数据处理管道

"处理数据的话题" — 核心数据处理逻辑。

Topic 约定:
  设备上行:
    helmet/{device_id}/attributes   — 传感器/GPS 属性数据 (JSON)
    helmet/{device_id}/events       — 设备事件 (JSON)
    helmet/{device_id}/sensor       — 原始传感器数据

  服务端下行:
    helmet/{device_id}/data/processed  — 经管道处理后的数据
    helmet/{device_id}/alerts          — 告警消息
    helmet/{device_id}/commands        — 下行指令

数据处理管道（按序执行）:
  1. validate        — 数据校验
  2. threshold_check — 阈值检测，生成告警
  3. gps_geofence    — 电子围栏（预留扩展）
  4. persist         — 数据持久化到日志文件
"""

import os
import json
import time
import logging
from datetime import datetime

from . import config

logger = logging.getLogger("mqtt.data")


# ==================== 处理器注册表 ====================

class DataPipeline(object):
    """
    数据处理管道

    接收设备上报的原始数据，依次通过注册的处理器，
    最终产出处理结果和告警。
    """

    def __init__(self, callback_publish=None):
        """
        :param callback_publish: async fn(topic, payload, qos, retain)
                                用于将处理结果发布回 MQTT
        """
        self._publish = callback_publish
        self._processors = {}
        self._init_default_processors()

    def _init_default_processors(self):
        """注册默认处理器"""
        self._processors["validate"] = self._validate
        self._processors["threshold_check"] = self._threshold_check
        self._processors["gps_geofence"] = self._gps_geofence
        self._processors["console_report"] = self._console_report
        self._processors["persist"] = self._persist

    def register(self, name, processor_fn):
        """注册自定义处理器"""
        self._processors[name] = processor_fn

    async def process(self, device_id, topic, payload_bytes):
        """
        处理一条设备上行消息

        :param device_id:    设备 ID（从 topic 中提取）
        :param topic:        原始 topic
        :param payload_bytes: 消息载荷（bytes）
        """
        # 尝试解析 JSON
        data = None
        raw_text = ""
        try:
            raw_text = payload_bytes.decode("utf-8")
            data = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("[%s] Non-JSON payload on %s: %s",
                           device_id, topic, payload_bytes[:100])
            data = {"_raw": raw_text}

        context = {
            "device_id": device_id,
            "topic": topic,
            "data": data,
            "raw": raw_text,
            "timestamp": time.time(),
            "alerts": [],
            "processed_data": dict(data) if isinstance(data, dict) else {},
        }

        # 依次执行管道中的处理器
        for proc_name in config.DATA_PIPELINE:
            if proc_name in self._processors:
                try:
                    await self._processors[proc_name](context)
                except Exception as e:
                    logger.error("[%s] Processor '%s' error: %s",
                                 device_id, proc_name, e)

        # 发布处理结果到 processed 主题
        if self._publish and context["processed_data"]:
            result_topic = "helmet/{}/data/processed".format(device_id)
            result_payload = json.dumps({
                "ts": datetime.now().isoformat(),
                "data": context["processed_data"],
            }, ensure_ascii=False)
            await self._publish(result_topic, result_payload, qos=0, retain=False)

        # 发布告警
        if self._publish and context["alerts"]:
            alert_topic = "helmet/{}/alerts".format(device_id)
            alert_payload = json.dumps({
                "ts": datetime.now().isoformat(),
                "alerts": context["alerts"],
            }, ensure_ascii=False)
            await self._publish(alert_topic, alert_payload, qos=1, retain=False)

        return context

    # ========== 内置处理器 ==========

    async def _validate(self, ctx):
        """
        数据校验处理器

        校验各字段的类型和范围，将合法值移入 processed_data，
        非法值记录告警。
        """
        data = ctx.get("data", {})
        if not isinstance(data, dict):
            return

        validated = {}
        # 温度校验
        if "temperature" in data:
            try:
                t = float(data["temperature"])
                if -40 <= t <= 100:
                    validated["temperature"] = round(t, 1)
                else:
                    ctx["alerts"].append({
                        "type": "invalid_value",
                        "field": "temperature",
                        "value": t,
                        "msg": "温度值超出范围: {}".format(t),
                    })
            except (ValueError, TypeError):
                ctx["alerts"].append({
                    "type": "invalid_value",
                    "field": "temperature",
                    "msg": "温度值格式错误: {}".format(data["temperature"]),
                })

        # 心率校验
        if "heart_rate" in data:
            try:
                hr = float(data["heart_rate"])
                if 0 <= hr <= 300:
                    validated["heart_rate"] = round(hr, 1)
                else:
                    ctx["alerts"].append({
                        "type": "invalid_value",
                        "field": "heart_rate",
                        "value": hr,
                        "msg": "心率值超出范围: {}".format(hr),
                    })
            except (ValueError, TypeError):
                ctx["alerts"].append({
                    "type": "invalid_value",
                    "field": "heart_rate",
                    "msg": "心率值格式错误: {}".format(data["heart_rate"]),
                })

        # 经度校验
        if "longitude" in data:
            try:
                lng = float(data["longitude"])
                if -180 <= lng <= 180:
                    validated["longitude"] = round(lng, 6)
                else:
                    ctx["alerts"].append({
                        "type": "invalid_value",
                        "field": "longitude",
                        "value": lng,
                        "msg": "经度超出范围: {}".format(lng),
                    })
            except (ValueError, TypeError):
                pass

        # 纬度校验
        if "latitude" in data:
            try:
                lat = float(data["latitude"])
                if -90 <= lat <= 90:
                    validated["latitude"] = round(lat, 6)
                else:
                    ctx["alerts"].append({
                        "type": "invalid_value",
                        "field": "latitude",
                        "value": lat,
                        "msg": "纬度超出范围: {}".format(lat),
                    })
            except (ValueError, TypeError):
                pass

        # 速度校验
        if "velocity" in data:
            try:
                v = float(data["velocity"])
                if 0 <= v <= 100:
                    validated["velocity"] = round(v, 2)
                else:
                    ctx["alerts"].append({
                        "type": "invalid_value",
                        "field": "velocity",
                        "value": v,
                        "msg": "速度超出范围: {}".format(v),
                    })
            except (ValueError, TypeError):
                pass

        ctx["processed_data"] = validated

    async def _threshold_check(self, ctx):
        """
        阈值告警处理器

        根据 config.ALERT_THRESHOLDS 检测异常值，
        生成告警。
        """
        data = ctx.get("processed_data", {})
        thresholds = config.ALERT_THRESHOLDS

        for field, value in data.items():
            if field not in thresholds:
                continue

            limits = thresholds[field]

            if "min" in limits and value < limits["min"]:
                ctx["alerts"].append({
                    "type": "threshold_low",
                    "field": field,
                    "value": value,
                    "threshold": limits["min"],
                    "msg": "{} 低于阈值: {} < {}".format(field, value, limits["min"]),
                })

            if "max" in limits and value > limits["max"]:
                ctx["alerts"].append({
                    "type": "threshold_high",
                    "field": field,
                    "value": value,
                    "threshold": limits["max"],
                    "msg": "{} 超过阈值: {} > {}".format(field, value, limits["max"]),
                })

    async def _gps_geofence(self, ctx):
        """
        GPS 电子围栏处理器（预留扩展）

        当前仅透传 GPS 数据，未来可在此接入实际的电子围栏判断逻辑。
        """
        data = ctx.get("processed_data", {})
        if "latitude" in data and "longitude" in data:
            # 预留：电子围栏检查
            # 例如：检查设备是否在指定区域内，若偏离则生成告警
            pass

    async def _console_report(self, ctx):
        """
        控制台实时输出处理器

        将设备上报的数据以彩色单行形式打印到终端，
        支持 GPS 坐标、传感器数值、告警的实时展示。
        兼容 Windows GBK / Linux UTF-8 终端。
        """
        from datetime import datetime

        device_id = ctx["device_id"]
        data = ctx.get("processed_data", {})
        alerts = ctx.get("alerts", [])

        ts = datetime.now().strftime("%H:%M:%S")

        # 构建单行摘要（纯 ASCII 标记，跨平台兼容）
        parts = [f"\033[36m[{ts}]\033[0m", f"\033[1m{device_id}\033[0m"]

        if "latitude" in data and "longitude" in data:
            parts.append(
                f"GPS({data['latitude']:.6f},{data['longitude']:.6f})"
            )
        if "temperature" in data:
            t = data["temperature"]
            color = "\033[31m" if t > 37.5 else "\033[32m"
            parts.append(f"TEMP:{color}{t:.1f}C\033[0m")
        if "heart_rate" in data:
            hr = int(data["heart_rate"])
            color = "\033[31m" if hr > 150 else "\033[33m" if hr > 100 else "\033[32m"
            parts.append(f"HR:{color}{hr}bpm\033[0m")
        if "velocity" in data:
            parts.append(f"SPD:{data['velocity']:.1f}m/s")

        line = " | ".join(parts)
        print(line, flush=True)

        # 告警单独高亮输出
        for alert in alerts:
            print(
                f"  \033[41;37m ALERT \033[0m \033[31m{alert.get('msg', str(alert))}\033[0m",
                flush=True,
            )

    async def _persist(self, ctx):
        """
        数据持久化处理器

        将处理后的数据写入日志文件。
        文件名格式: DATA_LOG_DIR/{device_id}_{YYYYMMDD}.log
        """
        if not config.DATA_LOG_ENABLED:
            return

        device_id = ctx["device_id"]
        log_dir = config.DATA_LOG_DIR

        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError:
            logger.warning("Cannot create data log dir: %s", log_dir)
            return

        date_str = datetime.now().strftime("%Y%m%d")
        filename = os.path.join(log_dir, "{}_{}.log".format(device_id, date_str))

        record = {
            "ts": datetime.now().isoformat(),
            "topic": ctx["topic"],
            "data": ctx.get("processed_data", {}),
        }
        if ctx.get("alerts"):
            record["alerts"] = ctx["alerts"]

        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except IOError as e:
            logger.error("Persist error: %s", e)


# ==================== 管理多个设备的数据管道 ====================

class DataHandlerManager(object):
    """
    数据处理器管理器

    为每个设备维护独立的数据管道实例，
    同时提供全局限流、聚合等能力。
    """

    def __init__(self):
        self._pipeline = None
        self._rate_limits = {}  # { device_id: last_ts }

    def set_publish_callback(self, callback):
        """设置 MQTT 发布回调"""
        self._pipeline = DataPipeline(callback_publish=callback)

    async def handle_message(self, device_id, topic, payload):
        """
        处理一条设备消息

        :param device_id: 设备 ID
        :param topic:     消息主题
        :param payload:   消息载荷（bytes）
        """
        if self._pipeline is None:
            logger.warning("Data pipeline not initialized")
            return

        # 简单限流：同一设备每秒最多处理一次
        now = time.time()
        last = self._rate_limits.get(device_id, 0)
        if now - last < 1.0:
            logger.debug("[%s] Rate limited", device_id)
            return
        self._rate_limits[device_id] = now

        await self._pipeline.process(device_id, topic, payload)
