# boom68-ctl (Langtu BOOM68 / HE68 Linux Driver Suite)

Linux TUI / CLI драйвер и утилита управления для магнитной клавиатуры **Langtu BOOM68 / HE68** (USB Vendor/Product `0c45:80b5`, Microdia / HFD HID).

---

## Возможности

- **🩸 Blood Noir TUI**: Полноэкранный интерактивный интерфейс в терминале с темой *Blood Noir* (`#e62544` crimson, `#b8142f` blood, `#8f254b` wine), поддержкой 256-color fallback и встроенным ASCII/ANSI арт-рендером (`HOLY VIBECODE`).
- **⚡ Fast CLI**: Мгновенное управление подсветкой из терминала, bash-скриптов и хоткеев оконного менеджера (i3, Hyprland, Sway, GNOME, KDE).
- **🔊 Realtime Audio Equalizer**: Реактивная цветомузыка на Cava + PipeWire с прямой записью в USB HID без задержек. Умное авто-отслеживание источника звука (при переключении между наушниками и колонками).
- **💡 Аппаратная RGB-полоса**: Прошивка биндов верхней светодиодной полосы в память контроллера (`Fn+L-Alt`, `Fn+R-Alt`, `Fn+Стрелки`).
- **⚙️ Udev правила**: Безопасный доступ к `/dev/hidraw*` без необходимости запуска от `sudo`.

---

## Структура проекта

| Файл | Описание |
| :--- | :--- |
| `boom68_cli.py` | Единая точка входа CLI и TUI диспетчер (`boom68`) |
| `boom68_tui.py` | Интерактивный терминальный интерфейс (curses, Blood Noir) |
| `boom68_ctl.py` | Низкоуровневый HID-драйвер протокола клавиатуры |
| `boom68_visualizer.py` | Демон аудио-визуализатора (Cava + PipeWire) |
| `99-langtu-boom68.rules` | Udev-правило для непривилегированного доступа к HID |
| `install.sh` | Скрипт автоматической установки |
| `uninstall.sh` | Чистый деинсталлятор |

---

## Установка

```bash
git clone <URL_РЕПОЗИТОРИЯ>
cd boom68-ctl
chmod +x install.sh
./install.sh
```

После установки утилита доступна глобально как команда `boom68`.

---

## Использование

### 1. Интерактивный TUI
Запуск интерфейса:
```bash
boom68
# или
boom68 tui
```
**Навигация:**
- `1..4` — переключение вкладок (Клавиши, Эквалайзер, Полоса, Инфо).
- `Tab` / `Shift+Tab` / `↑` / `↓` — выбор параметров.
- `←` / `→` — изменение значений (яркость, скорость, режимы, цвета).
- `Enter` — применить / прошить бинды / запустить эквалайзер.
- `q` — выход.

### 2. Быстрый CLI
```bash
# Статус устройства
boom68 status

# Включение / выключение подсветки
boom68 on
boom68 off

# Смена режима и цвета
boom68 set --mode breathing --color "#e62544"
boom68 set --mode static --color cyan --brightness 6

# Список режимов
boom68 modes

# Управление эквалайзером (фоновый демон)
boom68 eq start -d --mode bars --color crimson
boom68 eq status
boom68 eq stop
boom68 eq sources

# Прошивка биндов верхней полосы
boom68 lightbar restore
```
