import os
import gc
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

# Candado global para evitar que 2 navegadores se abran al mismo segundo y saturen los 512 MB de RAM
navegador_lock = threading.Lock()

# Servidor Flask para la web y los pings
app_flask = Flask(__name__)

# --- DISEÑO VISUAL DE LA PÁGINA WEB ---
html_template = """
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Consultas HBO Max y Prime Video</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #12151c;
            color: #ffffff;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 110px 15px 30px 15px;
            box-sizing: border-box;
        }
        
        /* Estilos del banner de publicidad superior */
        .banner-promo {
            position: fixed;
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
            box-shadow: 0 4px 10px rgba(0,0,0,0.6);
            z-index: 1000;
            line-height: 1.4;
        }
        
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
        .wrapper {
            width: 100%;
            max-width: 440px;
        }

        /* Estilo de las 2 tarjetas (Prime Video y HBO Max) */
        .card-opcion {
            background: rgba(30, 35, 45, 0.92);
            border: 2px solid #2b3240;
            border-radius: 14px;
            padding: 20px 22px;
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 6px 15px rgba(0,0,0,0.35);
        }

        .card-opcion:hover {
            transform: translateY(-2px);
            border-color: #4a5568;
        }

        .card-opcion.activa-prime {
            border-color: #29b6f6;
            box-shadow: 0 0 15px rgba(41, 182, 246, 0.35);
        }

        .card-opcion.activa-max {
            border-color: #2563eb;
            box-shadow: 0 0 15px rgba(37, 99, 235, 0.4);
        }

        .card-info h3 {
            margin: 0 0 6px 0;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: #ffffff;
        }

        .card-info p {
            margin: 0;
            font-size: 14px;
            color: #b0b8c4;
        }

        .card-icono {
            width: 54px;
            height: 54px;
            border-radius: 12px;
            display: flex;
            justify-content: center;
            align-items: center;
            flex-shrink: 0;
            margin-left: 15px;
        }

        .icono-prime {
            background-color: #29b6f6;
            box-shadow: 0 0 10px rgba(41, 182, 246, 0.4);
        }

        .icono-max {
            background-color: #1d4ed8;
            box-shadow: 0 0 10px rgba(29, 78, 216, 0.5);
        }

        .card-icono svg {
            width: 28px;
            height: 28px;
            fill: none;
            stroke: #ffffff;
            stroke-width: 2;
            stroke-linecap: round;
            stroke-linejoin: round;
        }

        /* Caja del formulario que aparece al seleccionar */
        .contenedor-form {
            background-color: #1e232d;
            border: 1px solid #2e3646;
            padding: 25px;
            border-radius: 14px;
            box-shadow: 0 8px 20px rgba(0,0,0,0.45);
            text-align: center;
            margin-top: 10px;
            display: none;
        }

        .contenedor-form h2 {
            margin-top: 0;
            font-size: 20px;
            color: #ffffff;
            margin-bottom: 18px;
        }

        input[type="email"] {
            width: 100%;
            padding: 12px 14px;
            margin-bottom: 16px;
            border: 1px solid #3d4659;
            background-color: #13171f;
            color: #ffffff;
            border-radius: 8px;
            box-sizing: border-box;
            font-size: 15px;
            outline: none;
        }

        input[type="email"]:focus {
            border-color: #29b6f6;
        }

        button {
            background-color: #007bff;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            font-weight: bold;
            width: 100%;
            transition: background-color 0.2s;
        }

        button:hover { background-color: #0056b3; }
        button:disabled { background-color: #555; cursor: not-allowed; }

        .resultado {
            margin-top: 20px;
            font-weight: bold;
            color: #ffffff;
            padding: 16px;
            border-radius: 10px;
            background-color: #262d3b;
            border: 1px solid #3b4459;
            word-break: break-word;
            text-align: center;
            font-size: 17px;
        }
        
        /* Estilos para la animación de carga */
        #cargando { display: none; margin-top: 20px; font-size: 15px; color: #cbd5e1; font-weight: bold; }
        .spinner { border: 4px solid rgba(255, 255, 255, 0.15); border-left-color: #29b6f6; border-radius: 50%; width: 32px; height: 32px; animation: spin 1s linear infinite; margin: 0 auto 10px auto; }
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

    <div class="wrapper">
        <!-- OPCIÓN 1: PRIME VIDEO -->
        <div class="card-opcion" id="card-prime" onclick="seleccionarPlataforma('prime')">
            <div class="card-info">
                <h3>PRIME VIDEO</h3>
            </div>
            <div class="card-icono icono-prime">
                <svg viewBox="0 0 24 24">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                    <polygon points="12 11 9 15 15 15 12 11" fill="#ffffff"></polygon>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                </svg>
            </div>
        </div>

        <!-- OPCIÓN 2: HBO MAX -->
        <div class="card-opcion" id="card-max" onclick="seleccionarPlataforma('max')">
            <div class="card-info">
                <h3>HBO MAX</h3>
            </div>
            <div class="card-icono icono-max">
                <svg viewBox="0 0 24 24">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                    <polygon points="12 11 9 15 15 15 12 11" fill="#ffffff"></polygon>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                </svg>
            </div>
        </div>

        <!-- FORMULARIO DESPLEGABLE -->
        <div class="contenedor-form" id="caja-formulario">
            <h2 id="titulo-form">Consultar Código</h2>
            <form method="POST" onsubmit="mostrarCarga()">
                <input type="hidden" name="plataforma" id="input-plataforma" value="{{ plataforma_actual or 'max' }}">
                <input type="email" name="correo" placeholder="Ingresa el correo de la cuenta" required>
                <button type="submit" id="btn-consultar">Consultar Código</button>
            </form>
            
            <!-- Pantalla de carga (Oculta por defecto) -->
            <div id="cargando">
                <div class="spinner"></div>
                <p>⏳ Esperar aprox. 1 minuto, obteniendo código...</p>
            </div>
        </div>

        {% if resultado %}
            <div class="resultado" id="resultado-final">
                <p>{{ resultado }}</p>
            </div>
        {% endif %}
    </div>

    <script>
        function seleccionarPlataforma(plat) {
            const cardPrime = document.getElementById('card-prime');
            const cardMax = document.getElementById('card-max');
            const cajaForm = document.getElementById('caja-formulario');
            const inputPlat = document.getElementById('input-plataforma');
            const tituloForm = document.getElementById('titulo-form');
            const btnConsultar = document.getElementById('btn-consultar');

            cardPrime.classList.remove('activa-prime');
            cardMax.classList.remove('activa-max');
            cajaForm.style.display = 'block';
            inputPlat.value = plat;

            if (plat === 'prime') {
                cardPrime.classList.add('activa-prime');
                tituloForm.innerText = "Consultar Código Prime Video";
                btnConsultar.style.backgroundColor = "#0288d1";
            } else {
                cardMax.classList.add('activa-max');
                tituloForm.innerText = "Consultar Código HBO Max";
                btnConsultar.style.backgroundColor = "#1d4ed8";
            }
        }

        function mostrarCarga() {
            document.getElementById('btn-consultar').disabled = true;
            document.getElementById('btn-consultar').innerText = "Procesando...";
            document.getElementById('cargando').style.display = 'block';
            
            var resultadoPrevio = document.getElementById('resultado-final');
            if (resultadoPrevio) {
                resultadoPrevio.style.display = 'none';
            }
        }

        // Mantener seleccionada la tarjeta tras enviar una consulta
        {% if plataforma_actual %}
            seleccionarPlataforma('{{ plataforma_actual }}');
        {% endif %}
    </script>
</body>
</html>
"""

