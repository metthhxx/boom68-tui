#!/usr/bin/env python3
"""
Language: Python 3
Filename: boom68_ctl.py
Platform: Linux
Target: Langtu BOOM68 / HE68 (Microdia 0c45:80b5) RGB Lighting Controller
"""

import sys
import os
import glob
import time
import select
import argparse

VENDOR_ID = "00000C45"
PRODUCT_ID = "000080B5"

# Commands from Langtu driver protocol
CMD_GET_LED_EFFECT = 19       # 0x13
CMD_SET_LED_EFFECT = 35       # 0x23
CMD_SET_SIDE_LIGHT = 45       # 0x2D
CMD_GET_SIDE_LIGHT = 29       # 0x1D
CMD_SET_CUSTOM_LED_DATA = 36  # 0x24
CMD_GET_CUSTOM_LED_DATA = 20  # 0x14

PRESET_MODES = {
    "off": 0,
    "static": 1,
    "single_on": 2,
    "single_off": 3,
    "stars": 4,
    "snow": 5,
    "flowers": 6,
    "breathe": 7,
    "spectrum": 8,
    "spring": 9,
    "cross": 10,
    "wave": 11,
    "twists": 12,
    "trigger": 13,
    "birds": 14,
    "ripple": 15,
    "stream": 16,
    "mountains": 17,
    "drizzle": 18,
    "shuttle": 19,
    "custom": 128,
}

def find_hidraw_device():
    """Finds the vendor-specific hidraw node (Usage Page 0xff68) for BOOM68."""
    for sysfs_path in glob.glob("/sys/class/hidraw/hidraw*"):
        uevent_file = os.path.join(sysfs_path, "device", "uevent")
        if not os.path.exists(uevent_file):
            continue
        try:
            with open(uevent_file, "r") as f:
                content = f.read()
            if VENDOR_ID in content and PRODUCT_ID in content:
                # Check report descriptor
                rd_file = os.path.join(sysfs_path, "device", "report_descriptor")
                if os.path.exists(rd_file):
                    with open(rd_file, "rb") as rf:
                        desc = rf.read()
                    # 0x06, 0x68, 0xff corresponds to Vendor Defined Page 0xff68
                    if b"\x06\x68\xff" in desc:
                        dev_node = "/dev/" + os.path.basename(sysfs_path)
                        return dev_node
        except Exception:
            continue
    return None

def build_packet(cmd, content_size, addr=0, data=None, report_len=64, is_last=True):
    """
    Constructs a 64-byte protocol packet.
    Header: [0xAA, cmd, content_size, addr_low, addr_high, 0, is_last_flag, 0]
    Payload starts at offset 8.
    """
    pkt = bytearray(report_len)
    pkt[0] = 0xAA
    pkt[1] = cmd & 0xFF
    pkt[2] = content_size & 0xFF
    pkt[3] = addr & 0xFF
    pkt[4] = (addr >> 8) & 0xFF
    pkt[5] = 0
    pkt[6] = 1 if is_last else 0
    pkt[7] = 0
    if data:
        for i, b in enumerate(data[:content_size]):
            pkt[8 + i] = b & 0xFF
    return pkt

def send_and_receive(fd, packet, expected_cmd, timeout=0.5):
    """Sends packet to hidraw device and waits for response (header 0x55)."""
    # Drain any stale input
    while True:
        r, _, _ = select.select([fd], [], [], 0)
        if not r:
            break
        try:
            os.read(fd, 64)
        except Exception:
            break

    # Send report
    os.write(fd, packet)

    # Wait response
    end_time = time.time() + timeout
    while time.time() < end_time:
        rem = max(0.01, end_time - time.time())
        r, _, _ = select.select([fd], [], [], rem)
        if r:
            res = os.read(fd, 64)
            if len(res) >= 8 and res[0] == 0x55 and res[1] == expected_cmd:
                return res
    return None

def get_current_effect(fd):
    pkt = build_packet(CMD_GET_LED_EFFECT, 16, 0)
    res = send_and_receive(fd, pkt, CMD_GET_LED_EFFECT, timeout=0.5)
    if not res:
        return None
    data = res[8:24]
    return {
        "mode": data[0],
        "red": data[1],
        "green": data[2],
        "blue": data[3],
        "secondaryRed": data[5],
        "secondaryGreen": data[6],
        "secondaryBlue": data[7],
        "colorMode": data[8],       # 0 = single color, 1 = RGB cycle
        "brightness": data[9],     # 1..6
        "speed": data[10],         # 1..6
        "direction": data[11],     # 0..3
        "effectModeType": data[12]
    }

