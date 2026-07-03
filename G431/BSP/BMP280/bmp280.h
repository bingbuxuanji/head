#ifndef __BMP280_H
#define __BMP280_H

#include "stm32g4xx.h"
#include "main.h"
#include <stdint.h>
#include <stdbool.h>

#include "i2c.h"

// ---------------------------
//  I2C 地址配置（取决于SDO引脚）
// ---------------------------
#define BMP280_I2C_ADDR_0x76  0x76    // SDO接地或悬空 (左移1位前地址)
#define BMP280_I2C_ADDR_0x77  0x77    // SDO接高电平

// 可根据实际硬件修改使用的地址宏
#define BMP280_I2C_ADDRESS    BMP280_I2C_ADDR_0x76

// ---------------------------
//  寄存器地址
// ---------------------------
#define BMP280_REG_ID         0xD0    // 芯片ID (应为0x58)
#define BMP280_REG_RESET      0xE0    // 软件复位
#define BMP280_REG_CTRL_MEAS  0xF4    // 控制测量寄存器
#define BMP280_REG_CONFIG     0xF5    // 配置寄存器
#define BMP280_REG_PRESS_MSB  0xF7    // 压力数据高位
#define BMP280_REG_PRESS_LSB  0xF8    // 压力数据中位
#define BMP280_REG_PRESS_XLSB 0xF9    // 压力数据低位
#define BMP280_REG_TEMP_MSB   0xFA    // 温度数据高位
#define BMP280_REG_TEMP_LSB   0xFB    // 温度数据中位
#define BMP280_REG_TEMP_XLSB  0xFC    // 温度数据低位

// ---------------------------
//  校准数据寄存器起始地址
// ---------------------------
#define BMP280_CALIB_START    0x88
#define BMP280_CALIB_END      0xBE

// ---------------------------
//  测量模式
// ---------------------------
#define BMP280_MODE_SLEEP     0x00
#define BMP280_MODE_FORCED    0x01
#define BMP280_MODE_NORMAL    0x03

// ---------------------------
//  过采样设置 (OSRS)
// ---------------------------
#define BMP280_OSRS_SKIPPED   0x00
#define BMP280_OSRS_1X        0x01
#define BMP280_OSRS_2X        0x02
#define BMP280_OSRS_4X        0x03
#define BMP280_OSRS_8X        0x04
#define BMP280_OSRS_16X       0x05

// ---------------------------
//  滤波器系数
// ---------------------------
#define BMP280_FILTER_OFF     0x00
#define BMP280_FILTER_2       0x01
#define BMP280_FILTER_4       0x02
#define BMP280_FILTER_8       0x03
#define BMP280_FILTER_16      0x04

// ---------------------------
//  数据结果结构体
// ---------------------------
typedef struct
{
    float temperature;      // 温度 (单位: °C)
    float pressure;         // 气压 (单位: Pa)
} BMP280_Result_t;

// ---------------------------
//  函数声明
// ---------------------------
uint8_t BMP280_Init(void);
uint8_t BMP280_SoftReset(void);
uint8_t BMP280_CheckChipID(void);
uint8_t BMP280_ReadCalibration(void);
uint8_t BMP280_SetMode(uint8_t mode, uint8_t osrs_t, uint8_t osrs_p, uint8_t filter);
uint8_t BMP280_ReadData(BMP280_Result_t *result);

#endif

