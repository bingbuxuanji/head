#ifndef OLED_OLEDFONT_H_
#define OLED_OLEDFONT_H_

#include "stdio.h"
#include "string.h"
#include "stdint.h"
#include "headfile.h"

// ==============================================
// GB2312 16*16 �ֿ����ã�W25Q16 ר�ã�
// ==============================================
// �ֿ����ַ��256���� * 4096�ֽ� = 0x100000��1MBλ�ã�
#define GB2312_H1616_BASE_ADDR    (256UL * 4096UL)  

// ÿ��16*16���̶ֹ�ռ��32�ֽ�
#define GB2312_FONT_SIZE          32UL              

// GB2312�ܺ�������72�� �� 94��/�� = 6768����������Χ 0~6767
#define GB2312_MAX_CHAR_INDEX     6767UL 


uint16_t GB2312_CodeToIndex(uint8_t gb_h, uint8_t gb_l);
uint8_t GB2312_GetFontByIndex(uint16_t no, uint8_t *font_buf);
uint8_t GB2312_IsFontReady(void);

extern const unsigned char F6x8[][6];
extern const unsigned char F8X16[];
extern const unsigned char Hzk[][32];
extern unsigned char BMP1[];
//extern unsigned char BMP2[].........
#endif /* OLED_OLEDFONT_H_ */

