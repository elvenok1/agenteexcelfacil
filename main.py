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
        print(f"La respuesta de la herramienta no es un JSON válido.")
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
    print(f"[INFO] userId: {userId}")
    print(f"[INFO] question_user: {question_user}")
    print(f"[INFO] imagen: {imagen.filename if imagen else 'No proporcionada'}")
    
    # 1. Configurar cliente de Gemini
    print("[PASO 1] Configurando cliente de Gemini...")
    try:
        genai.configure(api_key=gemini_api_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"API Key de Gemini inválida o mal configurada. Error: {e}")
    print("[PASO 1] Cliente de Gemini configurado correctamente.")

    # 2. Ejecutar la herramienta
    print("[PASO 2] Llamando a la herramienta externa 'buscar_historial_estudiante'...")
    historial_actualizado = buscar_historial_estudiante(userId)
    print(f"[PASO 2] Herramienta externa respondió con {len(str(historial_actualizado))} caracteres")

    # 3. Preparar el contenido
    print("[PASO 3] Preparando contenido para Gemini...")
    try:
        chat_history = json.loads(memoria) if memoria else []
        if not isinstance(chat_history, list): 
            chat_history = []
    except (json.JSONDecodeError, TypeError):
        chat_history = []
    
    # System prompt con información del historial
    system_prompt = f"""Eres un asistente experto en Excel muy amable y profesional. Tu objetivo es ayudar a los usuarios con sus dudas sobre Excel de manera clara y práctica.

Información del estudiante:
{json.dumps(historial_actualizado, indent=2, ensure_ascii=False)}

Instrucciones:
- Responde de manera concisa y útil
- Si el usuario envía una imagen, analízala y proporciona ayuda específica
- Usa la información del historial para personalizar tus respuestas
- Siempre sé amable y educativo
"""

    user_prompt_parts = []

    # Agregar la pregunta si existe
    if question_user and question_user.strip():
        print(f"[PASO 3] Pregunta del usuario: '{question_user[:50]}...'")
        user_prompt_parts.append(question_user.strip())

    # Procesar imagen si existe
    if imagen and imagen.filename:
        print(f"[PASO 3] Procesando imagen: {imagen.filename}")
        print(f"[PASO 3] Content-Type: {imagen.content_type}")
        
        # Validar tipo MIME
        valid_types = ["image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"]
        
        if imagen.content_type not in valid_types:
            print(f"!!! ERROR: Tipo de imagen no válido: {imagen.content_type}")
            raise HTTPException(
                status_code=400,
                detail=f"Tipo de imagen no válido: {imagen.content_type}. Tipos permitidos: {', '.join(valid_types)}"
            )
        
        # Leer bytes de la imagen
        try:
            image_data = await imagen.read()
            print(f"[PASO 3] Imagen leída correctamente: {len(image_data)} bytes")
            
            # Crear parte de imagen limpia sin metadata adicional
            image_part = {
                "mime_type": imagen.content_type,
                "data": image_data
            }
            user_prompt_parts.append(image_part)
            
        except Exception as e:
            print(f"!!! ERROR al leer la imagen: {e}")
            raise HTTPException(status_code=400, detail=f"Error al procesar la imagen: {str(e)}")

    # Validar que al menos haya pregunta o imagen
    if not user_prompt_parts:
        print("!!! ERROR: No se proporcionó ni pregunta ni imagen.")
        raise HTTPException(
            status_code=400,
            detail="Debes proporcionar al menos una pregunta (question_user) o una imagen."
        )

    print(f"[PASO 3] Contenido preparado: {len(user_prompt_parts)} parte(s)")
    
    # 4. Enviar la solicitud a Gemini
    try:
        print("[PASO 4] Inicializando modelo Gemini...")
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2048,
            }
        )
        
        # Crear historial de conversación
        print("[PASO 4] Creando historial de conversación...")
        conversation_history = [
            {"role": "user", "parts": [system_prompt]},
            {"role": "model", "parts": ["¡Entendido! Estoy listo para ayudar con Excel. ¿En qué puedo asistirte?"]}
        ]
        
        # Agregar historial previo si existe
        if chat_history:
            conversation_history.extend(chat_history)
        
        conversation = model.start_chat(history=conversation_history)
        
        print("[PASO 4] Enviando solicitud a la API de Gemini...")
        print(f"[PASO 4] Número de partes en el mensaje: {len(user_prompt_parts)}")
        
        response = conversation.send_message(user_prompt_parts)
        
        print("[PASO 4] Respuesta recibida de la API de Gemini exitosamente.")
        print(f"[PASO 4] Longitud de respuesta: {len(response.text)} caracteres")
        
        output = {
            "status": "success",
            "userId": userId,
            "respuesta_gemini": response.text,
            "info_historial_usada": historial_actualizado,
            "timestamp": timestamp
        }
        
        print("--- [FIN] Solicitud completada con éxito. ---\n")
        return JSONResponse(content=output)
        
    except Exception as e:
        print(f"!!! ERROR FATAL durante la llamada a Gemini: {type(e).__name__}")
        print(f"!!! Detalles del error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error al generar la respuesta de Gemini: {str(e)}"
        )

# --- Endpoint de prueba ---
@app.get("/")
def read_root():
    return {
        "status": "Servicio de Gemini funcionando correctamente",
        "version": "2.0",
        "endpoints": {
            "POST /generar-respuesta": "Endpoint principal para generar respuestas"
        }
    }

# --- Endpoint de salud ---
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Gemini Assistant API"
    }
