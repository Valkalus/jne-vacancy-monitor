# JNE Vacancy Monitor

Este script verifica la página de convocatorias del JNE cada 5 minutos usando GitHub Actions.

## Configuración rápida

1. Crea un **repo público** en GitHub y sube estos archivos.
2. Entra en Settings → Secrets → Actions y añade:
   - `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`
   - (Opcional) SMTP_USER, SMTP_PASS, SMTP_HOST, SMTP_PORT, NOTIFY_EMAIL_TO
3. Ve a la pestaña **Actions** y ejecuta el workflow manualmente la primera vez.

Si la página se carga por JS y no aparecen convocatorias, se deberá mejorar usando Playwright.
