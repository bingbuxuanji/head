# -*- coding: UTF-8 -*-
"""
MQTT 3.1.1 报文解析与构建

实现 MQTT 固定头部 + 可变头部的二进制编解码，
支持 QoS 0/1 和基础控制报文类型。
"""

import struct
import logging

logger = logging.getLogger("mqtt.packet")

# ---------- MQTT 控制报文类型 ----------
CONNECT      = 1
CONNACK      = 2
PUBLISH      = 3
PUBACK       = 4
PUBREC       = 5
PUBREL       = 6
PUBCOMP      = 7
SUBSCRIBE    = 8
SUBACK       = 9
UNSUBSCRIBE  = 10
UNSUBACK     = 11
PINGREQ      = 12
PINGRESP     = 13
DISCONNECT   = 14

PACKET_NAMES = {
    1: "CONNECT", 2: "CONNACK", 3: "PUBLISH", 4: "PUBACK",
    5: "PUBREC", 6: "PUBREL", 7: "PUBCOMP", 8: "SUBSCRIBE",
    9: "SUBACK", 10: "UNSUBSCRIBE", 11: "UNSUBACK",
    12: "PINGREQ", 13: "PINGRESP", 14: "DISCONNECT",
}

# ---------- CONNACK 返回码 ----------
CONNACK_ACCEPTED              = 0
CONNACK_REFUSED_PROTOCOL      = 1
CONNACK_REFUSED_ID_REJECTED   = 2
CONNACK_REFUSED_SERVER_UNAVAIL= 3
CONNACK_REFUSED_BAD_USER_PWD  = 4
CONNACK_REFUSED_NOT_AUTHORIZED= 5


class MQTTPacketError(Exception):
    """MQTT 报文解析错误"""
    pass


class ProtocolError(MQTTPacketError):
    """协议违规"""
    pass


# ==================== 编码工具 ====================

def encode_remaining_length(length):
    """编码剩余长度（变长编码，1-4字节）"""
    if length < 0 or length > 268435455:
        raise ValueError("Remaining length out of range: {}".format(length))
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        encoded.append(digit)
        if length == 0:
            break
    return bytes(encoded)


def decode_remaining_length(data, offset=0):
    """解码剩余长度，返回 (length, bytes_consumed)"""
    multiplier = 1
    value = 0
    consumed = 0
    while True:
        if offset + consumed >= len(data):
            raise MQTTPacketError("Incomplete remaining length")
        digit = data[offset + consumed]
        consumed += 1
        value += (digit & 0x7F) * multiplier
        if value > 268435455:
            raise MQTTPacketError("Remaining length exceeds maximum")
        if (digit & 0x80) == 0:
            break
        multiplier *= 128
        if multiplier > 128 * 128 * 128:
            raise MQTTPacketError("Malformed remaining length")
    return value, consumed


def encode_utf8(s):
    """编码 MQTT UTF-8 字符串：2字节长度前缀 + UTF-8数据"""
    if isinstance(s, str):
        s = s.encode("utf-8")
    if len(s) > 65535:
        raise ValueError("String too long for MQTT UTF-8")
    return struct.pack("!H", len(s)) + s


def decode_utf8(data, offset=0):
    """解码 MQTT UTF-8 字符串，返回 (str, new_offset)"""
    if offset + 2 > len(data):
        raise MQTTPacketError("Incomplete UTF-8 length prefix")
    length = struct.unpack("!H", data[offset:offset + 2])[0]
    if offset + 2 + length > len(data):
        raise MQTTPacketError("Truncated UTF-8 string")
    s = data[offset + 2:offset + 2 + length].decode("utf-8", errors="replace")
    return s, offset + 2 + length


# ==================== 固定头部 ====================

def build_fixed_header(packet_type, flags, remaining_length):
    """构建 MQTT 固定头部"""
    byte1 = (packet_type << 4) | flags
    return bytes([byte1]) + encode_remaining_length(remaining_length)


def parse_fixed_header(data, offset=0):
    """
    解析固定头部，返回 dict:
      packet_type, flags, remaining_length, header_length
    """
    if offset >= len(data):
        raise MQTTPacketError("Empty packet")
    byte1 = data[offset]
    packet_type = (byte1 & 0xF0) >> 4
    flags = byte1 & 0x0F
    rem_len, consumed = decode_remaining_length(data, offset + 1)
    return {
        "packet_type": packet_type,
        "flags": flags,
        "remaining_length": rem_len,
        "header_length": 1 + consumed,
    }


# ==================== 各报文构建 ====================

