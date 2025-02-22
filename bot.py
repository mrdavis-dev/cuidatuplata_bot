from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ConversationHandler, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timezone
from pytz import timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import google.generativeai as genai
import threading
import asyncio
import os

ESPERANDO_FECHA = 1

clave = os.environ.get('CLAVE')
gemini_key = os.environ.get('GEMINI_KEY')
client = MongoClient(f"mongodb://mongo:{clave}@roundhouse.proxy.rlwy.net:47036")
# client = MongoClient("mongodb://localhost:27017/")
db = client["paylog"]
collection = db["users"]
collection_reg = db["registro"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name

    user_timezone = context.user_data.get('timezone', 'UTC')  # Default: UTC
    # Convertir la fecha a la zona horaria del usuario
    tz = timezone(user_timezone)
    local_date = update.message.date.astimezone(tz)
    
    existing_user = collection.find_one({"user_id": user_id})
    if not existing_user:
        collection.insert_one({
            "user_id": user_id,
            "name": user_name,
            "created_at": local_date
        })

    await update.message.reply_text(
        f"Hola {user_name}! Soy tu bot de finanzas. ¿Qué deseas hacer?",
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    # Verificamos el paso actual para determinar la acción
    step = context.user_data.get('step')

    if step == 'get_monto':
        await handle_monto(update, context)
    elif step == 'get_descripcion':
        await handle_descripcion(update, context)
    elif text == 'resumen':
        await get_summary(update, context)
    elif step == ESPERANDO_FECHA:  # Si está esperando una fecha, vamos al proceso de resumen
        await process_summary(update, context)
    elif text == 'ingresar':
        keyboard = [
            [InlineKeyboardButton("🎯 Gasto fijo", callback_data='gasto_fijo')],
            [InlineKeyboardButton("🎲 Gastos variables", callback_data='gasto_variable')],
            [InlineKeyboardButton("🧩 Ahorro o inversion", callback_data='ahorro_o_inversion')],
            [InlineKeyboardButton("💵 Ingreso", callback_data='ingreso')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Por favor, selecciona una categoría.", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Por favor, selecciona una opción del menú.")


async def get_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.message.chat_id
    user = collection.find_one({'user_id': chat_id})

    if not user:
        await update.message.reply_text("Usuario no encontrado.")
        return ConversationHandler.END

    context.user_data['step'] = ESPERANDO_FECHA

    await update.message.reply_text(
        "Por favor, escribe desde qué fecha hasta qué fecha necesitas el resumen.\n"
        "Ejemplo: `1 de enero al 15 de enero` o `2024-01-01 a 2024-01-15`"
    )

    return ESPERANDO_FECHA

async def process_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.message.chat_id
    input_user = update.message.text  # Guardamos la respuesta del usuario

    if context.user_data.get('step') != ESPERANDO_FECHA:
        await update.message.reply_text("Por favor, selecciona una opción del menú.")
        return ConversationHandler.END
    
    # Obtener los registros del usuario
    registros = list(collection_reg.find({'user_id': chat_id}))

    if not registros:
        await update.message.reply_text("No se encontraron registros en ese período.")
        return ConversationHandler.END

    # Formatear la respuesta
    lista_registros = [
        f"{reg['descripcion']} - {reg['monto']} - {reg['fecha'].strftime('%Y-%m-%d')}"
        for reg in registros
    ]
    respuesta = "\n".join(lista_registros)

    # Generar informe con IA
    genai.configure(api_key = gemini_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    Genera un informe financiero corto.

    Fechas a utilizar para hacer el resumen:
    {input_user}

    Transacciones a analizar:
    {respuesta}
    """
    response = model.generate_content(prompt)

    # Enviar el resumen generado por IA al usuario
    await update.message.reply_text("Aquí tienes tu resumen financiero:")
    await update.message.reply_text(response.text)

    context.user_data['step'] = None
    return ConversationHandler.END  # Finaliza la conversación

async def start_insert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra las opciones de categorías cuando el usuario usa /ingresar"""
    keyboard = [
        [InlineKeyboardButton("🎯 Gasto fijo", callback_data='gasto_fijo')],
        [InlineKeyboardButton("🎲 Gastos variables", callback_data='gasto_variable')],
        [InlineKeyboardButton("🧩 Ahorro o inversión", callback_data='ahorro_o_inversion')],
        [InlineKeyboardButton("💵 Ingreso", callback_data='ingreso')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Por favor, selecciona una categoría.", reply_markup=reply_markup)

async def insert_expenses_or_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    categoria = query.data
    context.user_data["categoria"] = categoria

    if categoria in ['gasto_fijo', 'gasto_variable', 'ahorro_o_inversion', 'ingreso']:
        await context.bot.send_message(query.message.chat.id, "Ingresa el monto:")
        context.user_data['step'] = "get_monto"

async def handle_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        monto = float(update.message.text)
        context.user_data['monto'] = monto
        categoria = context.user_data.get('categoria')

        await context.bot.send_message(update.message.chat.id, f"El monto es: {monto:.2f}.")
        if categoria == 'ingreso':
            await context.bot.send_message(update.message.chat.id, "Ingresa una descripción para este ingreso:")
        else:
            await context.bot.send_message(update.message.chat.id, "Ingresa una descripción para este gasto:")
        context.user_data['step'] = 'get_descripcion'
    except ValueError:
        await context.bot.send_message(update.message.chat.id, "Por favor, ingresa un valor numérico válido para el monto.")

async def handle_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    descripcion = update.message.text
    categoria = context.user_data.get('categoria')
    monto = context.user_data.get('monto')
    
    message_date = update.message.date
    user_timezone = context.user_data.get('timezone', 'UTC')  # Default: UTC

    # Convertir la fecha a la zona horaria del usuario
    tz = timezone(user_timezone)
    local_date = message_date.astimezone(tz)
    
    registro = {
        "user_id": update.effective_user.id,
        "fecha": local_date,
        "categoria": categoria,
        "monto": monto,
        "descripcion": descripcion
    }
    
    collection_reg.insert_one(registro)
    
    await context.bot.send_message(
        update.message.chat.id, 
        f"Registrado creado:\nCategoría: {categoria}\nMonto: {monto:.2f}\nDescripción: {descripcion}"
    )

    context.user_data['step'] = None
    del context.user_data['categoria']
    del context.user_data['monto']



async def send_reminders(app):
    users = collection.find({})  # Obtener todos los usuarios

    for user in users:
        user_id = user.get("user_id")  # Obtener el user_id

        try:
            await app.bot.send_message(user_id, "¡Recuerda registrar tus ingresos o gastos para mantener tu control financiero!")
            print(f"Mensaje enviado a {user_id}")

        except Exception as e:
            print(f"Error al enviar mensaje a {user_id}: {e}")

async def schedule_reminders(app):
    """Ejecuta send_reminders cada cierto tiempo."""
    await asyncio.sleep(28800)

    while True:
        await send_reminders(app)
        await asyncio.sleep(28800)  # 8 horas

def start_schedule_reminders(app):
    """Ejecuta schedule_reminders en un hilo separado."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(schedule_reminders(app))


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app_url = os.getenv('URL')

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("ingresar", start_insert))
    app.add_handler(CallbackQueryHandler(insert_expenses_or_income, pattern='^(gasto_fijo|gasto_variable|ahorro_o_inversion|ingreso)$'))
    
    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("resumen", get_summary)],
        states={
            ESPERANDO_FECHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_summary)],
        },
        fallbacks=[]  # Puedes agregar fallbacks si es necesario
    )
    app.add_handler(conversation_handler)

    # Iniciar el bucle de recordatorios en un hilo separado
    reminder_thread = threading.Thread(target=start_schedule_reminders, args=(app,), daemon=True)
    reminder_thread.start()

    app.run_webhook(
        listen='0.0.0.0',
        port=8000,
        secret_token = token.split(":", 1)[1].strip(),
        webhook_url=app_url
        # webhook_url='https://f2a8-181-197-40-234.ngrok-free.app'
    )

if __name__ == "__main__":
    main()