# --- RUTAS DE FLASK ---
@app_flask.route('/', methods=['GET', 'POST'])
def index():
    resultado = None
    plataforma_actual = None
    if request.method == 'POST':
        correo = request.form.get('correo', '').strip()
        plataforma_actual = request.form.get('plataforma', 'max').strip().lower()
        try:
            # El candado asegura que si hay otra consulta en curso, espere su turno sin duplicar la RAM
            with navegador_lock:
                resultado = asyncio.run(extraer_codigo_web(correo, plataforma_actual))
        except Exception as e:
            resultado = f"Error al procesar: {e}"
        finally:
            gc.collect()  # Limpiar memoria RAM inmediatamente
            
    return render_template_string(html_template, resultado=resultado, plataforma_actual=plataforma_actual)

@app_flask.route('/ping')
def ping():
    return "Bot activo y funcionando"

def run_flask():
    # threaded=True pero controlado por nuestro candado y sin recarga en modo debug
    app_flask.run(host="0.0.0.0", port=10000, debug=False, use_reloader=False)


# --- LÓGICA DE EXTRACCIÓN OPTIMIZADA (SOPORTA MAX Y PRIME VIDEO) ---
async def extraer_codigo_web(correo_cliente: str, plataforma: str = "max", max_intentos: int = 3) -> str:
    nombre_plat = "Prime Video" if plataforma == "prime" else "HBO Max"

    # Iniciamos Playwright UNA sola vez fuera del bucle de reintentos
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--no-zygote",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--mute-audio",
                "--js-flags=--max-old-space-size=128"  # Limita la RAM de JavaScript en el navegador
            ]
        )
        
        try:
            for intento in range(1, max_intentos + 1):
                context = await browser.new_context()
                page = await context.new_page()

                # Bloquear recursos pesados (imágenes, fuentes, multimedia)
                await page.route(
                    "**/*", 
                    lambda route: route.abort() if route.request.resource_type in ["image", "font", "media"] else route.continue_()
                )

                try:
                    await page.goto("https://clientes.kingg.app/portal/login", timeout=45000)
                    await page.get_by_placeholder("Tu usuario").fill("yersonmg29")
                    await page.get_by_placeholder("Tu contraseña").fill("Yersonmg29cuentas*")
                    await page.get_by_text("Ingresar a mis servicios").click()
            
                    await page.wait_for_timeout(3000)
                    await page.locator("text=Bots").first.click()
                    await page.wait_for_selector("text=Buscar código o enlace", timeout=10000)

                   # 1. Seleccionar plataforma según la opción elegida (HBO Max o Prime Video)
                    await page.get_by_text("Seleccionar plataforma").click()
                    await page.wait_for_timeout(1000)

                    if plataforma == "prime":
                        # Usamos .last para asegurarnos de tocar la opción del menú desplegable recién abierto
                        await page.get_by_text("Prime Video", exact=True).last.click()
                        await page.wait_for_timeout(800)
                        await page.get_by_text("Código de acceso").last.click()
                    else:
                        # Flujo original de HBO Max
                        await page.get_by_text("Max Estandar").last.click()
                        await page.wait_for_timeout(800)
                        await page.get_by_text("MAX", exact=True).first.click()

                    await page.wait_for_timeout(1000)

                    # 2. Escribir el correo en la casilla (idéntico al de Max que ya funcionaba)
                    await page.locator("input[type='text'], input[type='email']").last.fill(correo_cliente)
                    await page.wait_for_timeout(1500)
                    
                    # 3. Seleccionar el correo que se despliega abajo y dar clic en Consultar
                    await page.get_by_text(correo_cliente).last.click()
                    await page.get_by_role("button", name="Consultar").click()

                    # 4. Espera inteligente: revisa cada 2 segundos (hasta 20s) para cerrar apenas salga el código
                    await page.wait_for_timeout(4000)
                    for _ in range(8):
                        texto_pantalla = await page.locator("body").inner_text()
                        # Recortamos a partir de "MÁS RECIENTE" o "CÓDIGO DE ACCESO" si aparece para mayor precisión
                        zona_busqueda = texto_pantalla
                        if "MÁS RECIENTE" in texto_pantalla:
                            zona_busqueda = texto_pantalla.split("MÁS RECIENTE")[-1]

                        busqueda = re.search(r'\b\d{3}\s+\d{3}\b|\b\d{6}\b', zona_busqueda)
                        if busqueda:
                            codigo_encontrado = re.sub(r'\D', '', busqueda.group(0))
                            return f"✅ El código de {nombre_plat} es: {codigo_encontrado}"
                        await page.wait_for_timeout(2000)
                    
                    if intento < max_intentos:
                        await asyncio.sleep(2)
                        continue
                    return f"⚠️ Se hizo la consulta de {nombre_plat} pero no se encontró el código tras varios intentos."

                except Exception as error:
                    if intento < max_intentos:
                        await asyncio.sleep(2)
                        continue
                    return f"❌ Error tras {max_intentos} intentos: {error}"
                
                finally:
                    # Cerramos la pestaña y el contexto tras cada intento para no acumular RAM
                    await page.close()
                    await context.close()
        finally:
            # Cerramos el navegador por completo y liberamos la memoria
            await browser.close()
            gc.collect()


