import os
import json
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import google.generativeai as genai
import requests # Para simular la llamada a la herramienta que busca el historial

# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="Servicio de Asistente Gemini",
    description="Recibe una consulta, una imagen opcional y un contexto para responder usando el modelo Gemini."
)

# --- Definición de la "Herramienta": Búsqueda de Historial ---
# Esta función simula una llamada a otra API para obtener datos del estudiante.
# En un caso real, la URL sería un servicio interno tuyo.
def buscar_historial_estudiante(user_id: str) -> dict:
    """
    Herramienta que busca información actualizada de un estudiante por su ID.
    Simula una petición GET a un servicio de usuarios.
    """
    print(f"Ejecutando herramienta: Buscando historial para userId: {user_id}")
    try:
        # Reemplaza esta URL con la URL real de tu servicio de usuarios/estudiantes
        # api_url = f"https://cursofacil.app/desktop_app/agente/resumen_estudiante.php/estudiantes/{user_id}"
        # response = requests.get(api_url)
        # response.raise_for_status() # Lanza un error si la petición falla (ej. 404, 500)
        # return response.json()

        

    except requests.exceptions.RequestException as e:
        print(f"Error al llamar a la API de historial: {e}")
        return {"error": f"No se pudo obtener el historial del usuario {user_id}."}

# --- Endpoint Principal de la API ---
# Este es el punto de entrada que recibirá las solicitudes POST.
@app.post("/generar-respuesta")
async def generar_respuesta(
    # Usamos Form(...) para recibir datos de un formulario (multipart/form-data)
    question_user: str = Form(...),
    gemini_api_key: str = Form(...),
    userId: str = Form(...),
    timestamp: str = Form(...),
    memoria: str = Form(...),  # La memoria (historial de chat) la recibimos como un string JSON
    imagen: UploadFile = File(None) # La imagen es opcional, por eso el "None"
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

    # 3. Preparar el contenido (prompt) para Gemini
    
    # Decodificar la memoria (historial de chat) que viene como string
    try:
        chat_history = json.loads(memoria)
        if not isinstance(chat_history, list):
             chat_history = [] # Si no es una lista, empezamos de cero
    except json.JSONDecodeError:
        chat_history = [] # Si el JSON es inválido, empezamos con un historial vacío

    # Construir el prompt del sistema con los datos de la herramienta
    system_prompt = f"""
    Eres un asistente experto en Excel muy amable.
    Estás ayudando a un estudiante con los siguientes datos actualizados: {json.dumps(historial_actualizado)}.
    Usa esta información para dar una respuesta más personalizada y contextual.
    El historial de la conversación reciente es el siguiente:
    """

    # Preparar el mensaje del usuario (texto e imagen)
    user_prompt_parts = [question_user]
    
    if imagen:
        print(f"Recibida imagen: {imagen.filename}, tipo: {imagen.content_type}")
        # Validar que sea una imagen
        if not imagen.content_type.startswith("image/"):
             raise HTTPException(status_code=400, detail="El archivo adjunto no es una imagen válida.")
        
        # Leer los bytes de la imagen para enviarlos a Gemini
        image_bytes = await imagen.read()
        
        user_prompt_parts.append({
            "mime_type": imagen.content_type,
            "data": image_bytes
        })

    # 4. Enviar la solicitud a Gemini
    try:
        # Seleccionamos un modelo que pueda manejar imágenes (gemini-1.5-flash es ideal)
        model = genai.GenerativeModel(model_name="gemini-1.5-flash")
        
        # Creamos la conversación con el prompt del sistema y el historial
        conversation = model.start_chat(
            history=[
                {"role": "user", "parts": [system_prompt]},
                {"role": "model", "parts": ["¡Entendido! Estoy listo para ayudar con la información proporcionada."]},
                *chat_history # Desempaquetamos el historial de chat aquí
            ]
        )
        
        # Enviamos el nuevo mensaje del usuario
        response = await conversation.send_message_async(user_prompt_parts)
        
        # Formatear la respuesta final
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