import fastapi
import uvicorn
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List

# --- Configuration & Strategy Rules ---
RANGE_CONFIG = {
    "min_candles": 15,
    "min_touches": 2,
    "width_min_pct": 0.7,
    "width_max_pct": 3.0,
    "touch_tolerance_pct": 1.0,
    "midrange_pct": 30,
}

IMPULSE_CONFIG = {
    "min_candles_consecutive": 2,
    "max_candles_total": 3,
    "min_total_pct_change": 1.5,
    "min_body_pct": 60,
}

TREND_THRESHOLD_PCT = 0.1
TREND_LOOKBACK = 10

# --- Pydantic Models ---
class CandleDataInput(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float

class AnalysisRequest(BaseModel):
    ohlc_data: List[CandleDataInput] = Field(..., min_items=RANGE_CONFIG["min_candles"])

class AnalysisResult(BaseModel):
    strategy_suggestion: str
    reason: str | None = None

# --- Helper Functions ---
def preprocess_data_from_json(data: List[CandleDataInput]) -> pd.DataFrame:
    try:
        data_dicts = [candle.dict() for candle in data]
        df = pd.DataFrame(data_dicts)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        
        # Calculate candle metrics
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['body_ratio'] = np.where(
            df['range'] == 0, 0,
            (df['body'] / df['range']) * 100
        )
        return df
    except Exception as e:
        raise ValueError(f"Data processing error: {e}")

def check_price_near_extreme(price, range_low, range_high, midrange_pct):
    total_range = range_high - range_low
    if total_range <= 0:
        return False
        
    lower_bound = range_low + total_range * ((100 - midrange_pct)/2/100)
    upper_bound = range_high - total_range * ((100 - midrange_pct)/2/100)
    return price < lower_bound or price > upper_bound

# --- Core Analysis Functions ---
def detect_range(df: pd.DataFrame) -> dict | None:
    """Identifies valid price ranges using rolling window approach"""
    min_candles = RANGE_CONFIG["min_candles"]
    if len(df) < min_candles:
        return None

    # Check windows starting from most recent data
    for start_idx in range(len(df) - min_candles, -1, -1):
        window = df.iloc[start_idx:start_idx + min_candles]
        window_high = window['high'].max()
        window_low = window['low'].min()

        if pd.isna(window_high) or window_high <= window_low:
            continue

        # Calculate touch tolerance
        high_tol = window_high * (RANGE_CONFIG["touch_tolerance_pct"] / 100)
        low_tol = window_low * (RANGE_CONFIG["touch_tolerance_pct"] / 100)

        # Count valid touches
        high_touches = window[window['high'] >= window_high - high_tol]
        low_touches = window[window['low'] <= window_low + low_tol]

        if (len(high_touches) >= RANGE_CONFIG["min_touches"] and 
            len(low_touches) >= RANGE_CONFIG["min_touches"]):
            
            width = window_high - window_low
            midpoint = (window_high + window_low) / 2
            if midpoint == 0:
                continue
                
            width_pct = (width / midpoint) * 100
            if RANGE_CONFIG["width_min_pct"] <= width_pct <= RANGE_CONFIG["width_max_pct"]:
                # Verify last close position
                last_close = window['close'].iloc[-1]
                upper_bound = window_high * (1 + RANGE_CONFIG["touch_tolerance_pct"]/100)
                lower_bound = window_low * (1 - RANGE_CONFIG["touch_tolerance_pct"]/100)
                
                if lower_bound <= last_close <= upper_bound:
                    return {
                        "high": window_high,
                        "low": window_low,
                        "width_pct": width_pct,
                        "start_index": start_idx,
                        "end_index": start_idx + min_candles - 1
                    }
    return None

def detect_trend_and_bos(df: pd.DataFrame) -> tuple[str | None, bool]:
    """Improved trend detection with dynamic lookback"""
    if len(df) < TREND_LOOKBACK + 1:
        return None, False

    lookback_data = df.iloc[-TREND_LOOKBACK-1:-1]  # Exclude last candle
    recent_data = df.iloc[-TREND_LOOKBACK:]
    
    # Trend detection
    price_change = (recent_data['close'].iloc[-1] - lookback_data['close'].iloc[0]) 
    price_change_pct = (price_change / lookback_data['close'].iloc[0]) * 100
    
    trend = None
    if price_change_pct > TREND_THRESHOLD_PCT:
        trend = "uptrend"
    elif price_change_pct < -TREND_THRESHOLD_PCT:
        trend = "downtrend"

    # BoS detection
    bos = False
    if trend == "uptrend":
        prev_high = lookback_data['high'].max()
        bos = df['high'].iloc[-1] > prev_high
    elif trend == "downtrend":
        prev_low = lookback_data['low'].min()
        bos = df['low'].iloc[-1] < prev_low

    return trend, bos

def check_recent_impulse(df: pd.DataFrame) -> bool:
    """Enhanced impulse detection with directional consistency"""
    for num_candles in range(IMPULSE_CONFIG["min_candles_consecutive"], 
                           IMPULSE_CONFIG["max_candles_total"] + 1):
        if len(df) < num_candles:
            continue
            
        subset = df.iloc[-num_candles:]
        start_price = subset['open'].iloc[0]
        end_price = subset['close'].iloc[-1]
        
        if start_price == 0:
            continue
            
        pct_change = abs((end_price - start_price) / start_price) * 100
        if pct_change < IMPULSE_CONFIG["min_total_pct_change"]:
            continue
            
        # Check body ratios and direction consistency
        body_ratios = subset['body_ratio']
        if body_ratios.mean() < IMPULSE_CONFIG["min_body_pct"]:
            continue
            
        direction = np.sign(end_price - start_price)
        consistent = all(
            (candle['close'] - candle['open']) * direction >= 0
            for _, candle in subset.iterrows()
        )
        
        if consistent:
            return True
            
    return False

# --- Main Analysis Logic ---
def analyze_data(df: pd.DataFrame) -> tuple[str, str]:
    """Enhanced analysis with clear priority logic"""
    detected_range = detect_range(df)
    last_close = df['close'].iloc[-1]
    reason = []

    # 1. Check Limit Catch conditions
    if detected_range:
        range_low = detected_range['low']
        range_high = detected_range['high']
        
        in_entry_zone = check_price_near_extreme(
            last_close, range_low, range_high, 
            RANGE_CONFIG["midrange_pct"]
        )
        
        range_details = (
            f"Range detected ({range_low:.2f}-{range_high:.2f}, "
            f"Width: {detected_range['width_pct']:.2f}%)"
        )
        reason.append(range_details)
        
        if in_entry_zone:
            # Check for pre-range impulse
            pre_range_data = df.iloc[:detected_range['start_index']]
            if not check_recent_impulse(pre_range_data):
                reason.append("Price in entry zone with no prior impulse")
                return "Limit Catch Entry", ". ".join(reason)

    # 2. Check In-Price Entry conditions
    trend, bos = detect_trend_and_bos(df)
    current_impulse = check_recent_impulse(df)
    
    reason.append(f"Trend: {trend or 'none'}, BoS: {bos}, Impulse: {current_impulse}")
    
    if trend and bos and not current_impulse:
        reason.append("Trend with BoS and no current impulse")
        return "In-Price Entry", ". ".join(reason)

    # 3. Default case
    return "No Entry", ". ".join(reason) or "No patterns detected"

# --- FastAPI Endpoint ---
app = FastAPI(title="Price Action Strategy Analyzer")

@app.post("/analyze", response_model=AnalysisResult)
async def analyze_ohlc(request: AnalysisRequest):
    try:
        df = preprocess_data_from_json(request.ohlc_data)
        strategy, reason = analyze_data(df)
        return AnalysisResult(
            strategy_suggestion=strategy,
            reason=reason
        )
    except ValueError as ve:
        raise HTTPException(400, detail=str(ve))
    except Exception as e:
        raise HTTPException(500, detail=f"Analysis error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)