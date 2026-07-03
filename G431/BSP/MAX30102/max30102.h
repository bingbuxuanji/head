// max30102.h — MAX30102 heart rate / SpO2 sensor driver (STM32G431 HAL)
#ifndef __MAX30102_H
#define __MAX30102_H

#include "stm32g4xx.h"
#include "main.h"
#include <stdint.h>
#include <stdbool.h>

// I2C 设备地址 (7位地址，HAL库会自动左移1位)
#define MAX30102_I2C_ADDR      0x57

/* ========== 寄存器地址映射 ========== */
// 中断状态
#define MAX30102_REG_INT_STAT1      0x00    // 中断状态1
#define MAX30102_REG_INT_STAT2      0x01    // 中断状态2
// 中断使能
#define MAX30102_REG_INT_EN1        0x02    // 中断使能1
#define MAX30102_REG_INT_EN2        0x03    // 中断使能2
// FIFO
#define MAX30102_REG_FIFO_WR_PTR    0x04    // FIFO写指针
#define MAX30102_REG_OVF_COUNTER    0x05    // FIFO溢出计数器
#define MAX30102_REG_FIFO_RD_PTR    0x06    // FIFO读指针
#define MAX30102_REG_FIFO_DATA      0x07    // FIFO数据寄存器
#define MAX30102_REG_FIFO_CONFIG    0x08    // FIFO配置寄存器 ★ 参考代码有，原有缺失
// 工作模式
#define MAX30102_REG_MODE_CONFIG    0x09    // 模式配置
// SpO2
#define MAX30102_REG_SPO2_CONFIG    0x0A    // SpO2配置
// LED电流
#define MAX30102_REG_LED1_PA        0x0C    // LED1 (RED) 脉冲幅度
#define MAX30102_REG_LED2_PA        0x0D    // LED2 (IR)  脉冲幅度
#define MAX30102_REG_PILOT_PA       0x10    // Pilot LED 脉冲幅度 ★ 参考代码有，原有缺失
// 温度
#define MAX30102_REG_TEMP_INTEGER   0x1F    // 温度整数部分
#define MAX30102_REG_TEMP_FRAC      0x20    // 温度小数部分
#define MAX30102_REG_TEMP_CONFIG    0x21    // 温度配置 ★ 原有缺失
// ID
#define MAX30102_REG_PART_ID        0xFF    // 器件ID (应为0x15)

/* ========== 中断使能位 ========== */
#define INT_EN1_FIFO_FULL           (1 << 7)  // FIFO almost full
#define INT_EN1_PPG_RDY             (1 << 6)  // New FIFO data ready
#define INT_EN1_ALC_OVF             (1 << 5)  // Ambient light cancellation overflow
#define INT_EN1_PWR_RDY             (1 << 0)  // Power ready

/* ========== FIFO配置位 ========== */
#define FIFO_CONFIG_SMP_AVE_1       0x00      // 1 sample (no averaging)
#define FIFO_CONFIG_SMP_AVE_2       0x20      // 2 samples averaged
#define FIFO_CONFIG_SMP_AVE_4       0x40      // 4 samples averaged
#define FIFO_CONFIG_SMP_AVE_8       0x60      // 8 samples averaged
#define FIFO_CONFIG_ROLLOVER_EN     (1 << 4)  // FIFO rolls over when full
#define FIFO_CONFIG_ALMOST_FULL_17  0x0F      // interrupt when 17 empty slots remain

/* ========== 数据结构 ========== */
typedef struct {
    uint32_t red;   // 红光 ADC 原始值 (18位有效，需 & 0x3FFFF)
    uint32_t ir;    // 红外光 ADC 原始值 (18位有效，需 & 0x3FFFF)
} MAX30102_Data_t;

/* ========== 函数声明 ========== */
uint8_t MAX30102_Init(void);                        // 初始化传感器，返回0成功
uint8_t MAX30102_ReadID(uint8_t *id);               // 读取器件ID，应为0x15
void    MAX30102_SoftReset(void);                   // 软件复位
uint8_t MAX30102_WriteReg(uint8_t reg, uint8_t data);
uint8_t MAX30102_ReadReg(uint8_t reg, uint8_t *data);
uint8_t MAX30102_ReadFIFO(MAX30102_Data_t *data, uint8_t max_samples, uint8_t *samples_read);
void    MAX30102_SetLEDCurrent(uint8_t red_ma, uint8_t ir_ma);

#endif

