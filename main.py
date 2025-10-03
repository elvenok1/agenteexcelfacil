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

# --- Definición de la "Herramienta": Búsqueda de Historial (CORREGIDO) ---
def buscar_historial_estudiante(user_id: str) -> dict:
    """
    Herramienta que busca información actualizada de un estudiante por su ID y curso.
    """
    print(f"Ejecutando herramienta: Buscando historial para userId: {user_id}")
    
    # URL base de tu herramienta
    api_url_base = "https://cursofacil.app/desktop_app/agente/resumen_estudiante.php"
    
    # Diccionario con los parámetros que se añadirán a la URL
    params = {
        'id': user_id,
        'course_id': 17  # ID del curso es una constante
    }

    try:
        # La librería 'requests' construirá la URL final: ...php?id=...&course_id=...
        response = requests.get(api_url_base, params=params)
        response.raise_for_status() # Lanza un error si la petición falla (ej. 404, 500)
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error al llamar a la API de historial: {e}")
        return {"error": f"No se pudo obtener el historial del usuario {user_id}."}
    except json.JSONDecodeError:
        print(f"La respuesta de la herramienta no es un JSON válido. Respuesta: {response.text}")
        return {"error": "La herramienta de historial devolvió una respuesta inesperada."}


# --- Endpoint Principal de la API ---
@app.post("/generar-respuesta")
async def generar_respuesta(
    # Campos requeridos
    gemini_api_key: str = Form(...),
    userId: str = Form(...),
    # Campos opcionales (se usa `None` como valor por defecto)
    question_user: str = Form(None),
    imagen: UploadFile = File(None),
    # Campos con valores por defecto
    timestamp: str = Form(""),
    memoria: str = Form("[]")
):
    """
    Recibe los datos, procesa la imagen si existe, consulta a Gemini y devuelve una respuesta.
    """
    # 1. Configurar el cliente de Gemini con la API Key del usuario
    try:
        genai.configure(api_key=gemini_api_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API Key de Gemini inválida o mal configurada. Error: {e}")

    # 2. Ejecutar la herramienta para obtener datos adicionales
    historial_actualizado = buscar_historial_estudiante(userId)

    # 3. Preparar el contenido para Gemini
    
    # Decodificar la memoria (historial de chat) de forma segura
    try:
        chat_history = json.loads(memoria)
        if not isinstance(chat_history, list):
             chat_history = []
    except (json.JSONDecodeError, TypeError):
        chat_history = []

    # Construir el prompt del sistema
    system_prompt = f"""
    Eres un asistente experto en Excel muy amable.
    Estás ayudando a un estudiante con los siguientes datos actualizados: {json.dumps(historial_actualizado)}.
    Usa esta información para dar una respuesta más personalizada y contextual.
    """

    # Preparar el mensaje del usuario (texto e imagen) de forma condicional
    user_prompt_parts = []
    if question_user:
        user_prompt_parts.append(question_user)
    
    if imagen and imagen.content_type:
        print(f"Recibida imagen: {imagen.filename}, tipo: {imagen.content_type}")
        if not imagen.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="El archivo adjunto no es una imagen válida.")
        
        image_bytes = await imagen.read()
        user_prompt_parts.append({
            "mime_type": imagen.content_type,
            "data": image_bytes
        })

    # VALIDACIÓN: Asegurarse de que se envió al menos una pregunta o una imagen
    if not user_prompt_parts:
        raise HTTPException(
            status_code=400, 
            detail="Se requiere una pregunta (question_user) o una imagen para procesar."
        )

    # 4. Enviar la solicitud a Gemini
    try:
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        
        conversation = model.start_chat(
            history=[
                {"role": "user", "parts": [system_prompt]},
                {"role": "model", "parts": ["¡Entendido! Estoy listo para ayudar con la información proporcionada."]},
                *chat_history
            ]
        )
        
        response = await conversation.send_message_async(user_prompt_parts)
        
        output = {
            "status": "success",
            "userId": userId,
            "respuesta_gemini": response.text,
            "info_historial_usada": historial_actualizado
        }
        return JSONResponse(content=output)

    except Exception as e:
        print(f"Error al contactar a la API de Gemini: {e}")
        raise HTTPException(status_code=500, detail=f"Error al generar la respuesta de Gemini: {str(e)}")


# --- Endpoint de prueba para verificar que el servidor está funcionando ---
@app.get("/")
def read_root():
    return {"status": "Servicio de Gemini funcionando"}
