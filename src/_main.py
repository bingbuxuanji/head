# -*- coding: UTF-8 -*-
"""
提升 CPU 主频: AT+LOG=17,5
"""
import utime
import gc
from machine import ExtInt,Pin
from misc import PowerKey, Power
from usr.protocol import WebSocketClient
from usr.utils import ChargeManager, AudioManager, NetManager, TaskManager, name, Button, Massage, CommandDispatcher
from usr.threading import Thread, Event, Condition
from usr.logging import getLogger
import sys_bus
import _thread
import ujson as json
from misc import USB
#from usr.helmet import AmapAPI, Point, Step, Route
from usr.helmet_test import AmapAPI, Point, Step, Route, Navigator, NavigationManager
from usr.thingscloud import ThingsCloudMQTT
# from usr import UI


logger = getLogger(__name__)



class Led(object):

    def __init__(self, GPIOn):
        self.__led = Pin(
            getattr(Pin, 'GPIO{}'.format(GPIOn)),
            Pin.OUT,
            Pin.PULL_PD,
            0
        )
        self.__off_period = 1000
        self.__on_period = 1000
        self.__count = 0
        self.__running_cond = Condition()
        self.__blink_thread = None
        self.off()

    @property
    def status(self):
        with self.__running_cond:
            return self.__led.read()

    def on(self):
        with self.__running_cond:
            self.__count = 0
            return self.__led.write(0)

    def off(self):
        with self.__running_cond:
            self.__count = 0
            return self.__led.write(1)

    def blink(self, on_period=50, off_period=50, count=None):
        if not isinstance(count, (int, type(None))):
            raise TypeError('count must be int or None type')
        with self.__running_cond:
            if self.__blink_thread is None:
                self.__blink_thread = Thread(target=self.__blink_thread_worker)
                self.__blink_thread.start()
            self.__on_period = on_period
            self.__off_period = off_period
            self.__count = count
            self.__running_cond.notify_all()

    def __blink_thread_worker(self):
        while True:
            with self.__running_cond:
                if self.__count is not None:
                    self.__running_cond.wait_for(lambda: self.__count is None or self.__count > 0)
                status = self.__led.read()
                self.__led.write(1 - status)
                utime.sleep_ms(self.__on_period if status else self.__off_period)
                self.__led.write(status)
                utime.sleep_ms(self.__on_period if status else self.__off_period)
                if self.__count is not None:
                    self.__count -= 1

enable_flag=0

