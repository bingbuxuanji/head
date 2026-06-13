# -*- coding: UTF-8 -*-
"""
智能头盔 MQTT 服务器 — 核心 Broker

基于 asyncio 的 MQTT 3.1.1 协议实现。

功能:
  - 客户端连接管理（CONNECT/CONNACK 认证握手）
  - 主题订阅与消息路由（支持 + / # 通配符）
  - QoS 0/1 消息分发
  - 保活检测（PINGREQ/PINGRESP）
  - 遗嘱消息处理
  - 保留消息存储
  - 数据处理管道集成（"处理数据的话题"）
"""

import asyncio
import logging
import time
import struct
import socket
import re

from . import config
from .mqtt_packet import (
    CONNECT, CONNACK, PUBLISH, PUBACK, PUBREC, PUBREL, PUBCOMP,
    SUBSCRIBE, SUBACK, UNSUBSCRIBE, UNSUBACK,
    PINGREQ, PINGRESP, DISCONNECT,
    CONNACK_ACCEPTED, CONNACK_REFUSED_PROTOCOL,
    CONNACK_REFUSED_ID_REJECTED, CONNACK_REFUSED_SERVER_UNAVAIL,
    CONNACK_REFUSED_BAD_USER_PWD, CONNACK_REFUSED_NOT_AUTHORIZED,
    parse_packet, ProtocolError,
    build_connack, build_publish, build_puback,
    build_suback, build_unsuback, build_pingresp,
)
from .topic_router import TopicRouter, validate_topic_name
from .session import Session, SessionManager
from .data_handler import DataHandlerManager

logger = logging.getLogger("mqtt.broker")


# ---------- 内网穿透适配工具 ----------

def _tcp_keepalive_opts():
    """
    返回当前平台可用的 TCP keepalive 选项列表

    按 (SOL_TCP_OPT, value) 顺序返回，兼容 Linux / Windows / macOS。
    各选项含义（ip(7) man 文档）：
      TCP_KEEPIDLE  — 空闲多少秒后开始发送 keepalive 探测包
      TCP_KEEPINTVL — 两次探测之间的间隔秒数
      TCP_KEEPCNT   — 断开前允许的最大探测失败次数
    """
    from . import config as cfg
    opts = []
    if hasattr(socket, "TCP_KEEPIDLE"):
        opts.append((socket.TCP_KEEPIDLE, cfg.TCP_KEEPIDLE))
    elif hasattr(socket, "TCP_KEEPALIVE"):
        # macOS / BSD 的等价选项（名称不同，含义相同）
        opts.append((socket.TCP_KEEPALIVE, cfg.TCP_KEEPIDLE))
    if hasattr(socket, "TCP_KEEPINTVL"):
        opts.append((socket.TCP_KEEPINTVL, cfg.TCP_KEEPINTVL))
    if hasattr(socket, "TCP_KEEPCNT"):
        opts.append((socket.TCP_KEEPCNT, cfg.TCP_KEEPCNT))
    return opts


