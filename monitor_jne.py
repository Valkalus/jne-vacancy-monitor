# monitor_jne.py (versión actualizada: busca 'fiscalizador' y variantes)
import os
import re
import json
import io
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
import smtplib
from PyPDF2 import PdfReader

# URL objetivo
URL = "https://portal.jne.gob.pe/portal/Pagina/Ver/77/page/Convocatoria-de-Personal-y-Practicantes"
SEEN_FILE = "seen.json"

# Keywords (regex compatibles) — añadimos fiscalizador y variantes
KEYWORDS = [
    r"\bfiscalizador\b",
    r"\bfiscalizador(es)?\b",
    r"\bfiscalizador\s+provincial\b",
    r"\bfiscalizador\s+provincia(l)?\b",
    r"\bfiscalizador\s+distrital\b",
    r"\bfiscalizador\s+distrito(al)?\b",
    r"\bfiscalizador(es)?\s+distrital(es)?\b",
    r"\bfiscalizador(es)?\s+provincial(es)?\b",
    # Mantén otras palabras que ya buscabas (CAS, DL 728, Practicante, Locación)
    r"\bCAS\b",
    r"\bD\.?\s*L\.?\s*728\b",
    r"\bDL\s*728\b",
    r"Locaci[oó]n de servicio",
    r"Practicante",
    r"Prácticante"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; vacancy-monitor/1.0)"}

# SMTP / email settings — manejar valores faltantes de forma segura
SMTP_USER = os.getenv("SMTP_USER") or None
SMTP_PASS = os.getenv("SMTP_PASS") or None
SMTP_HOST = os.getenv("SMTP_HOST") or "smtp.gmail.com"
_port_raw = os.getenv("SMTP_PORT")
try:
    SMTP_PORT = int(_port_raw) if _port_raw and _port_raw.strip() != "" else 587
except (ValueError, TypeError):
    SMTP_PORT = 587
NOTIFY_EMAIL_TO = os.getenv("NOTIFY_EMAIL_TO") or None

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram no configurado")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
        if not resp.ok:
            print("Telegram API error:", resp.text)
        return resp.ok
    except Exception as e:
        print("Error notificando Telegram:", e)
        return False

def send_email(subject, body):
    if not SMTP_USER or not SMTP_PASS or not NOTIFY_EMAIL_TO:
        print("Email no configurado o incompleto, saltando correo.")
        return False
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            mime_msg = MIMEText(body)
            mime_msg["Subject"] = subject
            mime_msg["From"] = SMTP_USER
            mime_msg["To"] = NOTIFY_EMAIL_TO
            server.sendmail(SMTP_USER, NOTIFY_EMAIL_TO, mime_msg.as_string())
        return True
    except Exception as e:
        print("Error enviando email:", e)
        return False

def find_pdf_links_and_text(html, base_url):
    """
    Retorna lista de tuples: (link_url, anchor_text)
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # capturar PDFs y enlaces del portal_documentos
        if href.lower().endswith(".pdf") or "/portal_documentos/files/" in href.lower():
            full = urljoin(base_url, href)
            text = (a.get_text(" ", strip=True) or "").strip()
            out.append((full, text))
    # eliminar duplicados manteniendo orden
    seen_local = set()
    unique = []
    for link, text in out:
        if link not in seen_local:
            unique.append((link, text))
            seen_local.add(link)
    return unique

def pdf_text_from_bytes(b):
    try:
        reader = PdfReader(io.BytesIO(b))
        text = []
        for p in reader.pages:
            try:
                page_text = p.extract_text() or ""
                text.append(page_text)
            except Exception:
                pass
        return "\n".join(text)
    except Exception:
        return ""

def matches_keywords(text):
    if not text:
        return False
    t = text.lower()
    for pattern in KEYWORDS:
        try:
            if re.search(pattern, t, re.IGNORECASE):
                return True
        except re.error:
            if pattern.lower() in t:
                return True
    return False

def main():
    seen = load_seen()
    try:
        r = requests.get(URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print("Error al obtener la página:", e)
        return

    items = find_pdf_links_and_text(r.text, URL)
    print(f"Enlaces potenciales encontrados: {len(items)}")
    new_seen = set(seen)

    for link, anchor_text in items:
        if link in seen:
            continue

        found_match = False
        matched_patterns = []

        # 1) revisar texto del enlace (más rápido, evita descargar)
        if anchor_text and matches_keywords(anchor_text):
            found_match = True
            matched_patterns.append("anchor_text")

        # 2) inspeccionar URL (nombre del archivo)
        if not found_match and matches_keywords(link):
            found_match = True
            matched_patterns.append("url")

        # 3) si aún no coincide, descargar PDF y analizar texto
        pdf_text = ""
        if not found_match:
            try:
                print("Descargando para analizar:", link)
                b = requests.get(link, headers=HEADERS, timeout=30).content
                pdf_text = pdf_text_from_bytes(b)
                if matches_keywords(pdf_text):
                    found_match = True
                    matched_patterns.append("pdf_text")
            except Exception as e:
                print("Error descargando/leyendo PDF:", e)

        # Si encontramos coincidencia, notificar
        if found_match:
            # tratar de extraer un título breve
            title = anchor_text or link.split("/")[-1]
            # formatear mensaje
            msg = (
                "🚨 *Nueva convocatoria potencial encontrada*\n\n"
                f"*Título:* {title}\n"
                f"*Enlace:* {link}\n"
                f"*Coincidencia en:* {', '.join(matched_patterns)}\n\n"
                "Revisa el documento por si corresponde (puede ser CAS u otro tipo)."
            )
            # Telegram no soporta markdown en todos los casos sin flags; usamos texto plano
            msg_plain = (
                "🚨 Nueva convocatoria potencial encontrada\n\n"
                f"Título: {title}\n"
                f"Enlace: {link}\n"
                f"Coincidencia en: {', '.join(matched_patterns)}\n\n"
                "Revisa el documento por si corresponde (puede ser CAS u otro tipo)."
            )
            print("Notificando: ", link, matched_patterns)
            send_telegram(msg_plain)
            send_email("Nueva convocatoria JNE detectada", msg_plain)

        # marcar como visto para no procesar de nuevo
        new_seen.add(link)

    if new_seen != seen:
        save_seen(new_seen)
        print("Se actualizaron entradas vistas:", len(new_seen) - len(seen))
    else:
        print("Sin novedades.")

if __name__ == "__main__":
    # modo normal — ejecuta main
    print("Ejecutando monitor JNE (búsqueda de 'fiscalizador' y otras)...")
    main()
