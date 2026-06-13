# -*- coding: UTF-8 -*-
"""
智能头盔 MQTT 客户端（原 ThingsCloud → 自建 MQTT 服务器）

基于 QuecPython umqtt，连接自建 MQTT Broker 实现属性上报、
事件上报与下行指令接收。

认证方式: 用户名 + 密码（设备自动注册）

Topic 约定:
  设备上行:
    helmet/{device_id}/attributes   — 属性数据 (JSON)
    helmet/{device_id}/events       — 事件数据 (JSON)
    helmet/{device_id}/sensor       — 原始传感器数据

  服务端下行:
    helmet/{device_id}/commands     — 下行指令

使用示例:
    client = ThingsCloudMQTT(
        endpoint="192.168.1.100",     # 自建 MQTT 服务器地址
        port=1883,
        username="helmet_001",
        password="helmet_key_001",
        client_id="helmet_001"
    )
    client.connect()
    client.publish_attributes({"temperature": 36.5, "longitude": 104.07572})
    client.disconnect()
"""

from umqtt import MQTTClient
from usr.threading import Lock
from usr.logging import getLogger

logger = getLogger(__name__)


class ThingsCloudMQTT(object):
    """
    智能头盔 MQTT 客户端（API 兼容原 ThingsCloud 接口）

    职责：
    - 连接自建 MQTT Broker
    - 发布属性数据到 helmet/{device_id}/attributes 主题
    - 发布事件数据到 helmet/{device_id}/events 主题
    - 订阅并接收云端下行指令 helmet/{device_id}/commands
    """

    # ---------- 初始化 ----------

    def __init__(self, endpoint, port=1883, username="", password="",
                 client_id="", keepalive=30,
                 access_token=None, project_key=None):
        """
        初始化 MQTT 客户端

        新参数（自建服务器）:
        :param endpoint:  MQTT 服务器地址（IP 或域名）
        :param port:      MQTT 端口，默认 1883
        :param username:  MQTT 用户名（设备标识，如 'helmet_001'）
        :param password:  MQTT 密码
        :param client_id: MQTT 客户端 ID，默认与 username 相同
        :param keepalive: 保活间隔（秒），默认 30（穿透场景推荐值）

        旧参数（ThingsCloud，已弃用但保留兼容）:
        :param access_token: ThingsCloud AccessToken → 映射为 username
        :param project_key:  ThingsCloud ProjectKey  → 映射为 password
        """
        # ---- 兼容旧版 ThingsCloud 参数名 ----
        if access_token is not None:
            username = access_token
        if project_key is not None:
            password = project_key

        self._endpoint = endpoint
        self._port = port
        self._username = username or ""
        self._password = password or ""
        self._client_id = client_id if client_id else (self._username or "helmet_device")
        self._keepalive = keepalive

        self._client = None            # MQTTClient 实例
        self._lock = Lock()            # 保护 _client
        self._downlink_callback = None  # 下行指令回调: fn(topic, msg)

        # ---------- 属性管理 ----------
        self._attributes = {}          # 已注册的属性元信息
        self._attr_values = {}         # 当前属性值

        # ---------- Topic 构建 ----------
        self._topic_attr = "helmet/{}/attributes".format(self._client_id)
        self._topic_event = "helmet/{}/events".format(self._client_id)
        self._topic_sensor = "helmet/{}/sensor".format(self._client_id)
        self._topic_cmd = "helmet/{}/commands".format(self._client_id)

    # ---------- 连接管理 ----------

    def connect(self, clean_session=True):
        """
        连接自建 MQTT 服务器

        :param clean_session: 是否清除服务端会话
        :return: 0 成功，-1 失败
        """
        with self._lock:
            try:
                self._client = MQTTClient(
                    self._client_id,
                    self._endpoint,
                    port=self._port,
                    user=self._username,
                    password=self._password,
                    keepalive=self._keepalive
                )
                # 注册下行消息回调
                self._client.set_callback(self.__on_message)
                # 注册内部异常回调
                self._client.error_register_cb(self.__on_error)

                result = self._client.connect(clean_session)
                if result == 0:
                    logger.info("MQTT connected: {}:{} as {}".format(
                        self._endpoint, self._port, self._client_id))

                    # 订阅下行指令主题
                    try:
                        self._client.subscribe(self._topic_cmd, qos=1)
                        logger.info("Subscribed: {}".format(self._topic_cmd))
                    except Exception as e:
                        logger.warn("Subscribe failed: {}".format(e))

                    return 0
                else:
                    logger.error("MQTT connect failed, result={}".format(result))
                    return -1
            except Exception as e:
                logger.error("MQTT connect exception: {}".format(e))
                return -1

    def disconnect(self):
        """断开 MQTT 连接并释放资源"""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception as e:
                    logger.warn("MQTT disconnect exception: {}".format(e))
                self._client = None
        logger.info("MQTT disconnected")

    @property
    def is_connected(self):
        """查询是否已连接"""
        with self._lock:
            if self._client is None:
                return False
        try:
            return self._client.get_mqttsta() == 0
        except Exception:
            return False

    # ---------- 属性管理 ----------

    def register_attribute(self, name, unit="", min_val=None, max_val=None, precision=None):
        """
        注册一个设备属性（元信息，本地记录）

        与原 ThingsCloud 接口兼容，在自建服务器模式下仅本地记录元信息。

        :param name:      属性名，如 'temperature'
        :param unit:      单位，如 '°C'
        :param min_val:   最小值
        :param max_val:   最大值
        :param precision: 精度
        :return: 0
        """
        self._attributes[name] = {
            "unit": unit,
            "min": min_val,
            "max": max_val,
            "precision": precision
        }
        return 0

    def set_attributes(self, data_dict):
        """
        设置属性值（合并到内部缓存，覆盖同名 key）

        :param data_dict: 属性字典，如 {"temperature": 36.5}
        :return: 0
        """
        self._attr_values.update(data_dict)
        return 0

    # ---------- 属性上报 ----------

    def publish_attributes(self, data_dict=None):
        """
        上报属性数据到 MQTT 服务器

        发布到主题: helmet/{device_id}/attributes

        :param data_dict: 属性字典，如 {"temperature": 34.2}。
                          为 None 时使用 set_attributes() 设置的内部缓存。
        :return: 0 成功，-1 失败
        """
        if data_dict is None:
            if not self._attr_values:
                logger.warn("MQTT no attributes to publish")
                return -1
            data_dict = self._attr_values

        if not self.is_connected:
            logger.warn("MQTT not connected, cannot publish")
            return -1

        import ujson as json
        try:
            payload = json.dumps(data_dict)
            self._client.publish(self._topic_attr, payload.encode('utf-8'))
            logger.debug("Attributes published to {}: {}".format(
                self._topic_attr, data_dict))
            return 0
        except Exception as e:
            logger.error("Publish attributes error: {}".format(e))
            return -1

    def publish_event(self, event_id, params=None):
        """
        上报事件到 MQTT 服务器

        发布到主题: helmet/{device_id}/events

        :param event_id: 事件标识符，如 'device_online'
        :param params:   事件参数字典，可选
        :return: 0 成功，-1 失败
        """
        import ujson as json
        data = {"event": event_id}
        if params:
            data["params"] = params
        return self._publish_to_topic(self._topic_event, json.dumps(data))

    def publish_sensor(self, data_dict):
        """
        上报原始传感器数据

        发布到主题: helmet/{device_id}/sensor

        :param data_dict: 传感器数据字典
        :return: 0 成功，-1 失败
        """
        import ujson as json
        return self._publish_to_topic(self._topic_sensor, json.dumps(data_dict))

    # ---------- 下行消息 ----------

    def set_downlink_callback(self, callback):
        """
        注册云端下行指令回调

        :param callback: callable(topic, msg)
                         topic — 字符串类型的主题
                         msg   — 字符串类型的消息体
        """
        self._downlink_callback = callback

    def __on_message(self, topic, msg):
        """下行消息内部回调"""
        try:
            # 统一转字符串（方便业务层处理）
            topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
            msg_str = msg.decode('utf-8') if isinstance(msg, bytes) else msg

            logger.debug("Downlink: topic={}, msg={}".format(
                topic_str, msg_str[:100] if msg_str else msg_str))

            if self._downlink_callback is not None:
                self._downlink_callback(topic_str, msg_str)
        except Exception as e:
            logger.error("Downlink callback error: {}".format(e))

    def __on_error(self, error_info):
        """MQTT 内部线程异常回调"""
        logger.error("MQTT internal error: {}".format(error_info))

    # ---------- 内部方法 ----------

    def _publish_to_topic(self, topic, payload):
        """发布消息到指定 topic"""
        if not self.is_connected:
            logger.warn("MQTT not connected, cannot publish to {}".format(topic))
            return -1
        try:
            if isinstance(topic, str):
                topic = topic.encode('utf-8')
            if isinstance(payload, str):
                payload = payload.encode('utf-8')
            self._client.publish(topic, payload)
            logger.debug("Published to {}: {}".format(topic, payload[:80] if payload else ""))
            return 0
        except Exception as e:
            logger.error("Publish to {} error: {}".format(topic, e))
            return -1
