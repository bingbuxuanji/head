#!/usr/bin/env python3
"""Fix gps.c USART2 callback for nav text display."""
import os

path = os.path.join(os.path.dirname(__file__), '..', 'BSP', 'GPS', 'gps.c')
path = os.path.normpath(path)

with open(path, 'rb') as f:
    c = f.read()

# Find the broken block
marker = b'if(huart->Instance==USART2)'
idx = c.find(marker)
assert idx >= 0

# Find matching close brace
brace_start = c.find(b'{', idx)
depth = 0
i = brace_start
while i < len(c):
    if c[i:i+1] == b'{': depth += 1
    elif c[i:i+1] == b'}':
        depth -= 1
        if depth == 0:
            break
    i += 1
end = i + 1

# Build replacement with proper escapes
# Use raw bytes for escaped characters to avoid bash issues
cr = bytes([0x5C, 0x72])  # \r
cn = bytes([0x5C, 0x6E])  # \n
nul = bytes([0x5C, 0x30])  # \0

new_block = (
    b'if(huart->Instance==USART2)\n'
    b'        {\n'
    b'            if (Size > 1 && get_gps_flag_buf[0] == \'t\')\n'
    b'            {\n'
    b'                get_gps_flag_buf[Size] = ' + nul + b';\n'
    b'                OLED_ShowString_UTF8(0, 6, (char *)&get_gps_flag_buf[1], 0);\n'
    b'            }\n'
    b'            else if (Size > 0 && get_gps_flag_buf[0] == \'g\')\n'
    b'            {\n'
    b'                count++;\n'
    b'                if(count>=3) count=3;\n'
    b'                sprintf(tx_gps_buf, "g%.6f,%.6f' + cr + cn + b'",\n'
    b'                        GPS_DUG[count][0], GPS_DUG[count][1]);\n'
    b'                HAL_UART_Transmit(&huart2, (uint8_t*)tx_gps_buf, strlen(tx_gps_buf), 100);\n'
    b'            }\n'
    b'\n'
    b'            memset(get_gps_flag_buf, 0, sizeof(get_gps_flag_buf));\n'
    b'            HAL_UARTEx_ReceiveToIdle_DMA(&huart2, get_gps_flag_buf, sizeof(get_gps_flag_buf));\n'
    b'        }'
)

c = c[:idx] + new_block + c[end:]

with open(path, 'wb') as f:
    f.write(c)
print('Fixed gps.c')
