/**
 * @file    utf8_font.c
 * @brief   UTF-8 Font System — decode UTF-8, binary-search W25Q128 font
 *          index, render 16x16 glyphs on 128x32 OLED.
 */

#include "./utf8_font/utf8_font.h"
#include "./W25Q128/bsp_spi_flash.h"
#include "./OLED/oled.h"
#include "usart.h"
#include <string.h>
#include <stdio.h>

/* ── Helper: read a little-endian uint32 from W25Q128 ─────────────────── */

static uint32_t read_uint32_le(uint32_t addr)
{
    uint8_t buf[4];
    SPI_FLASH_BufferRead(buf, addr, 4);
    return buf[0] | ((uint32_t)buf[1] << 8)
         | ((uint32_t)buf[2] << 16) | ((uint32_t)buf[3] << 24);
}

/* ── UART Font Download Mode ──────────────────────────────────────────── */

#define W25Q_SECTOR_SIZE        4096U
#define PKT_STX                 0xAA
#define PKT_HDR_SIZE            5U
#define PKT_CRC_SIZE            2U
#define PKT_MAX_DATA            1024U
#define PKT_MAX_RETRIES         3U

/* CRC-16/MODBUS (poly 0x8005, reflected) */
static uint16_t crc16_modbus(const uint8_t *data, uint16_t len)
{
    uint16_t crc = 0xFFFF;
    while (len--)
    {
        crc ^= *data++;
        for (uint8_t i = 0; i < 8; i++)
            crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : crc >> 1;
    }
    return crc;
}

