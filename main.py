from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

# Token de verificación (debe coincidir con el que pongas en Meta)
VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "alfinfbot-token")


@app.route("/", methods=["GET"])
def verify():
    # Verificación del webhook de Meta
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Error: token inválido", 403


@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Mensaje recibido de Meta:")
    print(json.dumps(data, indent=4, ensure_ascii=False))
    return "EVENT_RECEIVED", 200



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


