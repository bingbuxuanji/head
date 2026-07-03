#ifndef __MPU6050_H
#define __MPU6050_H

#include "main.h"
#include <stdint.h>

// ----------------------------
// I2C 地址（AD0接GND时为0x68，接VCC时为0x69）
// ----------------------------
#define MPU6050_ADDR         0x68

// ----------------------------
// 寄存器地址映射
// ----------------------------
#define MPU6050_WHO_AM_I     0x75    // 只读，固定值0x68
#define MPU6050_PWR_MGMT_1   0x6B    // 电源管理1
#define MPU6050_SMPLRT_DIV   0x19    // 采样率分频
#define MPU6050_CONFIG       0x1A    // 低通滤波器配置
#define MPU6050_GYRO_CONFIG  0x1B    // 陀螺仪量程配置
#define MPU6050_ACCEL_CONFIG 0x1C    // 加速度计量程配置
#define MPU6050_ACCEL_XOUT_H 0x3B    // 加速度计X轴高8位
#define MPU6050_ACCEL_XOUT_L 0x3C    // 加速度计X轴低8位
#define MPU6050_ACCEL_YOUT_H 0x3D
#define MPU6050_ACCEL_YOUT_L 0x3E
#define MPU6050_ACCEL_ZOUT_H 0x3F
#define MPU6050_ACCEL_ZOUT_L 0x40
#define MPU6050_TEMP_OUT_H   0x41    // 温度高8位
#define MPU6050_TEMP_OUT_L   0x42    // 温度低8位
#define MPU6050_GYRO_XOUT_H  0x43    // 陀螺仪X轴高8位
#define MPU6050_GYRO_XOUT_L  0x44
#define MPU6050_GYRO_YOUT_H  0x45
#define MPU6050_GYRO_YOUT_L  0x46
#define MPU6050_GYRO_ZOUT_H  0x47
#define MPU6050_GYRO_ZOUT_L  0x48

// ----------------------------
// 量程与灵敏度系数
// ----------------------------
// 加速度计量程可选：±2g, ±4g, ±8g, ±16g
#define ACCEL_FS_SEL_2G      0x00
#define ACCEL_FS_SEL_4G      0x08
#define ACCEL_FS_SEL_8G      0x10
#define ACCEL_FS_SEL_16G     0x18
// 对应灵敏度（LSB/g）
#define ACCEL_SCALE_2G       16384.0f
#define ACCEL_SCALE_4G       8192.0f
#define ACCEL_SCALE_8G       4096.0f
#define ACCEL_SCALE_16G      2048.0f

// 陀螺仪量程可选：±250, ±500, ±1000, ±2000 °/s
#define GYRO_FS_SEL_250      0x00
#define GYRO_FS_SEL_500      0x08
#define GYRO_FS_SEL_1000     0x10
#define GYRO_FS_SEL_2000     0x18
// 对应灵敏度（LSB/(°/s)）
#define GYRO_SCALE_250       131.0f
#define GYRO_SCALE_500       65.5f
#define GYRO_SCALE_1000      32.8f
#define GYRO_SCALE_2000      16.4f

// ----------------------------
// 数据结构体
// ----------------------------
typedef struct
{
    float ax;       // 加速度 X (g)
    float ay;       // 加速度 Y (g)
    float az;       // 加速度 Z (g)
    float gx;       // 角速度 X (°/s)
    float gy;       // 角速度 Y (°/s)
    float gz;       // 角速度 Z (°/s)
    float temp;     // 温度 (°C)
} MPU6050_DataTypeDef;

// ----------------------------
// 函数声明
// ----------------------------
uint8_t MPU6050_Init(void);
uint8_t MPU6050_ReadRaw(int16_t *ax, int16_t *ay, int16_t *az,
                        int16_t *gx, int16_t *gy, int16_t *gz,
                        int16_t *temp);
uint8_t MPU6050_ReadAll(MPU6050_DataTypeDef *data);
void MPU6050_GetAngle(float *roll, float *pitch);  // 互补滤波简易姿态

#endif