void UTF8_FONT_DownloadMode(void)
{
    uint32_t total_bytes = 0;
    uint32_t flash_addr  = UTF8_FONT_BASE_ADDR;
    uint32_t received     = 0;
    uint16_t expected_seq = 0;
    HAL_StatusTypeDef st;
    uint8_t  rx_byte;

    printf("\r\n=== FONT DOWNLOAD MODE (protocol v2) ===\r\n");
    printf("Run: python send_font.py COMx utf8_font.bin\r\n");
    printf("Waiting for FONT_DL command...\r\n");

    /* ── Phase 1: Handshake ─────────────────────────────────────────── */
    char cmd_buf[64];
    uint8_t cmd_pos = 0;

    while (cmd_pos < sizeof(cmd_buf) - 1)
    {
        st = HAL_UART_Receive(&huart2, &rx_byte, 1, 100);
        if (st == HAL_OK)
        {
            cmd_buf[cmd_pos++] = rx_byte;
            if (rx_byte == '\n') break;
        }
    }
    cmd_buf[cmd_pos] = '\0';

    if (sscanf(cmd_buf, "FONT_DL:%lu", &total_bytes) != 1 || total_bytes == 0)
    {
        printf("Bad command: %s\r\n", cmd_buf);
        return;
    }

    printf("Request: %lu bytes (%.1f KB)\r\n", total_bytes, total_bytes / 1024.0);

    /* Erase W25Q128 sectors covering the font area */
    {
        uint32_t end_addr  = UTF8_FONT_BASE_ADDR + total_bytes;
        uint32_t sec_start = UTF8_FONT_BASE_ADDR / W25Q_SECTOR_SIZE;
        uint32_t sec_end   = (end_addr + W25Q_SECTOR_SIZE - 1U) / W25Q_SECTOR_SIZE;
        printf("Erasing sectors %lu~%lu...\r\n", sec_start, sec_end - 1);
        for (uint32_t s = sec_start; s < sec_end; s++)
            SPI_FLASH_SectorErase(s * W25Q_SECTOR_SIZE);
    }

    printf("READY\r\n");

    /* ── Phase 2: Packet transfer (MCU pulls) ────────────────────────── */
    while (received < total_bytes)
    {
        /* Request next packet */
        {
            char req[16];
            int n = sprintf(req, "GET:%u\r\n", expected_seq);
            HAL_UART_Transmit(&huart2, (uint8_t *)req, n, 1000);
        }

        /* Wait for packet with retry */
        uint8_t  retry;
        uint8_t  pkt_ok = 0;
        uint16_t pkt_seq, pkt_len;
        uint8_t  pkt_buf[PKT_MAX_DATA + PKT_CRC_SIZE];

        for (retry = 0; retry < PKT_MAX_RETRIES; retry++)
        {
            /* ── Read STX ──────────────────────────────────────────── */
            uint16_t timeout;
            for (timeout = 0; timeout < 5000; timeout++)
            {
                st = HAL_UART_Receive(&huart2, &rx_byte, 1, 1);
                if (st == HAL_OK && rx_byte == PKT_STX) break;
            }
            if (timeout >= 5000)
            {
                printf("ERR:%u:TMO\r\n", expected_seq);
                continue;
            }

            /* ── Read header: seq(2) + len(2) ──────────────────────── */
            uint8_t hdr[4];
            if (HAL_UART_Receive(&huart2, hdr, 4, 200) != HAL_OK)
            {
                printf("ERR:%u:HDR\r\n", expected_seq);
                continue;
            }

            pkt_seq = hdr[0] | ((uint16_t)hdr[1] << 8);
            pkt_len = hdr[2] | ((uint16_t)hdr[3] << 8);

            if (pkt_len > PKT_MAX_DATA || pkt_len == 0)
            {
                printf("ERR:%u:LEN:%u\r\n", pkt_seq, pkt_len);
                continue;
            }

            /* ── Read payload + CRC ────────────────────────────────── */
            uint16_t to_read = pkt_len + PKT_CRC_SIZE;
            uint16_t pos = 0;

            while (pos < to_read)
            {
                st = HAL_UART_Receive(&huart2, &rx_byte, 1, 200);
                if (st != HAL_OK) break;
                pkt_buf[pos++] = rx_byte;
            }
            if (pos < to_read)
            {
                printf("ERR:%u:DATA:%u/%u\r\n", pkt_seq, pos, to_read);
                continue;
            }

            /* ── Verify CRC ────────────────────────────────────────── */
            uint8_t crc_buf[4 + PKT_MAX_DATA];
            crc_buf[0] = hdr[0]; crc_buf[1] = hdr[1];
            crc_buf[2] = hdr[2]; crc_buf[3] = hdr[3];
            memcpy(crc_buf + 4, pkt_buf, pkt_len);

            uint16_t crc_calc = crc16_modbus(crc_buf, 4 + pkt_len);
            uint16_t crc_recv = pkt_buf[pkt_len] | ((uint16_t)pkt_buf[pkt_len + 1] << 8);

            if (crc_calc != crc_recv)
            {
                printf("ERR:%u:CRC (calc=0x%04X recv=0x%04X)\r\n",
                       pkt_seq, crc_calc, crc_recv);
                continue;
            }

            /* ── Sequence check ────────────────────────────────────── */
            if (pkt_seq != expected_seq)
            {
                printf("ERR:%u:SEQ (expected %u)\r\n", pkt_seq, expected_seq);
                continue;
            }

            /* All checks passed */
            pkt_ok = 1;
            break;
        }

        if (!pkt_ok)
        {
            printf("FAIL: packet %u failed after %u retries\r\n",
                   expected_seq, PKT_MAX_RETRIES);
            return;
        }

        /* ── Write to flash ──────────────────────────────────────────── */
        SPI_FLASH_BufferWrite(pkt_buf, flash_addr, pkt_len);
        flash_addr += pkt_len;
        received   += pkt_len;

        printf("OK:%u\r\n", expected_seq);

        /* Progress every 32 packets */
        if ((expected_seq & 0x1F) == 0 || received >= total_bytes)
        {
            uint32_t pct = received * 100 / total_bytes;
            printf("  %lu%% (%lu/%lu KB)  seq=%u\r\n",
                   pct, received / 1024, total_bytes / 1024, expected_seq);
        }

        expected_seq++;
    }

    /* ── Phase 3: Verify ──────────────────────────────────────────────── */
    printf("\r\nTransfer complete: %lu bytes\r\n", received);

    uint32_t header[4];
    SPI_FLASH_BufferRead((uint8_t *)header, UTF8_FONT_BASE_ADDR, 16);

    if (header[0] == UTF8_FONT_MAGIC && header[1] > 0)
    {
        printf("SUCCESS:%lu\r\n", header[1]);
        printf("Font ready: %lu chars\r\n", header[1]);
    }
    else
    {
        printf("FAIL: bad magic 0x%08lX, chars=%lu\r\n", header[0], header[1]);
    }
}

