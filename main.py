# flask server gets message and sends it to telegram bot
from flask import Flask, request, jsonify
from telegramBot import TelegramBot
import threading
import requests

app = Flask(__name__,template_folder='templates')
bot = TelegramBot()  # Make it globally accessible

@app.route('/send_message', methods=['POST'])
async def send_message():
    data = request.json
    if not data or 'message' not in data:
        return jsonify({"error": "Invalid request"}), 400

    message = data['message']
    await bot.broadcast_message(message)
    return jsonify({"status": "Message sent successfully"}), 200

def run_flask():
    app.run(port=5008)


@app.route('/test', methods=['GET'])
def send_test_request():
    # Allow only requests from localhost (127.0.0.1 or ::1 for IPv6)
    if request.remote_addr not in ('127.0.0.1', '::1'):
        return jsonify({"error": "Unauthorized. This endpoint can only be called from localhost."}), 403

    message = request.args.get('message')
    if not message:
        return jsonify({"error": "Missing 'message' parameter"}), 400

    print("Sending test request to Flask server...")
    url = 'http://localhost:5008/send_message'
    payload = {'message': message}

    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Test message sent successfully!")
            return jsonify({"status": "Test message sent successfully"}), 200
        else:
            print(f"Failed to send test message: {response.text}")
            return jsonify({"error": "Failed to send test message"}), 500
    except requests.RequestException as e:
        print(f"Error sending test request: {e}")
        return jsonify({"error": str(e)}), 500


def main():
    # Start the Flask server in a separate thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Run the Telegram bot (blocking)
    bot.run_bot()

if __name__ == '__main__':
    main()
