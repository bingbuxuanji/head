#ifndef _FUNC_H
#define _FUNC_H

#include "stm32g4xx.h"
#include "main.h"

#include "i2c.h"
#include "usart.h"

#include "stdio.h"

#include "./BH1750/bh1750.h"
#include "./BMP280/bmp280.h"
#include "./MPU6050/mpu6050.h"
#include "./MAX30102/max30102.h"
#include "./MAX30102/algorithm.h"

/* 按键状态 */
typedef struct
{
    uint8_t key_state;
    uint8_t last_state;
} key_state;

/* MAX30102 测量结果 */
typedef struct {
    int32_t heart_rate;     // 心率 (bpm), -999 表示无效
    int8_t  hr_valid;       // 心率是否有效 (1/0)
    int32_t spo2;           // 血氧饱和度 (%), -999 表示无效
    int8_t  spo2_valid;     // 血氧是否有效 (1/0)
    uint32_t red;           // 当前红光 ADC 值
    uint32_t ir;            // 当前红外光 ADC 值
} MAX30102_Result_t;

/* 全局变量 */
extern volatile uint32_t sys_tick;
extern uint16_t last_500ms, last_10ms;
extern key_state S1, S2, S3, S4;
extern MAX30102_Result_t max30102_result;

/* 导航文字 + 时间（从 EC800 't' 报文解析，供 OLED 显示） */
extern char g_nav_text[48];
extern char g_nav_full[256];
extern volatile uint8_t g_nav_text_updated;
extern char g_time_text[16];
extern int32_t g_sensor_hr;
extern char g_mood_text[8];
extern volatile uint8_t g_time_updated;

/* 函数声明 */
void sersor_init(void);        // 传感器初始化
void send_init_status(void);   // 发送传感器初始化状态 (i 报文)
void test_gps_update(void);    // GPS 测试模式：设置初始坐标
void nav_scroll_update(void);   // 导航文字滚动截取一屏到 g_nav_text
void sersor_data(void);        // 传感器数据采集与计算
void key_scan(void);           // 按键扫描
void def_main(void);           // 主循环

#endif

