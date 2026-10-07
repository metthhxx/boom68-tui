#!/usr/bin/env python3
"""
Language: Python 3
Filename: boom68_cli.py
Platform: Linux
Target: Langtu BOOM68 / HE68 Unified Command Line Suite
"""

import sys
import os
import time
import signal
import argparse
import subprocess

# Ensure local imports work even through symlinks
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import boom68_ctl
import boom68_visualizer

PID_FILE = "/tmp/boom68_eq.pid"
STATE_FILE = "/tmp/boom68_eq.state"

COLOR_NAMES = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "yellow": (255, 255, 0),
    "white": (255, 255, 255),
    "orange": (255, 120, 0),
    "pink": (255, 20, 147),
    "purple": (160, 32, 240),
}

def parse_any_color(c_str):
    """Parses color from name ('cyan', 'pink') or hex ('#00ffaa', 'ff00aa')."""
    if not c_str:
        return (255, 255, 255)
    name = c_str.lower().strip()
    if name in COLOR_NAMES:
        return COLOR_NAMES[name]
    clean = name.lstrip("#")
    if len(clean) == 6:
        return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))
    if len(clean) == 3:
        return (int(clean[0]*2, 16), int(clean[1]*2, 16), int(clean[2]*2, 16))
    raise ValueError(f"Unknown color format '{c_str}'. Use hex (#ff0088) or names: {', '.join(COLOR_NAMES.keys())}")

def get_open_device():
    dev_node = boom68_ctl.find_hidraw_device()
    if not dev_node:
        print("[!] Ошибка: Клавиатура Langtu BOOM68 не найдена в системе.", file=sys.stderr)
        print("    Проверь USB-подключение (/dev/hidraw*).", file=sys.stderr)
        sys.exit(1)
    try:
        fd = os.open(dev_node, os.O_RDWR)
        return dev_node, fd
    except PermissionError:
        print(f"[!] Ошибка доступа к {dev_node}. Нет прав rw.", file=sys.stderr)
        print("    Примени udev правило: sudo cp 99-langtu-boom68.rules /etc/udev/rules.d/ && sudo udevadm trigger", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"[!] Не удалось открыть {dev_node}: {e}", file=sys.stderr)
        sys.exit(1)

def is_eq_running():
    if not os.path.exists(PID_FILE):
        return False, None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True, pid
    except (OSError, ValueError):
        # Process dead, remove stale pid file
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        return False, None

# ----------------- Commands -----------------

def cmd_status(args):
    """Full diagnostic status of keyboard, equalizer, and lightbar."""
    dev_node, fd = get_open_device()
    try:
        info = boom68_ctl.get_current_effect(fd)
        fn_bytes = boom68_ctl.read_fn_keys(fd)
    finally:
        os.close(fd)

    eq_running, eq_pid = is_eq_running()

    print("══════════════════════════════════════════════════════════════════════")
    print(f"  ⌨ Langtu BOOM68 / HE68 Control Center")
    print("══════════════════════════════════════════════════════════════════════")
    print(f"  • Устройство:       {dev_node}")

    if info:
        mode_rev = {v: k for k, v in boom68_ctl.PRESET_MODES.items()}
        mode_name = mode_rev.get(info["mode"], f"unknown ({info['mode']})")
        color_hex = f"#{info['red']:02x}{info['green']:02x}{info['blue']:02x}"
        print(f"  • Подсветка клавиш: {mode_name.upper()} (режим {info['mode']})")
        print(f"  • Цвет:             RGB({info['red']}, {info['green']}, {info['blue']}) [{color_hex}]")
        print(f"  • Режим цвета:      {'🌈 RGB Rainbow' if info['colorMode'] == 1 else 'Однотонный'}")
        print(f"  • Яркость:          {info['brightness']} / 6  {'★' * info['brightness']}")
        print(f"  • Скорость:         {info['speed']} / 6")
        print(f"  • Направление:      {info['direction']}")
    else:
        print("  • Подсветка:        Не удалось прочитать текущий статус")

    print("──────────────────────────────────────────────────────────────────────")
    if eq_running:
        print(f"  • Эквалайзер:       🟢 АКТИВЕН (PID: {eq_pid})")
    else:
        print(f"  • Эквалайзер:       ⚪ Остановлен")

    print("──────────────────────────────────────────────────────────────────────")
    print("  • Верхняя RGB-полоса (正面灯条):")
    if fn_bytes and len(fn_bytes) >= 512:
        lalt_code = fn_bytes[82*4 + 3]
        ralt_code = fn_bytes[84*4 + 3]
        up_code = fn_bytes[90*4 + 3]
        down_code = fn_bytes[89*4 + 3]
        print(f"    - Fn + L-Alt:     {'Цвет полосы (ID 29)' if lalt_code == 29 else f'Функция {lalt_code}'}")
        print(f"    - Fn + R-Alt:     {'Режим полосы (ID 27)' if ralt_code == 27 else f'Функция {ralt_code}'}")
        print(f"    - Fn + Стрелки:   {'Яркость (+/-)' if up_code == 66 and down_code == 67 else 'Настроены'}")
    else:
        print("    - Статус биндов:  Не удалось прочитать FN-слой")
    print("══════════════════════════════════════════════════════════════════════")

