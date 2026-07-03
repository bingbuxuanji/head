#ifndef OLED_H
#define OLED_H

#include "main.h"
#include <string.h>
#include <stdio.h>

#define OLED_WIDTH  128
#define OLED_HEIGHT 32

void OLED_Init(void);
void OLED_Refresh(void);
void OLED_Clear(void);
void OLED_Allfill(void);
void OLED_Draw_Point(uint8_t x, uint8_t y, uint8_t color);
void OLED_Show_Char(uint8_t x, uint8_t y, uint8_t chr, uint8_t size);
void OLED_Show_Str(uint8_t x, uint8_t y, char *str, uint8_t size);
void OLED_Show_Num(uint8_t x, uint8_t y, uint32_t num, uint8_t len, uint8_t size);
void OLED_Show_Float(uint8_t x, uint8_t y, float num, uint8_t accuracy, uint8_t size);
void OLED_Show_Pic(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1, const uint8_t *pic);
void OLED_Set_Pos(uint8_t x, uint8_t y);


#endif
