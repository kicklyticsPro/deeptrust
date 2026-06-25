import time
from filters import get_sbf120_tickers, filter_pea_liquidity
from analysis import analyze_stock
from notifications import send_telegram_alert, format_alert_message

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "VOTRE_TOKEN_ICI" # Remplacez par votre token
CHAT_ID = "VOTRE_CHAT_ID_ICI"     # Remplacez par votre ID
SCAN_INTERVAL = 3600               # Scan toutes les heures (en secondes)
MIN_SCORE_FOR_ALERT = 4            # Seuil de déclenchement (Confirmé)

def run_scanner():
    print("Démarrage du scanner PEA Trader Pro...")
    
    # 1. On définit l'univers une fois au début (ou une fois par jour)
    raw_list = get_sbf120_tickers()
    universe = filter_pea_liquidity(raw_list)
    
    while True:
        print(f"\n--- Scan en cours ({len(universe)} actions) ---")
        
        for ticker in universe:
            try:
                analysis = analyze_stock(ticker)
                if not analysis:
                    continue
                
                score_value = int(analysis['score'].split('/')[0])
                
                # Condition d'alerte : Signal d'achat avec score élevé
                if analysis['signal'] == "ACHAT" and score_value >= MIN_SCORE_FOR_ALERT:
                    print(f"!!! SIGNAL DÉTECTÉ SUR {ticker} (Score: {score_value}) !!!")
                    
                    message = format_alert_message(ticker, analysis)
                    send_telegram_alert(TELEGRAM_TOKEN, CHAT_ID, message)
                else:
                    print(f"Analyse {ticker}: Score {score_value}/6 (Pas de signal)")
                    
            except Exception as e:
                print(f"Erreur lors de l'analyse de {ticker}: {e}")
            
            # Petite pause pour ne pas saturer l'API Yahoo
            time.sleep(1)
            
        print(f"Scan terminé. Prochain scan dans {SCAN_INTERVAL/60} minutes.")
        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    run_scanner()
