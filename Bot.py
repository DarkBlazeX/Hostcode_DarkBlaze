import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient
from flask import Flask, request
import subprocess
import threading

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONGO_URI = os.getenv('MONGODB_URI')
CHANNEL_ID_1 = os.getenv('CHANNEL_ID_1')
CHANNEL_ID_2 = os.getenv('CHANNEL_ID_2')
ADMIN_USER_ID = int(os.getenv('ADMIN_USER_ID'))

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client['telegram_bot']
users_collection = db['users']
bots_collection = db['bots']

# Flask app setup
app = Flask(__name__)

# Telegram bot setup
updater = Updater(TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Define start command handler
def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_id = user.id

    # Check if user is already registered
    if users_collection.find_one({"user_id": user_id}):
        context.bot.send_message(chat_id=user_id, text="Welcome back! Use /menu to access the main menu.")
        return

    keyboard = [
        [InlineKeyboardButton("Join Channel 1", url=f"https://t.me/{CHANNEL_ID_1}"),
         InlineKeyboardButton("Join Channel 2", url=f"https://t.me/{CHANNEL_ID_2}")],
        [InlineKeyboardButton("Check Membership", callback_data='check_membership')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=user_id, text="Please join our 2 channels to use this bot.", reply_markup=reply_markup)

# Define check membership callback
def check_membership(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    # Check if the user is a member of both channels
    chat_member_1 = context.bot.get_chat_member(chat_id=CHANNEL_ID_1, user_id=user_id)
    chat_member_2 = context.bot.get_chat_member(chat_id=CHANNEL_ID_2, user_id=user_id)
    if chat_member_1.status in ['member', 'administrator', 'creator'] and chat_member_2.status in ['member', 'administrator', 'creator']:
        # Register the user
        users_collection.insert_one({"user_id": user_id, "plan": "free", "bot_count": 0})
        context.bot.send_message(chat_id=user_id, text="Thank you for joining the channels! Use /menu to access the main menu.")
    else:
        context.bot.send_message(chat_id=user_id, text="You need to join both channels to use this bot. Please try again after joining.")

# Define menu command handler
def menu(update: Update, context: CallbackContext) -> None:
    keyboard = [
        ["Create New Bot", "My Bot"],
        ["Buy Premium"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    context.bot.send_message(chat_id=update.message.chat_id, text="Main Menu:", reply_markup=reply_markup)

# Define message handler for bot creation
def create_new_bot(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    context.bot.send_message(chat_id=user_id, text="Send me the Python code for the bot you want to create.")
    context.user_data['awaiting_code'] = True

# Define message handler for receiving Python code
def receive_code(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if 'awaiting_code' in context.user_data and context.user_data['awaiting_code']:
        context.user_data['awaiting_code'] = False
        code = update.message.text

        if "```python" in code:
            code = code.replace("```python", "").replace("```", "")
        
        bot_id = bots_collection.insert_one({"user_id": user_id, "code": code, "status": "pending"}).inserted_id
        keyboard = [
            [InlineKeyboardButton("Approve", callback_data=f'approve_{bot_id}'),
             InlineKeyboardButton("Reject", callback_data=f'reject_{bot_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"New bot code received:\n\n{code}\n\nApprove or reject:", reply_markup=reply_markup)
        context.bot.send_message(chat_id=user_id, text="Your bot code has been submitted for approval. Please wait for an admin to review it.")

# Define callback for approve and reject
def approval_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    admin_id = query.from_user.id
    if admin_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=admin_id, text="You are not authorized to perform this action.")
        return

    data = query.data.split('_')
    action = data[0]
    bot_id = data[1]
    bot_data = bots_collection.find_one({"_id": bot_id})

    if action == "approve":
        bot_name = f"bot_{bot_id}.py"
        with open(bot_name, "w") as file:
            file.write(bot_data["code"])
        run_bot(bot_name)
        bots_collection.update_one({"_id": bot_id}, {"$set": {"status": "approved"}})
        context.bot.send_message(chat_id=bot_data["user_id"], text="Your bot code has been approved and is now running!")
    elif action == "reject":
        bots_collection.update_one({"_id": bot_id}, {"$set": {"status": "rejected"}})
        context.bot.send_message(chat_id=bot_data["user_id"], text="Your bot code has been rejected.")

    query.edit_message_text(text=f"Bot code has been {action}d.")

# Define function to run bot
def run_bot(bot_name):
    def target():
        subprocess.run(["python", bot_name])
    threading.Thread(target=target).start()

# Define buy premium command handler
def buy_premium(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data='buy_premium')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.bot.send_message(chat_id=update.message.chat_id, text="Do you really want to buy premium?", reply_markup=reply_markup)

# Define buy premium callback
def premium_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    if query.data == 'buy_premium':
        context.bot.send_message(chat_id=user_id, text="Please contact the bot owner to make the payment and get premium access.")
        context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"User {user_id} wants to buy premium. Please contact them for payment.")

# Define admin panel command handler
def admin_panel(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access the admin panel.")
        return

    keyboard = [
        ["View All Users", "View All Hosted Bots"],
        ["Broadcast to All", "Give Premium"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    context.bot.send_message(chat_id=user_id, text="Admin Panel:", reply_markup=reply_markup)

# Define admin functions
def view_all_users(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    users = users_collection.find()
    user_list = "\n".join([f"User ID: {user['user_id']}, Plan: {user['plan']}" for user in users])
    context.bot.send_message(chat_id=user_id, text=f"All Users:\n{user_list}")

def view_all_hosted_bots(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    bots = bots_collection.find()
    bot_list = "\n".join([f"Bot ID: {bot['_id']}, User ID: {bot['user_id']}, Status: {bot['status']}" for bot in bots])
    context.bot.send_message(chat_id=user_id, text=f"All Hosted Bots:\n{bot_list}")

def broadcast_to_all(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    context.bot.send_message(chat_id=user_id, text="Send me the message you want to broadcast.")
    context.user_data['awaiting_broadcast'] = True

def handle_broadcast_message(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    if 'awaiting_broadcast' in context.user_data and context.user_data['awaiting_broadcast']:
        context.user_data['awaiting_broadcast'] = False
        message = update.message.text

        users = users_collection.find()
        for user in users:
            context.bot.send_message(chat_id=user['user_id'], text=message)
        context.bot.send_message(chat_id=user_id, text="Broadcast message sent to all users.")

def give_premium(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    context.bot.send_message(chat_id=user_id, text="Send me the user ID of the user you want to give premium access to.")
    context.user_data['awaiting_premium'] = True

def handle_premium_user_id(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        context.bot.send_message(chat_id=user_id, text="You are not authorized to access this information.")
        return

    if 'awaiting_premium' in context.user_data and context.user_data['awaiting_premium']:
        context.user_data['awaiting_premium'] = False
        premium_user_id = int(update.message.text)
        users_collection.update_one({"user_id": premium_user_id}, {"$set": {"plan": "premium"}})
        context.bot.send_message(chat_id=premium_user_id, text="Congratulations! You have been given premium access.")
        context.bot.send_message(chat_id=user_id, text="Premium access granted.")

# Register handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("menu", menu))
dispatcher.add_handler(CommandHandler("admin", admin_panel))
dispatcher.add_handler(MessageHandler(Filters.regex("Create New Bot"), create_new_bot))
dispatcher.add_handler(MessageHandler(Filters.regex("My Bot"), lambda update, context: context.bot.send_message(chat_id=update.message.chat_id, text="This feature is under development.")))
dispatcher.add_handler(MessageHandler(Filters.regex("Buy Premium"), buy_premium))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, receive_code))
dispatcher.add_handler(CallbackQueryHandler(approval_callback, pattern="approve_|reject_"))
dispatcher.add_handler(CallbackQueryHandler(check_membership, pattern="check_membership"))
dispatcher.add_handler(CallbackQueryHandler(premium_callback, pattern="buy_premium"))
dispatcher.add_handler(MessageHandler(Filters.regex("View All Users"), view_all_users))
dispatcher.add_handler(MessageHandler(Filters.regex("View All Hosted Bots"), view_all_hosted_bots))
dispatcher.add_handler(MessageHandler(Filters.regex("Broadcast to All"), broadcast_to_all))
dispatcher.add_handler(MessageHandler(Filters.text & Filters.user(user_id=ADMIN_USER_ID), handle_broadcast_message))
dispatcher.add_handler(MessageHandler(Filters.regex("Give Premium"), give_premium))
dispatcher.add_handler(MessageHandler(Filters.text & Filters.user(user_id=ADMIN_USER_ID), handle_premium_user_id))

# Start the bot
updater.start_polling()

# Flask app routes
@app.route('/setwebhook', methods=['GET', 'POST'])
def set_webhook():
    s = updater.bot.setWebhook(f"{request.url_root}{TOKEN}")
    if s:
        return "Webhook setup successful"
    return "Webhook setup failed"

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return 'ok'

if __name__ == '__main__':
    app.run(port=5002, debug=True)
