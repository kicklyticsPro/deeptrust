import streamlit as st
import pandas as pd
from analysis import get_stock_data, analyze_stock
from filters import get_sbf120_tickers, filter_pea_liquidity
import plotly.graph_objects as go

st.set_page_config(page_title="PEA Trader Pro", layout="wide")

st.title("🚀 PEA Trader Pro - Analyse en Temps Réel")

# Barre latérale pour les filtres
st.sidebar.header("Configuration du Filtre PEA")
min_vol = st.sidebar.slider("Volume min quotidien (M€)", 0, 50, 2)

# Cache pour ne pas rescanner à chaque clic
@st.cache_data(ttl=3600)
def get_eligible_universe(vol_threshold):
    raw_list = get_sbf120_tickers()
    return filter_pea_liquidity(raw_list, min_volume_euro=vol_threshold*1000000)

TICKERS = get_eligible_universe(min_vol)
st.sidebar.write(f"Actions analysées : {len(TICKERS)}")

results = []

for ticker in TICKERS:
    analysis = analyze_stock(ticker)
    if analysis:
        results.append({
            "Ticker": ticker,
            "Prix": analysis['price'],
            "Score": analysis['score'],
            "Raisons": analysis['reasons'],
            "Signal": analysis['signal'],
            "Stop Loss": analysis['stop_loss'],
            "Take Profit": analysis['take_profit']
        })

df_results = pd.DataFrame(results)

# Affichage des alertes
st.subheader("🎯 Opportunités de Trading (Confirmé)")
col1, col2 = st.columns(2)

buys = df_results[df_results['Signal'] == "ACHAT"]
sells = df_results[df_results['Signal'] == "VENTE"]

with col1:
    st.success("🟢 Signaux d'ACHAT (Flux validé)")
    if not buys.empty:
        st.dataframe(buys)
    else:
        st.write("Aucun signal d'achat détecté.")

with col2:
    st.error("🔴 Signaux de VENTE (Prise de profit)")
    if not sells.empty:
        st.dataframe(sells)
    else:
        st.write("Aucun signal de vente détecté.")

# Détail par action
st.subheader("📊 Analyse Graphique & Volatilité")
selected_ticker = st.selectbox("Choisir une action pour voir le graphique :", TICKERS)
data_chart = get_stock_data(selected_ticker, interval="1h", period="1mo")

fig = go.Figure()
fig.add_trace(go.Candlestick(x=data_chart.index,
                open=data_chart['Open'],
                high=data_chart['High'],
                low=data_chart['Low'],
                close=data_chart['Close'], name='Prix'))
st.plotly_chart(fig, use_container_width=True)
