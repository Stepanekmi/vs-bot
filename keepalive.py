import os
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.get("/")
def root():
    return "OK"

@app.get("/ping")
def ping():
    return "pong"

def keepalive():
    """Na Renderu otevře HTTP port, aby služba nepadala na port scan."""
    port = int(os.environ.get("PORT", "10000"))
    Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=port, debug=False, use_reloader=False
        ),
        daemon=True,
    ).start()
