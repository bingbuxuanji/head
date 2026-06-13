# -*- coding: UTF-8 -*-
"""
MQTT 主题匹配与消息路由

支持 MQTT 3.1.1 通配符：
  - '+'  匹配单层主题
  - '#'  匹配多层主题（仅允许出现在末尾）
"""

import re
import fnmatch
import logging

logger = logging.getLogger("mqtt.topic")

# ---------- Topic 合法性校验 ----------

# MQTT 主题中禁止使用的字符
_TOPIC_FORBIDDEN = {"+", "#"}

# 主题层级正则：不允许空层级
_TOPIC_LEVEL_RE = re.compile(r"^[^/]+$")


def validate_topic_name(topic):
    """
    校验普通主题名（不含通配符）

    :param topic: 主题字符串
    :return: True 合法
    :raises ValueError: 不合法
    """
    if not topic:
        raise ValueError("Topic must not be empty")
    if any(c in topic for c in "\x00"):
        raise ValueError("Topic contains null character")

    levels = topic.split("/")
    for level in levels:
        if not level:
            raise ValueError("Topic contains empty level: {}".format(repr(topic)))
        if "+" in level or "#" in level:
            raise ValueError("Topic name must not contain wildcards '+' or '#': {}".format(repr(topic)))
    return True


def validate_topic_filter(topic_filter):
    """
    校验主题过滤器（可含通配符）

    :param topic_filter: 主题过滤器字符串
    :return: True 合法
    :raises ValueError: 不合法
    """
    if not topic_filter:
        raise ValueError("Topic filter must not be empty")
    if any(c in topic_filter for c in "\x00"):
        raise ValueError("Topic filter contains null character")

    levels = topic_filter.split("/")
    for i, level in enumerate(levels):
        if not level:
            raise ValueError("Topic filter contains empty level")

        # '#' 只能出现在最后一个层级
        if "#" in level:
            if level != "#":
                raise ValueError("'#' must occupy an entire level: {}".format(repr(topic_filter)))
            if i != len(levels) - 1:
                raise ValueError("'#' must be the last level: {}".format(repr(topic_filter)))

        # '+' 只能独占一个层级
        if "+" in level and level != "+":
            raise ValueError("'+' must occupy an entire level: {}".format(repr(topic_filter)))

    return True


# ---------- 通配符匹配 ----------

def topic_matches(topic_filter, topic_name):
    """
    判断 topic_name 是否匹配 topic_filter（含通配符）

    :param topic_filter: 订阅过滤器，如 "sensor/+/temp" 或 "sensor/#"
    :param topic_name:   实际主题名，如 "sensor/device1/temp"
    :return: bool
    """
    filter_levels = topic_filter.split("/")
    topic_levels = topic_name.split("/")

    for i, fl in enumerate(filter_levels):
        if fl == "#":
            # '#' 匹配剩余所有层级（包括空）
            return True
        if fl == "+":
            # '+' 匹配单个层级
            if i >= len(topic_levels):
                return False
            continue
        # 普通层级：精确匹配
        if i >= len(topic_levels) or fl != topic_levels[i]:
            return False

    # 过滤器层级已耗尽，主题层级也必须耗尽才算匹配
    return len(filter_levels) == len(topic_levels)


# ---------- 订阅路由表 ----------

class TopicRouter(object):
    """
    主题路由器：管理订阅关系，提供消息分发

    内部使用哈希表 + 通配符列表混合存储：
      - 精确订阅（无通配符）走 O(1) 查找
      - 通配符订阅走线性匹配（通常数量很少）
    """

    def __init__(self):
        # { topic_filter: set of (session_id, qos) }
        self._subscriptions = {}
        # { session_id: set of topic_filter }  反向索引，用于断开时清理
        self._session_subs = {}
        # 精确主题 → 直接索引，加速无通配符场景
        self._exact_index = {}

    # ---------- 订阅 ----------

    def add_subscription(self, session_id, topic_filter, qos=0):
        """
        添加订阅

        :param session_id:   客户端会话 ID
        :param topic_filter: 主题过滤器（可含通配符）
        :param qos:          订阅 QoS
        """
        validate_topic_filter(topic_filter)

        if topic_filter not in self._subscriptions:
            self._subscriptions[topic_filter] = {}

        self._subscriptions[topic_filter][session_id] = qos

        # 反向索引
        if session_id not in self._session_subs:
            self._session_subs[session_id] = set()
        self._session_subs[session_id].add(topic_filter)

        # 精确索引（无通配符时）
        if "+" not in topic_filter and "#" not in topic_filter:
            self._exact_index.setdefault(topic_filter, {})[session_id] = qos

        logger.debug("SUB: session=%s filter=%s qos=%d", session_id, topic_filter, qos)

    def remove_subscription(self, session_id, topic_filter):
        """
        移除单个订阅
        """
        if topic_filter in self._subscriptions:
            self._subscriptions[topic_filter].pop(session_id, None)
            if not self._subscriptions[topic_filter]:
                del self._subscriptions[topic_filter]

        if session_id in self._session_subs:
            self._session_subs[session_id].discard(topic_filter)

        if topic_filter in self._exact_index:
            self._exact_index[topic_filter].pop(session_id, None)
            if not self._exact_index[topic_filter]:
                del self._exact_index[topic_filter]

    def remove_all_subscriptions(self, session_id):
        """
        移除某个会话的全部订阅（断开连接时调用）
        """
        if session_id not in self._session_subs:
            return

        for topic_filter in list(self._session_subs[session_id]):
            self.remove_subscription(session_id, topic_filter)

        self._session_subs.pop(session_id, None)

    # ---------- 匹配查询 ----------

    def get_subscribers(self, topic_name):
        """
        获取所有匹配该主题的订阅者

        :param topic_name: 发布主题名
        :return: [(session_id, qos), ...]
        """
        result = {}  # session_id → max_qos

        # 1. 精确索引查找（O(1)）
        if topic_name in self._exact_index:
            for sid, qos in self._exact_index[topic_name].items():
                result[sid] = max(result.get(sid, 0), qos)

        # 2. 通配符匹配（遍历含通配符的过滤器）
        for topic_filter, subs in self._subscriptions.items():
            if "+" not in topic_filter and "#" not in topic_filter:
                continue  # 已在精确索引中处理
            if topic_matches(topic_filter, topic_name):
                for sid, qos in subs.items():
                    result[sid] = max(result.get(sid, 0), qos)

        return [(sid, qos) for sid, qos in result.items()]

    def get_session_subscriptions(self, session_id):
        """获取某个会话的所有订阅"""
        return self._session_subs.get(session_id, set())

    # ---------- 统计 ----------

    @property
    def total_subscriptions(self):
        return sum(len(subs) for subs in self._subscriptions.values())

    @property
    def total_filters(self):
        return len(self._subscriptions)