def cmd_on(args):
    dev_node, fd = get_open_device()
    try:
        ok = boom68_ctl.set_led_effect(fd, mode=1, r=255, g=255, b=255, color_mode=0, brightness=5)
        print("✔ Подсветка включена (Статичный белый)" if ok else "[!] Ошибка отправки команды")
    finally:
        os.close(fd)

def cmd_off(args):
    dev_node, fd = get_open_device()
    try:
        ok = boom68_ctl.set_led_effect(fd, mode=0, brightness=1)
        print("✔ Подсветка выключена" if ok else "[!] Ошибка отправки команды")
    finally:
        os.close(fd)

def cmd_set(args):
    dev_node, fd = get_open_device()
    try:
        mode_num = boom68_ctl.PRESET_MODES[args.mode]
        color_mode = 1 if args.rgb else 0
        r, g, b = (255, 255, 255)

        if args.color:
            r, g, b = parse_any_color(args.color)
            color_mode = 0
        elif args.rgb:
            color_mode = 1

        ok = boom68_ctl.set_led_effect(
            fd,
            mode=mode_num,
            r=r, g=g, b=b,
            color_mode=color_mode,
            brightness=args.brightness,
            speed=args.speed,
            direction=args.direction,
            color_order=args.order
        )
        if ok:
            col_desc = "🌈 Радуга" if color_mode == 1 else f"#{r:02x}{g:02x}{b:02x}"
            print(f"✔ Применено: режим={args.mode}, цвет={col_desc}, яркость={args.brightness}, скорость={args.speed}, порядок={args.order}")
        else:
            print("[!] Ошибка установки подсветки на клавиатуре.")
    finally:
        os.close(fd)

def cmd_modes(args):
    print("Доступные режимы подсветки клавиш:")
    for m in boom68_ctl.PRESET_MODES.keys():
        print(f"  • {m}")

# ----------------- Equalizer Subcommands -----------------

def cmd_eq_start(args):
    running, pid = is_eq_running()
    if running:
        print(f"[!] Эквалайзер уже запущен (PID {pid}). Для остановки: boom68 eq stop")
        return

    # Color parsing
    if args.color.lower() == "rainbow":
        c_mode = "rainbow"
        c_rgb = (255, 20, 147)
    else:
        c_mode = "custom"
        c_rgb = parse_any_color(args.color)

    if args.daemon:
        cmd = [
            sys.executable,
            os.path.join(SCRIPT_DIR, "boom68_visualizer.py"),
            "--mode", args.mode,
            "--source", args.source,
            "--sensitivity", str(args.sensitivity),
            "--fps", str(args.fps),
            "--order", args.order,
            "--color", f"{c_rgb[0]},{c_rgb[1]},{c_rgb[2]}" if c_mode == "custom" else "rainbow"
        ]
        log_file = open("/tmp/boom68_eq.log", "w")
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, start_new_session=True)
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))
        print(f"✔ Музыкальный эквалайзер запущен в фоне (PID {proc.pid})")
        print(f"  Стиль: {args.mode} | Источник: {args.source} | Чувствительность: {args.sensitivity}")
        print("  Остановить: boom68 eq stop")
    else:
        # Foreground mode
        engine = boom68_visualizer.AudioEqualizerEngine(
            mode=args.mode,
            sensitivity=args.sensitivity,
            fps=args.fps,
            color_mode=c_mode,
            custom_color=c_rgb,
            color_order=args.order,
            audio_source=args.source
        )

        def sig_handler(sig, frame):
            print("\nОстановка эквалайзера и возврат подсветки...")
            engine.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        print(f"🎵 Музыкальный эквалайзер запущен (Интерактивный режим)")
        print(f"  Стиль: {args.mode} | Источник: {args.source} | Порядок: {args.order}")
        print("  Нажми Ctrl+C для выхода.")
        ok = engine.start()
        if not ok:
            sys.exit(1)
        while True:
            time.sleep(1)

