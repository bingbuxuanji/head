#include "func.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

/* 心率演算过程 debug 开关：0=关闭（不发垃圾报文到 UART2），1=开启 */
#define DEBUG_MAX30102_RUN 0

volatile uint32_t sys_tick = 0;
uint16_t last_500ms = 0, last_10ms = 0;        // 匹配 func.h 的 extern 声明
static volatile uint8_t last_100ms = 0;         // 仅 func.c 内部使用

key_state S1 = {1, 0};
key_state S2 = {1, 0};
key_state S3 = {1, 0};
key_state S4 = {1, 0};

MAX30102_Result_t max30102_result = {0};

/* ---------- 传感器数据缓存 ---------- */
static float    g_sensor_temp     = -1.0f;   // BMP280 温度, -1 表示无效
int32_t  g_sensor_hr       = -1;              // MAX30102 心率, -1 表示无效（供 OLED 显示）
static int32_t  g_sensor_pressure = -1;      // BMP280 气压, -1 表示无效

/* ---------- IMU 数据缓存 ---------- */
static float g_imu_ax = -999.0f, g_imu_ay = -999.0f, g_imu_az = -999.0f;
static float g_imu_gx = -999.0f, g_imu_gy = -999.0f, g_imu_gz = -999.0f;

/* ---------- 摔倒检测 ---------- */
static uint8_t g_high_acc_count = 0;  // 连续高加速度计数

/* ---------- 5 秒发送计数器 ---------- */
static uint8_t g_sec5_counter = 0;

/* ---------- GPS 坐标缓存 ---------- */
static float    g_gps_lng = 0.0f, g_gps_lat = 0.0f;
static uint8_t  g_gps_valid = 0;             // 0=无有效定位, 1=已定位

/* ---------- 测试模式（默认开启，方便调试）---------- */
static uint8_t g_gps_test_mode    = 1;       // GPS 测试模式：使用模拟轨迹
static uint8_t g_sensor_test_mode = 1;       // 传感器测试模式：使用模拟数据

/* GPS 模拟轨迹（成都郫都→天府广场，取自 tests/uart_slave_simulator.py） */
static const float g_test_route[][2] = {
    {30.818529, 103.985887},
    {30.808000, 103.991500},
    {30.790000, 104.005000},
    {30.769500, 104.015500},
    {30.738000, 104.037000},
    {30.701000, 104.058500},
    {30.670000, 104.065900},
    {30.657401, 104.065861},
};
#define TEST_ROUTE_LEN (sizeof(g_test_route) / sizeof(g_test_route[0]))
static uint8_t g_test_route_idx = 0;

/* 简易 LCG 伪随机（用于传感器模拟） */
static uint16_t g_test_rand = 0x1234;
static uint16_t test_rand(void) {
    g_test_rand = g_test_rand * 1103 + 12345;
    return g_test_rand;
}

/* 测试模式 GPS 更新：每 5 分钟推进一个轨迹点 */
void test_gps_update(void)
{
    g_gps_lng = g_test_route[g_test_route_idx][1];
    g_gps_lat = g_test_route[g_test_route_idx][0];
    g_gps_valid = 1;
    if (g_test_route_idx < TEST_ROUTE_LEN - 1)
        g_test_route_idx++;
}

/* 测试模式传感器更新：生成模拟值 */
static void test_sensor_update(void)
{
    g_sensor_temp     = 36.0f + (float)(test_rand() % 100) * 0.01f;  // 36.0~37.0
    g_sensor_hr       = 65 + (test_rand() % 35);                     // 65~99
    g_sensor_pressure = 100800 + (test_rand() % 1000);               // ~101kPa
    g_imu_ax = -0.20f + (float)(test_rand() % 40) * 0.01f;
    g_imu_ay = -0.15f + (float)(test_rand() % 30) * 0.01f;
    g_imu_az =  1.00f + (float)(test_rand() % 15) * 0.01f;
    g_imu_gx = -5.0f + (float)(test_rand() % 100) * 0.1f;
    g_imu_gy = -5.0f + (float)(test_rand() % 100) * 0.1f;
    g_imu_gz = -5.0f + (float)(test_rand() % 100) * 0.1f;
}

