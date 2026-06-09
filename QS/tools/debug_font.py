#!/usr/bin/env python3
"""Debug: verify font data and HZK16→OLED conversion for the demo chars."""
import os

FONT_PATH = os.path.join(os.path.dirname(__file__), 'font_16x16.bin')

def gb2312_to_index(gb_h, gb_l):
    return (gb_h - 0xB0) * 94 + (gb_l - 0xA1)

def hzk16_to_oled(src):
    """Simulate HZK16_To_OLED conversion in C code."""
    dst = [0] * 32
    for col in range(16):
        if col < 8:
            byte_idx = 0
            bit_pos = 7 - col
        else:
            byte_idx = 1
            bit_pos = 15 - col
        mask = 1 << bit_pos
        for row in range(8):
            if src[row * 2 + byte_idx] & mask:
                dst[col] |= (1 << row)
            if src[(row + 8) * 2 + byte_idx] & mask:
                dst[col + 16] |= (1 << row)
    return dst

def print_glyph(data, oled_fmt=True):
    """Print 16x16 glyph as ASCII art."""
    for row in range(16):
        line = ''
        for col in range(16):
            if oled_fmt:
                # SSD1306 column-major
                if col < 8:
                    byte_idx = 0
                    bit_pos = 7 - col
                else:
                    byte_idx = 1
                    bit_pos = 15 - col
                mask = 1 << bit_pos
                if row < 8:
                    val = data[row + 16 * 0]  # this isn't right for OLED fmt
                # Actually for OLED format, dst[col] contains rows 0-7 of column col
                # dst[col+16] contains rows 8-15 of column col
                if row < 8:
                    pixel = (data[col] >> row) & 1
                else:
                    pixel = (data[col + 16] >> (row - 8)) & 1
            else:
                # HZK16 row-major
                byte_ofs = row * 2 + (0 if col < 8 else 1)
                bit = 7 - (col % 8)
                pixel = (data[byte_ofs] >> bit) & 1
            line += '##' if pixel else '  '
        print(line)

# Read font file
with open(FONT_PATH, 'rb') as f:
    font_data = f.read()

print(f"Font file: {len(font_data)} bytes\n")

# Test: character '独' (GB2312 0xB6 0xC0)
gb_h, gb_l = 0xB6, 0xC0
index = gb2312_to_index(gb_h, gb_l)
offset = index * 32

print(f"=== 独 (GB2312 {gb_h:02X} {gb_l:02X}, index={index}, offset=0x{offset:06X}) ===")
print(f"Font file bytes at offset {offset}:")
src = list(font_data[offset:offset+32])
for i in range(0, 32, 16):
    print('  ' + ' '.join(f'{b:02X}' for b in src[i:i+16]))

print("\nHZK16 format (row-major) glyph:")
print_glyph(src, oled_fmt=False)

dst = hzk16_to_oled(src)
print("\nOLED format (column-major) glyph after conversion:")
print_glyph(dst, oled_fmt=True)

# Also test 角 and 兽
for gb_h, gb_l, name in [(0xBD, 0xC7, '角'), (0xCA, 0xDE, '兽')]:
    index = gb2312_to_index(gb_h, gb_l)
    offset = index * 32
    src = list(font_data[offset:offset+32])
    dst = hzk16_to_oled(src)
    print(f"\n=== {name} (GB2312 {gb_h:02X} {gb_l:02X}, index={index}) ===")
    print("OLED format glyph:")
    print_glyph(dst, oled_fmt=True)