def cmd_eq_stop(args):
    running, pid = is_eq_running()
    if not running:
        print("Эквалайзер не запущен.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
        print(f"✔ Эквалайзер (PID {pid}) остановлен, подсветка восстановлена.")
    except Exception as e:
        print(f"[!] Ошибка остановки PID {pid}: {e}")
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

def cmd_eq_sources(args):
    print("Доступные источники звука (PipeWire / ALSA):")
    targets = boom68_visualizer.get_audio_targets()
    for node_id, label in targets:
        print(f"  [{node_id}]  ->  {label}")

# ----------------- Lightbar Subcommands -----------------

def cmd_lightbar_restore(args):
    dev_node, fd = get_open_device()
    try:
        ok = boom68_ctl.restore_lightbar_fn_bindings(fd)
        if ok:
            print("✔ Горячие клавиши верхней RGB-полосы успешно зашиты в контроллер:")
            print("  • Fn + L-Alt:     Переключение цвета полосы (ID 29)")
            print("  • Fn + R-Alt:     Переключение режима/эффекта полосы (ID 27)")
            print("  • Fn + R-Ctrl:    Переключение цвета полосы (ID 29)")
            print("  • Fn + ↑ / ↓:     Яркость полосы (+ / -) (ID 66 / 67)")
            print("  • Fn + → / ←:     Скорость анимации полосы (+ / -) (ID 64 / 65)")
        else:
            print("[!] Не удалось записать настройки в память клавиатуры.")
    finally:
        os.close(fd)

def cmd_lightbar_info(args):
    dev_node, fd = get_open_device()
    try:
        fn_bytes = boom68_ctl.read_fn_keys(fd)
        if not fn_bytes:
            print("[!] Ошибка чтения FN-слоя.")
            return

        print("=== Бинды верхней RGB-полосы в памяти клавиатуры ===")
        labels = {
            82: "Fn + L-Alt",
            84: "Fn + R-Alt",
            87: "Fn + R-Ctrl",
            88: "Fn + ← (Left)",
            89: "Fn + ↓ (Down)",
            90: "Fn + ↑ (Up)",
            91: "Fn + → (Right)",
        }
        func_names = {
            27: "Смена режима/эффекта полосы (ID 27)",
            28: "Регулировка скорости полосы (ID 28)",
            29: "Смена цвета полосы (ID 29)",
            61: "Переключение яркости полосы (ID 61)",
            64: "Скорость полосы + (ID 64)",
            65: "Скорость полосы - (ID 65)",
            66: "Яркость полосы + (ID 66)",
            67: "Яркость полосы - (ID 67)",
        }
        for idx, name in labels.items():
            off = idx * 4
            page, p1, p2, p3 = fn_bytes[off : off + 4]
            fname = func_names.get(p3, f"Функция {p3}") if page == 13 else f"Стандартная кнопка (код {p1})"
            print(f"  {name:16s} -> {fname}")
    finally:
        os.close(fd)

# ----------------- CLI Argument Parser -----------------

def main():
    parser = argparse.ArgumentParser(
        prog="boom68",
        description="⚡ Langtu BOOM68 / HE68 Complete CLI Tool (Lighting, Equalizer, Lightbar)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Доступные команды")

    # Status / Info
    subparsers.add_parser("status", help="Полная диагностика состояния клавиатуры и эквалайзера")
    subparsers.add_parser("info", help="Псевдоним для status")

    # On / Off
    subparsers.add_parser("on", help="Включить подсветку")
    subparsers.add_parser("off", help="Выключить подсветку")

    # Modes list
    subparsers.add_parser("modes", help="Список доступных анимаций подсветки")

    # Set command
    set_p = subparsers.add_parser("set", help="Настройка подсветки клавиш")
    set_p.add_argument("--mode", "-m", choices=list(boom68_ctl.PRESET_MODES.keys()), default="static",
                       help="Режим анимации (по умолч.: static)")
    set_p.add_argument("--color", "-c", default=None,
                       help="Цвет: название (cyan, pink, red...) или HEX (#ff0088)")
    set_p.add_argument("--rgb", action="store_true",
                       help="Включить радужный RGB цикл")
    set_p.add_argument("--brightness", "-b", type=int, choices=range(1, 7), default=5,
                       help="Яркость от 1 до 6")
    set_p.add_argument("--speed", "-s", type=int, choices=range(1, 7), default=3,
                       help="Скорость от 1 до 6")
    set_p.add_argument("--direction", "-d", type=int, choices=[0, 1, 2, 3], default=0,
                       help="Направление эффекта 0-3")
    set_p.add_argument("--order", choices=["RGB", "BGR"], default="RGB",
                       help="Порядок каналов (RGB или инверсия BGR)")

    # Equalizer (eq) command
    eq_p = subparsers.add_parser("eq", help="Управление музыкальным эквалайзером")
    eq_sub = eq_p.add_subparsers(dest="eq_action", help="Действие эквалайзера")

    # eq start
    eq_start_p = eq_sub.add_parser("start", help="Запустить музыкальный эквалайзер")
    eq_start_p.add_argument("--mode", "-m", choices=["bars", "pulse", "wave"], default="bars",
                            help="Стиль: bars (столбцы), pulse (пульсация), wave (волна)")
    eq_start_p.add_argument("--color", "-c", default="pink",
                            help="Цвет: название (pink, cyan...), hex (#00ffcc), или 'rainbow'")
    eq_start_p.add_argument("--source", "-S", default="auto",
                            help="Процесс (Zen, Spotify...) или 'auto' для системного звука")
    eq_start_p.add_argument("--sensitivity", "-s", type=float, default=1.5,
                            help="Чувствительность к басам/громкости (по умолч.: 1.5)")
    eq_start_p.add_argument("--fps", type=int, default=60,
                            help="Частота кадров (по умолч.: 60)")
    eq_start_p.add_argument("--order", choices=["RGB", "BGR"], default="RGB",
                            help="Порядок каналов цвета")
    eq_start_p.add_argument("--daemon", "-d", action="store_true",
                            help="Запустить процесс в фоне (демон)")

    # eq stop
    eq_sub.add_parser("stop", help="Остановить запущенный эквалайзер")

    # eq status
    eq_sub.add_parser("status", help="Проверить статус работы эквалайзера")

    # eq sources
    eq_sub.add_parser("sources", help="Список доступных аудиопотоков и приложений")

    # Lightbar command
    lb_p = subparsers.add_parser("lightbar", help="Управление верхней RGB-полосой")
    lb_sub = lb_p.add_subparsers(dest="lb_action", help="Действие полосы")
    lb_sub.add_parser("restore", help="Прошить аппаратные горячие клавиши в клавиатуру (Fn+Alt, Fn+Стрелки)")
    lb_sub.add_parser("info", help="Показать активные бинды полосы в памяти клавиатуры")

    # TUI command
    subparsers.add_parser("tui", help="Запустить полноэкранный интерактивный TUI-интерфейс")

    args = parser.parse_args()

    if not args.subcommand:
        if sys.stdin.isatty() and sys.stdout.isatty():
            import boom68_tui
            boom68_tui.main()
        else:
            cmd_status(args)
        return

    if args.subcommand == "tui":
        import boom68_tui
        boom68_tui.main()
    elif args.subcommand in ("status", "info"):
        cmd_status(args)
    elif args.subcommand == "on":
        cmd_on(args)
    elif args.subcommand == "off":
        cmd_off(args)
    elif args.subcommand == "set":
        cmd_set(args)
    elif args.subcommand == "modes":
        cmd_modes(args)
    elif args.subcommand == "eq":
        if args.eq_action == "start":
            cmd_eq_start(args)
        elif args.eq_action == "stop":
            cmd_eq_stop(args)
        elif args.eq_action == "sources":
            cmd_eq_sources(args)
        elif args.eq_action == "status":
            running, pid = is_eq_running()
            if running:
                print(f"🟢 Эквалайзер запущен (PID {pid})")
            else:
                print("⚪ Эквалайзер остановлен")
        else:
            eq_p.print_help()
    elif args.subcommand == "lightbar":
        if args.lb_action == "restore":
            cmd_lightbar_restore(args)
        elif args.lb_action == "info":
            cmd_lightbar_info(args)
        else:
            lb_p.print_help()

if __name__ == "__main__":
    main()
