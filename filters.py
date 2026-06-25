import yfinance as yf
import pandas as pd

def get_sbf120_tickers():
    """
    Récupère une liste représentative des tickers du SBF 120.
    Note: Dans un environnement de production, on utiliserait une liste mise à jour via Euronext.
    """
    # Liste simplifiée des composants majeurs du SBF 120 (pour l'exemple)
    # En réel, on peut scraper Wikipedia ou utiliser un fichier CSV.
    tickers = [
        "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "AI.PA", "BNP.PA", "KER.PA", 
        "DIM.PA", "WLN.PA", "GLE.PA", "ACA.PA", "CA.PA", "DG.PA", "VIV.PA", "EDF.PA",
        "STLAP.PA", "ORPEA.PA", "UBI.PA", "ATO.PA", "SGO.PA", "RNO.PA", "ML.PA", "EN.PA"
    ]
    return tickers

def filter_pea_liquidity(tickers, min_volume_euro=2000000):
    """
    Filtre les actions par liquidité (Volume x Prix).
    """
    eligible_tickers = []
    print(f"Filtrage de {len(tickers)} tickers par liquidité...")
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            # On prend l'historique récent (5 derniers jours)
            hist = stock.history(period="5d")
            if hist.empty:
                continue
                
            # Calcul du volume quotidien moyen en Euros
            avg_volume = hist['Volume'].mean()
            avg_price = hist['Close'].mean()
            daily_turnover = avg_volume * avg_price
            
            if daily_turnover >= min_volume_euro:
                eligible_tickers.append(ticker)
            else:
                print(f"Skipping {ticker}: Liquidité insuffisante ({round(daily_turnover/1e6, 2)}M€/jour)")
        except Exception as e:
            print(f"Erreur sur {ticker}: {e}")
            
    return eligible_tickers

if __name__ == "__main__":
    raw_list = get_sbf120_tickers()
    filtered = filter_pea_liquidity(raw_list)
    print(f"\nActions retenues pour le PEA : {filtered}")
