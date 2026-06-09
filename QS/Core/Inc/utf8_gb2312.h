#ifndef __UTF8_GB2312_H__
#define __UTF8_GB2312_H__

#include "stdint.h"

/* Decode a UTF-8 sequence and return the Unicode code point.
   Returns the number of bytes consumed (1-4), or 0 on error.
   *unicode = decoded code point. */
uint8_t UTF8_Decode(const uint8_t *utf8, uint16_t *unicode);

/* Convert a Unicode code point to GB2312 index (0~6767).
   Returns 0xFFFF if the character is not in GB2312. */
uint16_t UnicodeToGB2312Index(uint16_t unicode);

/* Convert a Unicode code point to GB2312 byte pair (hb, lb).
   Returns 0 if successful, 1 if character not in GB2312. */
uint8_t UnicodeToGB2312(uint16_t unicode, uint8_t *gb_h, uint8_t *gb_l);

/* Check if a byte is the start of a UTF-8 multi-byte sequence (>= 0x80) */
#define UTF8_IS_LEADING(c)  (((uint8_t)(c)) >= 0xC0)

/* Check if a byte is a GB2312 Chinese high byte (0xB0~0xF7) */
#define GB2312_IS_CHINESE_H(c)  (((uint8_t)(c)) >= 0xB0 && ((uint8_t)(c)) <= 0xF7)

#endif /* __UTF8_GB2312_H__ */
