#!/usr/bin/env python3
"""
Language: Python 3
Filename: boom68_tui.py
Platform: Linux
Target: Langtu BOOM68 / HE68 Interactive Terminal User Interface (TUI)
"""

import os
import sys
import time
import curses
import signal
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import boom68_ctl
import boom68_visualizer

PID_FILE = "/tmp/boom68_eq.pid"

# BloodNoir Color Palette presets for keyboard
COLOR_PALETTE = [
    ("Crimson", 230, 37, 68, 1),
    ("Blood Red", 184, 20, 47, 2),
    ("Wine Noir", 143, 37, 75, 4),
    ("Ruby Rose", 217, 75, 104, 3),
    ("Muted Rose", 199, 110, 119, 6),
    ("Pale Lavender", 184, 178, 204, 13),
    ("Cyan Неон", 0, 255, 255, 7),
    ("Чистый Белый", 255, 255, 255, 7),
]

EQ_STYLES = [
    ("bars", "📊 Столбцы частот (Bars)"),
    ("pulse", "💥 Пульсация баса (Pulse)"),
    ("wave", "🌊 Звуковая волна (Wave)"),
]

TABS = ["💡 Подсветка", "🎵 Эквалайзер", "✨ RGB-полоса", "ℹ️ Инфо"]

def is_eq_running():
    if not os.path.exists(PID_FILE):
        return False, None
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True, pid
    except (OSError, ValueError):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass
        return False, None

def stop_eq():
    running, pid = is_eq_running()
    if not running:
        return
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(15):
            time.sleep(0.05)
            try:
                os.kill(pid, 0)
            except OSError:
                break
        else:
            os.kill(pid, signal.SIGKILL)
    except Exception:
        pass
    if os.path.exists(PID_FILE):
        try:
            os.remove(PID_FILE)
        except Exception:
            pass

def start_eq(mode="bars", source="auto", sensitivity=1.5, fps=60, color_str="pink", order="RGB"):
    stop_eq()
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "boom68_visualizer.py"),
        "--mode", mode,
        "--source", source,
        "--sensitivity", str(sensitivity),
        "--fps", str(fps),
        "--order", order,
        "--color", color_str
    ]
    log_file = open("/tmp/boom68_eq.log", "w")
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file, start_new_session=True)
    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))
    return proc.pid