class Application(object):

    def __init__(self):
        
        # 初始化 led; write(1) 灭； write(0) 亮
        self.wifi_red_led = Led(33)
        self.wifi_green_led = Led(32) #ai
        self.power_red_led = Led(39) 
        self.power_green_led = Led(38) #power
        self.lte_red_led = Led(23)
        self.lte_green_led = Led(24)#chat
        self.led_power_pin = Pin(Pin.GPIO27, Pin.OUT, Pin.PULL_DISABLE, 1)
        self.prev_emoj = None
        # self.power_green_led.blink(500, 500)
        self.power_key = PowerKey()
        self.power_key.powerKeyEventRegister(lambda status: None)
        
        
        # 初始化充电管理
        self.charge_manager = ChargeManager()

        # 初始化音频管理
        self.audio_manager = AudioManager()
        self.audio_manager.set_kws_cb(self.on_keyword_spotting)
        self.audio_manager.set_vad_cb(self.on_voice_activity_detection)

        # 初始化网络管理
        self.net_manager = NetManager()

        # 初始化任务调度器
        self.task_manager = TaskManager()

        # 初始化协议
        self.__protocol = WebSocketClient()
        self.__protocol.set_callback(
            audio_message_handler=self.on_audio_message,
            json_message_handler=self.on_json_message
        )

        self.__working_thread = None
        self.__record_thread = None
        self.__record_thread_stop_event = Event()
        self.__voice_activity_event = Event()
        self.__keyword_spotting_event = Event()

        # MQTT 后台 GPS 定时上报线程
        self.__tc_gps_thread = None
        self.__tc_gps_stop_event = Event()

        # self.gpio_pin = Pin(Pin.GPIO41, Pin.OUT, Pin.PULL_PD,0)

        # 初始化唤醒按键
        self.volumedown = ExtInt(ExtInt.GPIO28, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.setvolumedown, 200)
        # self.power_down = ExtInt(ExtInt.GPIO41, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.power_down_handle, 200)
        self.volumeup = ExtInt(ExtInt.GPIO29, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.setvolumeup, 200)
        # self.wakeup_key = Button(41, delay=3000, long_press_callback=self.power_down_handle, short_press_callback= self.on_talk_key_click)
        self.dispatcher = None          # 命令分发器
        self.uart = None                # 串口实例

        self.amap = AmapAPI(
            weather_key='2bffc6260ecb517988c9adeeac9534fa',
            direction_key='76d6a836a53dcd3d6b2bc07bcde85813',
            coding_key='ba2b8fb40f4b52ce161ca1584f99852e'
        )

        # 导航相关
        self.nav_manager = NavigationManager()
        self.current_lat = None
        self.current_lng = None
        self._gps_updated = False
        self._gps_request_pending = False
        self._svr_tts_active = False
        self._svr_tts_stop_time = 0
        self._gps_lock = _thread.allocate_lock()
        self._replanning = False

        # ThingsCloud MQTT 云平台客户端 → 自建 MQTT 服务器
        self.thingscloud = None
        self._last_tc_upload = 0          # 上次上传时间戳（ms），用于限频

        # 后台 GPS 定时器（统一管理导航 + MQTT 的 GPS 请求）
        self._last_bg_gps_request = 0     # 后台线程上次请求 GPS 的时间戳（ms）
        self._nav_gps_interval = 2000     # 导航期间 GPS 请求间隔（ms）
        self._tc_gps_interval = 30000     # 非导航期间 GPS 请求间隔（ms），默认 30 秒
        self._gps_request_time = 0        # GPS 请求发出时间戳（ms），用于 2 秒超时保护

        # 传感器数据由从机主动推送（事件上报），无需主机轮询
        # 见 readme.md §9.7 传感器模块 — 交互模式: 事件上报

        self.nav_manager.on_step_changed = self._on_nav_step_changed
        self.nav_manager.on_off_course = self._on_nav_off_course
        self.nav_manager.on_arrived = self._on_nav_arrived

    def _gps_default_handler(self, data):
        try:
            gps_str = data.decode().strip()
            if gps_str.startswith('g'):
                gps_str = gps_str[1:]
            gps_str = gps_str.strip("'")
            if ',' not in gps_str:
                logger.warn("Invalid GPS data format: {}".format(gps_str))
                return
            a_str, b_str = gps_str.split(',')
            a = float(a_str)
            b = float(b_str)

            if -90 <= a <= 90 and -180 <= b <= 180:
                latitude, longitude = a, b
            elif -90 <= b <= 90 and -180 <= a <= 180:
                latitude, longitude = b, a
            else:
                logger.warn("GPS coords out of range: a={}, b={}".format(a, b))
                return

            logger.info("GPS parsed: latitude={}, longitude={}".format(latitude, longitude))

            self._gps_lock.acquire()
            self.current_lat = latitude
            self.current_lng = longitude
            self._gps_updated = True
            self._gps_request_pending = False
            self._gps_lock.release()

            sys_bus.publish("GPS_DATA", {"latitude": latitude, "longitude": longitude})
            self._on_gps_for_navigation(longitude, latitude)

            # MQTT 经纬度上报（限频 30 秒，含断线重连）
            self._upload_gps_to_thingscloud(latitude, longitude)
        except Exception as e:
            logger.error("GPS parse error: {}".format(e))

    def _upload_gps_to_thingscloud(self, latitude, longitude):
        """上传 GPS 坐标到自建 MQTT 服务器（限频 30 秒，含断线重连）

        由 _gps_default_handler 在收到 GPS 数据后调用，
        内部自行限频，不会每次收到 GPS 都上传。
        """
        if self.thingscloud is None:
            return
        now = utime.ticks_ms()
        if not self.thingscloud.is_connected:
            # 断线后限频重连，避免在网络不可用时频繁尝试
            if utime.ticks_diff(now, self._last_tc_upload) >= 30000:
                if self.thingscloud.connect() == 0:
                    logger.info("MQTT 已重连")
                self._last_tc_upload = now
        else:
            if utime.ticks_diff(now, self._last_tc_upload) >= 30000:
                self.thingscloud.set_attributes({
                    "longitude": round(longitude, 6),
                    "latitude": round(latitude, 6)
                })
                self.thingscloud.publish_attributes()
                self._last_tc_upload = now

    # ---------- 传感器数据处理 ----------
    def _sensor_handler(self, data):
        """处理从机上报的传感器数据（s 报文）

        协议格式: s<temperature>,<heart_rate>,<velocity>
        示例:   s36.5,75,12.3
        占位:   s-1,-1,-1 表示该传感器无数据

        由 CommandDispatcher 在收到 UART 's' 消息时回调。
        """
        try:
            raw = data.decode('utf-8').strip()
            parts = raw.split(',')
            if len(parts) != 3:
                logger.warn("Sensor data format error, expected 3 values: {}".format(raw))
                return

            temp = float(parts[0])
            hr = float(parts[1])
            vel = float(parts[2])

            updates = {}
            if temp >= 0:
                updates["temperature"] = round(temp, 1)
            if hr >= 0:
                updates["heart_rate"] = round(hr, 1)
            if vel >= 0:
                updates["velocity"] = round(vel, 2)

            if updates:
                logger.info("Sensor data: {}".format(updates))
                sys_bus.publish("SENSOR_DATA", updates)

                # MQTT 属性上报（从机主动推送时即时上传）
                if self.thingscloud and self.thingscloud.is_connected:
                    self.thingscloud.set_attributes(updates)
                    self.thingscloud.publish_attributes()
        except Exception as e:
            logger.error("Sensor parse error: {}".format(e))

    def _request_gps_position(self, timeout_ms=3000):
        """主动通过串口请求GPS位置，等待返回新数据"""
        if not self.uart:
            self._gps_lock.acquire()
            lat, lng = self.current_lat, self.current_lng
            self._gps_lock.release()
            return lat, lng

        self._gps_lock.acquire()
        self._gps_updated = False
        self._gps_request_pending = True
        self._gps_request_time = utime.ticks_ms()
        self._gps_lock.release()

        self.uart.uartWrite('g')
        start = utime.ticks_ms()
        while utime.ticks_diff(utime.ticks_ms(), start) < timeout_ms:
            self._gps_lock.acquire()
            updated = self._gps_updated
            lat, lng = self.current_lat, self.current_lng
            self._gps_lock.release()
            if updated:
                return lat, lng
            utime.sleep_ms(50)

        self._gps_lock.acquire()
        lat, lng = self.current_lat, self.current_lng
        self._gps_lock.release()
        return lat, lng

    def _on_gps_for_navigation(self, lng, lat):
        """GPS更新时喂给导航管理器"""
        if not self.nav_manager.is_navigating:
            return
        self.nav_manager.update_position(lng, lat)

    def setvolumeup(self, args):
        volume = self.audio_manager.setvolume_up()
        print("setvolumeup:", volume)

    def setvolumedown(self, args):
        volume = self.audio_manager.setvolume_down()
        print("setvolumedown:", volume)

    def power_down_handle(self):
        logger.info("power down")
        Power.powerDown()

    def on_talk_key_click(self):
        if self.__working_thread is not None and self.__working_thread.is_running():
            return
        self.__working_thread = Thread(target=self.__working_thread_handler)
        self.__working_thread.start()
        self.__keyword_spotting_event.set()

    # ---------- 命令处理函数（供串口调用）----------
    def _cmd_power_down(self, data=None):
        self.power_down_handle()

    def _cmd_start_chat(self, data=None):
        self.on_talk_key_click()

    def _cmd_volume_down(self, data=None):
        self.setvolumedown(None)

    def _cmd_volume_up(self, data=None):
        self.setvolumeup(None)

    # ---------- 导航回调（直接发送 UART + TTS，不再中转 chat 循环）----------
    def _notify_nav_text(self, inject_text):
        """发送导航指令：串口下发 + TTS 播报（非阻塞入队）

        由导航回调直接调用，不依赖 chat 循环。
        服务端 TTS 活跃时跳过本地播报，避免冲突；串口下发不受影响。
        """
        if self.uart:
            self.uart.uartWrite(b't' + inject_text.encode('utf-8'))
        if not self._svr_tts_active:
            self.audio_manager.tts_play(inject_text)
            logger.info("导航语音已播报: {}".format(inject_text[:40]))

    def _on_nav_step_changed(self, step, idx, total):
        logger.info("导航路段切换: step={}/{}, instruction={}".format(idx + 1, total, step.instruction[:40] if step.instruction else ''))
        instruction = step.instruction if step.instruction else ''
        if instruction:
            self._notify_nav_text(instruction)
        # 路段切换时上报一次完整快照（GPS + 导航状态）
        if self.thingscloud and self.thingscloud.is_connected:
            self._gps_lock.acquire()
            lat, lng = self.current_lat, self.current_lng
            self._gps_lock.release()
            if lat is not None and lng is not None:
                self.thingscloud.set_attributes({
                    "longitude": round(lng, 6),
                    "latitude": round(lat, 6),
                })
                self.thingscloud.publish_attributes()

    def _on_nav_off_course(self):
        logger.info("导航偏航警告，触发重新规划")
        self._notify_nav_text('您已偏离导航路线，正在重新规划')
        # 后台基于当前位置重新请求高德路线并覆盖导航
        if not self._replanning:
            Thread(target=self._replan_route_worker).start(stack_size=64)

    def _on_nav_arrived(self):
        logger.info("导航到达终点")
        self._notify_nav_text('您已到达目的地，导航结束')

    def _replan_route_worker(self):
        """偏航后基于当前位置重新请求高德路线并覆盖导航"""
        if not self.nav_manager.is_navigating or not self.nav_manager.route:
            return
        self._replanning = True
        try:
            lat, lng = self._request_gps_position(timeout_ms=3000)
            if lat is None or lng is None:
                return
            origin = "{},{}".format(lng, lat)
            dest = self.nav_manager.route.destination

            route_data = self.amap.get_bicycle_route(origin, dest)
            if not route_data or route_data.get('errcode') != 0:
                logger.warn("偏航重规划：路线请求失败")
                return

            full_route = AmapAPI.parse_bicycle_route(route_data)
            if not full_route:
                logger.warn("偏航重规划：路线解析失败")
                return

            self.nav_manager.start(full_route, current_lng=lng, current_lat=lat)
            # 发送新路线第一步（后续步骤由 on_step_changed 回调驱动）
            first_step = full_route.steps[0] if full_route.steps else None
            if first_step:
                self._on_nav_step_changed(first_step, 0, len(full_route.steps))
            logger.info("偏航重规划完成，共 {} 个路段".format(len(full_route.steps)))
        except Exception as e:
            logger.error("偏航重规划异常: {}".format(e))
        finally:
            self._replanning = False

    # ---------- 导航 MCP 工具处理 ----------
    def _cmd_start_navigation(self, destination):
        """MCP工具: 开始导航，只说目的地，起点从GPS自动获取"""
        lat, lng = self._request_gps_position()
        if lat is None or lng is None:
            return "GPS未就绪，无法获取当前位置"

        origin = "{},{}".format(lng, lat)

        if ',' not in destination:
            addr_info = self.amap.get_addr_coding(destination)
            if 'error' in addr_info:
                return "目的地地址解析失败：" + addr_info['error']
            destination_coord = "{},{}".format(addr_info['longitude'], addr_info['latitude'])
            dest_name = addr_info.get('address', destination)
        else:
            destination_coord = destination
            dest_name = destination

        route_data = self.amap.get_bicycle_route(origin, destination_coord)
        if not route_data or route_data.get('errcode') != 0:
            err_msg = route_data.get('errmsg', '请求失败') if route_data else '请求失败'
            return "导航路线查询失败：{}".format(err_msg)

        route = AmapAPI.parse_bicycle_route(route_data)
        if not route:
            return "导航路线解析失败"

        self.nav_manager.start(route, current_lng=lng, current_lat=lat)

        km = route.total_distance_m / 1000.0
        minutes = route.total_duration_s // 60
        first_step = route.steps[0].instruction if route.steps else ''
        return "导航已开始，目的地{}，全程{:.1f}公里，预计{}分钟。{}".format(
            dest_name, km, minutes, first_step)

    def _cmd_stop_navigation(self):
        """MCP工具: 停止导航"""
        if self.nav_manager.is_navigating:
            self.nav_manager.stop()
            return "导航已停止"
        return "当前没有正在进行的导航"

    def _cmd_get_navigation_status(self):
        """MCP工具: 查询导航状态"""
        status = self.nav_manager.get_status()
        if status["state"] == "idle":
            return "当前没有正在进行的导航"
        if status["state"] == "finished":
            return "导航已完成"
        return "第{}/{}步，{}，剩余{:.0f}公里约{}分钟".format(
            status["step_index"] + 1, status["total_steps"],
            status["instruction"],
            status["total_remaining_m"] / 1000.0,
            status["total_remaining_min"])

    def _start_navigation_worker(self, destination, req_id):
        """后台线程：执行导航启动的耗时操作（GPS请求+API调用），完成后直接回mcp_tools_call"""
        try:
            summary = self._cmd_start_navigation(destination)
        except Exception as e:
            summary = "导航启动异常: {}".format(e)
            logger.error("_start_navigation_worker error: {}".format(e))

        self.__protocol.mcp_tools_call(tool_name="start_navigation", req_id=req_id, args=summary)
        logger.info("导航启动结果已回执: {}".format(summary[:50]))

    # ---------- 串口消息处理入口 ----------
    def _on_uart_message(self, msg_type, data):
        """由 Massage 调用的回调，将消息交给 dispatcher"""
        if self.dispatcher:
            self.dispatcher.dispatch(msg_type, data)
        else:
            logger.warn("Dispatcher not initialized")

    def __record_thread_handler(self):
        """纯粹是为了kws&vad能识别才起的线程持续读音频"""
        logger.debug("record thread handler enter")
        while not self.__record_thread_stop_event.is_set():
            self.audio_manager.opus_read()
            utime.sleep_ms(5)
        logger.debug("record thread handler exit")

    # ---------- MQTT 后台 GPS 定时上报线程 ----------
    def __tc_gps_thread_handler(self):
        """后台线程：GPS 定时请求，导航时每 2 秒，非导航时每 30 秒

        独立于对话流程，只要 UART 就绪就会持续运行。
        与 _request_gps_position（导航启动/偏航重规划时的阻塞式请求）通过
        _gps_request_pending 互斥，同一时刻只有一个 GPS 请求在进行中。

        传感器数据（温度/心率/速度）由从机主动推送（事件上报），无需此线程轮询。
        """
        logger.debug("GPS 后台线程 enter")
        while not self.__tc_gps_stop_event.is_set():
            if self.uart:
                now = utime.ticks_ms()
                should_send = False
                self._gps_lock.acquire()
                pending = self._gps_request_pending
                # 超时保护：超过 2 秒未收到回复则强制清除，防止死锁
                if pending and utime.ticks_diff(now, self._gps_request_time) >= 2000:
                    self._gps_request_pending = False
                    pending = False
                if not pending:
                    # 根据导航状态动态切换轮询间隔
                    interval = self._nav_gps_interval if self.nav_manager.is_navigating else self._tc_gps_interval
                    if utime.ticks_diff(now, self._last_bg_gps_request) >= interval:
                        self._gps_request_pending = True
                        self._gps_request_time = now
                        self._last_bg_gps_request = now
                        should_send = True
                self._gps_lock.release()
                if should_send:
                    self.uart.uartWrite('g')
            utime.sleep_ms(100)
        logger.debug("GPS 后台线程 exit")

    def _start_tc_gps_thread(self):
        """启动 MQTT 后台 GPS 定时上报线程"""
        if self.__tc_gps_thread is not None:
            return
        self.__tc_gps_stop_event.clear()
        self.__tc_gps_thread = Thread(target=self.__tc_gps_thread_handler)
        self.__tc_gps_thread.start(stack_size=64)
        logger.info("GPS 后台线程已启动，间隔 {} 秒".format(self._tc_gps_interval // 1000))

    def _stop_tc_gps_thread(self):
        """停止 MQTT 后台 GPS 定时上报线程"""
        if self.__tc_gps_thread is None:
            return
        self.__tc_gps_stop_event.set()
        self.__tc_gps_thread.join()
        self.__tc_gps_thread = None
        logger.info("GPS 后台线程已停止")

    def on_led(self):
        self.wifi_green_led.on()
        self.lte_green_led.on()
        self.power_green_led.on()
        
    def off_led(self):
        self.wifi_green_led.off()
        self.lte_green_led.off()
        self.power_green_led.off()
        
    def start_kws(self):
        self.audio_manager.start_kws()
        self.__record_thread_stop_event.clear()
        self.__record_thread = Thread(target=self.__record_thread_handler)
        self.__record_thread.start(stack_size=64)
        
    def setvolumeup(self,args):
        volume=self.audio_manager.setvolume_up()
        print("setvolumeup:", volume)
    def setvolumedown(self,args):
        volume=self.audio_manager.setvolume_down()
        print("setvolumedown:", volume)

    def power_down_handle(self):
        logger.info("power down")
        self._stop_tc_gps_thread()
        Power.powerDown()


    def stop_kws(self):
        self.__record_thread_stop_event.set()
        self.__record_thread.join()
        # self.audio_manager.stop_kws()
        
    def start_vad(self):
        self.audio_manager.start_vad()
    
    def stop_vad(self):
        self.audio_manager.stop_vad()

    def __working_thread_handler(self):
        t = Thread(target=self.__chat_process)
        t.start(stack_size=64)
        self.__keyword_spotting_event.wait()
        self.stop_kws()
        t.join()
        # self.start_kws()

    def __chat_process(self):
        global name
        self.__protocol.connect_flag = True
        self.power_green_led.on()
        self.start_vad()
        try:
            with self.__protocol:
                self.__protocol.hello()
                self.__protocol.wakeword_detected(name)
                is_listen_flag = False
                buffer = []  # 用于缓存最近5帧
                while True:
                    data = self.audio_manager.opus_read()
                    buffer.append(data)
                    if len(buffer) > 7:
                        buffer.pop(0)
                    if self.__voice_activity_event.is_set():
                        # 有人声
                        if not is_listen_flag:
                            self.__protocol.abort()
                            self.__protocol.listen("start")
                            is_listen_flag = True
                            for frame in buffer[:6]:  # 发送缓存的前6帧
                                self.__protocol.send(frame)
                        self.__protocol.send(data)
                        # logger.debug("send opus data to server")
                    else:
                        if is_listen_flag:
                            self.__protocol.listen("stop")
                            is_listen_flag = False
                    if not self.__protocol.is_state_ok or self.__protocol.connect_flag == False:
                        print("连接断开，退出聊天流程",self.__protocol.connect_flag)
                        break
                    utime.sleep_ms(5)
                    # logger.debug("read opus data length: {}".format(len(data)))
        except Exception as e:
            logger.error("working thread handler got Exception: {}".format(repr(e)))
        finally:
            print("__chat_process exit")
            self.lte_green_led.off()
            self.wifi_green_led.off()
            self.power_green_led.blink(500, 500)
            self.__working_thread = None
            self.stop_vad()
            self.start_kws()

    def on_talk_key_click(self):
        # logger.info("on_talk_key_click: ", args)
        if self.__working_thread is not None and self.__working_thread.is_running():
            return
        self.__working_thread = Thread(target=self.__working_thread_handler)
        self.__working_thread.start()
        self.__keyword_spotting_event.set()
        
    def on_keyword_spotting(self, state):
        logger.info("on_keyword_spotting: {}".format(state))
        if state[0] == 0:
            if state[1] != 0:
                # 唤醒词触发
                if self.__working_thread is not None and self.__working_thread.is_running():
                    return
                self.__working_thread = Thread(target=self.__working_thread_handler)
                self.__working_thread.start()
                self.__keyword_spotting_event.set()
            else:
                self.__keyword_spotting_event.clear()
            
    def on_voice_activity_detection(self, state):
        logger.info("on_voice_activity_detection: {}".format(state))
        if state == 1:
            self.__voice_activity_event.set()  # 有人声
            self.lte_green_led.on()
        else:
            self.__voice_activity_event.clear()  # 无人声
            self.lte_green_led.off()

    def on_audio_message(self, raw):
        # raise NotImplementedError("on_audio_message not implemented")
        self.audio_manager.opus_write(raw)

    def on_json_message(self, msg):
        return getattr(self, "handle_{}_message".format(msg["type"]))(msg)

    def handle_stt_message(data, msg):
        # pass
        raise NotImplementedError("handle_stt_message not implemented")

    def handle_tts_message(self, msg):
        state = msg["state"]
        if state == "start":
            self.wifi_green_led.blink(250, 250)
            self._svr_tts_active = True
        elif state == "stop":
            self.wifi_green_led.off()
            self._svr_tts_active = False
            self._svr_tts_stop_time = utime.ticks_ms()

#"happy" "cool"  "angry"  "think"
# ... existing code ...
    def handle_llm_message(data, msg):
        raise NotImplementedError("handle_llm_message not implemented")
    
    def handle_mcp_message(self, msg):
        print("msg: ", msg)
        data = msg.to_bytes()
        data_dict = json.loads(data)
        id = 1
        method = data_dict['payload']['method']
        if 'id' in data_dict['payload']:
            id = data_dict['payload']['id']
        print("MCP请求: ", method)
        
        if method == "initialize":
            self.__protocol.mcp_initialize()
        elif method == "tools/list":
            self.__protocol.mcp_tools_list()
        elif method == "tools/call":
            handle = data_dict['payload']['params']['name']
            
            if handle == "self.setvolume_down()":     
                print("当前音量大小", self.audio_manager.setvolume_down())
            elif handle == "self.setvolume_up()":
                print("当前音量大小", self.audio_manager.setvolume_up())
            elif handle == "self.setvolume_close()":
                print("当前音量大小", self.audio_manager.setvolume_close())
            elif handle == "self.setvolume()":
                arguments = data_dict['payload']["params"]["arguments"]["volume"]
                print("当前音量大小", arguments, self.audio_manager.setvolume(arguments))
            elif handle == "self.new_name()":
                arguments = data_dict['payload']["params"]["arguments"]["name"]
                print("name:", self.audio_manager.new_name(arguments))
            elif handle == "get_bicycle_route":
                # HTTP 请求甩到后台线程，避免阻塞 WebSocket 接收线程
                origin_raw = data_dict['payload']["params"]["arguments"]["origin"]
                destination_raw = data_dict['payload']["params"]["arguments"]["destination"]
                def bicycle_route_worker():
                    try:
                        origin = origin_raw if ',' in origin_raw else (
                            lambda a: "{},{}".format(a['longitude'], a['latitude']) if 'error' not in a else None
                        )(self.amap.get_addr_coding(origin_raw))
                        if origin is None:
                            self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args="起点地址解析失败")
                            return
                        destination = destination_raw if ',' in destination_raw else (
                            lambda a: "{},{}".format(a['longitude'], a['latitude']) if 'error' not in a else None
                        )(self.amap.get_addr_coding(destination_raw))
                        if destination is None:
                            self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args="终点地址解析失败")
                            return
                        route_data = self.amap.get_bicycle_route(origin, destination)
                        summary = "骑行路线查询失败"
                        if route_data and route_data.get('errcode') == 0:
                            paths = route_data.get('data', {}).get('paths', [])
                            if paths:
                                p = paths[0]
                                km = p.get('distance', 0) / 1000.0
                                minutes = p.get('duration', 0) // 60
                                first = p['steps'][0].get('instruction', '') if p.get('steps') else ''
                                summary = "总路程{:.1f}公里，预计{}分钟。{}".format(km, minutes, first)
                                def full_parse_worker():
                                    try:
                                        r = AmapAPI.parse_bicycle_route(route_data)
                                        if r:
                                            sys_bus.publish("ROUTE_FULL", r)
                                        else:
                                            logger.error("骑行路线解析失败，parse_bicycle_route 返回 None")
                                    except Exception as e:
                                        logger.error("后台解析异常: {}".format(e))
                                Thread(target=full_parse_worker).start(stack_size=64)
                            else:
                                summary = "骑行路线查询失败：无有效路径"
                        self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args=summary)
                    except Exception as e:
                        logger.error("bicycle_route_worker 异常: {}".format(e))
                Thread(target=bicycle_route_worker).start(stack_size=64)
                return

            elif handle == "start_navigation":
                destination = data_dict['payload']["params"]["arguments"]["destination"]
                def start_nav_worker():
                    try:
                        lat, lng = self._request_gps_position(timeout_ms=1500)
                        if lat is None or lng is None:
                            self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args="GPS未就绪")
                            return
                        origin = "{},{}".format(lng, lat)
                        dest_name = destination
                        if ',' not in destination:
                            addr_info = self.amap.get_addr_coding(destination)
                            if 'error' in addr_info:
                                self.__protocol.mcp_tools_call(tool_name=handle, req_id=id,
                                    args="目的地地址解析失败：" + addr_info['error'])
                                return
                            destination_coord = "{},{}".format(addr_info['longitude'], addr_info['latitude'])
                            dest_name = addr_info.get('address', destination)
                        else:
                            destination_coord = destination
                        route_data = self.amap.get_bicycle_route(origin, destination_coord)
                        summary = "导航路线查询失败"
                        if route_data and route_data.get('errcode') == 0:
                            paths = route_data.get('data', {}).get('paths', [])
                            if paths:
                                p = paths[0]
                                km = p.get('distance', 0) / 1000.0
                                minutes = p.get('duration', 0) // 60
                                first = p['steps'][0].get('instruction', '') if p.get('steps') else ''
                                summary = "导航已开始，目的地{}，全程{:.1f}公里，预计{}分钟。{}".format(
                                    dest_name, km, minutes, first)
                                def full_parse_and_start_worker():
                                    try:
                                        r = AmapAPI.parse_bicycle_route(route_data)
                                        if r:
                                            self.nav_manager.start(r, current_lng=lng, current_lat=lat)
                                        else:
                                            logger.error("导航路线解析失败，parse_bicycle_route 返回 None")
                                            self._notify_nav_text("导航启动失败，路线解析错误")
                                    except Exception as e:
                                        logger.error("后台解析异常: {}".format(e))
                                        self._notify_nav_text("导航启动失败")
                                Thread(target=full_parse_and_start_worker).start(stack_size=64)
                            else:
                                summary = "导航路线查询失败：无有效路径"
                        self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args=summary)
                    except Exception as e:
                        logger.error("start_nav_worker 异常: {}".format(e))
                Thread(target=start_nav_worker).start(stack_size=64)
                return

            elif handle == "stop_navigation":
                summary = self._cmd_stop_navigation()
                self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args=summary)
                return

            elif handle == "get_navigation_status":
                summary = self._cmd_get_navigation_status()
                self.__protocol.mcp_tools_call(tool_name=handle, req_id=id, args=summary)
                return

            self.__protocol.mcp_tools_call(tool_name=handle, req_id=id)
            # raise NotImplementedError("handle_mcp_message not implemented")
        
    def handle_iot_message(data, msg):
        pass
        # raise NotImplementedError("handle_iot_message not implemented")
    
    def handle_error_message(data, msg):
        pass
        # raise NotImplementedError("handle_error_message not implemented")

    def run(self):
        global enable_flag
        self.charge_manager.disable_charge()
        self.audio_manager.open_opus()
        self.volumedown.enable()
        self.volumeup.enable()
        self.power_green_led.blink(500, 500)

        self.dispatcher = CommandDispatcher()
        # 注册按键命令 b1~b4
        self.dispatcher.register('b', self._cmd_power_down, cmd_id='1')
        self.dispatcher.register('b', self._cmd_start_chat,  cmd_id='2')
        self.dispatcher.register('b', self._cmd_volume_down, cmd_id='3')
        self.dispatcher.register('b', self._cmd_volume_up,   cmd_id='4')

        # 注册 GPS 默认处理器
        self.dispatcher.register('g', self._gps_default_handler)

        # 注册传感器数据处理器（s 报文: 温度,心率,速度）
        self.dispatcher.register('s', self._sensor_handler)

        self.uart = Massage()
        self.uart.set_message_handler(self._on_uart_message)

        # ---------- 自建 MQTT 服务器连接 ----------
        # frp 内网穿透公网端点
        MQTT_SERVER_HOST = "frp-run.com"
        MQTT_SERVER_PORT = 18830
        MQTT_DEVICE_ID = "helmet_001"
        MQTT_DEVICE_KEY = "helmet_key_001"   # 设备密钥，需与服务器 config.py 中一致

        try:
            self.thingscloud = ThingsCloudMQTT(
                endpoint=MQTT_SERVER_HOST,
                port=MQTT_SERVER_PORT,
                username=MQTT_DEVICE_ID,
                password=MQTT_DEVICE_KEY,
                client_id=MQTT_DEVICE_ID,
                keepalive=30  # 穿透场景：30s PINGREQ 保持隧道活跃
            )
            # 注册属性元信息（本地记录，供数据处理管道校验参考）
            self.thingscloud.register_attribute("temperature", unit="°C", min_val=-40, max_val=100, precision=0.1)
            self.thingscloud.register_attribute("heart_rate", unit="BPM", min_val=0, max_val=300, precision=1)
            self.thingscloud.register_attribute("longitude", unit="°", min_val=-180, max_val=180, precision=0.000001)
            self.thingscloud.register_attribute("latitude", unit="°", min_val=-90, max_val=90, precision=0.000001)
            self.thingscloud.register_attribute("velocity", unit="m/s", min_val=0, max_val=100, precision=0.01)

            if self.thingscloud.connect() == 0:
                logger.info("MQTT 服务器已连接: {}:{}".format(MQTT_SERVER_HOST, MQTT_SERVER_PORT))
                self.thingscloud.publish_event("device_online", {"version": "1.0.0", "mode": "helmet"})
            else:
                logger.warn("MQTT 服务器连接失败，跳过云平台上报")
        except Exception as e:
            logger.error("MQTT 初始化异常: {}".format(e))

        # 启动 MQTT 后台 GPS 定时上报线程（独立于对话/导航）
        self._start_tc_gps_thread()

        self.wakeup_key = Button(27, delay=3000, long_press_callback=self.power_down_handle, short_press_callback= self.on_talk_key_click)
        enable_flag = 1
        self.start_kws()
        
    


def usb_callback(conn_status):
    status = conn_status
    if not enable_flag:
        if status == 0:
            app.off_led()
            Power.powerDown()
            # enable_flag=1
            print('USB is disconnected.')
        elif status == 1:
            app.on_led()
            # enable_flag=0
            
            print('USB is connected.')
     
def power_open_handle():
    if enable_flag: 
        app.off_led()
        app.run()  
        print("power_open_handle")
            


if __name__ == "__main__":    
    usb = USB()
    app = Application()
    usb.setCallback(usb_callback)
    # 检查 USB 连接状态
    if usb.getStatus():  # 假设 getStatus() 返回 True 表示 USB 已连接
        app.on_led()
        print("USB 已连接，仅启用充电业务")
        app.charge_manager.enable_charge()  # 只启用充电业务
        # Button(41, delay=3000, long_press_callback=power_open_handle, short_press_callback= None)

        print("USB 未连接，启动主业务")
        app.run()