# --- LÓGICA DE TELEGRAM ---
async def procesar_comando_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE, plataforma: str):
    user_id = update.effective_user.id
    nombre_plat = "Prime Video" if plataforma == "prime" else "HBO Max"
    cmd_ejemplo = "/prime" if plataforma == "prime" else "/max"
    
    if user_id not in IDS_PERMITIDOS:
        await update.message.reply_text("⛔ Acceso denegado. Tu ID no está registrado.")
        return

    try:
        correo = context.args[0].strip()
        await update.message.reply_text(f"🔍 Consultando código de {nombre_plat} para:\n{correo}\nPor favor, espera unos segundos...")
        
        loop = asyncio.get_running_loop()
        def tarea_sincronizada():
            with navegador_lock:
                return asyncio.run(extraer_codigo_web(correo, plataforma))
                
        resultado = await loop.run_in_executor(None, tarea_sincronizada)
        await update.message.reply_text(resultado)
        
    except IndexError:
        await update.message.reply_text(f"⚠️ Formato incorrecto. Por favor envía:\n{cmd_ejemplo} correo@cuenta.com")
    finally:
        gc.collect()

async def comando_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await procesar_comando_telegram(update, context, "max")

async def comando_prime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await procesar_comando_telegram(update, context, "prime")

def main():
    # Iniciar Flask en segundo plano
    hilo_flask = threading.Thread(target=run_flask, daemon=True)
    hilo_flask.start()

    # Iniciar bot de Telegram
    app = Application.builder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("max", comando_max))
    app.add_handler(CommandHandler("prime", comando_prime))
    print("🤖 Bot (Max + Prime) y servidor web Flask en línea. Esperando consultas...")
    app.run_polling()

if __name__ == "__main__":
    main()
