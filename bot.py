from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta
from pytz import timezone
from apscheduler.schedulers.background import BackgroundScheduler
import google.generativeai as genai
import asyncio
import os

clave = os.environ.get('CLAVE')
# client = MongoClient(f"mongodb+srv://botpaylog:{clave}@cluster0.u6rqw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0&tlsAllowInvalidCertificates=true")
client = MongoClient("mongodb://localhost:27017/")
db = client["paylog"]
collection = db["users"]
collection_reg = db["registro"]


def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        [['Ingresar Ingreso', 'Ver Resumen', 'Ingresar gastos']],
        one_time_keyboard=True,
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = get_reply_keyboard()
    
    await update.message.reply_text(
        "Hola! Soy tu bot de finanzas. ¿Qué deseas hacer?",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    # Verificamos el paso actual para determinar la acción
    step = context.user_data.get('step')

    if step == 'get_income':
        await get_income(update, context)
    if step == 'set_income':
        await set_income(update, context)
    elif step == 'get_monto':
        await handle_monto(update, context)
    elif step == 'get_descripcion':
        await handle_descripcion(update, context)
    elif text == 'Ingresar Ingreso':
        keyboard = [
            [InlineKeyboardButton("Quincenal", callback_data='q2')],
            [InlineKeyboardButton("Mensual", callback_data='m1')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Por favor, ingresa tu ingreso mensual o quincenal.", reply_markup=reply_markup)
    elif text == 'Ver Resumen':
        await get_summary(update.message.chat.id, context)
    elif text == 'Ingresar gastos':
        keyboard = [
            [InlineKeyboardButton("🎯 Gasto fijo", callback_data='gasto_fijo')],
            [InlineKeyboardButton("🎲 Gastos variables", callback_data='gasto_variable')],
            [InlineKeyboardButton("🧩 Ahorro o inversion", callback_data='ahorro_o_inversion')],
            [InlineKeyboardButton("💵 Ingreso", callback_data='ingreso')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Por favor, selecciona una categoría.", reply_markup=reply_markup)
    else:
        if context.user_data.get("step") == "get_income":
            await get_income(update, context)
        else:
            await update.message.reply_text("Por favor, selecciona una opción del menú.")


async def get_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        periodo = query.data
        context.user_data["periodo"] = periodo

        msj_context = f"Ingresa el monto quincenal: " if periodo == "q2" else f"Ingresa el monto mensual: "

        if periodo in ['q2', 'm1']:
            await context.bot.send_message(query.message.chat.id, msj_context)
            context.user_data['step'] = "set_income"

async def set_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        ingreso = float(update.message.text)
        context.user_data["ingreso"] = ingreso
        periodo = context.user_data.get('periodo')

        collection.update_one(
            {"user_id": update.effective_user.id},
            {
                "$set": {
                    "periodo": "quincenal" if periodo == "q2" else "mensual",
                    "ingreso": ingreso
                }
            },
            upsert=True
        )

        await update.message.reply_text(
            f"¡Datos guardados!\n"
        )
        
        context.user_data['step'] = None
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un valor numérico para tu ingreso mensual o quincenal.")

async def get_summary(chat_id, context):
    user = collection.find_one({'user_id': chat_id})
    if not user:
        # print("Usuario no encontrado en la base de datos.")
        return "Usuario no encontrado."
    
    # print(f"Usuario encontrado: {user}")  # Verificar datos del usuario
    
    user_periodo = user.get('periodo')  # "mensual" o "quincenal"
    fecha_actual = datetime.now()
    # print(f"Periodo del usuario: {user_periodo}")
    # print(f"Fecha actual: {fecha_actual}")

    # Define las fechas de inicio y fin según el periodo
    if user_periodo == "mensual":
        inicio = datetime(fecha_actual.year, fecha_actual.month, 1)
        fin = fecha_actual  # Hasta hoy
        print(f"Periodo mensual: Inicio: {inicio}, Fin: {fin}")
    elif user_periodo == "quincenal":
        dia_actual = fecha_actual.day
        if dia_actual <= 15:  # Primera quincena
            inicio = datetime(fecha_actual.year, fecha_actual.month, 1)
        else:  # Segunda quincena
            inicio = datetime(fecha_actual.year, fecha_actual.month, 16)
        fin = fecha_actual  # Hasta hoy
        print(f"Periodo quincenal: Inicio: {inicio}, Fin: {fin}")
    else:
        print("Periodo no válido configurado en el usuario.")
        return "Periodo no válido. Configure 'mensual' o 'quincenal'."

    # Filtrar registros por fecha
    registros = collection_reg.find({
        'user_id': chat_id,
        'fecha': {
            '$gte': inicio,
            '$lte': fin
        }
    })

    registros = list(registros)  # Convertir a lista para depuración
    # print(f"Registros encontrados: {registros}")  # Verificar los registros encontrados

    # Formatea la respuesta
    lista_registros = [f"{reg['descripcion']} - {reg['monto']} - {reg['fecha']}" for reg in registros]
    if not lista_registros:
        # print("No se encontraron registros en este periodo.")
        return "No se encontraron registros en este periodo."

    respuesta = "\n".join(lista_registros)
    print(f"Respuesta generada:\n{respuesta}")  # Verificar la respuesta final

    # funcion con IA
    genai.configure(api_key="AIzaSyBC__t_3GCTPwpoMz-h147OEwdZVwX5gqU")
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = f"""
    A continuación se muestra un resumen de transacciones financieras del usuario. Por favor, genera un informe detallado y profesional que incluya:
    1. Una introducción general sobre el periodo cubierto.
    2. Un desglose de las transacciones agrupadas por categoría (si aplica).
    3. Un análisis general que resuma el total gastado o ingresado.
    4. Observaciones o recomendaciones basadas en los datos.

    Resumen de transacciones:
    {respuesta}

    Genera el informe en un tono profesional y claro.
    """
    response = model.generate_content(prompt)
    print(response.text)


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
    async with app:
        users = collection.find({})
        for user in users:
            try:
                user_id = user["user_id"]
                await app.bot.send_message(user_id, "¡Recuerda registrar tus ingresos o gastos para mantener tu control financiero!")
            except Exception as e:
                print(f"Error al enviar mensaje a {user_id}: {e}")

def schedule_notifications(app):
    scheduler = BackgroundScheduler()
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    def send_task():
        asyncio.run_coroutine_threadsafe(send_reminders(app), loop)

    scheduler.add_job(
        send_task,
        'interval',
        hours=8
    )
    scheduler.start()   


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(token).build()
    app_url = os.getenv('RENDER_EXTERNAL_URL')

    schedule_notifications(app)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(insert_expenses_or_income, pattern='^(gasto_fijo|gasto_variable|ahorro_o_inversion|ingreso)$'))
    app.add_handler(CallbackQueryHandler(get_income, pattern='^(q2|m1)$'))
    
    app.run_webhook(
        listen='0.0.0.0',
        port=8000,
        secret_token="AAEhVYUgyOzFkxzdqkdE0-9pysEH8-y8ttg",
        # webhook_url=app_url
        webhook_url='https://0909-190-219-103-238.ngrok-free.app'
    )

if __name__ == "__main__":
    main()