import yfinance as yf
import pandas as pd
import pandas_ta as ta

def get_stock_data(ticker, interval="1d", period="1y"):
    """Récupère les données historiques avec un intervalle spécifique."""
    stock = yf.Ticker(ticker)
    df = stock.history(period=period, interval=interval)
    return df

def analyze_stock(ticker):
    """Analyse avancée avec Volume, Squeeze et Scoring pondéré."""
    # 1. Données Multi-Timeframe
    df_daily = get_stock_data(ticker, interval="1d", period="1y")
    df_1h = get_stock_data(ticker, interval="1h", period="1mo")
    
    if df_daily.empty or df_1h.empty or len(df_daily) < 50:
        return None

    # --- ANALYSE DAILY (Le Contexte) ---
    df_daily.ta.ema(length=50, append=True)
    df_daily.ta.ema(length=200, append=True)
    last_daily = df_daily.iloc[-1]
    
    # Tendance : Golden Cross ou prix au-dessus des EMA
    trend_score = 0
    if last_daily['Close'] > last_daily['EMA_200']: trend_score += 1
    if last_daily['EMA_50'] > last_daily['EMA_200']: trend_score += 1

    # --- ANALYSE 1H (Le Timing) ---
    df_1h.ta.rsi(length=14, append=True)
    df_1h.ta.macd(append=True)
    df_1h.ta.bbands(length=20, std=2, append=True)
    df_1h.ta.sma(length=20, column="Volume", append=True) # Moyenne du volume
    df_1h.ta.atr(length=14, append=True)

    last_1h = df_1h.iloc[-1]
    prev_1h = df_1h.iloc[-2]
    
    # Identification dynamique
    rsi_col = [c for c in df_1h.columns if "RSI" in c][0]
    macd_h_col = [c for c in df_1h.columns if "MACDh" in c][0]
    bb_width_col = [c for c in df_1h.columns if "BBB" in c][0]
    vol_sma_col = [c for c in df_1h.columns if "SMA_20" in c][0]
    atr_col = [c for c in df_1h.columns if "ATR" in c][0]

    # --- SYSTÈME DE SCORING ---
    final_score = 0
    reasons = []

    # A. Confirmation Tendance (Max 2 pts)
    final_score += trend_score
    if trend_score >= 1: reasons.append("Tendance Daily OK")

    # B. Momentum (Max 2 pts)
    if last_1h[macd_h_col] > 0 and prev_1h[macd_h_col] <= 0:
        final_score += 2
        reasons.append("Croisement MACD")
    elif last_1h[rsi_col] < 40:
        final_score += 1
        reasons.append("RSI en zone d'achat")

    # C. Volume (Max 1 pt)
    if last_1h['Volume'] > (last_1h[vol_sma_col] * 1.2):
        final_score += 1
        reasons.append("Volume en hausse")

    # D. Squeeze/Volatilité (Max 1 pt)
    # Si la largeur des bandes est faible (percentile 25), on est en squeeze
    if last_1h[bb_width_col] < df_1h[bb_width_col].quantile(0.25):
        final_score += 1
        reasons.append("Squeeze de volatilité")

    # --- DÉCISION ---
    signal = "Neutre"
    if final_score >= 4:
        signal = "ACHAT"
    elif last_1h[rsi_col] > 75:
        signal = "VENTE"

    # Gestion du risque
    atr_value = last_1h[atr_col]
    stop_loss = last_1h['Close'] - (atr_value * 2)
    take_profit = last_1h['Close'] + (atr_value * 3)

    return {
        "price": round(last_1h['Close'], 2),
        "signal": signal,
        "score": f"{final_score}/6",
        "reasons": ", ".join(reasons),
        "stop_loss": round(stop_loss, 2),
        "take_profit": round(take_profit, 2),
        "trend": "Haussière" if trend_score >= 1 else "Baissière"
    }

if __name__ == "__main__":
    # Test rapide sur LVMH (MC.PA)
    ticker = "MC.PA"
    results = analyze_stock(ticker)
    print(f"Analyse pour {ticker}: {results}")
