from flask import Flask, request, jsonify
import requests, os, json
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = "alfinfbot-token"

@app.route("/", methods=["GET"])
def verify():
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
    print("📩 Mensaje recibido:", json.dumps(data, indent=2, ensure_ascii=False))

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            mensaje = entry["messages"][0]
            numero = mensaje["from"]
            texto = mensaje["text"]["body"].strip().lower()

            if texto == "entrada":
                resultado = crear_entrada_odoo(numero)
                if resultado:
                    enviar_mensaje(numero, "✅ Entrada registrada correctamente en Odoo.")
                else:
                    enviar_mensaje(numero, "⚠️ No se encontró tu usuario en Odoo.")
            else:
                enviar_mensaje(numero, "No te entendí. Escribe 'entrada' para registrar tu entrada.")
    except Exception as e:
        print("⚠️ Error procesando mensaje:", e)

    return "EVENT_RECEIVED", 200


def enviar_mensaje(numero, texto):
    url = f"https://graph.facebook.com/v20.0/{os.environ['META_PHONE_ID']}/messages"
    headers = {
        "Authorization": f"Bearer {os.environ['META_TOKEN']}",
        "Content-Type": "application/json"
    }
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "text": {"body": texto}
    }
    requests.post(url, headers=headers, json=data)


def crear_entrada_odoo(numero):
    print(f"🔎 Buscando empleado con número: {numero}")
    employee_id = buscar_empleado_por_numero(numero)
    if not employee_id:
        print("⚠️ Empleado no encontrado en Odoo")
        return False

    url = f"{os.environ['ODOO_URL']}/jsonrpc"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                2,  # ID del usuario administrador (ajústalo si es necesario)
                os.environ["ODOO_PASS"],
                "hr.attendance",
                "create",
                [{
                    "employee_id": employee_id,
                    "check_in": now
                }]
            ]
        }
    }

    response = requests.post(url, json=payload)
    print("📤 Respuesta Odoo:", response.text)
    return True


def buscar_empleado_por_numero(numero):
    url = f"{os.environ['ODOO_URL']}/jsonrpc"
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                2,  # ID de usuario admin
                os.environ["ODOO_PASS"],
                "hr.employee",
                "search",
                [[["mobile_phone", "=", numero]]]
            ]
        }
    }

    response = requests.post(url, json=payload).json()
    result = response.get("result", [])
    return result[0] if result else None


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
