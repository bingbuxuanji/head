import sim
import net
import Opus
import audio
import utime
import dataCall
import checkNet
import sys_bus
from machine import Pin,UART
from machine import ExtInt
import osTimer
from usr.threading import PriorityQueue, Queue, Thread
from usr.logging import getLogger
from misc import PowerKey, Power



logger = getLogger(__name__)
volume = 7
name = '_xiao_yuan_xiao_yuan'
# ==================== 音频管理 ====================


class AudioManager(object):

    def __init__(self, channel=0, volume=7, pa_number=33):
        self.aud = audio.Audio(channel)  # 初始化音频播放通道
        self.aud.set_pa(pa_number)
        self.aud.setVolume(volume)  # 设置音量
        self.aud.setCallback(self.audio_cb)
        self.rec = audio.Record(channel)
        self.rec.gain_set(3,9)
        self.__skip = 0
        self._audio_busy = False
        try:
            self.tts = audio.TTS(0)  # EC800M: 0=听筒
            self.tts.setCallback(self._tts_cb)
        except Exception as e:
            self.tts = None
            print("TTS init failed:", e)

        # TTS 队列管理：回调驱动消费，非阻塞，不额外开线程
        self._tts_queue = Queue(max_size=16)
        self._tts_active = False

    def tts_play(self, text):
        """本地TTS朗读：入队列；若当前空闲则立即开始播放"""
        if self.tts is None:
            return -1
        self._tts_queue.put(text)
        if not self._tts_active:
            self._tts_start_next()
        return 0

    def tts_stop(self):
        """停止当前 TTS 并清空待播队列"""
        if self.tts is None:
            return -1
        while True:
            try:
                self._tts_queue.get(block=False)
            except Queue.Empty:
                break
        self.tts.stop()
        self._tts_active = False
        return 0

    def _tts_start_next(self):
        """从队列取一条文字开始播放；队列空则恢复 opus"""
        try:
            text = self._tts_queue.get(block=False)
        except Queue.Empty:
            self.open_opus()
            return
        self._tts_active = True
        self.close_opus()
        self.aud.stopAll()
        self.tts.play(4, 1, 2, text)

    def _tts_cb(self, event):
        if event == 4:                 # TTS 播放完成，驱动下一条
            self._tts_active = False
            self._tts_start_next()

    @property
    def audio_busy(self):
        return self._audio_busy
        
    def setvolume_down(self):
        global volume
        volume -= 1
        if volume < 0: volume = 0
        self.aud.setVolume(volume)
        return volume
        
    def setvolume_up(self):
        global volume
        volume += 1
        if volume > 11: volume = 11
        self.aud.setVolume(volume)
        return volume
    
    def setvolume_close(self):
        global volume
        self.aud.setVolume(0)
        volume = 0
        return volume
    
    def setvolume(self,data):
        global volume
        self.aud.setVolume(data)
        volume = data
        return volume

    # ========== 音频文件 ====================

    def audio_cb(self, event):
        if event == 0:
            self._audio_busy = True
        elif event == 7:
            self._audio_busy = False
        else:
            pass

    def play(self, file):
        self.aud.play(0, 1, file)

    def stop(self):
        self.aud.stopAll()

    # ========= opus ====================

    def open_opus(self):
        self.close_opus()  # 先关再开，防重复
        try:
            self.pcm = audio.Audio.PCM(0, 1, 16000, 2, 1, 15)
            self.opus = Opus(self.pcm, 0, 60000)
        except Exception:
            # TTS 刚结束时 PCM 资源可能未完全释放，静默失败，
            # 下次 _tts_start_next / opus_read 会兜底返回零
            pass

    def close_opus(self):
        if hasattr(self, 'opus'):
            try:
                self.opus.close()
            except Exception:
                pass
            del self.opus
        if hasattr(self, 'pcm'):
            try:
                self.pcm.close()
            except Exception:
                pass
            del self.pcm

    def opus_read(self):
        if not hasattr(self, 'opus'):
            return b'\x00' * 60
        try:
            return self.opus.read(60)
        except Exception:
            return b'\x00' * 60

    def opus_write(self, data):
        if not hasattr(self, 'opus'):
            return -1
        try:
            return self.opus.write(data)
        except Exception:
            return -1

    # ========= vad & kws ====================

    def set_kws_cb(self, cb):
        self.rec.ovkws_set_callback(cb)
            
    def set_vad_cb(self, cb):
        def wrapper(state):
            if self.__skip != 2:
                self.__skip += 1
                return
            return cb(state)
        self._callable = wrapper
        self.rec.vad_set_callback(self._callable)

    def end_cb(self, para):
        if(para[0] == "stream"):
            if(para[2] == 1):
                pass
            elif (para[2] == 3):
                pass
            else:
                pass
        else:
            pass
    def new_name(self,data):
        global name
        name=data
        # print("当前唤醒词：", name)
        return name
    def start_kws(self):
        list=["_xiao_tian_xiao_tian",name,"_jiang_gou_jiang_gou"]
        self.rec.ovkws_start(list, 0.7)


    def stop_kws(self):
        self.rec.ovkws_stop()
    
    def start_vad(self):
        self.__skip = 0
        self.rec.vad_start()

    def stop_vad(self):
        self.rec.vad_stop()


