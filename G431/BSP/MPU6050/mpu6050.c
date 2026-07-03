#include "./MPU6050/mpu6050.h"
#include "i2c.h"          // 需包含你的I2C句柄定义
#include <math.h>

#define M_PI 3.14159265358979323846
#define PI 3.14159265358979323846f   

extern I2C_HandleTypeDef hi2c1;

// 静态变量：保存校准后的角速度零偏
static float gx_offset = 0, gy_offset = 0, gz_offset = 0;
static uint8_t is_calibrated = 0;

/* ------------------------------------------------------------------------- */
/* I2C 底层读写函数（私有） */
/* ------------------------------------------------------------------------- */
static uint8_t MPU6050_WriteReg(uint8_t reg, uint8_t data)
{
    return HAL_I2C_Mem_Write(&hi2c1, MPU6050_ADDR << 1, reg,
                             I2C_MEMADD_SIZE_8BIT, &data, 1, 100) == HAL_OK;
}

static uint8_t MPU6050_ReadReg(uint8_t reg, uint8_t *data)
{
    return HAL_I2C_Mem_Read(&hi2c1, MPU6050_ADDR << 1, reg,
                            I2C_MEMADD_SIZE_8BIT, data, 1, 100) == HAL_OK;
}

static uint8_t MPU6050_ReadRegs(uint8_t reg, uint8_t *data, uint16_t len)
{
    return HAL_I2C_Mem_Read(&hi2c1, MPU6050_ADDR << 1, reg,
                            I2C_MEMADD_SIZE_8BIT, data, len, 100) == HAL_OK;
}

/* ------------------------------------------------------------------------- */
/* 初始化函数 */
/* ------------------------------------------------------------------------- */
uint8_t MPU6050_Init(void)
{
    uint8_t id = 0;
    // 1. 唤醒芯片（退出睡眠模式）
    if (!MPU6050_WriteReg(MPU6050_PWR_MGMT_1, 0x00)) return 1;
    HAL_Delay(100);

    // 2. 检查 WHO_AM_I
    if (!MPU6050_ReadReg(MPU6050_WHO_AM_I, &id)) return 2;
    if (id != 0x68) return 3;

    // 3. 配置采样率分频 (125Hz, 1kHz / (7+1) = 125Hz)
    MPU6050_WriteReg(MPU6050_SMPLRT_DIV, 0x07);
    // 4. 配置数字低通滤波器 (DLPF, 带宽约20Hz)
    MPU6050_WriteReg(MPU6050_CONFIG, 0x06);
    // 5. 陀螺仪量程 ±2000 °/s
    MPU6050_WriteReg(MPU6050_GYRO_CONFIG, GYRO_FS_SEL_2000);
    // 6. 加速度计量程 ±2g
    MPU6050_WriteReg(MPU6050_ACCEL_CONFIG, ACCEL_FS_SEL_2G);

    return 0;
}

/* ------------------------------------------------------------------------- */
/* 读取原始数据（int16） */
/* ------------------------------------------------------------------------- */
uint8_t MPU6050_ReadRaw(int16_t *ax, int16_t *ay, int16_t *az,
                        int16_t *gx, int16_t *gy, int16_t *gz,
                        int16_t *temp)
{
    uint8_t buf[14];
    if (!MPU6050_ReadRegs(MPU6050_ACCEL_XOUT_H, buf, 14)) return 1;

    *ax = (int16_t)((buf[0] << 8) | buf[1]);
    *ay = (int16_t)((buf[2] << 8) | buf[3]);
    *az = (int16_t)((buf[4] << 8) | buf[5]);
    *temp = (int16_t)((buf[6] << 8) | buf[7]);
    *gx = (int16_t)((buf[8] << 8) | buf[9]);
    *gy = (int16_t)((buf[10] << 8) | buf[11]);
    *gz = (int16_t)((buf[12] << 8) | buf[13]);

    return 0;
}

/* ------------------------------------------------------------------------- */
/* 读取并转换为物理量（g, °/s, ℃） */
/* 注意：目前固定使用 ±2g 和 ±2000°/s 的灵敏度系数 */
/* ------------------------------------------------------------------------- */
uint8_t MPU6050_ReadAll(MPU6050_DataTypeDef *data)
{
    int16_t ax_raw, ay_raw, az_raw;
    int16_t gx_raw, gy_raw, gz_raw;
    int16_t temp_raw;

    if (MPU6050_ReadRaw(&ax_raw, &ay_raw, &az_raw,
                        &gx_raw, &gy_raw, &gz_raw,
                        &temp_raw)) return 1;

    // 加速度：±2g 量程，灵敏度 16384 LSB/g
    data->ax = ax_raw / 16384.0f;
    data->ay = ay_raw / 16384.0f;
    data->az = az_raw / 16384.0f;

    // 陀螺仪：±2000°/s 量程，灵敏度 16.4 LSB/(°/s)
    if (!is_calibrated) {
        // 第一次调用时简单校准零偏（静止状态）
        gx_offset = gx_raw;
        gy_offset = gy_raw;
        gz_offset = gz_raw;
        is_calibrated = 1;
    }
    data->gx = (gx_raw - gx_offset) / 16.4f;
    data->gy = (gy_raw - gy_offset) / 16.4f;
    data->gz = (gz_raw - gz_offset) / 16.4f;

    // 温度：公式 T(℃) = raw/340.0 + 36.53
    data->temp = temp_raw / 340.0f + 36.53f;

    return 0;
}

/* ------------------------------------------------------------------------- */
/* 互补滤波计算 roll 和 pitch (仅依赖加速度计) */
/* ------------------------------------------------------------------------- */
void MPU6050_GetAngle(float *roll, float *pitch)
{
    MPU6050_DataTypeDef data;
    MPU6050_ReadAll(&data);

    // 加速度计求俯仰角 (Pitch) 和横滚角 (Roll)
    *pitch = atan2f(-data.ax, sqrtf(data.ay * data.ay + data.az * data.az)) * 180.0f / (float)PI;
	*roll  = atan2f(data.ay, data.az) * 180.0f / (float)PI;
}