def set_led_effect(fd, mode=1, r=255, g=0, b=0, color_mode=0, brightness=5, speed=3, direction=0,
                   sec_r=0, sec_g=0, sec_b=0, effect_type=0, color_order="RGB"):
    if color_order == "BGR":
        out_r, out_g, out_b = b, g, r
    else:
        out_r, out_g, out_b = r, g, b

    data = bytearray(16)
    data[0] = mode & 0xFF
    data[1] = out_r & 0xFF
    data[2] = out_g & 0xFF
    data[3] = out_b & 0xFF
    data[4] = 255              # driverSetting
    data[5] = sec_r & 0xFF
    data[6] = sec_g & 0xFF
    data[7] = sec_b & 0xFF
    data[8] = color_mode & 0xFF
    data[9] = brightness & 0xFF
    data[10] = speed & 0xFF
    data[11] = direction & 0xFF
    data[12] = effect_type & 0xFF
    data[13] = 0
    data[14] = 170             # 0xAA check code
    data[15] = 85              # 0x55 check code

    pkt = build_packet(CMD_SET_LED_EFFECT, 16, 0, data=data)
    res = send_and_receive(fd, pkt, CMD_SET_LED_EFFECT, timeout=0.8)
    return res is not None

def set_side_light(fd, mode=1, r=255, g=255, b=255, color_mode=0, brightness=5, speed=3):
    """
    Controls the upper RGB lightbar / light strip (CMD 45 SET_SIDE_LIGHT & CMD 43 SET_LIGHT_BOX).
    Modes: 1 = Flowing (Радуга), 2 = Static (Статичный), 3 = Breathe (Дыхание),
           4 = Spectrum (Спектр), 5 = Off (Выключить), 6 = Scroll (Бегущий)
    """
    data = bytearray(24)
    data[0] = mode & 0xFF
    data[1] = r & 0xFF
    data[2] = g & 0xFF
    data[3] = b & 0xFF
    data[8] = color_mode & 0xFF
    data[9] = brightness & 0xFF
    data[10] = speed & 0xFF

    # Send CMD 45 (SET_SIDE_LIGHT)
    pkt45 = build_packet(CMD_SET_SIDE_LIGHT, 24, 0, data=data)
    try:
        os.write(fd, pkt45)
    except Exception:
        pass

    # Send CMD 43 (SET_LIGHT_BOX)
    pkt43 = build_packet(43, 24, 0, data=data)
    try:
        os.write(fd, pkt43)
    except Exception:
        pass

    return True

def read_fn_keys(fd):
    """Reads the 512-byte FN layer key mapping table (CMD 22)."""
    total_len = 512
    chunk_size = 56
    num_chunks = (total_len + chunk_size - 1) // chunk_size
    fn_bytes = bytearray()
    for i in range(num_chunks):
        addr = i * chunk_size
        p_len = min(chunk_size, total_len - addr)
        is_last = (i == num_chunks - 1)
        pkt = build_packet(22, p_len, addr=addr, is_last=is_last)
        res = send_and_receive(fd, pkt, 22, timeout=0.5)
        if not res:
            return None
        fn_bytes.extend(res[8:8+p_len])
    return fn_bytes

def write_fn_keys(fd, fn_bytes):
    """Writes the 512-byte FN layer key mapping table (CMD 38)."""
    total_len = len(fn_bytes)
    chunk_size = 56
    num_chunks = (total_len + chunk_size - 1) // chunk_size
    for i in range(num_chunks):
        addr = i * chunk_size
        p_len = min(chunk_size, total_len - addr)
        is_last = (i == num_chunks - 1)
        chunk = fn_bytes[addr : addr + p_len]
        pkt = build_packet(38, p_len, addr=addr, data=chunk, is_last=is_last)
        res = send_and_receive(fd, pkt, 38, timeout=0.5)
        if not res:
            return False
    return True

