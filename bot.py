import os
import json
import logging
from datetime import datetime
import unicodedata
import re
import mysql.connector
import asyncio  # ✅ agregado

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ===== VARIABLES DE ENTORNO =====
TOKEN = os.getenv("TELEGRAM_TOKEN")

# ===== CONEXIÓN MYSQL =====
def conectar_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# ===== LOGGING =====
logging.basicConfig(level=logging.WARNING)

# ===== CONFIG =====
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

user_data_temp = {}

# ===== RUTA TEMPORAL =====
RUTA_BASE = "/tmp/fotos"

# ===== LIMPIEZA =====
def limpiar_nombre(nombre):
    nombre = unicodedata.normalize('NFKD', nombre).encode('ascii', 'ignore').decode('ascii')
    nombre = re.sub(r'[^A-Za-z0-9_]', '_', nombre)
    return nombre.upper()

# ===== LOTE =====
def generar_lote(proyecto):
    fecha = datetime.now().strftime("%Y%m%d")
    return f"{limpiar_nombre(proyecto)}-{fecha}"

# ===== CONSECUTIVO =====
def obtener_consecutivo(proyecto):
    archivo = "contador_proyectos.json"

    if os.path.exists(archivo):
        with open(archivo, "r") as f:
            data = json.load(f)
    else:
        data = {}

    data[proyecto] = data.get(proyecto, 0) + 1

    with open(archivo, "w") as f:
        json.dump(data, f)

    return str(data[proyecto]).zfill(3)

# ===== CARPETA =====
def crear_carpeta(ruta):
    if not os.path.exists(ruta):
        os.makedirs(ruta)

# ===== MYSQL =====
def guardar_en_db(data, user_id, usuario):
    conn = conectar_db()
    cursor = conn.cursor()

    query = """
    INSERT INTO fotos 
    (lote, archivo, proyecto, categoria, concepto, area, etapa, estado, user_id, usuario)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    valores = (
        data["lote"],
        data["archivo"],
        data["proyecto"],
        data["categoria"],
        data["concepto"],
        data["area"],
        data["etapa"],
        "STANDBY",
        user_id,
        usuario
    )

    cursor.execute(query, valores)
    conn.commit()

    cursor.close()
    conn.close()

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data_temp[user_id] = {}

    keyboard = [[InlineKeyboardButton(p, callback_data=f"proyecto|{p}")] for p in CONFIG.keys()]
    await update.message.reply_text("Selecciona proyecto:", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== BOTONES =====
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id not in user_data_temp:
        user_data_temp[user_id] = {}

    data = user_data_temp[user_id]
    tipo, valor = query.data.split("|")

    if tipo == "proyecto":
        data["proyecto"] = valor
        categorias = CONFIG[valor]["categorias"].keys()
        keyboard = [[InlineKeyboardButton(c, callback_data=f"categoria|{c}")] for c in categorias]
        await query.edit_message_text("Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif tipo == "categoria":
        data["categoria"] = valor
        conceptos = CONFIG[data["proyecto"]]["categorias"][valor]["conceptos"]
        keyboard = [[InlineKeyboardButton(c, callback_data=f"concepto|{c}")] for c in conceptos]
        await query.edit_message_text("Concepto:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif tipo == "concepto":
        data["concepto"] = valor
        areas = CONFIG[data["proyecto"]]["categorias"][data["categoria"]]["conceptos"].get(valor, [])
        keyboard = [[InlineKeyboardButton(a, callback_data=f"area|{a}")] for a in areas]
        keyboard.append([InlineKeyboardButton("OTROS", callback_data="area|OTROS")])
        await query.edit_message_text("Área:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif tipo == "area":
        data["area"] = valor
        etapas = ["ANTES", "DURANTE", "FINAL"]
        keyboard = [[InlineKeyboardButton(e, callback_data=f"etapa|{e}")] for e in etapas]
        await query.edit_message_text("Etapa:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif tipo == "etapa":
        data["etapa"] = valor
        data["lote"] = generar_lote(data["proyecto"])
        await query.edit_message_text(f"Lote: {data['lote']}\nEnvía fotos")

# ===== FOTO =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_temp.get(user_id)

    if not data:
        await update.message.reply_text("Usa /start primero")
        return

    carpeta = os.path.join(RUTA_BASE, limpiar_nombre(data["proyecto"]))
    crear_carpeta(carpeta)

    consecutivo = obtener_consecutivo(data["proyecto"])

    nombre = f"{data['lote']}_{data['categoria']}_{data['concepto']}_{data['area']}_{data['etapa']}_{consecutivo}.jpg"
    ruta = os.path.join(carpeta, nombre)

    print("📸 Foto recibida")
    print(f"Ruta: {ruta}")

    foto = update.message.photo[-1]
    file = await foto.get_file()  # ✅ corregido
    await file.download_to_drive(ruta)

    print("✅ Imagen guardada")

    await asyncio.to_thread(  # ✅ evita bloqueo por MySQL
        guardar_en_db,
        {
            "lote": data["lote"],
            "archivo": nombre,
            "proyecto": data["proyecto"],
            "categoria": data["categoria"],
            "concepto": data["concepto"],
            "area": data["area"],
            "etapa": data["etapa"]
        },
        user_id,
        update.effective_user.username or "SIN_USERNAME"
    )

    await update.message.reply_text(nombre)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(handle_buttons))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Bot corriendo...")
app.run_polling()
