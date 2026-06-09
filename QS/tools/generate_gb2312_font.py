#!/usr/bin/env python3
"""
GB2312 16x16 dot matrix font generator for W25Q16 SPI flash.

Generates the HZK16-compatible binary font file for all GB2312 Chinese characters
(94 zones x 94 chars = 6768 chars, 32 bytes each = ~211KB).

Usage:
    python generate_gb2312_font.py              # Generate font_16x16.bin
    python generate_gb2312_font.py --serial COM3  # Generate and send to MCU
    python generate_gb2312_font.py --send COM3 font_16x16.bin  # Send existing file

Requires: pyserial (for --send mode), Pillow (for font rendering)
"""

import struct
import os
import sys
import argparse
import time

FONT_SIZE = 32  # bytes per 16x16 character
ZONE_COUNT = 72  # GB2312 zones 0xB0-0xF7
CHAR_PER_ZONE = 94  # chars per zone 0xA1-0xFE
FONT_BASE_ADDR = 0x100000  # 1MB offset in W25Q16


def generate_font_with_pillow(output_path):
    """Generate 16x16 GB2312 font bitmap using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        print("Or provide a HZK16 file directly.")
        return False

    # Try common Chinese fonts - prefer bold/sans-serif for OLED clarity
    font_paths = [
        "C:/Windows/Fonts/simhei.ttf",   # SimHei (黑体) - best for OLED
        "C:/Windows/Fonts/msyh.ttc",     # Microsoft YaHei
        "C:/Windows/Fonts/simsun.ttc",   # SimSun - fallback
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]

    font = None
    font_name = ""
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 28)  # Render large for quality
                font_name = os.path.basename(fp)
                print(f"Using font: {fp}")
                break
            except Exception:
                continue

    if font is None:
        print("ERROR: No suitable Chinese font found.")
        print("Install a Chinese font or provide a HZK16 file.")
        return False

    total_chars = ZONE_COUNT * CHAR_PER_ZONE
    data = bytearray(total_chars * FONT_SIZE)

    for zone in range(ZONE_COUNT):
        gb_h = 0xB0 + zone
        for bit in range(CHAR_PER_ZONE):
            gb_l = 0xA1 + bit
            index = zone * CHAR_PER_ZONE + bit

            try:
                gb_bytes = bytes([gb_h, gb_l])
                char = gb_bytes.decode('gb2312')
            except (UnicodeDecodeError, LookupError):
                continue

            # Render at 28px on 32x32 canvas, then downscale to 16x16
            img = Image.new('L', (32, 32), 0)
            draw = ImageDraw.Draw(img)
            bbox = draw.textbbox((0, 0), char, font=font)
            # Center the character
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            x = (32 - tw) // 2 - bbox[0]
            y = (32 - th) // 2 - bbox[1] - 1
            draw.text((x, y), char, font=font, fill=255)

            # Downscale with threshold for clean edges
            img = img.resize((16, 16), Image.LANCZOS)

            # Binarize with threshold
            threshold = 80
            img_bin = img.point(lambda p: 255 if p > threshold else 0)

            # Convert to HZK16 format (row-major, MSB left)
            offset = index * FONT_SIZE
            for row in range(16):
                byte_val = 0
                for col in range(8):
                    if img_bin.getpixel((col, row)):
                        byte_val |= (0x80 >> col)
                data[offset + row * 2] = byte_val

                byte_val = 0
                for col in range(8):
                    if img_bin.getpixel((col + 8, row)):
                        byte_val |= (0x80 >> col)
                data[offset + row * 2 + 1] = byte_val

            if index % 500 == 0:
                print(f"  Progress: {index}/{total_chars}")

    with open(output_path, 'wb') as f:
        f.write(data)

    print(f"Generated {len(data)} bytes -> {output_path}")
    print(f"Characters: {total_chars}")
    print(f"Expected W25Q16 address: 0x{FONT_BASE_ADDR:06X}")
    return True


def read_hzk16(hzk_path, output_path):
    """Convert a raw HZK16 file to W25Q16-ready binary."""
    expected_size = ZONE_COUNT * CHAR_PER_ZONE * FONT_SIZE

    with open(hzk_path, 'rb') as f:
        data = f.read()

    if len(data) < expected_size:
        print(f"WARNING: HZK16 file is {len(data)} bytes, expected {expected_size}")
        # Pad with zeros
        data = data + b'\x00' * (expected_size - len(data))
    elif len(data) > expected_size:
        data = data[:expected_size]

    with open(output_path, 'wb') as f:
        f.write(data)

    print(f"Converted {len(data)} bytes -> {output_path}")
    return True


def send_via_serial(port, bin_path, baudrate=115200):
    """Send font binary to STM32 via UART for W25Q16 programming."""
    try:
        import serial
    except ImportError:
        print("ERROR: pyserial not installed. Run: pip install pyserial")
        return False

    file_size = os.path.getsize(bin_path)
    print(f"Opening {port} at {baudrate} baud...")
    print(f"Sending {file_size} bytes ({file_size/1024:.1f} KB)...")

    ser = serial.Serial(port, baudrate, timeout=5)
    ser.reset_input_buffer()

    # Send download command
    cmd = f"FONT_DL:{FONT_BASE_ADDR}:{file_size}\n".encode()
    ser.write(cmd)
    print(f"Sent command: {cmd.decode().strip()}")

    # Wait for ACK
    response = ser.readline().decode().strip()
    print(f"MCU response: {response}")
    if "READY" not in response:
        print("ERROR: MCU not ready for download")
        ser.close()
        return False

    # Read file and send in chunks
    CHUNK = 256  # Match W25Q16 page size
    with open(bin_path, 'rb') as f:
        offset = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break

            # Send chunk header: offset (4 bytes) + length (2 bytes) + data + CRC
            header = struct.pack('>IH', FONT_BASE_ADDR + offset, len(chunk))
            ser.write(header + chunk)

            ack = ser.read(2)
            if ack != b'OK':
                print(f"ERROR at offset {offset}: expected 'OK', got {ack}")
                ser.close()
                return False

            offset += len(chunk)
            if offset % (32 * 1024) == 0:
                progress = offset * 100 // file_size
                print(f"  Progress: {progress}% ({offset}/{file_size} bytes)")

    # Send done marker
    ser.write(b'DONE')
    final = ser.readline().decode().strip()
    print(f"Final response: {final}")

    ser.close()
    print("Download complete!")
    return True


def main():
    parser = argparse.ArgumentParser(description='GB2312 16x16 Font Generator for W25Q16')
    parser.add_argument('--hzk', help='Path to HZK16 font file')
    parser.add_argument('--output', default='font_16x16.bin', help='Output binary file')
    parser.add_argument('--send', help='Send to MCU via serial port (COMx)')
    parser.add_argument('--serial', help='Generate AND send via serial port')
    parser.add_argument('--baudrate', type=int, default=115200, help='Serial baudrate')
    args = parser.parse_args()

    output = args.output

    if args.hzk and os.path.exists(args.hzk):
        print(f"Converting HZK16 file: {args.hzk}")
        if not read_hzk16(args.hzk, output):
            sys.exit(1)
    elif args.hzk:
        print(f"ERROR: HZK16 file not found: {args.hzk}")
        sys.exit(1)
    else:
        print("Generating font with Pillow...")
        if not generate_font_with_pillow(output):
            print("\nAlternative: Download HZK16 file and use --hzk option")
            print("  python generate_gb2312_font.py --hzk HZK16")
            sys.exit(1)

    # Send if requested
    port = args.send or args.serial
    if port:
        send_via_serial(port, output, args.baudrate)


if __name__ == '__main__':
    main()
