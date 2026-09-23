import base64
import json
import time
import requests

LAST_WORKING_MODEL = None
LAST_WORKING_MODEL_TIME = 0
MODEL_CACHE_TTL = 600  # 10 minutes in seconds

def get_available_gemini_models(api_key: str) -> list:
    """
    Queries the Gemini API to get all available vision/text generation models for the key.
    Returns a sorted list prioritizing stable flash and pro models.
    """
    default_models = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-2.5-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-pro",
        "gemini-2.5-pro"
    ]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            fetched = []
            for m in data.get("models", []):
                name = m.get("name", "").replace("models/", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods and "gemini" in name.lower() and not any(x in name.lower() for x in ["embedding", "aqa", "imagen", "tts", "bison"]):
                    fetched.append(name)
            
            if fetched:
                # Prioritize flash models first, then pro models
                def sort_priority(n):
                    s = 100
                    if "flash" in n:
                        s -= 50
                    if "2.0" in n:
                        s -= 20
                    elif "2.5" in n:
                        s -= 15
                    elif "1.5" in n:
                        s -= 10
                    if "lite" in n or "8b" in n:
                        s += 5
                    if "exp" in n or "preview" in n:
                        s += 10
                    return s
                
                fetched.sort(key=sort_priority)
                combined = []
                for m in fetched + default_models:
                    if m not in combined:
                        combined.append(m)
                return combined
    except Exception:
        pass
        
    return default_models

def parse_attendance_image(image_bytes: bytes, mime_type: str, employee_names: list, api_key: str) -> dict:
    """
    Sends the handwritten attendance sheet image to the Gemini API
    using HTTP POST requests to perform OCR and structure the results.
    Caches the last working model for 10 minutes to ensure fast execution.
    """
    global LAST_WORKING_MODEL, LAST_WORKING_MODEL_TIME
    
    api_key = api_key.strip()
    
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
    
    now = time.time()
    all_models = get_available_gemini_models(api_key)
    
    # Check if we have a cached working model within the 10-minute (600s) TTL
    if LAST_WORKING_MODEL and (now - LAST_WORKING_MODEL_TIME) < MODEL_CACHE_TTL:
        # Prioritize the cached working model first
        candidate_models = [LAST_WORKING_MODEL] + [m for m in all_models if m != LAST_WORKING_MODEL]
    else:
        # Cache expired or not set, evaluate models starting from primary list
        candidate_models = all_models
        
    headers = {"Content-Type": "application/json"}
    last_error_msg = ""
    
    for model_name in candidate_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        generation_config = {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
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
            "generationConfig": generation_config
        }
        
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=30)
                if response.status_code == 200:
                    res_json = response.json()
                    try:
                        text_content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        if text_content.startswith("```"):
                            lines = text_content.splitlines()
                            if lines[0].startswith("```json"):
                                text_content = "\n".join(lines[1:-1])
                            elif lines[0].startswith("```"):
                                text_content = "\n".join(lines[1:-1])
                        data = json.loads(text_content)
                        
                        # Cache the working model and update timestamp
                        LAST_WORKING_MODEL = model_name
                        LAST_WORKING_MODEL_TIME = time.time()
                        return data
                    except (KeyError, IndexError, json.JSONDecodeError) as e:
                        raise ValueError(f"Error al decodificar la respuesta de Gemini ({model_name}): {str(e)}. Respuesta cruda: {response.text}")
                
                if response.status_code in (503, 429):
                    last_error_msg = f"HTTP {response.status_code} ({model_name}): {response.text}"
                    if attempt < max_retries:
                        time.sleep(1)
                        continue
                    else:
                        break
                
                if response.status_code == 404:
                    last_error_msg = f"HTTP 404 ({model_name}): Modelo no disponible."
                    break
                    
                last_error_msg = f"Error HTTP {response.status_code} ({model_name}): {response.text}"
                break
                
            except requests.exceptions.RequestException as req_err:
                last_error_msg = f"Error de red ({model_name}): {str(req_err)}"
                if attempt < max_retries:
                    time.sleep(1)
                    continue
                break
                
    raise ValueError(f"Servicio de IA temporalmente saturado en Google. Último detalle: {last_error_msg}")


