import os
import json
import requests
import time
import threading

# =======================
# ⚙️ НАСТРОЙКИ ПОЛЬЗОВАТЕЛЕЙ
# =======================
SETTINGS_FILENAME = "settings.json"

def save_settings(all_settings):
    try:
        with open(SETTINGS_FILENAME, "w", encoding="utf-8") as f:
            json.dump(all_settings, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Ошибка при сохранении settings.json: {e}")

if os.path.exists(SETTINGS_FILENAME):
    try:
        with open(SETTINGS_FILENAME, "r", encoding="utf-8") as f:
            ALL_SETTINGS = json.load(f)
    except Exception as e:
        print(f"Ошибка чтения settings.json: {e}")
        ALL_SETTINGS = {}
else:
    ALL_SETTINGS = {}

DEFAULT_SETTINGS = {
    "threshold": 6.0,
    "poll_interval": 10,
    "monitoring": False,
    "timeframe": "1m"
}

def get_user_settings(chat_id):
    cid = str(chat_id)
    if cid not in ALL_SETTINGS:
        ALL_SETTINGS[cid] = DEFAULT_SETTINGS.copy()
        save_settings(ALL_SETTINGS)
    return ALL_SETTINGS[cid]


# =======================
# 🔐 TELEGRAM API
# =======================
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except Exception:
    ADMIN_ID = 0

if not TELEGRAM_TOKEN:
    print("⚠️ BOT_TOKEN не задан. Установи его в переменных Railway.")

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None

last_update_id = 0
last_prices = {}

PARAM_NAMES = {
    "threshold": "порог",
    "poll_interval": "интервал",
    "monitoring": "мониторинг",
    "timeframe": "таймфрейм"
}
PARAM_NAMES_RU = {v: k for k, v in PARAM_NAMES.items()}


# =======================
# 📩 Telegram функции
# =======================
def send_message(chat_id, text):
    if not API_URL:
        print(f"send_message: Telegram API не настроен. Сообщение: {text}")
        return
    try:
        r = requests.post(f"{API_URL}/sendMessage", data={"chat_id": chat_id, "text": text})
        if r.status_code != 200:
            print(f"Ошибка Telegram ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")


def get_updates(offset=None, timeout=100):
    if not API_URL:
        return {}
    try:
        resp = requests.get(f"{API_URL}/getUpdates", params={"timeout": timeout, "offset": offset})
        return resp.json()
    except Exception as e:
        print(f"Ошибка получения обновлений: {e}")
        return {}


# =======================
# 📊 Данные MEXC
# =======================
def get_mexc_futures_tickers():
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            print(f"Ошибка MEXC Futures API: {res.status_code}")
            return []
        data = res.json().get("data", [])
        return [t for t in data if isinstance(t, dict) and t.get("symbol", "").endswith("_USDT")]
    except Exception as e:
        print(f"Ошибка MEXC Futures API: {e}")
        return []


# =======================
# 🟢 ГЛОБАЛЬНЫЙ МОНИТОРИНГ
# =======================
def global_monitor():
    global last_prices, ALL_SETTINGS
    print("📡 Глобальный мониторинг запущен.")
    while True:
        try:
            active = [uid for uid, s in ALL_SETTINGS.items() if isinstance(s, dict) and s.get("monitoring")]
            if not active:
                time.sleep(5)
                continue

            poll_intervals = [s.get("poll_interval", 10) for uid, s in ALL_SETTINGS.items() if isinstance(s, dict) and s.get("monitoring")]
            poll_interval = min(poll_intervals) if poll_intervals else 10

            thresholds = [s.get("threshold", 6.0) for uid, s in ALL_SETTINGS.items() if isinstance(s, dict) and s.get("monitoring")]
            global_threshold = min(thresholds) if thresholds else 6.0

            tickers = get_mexc_futures_tickers()
            if not tickers:
                time.sleep(poll_interval)
                continue

            for t in tickers:
                if not isinstance(t, dict):
                    continue

                symbol = t.get("symbol", "").replace("_", "")
                price_str = t.get("lastPrice")
                if not price_str:
                    continue

                try:
                    price = float(price_str)
                except:
                    continue

                prev = last_prices.get(symbol)
                last_prices[symbol] = price

                if prev and prev > 0:
                    change = (price - prev) / prev * 100
                    if abs(change) >= global_threshold:
                        if change > 0:
                            msg = f"🚀 PUMP на {symbol}: +{change:.2f}% — SHORT зона"
                        else:
                            msg = f"💥 DUMP на {symbol}: {change:.2f}% — LONG зона"
                        for uid in active:
                            send_message(uid, msg)

            time.sleep(poll_interval)
        except Exception as e:
            print(f"Ошибка в global_monitor: {e}")
            time.sleep(5)


# =======================
# 🧠 Обработка команд
# =======================
def handle_command(chat_id, text):
    user_settings = get_user_settings(chat_id)
    parts = text.strip().split()
    if not parts:
        return None
    cmd = parts[0].lower()

    if cmd == "/start":
        if user_settings.get("monitoring"):
            return "⚠️ Мониторинг уже запущен."
        user_settings["monitoring"] = True
        save_settings(ALL_SETTINGS)
        return "✅ Ты подключён к общему мониторингу сигналов MEXC!"

    elif cmd == "/stop":
        user_settings["monitoring"] = False
        save_settings(ALL_SETTINGS)
        return "🛑 Мониторинг остановлен."

    elif cmd == "/test":
        return "🤖 Бот работает и подключен к MEXC Futures!"

    elif cmd == "/settings":
        lines = []
        for k, v in user_settings.items():
            ru_name = PARAM_NAMES.get(k, k)
            if k == "threshold":
                lines.append(f"{ru_name}: {v}%")
            elif k == "monitoring":
                lines.append(f"{ru_name}: {'Включен' if v else 'Выключен'}")
            else:
                lines.append(f"{ru_name}: {v}")
        return "⚙️ Текущие настройки:\n" + "\n".join(lines)

    elif cmd == "/set":
        if len(parts) < 3:
            return "Использование: /set параметр значение\nПараметры: порог, интервал, таймфрейм"
        param_input = parts[1].lower()
        value = parts[2]
        if param_input in PARAM_NAMES_RU:
            key = PARAM_NAMES_RU[param_input]
        elif param_input in user_settings:
            key = param_input
        else:
            return "Неизвестный параметр.\nДоступные: порог, интервал, таймфрейм"

        try:
            if key in ("threshold", "poll_interval"):
                user_settings[key] = float(value)
            elif key == "timeframe":
                user_settings[key] = str(value)
            save_settings(ALL_SETTINGS)
            ru_name = PARAM_NAMES.get(key, key)
            return f"✅ {ru_name} обновлён на {value}"
        except ValueError:
            return "Некорректное значение."

    elif cmd == "/help":
        return (
            "📘 Команды:\n"
            "/start — включить мониторинг\n"
            "/stop — выключить мониторинг\n"
            "/settings — показать настройки\n"
            "/set параметр значение — изменить параметр\n"
            "/test — проверить работу\n"
            "/help — список команд"
        )

    else:
        return "❓ Неизвестная команда. Введи /help."


# =======================
# 🚀 Основной цикл Telegram polling
# =======================
def main():
    global last_update_id
    print("🚀 Telegram polling запущен...")
    while True:
        updates = get_updates(last_update_id + 1)
        if "result" in updates:
            for update in updates["result"]:
                try:
                    last_update_id = update["update_id"]
                    if "message" in update:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"].get("text", "")
                        reply = handle_command(chat_id, text)
                        if reply:
                            send_message(chat_id, reply)
                except Exception as e:
                    print(f"Ошибка update: {e}")
        time.sleep(0.5)


# =======================
# 🧩 Запуск всего
# =======================
if __name__ == "__main__":
    print("📡 Запуск глобального мониторинга и Telegram polling...")
    threading.Thread(target=global_monitor, daemon=True).start()
    time.sleep(2)
    main()
