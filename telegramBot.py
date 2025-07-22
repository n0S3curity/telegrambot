import json
import os
import requests
import asyncio  # Needed for potential delays in broadcasting
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters


class TelegramBot:
    def __init__(self, config_path='config.json'):
        self.config = {}
        self._load_config(config_path)

        self.bot_token = self.config.get("Telegram", {}).get("bot_token")
        self.allowed_user_ids = [int(uid) for uid in self.config.get("Telegram", {}).get("allowed_user_ids", [])]
        # self.notification_group_id is not strictly needed for this logic,
        # but you can keep it if you have a separate use case for a single group.
        self.notification_group_id = self.config.get("Telegram", {}).get("notification_group_id", None)

    def _load_config(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        try:
            with open(path, 'r') as file:
                self.config = json.load(file)
        except json.JSONDecodeError as e:
            raise ValueError(f"Error decoding config file: {e}")
        except KeyError as e:
            raise KeyError(f"Error loading config file: Missing key {e}")

    # --- Low-level function to send to a single chat ID (used for individual replies) ---
    def _send_api_message_to_chat(self, chat_id, text, parse_mode=None):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2"  # Default parse mode
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            # print(f"Message sent to chat_id {chat_id}: {text[:50]}...") # Log success (optional)
        except requests.RequestException as e:
            print(f"Error sending message to chat_id {chat_id}: {e}")
            return False
        return True

    # --- Function to broadcast to all allowed users (used for general notifications) ---
    async def broadcast_message(self, message_text, parse_mode=None):
        if not self.allowed_user_ids:
            print("No allowed user IDs configured for broadcast.")
            return

        print(f"Broadcasting message to {len(self.allowed_user_ids)} authorized users.")
        for user_id in self.allowed_user_ids:
            success = self._send_api_message_to_chat(user_id, message_text, parse_mode)
            if not success:
                print(f"Failed to send broadcast message to user ID: {user_id}")
            await asyncio.sleep(0.05)  # Small delay to avoid Telegram rate limits

    # --- Access control helper ---
    def _is_authorized(self, user_id):
        return user_id in self.allowed_user_ids

    # --- Unauthorized message sender (sends individually to the unauthorized user) ---
    async def _send_unauthorized_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🚫 You are not authorized to use this bot. Please contact the administrator."
        )

    # --- Command: /start (Individual Reply) ---
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_first_name = update.effective_user.first_name

        print(f"Received /start from User: {user_first_name}, ID: {user_id}")

        if not self._is_authorized(user_id):
            await self._send_unauthorized_message(update, context)
            return

        # This is a direct reply to the user, so it sends individually
        message = f"👋 Hello {user_first_name}! Your User ID is `{user_id}`. Welcome to the bot!"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode="Markdown")

    # --- Command: /Irrigation_status (Individual Reply, as requested by user's choice) ---
    async def get_Irrigation_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await self._send_unauthorized_message(update, context)
            return

        irrigation_status = {}
        # send get status request to the irrigation system API
        try:
            response = requests.get("http://192.168.3.23:5000/api/status")  # Replace with actual API URL
            response.raise_for_status()
            irrigation_status = response.json()  # Assuming the API returns JSON data
        except Exception as e:
            print(f"Error fetching irrigation status: {e}")
            irrigation_status = {"error": "Failed to fetch irrigation status."}
        
        json_string = {}
        for sensor in irrigation_status:
            print(f"Sensor: {sensor}")
            moisture_value = irrigation_status.get(sensor, {}).get('moisture', 0)
            sensor_data ={}
            sensor_data['moisture'] = moisture_value
            sensor_data['moisture_percentage'] = f"{int((moisture_value / 1024) * 100)}%"
            sensor_data['status'] = "wet" if moisture_value < 400 else "dry"
            json_string[sensor] = sensor_data # Convert to percentage
            
        message_text = f"Irrigation Status \n```json\n{json_string}\n```"

        # --- IMPORTANT CHANGE: Sends only to the user who requested it ---
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, parse_mode="MarkdownV2")
        # No confirmation needed, as it's a direct reply.

    # --- Handler for free text (Individual Reply) ---
    async def handle_free_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await self._send_unauthorized_message(update, context)
            return

        user_message = update.message.text
        user_first_name = update.effective_user.first_name
        print(f"Authorized user '{user_first_name}' (ID: {user_id}) sent free text: {user_message}")

        # These are individual replies to the sender
        if "hello" in user_message.lower():
            await update.message.reply_text(f"Hello there, {user_first_name}!")
        elif "status" in user_message.lower():
            await update.message.reply_text("Fetching latest status...")
            # If a free text "status" should also trigger a *broadcast* status,
            # you would add: await self.broadcast_message("Free text trigger: Checking irrigation status...")
            # For now, it's just a conversational reply, then the individual status.
            await self.get_Irrigation_status(update, context)  # This will send status individually
        else:
            await update.message.reply_text(
                "I'm not sure how to respond to that. Try a command like /Irrigation_status or /start.")

    # --- Optional: A command to manually trigger a general broadcast (FOR ALL USERS) ---
    async def send_general_alert_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await self._send_unauthorized_message(update, context)
            return

        # Example general alert message that goes to ALL authorized users
        alert_message = "🔔 **System Maintenance Notice:** We'll be updating services tonight. Expect brief downtime."
        await self.broadcast_message(alert_message, parse_mode="Markdown")
        await update.message.reply_text("General alert broadcasted to all authorized users.")

    # --- Optional: A command to broadcast the *current irrigation status* to all users ---
    async def broadcast_irrigation_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await self._send_unauthorized_message(update, context)
            return

        irrigation_status = {
            "status": "Active",
            "last_run": "2023-10-01 12:00:00",
            "next_run": "2023-10-01 18:00:00"
        }
        json_string = json.dumps(irrigation_status, indent=4)
        message_text = f"📢 **Current Irrigation Status (Broadcast):**\n```json\n{json_string}\n```"

        await self.broadcast_message(message_text, parse_mode="MarkdownV2")
        await update.message.reply_text("Irrigation status broadcasted to all authorized users.")

    def run_bot(self):
        app = ApplicationBuilder().token(self.bot_token).build()

        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("Irrigation_status", self.get_Irrigation_status))  # Now sends individually
        app.add_handler(CommandHandler("send_general_alert", self.send_general_alert_command))  # Broadcast to all
        app.add_handler(CommandHandler("broadcast_irrigation_status",
                                       self.broadcast_irrigation_status_command))  # Broadcast specific status

        # Ensure the free text handler is last or filtered carefully
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_free_text))

        print("✅ Telegram bot is running... Press Ctrl+C to stop.")
        app.run_polling()


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run_bot()