#include "./BMP280/bmp280.h"
#include <math.h>

extern I2C_HandleTypeDef hi2c1;  // 使用你的I2C句柄

// ---------------------------
//  校准数据结构体
// ---------------------------
typedef struct
{
    uint16_t dig_T1;
    int16_t  dig_T2;
    int16_t  dig_T3;
    uint16_t dig_P1;
    int16_t  dig_P2;
    int16_t  dig_P3;
    int16_t  dig_P4;
    int16_t  dig_P5;
    int16_t  dig_P6;
    int16_t  dig_P7;
    int16_t  dig_P8;
    int16_t  dig_P9;
} BMP280_Calib_t;

static BMP280_Calib_t calib;
static int32_t t_fine = 0;      // 用于温度补偿的中间变量，供压力计算使用

// ---------------------------
//  I2C 读写辅助函数
// ---------------------------
static uint8_t BMP280_ReadReg8(uint8_t reg, uint8_t *data)
{
    return HAL_I2C_Mem_Read(&hi2c1, BMP280_I2C_ADDRESS << 1, reg,
                            I2C_MEMADD_SIZE_8BIT, data, 1, 100) == HAL_OK;
}

static uint8_t BMP280_WriteReg8(uint8_t reg, uint8_t value)
{
    return HAL_I2C_Mem_Write(&hi2c1, BMP280_I2C_ADDRESS << 1, reg,
                             I2C_MEMADD_SIZE_8BIT, &value, 1, 100) == HAL_OK;
}

static uint8_t BMP280_ReadRegs(uint8_t reg, uint8_t *data, uint16_t len)
{
    return HAL_I2C_Mem_Read(&hi2c1, BMP280_I2C_ADDRESS << 1, reg,
                            I2C_MEMADD_SIZE_8BIT, data, len, 100) == HAL_OK;
}

// ---------------------------
//  读取校准数据 (小端格式)
// ---------------------------
uint8_t BMP280_ReadCalibration(void)
{
    uint8_t buf[24];
    if (!BMP280_ReadRegs(BMP280_CALIB_START, buf, 24)) return 0;

    calib.dig_T1 = (uint16_t)(buf[1] << 8 | buf[0]);
    calib.dig_T2 = (int16_t)(buf[3] << 8 | buf[2]);
    calib.dig_T3 = (int16_t)(buf[5] << 8 | buf[4]);
    calib.dig_P1 = (uint16_t)(buf[7] << 8 | buf[6]);
    calib.dig_P2 = (int16_t)(buf[9] << 8 | buf[8]);
    calib.dig_P3 = (int16_t)(buf[11] << 8 | buf[10]);
    calib.dig_P4 = (int16_t)(buf[13] << 8 | buf[12]);
    calib.dig_P5 = (int16_t)(buf[15] << 8 | buf[14]);
    calib.dig_P6 = (int16_t)(buf[17] << 8 | buf[16]);
    calib.dig_P7 = (int16_t)(buf[19] << 8 | buf[18]);
    calib.dig_P8 = (int16_t)(buf[21] << 8 | buf[20]);
    calib.dig_P9 = (int16_t)(buf[23] << 8 | buf[22]);

    return 1;
}

// ---------------------------
//  软件复位
// ---------------------------
uint8_t BMP280_SoftReset(void)
{
    if (!BMP280_WriteReg8(BMP280_REG_RESET, 0xB6)) return 0;
    HAL_Delay(100);  // 等待复位完成
    return 1;
}

// ---------------------------
//  检查芯片ID (应为0x58)
// ---------------------------
uint8_t BMP280_CheckChipID(void)
{
    uint8_t id = 0;
    if (!BMP280_ReadReg8(BMP280_REG_ID, &id)) return 0;
    return (id == 0x58);
}

// ---------------------------
//  设置工作模式与滤波
// ---------------------------
uint8_t BMP280_SetMode(uint8_t mode, uint8_t osrs_t, uint8_t osrs_p, uint8_t filter)
{
    // 配置寄存器 (CONFIG)
    uint8_t config = (filter << 2);   // 滤波器配置
    if (!BMP280_WriteReg8(BMP280_REG_CONFIG, config)) return 0;

    // 控制测量寄存器 (CTRL_MEAS)
    uint8_t ctrl_meas = (osrs_t << 5) | (osrs_p << 2) | mode;
    if (!BMP280_WriteReg8(BMP280_REG_CTRL_MEAS, ctrl_meas)) return 0;

    return 1;
}

