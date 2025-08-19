from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/ping')
def ping():
    return "pong"

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.getenv('PORT',5000)))

def keep_alive():
    import threading, os
    def run():
        port = int(os.getenv('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
