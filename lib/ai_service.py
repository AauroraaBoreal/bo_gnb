import base64
import json
import requests

def parse_attendance_image(image_bytes: bytes, mime_type: str, employee_names: list, api_key: str) -> dict:
    """
    Sends the handwritten attendance sheet image to the Gemini API (gemini-2.5-flash)
    using HTTP POST requests to perform OCR and structure the results.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    # Base64 encode the image
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    # Construct the system instruction prompt
    prompt = f"""
    Eres un asistente contable experto para la empresa GNB Soluciones Industriales. Tu tarea es extraer la asistencia y las horas de entrada y salida de los trabajadores a partir de una foto de una planilla de asistencia semanal manuscrita en un cuaderno.
    
    El turno laboral estándar de la empresa es de 8:00 AM a 5:00 PM (8 horas de trabajo + 1 hora de almuerzo/refrigerio no pagada, es decir, 9 horas totales transcurridas).
    
    Reglas de negocio para calcular las horas reales trabajadas en el día:
    1. Si el trabajador asistió ("presente"), calcula las horas trabajadas:
       - La hora de inicio efectiva es a partir de las 8:00 AM. Si llega antes (ej. 7:35 AM), se cuenta desde las 8:00 AM (a menos que trabaje sobretiempo, pero por defecto asume inicio a las 8:00 AM). Si llega tarde (ej. 8:15 AM), calcula desde su hora real de entrada.
       - La hora de salida estándar es a las 5:00 PM (17:00). Si sale después (ej. 6:00 PM), esas son horas extras que se suman (ej. salida 6:00 PM = +1 hora extra, total = 9 horas).
       - Resta siempre 1 hora por refrigerio/almuerzo si el rango total transcurrido supera las 5 horas.
       - Ejemplos prácticos:
         * Entrada 7:35 AM, Salida 6:00 PM -> Inicio efectivo: 8:00 AM, Salida: 6:00 PM. Total transcurrido = 10 horas. Menos 1h de refrigerio = 9.0 horas reales de trabajo.
         * Entrada 8:18 AM, Salida 6:00 PM -> Inicio real: 8:18 AM (8.3 horas en decimal), Salida: 6:00 PM (18.0). Total transcurrido = 9.7 horas. Menos 1h de refrigerio = 8.7 horas reales de trabajo.
         * Entrada 8:06 AM, Salida 5:00 PM -> Inicio real: 8:06 AM (8.1 horas en decimal), Salida: 5:00 PM (17.0). Total transcurrido = 8.9 horas. Menos 1h de refrigerio = 7.9 horas reales de trabajo.
         * Entrada 9:02 AM, Salida 6:00 PM -> Inicio real: 9:02 AM (9.0), Salida: 6:00 PM (18.0). Total transcurrido = 9.0 horas. Menos 1h de refrigerio = 8.0 horas reales de trabajo.
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
            "responseMimeType": "application/json"
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    
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
