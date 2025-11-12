from flask import Flask, request, jsonify
import requests, os, json
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = "alfinfbot-token"

# ====== VERIFICACIÓN WEBHOOK (META) ======
@app.route("/", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Error: token inválido", 403


# ====== PROCESAR MENSAJES ENTRANTES ======
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Mensaje recibido:")
    print(json.dumps(data, indent=4, ensure_ascii=False))

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            mensaje = entry["messages"][0]
            numero = mensaje["from"]
            texto = mensaje["text"]["body"].strip().lower()

            if texto == "entrada":
                crear_entrada_odoo(numero)
                enviar_mensaje(numero, "✅ Entrada registrada correctamente en Odoo.")
            else:
                enviar_mensaje(numero, "No te entendí. Escribe 'entrada' para registrar tu entrada.")
    except Exception as e:
        print("⚠️ Error procesando mensaje:", e)

    return "EVENT_RECEIVED", 200


# ====== FUNCIÓN PARA ENVIAR MENSAJES A WHATSAPP ======
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


# ====== FUNCIÓN PARA CREAR ENTRADA EN ODOO ======
def crear_entrada_odoo(numero):
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
                1,
                os.environ["ODOO_PASS"],
                "hr.attendance",
                "create",
                [{
                    "employee_id": buscar_empleado_por_numero(numero),
                    "check_in": now,
                }]
            ]
        }
    }

    response = requests.post(url, json=payload)
    print("📤 Respuesta de Odoo:", response.text)


# ====== BUSCAR EMPLEADO POR NÚMERO DE TELÉFONO ======
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
                1,
                os.environ["ODOO_PASS"],
                "hr.employee",
                "search",
                [[["work_phone", "=", numero]]]
            ]
        }
    }
    res = requests.post(url, json=payload).json()
    employee_ids = res.get("result", [])
    return employee_ids[0] if employee_ids else False


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
