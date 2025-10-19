import os
import json
import requests
import time
import threading

# 📁 Загружаем настройки из settings.json, если файл существует
if os.path.exists("settings.json"):
    with open("settings.json", "r") as f:
        SETTINGS = json.load(f)
else:
    SETTINGS = {
        "threshold": 6.0,
        "poll_interval": 10,
        "monitoring": False
    }

# 🔐 Безопасная загрузка токена и ID из переменных окружения
TELEGRAM_TOKEN = os.getenv("7618687590:AAH7tyDsI5WrRK7h_EQUusE2ziUlt6ijhk4")
ADMIN_ID = int(os.getenv("5496665478"))  # если нет, будет 0
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

last_update_id = 0
last_prices = {}


# 📩 Отправка сообщений в Telegram
def send_message(chat_id, text):
    try:
        requests.post(f"{API_URL}/sendMessage", data={"chat_id": chat_id, "text": text})
    except Exception as e:
        print(f"Ошибка отправки: {e}")


# 📨 Получение апдейтов
def get_updates(offset=None):
    try:
        resp = requests.get(f"{API_URL}/getUpdates", params={"timeout": 100, "offset": offset})
        return resp.json()
    except Exception as e:
        print(f"Ошибка получения обновлений: {e}")
        return {}


# 📊 Получение фьючерсов MEXC
def get_mexc_futures_tickers():
    try:
        url = "https://contract.mexc.com/api/v1/contract/ticker"
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            print(f"Ошибка MEXC Futures API: статус {res.status_code}")
            return []
        data = res.json().get("data", [])
        return [t for t in data if t.get("symbol", "").endswith("_USDT")]
    except Exception as e:
        print(f"Ошибка MEXC Futures API: {e}")
        return []


# 🔁 Мониторинг pump/dump
def monitor_market():
    global last_prices

    while SETTINGS["monitoring"]:
        tickers = get_mexc_futures_tickers()
        if not tickers:
            time.sleep(SETTINGS["poll_interval"])
            continue

        for t in tickers:
            try:
                symbol = t["symbol"].replace("_", "")
                price = float(t["lastPrice"])
                prev = last_prices.get(symbol)
                last_prices[symbol] = price

                if prev:
                    change = (price - prev) / prev * 100
                    if abs(change) >= SETTINGS["threshold"]:
                        if change > 0:
                            msg = f"🚀 PUMP на {symbol}: +{change:.2f}% — SHORT зона"
                        else:
                            msg = f"💥 DUMP на {symbol}: {change:.2f}% — LONG зона"
                        send_message(ADMIN_ID, msg)
            except Exception:
                continue

        time.sleep(SETTINGS["poll_interval"])


# ⚙️ Обработка команд
def handle_command(text):
    global SETTINGS

    parts = text.strip().split()
    cmd = parts[0].lower()

    if cmd == "/start":
        if SETTINGS["monitoring"]:
            return "⚠️ Мониторинг уже запущен."
        SETTINGS["monitoring"] = True
        threading.Thread(target=monitor_market, daemon=True).start()
        return "✅ Мониторинг фьючерсов MEXC запущен!"

    elif cmd == "/stop":
        SETTINGS["monitoring"] = False
        return "🛑 Мониторинг остановлен."

    elif cmd == "/test":
        return "🤖 Бот работает и подключен к MEXC Futures!"

    elif cmd == "/settings":
        s = "\n".join(f"{k}: {v}" for k, v in SETTINGS.items())
        return f"⚙️ Текущие настройки:\n{s}"

    elif cmd == "/set":
        if len(parts) < 3:
            return "Использование: /set параметр значение"
        key, value = parts[1], parts[2]
        if key not in SETTINGS:
            return "Неизвестный параметр."
        try:
            if key in ("threshold", "poll_interval"):
                value = float(value)
        except ValueError:
            return "Некорректное значение."
        SETTINGS[key] = value
        # сохраняем настройки в файл
        with open("settings.json", "w") as f:
            json.dump(SETTINGS, f, indent=4)
        return f"✅ {key} обновлён на {value}"

    elif cmd == "/help":
        return (
            "📘 Команды:\n"
            "/start — запустить мониторинг\n"
            "/stop — остановить мониторинг\n"
            "/settings — показать текущие настройки\n"
            "/set параметр значение — изменить параметр\n"
            "/test — проверить работу\n"
            "/help — список команд"
        )

    else:
        return "❓ Неизвестная команда. Введи /help."


# 🚀 Основной цикл Telegram-бота
def main():
    global last_update_id
    print("🚀 Бот запущен и ждёт команд в Telegram...")

    while True:
        updates = get_updates(last_update_id + 1)
        if "result" in updates:
            for update in updates["result"]:
                last_update_id = update["update_id"]
                if "message" in update:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"].get("text", "")
                    reply = handle_command(text)
                    if reply:
                        send_message(chat_id, reply)
        time.sleep(1)


if __name__ == "__main__":
    main()