/* ── UTF-8 decoder ────────────────────────────────────────────────────── */

uint8_t UTF8_Decode(const uint8_t **utf8, uint32_t *unicode)
{
    uint8_t c = **utf8;

    /* 1-byte: ASCII */
    if (c < 0x80) {
        *unicode = c;
        (*utf8)++;
        return 1;
    }

    /* 2-byte: U+0080 ~ U+07FF */
    if ((c & 0xE0) == 0xC0) {
        uint8_t c2 = (*utf8)[1];
        if ((c2 & 0xC0) != 0x80) goto err;
        *unicode = ((uint32_t)(c & 0x1F) << 6) | (c2 & 0x3F);
        (*utf8) += 2;
        return 2;
    }

    /* 3-byte: U+0800 ~ U+FFFF (Chinese characters) */
    if ((c & 0xF0) == 0xE0) {
        uint8_t c2 = (*utf8)[1], c3 = (*utf8)[2];
        if ((c2 & 0xC0) != 0x80 || (c3 & 0xC0) != 0x80) goto err;
        *unicode = ((uint32_t)(c & 0x0F) << 12)
                 | ((uint32_t)(c2 & 0x3F) << 6)
                 | (c3 & 0x3F);
        (*utf8) += 3;
        return 3;
    }

    /* 4-byte: U+10000 ~ U+10FFFF (emojis etc., fallback) */
    if ((c & 0xF8) == 0xF0) {
        uint8_t c2 = (*utf8)[1], c3 = (*utf8)[2], c4 = (*utf8)[3];
        if ((c2 & 0xC0) != 0x80 || (c3 & 0xC0) != 0x80 || (c4 & 0xC0) != 0x80) goto err;
        *unicode = ((uint32_t)(c & 0x07) << 18)
                 | ((uint32_t)(c2 & 0x3F) << 12)
                 | ((uint32_t)(c3 & 0x3F) << 6)
                 | (c4 & 0x3F);
        (*utf8) += 4;
        return 4;
    }

err:
    *unicode = 0;
    (*utf8)++;           /* skip the bad byte so the loop makes progress */
    return 0;
}

/* ── Font lookup (binary search in W25Q128) ────────────────────────────── */

uint8_t UTF8_FONT_Lookup(uint32_t unicode, uint8_t glyph_buf[UTF8_FONT_GLYPH_SIZE])
{
    /* Read master header */
    uint32_t magic = read_uint32_le(UTF8_FONT_BASE_ADDR);
    if (magic != UTF8_FONT_MAGIC)
        return 1;

    uint32_t N = read_uint32_le(UTF8_FONT_BASE_ADDR + 4);
    if (N == 0)
        return 1;

    /* Index table starts right after the 16-byte header */
    uint32_t index_base = UTF8_FONT_BASE_ADDR + UTF8_FONT_HEADER_SIZE;

    /* Quick range check against first and last code points */
    uint32_t first_cp = read_uint32_le(index_base);
    uint32_t last_cp  = read_uint32_le(index_base + (N - 1) * UTF8_FONT_IDX_ENTRY);

    if (unicode < first_cp || unicode > last_cp)
        return 1;

    /* Binary search the sorted index table */
    uint32_t lo = 0, hi = N;
    while (lo < hi) {
        uint32_t mid = (lo + hi) / 2;
        uint32_t cp  = read_uint32_le(index_base + mid * UTF8_FONT_IDX_ENTRY);

        if (cp == unicode) {
            /* Found — glyph area starts at index_base + N*4 + mid*32 */
            uint32_t glyph_addr = index_base
                                + N * UTF8_FONT_IDX_ENTRY
                                + mid * UTF8_FONT_GLYPH_SIZE;
            SPI_FLASH_BufferRead(glyph_buf, glyph_addr, UTF8_FONT_GLYPH_SIZE);
            return 0;
        } else if (cp < unicode) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }

    return 1;  /* not found */
}