/* ---------- 导航文字缓存 ---------- */
char        g_nav_text[48] = {0};             // OLED 显示窗口（约 6 中文/12 ASCII）
char        g_nav_full[256] = {0};            // 完整导航文字
uint16_t    g_nav_scroll = 0;                 // 滚动偏移（字节）
volatile uint8_t g_nav_text_updated = 0;     // 1=有新导航文字待刷新 OLED

/* ---------- 时间显示缓存 ---------- */
char        g_time_text[16] = {0};            // "HH:MM:SS"
char        g_mood_text[8]  = {0};            // 心情 ":)" ">:"
volatile uint8_t g_time_updated = 0;

/* ---------- 采集控制 ---------- */
static uint8_t g_sensor_status     = 0;      // 传感器初始化状态位掩码（0x01:BH1750, 0x02:BMP280, 0x04:MPU6050, 0x08:MAX30102）
static uint8_t g_collection_enabled = 0;     // 0=等待 EC800 启动指令, 1=允许定时上报

/* ---------- UART IDLE DMA 接收缓冲（参考 QS gps.c）---------- */
static uint8_t g_gps_rx_buf[512];            // USART1: GPS NMEA 数据
static uint8_t g_cmd_rx_buf[256];            // USART2: EC800 指令

/* ================================================================
 * MAX30102 internal working variables
 * ================================================================ */
static uint32_t aun_ir_buffer[BUFFER_SIZE];     // IR sensor data buffer
static uint32_t aun_red_buffer[BUFFER_SIZE];    // Red sensor data buffer
static int32_t  n_ir_buffer_length = BUFFER_SIZE;
static uint8_t  max30102_ready = 0;             // 0=collecting, 1=ready for calculation
static int32_t  sample_index = 0;               // current sample index

/* ================================================================
 * sersor_init()
 *   Initialize all sensors
 * ================================================================ */
void sersor_init(void)
{
    uint8_t id;
    g_sensor_status = 0;

    if (BH1750_Init() == 0) {
        g_sensor_status |= 0x01;
        printf("BH1750 Init OK\r\n");
    } else
        printf("BH1750 Init Failed\r\n");

    if (BMP280_Init() != 1)
        printf("BMP280 Init Failed\r\n");
    else {
        g_sensor_status |= 0x02;
        printf("BMP280 Init OK\r\n");
    }

    if (MPU6050_Init() != 0)
        printf("MPU6050 init failed\r\n");
    else {
        g_sensor_status |= 0x04;
        printf("MPU6050 ready\r\n");
    }

    /* MAX30102: 失败不阻塞，无心率数据时上报 -1 占位 */
    if (MAX30102_Init() == 0) {
        MAX30102_ReadID(&id);
        g_sensor_status |= 0x08;
        printf("MAX30102 Init OK, ID:0x%02X\r\n", id);
    } else {
        printf("MAX30102 Init Failed\r\n");
    }
}

/* ================================================================
 * MAX30102_run()
 *   Continuously collect MAX30102 data; calculate HR/SpO2 every
 *   time 500 samples are ready.
 *
 *   Strategy (matching Maxim reference code):
 *     Initial: collect 500 samples -> calculate HR/SpO2
 *     Loop:    keep last 400 samples, collect 100 new ones -> recalculate
 * ================================================================ */
