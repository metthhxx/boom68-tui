#!/usr/bin/env python3
"""
Language: Python 3
Filename: boom68_visualizer.py
Platform: Linux (PipeWire via Cava backend with per-process routing & zero lag)
Target: Langtu BOOM68 / HE68 Real-Time Audio Reactive Music Equalizer
"""

import os
import sys
import time
import signal
import select
import tempfile
import subprocess
import threading
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boom68_ctl

# Matrix definition of BOOM68 (rows x cols)
# row 0 (15 keys): Esc..Del
# row 1 (15 keys): Tab..PgUp
# row 2 (14 keys): Caps..PgDn
# row 3 (13 keys): L-Shift..ArrowUp
# row 4 (10 keys): L-Ctrl..ArrowRight
KEY_MATRIX = [
    [0, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 92, 106],
    [32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 60, 105],
    [48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 76, 108],
    [64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 90],
    [80, 81, 82, 83, 84, 85, 87, 88, 89, 91]
]

# Flattened unique physical keys
ALL_KEYS = []
for row in KEY_MATRIX:
    for k in row:
        if k not in ALL_KEYS:
            ALL_KEYS.append(k)

def get_audio_targets():
    """
    Returns a list of tuples (node_id_or_name, display_label) representing:
    - Master mix
    - Running audio apps (Zen, Spotify, Discord, Games, etc.)
    - Hardware sinks / devices (HDMI, USB headphones, Mic)
    """
    targets = [('auto', '🔊 Весь системный звук (Общий микс)')]
    seen = {'auto'}

    # 1. Apps from sink-inputs (robust block-based parser)
    try:
        out = subprocess.check_output(['pactl', 'list', 'sink-inputs'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        for block in out.split('Sink Input #')[1:]:
            props = {}
            for line in block.splitlines():
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    props[k.strip()] = v.strip(' \"')
            node = props.get('node.name') or props.get('application.name') or props.get('application.process.binary')
            app = props.get('application.name') or props.get('node.name') or props.get('application.process.binary')
            media = props.get('media.name', '')
            if node and node not in seen:
                seen.add(node)
                if media and media not in ('Playback', 'AudioStream', app):
                    label = f'📱 {app} ({media})'
                else:
                    label = f'📱 {app}'
                targets.append((node, label))
    except Exception:
        pass

    # 2. Hardware outputs from sinks with clean descriptions
    try:
        sinks_out = subprocess.check_output(['pactl', 'list', 'sinks'], stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore')
        for block in sinks_out.split('Sink #')[1:]:
            name = ''
            desc = ''
            for line in block.splitlines():
                line = line.strip()
                if line.startswith('Name: '):
                    name = line.split('Name: ', 1)[1].strip()
                elif line.startswith('Description: '):
                    desc = line.split('Description: ', 1)[1].strip()
            if name and name not in seen:
                seen.add(name)
                d_lower = desc.lower() + ' ' + name.lower()
                if 'hdmi' in d_lower or 'displayport' in d_lower:
                    icon = '🖥️'
                elif 'usb' in d_lower or 'headphone' in d_lower or 'headset' in d_lower:
                    icon = '🎧'
                elif 'speaker' in d_lower or 'analog' in d_lower:
                    icon = '🔈'
                else:
                    icon = '🔊'
                targets.append((name, f'{icon} {desc}'))
    except Exception:
        pass

    return targets

def clear_all_inputs_to(dest_node='boom68_eq'):
    """
    Disconnects any existing links targeting dest_node's input ports.
    """
    try:
        out = subprocess.check_output(['pw-link', '-I', '-l'], stderr=subprocess.DEVNULL).decode()
        curr_dest = ""
        for line in out.splitlines():
            line_str = line.strip()
            if not line.startswith(' '):
                curr_dest = line_str
            elif '|<-' in line and dest_node in curr_dest:
                parts = line_str.split('|<-')
                link_id = parts[0].strip()
                if link_id.isdigit():
                    subprocess.run(['pw-link', '-d', link_id], stderr=subprocess.DEVNULL)
    except Exception:
        pass

def route_pipewire_node(target_node, dest_node='boom68_eq'):
    """
    Exclusively connects target application or monitor ports to dest_node's input ports.
    """
    clear_all_inputs_to(dest_node)

    try:
        out_ports = subprocess.check_output(['pw-link', '-I', '-o'], stderr=subprocess.DEVNULL).decode().splitlines()
    except Exception:
        return False

    matched_fl = []
    matched_fr = []

    if target_node == 'auto':
        try:
            sink = subprocess.check_output(['pactl', 'get-default-sink'], stderr=subprocess.DEVNULL).decode().strip()
            target_prefix = sink
        except Exception:
            target_prefix = 'alsa_output'
    else:
        target_prefix = target_node

    for line in out_ports:
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2:
            pid, pname = parts[0], parts[1]
            prefix = pname.split(':', 1)[0]
            if prefix == target_prefix:
                if 'FL' in pname or '_1' in pname or 'output_FL' in pname or 'monitor_FL' in pname:
                    matched_fl.append(pid)
                elif 'FR' in pname or '_2' in pname or 'output_FR' in pname or 'monitor_FR' in pname:
                    matched_fr.append(pid)
                else:
                    matched_fl.append(pid)

    if not matched_fl and not matched_fr:
        return False

    for pid in matched_fl:
        subprocess.run(['pw-link', pid, f'{dest_node}:input_FL'], stderr=subprocess.DEVNULL)
    for pid in matched_fr:
        subprocess.run(['pw-link', pid, f'{dest_node}:input_FR'], stderr=subprocess.DEVNULL)

    # Fallback for mono streams
    if not matched_fr and matched_fl:
        for pid in matched_fl:
            subprocess.run(['pw-link', pid, f'{dest_node}:input_FR'], stderr=subprocess.DEVNULL)

    return True

    return True

class AudioEqualizerEngine:
    def __init__(self, mode="bars", sensitivity=1.5, fps=60,
                 color_mode="custom", custom_color=(255, 20, 147),
                 color_order="RGB", audio_source="auto"):
        self.mode = mode               # "bars", "pulse", "wave"
        self.sensitivity = float(sensitivity)
        self.fps = fps
        self.color_mode = color_mode   # "custom", "rainbow"
        self.custom_color = custom_color # (r, g, b)
        self.color_order = color_order # "RGB" or "BGR"
        self.audio_source = audio_source # "auto" or application node name
        self.running = False
        self.dev_node = boom68_ctl.find_hidraw_device()
        self.fd = None
        self.proc = None
        self.cava_conf_path = None

    def set_mode(self, mode):
        if mode in ("bars", "pulse", "wave"):
            self.mode = mode

    def set_sensitivity(self, sensitivity):
        self.sensitivity = max(0.2, min(10.0, float(sensitivity)))

    def set_color(self, r, g, b):
        self.custom_color = (int(r), int(g), int(b))
        self.color_mode = "custom"

    def set_color_mode(self, mode):
        if mode in ("custom", "rainbow"):
            self.color_mode = mode

    def set_color_order(self, order):
        if order in ("RGB", "BGR"):
            self.color_order = order

    def set_audio_source(self, target_node):
        self.audio_source = target_node
        if self.running:
            route_pipewire_node(self.audio_source, dest_node='boom68_eq')

    def start(self):
        if not self.dev_node:
            self.dev_node = boom68_ctl.find_hidraw_device()
        if not self.dev_node:
            print("[Equalizer] Error: BOOM68 keyboard not found on USB.", file=sys.stderr)
            return False

        try:
            self.fd = os.open(self.dev_node, os.O_RDWR)
        except Exception as e:
            print(f"[Equalizer] Error opening device {self.dev_node}: {e}", file=sys.stderr)
            return False

        # Switch keyboard to custom per-key lighting mode (mode 128)
        boom68_ctl.set_led_effect(self.fd, mode=128, brightness=6)
        time.sleep(0.05)

        self.running = True
        self.thread = threading.Thread(target=self._run_cava_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=0.3)
            except Exception:
                pass
            self.proc = None

        if self.cava_conf_path and os.path.exists(self.cava_conf_path):
            try:
                os.remove(self.cava_conf_path)
            except Exception:
                pass
            self.cava_conf_path = None

        if self.fd:
            try:
                boom68_ctl.set_led_effect(self.fd, mode=11, color_mode=1, brightness=5, speed=3)
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None

    def _send_rgb_buffer(self, rgb_map):
        """
        Sends 67 keys (268 bytes) in 5 packets of 56 bytes via CMD 50 (Fast RAM streaming).
        Average transfer latency is ~18-19ms.
        """
        if not self.fd:
            return

        total_keys = len(ALL_KEYS)
        data = bytearray(total_keys * 4)
        swap_rb = (self.color_order == "BGR")

        for i, led_id in enumerate(ALL_KEYS):
            idx = i * 4
            r, g, b = rgb_map.get(led_id, (0, 0, 0))
            data[idx] = led_id
            if swap_rb:
                data[idx + 1] = int(min(255, max(0, b)))
                data[idx + 2] = int(min(255, max(0, g)))
                data[idx + 3] = int(min(255, max(0, r)))
            else:
                data[idx + 1] = int(min(255, max(0, r)))
                data[idx + 2] = int(min(255, max(0, g)))
                data[idx + 3] = int(min(255, max(0, b)))

        content_size = len(data)
        chunk_size = 56
        num_packets = (content_size + chunk_size - 1) // chunk_size

        for p in range(num_packets):
            addr = p * chunk_size
            rem = min(chunk_size, content_size - addr)
            pkt = bytearray(64)
            pkt[0] = 0xAA
            pkt[1] = 50 # GET_LED_DATA / SET_MUSIC_DATA (RAM stream)
            pkt[2] = rem
            pkt[3] = addr & 0xFF
            pkt[4] = (addr >> 8) & 0xFF
            pkt[5] = 0
            pkt[6] = 1 if p == num_packets - 1 else 0
            pkt[7] = 0
            pkt[8:8+rem] = data[addr:addr+rem]
            try:
                os.write(self.fd, pkt)
            except Exception:
                break

    def _spawn_cava(self):
        conf_content = f"""
[general]
bars = 15
framerate = 60

[input]
method = pipewire
source = auto

[output]
channels = mono
method = raw
raw_target = /dev/stdout
data_format = binary
bit_format = 8bit

[smoothing]
monstercat = 0
waves = 0
noise_reduction = 0
"""
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".cava") as f:
            f.write(conf_content)
            self.cava_conf_path = f.name

        env = os.environ.copy()
        env['PIPEWIRE_PROPS'] = 'node.name="boom68_eq" node.autoconnect=false'
        cmd = ["cava", "-p", self.cava_conf_path]
        try:
            return subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"[Equalizer] Cava spawn failed: {e}", file=sys.stderr)
            return None

    def _run_cava_loop(self):
        self.proc = self._spawn_cava()
        if not self.proc:
            print("[Equalizer] Failed to start cava stream", file=sys.stderr)
            return

        time.sleep(0.2)
        route_pipewire_node(self.audio_source, dest_node='boom68_eq')

        cols_count = 15
        rows_count = 5
        decay_bars = np.zeros(cols_count, dtype=float)
        fd = self.proc.stdout.fileno()

        last_route_check = time.time()
        last_default_sink = None
        try:
            last_default_sink = subprocess.check_output(['pactl', 'get-default-sink'], stderr=subprocess.DEVNULL).decode().strip()
        except Exception:
            pass

        while self.running:
            # Check for audio sink changes or lost links every 1.0 second
            now = time.time()
            if now - last_route_check >= 1.0:
                last_route_check = now
                need_reroute = False
                if self.audio_source == 'auto':
                    try:
                        cur_sink = subprocess.check_output(['pactl', 'get-default-sink'], stderr=subprocess.DEVNULL).decode().strip()
                        if cur_sink != last_default_sink:
                            last_default_sink = cur_sink
                            need_reroute = True
                    except Exception:
                        pass

                # Also verify if boom68_eq still has incoming links
                if not need_reroute:
                    try:
                        links = subprocess.check_output(['pw-link', '-I', '-l'], stderr=subprocess.DEVNULL).decode()
                        if not any('boom68_eq:input' in l for l in links.splitlines()):
                            need_reroute = True
                    except Exception:
                        pass

                if need_reroute:
                    route_pipewire_node(self.audio_source, dest_node='boom68_eq')

            # Wait for data with short timeout
            r, _, _ = select.select([fd], [], [], 0.04)
            if not r or not self.running:
                continue

            try:
                # Read all available bytes from pipe to completely drain backlog
                raw = os.read(fd, 4096)
            except Exception:
                break

            if not raw or len(raw) < cols_count:
                continue

            # Take only the newest, freshest 15-byte frame
            rem = len(raw) % cols_count
            end = len(raw) - rem
            if end < cols_count:
                continue
            latest_bytes = raw[end - cols_count : end]

            raw_vals = np.frombuffer(latest_bytes, dtype=np.uint8).astype(float)
            scaled_vals = (raw_vals / 255.0) * self.sensitivity

            # Fast attack, instant reaction
            decay_bars = np.maximum(decay_bars * 0.65, scaled_vals)

            rgb_map = {}
            cr, cg, cb = self.custom_color

            if self.mode == "bars":
                for col_idx in range(cols_count):
                    energy = min(1.0, decay_bars[col_idx])
                    active_height = energy * rows_count # 0.0 .. 5.0

                    for r_idx in range(rows_count):
                        inverted_row = (rows_count - 1) - r_idx
                        if col_idx < len(KEY_MATRIX[inverted_row]):
                            led_id = KEY_MATRIX[inverted_row][col_idx]
                            level = active_height - r_idx

                            if level >= 1.0:
                                frac = 1.0
                            elif level > 0:
                                frac = level
                            else:
                                frac = 0.0

                            if frac <= 0.05:
                                rgb_map[led_id] = (0, 0, 0)
                            elif self.color_mode == "rainbow":
                                if r_idx <= 1:
                                    base = (0, 255, 60)
                                elif r_idx <= 3:
                                    base = (255, 200, 0)
                                else:
                                    base = (255, 0, 100)
                                rgb_map[led_id] = (int(base[0]*frac), int(base[1]*frac), int(base[2]*frac))
                            else:
                                intensity = 0.4 + 0.6 * (r_idx / max(1, rows_count - 1))
                                if r_idx == 4 and frac > 0.8:
                                    rgb_map[led_id] = (255, 255, 255)
                                else:
                                    rgb_map[led_id] = (
                                        int(min(255, cr * intensity * frac)),
                                        int(min(255, cg * intensity * frac)),
                                        int(min(255, cb * intensity * frac))
                                    )

            elif self.mode == "pulse":
                bass_energy = min(1.0, np.mean(decay_bars[:4]) * 1.3)
                mid_energy = min(1.0, np.mean(decay_bars[4:10]))

                for r_idx, row in enumerate(KEY_MATRIX):
                    for c_idx, led_id in enumerate(row):
                        dist = np.sqrt((c_idx - 7.0)**2 + (r_idx - 2.0)**2) / 8.0
                        glow = max(0.0, 1.0 - dist) * bass_energy
                        intensity = max(0.0, min(1.0, glow * 0.90 + mid_energy * 0.25))

                        if intensity <= 0.03:
                            rgb_map[led_id] = (0, 0, 0)
                        elif self.color_mode == "rainbow":
                            hue = (dist * 0.5 + time.time() * 0.8) % 1.0
                            r, g, b = hsv_to_rgb(hue, 1.0, intensity)
                            rgb_map[led_id] = (r, g, b)
                        else:
                            rgb_map[led_id] = (
                                int(min(255, cr * intensity)),
                                int(min(255, cg * intensity)),
                                int(min(255, cb * intensity))
                            )

            elif self.mode == "wave":
                phase = (time.time() * 4.5) % (2 * np.pi)
                for r_idx, row in enumerate(KEY_MATRIX):
                    for c_idx, led_id in enumerate(row):
                        col_val = min(1.0, decay_bars[min(c_idx, cols_count - 1)])
                        if self.color_mode == "rainbow":
                            hue = (c_idx / 15.0 + phase / (2*np.pi)) % 1.0
                            r, g, b = hsv_to_rgb(hue, 1.0, col_val)
                            rgb_map[led_id] = (r, g, b)
                        else:
                            wave_amp = (np.sin(c_idx * 0.6 + phase) + 1.0) / 2.0
                            intensity = max(0.0, min(1.0, col_val * 0.75 + wave_amp * 0.25 * col_val))
                            rgb_map[led_id] = (
                                int(min(255, cr * intensity)),
                                int(min(255, cg * intensity)),
                                int(min(255, cb * intensity))
                            )

            self._send_rgb_buffer(rgb_map)

def hsv_to_rgb(h, s, v):
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i %= 6
    if i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    else: r, g, b = v, p, q
    return int(r * 255), int(g * 255), int(b * 255)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Langtu BOOM68 Audio Reactive Visualizer")
    parser.add_argument("--mode", "-m", choices=["bars", "pulse", "wave"], default="bars",
                        help="Visualizer style (bars, pulse, wave)")
    parser.add_argument("--color", "-c", default="255,20,147",
                        help="RGB color as R,G,B or 'rainbow' (default: 255,20,147 pink)")
    parser.add_argument("--order", choices=["RGB", "BGR"], default="RGB",
                        help="Color channel order (default: RGB, use BGR if red/blue are inverted)")
    parser.add_argument("--source", "-S", default="auto",
                        help="Audio process or device name (e.g. Zen, vesktop, or 'auto')")
    parser.add_argument("--sensitivity", "-s", type=float, default=1.5,
                        help="Audio sensitivity multiplier (default: 1.5)")
    parser.add_argument("--fps", type=int, default=60,
                        help="Frame rate updates per second (default: 60)")
    parser.add_argument("--list-sources", action="store_true",
                        help="List active audio processes and devices")
    args = parser.parse_args()

    if args.list_sources:
        print("Active Audio Sources:")
        for k, v in get_audio_targets():
            print(f"  [{k}] -> {v}")
        sys.exit(0)

    NAMED_COLORS = {
        "pink": (255, 20, 147),
        "cyan": (0, 255, 255),
        "purple": (160, 32, 240),
        "green": (0, 255, 60),
        "red": (255, 0, 20),
        "blue": (0, 120, 255),
        "yellow": (255, 180, 0),
        "white": (255, 255, 255),
        "orange": (255, 120, 0),
        "magenta": (255, 0, 255),
    }

    c_raw = args.color.strip().lower()
    if c_raw == "rainbow":
        cm = "rainbow"
        cc = (255, 20, 147)
    elif c_raw in NAMED_COLORS:
        cm = "custom"
        cc = NAMED_COLORS[c_raw]
    elif c_raw.startswith("#") or (len(c_raw) == 6 and all(c in "0123456789abcdef" for c in c_raw)):
        clean = c_raw.lstrip("#")
        cm = "custom"
        cc = (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))
    elif "," in c_raw:
        cm = "custom"
        parts = [int(x.strip()) for x in c_raw.split(",")]
        cc = (parts[0], parts[1], parts[2])
    else:
        cm = "custom"
        cc = (255, 20, 147)

    engine = AudioEqualizerEngine(
        mode=args.mode,
        sensitivity=args.sensitivity,
        fps=args.fps,
        color_mode=cm,
        custom_color=cc,
        color_order=args.order,
        audio_source=args.source
    )

    def handle_sig(sig, frame):
        print("\nStopping audio visualizer and restoring backlight...")
        engine.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    print(f"🎵 Langtu BOOM68 Zero-Lag Equalizer Started!")
    print(f"Mode: {args.mode} | Source: {args.source} | Color: {args.color} | Order: {args.order}")
    print("Press Ctrl+C to exit.")

    ok = engine.start()
    if not ok:
        sys.exit(1)

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
