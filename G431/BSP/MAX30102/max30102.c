// max30102.c
#include "./MAX30102/max30102.h"
#include "i2c.h"      // 包含 hi2c2 的定义
#include <stdio.h>    // 调试用

extern I2C_HandleTypeDef hi2c2;

/* 内部调试打印宏，方便关闭 */
#define DEBUG_PRINT 1
#if DEBUG_PRINT
#define DEBUG(fmt, ...) printf("[MAX30102] " fmt, ##__VA_ARGS__)
#else
#define DEBUG(fmt, ...)
#endif

/* 写寄存器 */
uint8_t MAX30102_WriteReg(uint8_t reg, uint8_t data) {
    if (HAL_I2C_Mem_Write(&hi2c2, MAX30102_I2C_ADDR << 1, reg,
                          I2C_MEMADD_SIZE_8BIT, &data, 1, 100) != HAL_OK) {
        DEBUG("WriteReg error: reg=0x%02X\r\n", reg);
        return 1;
    }
    return 0;
}

/* 读寄存器 */
uint8_t MAX30102_ReadReg(uint8_t reg, uint8_t *data) {
    if (HAL_I2C_Mem_Read(&hi2c2, MAX30102_I2C_ADDR << 1, reg,
                         I2C_MEMADD_SIZE_8BIT, data, 1, 100) != HAL_OK) {
        DEBUG("ReadReg error: reg=0x%02X\r\n", reg);
        return 1;
    }
    return 0;
}

/* 读多个寄存器 */
static uint8_t MAX30102_ReadRegs(uint8_t reg, uint8_t *data, uint16_t len) {
    if (HAL_I2C_Mem_Read(&hi2c2, MAX30102_I2C_ADDR << 1, reg,
                         I2C_MEMADD_SIZE_8BIT, data, len, 100) != HAL_OK) {
        DEBUG("ReadRegs error: reg=0x%02X, len=%d\r\n", reg, len);
        return 1;
    }
    return 0;
}

/* 软件复位 */
void MAX30102_SoftReset(void) {
    DEBUG("Soft reset...\r\n");
    MAX30102_WriteReg(MAX30102_REG_MODE_CONFIG, 0x40);
    HAL_Delay(100);
}

/* 读取器件ID */
uint8_t MAX30102_ReadID(uint8_t *id) {
    return MAX30102_ReadReg(MAX30102_REG_PART_ID, id);
}

/* 设置LED电流 (0~0xFF 对应 0~50mA) */
void MAX30102_SetLEDCurrent(uint8_t red_ma, uint8_t ir_ma) {
    MAX30102_WriteReg(MAX30102_REG_LED1_PA, red_ma);
    MAX30102_WriteReg(MAX30102_REG_LED2_PA, ir_ma);
}

