from flask import Flask, request, jsonify
import requests, os, json, urllib3
from datetime import datetime

# Desactivar advertencias SSL (si el servidor Odoo no tiene cadena completa)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

VERIFY_TOKEN = "alfinfbot-token"


# =====================
# 🔹 VERIFICACIÓN WEBHOOK
# =====================
@app.route("/", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    else:
        return "Error: token inválido", 403


# =====================
# 🔹 RECEPCIÓN DE MENSAJES
# =====================
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📩 Mensaje recibido:", json.dumps(data, indent=2, ensure_ascii=False))

    try:
        entry = data["entry"][0]["changes"][0]["value"]

        # Solo procesar mensajes reales, ignorar estados
        if "messages" not in entry:
            print("ℹ️ Evento sin mensajes (solo estados). Ignorado.")
            return "EVENT_RECEIVED", 200

        mensaje = entry["messages"][0]
        numero = mensaje.get("from")
        texto = mensaje.get("text", {}).get("body", "")

        if not texto:
            print("⚠️ Mensaje sin texto. Ignorado.")
            return "EVENT_RECEIVED", 200

        texto = texto.strip().lower()
        print(f"💬 Mensaje de {numero}: {texto}")

        # ==========================
        # 🔹 COMANDOS WHATSAPP
        # ==========================
        if texto == "listado":
            listado = obtener_listado_contactos()
            enviar_mensaje(numero, listado)

        elif texto == "entrada":
            ok = crear_entrada_odoo(numero)
            if ok:
                enviar_mensaje(numero, "✅ Entrada registrada correctamente.")
            else:
                enviar_mensaje(numero, "⚠️ No se encontró un empleado con tu número.")

        elif texto == "salida":
            ok = crear_salida_odoo(numero)
            if ok:
                enviar_mensaje(numero, "📤 Salida registrada correctamente.")
            else:
                enviar_mensaje(numero, "⚠️ No se encontró un empleado con tu número.")

        else:
            enviar_mensaje(
                numero,
                "No te entendí. Escribe:\n\n"
                "• *listado* → Ver contactos\n"
                "• *entrada* → Registrar entrada\n"
                "• *salida* → Registrar salida"
            )

    except Exception as e:
        print("⚠️ Error procesando mensaje:", e)

    return "EVENT_RECEIVED", 200




# =====================
# 🔹 ENVÍO DE MENSAJES A WHATSAPP
# =====================
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
    try:
        response = requests.post(url, headers=headers, json=data)
        print("📤 Respuesta Meta:", response.text)
    except Exception as e:
        print("⚠️ Error enviando mensaje:", e)


# =====================
# 🔹 CREAR ENTRADA EN ODOO
# =====================
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
                os.environ["ODOO_USER"],
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

    response = requests.post(url, json=payload, verify=False)
    print("📤 Respuesta Odoo:", response.text)
    return True



def crear_salida_odoo(numero):
    print(f"🔎 Buscando empleado para salida: {numero}")
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
                os.environ["ODOO_USER"],
                os.environ["ODOO_PASS"],
                "hr.attendance",
                "create",
                [{
                    "employee_id": employee_id,
                    "check_out": now
                }]
            ]
        }
    }

    response = requests.post(url, json=payload, verify=False)
    print("📤 Respuesta Odoo:", response.text)
    return True

# =====================
# 🔹 OBTENER CONTACTOS DE ODOO
# =====================
def obtener_listado_contactos():
    print("📋 Solicitando listado de contactos en res.partner...")

    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "model": "res.partner",
            "method": "search_read",
            "args": [],
            "kwargs": {
                "domain": [],
                "fields": ["id", "name", "phone", "mobile", "email"],
                "order": "id"
            }
        }
    }

    try:
        response_raw = requests.post(url, json=payload, verify=False)
        print("📥 Respuesta RAW Odoo:", response_raw.text)

        response = response_raw.json()
        partners = response.get("result", [])

        if not partners:
            return "⚠️ No se encontraron contactos en Odoo."

        texto = "📋 *Listado de contactos:*\n"
        for p in partners:
            nombre = p.get("name", "Sin nombre")
            phone = p.get("phone") or p.get("mobile") or "Sin teléfono"
            email = p.get("email") or "-"
            texto += f"\n• {nombre} ({phone}) 📧 {email}"

        return texto[:3900]

    except Exception as e:
        print("⚠️ Error obteniendo listado:", e)
        return "❌ Error al obtener el listado desde Odoo."



# =====================
# 🔹 BUSCAR EMPLEADO POR TELÉFONO
# =====================
def buscar_empleado_por_numero(numero):
    numero = numero.replace("+", "").replace(" ", "")
    if numero.startswith("34"):
        numero = numero[2:]

    print(f"🔍 Buscando empleado vinculado al partner con teléfono o móvil: {numero}")

    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    # Buscar en res.partner
    payload_partner = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                os.environ["ODOO_USER"],
                os.environ["ODOO_PASS"],
                "res.partner",
                "search",
                [[
                    "|",
                    ["phone", "ilike", numero],
                    ["mobile", "ilike", numero]
                ]]
            ]
        }
    }

    response_partner = requests.post(url, json=payload_partner, verify=False).json()
    partners = response_partner.get("result", [])

    if not partners:
        print("⚠️ No se encontró ningún contacto con ese número en res.partner")
        return None

    partner_id = partners[0]
    print(f"✅ Contacto encontrado en res.partner ID={partner_id}")

    # Buscar el empleado vinculado
    payload_employee = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                os.environ["ODOO_USER"],
                os.environ["ODOO_PASS"],
                "hr.employee",
                "search",
                [[["address_home_id", "=", partner_id]]]
            ]
        }
    }

    response_employee = requests.post(url, json=payload_employee, verify=False).json()
    employees = response_employee.get("result", [])

    if not employees:
        print("⚠️ No se encontró empleado vinculado a ese partner")
        return None

    print(f"✅ Empleado encontrado ID={employees[0]}")
    return employees[0]


# =====================
# 🔹 MAIN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))




