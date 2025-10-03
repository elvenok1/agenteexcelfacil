import os
import json
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import google.generativeai as genai
import requests

# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="Servicio de Asistente Gemini",
    description="Recibe una consulta, una imagen opcional y un contexto para responder usando el modelo Gemini."
)

# --- Definición de la "Herramienta": Búsqueda de Historial (CON TIMEOUT) ---
def buscar_historial_estudiante(user_id: str) -> dict:
    """
    Herramienta que busca información actualizada de un estudiante por su ID y curso.
    """
    print(f"Ejecutando herramienta: Buscando historial para userId: {user_id}")
    api_url_base = "https://cursofacil.app/desktop_app/agente/resumen_estudiante.php"
    params = {'id': user_id, 'course_id': 17}

    try:
        # AÑADIMOS UN TIMEOUT DE 15 SEGUNDOS. SI TARDA MÁS, FALLARÁ.
        response = requests.get(api_url_base, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        print("!!! ERROR: La llamada a la API de historial ha tardado demasiado (timeout).")
        return {"error": "El servicio de historial de usuario no respondió a tiempo."}
    except requests.exceptions.RequestException as e:
        print(f"Error al llamar a la API de historial: {e}")
        return {"error": f"No se pudo obtener el historial del usuario {user_id}."}
    except json.JSONDecodeError:
        print(f"La respuesta de la herramienta no es un JSON válido. Respuesta: {response.text}")
        return {"error": "La herramienta de historial devolvió una respuesta inesperada."}

# --- Endpoint Principal de la API (CON LOGS DE DEPURACIÓN) ---
@app.post("/generar-respuesta")
async def generar_respuesta(
    gemini_api_key: str = Form(...),
    userId: str = Form(...),
    question_user: str = Form(None),
    imagen: UploadFile = File(None),
    timestamp: str = Form(""),
    memoria: str = Form("[]")
):
    print("\n--- [INICIO] Nueva solicitud recibida ---")
    
    # 1. Configurar cliente de Gemini
    print("[PASO 1] Configurando cliente de Gemini...")
    try:
        genai.configure(api_key=gemini_api_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API Key de Gemini inválida o mal configurada. Error: {e}")
    print("[PASO 1] Cliente de Gemini configurado.")

    # 2. Ejecutar la herramienta
    print("[PASO 2] Llamando a la herramienta externa 'buscar_historial_estudiante'...")
    historial_actualizado = buscar_historial_estudiante(userId)
    print(f"[PASO 2] Herramienta externa respondió: {historial_actualizado}")

    # 3. Preparar el contenido
    print("[PASO 3] Preparando contenido para Gemini...")
    try:
        chat_history = json.loads(memoria) if memoria else []
        if not isinstance(chat_history, list): chat_history = []
    except (json.JSONDecodeError, TypeError):
        chat_history = []
    
    system_prompt = f"Eres un asistente experto en Excel muy amable..." # (Acortado por brevedad)
    user_prompt_parts = []
    if question_user: user_prompt_parts.append(question_user)
    if imagen and imagen.content_type:
        if not imagen.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="El archivo adjunto no es una imagen válida.")
        image_bytes = await imagen.read()
        user_prompt_parts.append({"mime_type": imagen.content_type, "data": image_bytes})

    if not user_prompt_parts:
        print("!!! ERROR: No se proporcionó ni pregunta ni imagen. Abortando.")
        raise HTTPException(status_code=400, detail="Se requiere una pregunta (question_user) o una imagen para procesar.")
    print("[PASO 3] Contenido preparado.")
    
    # 4. Enviar la solicitud a Gemini
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        conversation = model.start_chat(history=[{"role": "user", "parts": [system_prompt]}, {"role": "model", "parts": ["¡Entendido!"]}, *chat_history])
        
        print("[PASO 4] Enviando solicitud a la API de Gemini...")
        response = await conversation.send_message_async(user_prompt_parts)
        print("[PASO 4] Respuesta recibida de la API de Gemini.")
        
        output = {"status": "success", "userId": userId, "respuesta_gemini": response.text, "info_historial_usada": historial_actualizado}
        print("--- [FIN] Solicitud completada con éxito. ---")
        return JSONResponse(content=output)
    except Exception as e:
        print(f"!!! ERROR FATAL durante la llamada a Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Error al generar la respuesta de Gemini: {str(e)}")

# --- Endpoint de prueba ---
@app.get("/")
def read_root():
    return {"status": "Servicio de Gemini funcionando"}
