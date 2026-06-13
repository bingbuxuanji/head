# -*- coding: UTF-8 -*-
"""
MQTT 客户端会话管理

每个 TCP 连接对应一个 Session，维护：
  - 连接状态
  - 保活计时
  - 遗嘱消息
  - 未确认的 QoS 1 消息
"""

import time
import asyncio
import logging

from . import config

logger = logging.getLogger("mqtt.session")


class Session(object):
    """
    MQTT 客户端会话

    生命周期：TCP 连接建立 → CONNECT → ... → DISCONNECT / 超时 → 销毁
    """

    __slots__ = (
        "client_id", "username", "reader", "writer",
        "clean_session", "keepalive",
        "will_topic", "will_message", "will_qos", "will_retain",
        "connected_at", "last_packet_at",
        "_addr", "_active",
    )

    def __init__(self, reader, writer):
        self.client_id = None       # CONNECT 后设置
        self.username = None
        self.reader = reader        # asyncio.StreamReader
        self.writer = writer        # asyncio.StreamWriter
        self.clean_session = True
        self.keepalive = 60
        self.will_topic = None
        self.will_message = None
        self.will_qos = 0
        self.will_retain = False
        self.connected_at = time.time()
        self.last_packet_at = time.time()
        self._addr = writer.get_extra_info("peername", ("?", 0))
        self._active = False        # True after successful CONNECT

    @property
    def addr(self):
        return "{}:{}".format(*self._addr) if self._addr else "?"

    @property
    def is_active(self):
        """是否已完成 CONNECT 握手"""
        return self._active

    def activate(self, connect_info):
        """
        CONNECT 成功后激活会话

        :param connect_info: parse_connect() 返回的字典
        """
        self.client_id = connect_info.get("client_id", "")
        self.username = connect_info.get("username")
        self.clean_session = connect_info.get("clean_session", True)
        self.keepalive = connect_info.get("keepalive", 60)

        # 遗嘱消息
        if connect_info.get("will_flag"):
            self.will_topic = connect_info.get("will_topic")
            self.will_message = connect_info.get("will_message")
            self.will_qos = connect_info.get("will_qos", 0)
            self.will_retain = connect_info.get("will_retain", False)

        self._active = True
        logger.info("Session activated: client_id=%s addr=%s keepalive=%ds",
                     self.client_id, self.addr, self.keepalive)

    def touch(self):
        """更新最近报文时间（用于保活判断）"""
        self.last_packet_at = time.time()

    def is_expired(self):
        """
        判断保活是否超时

        超时 = keepalive * KEEPALIVE_MULTIPLIER（配置中默认 1.5 倍）
        若 keepalive 为 0 则永不过期
        """
        if self.keepalive == 0:
            return False
        timeout = self.keepalive * config.KEEPALIVE_MULTIPLIER
        return (time.time() - self.last_packet_at) > timeout

    @property
    def idle_seconds(self):
        """空闲秒数"""
        return time.time() - self.last_packet_at

    async def send(self, data):
        """发送原始字节到客户端"""
        try:
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            logger.warning("Send to %s failed: %s", self.addr, e)
            raise

    async def close(self):
        """关闭连接"""
        self._active = False
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass

    def __repr__(self):
        cid = self.client_id or "?"
        return "Session({}, {})".format(cid, self.addr)


class SessionManager(object):
    """
    会话管理器

    职责：
      - 创建/销毁会话
      - 按 client_id 查找会话（用于定向消息推送）
      - 检测过期会话
    """

    def __init__(self):
        # { session_object: None } — 用于遍历所有活跃会话
        self._all = {}
        # { client_id: session_object }
        self._by_client_id = {}
        self._lock = asyncio.Lock()

    async def create(self, reader, writer):
        """创建新 Session"""
        session = Session(reader, writer)
        async with self._lock:
            self._all[session] = True
        return session

    async def activate(self, session, connect_info):
        """
        激活会话（CONNECT 成功后调用）

        如果同 client_id 已有旧会话，关闭旧会话。
        """
        client_id = connect_info.get("client_id", "")

        async with self._lock:
            if client_id and client_id in self._by_client_id:
                old = self._by_client_id[client_id]
                if old is not session:
                    logger.info("Kicking old session for client_id=%s", client_id)
                    await self._remove_internal(old)
                    try:
                        await old.close()
                    except Exception:
                        pass

            session.activate(connect_info)
            if client_id:
                self._by_client_id[client_id] = session

    async def remove(self, session):
        """移除会话"""
        async with self._lock:
            await self._remove_internal(session)

    async def _remove_internal(self, session):
        """内部移除（调用方需持有 _lock）"""
        self._all.pop(session, None)
        if session.client_id and session.client_id in self._by_client_id:
            if self._by_client_id.get(session.client_id) is session:
                del self._by_client_id[session.client_id]

    def get_by_client_id(self, client_id):
        """按 client_id 查找会话"""
        return self._by_client_id.get(client_id)

    async def check_expired(self):
        """检测并关闭所有过期会话，返回 [(session, will_topic, will_msg, will_qos, will_retain), ...]"""
        expired = []
        wills = []

        async with self._lock:
            for session in list(self._all):
                if session.is_expired():
                    expired.append(session)
                    # 收集遗嘱消息
                    if session.will_topic is not None:
                        wills.append((
                            session.will_topic,
                            session.will_message,
                            session.will_qos,
                            session.will_retain,
                        ))
                    await self._remove_internal(session)

        for session in expired:
            logger.info("Session expired: %s (idle=%.1fs)", session, session.idle_seconds)
            try:
                await session.close()
            except Exception:
                pass

        return wills

    @property
    def active_count(self):
        return len(self._all)

    def get_all(self):
        """获取所有活跃会话列表"""
        return list(self._all.keys())
