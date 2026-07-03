#ifndef __BH1750_H
#define __BH1750_H

#include "main.h"

// 7位器件地址 (ADDR=GND)
#define BH1750_ADDR         0x23

// 命令
#define BH1750_POWER_DOWN   0x00
#define BH1750_POWER_ON     0x01
#define BH1750_RESET        0x07

// 测量模式
#define BH1750_CONT_H_RES_MODE    0x10  // 连续高分辨率1lx (120ms)
#define BH1750_CONT_H_RES_MODE2   0x11  // 连续高分辨率0.5lx (120ms)
#define BH1750_CONT_L_RES_MODE    0x13  // 连续低分辨率4lx (16ms)
#define BH1750_ONE_H_RES_MODE     0x20  // 一次高分辨率1lx
#define BH1750_ONE_H_RES_MODE2    0x21  // 一次高分辨率0.5lx
#define BH1750_ONE_L_RES_MODE     0x23  // 一次低分辨率4lx

uint8_t BH1750_Init(void);
uint8_t BH1750_ReadLight(float *lux);
uint8_t BH1750_SetMode(uint8_t mode);

#endif



