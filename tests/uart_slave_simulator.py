# -*- coding: UTF-8 -*-
"""
UART 下位机模拟器 —— PC 端测试脚本

模拟从机 MCU 的串口行为，用于在 PC 上调试 EC800 模组的串口通信协议。

协议约定（与模组通信）：
  g           → GPS 请求（模组→从机），从机应答 g<lat>,<lng>
  b<cmd_id>   → 按键事件（从机→模组），cmd_id: 1=关机 2=对话 3=音量- 4=音量+
  t<text>     → 导航文字（模组→从机），从机显示在屏幕上
  s<temp>,<hr>,<vel> → 传感器数据（从机→模组），温度(°C),心率(BPM),速度(m/s)

启动方式：
  python uart_slave_simulator.py COM3          # Windows
  python uart_slave_simulator.py /dev/ttyUSB0  # Linux

依赖：pyserial
  pip install pyserial

交互命令（运行时键盘输入）：
  Enter       发送一条空行查看帮助
  1/2/3/4     发送按键事件 b1~b4
  g           手动发送一次模拟 GPS 坐标（不等待请求，直接推送）
  m           手动发送一次传感器数据 (温度/心率/速度, 随机值)
  d           开始/停止自动传感器上报 (每 5 秒)
  l<lat>,<lng> 设置当前位置
  q           退出

Author: test tools
"""

import sys
import time
import random
import threading
import signal

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("请先安装 pyserial: pip install pyserial")
    sys.exit(1)


# ============================================================================
# GPS 轨迹（郫都区团结 → 金牛区 → 青羊区天府广场）
# ============================================================================
DEFAULT_GPS_ROUTE = [
    (30.818529, 103.985887),  # 起点 郫都区团结镇
    (30.817000, 103.986500),
    (30.815100, 103.986900),
    (30.813500, 103.987200),
    (30.811800, 103.988800),
    (30.809500, 103.990100),
    (30.808000, 103.991500),
    (30.806200, 103.994000),  # 蜀源大道
    (30.803800, 103.997000),
    (30.800800, 103.999800),
    (30.797500, 104.002000),
    (30.794000, 104.003800),
    (30.790000, 104.005000),  # 交大路
    (30.786000, 104.006500),
    (30.782000, 104.008500),
    (30.778000, 104.010500),
    (30.774000, 104.013000),
    (30.769500, 104.015500),  # 沙湾路
    (30.765000, 104.018500),
    (30.760500, 104.021500),
    (30.756000, 104.025000),
    (30.751500, 104.028000),
    (30.747000, 104.031000),
    (30.742500, 104.034000),
    (30.738000, 104.037000),
    (30.733500, 104.039500),
    (30.729000, 104.042500),
    (30.724500, 104.045500),
    (30.720000, 104.048500),
    (30.715000, 104.051000),
    (30.710000, 104.053500),
    (30.705500, 104.056000),
    (30.701000, 104.058500),
    (30.697000, 104.060500),
    (30.693000, 104.062500),
    (30.689000, 104.064000),
    (30.684000, 104.065000),
    (30.680000, 104.065800),
    (30.675000, 104.066000),
    (30.670000, 104.065900),
    (30.665500, 104.065800),
    (30.661000, 104.065800),
    (30.657401, 104.065861),  # 终点 天府广场
]


# ============================================================================
# ANSI 颜色（终端显示）
# ============================================================================
class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


