import base64
import json
import requests

def parse_attendance_image(image_bytes: bytes, mime_type: str, employee_names: list, api_key: str) -> dict:
    """
    Sends the handwritten attendance sheet image to the Gemini API (gemini-3.5-flash)
    using HTTP POST requests to perform OCR and structure the results.
    """
    api_key = api_key.strip()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={api_key}"
    
    # Base64 encode the image
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    # Construct the system instruction prompt
    prompt = f"""
    Eres un asistente contable experto para la empresa GNB Soluciones Industriales. Tu tarea es extraer la asistencia y las horas de entrada y salida de los trabajadores a partir de una foto de una planilla de asistencia semanal manuscrita en un cuaderno.
    
    El turno laboral estándar de la empresa es de 8:00 AM a 5:00 PM (8 horas de trabajo + 1 hora de almuerzo/refrigerio no pagada, es decir, 9 horas totales transcurridas).
    
    Reglas de negocio para calcular las horas reales trabajadas en el día:
    1. Si el trabajador asistió ("presente"), calcula las horas trabajadas:
       - Regla de Entrada y Tolerancia:
         * La hora de entrada estándar es a las 8:00 AM.
         * Existe una tolerancia de hasta las 8:15 AM. Si el trabajador llega entre las 8:00 AM y las 8:15 AM (inclusive), se considera como si hubiera ingresado a las 8:00 AM (sin descuento).
         * Si llega después de las 8:15 AM (ejemplo: 8:16 AM en adelante), se le descuenta minuto a minuto desde las 8:00 AM (es decir, la hora de entrada efectiva para el cálculo es su hora real de llegada, por ejemplo, 8:16 AM).
         * Si llega antes de las 8:00 AM (ej. 7:35 AM), se cuenta desde las 8:00 AM (a menos que trabaje sobretiempo, pero por defecto asume inicio a las 8:00 AM).
       - Regla de Jornada Nocturna (Turno de Noche):
         * Si el turno es nocturno (por ejemplo, entrada a las 11:00 PM y salida a las 7:00 AM del día siguiente), esto corresponde a una jornada de noche y equivale a exactamente 8.0 horas trabajadas. Asegúrate de calcularlo como 8.0 horas (no 16.0 ni otros valores erróneos de cálculo de día cruzado).
       - La hora de salida estándar es a las 5:00 PM (17:00). Si sale después (ej. 6:00 PM), esas son horas extras que se suman (ej. salida 6:00 PM = +1 hora extra, total = 9 horas).
       - Resta siempre 1 hora por refrigerio/almuerzo si el rango total transcurrido supera las 5 horas (esta regla NO aplica a la jornada nocturna de 11:00 PM a 7:00 AM, la cual se registra directamente como 8.0 horas netas).
       - Ejemplos prácticos:
         * Entrada 7:35 AM, Salida 6:00 PM -> Como llegó antes de las 8:00 AM, su inicio efectivo es 8:00 AM. Salida: 6:00 PM. Total transcurrido = 10 horas. Menos 1h de refrigerio = 9.0 horas reales de trabajo.
         * Entrada 8:12 AM, Salida 5:00 PM -> Como llegó dentro de la tolerancia (<= 8:15 AM), su inicio efectivo es 8:00 AM. Salida: 5:00 PM. Total transcurrido = 9 horas. Menos 1h de refrigerio = 8.0 horas reales de trabajo.
         * Entrada 8:16 AM, Salida 5:00 PM -> Como llegó después de la tolerancia (> 8:15 AM), su inicio efectivo es 8:16 AM (8.27 horas decimales). Salida: 5:00 PM (17.00). Transcurrido = 8.73 horas. Menos 1h de refrigerio = 7.73 horas reales de trabajo.
         * Entrada 8:30 AM, Salida 5:00 PM -> Como llegó después de la tolerancia (> 8:15 AM), su inicio efectivo es 8:30 AM (8.50 horas decimales). Salida: 5:00 PM (17.00). Transcurrido = 8.50 horas. Menos 1h de refrigerio = 7.50 horas reales de trabajo.
         * Entrada 11:00 PM, Salida 7:00 AM -> Turno de noche. Corresponde a exactamente 8.0 horas reales de trabajo.
    2. Si dice "NO VINO" o similar, el estado es "no_vino" y las horas son 0.0.
    
    Debes mapear los nombres manuscritos en la foto a la siguiente lista oficial de trabajadores registrados en la base de datos (haz un emparejamiento inteligente aproximado/fuzzy matching si el nombre en el papel está abreviado, mal escrito o incompleto):
    {json.dumps(employee_names, ensure_ascii=False)}
    
    Retorna la información en formato JSON puro (sin markdown, sin bloques de código ```json ... ```), que cumpla exactamente con este esquema:
    {{
      "attendance": [
        {{
          "employee_name": "Nombre oficial mapeado de la lista proveída",
          "status": "presente" | "no_vino",
          "entry_time": "Hora de entrada extraída (ej. 7:35 AM)" o null,
          "exit_time": "Hora de salida extraída (ej. 6:00 PM)" o null,
          "calculated_hours": horas_calculadas_en_float
        }}
      ]
    }}
    
    Asegúrate de procesar todos los nombres legibles en la imagen. Si hay un nombre en la imagen que no puedes emparejar con ninguno de la lista oficial, inclúyelo en la lista con el "employee_name" como el nombre original de la foto y añade una nota explicativa o déjalo para que el usuario lo asocie manualmente.
    """
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": image_b64
                        }
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
            "thinkingConfig": {
                "thinkingBudget": 0
            },
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "attendance": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "employee_name": {"type": "STRING"},
                                "status": {"type": "STRING", "enum": ["presente", "no_vino"]},
                                "entry_time": {"type": "STRING"},
                                "exit_time": {"type": "STRING"},
                                "calculated_hours": {"type": "NUMBER"}
                            },
                            "required": ["employee_name", "status", "calculated_hours"]
                        }
                    }
                },
                "required": ["attendance"]
            }
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        if response.status_code == 404:
            try:
                list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                list_resp = requests.get(list_url)
                if list_resp.status_code == 200:
                    models_data = list_resp.json()
                    available_models = [m["name"].split("/")[-1] for m in models_data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
                    raise ValueError(
                        f"Error HTTP 404: El modelo solicitado no se encontró o no está disponible. "
                        f"Los modelos disponibles en tu cuenta para generación de contenido son: {available_models}. "
                        f"Detalle: {response.text}"
                    )
            except ValueError:
                raise
            except Exception:
                pass
        raise ValueError(f"Error HTTP {response.status_code}: {response.text}")
    
    res_json = response.json()
    try:
        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
        # Clean markdown code block wraps if the model returned them despite instructions
        if text_content.startswith("```"):
            lines = text_content.splitlines()
            if lines[0].startswith("```json"):
                text_content = "\n".join(lines[1:-1])
            elif lines[0].startswith("```"):
                text_content = "\n".join(lines[1:-1])
        data = json.loads(text_content)
        return data
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise ValueError(f"Error al decodificar la respuesta de Gemini: {str(e)}. Respuesta cruda: {response.text}")
