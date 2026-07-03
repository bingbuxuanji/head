#include "./OLED/oled.h"
#include "./OLED/oledfont.h"
#include "i2c.h"
// OLED I2C 设备地址 (7位地址0x3C)
#define OLED_ADDR        0x78  // 8位写地址（0x3C<<1）
#define OLED_CMD         0x00  // 控制字节：后续是命令
#define OLED_DATA        0x40  // 控制字节：后续是数据

// 屏幕尺寸 (128x32)
static uint8_t OLED_GRAM[128][4]; // 显存数组 [列][页]

// 向OLED发送一个命令
static void OLED_Write_Cmd(uint8_t cmd) {
    HAL_I2C_Mem_Write(&hi2c2, OLED_ADDR, OLED_CMD, I2C_MEMADD_SIZE_8BIT, &cmd, 1, 100);
}

// 向OLED发送一个数据
static void OLED_Write_Data(uint8_t data) {
    HAL_I2C_Mem_Write(&hi2c2, OLED_ADDR, OLED_DATA, I2C_MEMADD_SIZE_8BIT, &data, 1, 100);
}

// 设置光标位置 (x: 0-127, y: 0-3)
void OLED_Set_Pos(uint8_t x, uint8_t y) {
    OLED_Write_Cmd(0xB0 + y);          // 设置页地址 (0xB0~0xB7)
    OLED_Write_Cmd(((x & 0xF0) >> 4) | 0x10); // 设置列地址高位 (0x10~0x17)
    OLED_Write_Cmd(x & 0x0F);          // 设置列地址低位
}

// 更新显存到屏幕
void OLED_Refresh(void) {
    uint8_t i, j;
    for (i = 0; i < 4; i++) {
        OLED_Set_Pos(0, i);
        for (j = 0; j < 128; j++) {
            OLED_Write_Data(OLED_GRAM[j][i]);
        }
    }
}

// 清屏 (填充0)
void OLED_Clear(void) {
    memset(OLED_GRAM, 0, sizeof(OLED_GRAM));
    OLED_Refresh();
}

// 全屏点亮 (填充0xFF)
void OLED_Allfill(void) {
    memset(OLED_GRAM, 0xFF, sizeof(OLED_GRAM));
    OLED_Refresh();
}

// 画点 (x: 0-127, y: 0-31)
void OLED_Draw_Point(uint8_t x, uint8_t y, uint8_t color) {
    if (x > 127 || y > 31) return;
    uint8_t page = y / 8;      // 计算所在页 (0-3)
    uint8_t bit = y % 8;       // 计算页内位位置
    if (color) {
        OLED_GRAM[x][page] |=  (1 << bit);
    } else {
        OLED_GRAM[x][page] &= ~(1 << bit);
    }
}

// 显示一个字符 (单色点阵)
void OLED_Show_Char(uint8_t x, uint8_t y, uint8_t chr, uint8_t size) {
    uint8_t c = chr - ' ';
    uint8_t i, j;
    uint8_t temp;

    if (size == 16) { // 16x8点阵 ASCII
        for (i = 0; i < 16; i++) {
            temp = asc2_1608[c][i];
            for (j = 0; j < 8; j++) {
                if (temp & 0x80) OLED_Draw_Point(x + j, y + i, 1);
                temp <<= 1;
            }
        }
    } else { // 8x6点阵 ASCII
        for (i = 0; i < 8; i++) {
            temp = asc2_1206[c][i];
            for (j = 0; j < 6; j++) {
                if (temp & 0x80) OLED_Draw_Point(x + j, y + i, 1);
                temp <<= 1;
            }
        }
    }
}

// 显示字符串
void OLED_Show_Str(uint8_t x, uint8_t y, char *str, uint8_t size) {
	if (x > 127 || y > 31) return;
    uint8_t width = (size == 16) ? 8 : 6;   // 字体实际宽度
    while (*str) {
        OLED_Show_Char(x, y, *str, size);
        x += width;
        str++;
        if (x > (128 - width)) {  // 换行处理
            x = 0;
            y += size;
        }
    }
    OLED_Refresh();
}

// 显示整数
void OLED_Show_Num(uint8_t x, uint8_t y, uint32_t num, uint8_t len, uint8_t size) {
    char buf[10];
    sprintf(buf, "%d", num);
    OLED_Show_Str(x, y, buf, size);
}

// 显示浮点数
void OLED_Show_Float(uint8_t x, uint8_t y, float num, uint8_t accuracy, uint8_t size) {
    char buf[20];
    sprintf(buf, "%.*f", accuracy, num);
    OLED_Show_Str(x, y, buf, size);
}

// 显示图片 (取模方式: 阴码, 逆向, 列行式)
void OLED_Show_Pic(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1, const uint8_t *pic) {
    uint32_t index = 0;
    for (uint8_t y = y0; y < y1; y++) {
        for (uint8_t x = x0; x < x1; x++) {
            OLED_Draw_Point(x, y, pic[index] ? 1 : 0);
            index++;
        }
    }
}

// OLED初始化
void OLED_Init(void) {
    HAL_Delay(200);  // 等待OLED上电稳定

    OLED_Write_Cmd(0xAE); // 关闭显示
    OLED_Write_Cmd(0xD5); // 设置时钟分频因子,震荡频率
    OLED_Write_Cmd(0x80); // [3:0]分频, [7:4]震荡频率
    OLED_Write_Cmd(0xA8); // 设置驱动路数
    OLED_Write_Cmd(0x1F); // 1/32驱动 (0x1F对应32行)
    OLED_Write_Cmd(0xD3); // 设置显示偏移
    OLED_Write_Cmd(0x00); // 偏移0
    OLED_Write_Cmd(0x40); // 设置显示开始行 [5:0]行数
    OLED_Write_Cmd(0x8D); // 电荷泵设置
    OLED_Write_Cmd(0x14); // 开启电荷泵
    OLED_Write_Cmd(0x20); // 设置内存地址模式
    OLED_Write_Cmd(0x02); // [00:水平, 01:垂直, 02:页地址]
    OLED_Write_Cmd(0xA1); // 段重定义设置, 列地址0映射到SEG0
    OLED_Write_Cmd(0xC8); // 设置COM扫描方向
    OLED_Write_Cmd(0xDA); // 设置COM硬件引脚配置
    OLED_Write_Cmd(0x02); // 128x32模式配置
    OLED_Write_Cmd(0x81); // 对比度设置
    OLED_Write_Cmd(0xCF); // 对比度值 (0x00~0xFF)
    OLED_Write_Cmd(0xD9); // 设置预充电周期
    OLED_Write_Cmd(0xF1); // [3:0]PHASE1, [7:4]PHASE2
    OLED_Write_Cmd(0xDB); // 设置VCOMH 电压倍率
    OLED_Write_Cmd(0x40); // 0x20,0x30,0x40
    OLED_Write_Cmd(0xA4); // 全局显示开启; 0xA4:输出跟随RAM, 0xA5:忽略RAM
    OLED_Write_Cmd(0xA6); // 设置显示模式; 0xA6:正常, 0xA7:反色显示
    OLED_Write_Cmd(0xAF); // 开启显示

    OLED_Clear(); // 清屏
}

