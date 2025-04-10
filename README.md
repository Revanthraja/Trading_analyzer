# 📈 Price Action Strategy Analyzer

A FastAPI-powered service for analyzing OHLC (Open, High, Low, Close) candlestick data to detect potential trading signals using **price action strategies**.

The service returns actionable insights such as:

- ✅ **Limit Catch Entry**
- ✅ **In-Price Entry**
- ❌ **No Entry** (when conditions aren't met)![chart2](https://github.com/user-attachments/assets/f470921f-49a2-4a8e-ac12-1cf75ae13042)


Ideal for **backtesting**, **signal generation**, or integrating with a **trading bot** or dashboard.

---

## 📚 Table of Contents

- [📖 Introduction](#-introduction)
- [🧠 Strategy Logic Explained](#-strategy-logic-explained)
  - [Range Detection](#range-detection)
  - [Impulse Detection](#impulse-detection)
  - [Trend & BoS](#trend--bos)
- [🚀 How It Works](#-how-it-works)
- [🔧 Configuration Parameters](#-configuration-parameters)
- [💻 Installation & Usage](#-installation--usage)
- [📡 API Reference](#-api-reference)
- [📌 Example Use Cases](#-example-use-cases)
- [🛠 Developer Notes](#-developer-notes)
- [📜 License](#-license)

---

## 📖 Introduction

Price action is the study of price movement using raw candlestick data without relying heavily on lagging indicators. This service identifies strategic entry points using:

- Historical price **ranges**
- Momentum-based **impulse moves**
- Emerging **trend behavior** and **Breaks of Structure (BoS)**

You send a list of OHLC candles, and the system replies with the most probable strategy that aligns with the current market behavior.

---

## 🧠 Strategy Logic Explained

### 🟦 Range Detection

Detects a **sideways market zone** where price oscillates within a horizontal band.

✅ Criteria:

- A minimum of `15` candles (`min_candles`)
- At least `2` touches at **both upper and lower bounds**
- Width must be within `0.7%` to `3.0%` of the midpoint
- The **latest close** must lie within a **buffer zone** near range highs or lows (configurable)

📌 This is useful for identifying **range-bound setups** where traders wait for **breakouts** or **mean-reversion entries**.

---

### 🟨 Impulse Detection

Detects **sharp, directional price moves** to qualify **momentum** or **breakout phases**.

✅ Criteria:

- 2 to 3 consecutive candles
- Total price change ≥ `1.5%`
- Candle bodies make up ≥ `60%` of each candle’s total range
- Direction must be consistent (all bullish or all bearish)

📌 Used to **avoid traps** in ranging markets or confirm valid **breakouts**.

---

### 🟩 Trend & Break of Structure (BoS)

Detects emerging trends and confirms **structural breaks**.

✅ Criteria:

- Price must increase or decrease at least `0.1%` over the last `10` candles
- For BoS:
  - In **uptrend**: current high must break previous highs
  - In **downtrend**: current low must break previous lows

📌 Used to confirm trend continuation and avoid premature entries.

---

## 🚀 How It Works

1. Submit a POST request to `/analyze` with a list of OHLC candles.
2. The server:
   - Parses and validates the data
   - Runs the dataset through detection logic
   - Returns a suggested strategy based on priority logic:
     1. **Limit Catch Entry**
     2. **In-Price Entry**
     3. **No Entry**

3. Response includes a clear **reason** for the chosen suggestion.

---

## 🔧 Configuration Parameters

Inside the source code, you can customize:

```python
RANGE_CONFIG = {
    "min_candles": 15,               # Rolling window size for range detection
    "min_touches": 2,                # Touches at both ends of range
    "width_min_pct": 0.7,            # Minimum width as percentage
    "width_max_pct": 3.0,            # Maximum width
    "touch_tolerance_pct": 1.0,      # How close a touch needs to be to range edge
    "midrange_pct": 30               # Buffer area considered as entry zone
}

IMPULSE_CONFIG = {
    "min_candles_consecutive": 2,    # Minimum number of candles for impulse
    "max_candles_total": 3,          # Max consecutive candles to analyze
    "min_total_pct_change": 1.5,     # Total % change over the impulse
    "min_body_pct": 60               # Body as % of candle size
}

TREND_THRESHOLD_PCT = 0.1            # Threshold % for trend detection
TREND_LOOKBACK = 10                  # Candles to look back for trend/BOS
