from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
import os

client = MongoClient("mongodb://localhost:27017/")
db = client["paylog"]
collection = db["users"]

# Define a function to create a reply keyboard
def get_reply_keyboard():
    return ReplyKeyboardMarkup(
        [['Ingresar Ingreso', 'Ver Resumen']],
        one_time_keyboard=False,  # Keep the keyboard open
        resize_keyboard=True  # Resize buttons for better appearance
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_markup = get_reply_keyboard()
    
    await update.message.reply_text(
        "Hola! Soy tu bot de finanzas 50/30/20. ¿Qué deseas hacer?",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    if text == 'Ingresar Ingreso':
        await update.message.reply_text("Por favor, ingresa tu ingreso mensual.")
        context.user_data["step"] = "get_income"
    elif text == 'Ver Resumen':
        await get_summary(update.message.chat.id, context)
    else:
        await update.message.reply_text("Por favor, selecciona una opción del menú.")

async def get_income(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("step") != "get_income":
        await update.message.reply_text("Por favor, comienza con el comando /start.")
        return

    try:
        ingreso = float(update.message.text)
        context.user_data["ingreso"] = ingreso

        # Cálculos según el método 50/30/20...
        await update.message.reply_text(f"¡Datos guardados! Ingreso registrado como {ingreso:.2f}.")
        
    except ValueError:
        await update.message.reply_text("Por favor, ingresa un valor numérico para tu ingreso mensual.")

async def get_summary(chat_id, context):
    user_data = collection.find_one({"user_id": chat_id})
    
    if user_data:
        await context.bot.send_message(chat_id,
            f"Este es tu desglose financiero actual:\n"
            f"Ingreso: {user_data['ingreso']:.2f}\n"
            f"Necesidades: {user_data['necesidades']:.2f}\n"
            f"Deseos: {user_data['deseos']:.2f}\n"
            f"Ahorros: {user_data['ahorros']:.2f}"
        )
    else:
        await context.bot.send_message(chat_id, "Aún no has registrado ningún ingreso. Usa /start para comenzar.")

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

if __name__ == "__main__":
    main()