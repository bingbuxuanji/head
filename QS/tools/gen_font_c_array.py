#!/usr/bin/env python3
"""
Convert font_16x16.bin to a C array placed in a dedicated flash section.
The scatter file will place it at a fixed address in internal flash.
"""
import os

TOOLS = os.path.dirname(__file__)
FONT_BIN = os.path.join(TOOLS, 'font_16x16.bin')
OUTPUT_C = os.path.join(TOOLS, '..', 'Core', 'Src', 'font_data.c')
OUTPUT_H = os.path.join(TOOLS, '..', 'Core', 'Inc', 'font_data.h')

# Read binary
with open(FONT_BIN, 'rb') as f:
    data = f.read()

size = len(data)

# Write header
with open(OUTPUT_H, 'w', encoding='utf-8') as f:
    f.write('#ifndef __FONT_DATA_H__\n')
    f.write('#define __FONT_DATA_H__\n\n')
    f.write('#include <stdint.h>\n\n')
    f.write('#define FONT_EMBED_SIZE  {}\n'.format(size))
    f.write('#define FONT_EMBED_ADDR  0x08040000\n\n')
    f.write('extern const uint8_t font_embed_data[FONT_EMBED_SIZE];\n\n')
    f.write('#endif\n')

# Write C file
with open(OUTPUT_C, 'w', encoding='utf-8') as f:
    f.write('/* Auto-generated font binary embedded in internal flash */\n')
    f.write('#include "font_data.h"\n\n')
    f.write('__attribute__((section(".FontSection")))\n')
    f.write('const uint8_t font_embed_data[FONT_EMBED_SIZE] = {\n')

    for i in range(0, len(data), 16):
        chunk = data[i:i+16]
        hex_str = ', '.join(f'0x{b:02X}' for b in chunk)
        if i + 16 < len(data):
            f.write(f'    {hex_str},\n')
        else:
            f.write(f'    {hex_str}\n')

    f.write('};\n')

print(f'Generated: {size} bytes')
print(f'  {OUTPUT_C}')
print(f'  {OUTPUT_H}')