class MQTTBroker(object):
    """
    MQTT Broker 主类

    管理：
      - TCP 服务器
      - 客户端会话
      - 主题路由与消息分发
      - 保留消息
      - 保活检测定时器
      - 数据处理管道
    """

    def __init__(self, host=None, port=None):
        self.host = host or config.MQTT_HOST
        self.port = port or config.MQTT_PORT
        self._server = None
        self._running = False

        # 会话管理
        self.sessions = SessionManager()

        # 主题路由
        self.router = TopicRouter()

        # 保留消息: { topic: (payload, qos) }
        self._retained = {}

        # 数据处理管道
        self.data_handler = DataHandlerManager()
        self.data_handler.set_publish_callback(self._broker_publish)

        # 保活检测任务
        self._keepalive_task = None

        # 报文 ID 生成器
        self._pkt_id_counter = 0

    # ---------- 启动 / 停止 ----------

    async def start(self):
        """启动 MQTT Broker"""
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        self._running = True

        # 启动保活检测循环
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        addr = self._server.sockets[0].getsockname()
        logger.info("=" * 60)
        logger.info("MQTT Broker 已启动 — %s:%d", addr[0], addr[1])
        logger.info("  认证: %s", "启用" if config.AUTH_ENABLED else "关闭（允许匿名）")
        logger.info("  数据处理管道: %s", " → ".join(config.DATA_PIPELINE))
        logger.info("  数据日志目录: %s", config.DATA_LOG_DIR)
        logger.info("=" * 60)

    async def stop(self):
        """停止 MQTT Broker"""
        self._running = False

        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        # 断开所有客户端
        for session in self.sessions.get_all():
            try:
                await session.close()
            except Exception:
                pass

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        logger.info("MQTT Broker 已停止")

    # ---------- 客户端连接处理 ----------

    async def _handle_client(self, reader, writer):
        """
        处理新的 TCP 连接

        每个客户端连接在一个独立的 asyncio Task 中处理，
        直至连接断开或协议错误。
        """
        # ---------- 内网穿透适配：TCP Keepalive ----------
        # 在应用层 MQTT PINGREQ 之外，OS 层也开启 TCP keepalive
        # 双重保活确保穿越多层 NAT/隧道时连接状态可靠
        sock = writer.get_extra_info("socket")
        if sock is not None:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                # TCP_KEEPIDLE / TCP_KEEPINTVL / TCP_KEEPCNT
                # 不同平台常量名不同，静默失败兼容
                for opt_name, opt_val in _tcp_keepalive_opts():
                    try:
                        sock.setsockopt(socket.IPPROTO_TCP, opt_name, opt_val)
                    except (OSError, AttributeError):
                        pass
            except Exception:
                pass

        session = await self.sessions.create(reader, writer)
        logger.debug("新连接: %s", session.addr)

        buffer = b""
        try:
            while self._running:
                # 读取数据（带超时，防止僵死连接永久占用）
                try:
                    chunk = await asyncio.wait_for(
                        reader.read(4096), timeout=session.keepalive + 30
                    )
                except asyncio.TimeoutError:
                    if session.is_active and session.is_expired():
                        logger.info("读取超时，关闭空闲连接: %s", session)
                        break
                    continue

                if not chunk:
                    logger.debug("客户端断开: %s", session)
                    break

                buffer += chunk
                session.touch()

                # 循环解析缓冲区中的所有完整报文
                while buffer:
                    try:
                        packet = parse_packet(buffer)
                    except ProtocolError as e:
                        logger.warning("协议错误: %s from %s", e, session)
                        await session.close()
                        return

                    if packet is None:
                        break  # 数据不完整，等待更多数据

                    # 消费已解析的数据
                    buffer = buffer[packet["total_length"]:]

                    # 处理报文
                    await self._dispatch(session, packet)

        except asyncio.CancelledError:
            pass
        except ConnectionResetError:
            logger.debug("连接重置: %s", session)
        except Exception as e:
            logger.error("客户端处理异常 %s: %s", session, e)
        finally:
            await self._on_disconnect(session)

    async def _dispatch(self, session, packet):
        """
        报文分发

        :param session: 客户端会话
        :param packet:  parse_packet() 结果
        """
        ptype = packet["type"]
        parsed = packet.get("parsed", {})

        if ptype == CONNECT:
            await self._handle_connect(session, parsed)
        elif ptype == PUBLISH:
            await self._handle_publish(session, parsed)
        elif ptype == PUBACK:
            pass  # QoS 1 确认（当前仅记录）
        elif ptype == PUBREC:
            # QoS 2 — 回复 PUBREL
            pkt_id = parsed.get("packet_id", 0)
            from .mqtt_packet import build_pubrel
            await session.send(build_pubrel(pkt_id))
        elif ptype == PUBREL:
            # QoS 2 — 回复 PUBCOMP
            pkt_id = parsed.get("packet_id", 0)
            from .mqtt_packet import build_pubcomp
            await session.send(build_pubcomp(pkt_id))
        elif ptype == PUBCOMP:
            pass  # QoS 2 完成
        elif ptype == SUBSCRIBE:
            await self._handle_subscribe(session, parsed)
        elif ptype == UNSUBSCRIBE:
            await self._handle_unsubscribe(session, parsed)
        elif ptype == PINGREQ:
            await session.send(build_pingresp())
            logger.debug("PINGREQ/PINGRESP: %s", session)
        elif ptype == DISCONNECT:
            logger.debug("DISCONNECT: %s", session)
            await session.close()
        else:
            logger.warning("未处理的报文类型 %d: %s", ptype, session)

    # ---------- CONNECT ----------

    async def _handle_connect(self, session, connect_info):
        """处理 CONNECT 报文：认证 + 激活会话"""
        # 协议版本检查
        proto_level = connect_info.get("protocol_level", 0)
        if proto_level < 3 or proto_level > 4:
            logger.warning("不支持的协议版本: %d from %s", proto_level, session)
            await session.send(build_connack(
                False, CONNACK_REFUSED_PROTOCOL
            ))
            await session.close()
            return

        # 认证
        if config.AUTH_ENABLED:
            username = connect_info.get("username", "")
            password = connect_info.get("password", "")
            if not self._authenticate(username, password):
                logger.warning("认证失败: user=%s from %s", username, session)
                await session.send(build_connack(
                    False, CONNACK_REFUSED_BAD_USER_PWD
                ))
                await session.close()
                return
            logger.info("认证通过: user=%s", username)

        # 激活会话
        await self.sessions.activate(session, connect_info)

        # 发送 CONNACK
        await session.send(build_connack(False, CONNACK_ACCEPTED))

        # 发送该 client_id 匹配的保留消息
        for topic, (payload, qos) in self._retained.items():
            if self.router.get_subscribers(topic):
                # 仅当有订阅者时才发送保留消息
                try:
                    pkt = build_publish(topic, payload, qos=qos, retain=True)
                    await session.send(pkt)
                except Exception:
                    pass

        logger.info("客户端已连接: client_id=%s addr=%s",
                     session.client_id, session.addr)

    def _authenticate(self, username, password):
        """简单的用户名密码认证"""
        if not username:
            return False
        expected = config.AUTH_CREDENTIALS.get(username)
        if expected is None:
            # 允许任意以 helmet_ 开头的用户名（设备自动注册）
            if username.startswith("helmet_"):
                return True
            return False
        return expected == (password or "")

    # ---------- PUBLISH ----------

    async def _handle_publish(self, session, parsed):
        """
        处理 PUBLISH 报文

        1. 校验主题名
        2. 将消息路由给所有匹配的订阅者
        3. 若为属性/传感器数据，送入数据处理管道
        4. 若设置 retain，更新保留消息
        """
        topic = parsed["topic"]
        qos = parsed["qos"]
        retain = parsed["retain"]
        packet_id = parsed.get("packet_id")
        payload = parsed["payload"]

        # 校验主题名
        try:
            validate_topic_name(topic)
        except ValueError:
            logger.warning("非法主题名: %s from %s", topic, session)
            return

        # QoS 1: 立即回复 PUBACK
        if qos == 1 and packet_id:
            await session.send(build_puback(packet_id))

        # 保留消息
        if retain:
            if payload:
                self._retained[topic] = (payload, qos)
            else:
                # 零字节载荷 = 删除保留消息
                self._retained.pop(topic, None)

        # 解码载荷文本（用于日志和数据处理）
        payload_text = ""
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError:
            payload_text = "<binary {} bytes>".format(len(payload))

        logger.debug("PUBLISH: topic=%s qos=%d from=%s payload=%s",
                     topic, qos, session.client_id, payload_text[:120])

        # ---------- 数据处理管道 ----------
        # 匹配 helmet/{device_id}/attributes 和 helmet/{device_id}/sensor 主题
        # 这些数据进入处理管道
        attr_match = re.match(r"^helmet/([^/]+)/(attributes|sensor)$", topic)
        if attr_match:
            device_id = attr_match.group(1)
            await self.data_handler.handle_message(device_id, topic, payload)

        # ---------- 消息路由 ----------
        subscribers = self.router.get_subscribers(topic)
        for sub_sid, sub_qos in subscribers:
            subscriber = self.sessions.get_by_client_id(sub_sid)
            if subscriber is None or not subscriber.is_active:
                continue

            effective_qos = max(qos, 0)  # 取发布 QoS 和订阅 QoS 的最小值
            try:
                pkt = build_publish(
                    topic, payload,
                    qos=effective_qos,
                    retain=retain
                )
                await subscriber.send(pkt)
            except Exception as e:
                logger.warning("发送到 %s 失败: %s", subscriber, e)

    # ---------- SUBSCRIBE ----------

    async def _handle_subscribe(self, session, parsed):
        """处理 SUBSCRIBE 报文"""
        packet_id = parsed["packet_id"]
        topics = parsed["topics"]

        return_codes = []
        for topic_filter, qos in topics:
            try:
                self.router.add_subscription(session.client_id, topic_filter, qos)
                return_codes.append(qos)  # granted QoS
                logger.debug("订阅: %s → %s (qos=%d)",
                             session.client_id, topic_filter, qos)
            except ValueError as e:
                logger.warning("订阅拒绝: %s — %s", topic_filter, e)
                return_codes.append(0x80)  # failure

        await session.send(build_suback(packet_id, return_codes))

        # 对新订阅发送匹配的保留消息
        for topic_filter, _ in topics:
            for retained_topic, (payload, qos) in self._retained.items():
                from .topic_router import topic_matches
                if topic_matches(topic_filter, retained_topic):
                    try:
                        pkt = build_publish(retained_topic, payload, qos=qos, retain=True)
                        await session.send(pkt)
                    except Exception:
                        pass

    # ---------- UNSUBSCRIBE ----------

    async def _handle_unsubscribe(self, session, parsed):
        """处理 UNSUBSCRIBE 报文"""
        packet_id = parsed["packet_id"]
        topics = parsed["topics"]

        for topic_filter in topics:
            self.router.remove_subscription(session.client_id, topic_filter)
            logger.debug("取消订阅: %s → %s", session.client_id, topic_filter)

        await session.send(build_unsuback(packet_id))

    # ---------- 断开 ----------

    async def _on_disconnect(self, session):
        """客户端断开连接后的清理"""
        if not session.is_active:
            await self.sessions.remove(session)
            return

        logger.info("客户端断开: client_id=%s addr=%s",
                     session.client_id, session.addr)

        # 处理遗嘱消息
        if session.will_topic is not None and session.will_message is not None:
            logger.info("发布遗嘱消息: topic=%s", session.will_topic)
            subscribers = self.router.get_subscribers(session.will_topic)
            for sub_sid, sub_qos in subscribers:
                sub = self.sessions.get_by_client_id(sub_sid)
                if sub and sub.is_active:
                    try:
                        pkt = build_publish(
                            session.will_topic,
                            session.will_message,
                            qos=session.will_qos,
                            retain=session.will_retain,
                        )
                        await sub.send(pkt)
                    except Exception:
                        pass

            # 遗嘱保留
            if session.will_retain:
                self._retained[session.will_topic] = (
                    session.will_message, session.will_qos
                )

        # 清理订阅
        self.router.remove_all_subscriptions(session.client_id)
        await self.sessions.remove(session)

    # ---------- 保活检测 ----------

    async def _keepalive_loop(self):
        """定期检测过期会话"""
        while self._running:
            await asyncio.sleep(10)  # 每 10 秒检查一次
            wills = await self.sessions.check_expired()

            # 处理遗嘱消息
            for will_topic, will_msg, will_qos, will_retain in wills:
                subscribers = self.router.get_subscribers(will_topic)
                for sub_sid, sub_qos in subscribers:
                    sub = self.sessions.get_by_client_id(sub_sid)
                    if sub and sub.is_active:
                        try:
                            pkt = build_publish(
                                will_topic, will_msg,
                                qos=will_qos, retain=will_retain,
                            )
                            await sub.send(pkt)
                        except Exception:
                            pass

    # ---------- 服务端发布 ----------

    async def _broker_publish(self, topic, payload, qos=0, retain=False):
        """
        服务端向订阅者发布消息（由数据处理管道等内部组件调用）

        :param topic:   主题字符串
        :param payload: 载荷（字符串或字节）
        :param qos:     QoS 等级
        :param retain:  是否保留
        """
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        # QoS > 0 时需要报文 ID（每个订阅者独立 ID）
        pkt_id = None
        if qos > 0:
            self._pkt_id_counter = (self._pkt_id_counter + 1) % 65535
            if self._pkt_id_counter == 0:
                self._pkt_id_counter = 1
            pkt_id = self._pkt_id_counter

        subscribers = self.router.get_subscribers(topic)
        for sub_sid, sub_qos in subscribers:
            sub = self.sessions.get_by_client_id(sub_sid)
            if sub and sub.is_active:
                try:
                    # 每个订阅者用递增的 packet_id（MQTT 规范要求 QoS>0 时唯一）
                    if qos > 0:
                        self._pkt_id_counter = (self._pkt_id_counter + 1) % 65535
                        if self._pkt_id_counter == 0:
                            self._pkt_id_counter = 1
                        sid = self._pkt_id_counter
                    else:
                        sid = None
                    pkt = build_publish(topic, payload, qos=qos, retain=retain, packet_id=sid)
                    await sub.send(pkt)
                except Exception as e:
                    logger.warning("Broker publish failed to %s: %s", sub, e)