# ============================================================================
# UART 下位机模拟器
# ============================================================================
class UartSlaveSimulator:
    """模拟从机 MCU 的串口行为"""

    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None

        # GPS 模拟（只在收到上位机 g 请求时应答，不主动推送）
        self.current_lat = DEFAULT_GPS_ROUTE[0][0]
        self.current_lng = DEFAULT_GPS_ROUTE[0][1]
        self.route = DEFAULT_GPS_ROUTE
        self.route_index = 0
        self._last_gps_response_time = 0          # 上次应答时间戳
        self._gps_response_interval = 5.0          # GPS 应答最小间隔（秒）

        # 传感器模拟（默认开启，定时上报温度/心率/速度）
        self.auto_sensor_enabled = True
        self.sensor_thread = None
        self.sensor_stop_event = threading.Event()

        # 统计
        self.rx_count = 0
        self.tx_count = 0

    # ---------- 串口 ----------
    def connect(self):
        """打开串口"""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1,
            )
            print(f"{Color.GREEN}串口 {self.port} 已打开 (baud={self.baudrate}){Color.RESET}")
            return True
        except serial.SerialException as e:
            print(f"{Color.RED}串口打开失败: {e}{Color.RESET}")
            return False

    def disconnect(self):
        """关闭串口"""
        self.stop_auto_sensor()
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"{Color.YELLOW}串口 {self.port} 已关闭{Color.RESET}")

    # ---------- GPS 模拟 ----------
    def _advance_route(self):
        """沿预设轨迹前进一个点，到达终点后停止"""
        if self.route_index < len(self.route) - 1:
            self.route_index += 1
            self.current_lat, self.current_lng = self.route[self.route_index]

    def send_gps_response(self):
        """发送当前 GPS 坐标（不推进轨迹，由调用方决定是否推进）"""
        gps_str = f"g{self.current_lat:.6f},{self.current_lng:.6f}"
        self._send_raw(gps_str.encode('utf-8'))
        print(f"  {Color.CYAN}[GPS] → {gps_str}{Color.RESET}")

    # ---------- 传感器模拟 ----------
    @staticmethod
    def _gen_sensor_data():
        """随机生成传感器数据，返回 (temperature, heart_rate, velocity)"""
        temp = round(random.uniform(36.1, 36.9), 1)       # 体温 36.1~36.9 °C
        hr = random.randint(65, 95)                        # 心率 65~95 BPM
        vel = round(random.uniform(0.5, 12.0), 1)          # 骑行速度 0.5~12.0 m/s
        return temp, hr, vel

    def send_sensor(self):
        """手动发送一次传感器数据（随机值）"""
        temp, hr, vel = self._gen_sensor_data()
        self._send_sensor_raw(temp, hr, vel)

    def send_alert(self, alert_type=0):
        """发送告警传感器数据
        alert_type: 1=体温告警  2=心率告警  3=双重告警  0=随机告警
        """
        if alert_type == 0:
            alert_type = random.randint(1, 3)
        if alert_type == 1:
            temp, hr = round(random.uniform(38.5, 41.0), 1), random.randint(70, 100)
            tag = "体温告警"
        elif alert_type == 2:
            temp, hr = round(random.uniform(36.1, 37.2), 1), random.randint(160, 200)
            tag = "心率告警"
        else:
            temp, hr = round(random.uniform(38.5, 41.0), 1), random.randint(160, 200)
            tag = "双重告警"
        vel = round(random.uniform(0.5, 12.0), 1)
        self._send_sensor_raw(temp, hr, vel)
        print(f"  {Color.RED}[ALERT {tag}] → s{temp},{hr},{vel}{Color.RESET}")

    def _send_sensor_raw(self, temp, hr, vel):
        data = f"s{temp},{hr},{vel}".encode('utf-8')
        self._send_raw(data)

    def _sensor_auto_worker(self):
        """后台线程：每隔 5 秒上报一次随机传感器数据"""
        while not self.sensor_stop_event.is_set():
            temp, hr, vel = self._gen_sensor_data()
            data = f"s{temp},{hr},{vel}".encode('utf-8')
            self._send_raw(data)
            print(f"  {Color.CYAN}[SENSOR] → s{temp},{hr},{vel}{Color.RESET}")
            self.sensor_stop_event.wait(timeout=5.0)

    def start_auto_sensor(self):
        """开始自动上报传感器数据"""
        if self.auto_sensor_enabled:
            return
        self.auto_sensor_enabled = True
        self.sensor_stop_event.clear()
        self.sensor_thread = threading.Thread(target=self._sensor_auto_worker, daemon=True)
        self.sensor_thread.start()
        print(f"{Color.GREEN}[SENSOR] 自动上报已启动 (间隔 5s, 随机值){Color.RESET}")

    def stop_auto_sensor(self):
        """停止自动上报传感器数据"""
        if not self.auto_sensor_enabled:
            return
        self.auto_sensor_enabled = False
        self.sensor_stop_event.set()
        if self.sensor_thread:
            self.sensor_thread.join(timeout=3.0)
        print(f"{Color.YELLOW}[SENSOR] 自动上报已停止{Color.RESET}")

    # ---------- 按键模拟 ----------
    def send_button(self, cmd_id):
        """发送按键事件 b<cmd_id>"""
        data = f"b{cmd_id}".encode('utf-8')
        self._send_raw(data)
        names = {'1': '关机', '2': '对话', '3': '音量-', '4': '音量+'}
        name = names.get(cmd_id, '未知')
        print(f"  {Color.MAGENTA}[BTN] → b{cmd_id} ({name}){Color.RESET}")

    # ---------- 底层收发 ----------
    def _send_raw(self, data: bytes):
        """写原始字节到串口"""
        if not self.ser or not self.ser.is_open:
            print(f"{Color.RED}串口未打开，无法发送{Color.RESET}")
            return
        self.ser.write(data)
        self.tx_count += 1

    def read_and_process(self):
        """读串口缓冲区并处理收到的数据（非阻塞，每次调用处理一帧）"""
        if not self.ser or not self.ser.is_open:
            return

        try:
            raw = self.ser.read(256)
            if not raw:
                return
            self.rx_count += 1
            self._handle_rx(raw)
        except serial.SerialException as e:
            print(f"{Color.RED}串口读异常: {e}{Color.RESET}")

    def _handle_rx(self, data: bytes):
        """解析并显示从模组收到的消息"""
        if len(data) < 1:
            return

        msg_type = chr(data[0])

        if msg_type == 't':
            # 导航文字：模组 → 从机，用于屏幕显示
            text = data[1:].decode('utf-8', errors='replace')
            print(f"{Color.YELLOW}[NAV 显示] ← t: {text}{Color.RESET}")

        elif msg_type == 'g':
            # GPS 请求：模组请求从机返回当前 GPS 坐标，从机应答（最少间隔 5 秒才推进轨迹）
            print(f"{Color.CYAN}[GPS 请求] ← g{Color.RESET}")
            now = time.time()
            if now - self._last_gps_response_time >= self._gps_response_interval:
                self._advance_route()
                self._last_gps_response_time = now
            time.sleep(0.05)  # 模拟从机处理延迟
            self.send_gps_response()

        elif msg_type == 'b':
            # 按键事件回显（通常模组不会发 b 给从机，但记录以防万一）
            payload = data[1:].decode('utf-8', errors='replace') if len(data) > 1 else ''
            print(f"  [BTN 回显] ← b{payload}")

        else:
            # 未知消息类型
            hex_str = ' '.join(f'{b:02X}' for b in data)
            print(f"  [UNKNOWN] ← {msg_type} | hex: {hex_str}")


