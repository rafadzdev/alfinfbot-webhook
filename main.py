from flask import Flask, request, jsonify
import requests, os, json, urllib3, traceback
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
            ok, name, hora = crear_entrada_odoo(numero)
            if ok:
                enviar_mensaje(numero, f"✅ Entrada registrada correctamente:\n\n👤 {name}\n⏰ {hora}")
            else:
                enviar_mensaje(numero, "⚠️ No se encontró un empleado con tu número.")

        elif texto == "salida":
            ok, name, hora = crear_salida_odoo(numero)
            if ok:
                enviar_mensaje(numero, f"📤 Salida registrada correctamente:\n\n👤 {name}\n⏰ {hora}")
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
        traceback.print_exc()

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
        traceback.print_exc()



# =====================
# 🔹 OBTENER ÚLTIMA ASISTENCIA
# =====================
def obtener_ultima_asistencia(employee_id):
    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                int(os.environ["ODOO_USER"]),
                os.environ["ODOO_PASS"],
                "hr.attendance",
                "search_read",
                [[["employee_id", "=", employee_id]]],
                {
                    "fields": ["id", "check_in", "check_out"],
                    "order": "id desc",
                    "limit": 1
                }
            ]
        }
    }

    response = requests.post(url, json=payload, verify=False).json()
    result = response.get("result", [])

    return result[0] if result else None



# =====================
# 🔹 CREAR ENTRADA
# =====================
def crear_entrada_odoo(numero):
    employee_id, employee_name = buscar_empleado_por_numero(numero)
    if not employee_id:
        return False, None, None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ultima = obtener_ultima_asistencia(employee_id)
    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    # Cerrar asistencia anterior si no tiene salida
    if ultima and not ultima.get("check_out"):
        payload_fix = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    os.environ["ODOO_DB"],
                    int(os.environ["ODOO_USER"]),
                    os.environ["ODOO_PASS"],
                    "hr.attendance",
                    "write",
                    [[ultima["id"]], {"check_out": now}]
                ]
            }
        }
        requests.post(url, json=payload_fix, verify=False)

    # Crear nueva entrada
    payload_new = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                int(os.environ["ODOO_USER"]),
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
    requests.post(url, json=payload_new, verify=False)
    return True, employee_name, now



# =====================
# 🔹 CREAR SALIDA
# =====================
def crear_salida_odoo(numero):
    employee_id, employee_name = buscar_empleado_por_numero(numero)
    if not employee_id:
        return False, None, None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ultima = obtener_ultima_asistencia(employee_id)

    if not ultima or ultima.get("check_out"):
        return False, None, None

    url = f"{os.environ['ODOO_URL']}/jsonrpc"
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                int(os.environ["ODOO_USER"]),
                os.environ["ODOO_PASS"],
                "hr.attendance",
                "write",
                [[ultima["id"]], {"check_out": now}]
            ]
        }
    }

    requests.post(url, json=payload, verify=False)
    return True, employee_name, now



# =====================
# 🔹 OBTENER LISTADO DE CONTACTOS
# =====================
def obtener_listado_contactos():
    print("📋 Solicitando listado de empleados...")
    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                int(os.environ["ODOO_USER"]),
                os.environ["ODOO_PASS"],
                "hr.employee",
                "search_read",
                [[]],
                {
                    "fields": ["id", "name", "mobile_phone", "work_email"],
                    "order": "name",
                    "limit": 200
                }
            ]
        }
    }

    try:
        response_raw = requests.post(url, json=payload, verify=False)
        response = response_raw.json()
        employees = response.get("result", [])

        if not employees:
            return "⚠️ No se encontraron empleados."

        texto = "📋 *Listado de empleados:*\n"
        for emp in employees:
            texto += f"\n• {emp['name']} ({emp.get('mobile_phone','Sin teléfono')}) 📧 {emp.get('work_email','-')}"

        return texto[:3900]

    except Exception as e:
        print("⚠️ Error:", e)
        traceback.print_exc()
        return "❌ Error al obtener empleados."



# =====================
# 🔹 BUSCAR EMPLEADO POR TELÉFONO
# =====================
def buscar_empleado_por_numero(numero):
    numero = numero.replace("+", "").replace(" ", "").replace("-", "")
    if numero.startswith("34"):
        numero = numero[2:]

    url = f"{os.environ['ODOO_URL']}/jsonrpc"

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [
                os.environ["ODOO_DB"],
                int(os.environ["ODOO_USER"]),
                os.environ["ODOO_PASS"],
                "hr.employee",
                "search_read",
                [[["mobile_phone", "!=", False]]],
                {
                    "fields": ["id", "name", "mobile_phone"],
                    "limit": 500
                }
            ]
        }
    }

    response_raw = requests.post(url, json=payload, verify=False)
    empleados = response_raw.json().get("result", [])

    for emp in empleados:
        tel = (emp.get("mobile_phone") or "").replace("+", "").replace(" ", "").replace("-", "")
        if tel.startswith("34"):
            tel = tel[2:]

        if tel == numero:
            return emp["id"], emp["name"]

    return None, None



# =====================
# 🔹 MAIN
# =====================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
