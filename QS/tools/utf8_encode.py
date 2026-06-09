#!/usr/bin/env python3
"""Print UTF-8 hex escapes for command-line Chinese text."""
import sys
text = sys.argv[1] if len(sys.argv) > 1 else "前方500米左转"
u8 = text.encode('utf-8')
# Hex
print('Hex:', ' '.join(f'{b:02X}' for b in u8))
# C escape
print('C escapes:', ''.join(f'\\x{b:02X}' for b in u8))
# Full 't' prefix message
print()
print('Full t msg (hex):', '74 ' + ' '.join(f'{b:02X}' for b in u8))