# ==================== 充电管理 ====================


class ChargeManager(object):

    def __init__(self, GPIOn=3):
        self.charge_pin = Pin(getattr(Pin, "GPIO{}".format(GPIOn)), Pin.OUT, Pin.PULL_PU)
    
    def enable_charge(self):
        self.charge_pin.write(1)
    
    def disable_charge(self):
        self.charge_pin.write(0)


# ==================== 网络管理 ====================


class NetManager(object):
    
    def __init__(self):
        # 注册网络回调
        dataCall.setCallback(self.__net_callback)

    def __net_callback(self, args):
        if args[1] == 0:
            sys_bus.publish("NET_STATE_CHANGE", dict(state="net_disconnect"))
            Thread(target=self.wait_network_ready).start()
        else:
            sys_bus.publish("NET_STATE_CHANGE", dict(state="net_connected"))

    @staticmethod
    def make_cfun():
        net.setModemFun(0, 0)
        utime.sleep_ms(200)
        net.setModemFun(1, 0)

    def wait_network_ready(self):
        while True:
            if sim.getStatus() != 1:
                logger.debug('no sim card.')
                sys_bus.publish("NET_STATE_CHANGE", dict(state="no_sim_card"))
            else:
                logger.debug('sim card ready.')
                sys_bus.publish("NET_STATE_CHANGE", dict(state="net_connecting"))
            code = checkNet.waitNetworkReady(10)
            if code == (3, 1):
                logger.info('network ready.')
                break
            else:
                if net.csqQueryPoll() < 18:
                    sys_bus.publish("NET_STATE_CHANGE", dict(state="no_signal"))
                logger.debug('make cfun.')
                self.make_cfun()


# ==================== 任务调度 ====================


class _Task(object):

    def __init__(self, target, args=(), kwargs={}, priority=0, sync=True, title="anon"):
        self.__target = target
        self.args = args
        self.kwargs = kwargs
        self.priority = priority
        self.sync = sync
        self.title = title
    
    def __str__(self):
        return "<Task: {}>".format(self.title)
        
    def __lt__(self, other):
        # 小顶堆优先级排序
        return self.priority < other.priority
    
    def __gt__(self, other):
        return self.priority > other.priority
    
    def __eq__(self, other):
        return self.priority == other.priority
        
    def run(self):
        if self.sync:
            self.__target(*self.args, **self.kwargs)
        else:
            Thread(target=self.__target, args=self.args, kwargs=self.kwargs).start()


class TaskManager(object):

    def __init__(self):
        self.__q = PriorityQueue()
        self.__main_thread = Thread(target=self.__main_loop)
        
    def __main_loop(self):
        while True:
            task = self.__q.get()
            try:
                task.run()
            except Exception as e:
                logger.error("{} run failed, Exception details: {}".format(task, repr(e)))
            else:
                pass
    
    def run_forever(self):
        logger.info('task manager run forever.')
        self.__main_thread.start()

    def submit(self, func, args=(), kwargs={}, priority=0, title="anon"):
        self.__q.put(_Task(target=func, args=args, kwargs=kwargs, priority=priority, title=title))
        
       
       



class Button(object):

    def __init__(self, gpio_number, delay=3000, long_press_callback=lambda: None, short_press_callback=lambda: None):
        self.key = ExtInt(getattr(ExtInt, "GPIO{}".format(gpio_number)), ExtInt.IRQ_RISING_FALLING, ExtInt.PULL_PU, self.__callback, 150)
        self.key.enable()
        self.delay = delay
        self.timer = osTimer()
        self.start_time = None
        self.end_time = None
        self.long_press_callback = long_press_callback
        self.short_press_callback = short_press_callback
        self.is_pressed = False  # 状态变量：按键是否被按下
        
        
    def __callback(self, args):
        gpio_number, mode = args
        if not self.is_pressed:
            # 下降沿，按下
            print("按键按下")
            self.is_pressed = True
            self.start_time = utime.ticks_ms()
            self.timer.start(self.delay, 0, lambda args: self.long_press_callback())
        elif self.is_pressed:
            # 上升沿，释放
            print("按键释放")
            self.is_pressed = False
            self.timer.stop()
            self.end_time = utime.ticks_ms()
            duration = utime.ticks_diff(self.end_time, self.start_time)
            if duration < self.delay:
                self.short_press_callback()


