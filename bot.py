import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
# ===== CONEXIÓN MYSQL =====
import mysql.connector

def conectar_db():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME")
    )

# ===== IMPORTS =====
import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes


# ===== LOGGING LIMPIO =====
logging.basicConfig(level=logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# ===== CONFIG JSON =====
with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# ===== MEMORIA =====
user_data_temp = {}

# ===== RUTA =====
RUTA_BASE = "FOTOS_OBRA"

# ===== LIMPIEZA =====
import unicodedata
import re

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

    # ===== PROYECTO =====
    if tipo == "proyecto":
        data["proyecto"] = valor

        categorias = CONFIG[valor]["categorias"].keys()
        keyboard = [[InlineKeyboardButton(c, callback_data=f"categoria|{c}")] for c in categorias]
        keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|start")])

        await query.edit_message_text("Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))

    # ===== CATEGORIA =====
    elif tipo == "categoria":
        if "proyecto" not in data:
            await query.edit_message_text("Reinicia con /start")
            return

        data["categoria"] = valor

        conceptos = CONFIG[data["proyecto"]]["categorias"][data["categoria"]]["conceptos"]
        keyboard = [[InlineKeyboardButton(c, callback_data=f"concepto|{c}")] for c in conceptos]
        keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|proyecto")])

        await query.edit_message_text("Concepto:", reply_markup=InlineKeyboardMarkup(keyboard))

    # ===== CONCEPTO =====
    elif tipo == "concepto":
        data["concepto"] = valor

        areas = CONFIG[data["proyecto"]]["categorias"][data["categoria"]]["conceptos"].get(valor, [])
        keyboard = [[InlineKeyboardButton(a, callback_data=f"area|{a}")] for a in areas]

        keyboard.append([InlineKeyboardButton("OTROS", callback_data="area|OTROS")])
        keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|categoria")])

        await query.edit_message_text("Área:", reply_markup=InlineKeyboardMarkup(keyboard))

    # ===== AREA =====
    elif tipo == "area":
        data["area"] = valor

        etapas = ["ANTES", "DURANTE", "FINAL"]
        keyboard = [[InlineKeyboardButton(e, callback_data=f"etapa|{e}")] for e in etapas]
        keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|concepto")])

        await query.edit_message_text("Etapa:", reply_markup=InlineKeyboardMarkup(keyboard))

    # ===== ETAPA =====
    elif tipo == "etapa":
        data["etapa"] = valor
        data["lote"] = generar_lote(data["proyecto"])

        keyboard = [
            [InlineKeyboardButton("FINALIZAR", callback_data="finalizar|ok")],
            [InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|area")]
        ]

        await query.edit_message_text(
            f"Lote: {data['lote']}\nEnvía fotos",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ===== FINALIZAR =====
    elif tipo == "finalizar":
        user_data_temp.pop(user_id, None)
        await query.edit_message_text("Sesión finalizada. Usa /start")

    # ===== BACK =====
    elif tipo == "back":
        paso = valor

        if paso == "start":
            keyboard = [[InlineKeyboardButton(p, callback_data=f"proyecto|{p}")] for p in CONFIG.keys()]
            await query.edit_message_text("Selecciona proyecto:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif paso == "proyecto":
            categorias = CONFIG[data["proyecto"]]["categorias"].keys()
            keyboard = [[InlineKeyboardButton(c, callback_data=f"categoria|{c}")] for c in categorias]
            keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|start")])

            await query.edit_message_text("Categoría:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif paso == "categoria":
            conceptos = CONFIG[data["proyecto"]]["categorias"][data["categoria"]]["conceptos"]
            keyboard = [[InlineKeyboardButton(c, callback_data=f"concepto|{c}")] for c in conceptos]
            keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|proyecto")])

            await query.edit_message_text("Concepto:", reply_markup=InlineKeyboardMarkup(keyboard))

        elif paso == "concepto":
            areas = CONFIG[data["proyecto"]]["categorias"][data["categoria"]]["conceptos"].get(data["concepto"], [])
            keyboard = [[InlineKeyboardButton(a, callback_data=f"area|{a}")] for a in areas]
            keyboard.append([InlineKeyboardButton("OTROS", callback_data="area|OTROS")])
            keyboard.append([InlineKeyboardButton("⬅️ ATRÁS", callback_data="back|categoria")])

            await query.edit_message_text("Área:", reply_markup=InlineKeyboardMarkup(keyboard))

# ===== FOTO =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_temp.get(user_id)

    if not data:
        await update.message.reply_text("Usa /start primero")
        return

    proyecto = data["proyecto"]
    categoria = data["categoria"]
    concepto = data["concepto"]
    area = data["area"]
    etapa = data["etapa"]
    lote = data["lote"]

    carpeta = os.path.join(RUTA_BASE, limpiar_nombre(proyecto))
    crear_carpeta(carpeta)

    consecutivo = obtener_consecutivo(proyecto)

    nombre = f"{lote}_{categoria}_{concepto}_{area}_{etapa}_{consecutivo}.jpg"
    ruta = os.path.join(carpeta, nombre)

    foto = update.message.photo[-1]
    file = await context.bot.get_file(foto.file_id)
    await file.download_to_drive(ruta)

    guardar_en_db(
        {
            "lote": lote,
            "archivo": nombre,
            "proyecto": proyecto,
            "categoria": categoria,
            "concepto": concepto,
            "area": area,
            "etapa": etapa
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