class Boom68TUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.dev_node = None
        self.active_tab = 0
        self.focus_index = 0
        self.message = ""
        self.message_time = 0

        # Backlight State
        self.state = {
            "mode": 1,
            "mode_key": "static",
            "r": 230, "g": 37, "b": 68,
            "colorMode": 0,
            "brightness": 5,
            "speed": 3,
            "direction": 0,
            "order": "RGB",
            "is_on": True,
        }

        # Equalizer Settings
        self.eq_state = {
            "mode": "bars",
            "source": "auto",
            "sensitivity": 1.5,
            "color": "crimson",
            "rainbow": False,
        }
        self.audio_sources = [("auto", "🔊 Весь системный звук (Общий микс)")]
        self.last_sources_update = 0

        # Lightbar State
        self.lb_fn_restored = False

        # Image Cache (Tab 4)
        self.img_cache = None
        self.img_pair_cache = {}
        self.next_pair_id = 40

        self.setup_curses()
        self.load_device_state()
        self.refresh_audio_sources()

    def setup_curses(self):
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.nodelay(True)
        self.stdscr.timeout(100) # 100ms non-blocking

        # Initialize Blood Noir theme
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()

            def c1000(hex_c):
                h = hex_c.lstrip("#")
                return (
                    int(int(h[0:2], 16) * 1000 / 255),
                    int(int(h[2:4], 16) * 1000 / 255),
                    int(int(h[4:6], 16) * 1000 / 255),
                )

            can_change = curses.can_change_color()

            if can_change and curses.COLORS >= 35:
                # Custom color slots from BloodNoir.sublime-color-scheme
                curses.init_color(20, *c1000("#e62544")) # crimson
                curses.init_color(21, *c1000("#b8142f")) # blood
                curses.init_color(22, *c1000("#8f254b")) # wine
                curses.init_color(23, *c1000("#d94b68")) # ruby
                curses.init_color(24, *c1000("#8f98a3")) # ash
                curses.init_color(25, *c1000("#b8b2cc")) # pale_lavender
                curses.init_color(26, *c1000("#c76e77")) # muted_rose
                curses.init_color(27, *c1000("#ece8eb")) # fg
                curses.init_color(28, *c1000("#708284")) # fg_subtle
                curses.init_color(29, *c1000("#3a131b")) # selection
                curses.init_color(30, *c1000("#8f254b")) # border / wine accent
                curses.init_color(31, *c1000("#100f12")) # bg
                curses.init_color(32, *c1000("#1a181e")) # bg_highlight

                c_crimson = 20
                c_blood = 21
                c_wine = 22
                c_ruby = 23
                c_ash = 24
                c_lavender = 25
                c_rose = 26
                c_fg = 27
                c_subtle = 28
                c_sel = 29
                c_border = 30
                c_bg_hl = 32
            else:
                # Accurate 256-color fallback
                c_crimson = 197
                c_blood = 160
                c_wine = 89
                c_ruby = 168
                c_ash = 245
                c_lavender = 183
                c_rose = 132
                c_fg = 255
                c_subtle = 243
                c_sel = 52
                c_border = 89
                c_bg_hl = 234

            # Pairs: (ID, FG, BG)
            curses.init_pair(1, c_crimson, -1)             # Crimson (primary neon accent)
            curses.init_pair(2, c_blood, -1)               # Blood (deep red)
            curses.init_pair(3, c_ruby, -1)                # Ruby (bright highlight)
            curses.init_pair(4, c_wine, -1)                # Wine (accent)
            curses.init_pair(5, c_border, -1)              # Border (gothic wine frame)
            curses.init_pair(6, c_rose, -1)                # Muted rose (secondary)
            curses.init_pair(7, c_fg, -1)                  # Ghost white FG (#ece8eb)
            curses.init_pair(8, c_fg, c_sel)               # Selection (#ece8eb on #3a131b)
            curses.init_pair(9, c_fg, c_crimson)           # Active badge (white on crimson)
            curses.init_pair(10, c_fg, c_wine)             # Secondary badge (white on wine)
            curses.init_pair(11, c_fg, c_blood)            # Selected tab (white on blood red)
            curses.init_pair(12, c_subtle, -1)             # Subtle text (#708284)
            curses.init_pair(13, c_lavender, -1)           # Pale lavender
            curses.init_pair(14, c_subtle, c_bg_hl)        # Footer (subtle on bg_highlight)

            self.prepare_image("/home/meth/boom68-ctl/1.jpg", tw=28, th=28)

    def show_msg(self, text):
        self.message = text
        self.message_time = time.time()

    def get_fd(self):
        if not self.dev_node:
            self.dev_node = boom68_ctl.find_hidraw_device()
        if not self.dev_node:
            return None
        try:
            return os.open(self.dev_node, os.O_RDWR)
        except Exception:
            return None

    def load_device_state(self):
        fd = self.get_fd()
        if fd is None:
            self.show_msg("Клавиатура не подключена!")
            return
        try:
            eff = boom68_ctl.get_current_effect(fd)
            if eff:
                self.state["mode"] = eff["mode"]
                rev = {v: k for k, v in boom68_ctl.PRESET_MODES.items()}
                self.state["mode_key"] = rev.get(eff["mode"], "static")
                self.state["r"] = eff["red"]
                self.state["g"] = eff["green"]
                self.state["b"] = eff["blue"]
                self.state["colorMode"] = eff["colorMode"]
                self.state["brightness"] = eff["brightness"]
                self.state["speed"] = eff["speed"]
                self.state["direction"] = eff["direction"]
                self.state["is_on"] = (eff["mode"] != 0)
        finally:
            os.close(fd)

    def apply_state(self):
        fd = self.get_fd()
        if fd is None:
            self.show_msg("Ошибка: устройство недоступно")
            return
        try:
            mode_num = boom68_ctl.PRESET_MODES.get(self.state["mode_key"], 1)
            if not self.state["is_on"]:
                mode_num = 0

            boom68_ctl.set_led_effect(
                fd,
                mode=mode_num,
                r=self.state["r"],
                g=self.state["g"],
                b=self.state["b"],
                color_mode=self.state["colorMode"],
                brightness=self.state["brightness"],
                speed=self.state["speed"],
                direction=self.state["direction"],
                color_order=self.state["order"]
            )
            self.show_msg("✔ Настройки подсветки применены")
        finally:
            os.close(fd)

    def refresh_audio_sources(self):
        now = time.time()
        if now - self.last_sources_update > 2.5:
            targets = boom68_visualizer.get_audio_targets()
            if targets:
                self.audio_sources = targets
            self.last_sources_update = now

    def run(self):
        while True:
            self.refresh_audio_sources()
            self.draw()
            ch = self.stdscr.getch()
            if ch == -1:
                continue
            if ch in (ord('q'), ord('Q'), 27): # Q or ESC
                break
            self.handle_input(ch)

    def handle_input(self, ch):
        # Global hotkeys
        if ch == ord('\t'): # Tab key
            self.active_tab = (self.active_tab + 1) % len(TABS)
            self.focus_index = 0
            return
        if ch in (ord('1'), ord('2'), ord('3'), ord('4')):
            self.active_tab = ch - ord('1')
            self.focus_index = 0
            return
        if ch in (ord('o'), ord('O')):
            self.state["is_on"] = not self.state["is_on"]
            self.apply_state()
            return

        # Tab specific controls
        if self.active_tab == 0:
            self.handle_lighting_input(ch)
        elif self.active_tab == 1:
            self.handle_equalizer_input(ch)
        elif self.active_tab == 2:
            self.handle_lightbar_input(ch)
        elif self.active_tab == 3:
            if ch in (curses.KEY_UP, ord('k')):
                self.focus_index = max(0, self.focus_index - 1)
            elif ch in (curses.KEY_DOWN, ord('j')):
                self.focus_index = min(10, self.focus_index + 1)

    # ---------------- TAB 0: LIGHTING ----------------
    def handle_lighting_input(self, ch):
        # Focus items in Tab 0:
        # 0: Режим анимации (список)
        # 1: Радуга / Свой цвет
        # 2: Быстрая палитра
        # 3: Яркость
        # 4: Скорость
        # 5: Порядок каналов (RGB/BGR)
        modes_list = list(boom68_ctl.PRESET_MODES.keys())

        if ch in (curses.KEY_UP, ord('k')):
            self.focus_index = max(0, self.focus_index - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            self.focus_index = min(5, self.focus_index + 1)

        elif ch in (curses.KEY_LEFT, ord('h')):
            if self.focus_index == 0:
                cur_idx = modes_list.index(self.state["mode_key"]) if self.state["mode_key"] in modes_list else 0
                self.state["mode_key"] = modes_list[(cur_idx - 1) % len(modes_list)]
                self.apply_state()
            elif self.focus_index == 1:
                self.state["colorMode"] = 1 - self.state["colorMode"]
                self.apply_state()
            elif self.focus_index == 3:
                self.state["brightness"] = max(1, self.state["brightness"] - 1)
                self.apply_state()
            elif self.focus_index == 4:
                self.state["speed"] = max(1, self.state["speed"] - 1)
                self.apply_state()
            elif self.focus_index == 5:
                self.state["order"] = "BGR" if self.state["order"] == "RGB" else "RGB"
                self.apply_state()

        elif ch in (curses.KEY_RIGHT, ord('l')):
            if self.focus_index == 0:
                cur_idx = modes_list.index(self.state["mode_key"]) if self.state["mode_key"] in modes_list else 0
                self.state["mode_key"] = modes_list[(cur_idx + 1) % len(modes_list)]
                self.apply_state()
            elif self.focus_index == 1:
                self.state["colorMode"] = 1 - self.state["colorMode"]
                self.apply_state()
            elif self.focus_index == 3:
                self.state["brightness"] = min(6, self.state["brightness"] + 1)
                self.apply_state()
            elif self.focus_index == 4:
                self.state["speed"] = min(6, self.state["speed"] + 1)
                self.apply_state()
            elif self.focus_index == 5:
                self.state["order"] = "BGR" if self.state["order"] == "RGB" else "RGB"
                self.apply_state()

        elif ch in (curses.KEY_ENTER, 10, 13, ord(' ')):
            if self.focus_index == 1:
                self.state["colorMode"] = 1 - self.state["colorMode"]
                self.apply_state()
            elif self.focus_index == 2:
                # Cycle palette color
                cur_r, cur_g, cur_b = self.state["r"], self.state["g"], self.state["b"]
                idx = 0
                for i, (_, r, g, b, _) in enumerate(COLOR_PALETTE):
                    if (r, g, b) == (cur_r, cur_g, cur_b):
                        idx = (i + 1) % len(COLOR_PALETTE)
                        break
                _, r, g, b, _ = COLOR_PALETTE[idx]
                self.state["r"], self.state["g"], self.state["b"] = r, g, b
                self.state["colorMode"] = 0
                self.apply_state()
            elif self.focus_index == 5:
                self.state["order"] = "BGR" if self.state["order"] == "RGB" else "RGB"
                self.apply_state()

    # ---------------- TAB 1: EQUALIZER ----------------
    def handle_equalizer_input(self, ch):
        # Focus items in Tab 1:
        # 0: Включить/Выключить EQ
        # 1: Стиль (bars, pulse, wave)
        # 2: Источник звука (auto, Zen, Spotify...)
        # 3: Чувствительность (0.5 - 4.0)
        # 4: Цвет эквалайзера (радуга / палитра)

        if ch in (curses.KEY_UP, ord('k')):
            self.focus_index = max(0, self.focus_index - 1)
        elif ch in (curses.KEY_DOWN, ord('j')):
            self.focus_index = min(4, self.focus_index + 1)

        elif ch in (curses.KEY_LEFT, ord('h')):
            if self.focus_index == 1:
                cur = [s[0] for s in EQ_STYLES].index(self.eq_state["mode"])
                self.eq_state["mode"] = EQ_STYLES[(cur - 1) % len(EQ_STYLES)][0]
                self.restart_eq_if_active()
            elif self.focus_index == 2:
                s_ids = [s[0] for s in self.audio_sources]
                cur = s_ids.index(self.eq_state["source"]) if self.eq_state["source"] in s_ids else 0
                self.eq_state["source"] = s_ids[(cur - 1) % len(s_ids)]
                self.restart_eq_if_active()
            elif self.focus_index == 3:
                self.eq_state["sensitivity"] = max(0.5, round(self.eq_state["sensitivity"] - 0.2, 1))
                self.restart_eq_if_active()
            elif self.focus_index == 4:
                self.cycle_eq_color(reverse=True)

        elif ch in (curses.KEY_RIGHT, ord('l')):
            if self.focus_index == 1:
                cur = [s[0] for s in EQ_STYLES].index(self.eq_state["mode"])
                self.eq_state["mode"] = EQ_STYLES[(cur + 1) % len(EQ_STYLES)][0]
                self.restart_eq_if_active()
            elif self.focus_index == 2:
                s_ids = [s[0] for s in self.audio_sources]
                cur = s_ids.index(self.eq_state["source"]) if self.eq_state["source"] in s_ids else 0
                self.eq_state["source"] = s_ids[(cur + 1) % len(s_ids)]
                self.restart_eq_if_active()
            elif self.focus_index == 3:
                self.eq_state["sensitivity"] = min(4.0, round(self.eq_state["sensitivity"] + 0.2, 1))
                self.restart_eq_if_active()
            elif self.focus_index == 4:
                self.cycle_eq_color(reverse=False)

        elif ch in (curses.KEY_ENTER, 10, 13, ord(' ')):
            if self.focus_index == 0:
                running, _ = is_eq_running()
                if running:
                    stop_eq()
                    self.show_msg("⏹ Эквалайзер остановлен")
                else:
                    col = "rainbow" if self.eq_state["rainbow"] else self.eq_state["color"]
                    pid = start_eq(
                        mode=self.eq_state["mode"],
                        source=self.eq_state["source"],
                        sensitivity=self.eq_state["sensitivity"],
                        color_str=col,
                        order=self.state["order"]
                    )
                    self.show_msg(f"▶ Эквалайзер запущен (PID {pid})")
            elif self.focus_index == 1:
                cur = [s[0] for s in EQ_STYLES].index(self.eq_state["mode"])
                self.eq_state["mode"] = EQ_STYLES[(cur + 1) % len(EQ_STYLES)][0]
                self.restart_eq_if_active()
            elif self.focus_index == 2:
                s_ids = [s[0] for s in self.audio_sources]
                cur = s_ids.index(self.eq_state["source"]) if self.eq_state["source"] in s_ids else 0
                self.eq_state["source"] = s_ids[(cur + 1) % len(s_ids)]
                self.restart_eq_if_active()
            elif self.focus_index == 4:
                self.cycle_eq_color()

        elif ch in (ord('r'), ord('R')):
            self.refresh_audio_sources()
            self.show_msg("🔄 Список аудиопотоков обновлен")

    def cycle_eq_color(self, reverse=False):
        color_choices = ["rainbow", "cyan", "pink", "purple", "green", "red", "yellow", "white"]
        cur = "rainbow" if self.eq_state["rainbow"] else self.eq_state["color"]
        cur_idx = color_choices.index(cur) if cur in color_choices else 0
        step = -1 if reverse else 1
        new_c = color_choices[(cur_idx + step) % len(color_choices)]
        if new_c == "rainbow":
            self.eq_state["rainbow"] = True
        else:
            self.eq_state["rainbow"] = False
            self.eq_state["color"] = new_c
        self.restart_eq_if_active()

    def restart_eq_if_active(self):
        running, _ = is_eq_running()
        if running:
            col = "rainbow" if self.eq_state["rainbow"] else self.eq_state["color"]
            start_eq(
                mode=self.eq_state["mode"],
                source=self.eq_state["source"],
                sensitivity=self.eq_state["sensitivity"],
                color_str=col,
                order=self.state["order"]
            )
            self.show_msg("🔄 Эквалайзер перезапущен с новыми параметрами")

    # ---------------- TAB 2: LIGHTBAR ----------------
    def handle_lightbar_input(self, ch):
        if ch in (curses.KEY_ENTER, 10, 13, ord(' ')):
            fd = self.get_fd()
            if fd:
                try:
                    ok = boom68_ctl.restore_lightbar_fn_bindings(fd)
                    self.lb_fn_restored = ok
                    if ok:
                        self.show_msg("⚡ Fn-клавиши полосы успешно прошиты в клавиатуру!")
                    else:
                        self.show_msg("❌ Ошибка записи биндов в память контроллера")
                finally:
                    os.close(fd)

    def safe_addstr(self, y, x, text, attr=0):
        h, w = self.stdscr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w - 1:
            return
        avail = w - x - 1
        if avail <= 0:
            return
        if len(text) > avail:
            text = text[:avail]
        try:
            self.stdscr.addstr(y, x, text, attr)
        except curses.error:
            pass

    # ---------------- DRAWING (BLOOD NOIR THEME) ----------------
    def draw_box(self, y1, x1, y2, x2):
        try:
            self.stdscr.attron(curses.color_pair(5)) # Blood Noir Wine Border (#8f254b)
            self.stdscr.addch(y1, x1, "╭")
            self.stdscr.addch(y1, x2, "╮")
            self.stdscr.addch(y2, x1, "╰")
            self.stdscr.addch(y2, x2, "╯")
            for x in range(x1 + 1, x2):
                self.stdscr.addch(y1, x, "─")
                self.stdscr.addch(y2, x, "─")
            for y in range(y1 + 1, y2):
                self.stdscr.addch(y, x1, "│")
                self.stdscr.addch(y, x2, "│")
            self.stdscr.attroff(curses.color_pair(5))
        except curses.error:
            pass

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 22 or w < 65:
            self.safe_addstr(0, 0, "Увеличь окно терминала (мин. 65x22)", curses.color_pair(1))
            self.stdscr.refresh()
            return

        # 1. Header Box
        self.draw_box(0, 0, 2, w - 1)
        title = "🩸 LANGTU BOOM68 / HE68 CONTROL DASHBOARD 🩸"
        self.safe_addstr(1, max(2, (w - len(title)) // 2), title, curses.A_BOLD | curses.color_pair(1))

        # Status pill in header right
        running, pid = is_eq_running()
        status_txt = f" EQ: 🩸 ON (PID {pid}) " if running else " EQ: ⚪ OFF "
        st_pair = curses.color_pair(9) if running else curses.color_pair(12)
        self.safe_addstr(1, w - len(status_txt) - 3, status_txt, st_pair | curses.A_BOLD)

        # 2. Tabs Row
        tab_x = 2
        for i, name in enumerate(TABS):
            label = f" [{i+1}] {name} "
            if i == self.active_tab:
                self.safe_addstr(3, tab_x, label, curses.color_pair(11) | curses.A_BOLD)
            else:
                self.safe_addstr(3, tab_x, label, curses.color_pair(12))
            tab_x += len(label) + 2

        # 3. Main Content Box
        content_top = 4
        content_bottom = h - 3
        self.draw_box(content_top, 0, content_bottom, w - 1)

        if self.active_tab == 0:
            self.draw_lighting_tab(content_top + 1, 3, w - 6)
        elif self.active_tab == 1:
            self.draw_equalizer_tab(content_top + 1, 3, w - 6)
        elif self.active_tab == 2:
            self.draw_lightbar_tab(content_top + 1, 3, w - 6)
        elif self.active_tab == 3:
            self.draw_info_tab(content_top + 1, 3, w - 6)

        # 4. Message / Notification bar
        if self.message and (time.time() - self.message_time < 4.0):
            self.safe_addstr(h - 3, 3, f"📢 {self.message}", curses.color_pair(3) | curses.A_BOLD)

        # 5. Bottom Footer / Keybindings (Subtle on Bg Highlight)
        footer = " [Tab/1-4] Вкладки  [↑/↓] Пункт  [←/→] Значение  [Space/Enter] Применить  [O] Вкл/Выкл  [Q] Выход "
        self.safe_addstr(h - 2, max(0, (w - len(footer)) // 2), footer, curses.color_pair(14))

        self.stdscr.refresh()

    def draw_lighting_tab(self, y, x, max_w):
        lines = [
            ("Анимация (Режим):", f"< {self.state['mode_key'].upper()} >", 0),
            ("Режим цвета:", "🌈 RGB Радуга" if self.state["colorMode"] == 1 else "🎨 Однотонный", 1),
            ("Текущий цвет:", f"● RGB({self.state['r']}, {self.state['g']}, {self.state['b']}) [#{self.state['r']:02x}{self.state['g']:02x}{self.state['b']:02x}]", 2),
            ("Яркость подсветки:", f"{'★' * self.state['brightness']}{'☆' * (6 - self.state['brightness'])} ({self.state['brightness']}/6)", 3),
            ("Скорость анимации:", f"{'■' * self.state['speed']}{'□' * (6 - self.state['speed'])} ({self.state['speed']}/6)", 4),
            ("Порядок каналов:", f"< {self.state['order']} >", 5),
        ]

        # Power switch banner
        power_str = " [🩸 ПОДСВЕТКА ВКЛЮЧЕНА] " if self.state["is_on"] else " [⚫ ПОДСВЕТКА ВЫКЛЮЧЕНА] "
        power_pair = curses.color_pair(9) if self.state["is_on"] else curses.color_pair(12)
        self.safe_addstr(y, x, power_str, power_pair | curses.A_BOLD)
        self.safe_addstr(y, x + len(power_str) + 2, "(Нажми 'O' для переключения)", curses.color_pair(12))

        y += 2
        for label, val, idx in lines:
            prefix = " ❯ " if self.focus_index == idx else "   "
            attr = curses.color_pair(1) | curses.A_BOLD if self.focus_index == idx else curses.color_pair(7)

            self.safe_addstr(y, x, f"{prefix}{label:<22}", attr)
            val_attr = curses.color_pair(8) | curses.A_BOLD if self.focus_index == idx else curses.color_pair(13) | curses.A_BOLD
            self.safe_addstr(y, x + 26, f" {val} ", val_attr)
            y += 2

        # Palette preview row (Blood Noir themed palette)
        self.safe_addstr(y, x + 3, "Blood Noir Палитра [Enter/Space для выбора]:", curses.color_pair(6) | curses.A_BOLD)
        y += 1
        pal_x = x + 3
        for i, (name, r, g, b, cpair) in enumerate(COLOR_PALETTE):
            if i == 4:
                y += 1
                pal_x = x + 3
            is_active = (r, g, b) == (self.state["r"], self.state["g"], self.state["b"]) and self.state["colorMode"] == 0
            badge = f" [● {name}] " if is_active else f" ● {name} "
            attr = curses.color_pair(8) | curses.A_BOLD if is_active else curses.color_pair(cpair)
            self.safe_addstr(y, pal_x, badge, attr)
            pal_x += len(badge) + 2

    def draw_equalizer_tab(self, y, x, max_w):
        running, pid = is_eq_running()

        # Big toggle status
        if running:
            toggle_btn = f"  ▶ [АКТИВЕН: PID {pid}] - Нажми [SPACE] чтобы остановить  "
            btn_pair = curses.color_pair(9)
        else:
            toggle_btn = "  ⏹ [ВЫКЛЮЧЕН] - Нажми [SPACE] чтобы запустить реакцию на звук  "
            btn_pair = curses.color_pair(8)

        prefix = " ❯" if self.focus_index == 0 else "  "
        self.safe_addstr(y, x, prefix, curses.color_pair(1) | curses.A_BOLD)
        self.safe_addstr(y, x + 3, toggle_btn, btn_pair | curses.A_BOLD)

        y += 3

        st_name = dict(EQ_STYLES).get(self.eq_state["mode"], self.eq_state["mode"])
        src_label = dict(self.audio_sources).get(self.eq_state["source"], self.eq_state["source"])
        if len(src_label) > 40:
            src_label = src_label[:37] + "..."

        col_desc = "🌈 Радужный спектр" if self.eq_state["rainbow"] else f"● {self.eq_state['color'].capitalize()}"

        rows = [
            ("Стиль анимации:", f"< {st_name} >", 1),
            ("Источник аудио:", f"< {src_label} > (Клавиша 'R' - обновить)", 2),
            ("Чувствительность:", f"< {self.eq_state['sensitivity']}x >  [← / →]", 3),
            ("Цвет эквалайзера:", f"< {col_desc} >", 4),
        ]

        for label, val, idx in rows:
            prefix = " ❯ " if self.focus_index == idx else "   "
            attr = curses.color_pair(1) | curses.A_BOLD if self.focus_index == idx else curses.color_pair(7)

            self.safe_addstr(y, x, f"{prefix}{label:<20}", attr)
            val_attr = curses.color_pair(8) | curses.A_BOLD if self.focus_index == idx else curses.color_pair(13) | curses.A_BOLD
            self.safe_addstr(y, x + 24, f" {val} ", val_attr)
            y += 2

        # Visual Equalizer preview simulation bar
        y += 1
        self.safe_addstr(y, x + 3, "Визуализатор PipeWire / Cava:", curses.color_pair(6) | curses.A_BOLD)
        y += 1
        bars_demo = " ▂▃▄▅▆▇█▇▆▅▄▃▂  ▂▃▅▆▇██▇▆▅▄▃▂ ▂▃▄▅▆▇█"
        self.safe_addstr(y, x + 3, bars_demo, curses.color_pair(1) | curses.A_BOLD)

    def draw_lightbar_tab(self, y, x, max_w):
        self.safe_addstr(y, x, "🩸 АППАРАТНАЯ ВЕРХНЯЯ RGB-ПОЛОСА (正面灯条)", curses.color_pair(1) | curses.A_BOLD)
        y += 2

        self.safe_addstr(y, x, "Микроконтроллер Langtu BOOM68 управляет полосой через FN-слой.", curses.color_pair(7))
        y += 2

        # Flash hotkey button
        restore_btn = " ⚡ [ENTER] ПРОШИТЬ И ВОССТАНОВИТЬ FN-КЛАВИШИ ПОЛОСЫ В ПАМЯТЬ КЛАВИАТУРЫ "
        btn_pair = curses.color_pair(9) if self.lb_fn_restored else curses.color_pair(8)
        self.safe_addstr(y, x + 2, restore_btn, btn_pair | curses.A_BOLD)
        y += 3

        self.safe_addstr(y, x, "Таблица горячих клавиш клавиатуры:", curses.color_pair(3) | curses.A_BOLD)
        y += 1

        shortcuts = [
            ("Fn + L-Alt / R-Ctrl", "Переключение ЦВЕТА полосы (Красный, Зеленый, Синий, Белый...)", "ID 29"),
            ("Fn + R-Alt", "Переключение РЕЖИМА/ЭФФЕКТА полосы (Радуга, Дыхание, Выкл...)", "ID 27"),
            ("Fn + ↑ (Вверх)", "ЯРКОСТЬ полосы + (прибавь если полоса погасла)", "ID 66"),
            ("Fn + ↓ (Вниз)", "ЯРКОСТЬ полосы - (уменьшить яркость)", "ID 67"),
            ("Fn + → (Вправо)", "СКОРОСТЬ анимации полосы +", "ID 64"),
            ("Fn + ← (Влево)", "СКОРОСТЬ анимации полосы -", "ID 65"),
        ]

        for keys, desc, fid in shortcuts:
            self.safe_addstr(y, x + 2, f"• {keys:<22}", curses.color_pair(1) | curses.A_BOLD)
            self.safe_addstr(y, x + 26, f" {desc}", curses.color_pair(7))
            self.safe_addstr(y, x + 26 + len(desc) + 2, f"[{fid}]", curses.color_pair(3))
            y += 1

    def rgb_to_256(self, r, g, b):
        if abs(r - g) < 8 and abs(g - b) < 8 and abs(r - b) < 8:
            if r < 8: return 16
            if r > 248: return 231
            return min(255, max(232, 232 + int((r - 8) / 10.5)))
        cr = int(r * 5 / 255 + 0.5)
        cg = int(g * 5 / 255 + 0.5)
        cb = int(b * 5 / 255 + 0.5)
        return min(255, max(16, 16 + 36 * cr + 6 * cg + cb))

    def prepare_image(self, path="/home/meth/boom68-ctl/1.jpg", tw=28, th=28):
        if not os.path.exists(path):
            return
        try:
            from PIL import Image
            im = Image.open(path).convert('RGB')
            im = im.resize((tw, th), Image.Resampling.LANCZOS)
            grid = []
            for y in range(0, th, 2):
                row = []
                for x in range(tw):
                    c1 = self.rgb_to_256(*im.getpixel((x, y)))
                    c2 = self.rgb_to_256(*im.getpixel((x, y + 1)))
                    key = (c1, c2)
                    if key not in self.img_pair_cache:
                        curses.init_pair(self.next_pair_id, c1, c2)
                        self.img_pair_cache[key] = self.next_pair_id
                        self.next_pair_id += 1
                    row.append(self.img_pair_cache[key])
                grid.append(row)
            self.img_cache = grid
        except Exception:
            self.img_cache = None

    def draw_info_tab(self, y, x, max_w):
        h, w = self.stdscr.getmaxyx()
        info_lines = [
            ("Модель устройства:", "Langtu BOOM68 / HE68"),
            ("USB Vendor / Product:", "0c45:80b5 (Microdia)"),
            ("HID Узел:", f"{self.dev_node or 'Не найден'}"),
            ("Звуковой стек:", "PipeWire (Zero-Lag shm)"),
            ("Эквалайзер бэкенд:", "Cava v0.10.x"),
            ("Поддерживаемые плееры:", "Zen, Spotify, Chrome..."),
            ("Авто-watchdog:", "Наушники ⟷ Колонки"),
            ("Тема оформления:", "Blood Noir (#e62544)"),
            ("Udev правило:", "99-langtu-boom68.rules"),
        ]

        self.safe_addstr(y, x, "🩸 СИСТЕМНАЯ ДИАГНОСТИКА И АРХИТЕКТУРА", curses.color_pair(1) | curses.A_BOLD)
        start_y = y + 2

        # 1. Left column: Info table
        curr_y = start_y
        for k, v in info_lines:
            self.safe_addstr(curr_y, x + 2, f"{k:<23}", curses.color_pair(6) | curses.A_BOLD)
            self.safe_addstr(curr_y, x + 26, f"{v}", curses.color_pair(7))
            curr_y += 1

        # 2. Right column: Rendered 1.jpg image with Blood Noir border!
        if self.img_cache:
            img_w = len(self.img_cache[0])
            img_h = len(self.img_cache)
            if w >= 76:
                img_x = max(x + 44, w - img_w - 5)
                box_y = start_y - 1
            else:
                img_x = x + 2
                box_y = curr_y + 1

            if box_y + img_h + 1 < h - 2:
                # Frame box for image
                self.draw_box(box_y, img_x - 1, box_y + img_h + 1, img_x + img_w)
                title = " HOLY VIBECODE "
                title_x = max(img_x, img_x + (img_w - len(title)) // 2)
                self.safe_addstr(box_y, title_x, title, curses.color_pair(3) | curses.A_BOLD)
                # Half-block image pixel rows
                for r_idx, row in enumerate(self.img_cache):
                    for c_idx, pid in enumerate(row):
                        try:
                            self.stdscr.addstr(box_y + 1 + r_idx, img_x + c_idx, "▀", curses.color_pair(pid))
                        except curses.error:
                            pass

def main():
    def curses_runner(stdscr):
        app = Boom68TUI(stdscr)
        app.run()

    try:
        curses.wrapper(curses_runner)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