class Massage(object):
    def __init__(self, no=UART.UART2, bate=115200, data_bits=8, parity=0, stop_bits=1, flow_control=0):
        self.uart = UART(no, bate, data_bits, parity, stop_bits, flow_control)
        self.uart.set_callback(self.callback)
        self.message_handler = None   # 外部注册的处理器，签名为 handler(msg_type, data)
        self._tick_cb = None          # UART 数据接收心跳回调

        # ---------- TX 队列：消除多线程写 UART 的竞争 ----------
        self.__tx_queue = Queue(max_size=64)
        self.__tx_thread = Thread(target=self.__tx_thread_worker)
        self.__tx_thread.start()

    def set_message_handler(self, handler):
        """注册全局消息处理器，接收 (msg_type, data_bytes) 参数"""
        self.message_handler = handler

    def callback(self, para):
        if para[0] == 0:
            self.uartRead(para[2])

    def uartWrite(self, msg):
        """线程安全的 UART 写：将整条消息放入发送队列，由 TX 线程取出写入硬件"""
        self.__tx_queue.put(msg)

    def __tx_thread_worker(self):
        """独立 TX 线程：串行化所有写请求，避免多线程竞争 UART 硬件"""
        while True:
            msg = self.__tx_queue.get()
            try:
                # 统一转为 bytes，兼容外部传入的 str/bytes
                if isinstance(msg, str):
                    msg = msg.encode('utf-8')
                self.uart.write(msg)
            except Exception as e:
                print("TX thread error: {}".format(e))

    def set_tick_callback(self, cb):
        """注册心跳回调：每次收到 UART 数据时调用，用于保持时间发送等"""
        self._tick_cb = cb

    def uartRead(self, length):
        msg = self.uart.read(length)
        if not msg or len(msg) < 1:
            return
        # 心跳回调：每次收到数据都触发，不受线程阻塞影响
        if self._tick_cb:
            try:
                self._tick_cb()
            except Exception:
                pass
        # 按行切分，处理缓冲区中可能粘包的多条消息
        # 从机 printf 以 \r\n 结尾，统一替换为 \n 后拆分
        msg = msg.replace(b'\r\n', b'\n')
        lines = msg.split(b'\n')
        for raw in lines:
            raw = raw.strip()
            if not raw or len(raw) < 2:
                continue
            msg_type = chr(raw[0])          # 第一个字节：'b', 'g', 's', 'm', 't'...
            data = raw[1:]                  # 剩余字节
            if self.message_handler:
                self.message_handler(msg_type, data)

class CommandDispatcher(object):
    def __init__(self):
        # 结构: { msg_type: { cmd_id: callback, None: default_callback } }
        self._handlers = {}

    def register(self, msg_type, callback, cmd_id=None):
        """注册一个消息处理器
        :param msg_type: 消息类型，如 'b'（按键）、'g'(GPS)
        :param callback: 回调函数，签名为 callback(data)   data 为 bytes
        :param cmd_id:   可选，命令标识，如 '1','2'；若不提供则注册为默认处理器
        """
        if msg_type not in self._handlers:
            self._handlers[msg_type] = {}
        if cmd_id is None:
            # 默认处理器
            self._handlers[msg_type][None] = callback
        else:
            self._handlers[msg_type][cmd_id] = callback

    def dispatch(self, msg_type, data):
        """分发消息，data 为 bytes 类型（已去掉第一个字节的消息类型标识）"""
        if msg_type not in self._handlers:
            logger.debug("Unknown message type: {}".format(msg_type))
            return

        handlers = self._handlers[msg_type]
        callback = None

        # 根据消息类型决定如何获取命令 ID
        if msg_type == 'b':
            # 按键消息：第一个字节是命令 ID（如 b'1'）
            if len(data) == 0:
                logger.warn("Empty data for button message")
                return
            cmd_id = chr(data[0])   # 例如 b'1' -> '1'
            # 优先查找特定命令 ID 的处理器
            if cmd_id in handlers:
                callback = handlers[cmd_id]
            elif None in handlers:
                callback = handlers[None]   # 若没有特定处理器，尝试默认处理器
        else:
            # 其他消息（如 GPS）：不解析命令 ID，直接使用默认处理器
            if None in handlers:
                callback = handlers[None]
            else:
                logger.warn("No default handler for msg_type: {}".format(msg_type))
                return

        if callback:
            try:
                callback(data)
            except Exception as e:
                logger.error("Handler error for {}: {}".format(msg_type, e))
        else:
            logger.warn("No handler found for {} cmd_id={}".format(msg_type, cmd_id if msg_type=='b' else 'default'))
