#include "utf8_gb2312.h"

/* Generated sorted Unicode→GB2312 lookup table */
#include "unicode_gb2312_table.inc"

/* ─── UTF-8 Decoder ────────────────────────────────────────────
   UTF-8 encoding:
   1-byte: 0xxxxxxx                          → U+0000..U+007F
   2-byte: 110xxxxx 10xxxxxx                 → U+0080..U+07FF
   3-byte: 1110xxxx 10xxxxxx 10xxxxxx        → U+0800..U+FFFF
   4-byte: 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx → U+10000..U+10FFFF
*/

uint8_t UTF8_Decode(const uint8_t *utf8, uint16_t *unicode)
{
    uint8_t c = utf8[0];

    if (c < 0x80) {
        *unicode = c;
        return 1;
    }

    if ((c & 0xE0) == 0xC0) {
        /* 2-byte sequence */
        if ((utf8[1] & 0xC0) != 0x80) return 0;
        *unicode = ((uint16_t)(c & 0x1F) << 6) | (utf8[1] & 0x3F);
        return 2;
    }

    if ((c & 0xF0) == 0xE0) {
        /* 3-byte sequence (Chinese characters are here) */
        if ((utf8[1] & 0xC0) != 0x80) return 0;
        if ((utf8[2] & 0xC0) != 0x80) return 0;
        *unicode = ((uint16_t)(c & 0x0F) << 12)
                 | ((uint16_t)(utf8[1] & 0x3F) << 6)
                 | (utf8[2] & 0x3F);
        return 3;
    }

    if ((c & 0xF8) == 0xF0) {
        /* 4-byte sequence (beyond BMP, rare) */
        if ((utf8[1] & 0xC0) != 0x80) return 0;
        if ((utf8[2] & 0xC0) != 0x80) return 0;
        if ((utf8[3] & 0xC0) != 0x80) return 0;
        *unicode = 0xFFFD;  /* beyond BMP, use replacement */
        return 4;
    }

    return 0;  /* invalid */
}

/* ─── Unicode → GB2312 binary search ─────────────────────────── */

uint16_t UnicodeToGB2312Index(uint16_t unicode)
{
    uint16_t lo = 0;
    uint16_t hi = UNICODE_TABLE_SIZE - 1;

    while (lo <= hi) {
        uint16_t mid = lo + (hi - lo) / 2;
        uint16_t val = unicode_sorted[mid];

        if (val == unicode) {
            return gb2312_index_sorted[mid];
        }
        if (val < unicode) {
            lo = mid + 1;
        } else {
            if (mid == 0) break;
            hi = mid - 1;
        }
    }

    return 0xFFFF;
}

uint8_t UnicodeToGB2312(uint16_t unicode, uint8_t *gb_h, uint8_t *gb_l)
{
    uint16_t index = UnicodeToGB2312Index(unicode);

    if (index == 0xFFFF) {
        *gb_h = 0;
        *gb_l = 0;
        return 1;
    }

    *gb_h = 0xB0 + (uint8_t)(index / 94);
    *gb_l = 0xA1 + (uint8_t)(index % 94);
    return 0;
}
