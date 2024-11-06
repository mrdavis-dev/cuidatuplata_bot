from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes
from datetime import datetime
import os

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
        "Hola! Soy tu bot de finanzas 50/30/20. ¿Qué deseas hacer?",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    # Verificamos el paso actual para determinar la acción
    step = context.user_data.get('step')

    if step == 'get_income':
        await get_income(update, context)
    elif step == 'get_monto':
        await handle_monto(update, context)
    elif step == 'get_descripcion':
        await handle_descripcion(update, context)
    elif text == 'Ingresar Ingreso':
        await update.message.reply_text("Por favor, ingresa tu ingreso mensual.")
        context.user_data['step'] = "get_income"
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
        await update.message.reply_text("Por favor, selecciona una opción del menú.")

async def get_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        ingreso = float(update.message.text)
        context.user_data["ingreso"] = ingreso

        necesidades = ingreso * 0.5
        deseos = ingreso * 0.3
        ahorros = ingreso * 0.2

        collection.update_one(
            {"user_id": update.effective_user.id},
            {
                "$set": {
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
    user_data = collection.find_one({"user_id": chat_id})
    
    if user_data:
        await context.bot.send_message(chat_id,
            f"Este es tu desglose financiero actual:\n"
            f"Ingreso: {user_data['ingreso']:.2f}\n"
            f"Gastos fijos: {user_data['gastos_fijos']:.2f}\n"
            f"Gastos variables: {user_data['gastos_variables']:.2f}\n"
            f"Ahorros: {user_data['ahorros']:.2f}"
        )
    else:
        await context.bot.send_message(chat_id, "Aún no has registrado ningún ingreso. Usa /start para comenzar.")

async def insert_expenses_or_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    categoria = query.data
    context.user_data["categoria"] = categoria

    if categoria in ['gasto_fijo', 'gasto_variable', 'ahorro_o_inversion']:
        await context.bot.send_message(query.message.chat.id, "Ingresa el monto:")
        context.user_data['step'] = "get_monto"

async def handle_monto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        monto = float(update.message.text)
        context.user_data['monto'] = monto

        await context.bot.send_message(update.message.chat.id, f"El monto es: {monto:.2f}.")
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
        f"Gasto registrado:\nCategoría: {categoria}\nMonto: {monto:.2f}\nDescripción: {descripcion}"
    )

    context.user_data['step'] = None
    del context.user_data['categoria']
    del context.user_data['monto']

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(insert_expenses_or_income))
    
    app.run_polling()

if __name__ == "__main__":
    main()