def build_connack(session_present=False, return_code=CONNACK_ACCEPTED):
    """构建 CONNACK 报文"""
    sp = 1 if session_present else 0
    variable = bytes([sp, return_code])
    header = build_fixed_header(CONNACK, 0, len(variable))
    return header + variable


def build_publish(topic, payload, qos=0, retain=False, packet_id=None, dup=False):
    """
    构建 PUBLISH 报文
    :param topic:   主题字符串
    :param payload: 载荷字节
    :param qos:     QoS 等级 (0 或 1)
    :param retain:  保留标志
    :param packet_id: QoS>0 时的报文标识符
    :param dup:     DUP 标志
    """
    flags = 0
    if retain:
        flags |= 0x01
    flags |= (qos & 0x03) << 1
    if dup:
        flags |= 0x08

    variable = encode_utf8(topic)
    if qos > 0:
        if packet_id is None:
            raise ValueError("packet_id required for QoS > 0")
        variable += struct.pack("!H", packet_id)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    remaining = len(variable) + len(payload)
    header = build_fixed_header(PUBLISH, flags, remaining)
    return header + variable + payload


def build_puback(packet_id):
    """构建 PUBACK 报文"""
    variable = struct.pack("!H", packet_id)
    header = build_fixed_header(PUBACK, 0, len(variable))
    return header + variable


def build_pubrec(packet_id):
    """构建 PUBREC 报文"""
    variable = struct.pack("!H", packet_id)
    header = build_fixed_header(PUBREC, 0, len(variable))
    return header + variable


def build_pubrel(packet_id):
    """构建 PUBREL 报文"""
    variable = struct.pack("!H", packet_id)
    header = build_fixed_header(PUBREL, 2, len(variable))  # flags=2 for PUBREL
    return header + variable


def build_pubcomp(packet_id):
    """构建 PUBCOMP 报文"""
    variable = struct.pack("!H", packet_id)
    header = build_fixed_header(PUBCOMP, 0, len(variable))
    return header + variable


def build_suback(packet_id, return_codes):
    """构建 SUBACK 报文"""
    variable = struct.pack("!H", packet_id) + bytes(return_codes)
    header = build_fixed_header(SUBACK, 0, len(variable))
    return header + variable


def build_unsuback(packet_id):
    """构建 UNSUBACK 报文"""
    variable = struct.pack("!H", packet_id)
    header = build_fixed_header(UNSUBACK, 0, len(variable))
    return header + variable


def build_pingresp():
    """构建 PINGRESP 报文"""
    return bytes([0xD0, 0x00])


def build_disconnect():
    """构建 DISCONNECT 报文"""
    return bytes([0xE0, 0x00])


# ==================== 各报文解析 ====================

def parse_connect(data, offset=0):
    """
    解析 CONNECT 报文，返回 dict:
      protocol_name, protocol_level, username_flag, password_flag,
      will_retain, will_qos, will_flag, clean_session, keepalive,
      client_id, username, password, will_topic, will_message
    """
    start = offset
    protocol_name, offset = decode_utf8(data, offset)
    if protocol_name not in ("MQTT", "MQIsdp"):
        raise ProtocolError("Unknown protocol: {}".format(protocol_name))

    if offset >= len(data):
        raise MQTTPacketError("Incomplete CONNECT")
    protocol_level = data[offset]
    offset += 1

    if offset >= len(data):
        raise MQTTPacketError("Incomplete CONNECT flags")
    flags = data[offset]
    offset += 1

    username_flag = bool(flags & 0x80)
    password_flag = bool(flags & 0x40)
    will_retain    = bool(flags & 0x20)
    will_qos       = (flags >> 3) & 0x03
    will_flag      = bool(flags & 0x04)
    clean_session  = bool(flags & 0x02)

    if offset + 2 > len(data):
        raise MQTTPacketError("Incomplete CONNECT keepalive")
    keepalive = struct.unpack("!H", data[offset:offset + 2])[0]
    offset += 2

    client_id, offset = decode_utf8(data, offset)

    result = {
        "protocol_name": protocol_name,
        "protocol_level": protocol_level,
        "username_flag": username_flag,
        "password_flag": password_flag,
        "will_retain": will_retain,
        "will_qos": will_qos,
        "will_flag": will_flag,
        "clean_session": clean_session,
        "keepalive": keepalive,
        "client_id": client_id,
        "username": None,
        "password": None,
        "will_topic": None,
        "will_message": None,
    }

    if will_flag:
        result["will_topic"], offset = decode_utf8(data, offset)
        if offset + 2 > len(data):
            raise MQTTPacketError("Incomplete will message")
        will_msg_len = struct.unpack("!H", data[offset:offset + 2])[0]
        offset += 2
        result["will_message"] = data[offset:offset + will_msg_len]
        offset += will_msg_len

    if username_flag:
        result["username"], offset = decode_utf8(data, offset)

    if password_flag:
        result["password"], offset = decode_utf8(data, offset)

    return result


