import pandas as pd
import time
import pytz
from datetime import datetime
import requests
from flask import Flask, request

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================
SYMBOL = "XAU/USD"
LOT_SIZE = 0.01
SL_PIPS = 25
TP_PIPS = 85
PIP_IN_PRICE = 0.1  # For Gold (1 pip = 0.1)

LEVELS = [1920, 1945, 1980, 2000]  # <-- Weekend H4 levels manually update karo

# Sessions (Pakistan Time)
LONDON_START = 12   # 12:00 PKT
LONDON_END = 16     # 16:00 PKT
NY_START = 17.5     # 17:30 PKT
NY_END = 22.5       # 22:30 PKT

CHECK_EVERY_SEC = 60

# Twelve Data API
TWELVE_API_KEY = "5be1b12e0de6475a850cc5caeea9ac72"
BASE_URL = "https://api.twelvedata.com"

# Telegram
BOT_TOKEN = "8178081661:AAH6yqv3JbtWBoXE28HR_Jdwi8g4vthGaiI"
CHAT_ID = "5969642968"

# ==============================
# HELPERS
# ==============================
def now_pkt():
    return datetime.now(pytz.timezone("Asia/Karachi"))

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Telegram send error:", e)

def in_session():
    t = now_pkt().hour + now_pkt().minute/60
    return (LONDON_START <= t < LONDON_END) or (NY_START <= t < NY_END)

def get_price():
    url = f"{BASE_URL}/price?symbol={SYMBOL}&apikey={TWELVE_API_KEY}"
    try:
        r = requests.get(url).json()
        return float(r["price"])
    except Exception as e:
        print("Price fetch error:", e)
        return None

def get_candles(interval="15min", n=50):
    url = f"{BASE_URL}/time_series?symbol={SYMBOL}&interval={interval}&outputsize={n}&apikey={TWELVE_API_KEY}"
    try:
        r = requests.get(url).json()
        df = pd.DataFrame(r["values"])
        df = df.astype({"open":"float","high":"float","low":"float","close":"float"})
        df = df[::-1].reset_index(drop=True)  # oldest → newest
        return df
    except Exception as e:
        print("Candle fetch error:", e)
        return pd.DataFrame()

# ==============================
# STRATEGY RULES
# ==============================
def price_action_confirmation():
    df = get_candles("15min", 3)
    if len(df) < 3:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last['close'] - last['open'])
    # Pin Bar Bullish
    if last['close'] > last['open'] and (last['high'] - last['close']) > 2 * body:
        return "BUY"
    # Pin Bar Bearish
    if last['close'] < last['open'] and (last['close'] - last['low']) > 2 * body:
        return "SELL"
    # Engulfing Bullish
    if last['close'] > prev['open'] and last['open'] < prev['close']:
        return "BUY"
    # Engulfing Bearish
    if last['close'] < prev['open'] and last['open'] > prev['close']:
        return "SELL"
    return None

def trend_check():
    df15 = get_candles("15min", 20)
    df1h = get_candles("1h", 50)
    if df15.empty or df1h.empty:
        return 0, 0
    m15_dir = 1 if df15['close'].iloc[-1] > df15['close'].mean() else -1
    h1_dir = 1 if df1h['close'].iloc[-1] > df1h['close'].mean() else -1
    return m15_dir, h1_dir

# ==============================
# FLASK ROUTES
# ==============================
last_alert = {"level": None, "direction": None}

@app.route('/')
def home():
    return "🚀 Gold Bot is Running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    # External service aap ko trigger kar sake (e.g., cron job)
    data = request.json
    # Yahan aap strategy run kar sakte hain
    return "OK"

def check_strategy():
    # Strategy logic yahan daalen
    price = get_price()
    if not price:
        return

    near_levels = [lv for lv in LEVELS if abs(price - lv) <= 1.0]
    if not near_levels:
        return

    signal = price_action_confirmation()
    if not signal:
        return

    m15_dir, h1_dir = trend_check()
    if signal == "BUY" and not (m15_dir == 1 and h1_dir == 1):
        return
    if signal == "SELL" and not (m15_dir == -1 and h1_dir == -1):
        return

    if last_alert["level"] == near_levels[0] and last_alert["direction"] == signal:
        return

    if signal == "BUY":
        sl = price - SL_PIPS * PIP_IN_PRICE
        tp = price + TP_PIPS * PIP_IN_PRICE
    else:
        sl = price + SL_PIPS * PIP_IN_PRICE
        tp = price - TP_PIPS * PIP_IN_PRICE

    msg = (
        f"🔥 A+ Setup Found ({SYMBOL})\n\n"
        f"Signal: {signal}\n"
        f"Entry: {price:.2f}\n"
        f"SL: {sl:.2f} ({SL_PIPS} pips)\n"
        f"TP: {tp:.2f} ({TP_PIPS} pips)\n"
        f"Lot Size: {LOT_SIZE}\n"
        f"Level: {near_levels}\n"
        f"Session: {'London' if now_pkt().hour<16 else 'New York'}\n\n"
        f"⚡ Rule: Trade only if clean candle close is confirmed!"
    )

    print(msg)
    send_telegram(msg)
    last_alert["level"] = near_levels[0]
    last_alert["direction"] = signal

# ==============================
# START (for Render)
# ==============================
if __name__ == '__main__':
    # Flask server run karein
    app.run(host='0.0.0.0', port=10000)
