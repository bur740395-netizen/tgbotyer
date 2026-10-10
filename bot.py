import os
import asyncio
import re
import threading
from flask import Flask, request, render_template_string
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from playwright.async_api import async_playwright

# 1. TUS CREDENCIALES
TOKEN = os.getenv("TELEGRAM_TOKEN")

# 2. BASE DE DATOS DE CLIENTES
IDS_PERMITIDOS = {7076121810, 1648637276}

# Servidor Flask para la web y los pings
app_flask = Flask(__name__)

# --- DISEÑO VISUAL DE LA PÁGINA WEB ---
html_template = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Consultas Max</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f4f4f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        
        /* Estilos del banner de publicidad superior */
        .banner-promo {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            background-color: #1a1a1a;
            color: #ffffff;
            text-align: center;
            padding: 15px 0;
            font-size: 22px;
            font-weight: 900;
            letter-spacing: 1px;
            text-shadow: 0 0 10px #ffffff, 0 0 20px #ffffff, 0 0 30px #ffffff;
            box-shadow: 0 4px 10px rgba(0,0,0,0.4);
            z-index: 1000;
            line-height: 1.4;
        }
        
        /* Ocultar el formato de enlace por defecto para mantener el efecto neón */
        .banner-promo a {
            color: inherit;
            text-decoration: none;
        }
        
        .banner-promo span {
            font-size: 28px;
            display: block;
            cursor: pointer;
        }

        /* Contenedor principal */
        .contenedor { background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); text-align: center; width: 100%; max-width: 400px; margin-top: 60px; }
        input[type="email"] { width: 90%; padding: 10px; margin-bottom: 20px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; width: 100%; }
        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #cccccc; cursor: not-allowed; }
        .resultado { margin-top: 20px; font-weight: bold; color: #333; padding: 15px; border-radius: 5px; background-color: #e9ecef; word-break: break-all; }
        
        /* Estilos para la animación de carga */
        #cargando { display: none; margin-top: 20px; font-size: 15px; color: #555; font-weight: bold; }
        .spinner { border: 4px solid rgba(0, 0, 0, 0.1); border-left-color: #007bff; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto 10px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <!-- BANNER PUBLICITARIO LLAMATIVO CON ENLACE A WHATSAPP -->
    <div class="banner-promo">
        PROMOCIONES Y VENTAS:
        <a href="https://wa.me/51931877274" target="_blank">
            <span>+51 931 877 274</span>
        </a>
    </div>

    <div class="contenedor">
        <h2>Consultar Código Max</h2>
        <form method="POST" onsubmit="mostrarCarga()">
            <input type="email" name="correo" placeholder="Ingresa el correo de la cuenta" required>
            <br>
            <button type="submit" id="btn-consultar">Consultar Código</button>
        </form>
        
        <!-- Pantalla de carga (Oculta por defecto) -->
        <div id="cargando">
            <div class="spinner"></div>
            <p>⏳ Esperar aprox. 1 minuto, obteniendo código...</p>
        </div>

        {% if resultado %}
            <div class="resultado" id="resultado-final">
                <p>{{ resultado }}</p>
            </div>
        {% endif %}
    </div>

    <!-- Script para controlar el botón y la carga -->
    <script>
        function mostrarCarga() {
            // Deshabilitar el botón y cambiar su texto
            document.getElementById('btn-consultar').disabled = true;
            document.getElementById('btn-consultar').innerText = "Procesando...";
            
            // Mostrar la animación y texto de carga
            document.getElementById('cargando').style.display = 'block';
            
            // Ocultar el resultado del correo anterior si el usuario hace una nueva consulta
            var resultadoPrevio = document.getElementById('resultado-final');
            if (resultadoPrevio) {
                resultadoPrevio.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""

# --- RUTAS DE FLASK ---
@app_flask.route('/', methods=['GET', 'POST'])
def index():
    resultado = None
    if request.method == 'POST':
        correo = request.form.get('correo')
        try:
            # Crea un nuevo ciclo asíncrono para ejecutar Playwright desde la ruta web
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultado = loop.run_until_complete(extraer_codigo_web(correo))
            loop.close()
        except Exception as e:
            resultado = f"Error al procesar: {e}"
            
    return render_template_string(html_template, resultado=resultado)

@app_flask.route('/ping')
def ping():
    return "Bot activo y funcionando"

def run_flask():
    app_flask.run(host="0.0.0.0", port=10000)

# --- LÓGICA DE EXTRACCIÓN (CON REINTENTOS) ---
async def extraer_codigo_web(correo_cliente: str, max_intentos: int = 3) -> str:
    for intento in range(1, max_intentos + 1):
        async with async_playwright() as p:
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

            await page.route(
                "**/*", 
                lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_()
            )

            try:
                await page.goto("https://clientes.kingg.app/portal/login", timeout=60000)
                await page.get_by_placeholder("Tu usuario").fill("yersonmg29")
                await page.get_by_placeholder("Tu contraseña").fill("Yersonmg29cuentas*")
                await page.get_by_text("Ingresar a mis servicios").click()
        
                await page.wait_for_timeout(3000)
                await page.locator("text=Bots").first.click()
                await page.wait_for_selector("text=Buscar código o enlace", timeout=10000)

                await page.get_by_text("Seleccionar plataforma").click()
                await page.get_by_text("Max Estandar").first.click()
                await page.get_by_text("MAX", exact=True).first.click()

                await page.locator("input[type='text'], input[type='email']").last.fill(correo_cliente)
                await page.wait_for_timeout(1500)
                
                await page.get_by_text(correo_cliente).last.click()
                await page.get_by_role("button", name="Consultar").click()

                await page.wait_for_timeout(20000) 
                texto_pantalla = await page.locator("body").inner_text()
                
                busqueda = re.search(r'\b\d{3}\s?\d{3}\b', texto_pantalla)
                
                if busqueda:
                    codigo_encontrado = busqueda.group(0).replace(" ", "")
                    return f"✅ El código de Max es: {codigo_encontrado}"
                
                # Si no encuentra el código pero aún quedan intentos, espera 3 segundos y reintenta
                if intento < max_intentos:
                    await asyncio.sleep(3)
                    continue
                return "⚠️ Se hizo la consulta pero no se encontró el código en la pantalla tras varios intentos."

            except Exception as error:
                if intento < max_intentos:
                    await asyncio.sleep(3)
                    continue
                return f"❌ Error tras {max_intentos} intentos: {error}"
                
            finally:
                await context.close()
                await browser.close()

# --- LÓGICA DE TELEGRAM ---
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
    # Iniciar Flask en segundo plano
    hilo_flask = threading.Thread(target=run_flask, daemon=True)
    hilo_flask.start()

    # Iniciar bot de Telegram
    app = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("max", comando_max))
    print("🤖 Bot y servidor web Flask en línea. Esperando consultas...")
    app.run_polling()

if __name__ == "__main__":
    main()