def parse_publish(header, data, offset=0):
    """
    解析 PUBLISH 报文，返回 dict:
      topic, payload, qos, retain, dup, packet_id
    """
    flags = header["flags"]
    retain = bool(flags & 0x01)
    qos = (flags >> 1) & 0x03
    dup = bool(flags & 0x08)

    topic, offset = decode_utf8(data, offset)

    packet_id = None
    if qos > 0:
        if offset + 2 > len(data):
            raise MQTTPacketError("Incomplete packet_id in PUBLISH")
        packet_id = struct.unpack("!H", data[offset:offset + 2])[0]
        offset += 2

    payload = data[offset:offset + header["remaining_length"] - (offset - 0)]

    return {
        "topic": topic,
        "payload": payload,
        "qos": qos,
        "retain": retain,
        "dup": dup,
        "packet_id": packet_id,
    }


def parse_subscribe(data, offset=0):
    """
    解析 SUBSCRIBE 报文，返回 dict:
      packet_id, topics: [(topic_filter, qos), ...]
    """
    if offset + 2 > len(data):
        raise MQTTPacketError("Incomplete SUBSCRIBE packet_id")
    packet_id = struct.unpack("!H", data[offset:offset + 2])[0]
    offset += 2

    topics = []
    end = len(data)
    while offset < end:
        topic_filter, offset = decode_utf8(data, offset)
        if offset >= end:
            raise MQTTPacketError("Incomplete SUBSCRIBE QoS")
        qos = data[offset] & 0x03
        offset += 1
        topics.append((topic_filter, qos))

    return {"packet_id": packet_id, "topics": topics}


def parse_unsubscribe(data, offset=0):
    """
    解析 UNSUBSCRIBE 报文，返回 dict:
      packet_id, topics: [topic_filter, ...]
    """
    if offset + 2 > len(data):
        raise MQTTPacketError("Incomplete UNSUBSCRIBE packet_id")
    packet_id = struct.unpack("!H", data[offset:offset + 2])[0]
    offset += 2

    topics = []
    end = len(data)
    while offset < end:
        topic_filter, offset = decode_utf8(data, offset)
        topics.append(topic_filter)

    return {"packet_id": packet_id, "topics": topics}


def parse_puback(data, offset=0):
    """解析 PUBACK，返回 packet_id"""
    return struct.unpack("!H", data[offset:offset + 2])[0]


# ==================== 报文完整解析入口 ====================

def parse_packet(data):
    """
    解析一个完整的 MQTT 报文，返回 dict:
      type, type_name, parsed_data (因报文类型而异)
    或 None（数据不完整时）
    """
    if not data:
        return None

    try:
        header = parse_fixed_header(data)
    except MQTTPacketError:
        return None

    total_len = header["header_length"] + header["remaining_length"]
    if len(data) < total_len:
        return None  # 不完整，等待更多数据

    packet_type = header["packet_type"]
    offset = header["header_length"]
    payload_data = data[offset:total_len]

    result = {
        "type": packet_type,
        "type_name": PACKET_NAMES.get(packet_type, "UNKNOWN"),
        "total_length": total_len,
    }

    try:
        if packet_type == CONNECT:
            result["parsed"] = parse_connect(payload_data)
        elif packet_type == PUBLISH:
            result["parsed"] = parse_publish(header, payload_data)
        elif packet_type == PUBACK:
            result["parsed"] = {"packet_id": parse_puback(payload_data)}
        elif packet_type == PUBREC:
            result["parsed"] = {"packet_id": struct.unpack("!H", payload_data[:2])[0]}
        elif packet_type == PUBREL:
            result["parsed"] = {"packet_id": struct.unpack("!H", payload_data[:2])[0]}
        elif packet_type == PUBCOMP:
            result["parsed"] = {"packet_id": struct.unpack("!H", payload_data[:2])[0]}
        elif packet_type == SUBSCRIBE:
            result["parsed"] = parse_subscribe(payload_data)
        elif packet_type == UNSUBSCRIBE:
            result["parsed"] = parse_unsubscribe(payload_data)
        elif packet_type in (PINGREQ, PINGRESP, DISCONNECT):
            result["parsed"] = {}
        else:
            logger.warning("Unknown packet type: %d", packet_type)
            result["parsed"] = {}
    except (MQTTPacketError, struct.error, IndexError) as e:
        logger.error("Packet parse error: %s", e)
        raise ProtocolError("Parse failed: {}".format(e))

    return result
