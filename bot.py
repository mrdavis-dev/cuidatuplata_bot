from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import certifi
import asyncio
import os

clave = os.getenv("CLAVE")
ca = certifi.where()
client = MongoClient(f"mongodb+srv://botpaylog:{clave}@cluster0.u6rqw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0", tlsCAFile=ca)
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
        # Crear botones inline para las categorías de gastos
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

        necesidades = ingreso * 0.5
        deseos = ingreso * 0.3
        ahorros = ingreso * 0.2

        collection.update_one(
            {"user_id": update.effective_user.id},
            {
                "$set": {
                    "periodo": "quincenal" if periodo == "q2" else "mensual",
                    "ingreso": ingreso,
                    "gastos_fijos": necesidades,
                    "gastos_variables": deseos,
                    "ahorros": ahorros
                }
            },
            upsert=True
        )

        await update.message.reply_text(
            f"¡Datos guardados! Según el método 50/30/20:\n"
            f"Gastos fijos: {necesidades:.2f}\n"
            f"Gastos variables: {deseos:.2f}\n"
            f"Ahorros: {ahorros:.2f}"
        )
        
        context.user_data['step'] = None
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un valor numérico para tu ingreso mensual.")

async def get_summary(chat_id, context):
    user_data = collection.find_one({'user_id': chat_id})
    user_periodo = user_data.get('periodo')
    fecha_actual = datetime.now()

    if user_periodo == 'mensual':
        fecha_inicio = fecha_actual.replace(day=1)  # Primer día del mes actual
    elif user_periodo == 'quincenal':
        if fecha_actual.day <= 15:  # Primera quincena
            fecha_inicio = fecha_actual.replace(day=1)
        else:  # Segunda quincena
            fecha_inicio = fecha_actual.replace(day=16)
    fecha_fin = fecha_actual  # Día actual como fin del rango

    user_data_registro = collection_reg.find({'user_id': chat_id,
                                              'fecha':{
                                                '$gte': fecha_inicio.strftime('%Y-%m-%d'),  # Desde fecha_inicio
                                                '$lte': fecha_fin.strftime('%Y-%m-%d')  # Hasta fecha_fin
                                              }})

    total_ingreso = 0
    total_ahorro_inversion = 0
    total_gastos_fijos = 0
    total_gastos_variables = 0

    for registro in user_data_registro:
        categoria = registro.get('categoria')
        monto = registro.get('monto', 0)

        if categoria == 'ingreso':
            total_ingreso =+ monto
        elif categoria == 'ahorro_o_inversion':
            total_ahorro_inversion += monto
        elif categoria == 'gasto_fijo':
            total_gastos_fijos += monto
        elif categoria == 'gasto_variable':
            total_gastos_variables += monto
    
    ingreso_total = user_data.get('ingreso', 0) + total_ingreso

    limite_gastos_fijos = ingreso_total * 0.50
    limite_gastos_variables = ingreso_total * 0.30
    limite_ahorros = ingreso_total * 0.20

    gastos_fijos_neto = total_gastos_fijos
    gastos_variables_neto = total_gastos_variables
    ahorros_neto = total_ahorro_inversion

    disponible_gastos_fijos = limite_gastos_fijos - total_gastos_fijos
    disponible_gastos_variables = limite_gastos_variables - total_gastos_variables
    disponible_ahorros = limite_ahorros - total_ahorro_inversion

    # Formatear cada categoría con alerta si se excede
    gastos_fijos_texto = (
        f"🔸 Gastos Fijos: {gastos_fijos_neto:.2f} (Referencia: máx 50% = {limite_gastos_fijos:.2f})\n"
        f"   ➡️ Disponible: {'⚠️ Excedido' if disponible_gastos_fijos < 0 else f'{disponible_gastos_fijos:.2f}'} 📉\n\n"
    )
    gastos_variables_texto = (
        f"🔸 Gastos Variables: {gastos_variables_neto:.2f} (Referencia: máx 30% = {limite_gastos_variables:.2f})\n"
        f"   ➡️ Disponible: {'⚠️ Excedido' if disponible_gastos_variables < 0 else f'{disponible_gastos_variables:.2f}'} 📉\n\n"
    )
    ahorros_texto = (
        f"🔸 Ahorros: {ahorros_neto:.2f} (Referencia: mín 20% = {limite_ahorros:.2f})\n"
        f"   ➡️ Disponible: {'⚠️ Excedido' if disponible_ahorros < 0 else f'{disponible_ahorros:.2f}'} 💹\n\n"
    )

    if user_data:
        await context.bot.send_message(
            chat_id,
            f"💰 *Desglose Financiero Actual (Referencia 50/30/20)* 💰\n\n"
            f"🔹 Ingreso Total: {ingreso_total:.2f} 💵\n\n"
            f"{gastos_fijos_texto}{gastos_variables_texto}{ahorros_texto}"
            f"📊 *Resumen General*: ¡Revisa tus gastos y ahorros! Asegúrate de alinearte con la referencia 50/30/20 para mantener tus finanzas en orden."
        )
    else:
        await context.bot.send_message(chat_id, "Aún no has registrado ningún ingreso. Usa /start para comenzar.")

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
    formatted_date = message_date.strftime('%Y-%m-%d %H:%M:%S')
    
    registro = {
        "user_id": update.effective_user.id,
        "fecha": formatted_date,
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
        secret_token="AAEmztxprgX1Ldd7gAvpyOMosbzj3zYBHmo",
        webhook_url=app_url
        # webhook_url='https://e520-190-219-103-156.ngrok-free.app'
    )

if __name__ == "__main__":
    main()