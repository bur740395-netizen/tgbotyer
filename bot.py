import os
import asyncio
import re
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# 1. TUS CREDENCIALES
TOKEN = os.getenv("TELEGRAM_TOKEN")

# 2. BASE DE DATOS DE CLIENTES (Optimizado como set para soportar 100-200+ usuarios con cero retraso)
IDS_PERMITIDOS = {7076121810, 1648637276, 7981030060} # Añade más IDs separados por comas aquí

# Servidor Flask para atender los pings de Render / cron-job.org
app_flask = Flask(__name__)

@app_flask.route('/ping')
def ping():
    return "Bot activo y funcionando"

def run_flask():
    app_flask.run(host="0.0.0.0", port=10000)

async def extraer_codigo_web(correo_cliente: str) -> str:
    async with async_playwright() as p:
        # Optimizaciones extremas de Playwright para ahorrar RAM en contenedores
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer"
            ]
        )
        context = await browser.new_context()
        page = await context.new_page()

       # Permitir CSS para que la web cargue bien, bloqueando solo imágenes, fuentes y medios pesados
        await page.route(
        "**/*", 
        lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_()
        )
        try:
            # PASO 1: Ingresar a la web
            await page.goto("https://clientes.kingg.app/portal/login", timeout=60000)

            # PASO 2: Login
            await page.get_by_placeholder("Tu usuario").fill("yersonmg29")
            await page.get_by_placeholder("Tu contraseña").fill("Yersonmg29cuentas*")
            await page.get_by_text("Ingresar a mis servicios").click()
        
            # Esperamos a que cargue el panel principal tras el login
            await page.wait_for_timeout(3000)

            # PASO 3: Navegar a la sección Bots
            await page.locator("text=Bots").first.click()

            # Esperamos a que cargue la sección Bots
            await page.wait_for_selector("text=Buscar código o enlace", timeout=10000)

            # PASO 4: Llenar el formulario de consulta
            await page.get_by_text("Seleccionar plataforma").click()
            await page.get_by_text("Max Estandar").first.click()
            
            await page.get_by_text("MAX", exact=True).first.click()

            await page.locator("input[type='text'], input[type='email']").last.fill(correo_cliente)
            await page.wait_for_timeout(1500)
            
            await page.get_by_text(correo_cliente).last.click()
            await page.get_by_role("button", name="Consultar").click()

            # PASO 5: Esperar y extraer el código
            await page.wait_for_timeout(20000) 
            
            texto_pantalla = await page.locator("body").inner_text()
            
            busqueda = re.search(r'\b\d{3}\s?\d{3}\b', texto_pantalla)
            
            if busqueda:
                codigo_encontrado = busqueda.group(0).replace(" ", "")
                return f"✅ El código de Max es: {codigo_encontrado}"
            else:
                return "⚠️ Se hizo la consulta pero no se encontró el código en la pantalla."

        except Exception as error:
            return f"❌ Error al navegar por la página: {error}"
            
        finally:
            await context.close()
            await browser.close()

async def comando_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in IDS_PERMITIDOS:
        await update.message.reply_text("⛔ Acceso denegado. Tu ID no está registrado.")
        return

    try:
        correo = context.args[0]
        await update.message.reply_text(f"🔍 Conectando al sistema para el correo:\n{correo}\nPor favor, espera unos segundos...")
        
        resultado = await extraer_codigo_web(correo)
        await update.message.reply_text(resultado)
        
    except IndexError:
        await update.message.reply_text("⚠️ Formato incorrecto. Por favor envía:\n/max correo@cuenta.com")

def main():
    # Iniciar Flask en segundo plano para el servidor web y los pings de mantenimiento
    hilo_flask = threading.Thread(target=run_flask, daemon=True)
    hilo_flask.start()

    # Iniciar bot de Telegram
    app = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("max", comando_max))
    print("🤖 Bot y servidor Flask en línea. Esperando comandos...")
    app.run_polling()

if __name__ == "__main__":
    main()