def restore_lightbar_fn_bindings(fd):
    """
    Restores hardware FN shortcuts for controlling the top RGB lightbar:
      Fn + L-Alt (Key 82) -> Function 29 (Front light strip color cycle)
      Fn + R-Alt (Key 84) -> Function 27 (Front light strip effect/mode cycle)
      Fn + R-Ctrl (Key 87) -> Function 29 (Front light strip color cycle)
      Fn + Up (Key 90) -> Function 66 (Front light strip brightness +)
      Fn + Down (Key 89) -> Function 67 (Front light strip brightness -)
      Fn + Right (Key 91) -> Function 64 (Front light strip speed +)
      Fn + Left (Key 88) -> Function 65 (Front light strip speed -)
    """
    fn_bytes = read_fn_keys(fd)
    if not fn_bytes or len(fn_bytes) < 512:
        return False
    fn_bytes = bytearray(fn_bytes)
    fn_bytes[82*4 : 82*4 + 4] = bytes([13, 0, 0, 29]) # L-Alt: Color toggle
    fn_bytes[84*4 : 84*4 + 4] = bytes([13, 0, 0, 27]) # R-Alt: Effect toggle
    fn_bytes[87*4 : 87*4 + 4] = bytes([13, 0, 0, 29]) # R-Ctrl: Color toggle
    fn_bytes[90*4 : 90*4 + 4] = bytes([13, 0, 0, 66]) # Up: Brightness +
    fn_bytes[89*4 : 89*4 + 4] = bytes([13, 0, 0, 67]) # Down: Brightness -
    fn_bytes[91*4 : 91*4 + 4] = bytes([13, 0, 0, 64]) # Right: Speed +
    fn_bytes[88*4 : 88*4 + 4] = bytes([13, 0, 0, 65]) # Left: Speed -
    return write_fn_keys(fd, fn_bytes)

def parse_hex_color(hex_str):
    hex_str = hex_str.lstrip("#")
    if len(hex_str) != 6:
        raise ValueError("Invalid hex color: must be 6 hex characters (e.g. ff0000 or #00ff88)")
    return int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)