// ---------------------------
//  读取原始温度ADC值 (20bit)
// ---------------------------
static uint32_t BMP280_ReadRawTemp(void)
{
    uint8_t data[3];
    if (!BMP280_ReadRegs(BMP280_REG_TEMP_MSB, data, 3)) return 0;
    return ((uint32_t)data[0] << 12) | ((uint32_t)data[1] << 4) | ((uint32_t)data[2] >> 4);
}

// ---------------------------
//  读取原始压力ADC值 (20bit)
// ---------------------------
static uint32_t BMP280_ReadRawPressure(void)
{
    uint8_t data[3];
    if (!BMP280_ReadRegs(BMP280_REG_PRESS_MSB, data, 3)) return 0;
    return ((uint32_t)data[0] << 12) | ((uint32_t)data[1] << 4) | ((uint32_t)data[2] >> 4);
}

// ---------------------------
//  计算补偿后温度
// ---------------------------
static float BMP280_CompensateTemp(int32_t adc_T)
{
    int32_t var1 = ((((adc_T >> 3) - ((int32_t)calib.dig_T1 << 1))) *
                    ((int32_t)calib.dig_T2)) >> 11;
    int32_t var2 = (((((adc_T >> 4) - ((int32_t)calib.dig_T1)) *
                      ((adc_T >> 4) - ((int32_t)calib.dig_T1))) >> 12) *
                    ((int32_t)calib.dig_T3)) >> 14;
    t_fine = var1 + var2;
    float T = (t_fine * 5 + 128) >> 8;
    return T / 100.0f;
}

// ---------------------------
//  计算补偿后压力
// ---------------------------
static float BMP280_CompensatePressure(int32_t adc_P)
{
    int64_t var1, var2, p;
    var1 = ((int64_t)t_fine) - 128000;
    var2 = var1 * var1 * (int64_t)calib.dig_P6;
    var2 = var2 + ((var1 * (int64_t)calib.dig_P5) << 17);
    var2 = var2 + (((int64_t)calib.dig_P4) << 35);
    var1 = ((var1 * var1 * (int64_t)calib.dig_P3) >> 8) +
           ((var1 * (int64_t)calib.dig_P2) << 12);
    var1 = (((((int64_t)1) << 47) + var1)) * ((int64_t)calib.dig_P1) >> 33;

    if (var1 == 0) return 0.0f;  // 防止除零错误

    p = 1048576 - adc_P;
    p = (((p << 31) - var2) * 3125) / var1;
    var1 = (((int64_t)calib.dig_P9) * (p >> 13) * (p >> 13)) >> 25;
    var2 = (((int64_t)calib.dig_P8) * p) >> 19;
    p = ((p + var1 + var2) >> 8) + (((int64_t)calib.dig_P7) << 4);
    return (float)p / 256.0f;
}

// ---------------------------
//  读取温度与压力
// ---------------------------
uint8_t BMP280_ReadData(BMP280_Result_t *result)
{
    uint32_t raw_temp = BMP280_ReadRawTemp();
    if (raw_temp == 0) return 0;

    uint32_t raw_press = BMP280_ReadRawPressure();
    if (raw_press == 0) return 0;

    result->temperature = BMP280_CompensateTemp((int32_t)raw_temp);
    result->pressure    = BMP280_CompensatePressure((int32_t)raw_press);

    return 1;
}

// ---------------------------
//  传感器初始化
// ---------------------------
uint8_t BMP280_Init(void)
{
    // 1. 软件复位
    if (!BMP280_SoftReset()) return 0;

    // 2. 读取校准数据
    if (!BMP280_ReadCalibration()) return 0;

    // 3. 设置模式: NORMAL, 温度过采样1x, 压力过采样1x, 滤波器关闭
    //    可根据需要调整过采样与滤波系数
    if (!BMP280_SetMode(BMP280_MODE_NORMAL,
                        BMP280_OSRS_1X,
                        BMP280_OSRS_1X,
                        BMP280_FILTER_OFF)) return 0;

    // 4. 可选：检查芯片ID确认通信
    // if (!BMP280_CheckChipID()) return 0;

    return 1;
}