# ============================================================================
# 交互式控制台
# ============================================================================
def list_available_ports():
    """扫描并返回可用串口列表"""
    return list(serial.tools.list_ports.comports())


def select_port_interactive():
    """交互式选择串口和波特率，返回 (port, baudrate) 或 (None, None) 表示退出"""
    ports = list_available_ports()

    if not ports:
        print(f"{Color.RED}未检测到任何串口设备{Color.RESET}")
        print("  请连接设备后重试，或手动指定: python uart_slave_simulator.py <串口号>")
        return None, None

    print(f"\n{Color.BOLD}可用串口列表:{Color.RESET}")
    print(f"{'-' * 50}")
    for i, p in enumerate(ports, 1):
        desc = p.description if p.description else "无描述"
        vid_pid = ""
        if p.vid and p.pid:
            vid_pid = f"  VID:PID={p.vid:04X}:{p.pid:04X}"
        serial_num = f"  SN={p.serial_number}" if p.serial_number else ""
        print(f"  {Color.GREEN}[{i}]{Color.RESET} {Color.BOLD}{p.device}{Color.RESET} — {desc}{vid_pid}{serial_num}")
    print(f"{'-' * 50}")

    while True:
        try:
            choice = input(f"请选择串口 [1-{len(ports)}] 或输入 q 退出: ").strip()
            if choice.lower() == 'q':
                return None, None
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                selected = ports[idx]
                baud = input("波特率 (默认 115200, 回车跳过): ").strip()
                baudrate = int(baud) if baud else 115200
                return selected.device, baudrate
            print(f"{Color.RED}  无效选择，请输入 1-{len(ports)}{Color.RESET}")
        except ValueError:
            print(f"{Color.RED}  无效输入，请输入数字{Color.RESET}")


def print_banner(sim: UartSlaveSimulator):
    """打印欢迎信息和帮助"""
    print(f"""
{Color.BOLD}{'=' * 60}{Color.RESET}
{Color.CYAN}  EC800 UART 下位机模拟器{Color.RESET}
{Color.BOLD}{'=' * 60}{Color.RESET}

  串口: {sim.port} @ {sim.baudrate} baud
  当前位置: {sim.current_lat:.6f}, {sim.current_lng:.6f}

{Color.BOLD}键盘命令:{Color.RESET}
  1 / 2 / 3 / 4   发送按键事件 (关机/对话/音量-/音量+)
  g               手动发送一次当前 GPS 坐标（不受请求-应答约束）
  l <lat>,<lng>   设置当前位置
  m               手动发送一次传感器数据 (温度/心率/速度, 随机值)
  d               开始/停止 自动传感器上报 (每 5 秒)
  s               显示统计信息
  q / Ctrl+C      退出

{Color.BOLD}{'=' * 60}{Color.RESET}
""")