/* 初始化传感器 — 寄存器值参照 Maxim 官方参考代码 */
uint8_t MAX30102_Init(void) {
    uint8_t id;
    DEBUG("Init start...\r\n");

    // 1. 软复位
    MAX30102_SoftReset();

    // 2. 检查器件ID
    if (MAX30102_ReadID(&id) != 0) {
        DEBUG("Read ID failed\r\n");
        return 1;
    }
    if (id != 0x15) {
        DEBUG("Wrong ID: 0x%02X (expected 0x15)\r\n", id);
        return 2;
    }
    DEBUG("Part ID: 0x%02X\r\n", id);

    // 3. 中断使能: FIFO almost full + New FIFO data ready (参照官方配置 0xC0)
    if (MAX30102_WriteReg(MAX30102_REG_INT_EN1, 0xC0)) return 3;
    if (MAX30102_WriteReg(MAX30102_REG_INT_EN2, 0x00)) return 3;

    // 4. 清空FIFO指针与溢出计数器 (参照官方初始化顺序)
    if (MAX30102_WriteReg(MAX30102_REG_FIFO_WR_PTR, 0x00)) return 3;
    if (MAX30102_WriteReg(MAX30102_REG_OVF_COUNTER, 0x00)) return 3;
    if (MAX30102_WriteReg(MAX30102_REG_FIFO_RD_PTR, 0x00)) return 3;

    // 5. FIFO配置: sample avg=1, fifo rollover=disable, fifo almost full=17
    //    对应 0x0F — 参照官方配置
    if (MAX30102_WriteReg(MAX30102_REG_FIFO_CONFIG, 0x0F)) return 3;

    // 6. 模式配置: 0x03 = SpO2 模式 (同时点亮 RED + IR)
    //    0x02 = 仅Red, 0x07 = Multi-LED 模式
    if (MAX30102_WriteReg(MAX30102_REG_MODE_CONFIG, 0x03)) return 3;

    // 7. SpO2配置: ADC量程 4096nA, 采样率 100Hz, LED脉冲宽度 400us
    //    0x27 = 0b00100111 — 参照官方配置 (保证信号质量和功耗平衡)
    if (MAX30102_WriteReg(MAX30102_REG_SPO2_CONFIG, 0x27)) return 3;

    // 8. LED电流设置: 0x24 ≈ 7mA (参照官方推荐值，避免过亮烧皮肤)
    if (MAX30102_WriteReg(MAX30102_REG_LED1_PA, 0x24)) return 3;   // RED ~7mA
    if (MAX30102_WriteReg(MAX30102_REG_LED2_PA, 0x24)) return 3;   // IR  ~7mA
    if (MAX30102_WriteReg(MAX30102_REG_PILOT_PA, 0x7F)) return 3;  // Pilot LED ~25mA

    HAL_Delay(100);
    DEBUG("Init success\r\n");
    return 0;
}

/* 读取FIFO数据
 * 注意: MAX30102 从 FIFO_DATA 读取时会自动递增内部读指针，
 * 不要手动写 FIFO_RD_PTR，否则会破坏 FIFO 状态机导致只读一次!
 */
uint8_t MAX30102_ReadFIFO(MAX30102_Data_t *data, uint8_t max_samples, uint8_t *samples_read) {
    uint8_t rd_ptr, wr_ptr;
    uint8_t samples_available;
    uint8_t fifo_buf[192];   // max 32 samples * 6 bytes

    // 获取读写指针
    if (MAX30102_ReadReg(MAX30102_REG_FIFO_RD_PTR, &rd_ptr) ||
        MAX30102_ReadReg(MAX30102_REG_FIFO_WR_PTR, &wr_ptr)) {
        return 1;
    }

    // 计算 FIFO 中可读取的样本数 (考虑环形缓冲)
    if (wr_ptr >= rd_ptr)
        samples_available = wr_ptr - rd_ptr;
    else
        samples_available = 32 - rd_ptr + wr_ptr;

    if (samples_available == 0) {
        if (samples_read) *samples_read = 0;
        return 2;   // FIFO empty
    }
    if (samples_available > max_samples)
        samples_available = max_samples;

    // 批量读取 FIFO_DATA (硬件会自动递增 rd_ptr)
    if (MAX30102_ReadRegs(MAX30102_REG_FIFO_DATA, fifo_buf, samples_available * 6)) {
        return 3;
    }

    // 解析数据: 每 6 字节 = 1 样本 (RED[17:0] + IR[17:0], 各占 3 字节)
    for (uint8_t i = 0; i < samples_available; i++) {
        data[i].red = ((uint32_t)fifo_buf[i*6] << 16) |
                      ((uint32_t)fifo_buf[i*6+1] << 8) |
                      fifo_buf[i*6+2];
        data[i].ir  = ((uint32_t)fifo_buf[i*6+3] << 16) |
                      ((uint32_t)fifo_buf[i*6+4] << 8) |
                      fifo_buf[i*6+5];
        data[i].red &= 0x3FFFF;  // 仅低 18 位有效
        data[i].ir  &= 0x3FFFF;
    }

    // 不手动写 FIFO_RD_PTR — 硬件自动处理
    if (samples_read) *samples_read = samples_available;
    return 0;
}

