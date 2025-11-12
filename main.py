from flask import Flask, request, jsonify
import requests, os, json
from datetime import datetime
import urllib3

# Desactivar advertencias SSL (solo necesario porque el servidor Odoo no tiene cadena SSL completa)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


# ====== ENVIAR MENSAJE A WHATSAPP ======
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


# ====== CREAR ENTRADA EN ODOO ======
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
                2,  # ID del usuario administrador (ajústalo si usas otro usuario)
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

    # 👇 Evita error SSL en Render
    response = requests.post(url, json=payload, verify=False)
    print("📤 Respuesta Odoo:", response.text)
    return True


# ====== BUSCAR EMPLEADO POR NÚMERO DE TELÉFONO ======
def buscar_empleado_por_numero(numero):
    # 🔧 Normalizar número (eliminar espacios, +, etc.)
    numero = numero.replace("+", "").replace(" ", "")
    if numero.startswith("34"):
        numero = numero[2:]

    print(f"🔍 Buscando empleado vinculado al partner con móvil: {numero}")

    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    # Paso 1: buscar partner por campo 'mobile' en res.partner
    payload_partner = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                2,  # ID usuario admin
                os.environ["ODOO_PASS"],
                "res.partner",
                "search",
                [[["mobile", "ilike", numero]]]
            ]
        }
    }
    # 👇 Evita error SSL en Render
    response = requests.post(url, json=payload, verify=False).json()
    result = response.get("result", [])
    return result[0] if result else None


# ====== EJECUCIÓN ======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