def print_stats(sim: UartSlaveSimulator):
    """打印统计信息"""
    sensor_status = "运行中 (5s间隔, 随机值)" if sim.auto_sensor_enabled else "已停止"
    print(f"""
{Color.BOLD}── 统计 ──{Color.RESET}
  串口:        {sim.port} @ {sim.baudrate}
  当前位置:    {sim.current_lat:.6f}, {sim.current_lng:.6f}
  GPS 轨迹:    仅在收到上位机 g 请求时应答 (路径点 {sim.route_index + 1}/{len(sim.route)})
  传感器上报:  {sensor_status}
  接收帧数:    {sim.rx_count}
  发送帧数:    {sim.tx_count}
""")


def handle_keyboard(sim: UartSlaveSimulator, line: str) -> bool:
    """处理键盘输入，返回 False 表示退出"""
    line = line.strip().lower()

    if not line:
        print_banner(sim)
        return True

    if line == 'q':
        return False

    if line in ('1', '2', '3', '4'):
        sim.send_button(line)
        return True

    if line == 'g':
        sim._advance_route()
        sim.send_gps_response()
        return True

    if line == 'm':
        sim.send_sensor()
        return True

    if line == 'a':
        sim.send_alert(0)          # 随机告警类型
        return True
    if line in ('a1', 'a2', 'a3'):
        sim.send_alert(int(line[1]))
        return True

    if line == 'd':
        if sim.auto_sensor_enabled:
            sim.stop_auto_sensor()
        else:
            sim.start_auto_sensor()
        return True

    if line.startswith('l'):
        # 格式: l<lat>,<lng>  例如 l39.9825,116.3054
        coords = line[1:].split(',')
        if len(coords) == 2:
            try:
                sim.current_lat = float(coords[0].strip())
                sim.current_lng = float(coords[1].strip())
                print(f"  {Color.GREEN}位置已更新: {sim.current_lat:.6f}, {sim.current_lng:.6f}{Color.RESET}")
            except ValueError:
                print(f"  {Color.RED}格式错误，示例: l39.9825,116.3054{Color.RESET}")
        else:
            print(f"  {Color.RED}格式错误，示例: l39.9825,116.3054{Color.RESET}")
        return True

    if line == 's':
        print_stats(sim)
        return True

    print(f"  {Color.RED}未知命令: '{line}'，回车查看帮助{Color.RESET}")
    return True


def main_loop(sim: UartSlaveSimulator):
    """主循环：串口轮询 + 键盘输入"""
    print_banner(sim)
    sim.start_auto_sensor()  # 默认开启传感器定时上报
    # GPS 不再自动推送，仅在收到上位机 g 请求时应答

    # 使用线程读键盘输入，避免 input() 阻塞串口轮询
    input_queue = []

    def keyboard_thread():
        while True:
            try:
                line = input()
                input_queue.append(line)
            except EOFError:
                break

    kb_thread = threading.Thread(target=keyboard_thread, daemon=True)
    kb_thread.start()

    running = True
    while running:
        # 读串口
        sim.read_and_process()

        # 处理键盘输入
        while input_queue:
            line = input_queue.pop(0)
            if not handle_keyboard(sim, line):
                running = False
                break

        time.sleep(0.01)  # 10ms 轮询周期

    kb_thread.join(timeout=0.5)


# ============================================================================
# 入口
# ============================================================================
def main():
    if len(sys.argv) < 2:
        # 没有指定端口 → 自动扫描并交互选择
        print(f"\n{Color.CYAN}未指定串口号，自动扫描可用串口...{Color.RESET}")
        port, baudrate = select_port_interactive()
        if port is None:
            sys.exit(0)
    else:
        port = sys.argv[1]
        baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    sim = UartSlaveSimulator(port, baudrate)

    # 注册退出清理
    def cleanup(signum=None, frame=None):
        print(f"\n{Color.YELLOW}正在退出...{Color.RESET}")
        sim.disconnect()
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    if not sim.connect():
        sys.exit(1)

    try:
        main_loop(sim)
    finally:
        sim.disconnect()


if __name__ == '__main__':
    main()