static void MAX30102_run(void)
{
    MAX30102_Data_t samples[32];  // FIFO max depth = 32
    uint8_t n_samples, ret;

    /* Drain ALL available samples from FIFO (up to 32 at once) */
    ret = MAX30102_ReadFIFO(samples, 32, &n_samples);
    if (ret != 0 || n_samples == 0) {
        return;  // FIFO empty or error — wait for next poll cycle
    }

    /* ---- Process all samples read from FIFO ---- */
    for (uint8_t i = 0; i < n_samples; i++) {
        if (!max30102_ready) {
            /* Phase 1: initial 500-sample collection */
            aun_red_buffer[sample_index] = samples[i].red;
            aun_ir_buffer[sample_index]  = samples[i].ir;
            max30102_result.red = samples[i].red;
            max30102_result.ir  = samples[i].ir;
            sample_index++;

#if DEBUG_MAX30102_RUN
            printf("COLLECT[%d] red=%lu ir=%lu\r\n",
                   (int)sample_index,
                   (unsigned long)samples[i].red,
                   (unsigned long)samples[i].ir);
#endif

            if (sample_index >= BUFFER_SIZE) {
                maxim_heart_rate_and_oxygen_saturation(
                    aun_ir_buffer, n_ir_buffer_length,
                    aun_red_buffer,
                    &max30102_result.spo2, &max30102_result.spo2_valid,
                    &max30102_result.heart_rate, &max30102_result.hr_valid);
                max30102_ready = 1;
                sample_index = 400;
#if DEBUG_MAX30102_RUN
                printf("=== FIRST CALC: HR=%d(%d) SpO2=%d(%d) ===\r\n",
                       (int)max30102_result.heart_rate, max30102_result.hr_valid,
                       (int)max30102_result.spo2, max30102_result.spo2_valid);
#endif
            }
        } else {
            /* Phase 2: sliding window — shift + collect 100 new samples */
            if (sample_index == 400) {
                // Shift buffer: discard oldest 100, keep last 400
                for (int32_t j = 100; j < BUFFER_SIZE; j++) {
                    aun_red_buffer[j - 100] = aun_red_buffer[j];
                    aun_ir_buffer[j - 100]  = aun_ir_buffer[j];
                }
            }

            aun_red_buffer[sample_index] = samples[i].red;
            aun_ir_buffer[sample_index]  = samples[i].ir;
            max30102_result.red = samples[i].red;
            max30102_result.ir  = samples[i].ir;
            sample_index++;

            if (sample_index >= BUFFER_SIZE) {
                maxim_heart_rate_and_oxygen_saturation(
                    aun_ir_buffer, n_ir_buffer_length,
                    aun_red_buffer,
                    &max30102_result.spo2, &max30102_result.spo2_valid,
                    &max30102_result.heart_rate, &max30102_result.hr_valid);
                sample_index = 400;

#if DEBUG_MAX30102_RUN
                printf("HR=%d(%d) SpO2=%d(%d) red=%lu ir=%lu\r\n",
                       (int)max30102_result.heart_rate, max30102_result.hr_valid,
                       (int)max30102_result.spo2, max30102_result.spo2_valid,
                       (unsigned long)max30102_result.red,
                       (unsigned long)max30102_result.ir);
#endif
            }
        }
    }
}

/* ================================================================
 * sersor_data()
 *   Sensor data acquisition dispatch (called every loop iteration)
 *   - MAX30102: 每轮都跑，快速排空 FIFO
 *   - BMP280:  由 sersor_slow_read() 每 500ms 读取一次
 *   - MPU6050: 由 imu_read() 每 100ms 读取一次
 * ================================================================ */
void sersor_data(void)
{
    MAX30102_run();

    /* 更新心率缓存（测试模式下由 test_sensor_update 统一管理） */
    if (!g_sensor_test_mode && max30102_result.hr_valid) {
        g_sensor_hr = max30102_result.heart_rate;
    }
}

/* ================================================================
 * sersor_slow_read()
 *   每 500ms 调用一次：读取 BMP280 温度 + 气压
 * ================================================================ */
static void sersor_slow_read(void)
{
    /* 测试模式下传感数据由 test_sensor_update 统一生成 */
    if (g_sensor_test_mode) return;

    BMP280_Result_t bmp_data;
    if (BMP280_ReadData(&bmp_data)) {
        g_sensor_temp     = bmp_data.temperature;
        g_sensor_pressure = (int32_t)bmp_data.pressure;
    }
}

/* ================================================================
 * imu_read()
 *   每 100ms 调用一次：读取 MPU6050 六轴数据
 * ================================================================ */
static void imu_read(void)
{
    if (g_sensor_test_mode) return;   /* 测试模式由 test_sensor_update 管理 */

    MPU6050_DataTypeDef mpu_data;
    if (MPU6050_ReadAll(&mpu_data) == 0) {
        g_imu_ax = mpu_data.ax;
        g_imu_ay = mpu_data.ay;
        g_imu_az = mpu_data.az;
        g_imu_gx = mpu_data.gx;
        g_imu_gy = mpu_data.gy;
        g_imu_gz = mpu_data.gz;
    }
}