/* ── Render one 16×16 glyph into OLED_GRAM ─────────────────────────────── */

static void OLED_Draw_Glyph(uint8_t x, uint8_t y,
                            const uint8_t glyph[UTF8_FONT_GLYPH_SIZE])
{
    for (uint8_t row = 0; row < 16; row++) {
        uint8_t bl = glyph[row * 2];        /* left  8 pixels of this row */
        uint8_t br = glyph[row * 2 + 1];    /* right 8 pixels of this row */

        /* Left half: columns x+0 … x+7 */
        for (uint8_t col = 0; col < 8; col++) {
            if (bl & (0x80 >> col))
                OLED_Draw_Point(x + col,     y + row, 1);
        }
        /* Right half: columns x+8 … x+15 */
        for (uint8_t col = 0; col < 8; col++) {
            if (br & (0x80 >> col))
                OLED_Draw_Point(x + col + 8, y + row, 1);
        }
    }
}

/* ── Font diagnostic ───────────────────────────────────────────────── */

void UTF8_FONT_Diag(void)
{
    uint32_t magic = read_uint32_le(UTF8_FONT_BASE_ADDR);
    uint32_t count = read_uint32_le(UTF8_FONT_BASE_ADDR + 4);

    printf("\r\n=== Font Diag ===\r\n");
    printf("Magic:   0x%08lX %s\r\n", (unsigned long)magic,
           magic == UTF8_FONT_MAGIC ? "(OK)" : "(BAD!)");
    printf("Chars:   %lu\r\n", (unsigned long)count);

    if (magic == UTF8_FONT_MAGIC && count > 0) {
        uint32_t first = read_uint32_le(UTF8_FONT_BASE_ADDR + 16);
        uint32_t last  = read_uint32_le(UTF8_FONT_BASE_ADDR + 16 + (count - 1) * 4);
        printf("Range:   U+%04lX ~ U+%04lX\r\n",
               (unsigned long)first, (unsigned long)last);
    }
    printf("=================\r\n");
}

/* ── Display a UTF-8 string on OLED ────────────────────────────────────── */

void OLED_Show_UTF8(uint8_t x, uint8_t y, const char *str, uint8_t size)
{
    if (size != 16) size = 16;  /* only 16-pixel-tall fonts for now */

    const uint8_t *p  = (const uint8_t *)str;
    uint8_t        cx = x, cy = y;
    uint8_t        glyph[UTF8_FONT_GLYPH_SIZE];

    while (*p) {
        uint32_t unicode;
        uint8_t  len = UTF8_Decode(&p, &unicode);

        if (len == 0) continue;  /* skip bad bytes */

        if (unicode < 0x80) {
            /* ── ASCII: use built-in 16×8 font ────────────────────── */
            if (cx > 127 - 8) {        /* wrap before drawing */
                cx = 0;
                cy += 16;
            }
            if (cy > 31) break;

            OLED_Show_Char(cx, cy, (uint8_t)unicode, 16);
            cx += 8;
        } else {
            /* ── Chinese / wide character: look up in W25Q128 ─────── */
            if (cx > 127 - 16) {       /* wrap before drawing */
                cx = 0;
                cy += 16;
            }
            if (cy > 31) break;

            if (UTF8_FONT_Lookup(unicode, glyph) == 0) {
                OLED_Draw_Glyph(cx, cy, glyph);
            } else {
                /* Character not in font — show '?' placeholder */
                printf("FONT? U+%04lX\r\n", (unsigned long)unicode);
                OLED_Show_Char(cx, cy, '?', 16);
            }
            cx += 16;
        }
    }

    OLED_Refresh();
}