def main():
    parser = argparse.ArgumentParser(description="Langtu BOOM68 / HE68 RGB Lighting CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # info command
    subparsers.add_parser("info", help="Get current keyboard lighting status")

    # set command
    set_parser = subparsers.add_parser("set", help="Set RGB backlight effect and color")
    set_parser.add_argument("--mode", "-m", choices=list(PRESET_MODES.keys()), default="static",
                            help="Lighting effect mode (default: static)")
    set_parser.add_argument("--color", "-c", default=None,
                            help="Hex color (e.g. ff0000, 00ffcc). Defaults to single color mode if given.")
    set_parser.add_argument("--rgb", action="store_true",
                            help="Enable dynamic RGB rainbow mode")
    set_parser.add_argument("--brightness", "-b", type=int, choices=range(1, 7), default=5,
                            help="Brightness level 1-6 (default: 5)")
    set_parser.add_argument("--speed", "-s", type=int, choices=range(1, 7), default=3,
                            help="Effect speed 1-6 (default: 3)")
    set_parser.add_argument("--direction", "-d", type=int, choices=[0, 1, 2, 3], default=0,
                            help="Direction 0-3 (default: 0)")

    # off / on shortcuts
    subparsers.add_parser("off", help="Turn off backlight")
    subparsers.add_parser("on", help="Turn on static backlight")

    # side command
    side_parser = subparsers.add_parser("side", help="Set side light effect")
    side_parser.add_argument("--mode", type=int, default=1, choices=range(1, 7), help="Side light mode (1-6)")
    side_parser.add_argument("--color", "-c", default="ffffff", help="Hex color")
    side_parser.add_argument("--brightness", "-b", type=int, default=5, help="Brightness 1-6")
    side_parser.add_argument("--speed", "-s", type=int, default=3, help="Speed 1-6")

    # lightbar shortcuts & binding recovery
    subparsers.add_parser("restore-lightbar", help="Restore hardware FN shortcuts for top RGB lightbar (Fn+Alt, Fn+Arrows)")
    subparsers.add_parser("fn-info", help="Show active FN layer key bindings")

    args = parser.parse_args()

    dev_node = find_hidraw_device()
    if not dev_node:
        print("Error: Langtu BOOM68 keyboard HID interface not found.", file=sys.stderr)
        print("Ensure the keyboard is plugged via USB.", file=sys.stderr)
        sys.exit(1)

    try:
        fd = os.open(dev_node, os.O_RDWR)
    except PermissionError:
        print(f"Error: Permission denied accessing {dev_node}.", file=sys.stderr)
        print("Run with sudo or apply the udev rule:", file=sys.stderr)
        print("  sudo cp 99-langtu-boom68.rules /etc/udev/rules.d/ && sudo udevadm trigger", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"Error opening {dev_node}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.command == "info" or args.command is None:
            info = get_current_effect(fd)
            if not info:
                print("Failed to read current lighting effect from keyboard.")
            else:
                mode_rev = {v: k for k, v in PRESET_MODES.items()}
                mode_name = mode_rev.get(info["mode"], f"unknown ({info['mode']})")
                print("=== Langtu BOOM68 Current Lighting ===")
                print(f"Device:      {dev_node}")
                print(f"Mode:        {mode_name} (code: {info['mode']})")
                print(f"Color:       RGB({info['red']}, {info['green']}, {info['blue']}) [#{info['red']:02x}{info['green']:02x}{info['blue']:02x}]")
                print(f"Color Mode:  {'RGB Rainbow' if info['colorMode'] == 1 else 'Single Color'}")
                print(f"Brightness:  {info['brightness']} / 6")
                print(f"Speed:       {info['speed']} / 6")
                print(f"Direction:   {info['direction']}")

        elif args.command == "off":
            ok = set_led_effect(fd, mode=0, brightness=1)
            print("Backlight turned OFF" if ok else "Failed to send command")

        elif args.command == "on":
            ok = set_led_effect(fd, mode=1, r=255, g=255, b=255, color_mode=0, brightness=5)
            print("Backlight turned ON (static white)" if ok else "Failed to send command")

        elif args.command == "set":
            mode_num = PRESET_MODES[args.mode]
            color_mode = 1 if args.rgb else 0
            r, g, b = (255, 255, 255)
            if args.color:
                r, g, b = parse_hex_color(args.color)
                color_mode = 0
            elif args.rgb:
                color_mode = 1

            ok = set_led_effect(
                fd,
                mode=mode_num,
                r=r, g=g, b=b,
                color_mode=color_mode,
                brightness=args.brightness,
                speed=args.speed,
                direction=args.direction
            )
            if ok:
                print(f"Applied: mode={args.mode}, rgb={'RGB' if color_mode==1 else f'#{r:02x}{g:02x}{b:02x}'}, brightness={args.brightness}, speed={args.speed}")
            else:
                print("Failed to set effect on keyboard.")

        elif args.command == "side":
            r, g, b = parse_hex_color(args.color)
            ok = set_side_light(fd, mode=args.mode, r=r, g=g, b=b, brightness=args.brightness, speed=args.speed)
            print(f"Side light updated" if ok else "Failed to update side light")

        elif args.command == "restore-lightbar":
            ok = restore_lightbar_fn_bindings(fd)
            if ok:
                print("Successfully restored lightbar hardware hotkeys:")
                print("  Fn + L-Alt / R-Ctrl: Switch Lightbar Color (Function 29)")
                print("  Fn + R-Alt:          Switch Lightbar Mode / Effect (Function 27)")
                print("  Fn + Up Arrow:       Increase Lightbar Brightness (Function 66)")
                print("  Fn + Down Arrow:     Decrease Lightbar Brightness (Function 67)")
                print("  Fn + Right Arrow:    Increase Lightbar Speed (Function 64)")
                print("  Fn + Left Arrow:     Decrease Lightbar Speed (Function 65)")
            else:
                print("Failed to restore FN key bindings")

        elif args.command == "fn-info":
            fn_bytes = read_fn_keys(fd)
            if not fn_bytes:
                print("Failed to read FN keys")
            else:
                print("=== Lightbar FN Bindings ===")
                labels = {
                    82: "L-Alt",
                    84: "R-Alt",
                    87: "R-Ctrl",
                    88: "Left Arrow",
                    89: "Down Arrow",
                    90: "Up Arrow",
                    91: "Right Arrow",
                }
                func_names = {
                    27: "Light Strip Mode Switch",
                    28: "Light Strip Speed Cycle",
                    29: "Light Strip Color Switch",
                    61: "Light Strip Brightness Toggle",
                    64: "Light Strip Speed +",
                    65: "Light Strip Speed -",
                    66: "Light Strip Brightness +",
                    67: "Light Strip Brightness -",
                }
                for idx, name in labels.items():
                    off = idx * 4
                    page, p1, p2, p3 = fn_bytes[off : off + 4]
                    fname = func_names.get(p3, f"Code {p3}") if page == 13 else f"Page {page}, val {p1},{p2},{p3}"
                    print(f"  Fn + {name:12s} (Key {idx:2d}): {fname}")

    finally:
        os.close(fd)

if __name__ == "__main__":
    main()
