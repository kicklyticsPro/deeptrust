import requests

def send_telegram_alert(api_token, chat_id, message):
    """Envoie un message via l'API Telegram."""
    url = f"https://api.telegram.org/bot{api_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")
        return None

def format_alert_message(ticker, analysis):
    """Formate l'analyse pour un affichage clair sur Telegram."""
    emoji = "🚀" if analysis['signal'] == "ACHAT" else "⚠️"
    
    msg = (
        f"{emoji} *SIGNAL {analysis['signal']}* {emoji}\n"
        f"--------------------------\n"
        f"*Action:* {ticker}\n"
        f"*Prix actuel:* {analysis['price']} €\n"
        f"*Score:* {analysis['score']}\n"
        f"*Raisons:* {analysis['reasons']}\n\n"
        f"🎯 *Take Profit:* {analysis['take_profit']} €\n"
        f"🛡️ *Stop Loss:* {analysis['stop_loss']} €\n"
        f"--------------------------\n"
        f"💡 _Vérifiez toujours le graphique avant d'entrer._"
    )
    return msg
