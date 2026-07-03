/**
 * @file    utf8_font.h
 * @brief   UTF-8 Font System — decode UTF-8 text and render 16x16 Chinese
 *          glyphs from W25Q128 external SPI flash onto 128x32 OLED.
 *
 * W25Q128 font binary layout (little-endian, starting at 0x00000000):
 *   Offset       Size   Field
 *   0x00000000   4      Magic: 0x464E5446 ("FTNF")
 *   0x00000004   4      Total character count (N)
 *   0x00000008   4      Glyph size in bytes (32)
 *   0x0000000C   4      Reserved
 *   0x00000010   N*4    Index table: sorted uint32 Unicode code points
 *   0xXXXXXXXX   N*32   Glyph bitmaps: 16x16 dots, row-major, MSB-left
 */

#ifndef __UTF8_FONT_H__
#define __UTF8_FONT_H__

#include <stdint.h>

/* ── Font binary constants ─────────────────────────────────────────────── */

#define UTF8_FONT_MAGIC          0x464E5446U  /* "FTNF" */
#define UTF8_FONT_HEADER_SIZE    16U
#define UTF8_FONT_GLYPH_SIZE     32U          /* 16x16 bits = 32 bytes */
#define UTF8_FONT_IDX_ENTRY      4U           /* uint32 per code point */

/* ── W25Q128 storage layout ────────────────────────────────────────────── */

#define UTF8_FONT_BASE_ADDR      0x00000000U  /* font starts at W25Q128 sector 0 */

/* ── API ───────────────────────────────────────────────────────────────── */

/**
 * @brief  Enter UART font download mode (protocol v2).
 *
 * Protocol:
 *   PC → MCU:  "FONT_DL:<total_bytes>\n"
 *   MCU:       erases W25Q128 sectors, responds "READY\n"
 *   MCU → PC:  "GET:<seq>\n"                  (pulls each packet)
 *   PC → MCU:  [STX][seq:2B LE][len:2B LE][data:N][CRC16:2B LE]
 *   MCU → PC:  "OK:<seq>\n"  or  "ERR:<seq>:<reason>\n"
 *   MCU → PC:  "SUCCESS:<char_count>\n"       (all done)
 *
 * Use with: python send_font.py COMx utf8_font.bin
 */
void UTF8_FONT_DownloadMode(void);

/**
 * @brief  Decode a UTF-8 byte sequence into a Unicode code point.
 * @param  utf8:  pointer to UTF-8 byte sequence (advanced past decoded bytes)
 * @param  unicode: output Unicode code point
 * @retval Number of bytes consumed (1~4), or 0 on error
 */
uint8_t UTF8_Decode(const uint8_t **utf8, uint32_t *unicode);

/**
 * @brief  Look up a Unicode code point in the W25Q128 font index.
 * @param  unicode:  Unicode code point
 * @param  glyph_buf: output buffer for 32-byte glyph bitmap (16x16)
 * @retval 0 if found, 1 if not in font
 */
uint8_t UTF8_FONT_Lookup(uint32_t unicode, uint8_t glyph_buf[UTF8_FONT_GLYPH_SIZE]);

/**
 * @brief  Diagnostic: verify font header and print character count.
 *         Call once after SPI_FLASH_Init() to confirm font binary integrity.
 */
void UTF8_FONT_Diag(void);

/**
 * @brief  Display a UTF-8 string on OLED.
 * @param  x, y: starting pixel position (x: 0~127, y: 0~31)
 * @param  str:  UTF-8 encoded null-terminated string
 * @param  size: font height (use 16 for 16x16 / 16x8 glyphs)
 *
 * ASCII characters (unicode < 0x80) are rendered at 8 px wide × 16 px high.
 * Chinese characters are rendered at 16 px wide × 16 px high.
 * Automatic line-wrapping is performed.  The display is refreshed at the end.
 */
void OLED_Show_UTF8(uint8_t x, uint8_t y, const char *str, uint8_t size);

#endif /* __UTF8_FONT_H__ */
