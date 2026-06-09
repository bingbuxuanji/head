#!/usr/bin/env python3
"""
Convert Chinese text to GB2312 hex for use in C code.

Usage:
    python chinese_to_c.py "你好世界"
    -> "\xC4\xE3\xBA\xC3\xCA\xC0\xBD\xE7"

    python chinese_to_c.py "你好世界" --var mytext
    -> const char mytext[] = "\xC4\xE3\xBA\xC3\xCA\xC0\xBD\xE7";
"""
import sys

def convert(text):
    gb = text.encode('gb2312')
    return ''.join(f'\\x{b:02X}' for b in gb)

if __name__ == '__main__':
    args = sys.argv[1:]
    var_name = None
    text_parts = []

    for a in args:
        if a == '--var':
            var_name = True
        elif var_name is True:
            var_name = a
        else:
            text_parts.append(a)

    text = ' '.join(text_parts)
    if not text:
        print(__doc__)
        sys.exit(1)

    hex_str = convert(text)

    if var_name:
        print(f'const char {var_name}[] = "{hex_str}";')
    else:
        print(f'"{hex_str}"')
