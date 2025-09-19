import os
import re
import json
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText

URL = "https://portal.jne.gob.pe/portal/Pagina/Ver/77/page/Convocatoria-de-Personal-y-Practicantes"
SEEN_FILE = "seen.json"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# SMTP / email settings — manejar valores faltantes de forma segura
SMTP_USER = os.getenv("SMTP_USER") or None
SMTP_PASS = os.getenv("SMTP_PASS") or None
SMTP_HOST = os.getenv("SMTP_HOST") or "smtp.gmail.com"

# Intentar convertir SMTP_PORT a entero; si falla, usar 587 por defecto
_port_raw = os.getenv("SMTP_PORT")
try:
    SMTP_PORT = int(_port_raw) if _port_raw and _port_raw.strip() != "" else 587
except (ValueError, TypeError):
    SMTP_PORT = 587

NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO") or None

KEYWORDS = ["CAS", "D.L. 728", "Locación", "Locacion", "Servicio"]

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram no configurado")
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
    )

def send_email(msg):
    if not SMTP_USER or not SMTP_PASS or not NOTIFY_EMAIL_TO:
        print("Email no configurado")
        return
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            mime_msg = MIMEText(msg)
            mime_msg["Subject"] = "Nuevas Convocatorias JNE"
            mime_msg["From"] = SMTP_USER
            mime_msg["To"] = NOTIFY_EMAIL_TO
            server.sendmail(SMTP_USER, NOTIFY_EMAIL_TO, mime_msg.as_string())
    except Exception as e:
        print(f"Error enviando email: {e}")

def fetch_links():
    resp = requests.get(URL)
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        if "/portal_documentos/files/" in a["href"] and a["href"].endswith(".pdf"):
            links.append(a["href"])
    return links

def main():
    seen = load_seen()
    found = fetch_links()
    new_links = [link for link in found if link not in seen]

    if not new_links:
        print("No hay convocatorias nuevas")
        return

    for link in new_links:
        full_url = link if link.startswith("http") else f"https://portal.jne.gob.pe{link}"
        try:
            pdf_text = requests.get(full_url).text
        except:
            pdf_text = ""
        if any(keyword.lower() in pdf_text.lower() for keyword in KEYWORDS):
            msg = f"Nueva convocatoria detectada: {full_url}"
            print(msg)
            send_telegram(msg)
            send_email(msg)

    seen.update(new_links)
    save_seen(seen)

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    print("🔧 EJECUTANDO MODO DE PRUEBA...")
    # Comprobamos si las variables de entorno están presentes
    import os
    print("DEBUG: TELEGRAM_TOKEN presente?", bool(os.getenv("TELEGRAM_TOKEN")))
    print("DEBUG: TELEGRAM_CHAT_ID presente?", bool(os.getenv("TELEGRAM_CHAT_ID")))

    # Enviar prueba solo si las secrets están configuradas
    if os.getenv("TELEGRAM_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        send_telegram("✅ PRUEBA: El sistema de monitor JNE está funcionando y puede enviarte alertas.")
    else:
        print("Telegram no está configurado en las Secrets. Revisa TELEGRAM_TOKEN y TELEGRAM_CHAT_ID.")