/* ================================================================
 * send_init_status()
 *   发送 i 报文: i<hex>
 *   传感器初始化状态位掩码（0x01:BH1750, 0x02:BMP280,
 *   0x04:MPU6050, 0x08:MAX30102），例 iF = 全部就绪
 *   开机后调用一次，通知 EC800 哪些传感器可用。
 * ================================================================ */
void send_init_status(void)
{
    printf("i%X\r\n", g_sensor_status);
}

/* ================================================================
 * send_sensor_uart()
 *   发送 s 报文: s<温度>,<心率>,<气压>
 *   占位: -1 表示该传感器无数据
 * ================================================================ */
static void send_sensor_uart(void)
{
    printf("s%.1f,%ld,%ld\r\n",
           (double)g_sensor_temp,
           (long)g_sensor_hr,
           (long)g_sensor_pressure);
}

/* ================================================================
 * send_imu_uart()
 *   发送 m 报文: m<ax>,<ay>,<az>,<gx>,<gy>,<gz>
 *   占位: -999 表示该轴无数据
 *   正常每 5 秒由 def_main 定时发送，摔倒/碰撞时立即触发
 * ================================================================ */
static void send_imu_uart(void)
{
    printf("m%.3f,%.3f,%.3f,%.3f,%.3f,%.3f\r\n",
           (double)g_imu_ax, (double)g_imu_ay, (double)g_imu_az,
           (double)g_imu_gx, (double)g_imu_gy, (double)g_imu_gz);
}

/* ================================================================
 * imu_fall_detect()
 *   每 100ms 调用一次：摔倒/碰撞检测
 *   检测到异常时立即触发一次数据上报（不等待 5s 定时）
 *
 *   判断依据（参考 readme §9.8）：
 *     - 合加速度 |a| > 3g 持续 → 可能碰撞
 *     - 角速度幅值 |ω| > 300°/s 且 |a| < 0.5g → 可能摔倒
 * ================================================================ */
static void imu_fall_detect(void)
{
    float acc_mag, gyro_mag;

    /* 数据无效时跳过（哨兵值 -999） */
    if (g_imu_ax < -900.0f) return;

    acc_mag = sqrtf(g_imu_ax * g_imu_ax +
                    g_imu_ay * g_imu_ay +
                    g_imu_az * g_imu_az);
    gyro_mag = sqrtf(g_imu_gx * g_imu_gx +
                     g_imu_gy * g_imu_gy +
                     g_imu_gz * g_imu_gz);

    /* 条件 1：碰撞 — 合加速度 > 3g 持续 > 300ms (3 次 * 100ms) */
    if (acc_mag > 3.0f) {
        g_high_acc_count++;
        if (g_high_acc_count >= 3) {
            g_high_acc_count = 0;
            printf("ALERT: collision detected |a|=%.1fg\r\n", (double)acc_mag);
            if (g_collection_enabled) {
                send_sensor_uart();
                send_imu_uart();
            }
            return;
        }
    } else {
        g_high_acc_count = 0;
    }

    /* 条件 2：摔倒 — 角速度 > 300°/s 且加速度骤降 < 0.5g */
    if (gyro_mag > 300.0f && acc_mag < 0.5f) {
        printf("ALERT: fall detected |ω|=%.1f°/s |a|=%.2fg\r\n",
               (double)gyro_mag, (double)acc_mag);
        if (g_collection_enabled) {
            send_sensor_uart();
            send_imu_uart();
        }
    }
}

/* ================================================================
 * DM_To_DD()
 *   度分格式 → 十进制度（参考 QS gps.c）
 *   输入: dm=原始度分值(如 3027.1234), dir='N'/'S'/'E'/'W'
 *   输出: 十进制度 (如 30.452057)
 * ================================================================ */
static float DM_To_DD(float dm, char dir)
{
    int   deg = (int)(dm / 100.0f);
    float min = dm - (float)(deg * 100);
    float dd  = (float)deg + min / 60.0f;

    if (dir == 'S' || dir == 'W')
        dd = -dd;
    return dd;
}

