#include "./BH1750/bh1750.h"
#include "i2c.h"          // 包含 hi2c1 句柄

extern I2C_HandleTypeDef hi2c1;

// 发送单字节命令
static uint8_t BH1750_WriteCmd(uint8_t cmd)
{
    return HAL_I2C_Master_Transmit(&hi2c1, BH1750_ADDR << 1, &cmd, 1, 100);
}

// 初始化：上电、可选复位、设为连续高分辨率模式2（推荐）
uint8_t BH1750_Init(void)
{
    // 上电
    if (BH1750_WriteCmd(BH1750_POWER_ON) != HAL_OK)
        return 1;
    HAL_Delay(10);
    return BH1750_SetMode(BH1750_CONT_H_RES_MODE2);
}

// 设置测量模式
uint8_t BH1750_SetMode(uint8_t mode)
{
    return BH1750_WriteCmd(mode);
}

// 读取光照值 (lux)
uint8_t BH1750_ReadLight(float *lux)
{
    uint8_t data[2];
    // 等待传感器完成测量（取决于模式，高分辨率需120~180ms）
    HAL_Delay(180);
    // 读取2字节数据
    if (HAL_I2C_Master_Receive(&hi2c1, BH1750_ADDR << 1, data, 2, 100) != HAL_OK)
        return 1;
    // 合并为16位
    uint16_t raw = (data[0] << 8) | data[1];
    // 转换：lux = raw / 1.2
    *lux = (float)raw / 1.2f;
    return 0;
}

