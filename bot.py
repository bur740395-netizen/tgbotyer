import asyncio
import re
import os
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# 1. TUS CREDENCIALES
TOKEN = "8925788497:AAH7Kg8QB7gRWrXgtgvC0fBCvzUePgkFZjc"

# 2. BASE DE DATOS DE CLIENTES
IDS_PERMITIDOS = [7076121810, 987654321] # Pon tu ID aquí para probar

async def extraer_codigo_web(correo_cliente: str) -> str:
    async with async_playwright() as p:
        # IMPORTANTE EN LA NUBE: headless=True para que corra en el servidor sin interfaz visual
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # PASO 1: Ingresar a la web
            await page.goto("https://clientes.kingg.app/portal/login")

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

# Servidor Flask para atender los pings y mantener despierto a Render
app_flask = Flask(__name__)

@app_flask.route('/ping')
def ping():
    return "Bot activo y funcionando", 200

def run_flask():
    port = int(os.environ.get("PORT", 3000))
    app_flask.run(host="0.0.0.0", port=port)

def main():
    # Iniciar servidor Flask en un hilo paralelo
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

    # Iniciar bot de Telegram
    app = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("max", comando_max))
    print("🤖 Bot en línea en la nube. Esperando comandos...")
    app.run_polling()

if __name__ == "__main__":
    main()