/* ================================================================
 * GPS_Parse_Data()
 *   解析 NMEA GGA 语句，提取经纬度（参考 QS gps.c GPS_Parse_Data）
 *   GGA 格式: $GxGGA,hhmmss,ddmm.mmmm,N,dddmm.mmmm,E,q,...
 * ================================================================ */
static void GPS_Parse_Data(char *buf)
{
    char *gga, *end, *p;
    char line[128];
    float raw_lat = 0.0f, raw_lon = 0.0f;
    char  lat_dir = 'N', lon_dir = 'E';
    int   i, len;

    /* 查找 GGA 语句 */
    gga = strstr(buf, "$GNGGA");
    if (!gga) gga = strstr(buf, "$GPGGA");
    if (!gga) return;

    /* 截取一行 */
    end = strchr(gga, '\n');
    if (!end) end = strchr(gga, '\r');
    if (!end) end = gga + strlen(gga);
    len = (int)(end - gga);
    if (len >= (int)sizeof(line)) len = (int)sizeof(line) - 1;
    memcpy(line, gga, (size_t)len);
    line[len] = '\0';

    /* 去除尾部 \r */
    for (i = len - 1; i >= 0 && line[i] == '\r'; i--)
        line[i] = '\0';

    /* 按逗号分割提取字段 */
    p = line;
    for (i = 0; i <= 6; i++) {
        char *next = strchr(p, ',');
        if (next) *next = '\0';   /* 临时截断 */

        switch (i) {
            case 2: if (*p) raw_lat = (float)atof(p); break;   /* 纬度 */
            case 3: if (*p) lat_dir = p[0];         break;     /* N/S */
            case 4: if (*p) raw_lon = (float)atof(p); break;   /* 经度 */
            case 5: if (*p) lon_dir = p[0];         break;     /* E/W */
            case 6: /* 定位质量: 1=单点定位, 2=差分定位 */
                if (*p && (p[0] == '1' || p[0] == '2'))
                    g_gps_valid = 1;
                break;
        }

        if (next) p = next + 1;
        else break;
    }

    /* 度分 → 十进制度 */
    if (raw_lat != 0.0f) g_gps_lat = DM_To_DD(raw_lat, lat_dir);
    if (raw_lon != 0.0f) g_gps_lng = DM_To_DD(raw_lon, lon_dir);
}

/* ================================================================
 * gps_uart_init()
 *   启动 USART1+USART2 的 IDLE DMA 接收（参考 QS GPS_Init）
 *   替代原来的 usart_start_DMA，在 main.c 初始化阶段调用
 * ================================================================ */
void gps_uart_init(void)
{
    HAL_UARTEx_ReceiveToIdle_DMA(&huart1, g_gps_rx_buf, sizeof(g_gps_rx_buf));
    HAL_UARTEx_ReceiveToIdle_DMA(&huart2, g_cmd_rx_buf, sizeof(g_cmd_rx_buf));
}

/* 前向声明 */
void nav_scroll_update(void);

/* ================================================================
 * HAL_UARTEx_RxEventCallback()
 *   HAL 弱函数覆盖：任意 UART 收到 IDLE 时 HAL 自动回调
 *   - USART1: 解析 GPS NMEA → 更新 g_gps_lng/g_gps_lat
 *   - USART2: 处理 EC800 指令 (g/t)
 *   参考 QS gps.c HAL_UARTEx_RxEventCallback
 * ================================================================ */
void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if (huart->Instance == USART1) {
        /* GPS NMEA 数据 */
        char tmp[256];
        uint16_t n;

        n = Size < (uint16_t)(sizeof(tmp) - 1) ? Size : (uint16_t)(sizeof(tmp) - 1);
        memcpy(tmp, g_gps_rx_buf, n);
        tmp[n] = '\0';
        GPS_Parse_Data(tmp);
        HAL_UARTEx_ReceiveToIdle_DMA(&huart1, g_gps_rx_buf, sizeof(g_gps_rx_buf));
    }
    else if (huart->Instance == USART2) {
        /* EC800 指令 — 按 \r\n 分行解析，彻底解决粘包 */
        uint16_t pos = 0;

        while (pos < Size) {
            /* 定位行首，跳过前导 \r\n */
            while (pos < Size && (g_cmd_rx_buf[pos] == '\r' || g_cmd_rx_buf[pos] == '\n'))
                pos++;
            if (pos >= Size) break;

            uint16_t line_start = pos;
            /* 找行尾 \r 或 \n */
            while (pos < Size && g_cmd_rx_buf[pos] != '\r' && g_cmd_rx_buf[pos] != '\n')
                pos++;
            uint16_t line_len = pos - line_start;
            if (line_len == 0) continue;

            char cmd = (char)g_cmd_rx_buf[line_start];
            uint8_t *payload = &g_cmd_rx_buf[line_start + 1];
            uint16_t payload_len = line_len - 1;

            if (cmd == 'i') {
                g_collection_enabled = 1;
            }
            else if (cmd == 'g') {
                char tx[64];
                sprintf(tx, "g%.6f,%.6f\r\n",
                        (double)g_gps_lng, (double)g_gps_lat);
                HAL_UART_Transmit(&huart2, (uint8_t *)tx,
                                  (uint16_t)strlen(tx), 100);
            }
            else if (cmd == 't' && payload_len > 0) {
                /* 区分时间（"HH:MM:SS"[ mood]）和导航文字 */
                if (payload_len >= 8 && payload[2] == ':' && payload[5] == ':') {
                    memcpy(g_time_text, payload, 8);
                    g_time_text[8] = '\0';
                    /* 提取心情（时间后的 ASCII 文本） */
                    if (payload_len > 9 && payload[8] == ' ') {
                        uint16_t ml = payload_len - 9;
                        if (ml > sizeof(g_mood_text) - 1)
                            ml = sizeof(g_mood_text) - 1;
                        memcpy(g_mood_text, payload + 9, ml);
                        g_mood_text[ml] = '\0';
                    } else {
                        g_mood_text[0] = '\0';
                    }
                    g_time_updated = 1;
                } else {
                    /* 导航文字：存入完整缓存，滚动从头开始 */
                    uint16_t n = payload_len;
                    if (n > sizeof(g_nav_full) - 1)
                        n = sizeof(g_nav_full) - 1;
                    memcpy(g_nav_full, payload, n);
                    g_nav_full[n] = '\0';
                    g_nav_scroll = 0;
                    g_nav_text_updated = 1;  /* 主循环会调 nav_scroll_update */
                }
            }
        }

        HAL_UARTEx_ReceiveToIdle_DMA(&huart2, g_cmd_rx_buf, sizeof(g_cmd_rx_buf));
    }
}

/* ================================================================
 * key_scan()
 *   Key scan (called every 10ms)
 * ================================================================ */
void key_scan(void)
{
    S1.key_state = HAL_GPIO_ReadPin(S1_GPIO_Port, S1_Pin);
    S2.key_state = HAL_GPIO_ReadPin(S2_GPIO_Port, S2_Pin);
    S3.key_state = HAL_GPIO_ReadPin(S3_GPIO_Port, S3_Pin);
    S4.key_state = HAL_GPIO_ReadPin(S4_GPIO_Port, S4_Pin);

    if ((S1.key_state == 0) && (S1.last_state == 1))
        printf("b1\r\n");
    if ((S2.key_state == 0) && (S2.last_state == 1))
        printf("b2\r\n");
    if ((S3.key_state == 0) && (S3.last_state == 1))
        printf("b3\r\n");
    if ((S4.key_state == 0) && (S4.last_state == 1))
        printf("b4\r\n");

    S1.last_state = S1.key_state;
    S2.last_state = S2.key_state;
    S3.last_state = S3.key_state;
    S4.last_state = S4.key_state;
}

/* ================================================================
 * nav_scroll_update()
 *   超长导航文字单行滚动：从 g_nav_full 截取一屏到 g_nav_text
 * ================================================================ */
void nav_scroll_update(void)
{
    if (!g_nav_full[0]) return;

    uint8_t *src = (uint8_t *)g_nav_full + g_nav_scroll;
    char    *dst = g_nav_text;
    int      px  = 0;
    uint8_t  c;

    /* 逐个 UTF-8 字符放入显示窗口，直到接近 120px */
    while (*src && px < 112) {
        c = *src;
        uint8_t  len = 1;
        if ((c & 0xE0) == 0xC0)      len = 2;
        else if ((c & 0xF0) == 0xE0) len = 3;
        else if ((c & 0xF8) == 0xF0) len = 4;

        /* 检查是否会超出 OLED 宽度或缓冲区 */
        int char_w = (len == 1) ? 8 : 16;   // ASCII 8px, 中文 16px
        if (px + char_w > 128) break;
        if (src + len > (uint8_t *)g_nav_full + sizeof(g_nav_full)) break;
        if (dst + len > g_nav_text + sizeof(g_nav_text) - 1) break;

        memcpy(dst, src, len);
        dst += len;
        src += len;
        px  += char_w;
    }
    *dst = '\0';
    g_nav_text_updated = 1;

    /* 滚动指针前进一个 UTF-8 字符 */
    c = (uint8_t)g_nav_full[g_nav_scroll];
    if      ((c & 0xE0) == 0xC0) g_nav_scroll += 2;
    else if ((c & 0xF0) == 0xE0) g_nav_scroll += 3;
    else if ((c & 0xF8) == 0xF0) g_nav_scroll += 4;
    else                          g_nav_scroll += 1;

    /* 超出末尾则回绕 */
    if (g_nav_scroll >= sizeof(g_nav_full) || !g_nav_full[g_nav_scroll])
        g_nav_scroll = 0;
}

/* ================================================================
 * def_main()
 *   Main loop dispatch
 *
 *   时序:
 *     - 每轮:     sersor_data() (MAX30102 FIFO 快排)
 *     - 每 10ms:  key_scan()
 *     - 每 100ms: imu_read() → imu_fall_detect() (10Hz 姿态 + 摔倒检测)
 *                 摔倒触发 → 立即 send_sensor_uart() + send_imu_uart()
 *     - 每 500ms: sersor_slow_read() (BMP280)
 *     - 每 5s:    send_sensor_uart() + send_imu_uart() (正常定时上报)
 * ================================================================ */
void def_main(void)
{
    if (last_10ms == 1) {
        last_10ms = 0;
        key_scan();
    }
    if (last_100ms == 1) {
        last_100ms = 0;
        imu_read();
        imu_fall_detect();   // 检测到摔倒/碰撞会立即上报
    }
    if (last_500ms == 1) {
        last_500ms = 0;
        sersor_slow_read();

        /* 未收到 EC800 启动指令前，每 2 秒重发传感器状态 */
        if (!g_collection_enabled) {
            static uint8_t init_retry = 0;
            init_retry++;
            if (init_retry >= 4) {   // 4 × 500ms = 2 秒
                init_retry = 0;
                send_init_status();
            }
        }

        /* 导航文字滚动：每 500ms 推进一个字符 */
        if (g_collection_enabled && g_nav_full[0]) {
            nav_scroll_update();
        }

        g_sec5_counter++;
        if (g_sec5_counter >= 10) {   // 10 × 500ms = 5 秒
            g_sec5_counter = 0;

            /* 测试模式：GPS 每 5 分钟更新，传感器每 5 秒更新 */
            if (g_sensor_test_mode)
                test_sensor_update();
            if (g_gps_test_mode) {
                static uint8_t gps_tick = 0;
                gps_tick++;
                if (gps_tick >= 60) {  // 60 × 5s = 5 分钟
                    gps_tick = 0;
                    test_gps_update();
                }
            }

            if (g_collection_enabled) {
                send_sensor_uart();
                send_imu_uart();
            }
        }
    }
    sersor_data();
}

/* ================================================================
 * HAL_TIM_PeriodElapsedCallback()
 *   TIM2 interrupt callback — system timebase
 * ================================================================ */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        sys_tick++;
        if (sys_tick % 10 == 0)  last_10ms  = 1;
        if (sys_tick % 100 == 0) last_100ms = 1;
        if (sys_tick % 500 == 0) last_500ms = 1;
    }
}
