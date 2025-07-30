import streamlit as st
import io
import json
import requests
from PyPDF2 import PdfReader # Importación de PyPDF2 para leer PDFs
from docx import Document # Importación de python-docx para leer DOCX

# --- Configuración de la página de Streamlit ---
st.set_page_config(layout="wide", page_title="Bot Revisor de Currículum y Pre-Entrevistas")

# --- Funciones de Extracción de Texto ---
def extract_text_from_pdf(uploaded_file):
    """Extrae texto de un archivo PDF."""
    try:
        # Crea un objeto PdfReader a partir del archivo subido
        reader = PdfReader(uploaded_file)
        text = ""
        # Itera sobre cada página para extraer el texto
        for page in reader.pages:
            text += page.extract_text() or "" # Añade el texto de la página, o una cadena vacía si no hay texto
        return text
    except Exception as e:
        # Muestra un mensaje de error si la lectura del PDF falla
        st.error(f"Error al leer el PDF: {e}")
        return None

def extract_text_from_docx(uploaded_file):
    """Extrae texto de un archivo DOCX."""
    try:
        # Crea un objeto Document a partir del archivo subido
        document = Document(uploaded_file)
        text = ""
        # Itera sobre cada párrafo para extraer el texto
        for paragraph in document.paragraphs:
            text += paragraph.text + "\n" # Añade el texto del párrafo seguido de un salto de línea
        return text
    except Exception as e:
        # Muestra un mensaje de error si la lectura del DOCX falla
        st.error(f"Error al leer el DOCX: {e}")
        return None

# --- Función para Llamar a la API de Gemini ---
async def get_gemini_analysis(cv_text, job_description):
    """
    Llama a la API de Gemini para analizar el CV, generar preguntas y dar una puntuación.
    """
    # Define el prompt que se enviará al modelo Gemini.
    # Se le indica al modelo su rol y qué información debe devolver.
    prompt = f"""
    Eres un experto en reclutamiento y análisis de perfiles. Tu tarea es analizar un currículum (CV) y una descripción de puesto, y proporcionar un análisis detallado, sugerir preguntas de entrevista con respuestas óptimas, y dar una puntuación de afinidad.

    **Currículum (CV):**
    {cv_text}

    **Descripción del Puesto (Job Description):**
    {job_description}

    Por favor, proporciona la siguiente información en formato JSON:
    1.  **profile_analysis**: Un análisis conciso del perfil del candidato basado en el CV en relación con el puesto.
    2.  **strengths**: Una lista de las principales fortalezas del candidato para el puesto.
    3.  **weaknesses**: Una lista de las posibles debilidades o áreas de mejora del candidato para el puesto.
    4.  **interview_questions**: Una lista de 3 a 5 objetos, donde cada objeto contiene una `question` (pregunta de entrevista) y una `optimal_answer` (respuesta ideal esperada).
    5.  **affinity_score**: Una puntuación numérica del 1 al 10 que representa la afinidad del candidato con el puesto (1 = muy baja afinidad, 10 = afinidad perfecta).
    6.  **reasoning_score**: Un breve razonamiento para la puntuación de afinidad.

    Asegúrate de que la respuesta sea un JSON válido y siga exactamente el esquema proporcionado.
    """

    # Inicializa el historial del chat con el prompt del usuario
    chat_history = []
    chat_history.append({"role": "user", "parts": [{"text": prompt}]})

    # Define el payload para la solicitud a la API de Gemini, incluyendo el esquema JSON esperado
    payload = {
        "contents": chat_history,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "profile_analysis": {"type": "STRING"},
                    "strengths": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "weaknesses": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "interview_questions": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "question": {"type": "STRING"},
                                "optimal_answer": {"type": "STRING"}
                            }
                        }
                    },
                    "affinity_score": {"type": "INTEGER", "minimum": 1, "maximum": 10},
                    "reasoning_score": {"type": "STRING"}
                },
                "required": ["profile_analysis", "strengths", "weaknesses", "interview_questions", "affinity_score", "reasoning_score"]
            }
        }
    }

    # La clave API se inyecta automáticamente en el entorno de Canvas.
    # No es necesario proporcionarla manualmente aquí.
    api_key = ""
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={api_key}"

    retries = 0
    max_retries = 5
    # Bucle para reintentar la llamada a la API en caso de fallos temporales
    while retries < max_retries:
        try:
            # Realiza la solicitud POST a la API de Gemini
            response = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            response.raise_for_status() # Lanza un error para códigos de estado HTTP erróneos (4xx o 5xx)
            result = response.json() # Parsea la respuesta JSON

            # Verifica si la respuesta contiene los datos esperados del modelo
            if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                json_string = result["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(json_string) # Devuelve el JSON parseado
            else:
                st.error("La API de Gemini no devolvió una respuesta válida o completa.")
                return None
        except requests.exceptions.RequestException as e:
            # Maneja errores de red o de la API con reintentos exponenciales
            st.warning(f"Error de red o API (intento {retries + 1}/{max_retries}): {e}")
            retries += 1
            import asyncio # Importa asyncio solo cuando se necesita para el sleep
            await asyncio.sleep(2 ** retries) # Retraso exponencial antes del siguiente reintento
        except json.JSONDecodeError as e:
            # Maneja errores si la respuesta de Gemini no es un JSON válido
            st.error(f"Error al decodificar la respuesta JSON de Gemini: {e}. Respuesta: {response.text}")
            return None
    # Si se agotan los reintentos, muestra un error
    st.error("Se agotaron los intentos para llamar a la API de Gemini. Por favor, verifica tu conexión o intenta más tarde.")
    return None

# --- Interfaz de Usuario de Streamlit ---
st.title("🤖 Bot Revisor de Currículum y Pre-Entrevistas")
st.markdown("Carga un CV y la descripción del puesto para obtener un análisis detallado, preguntas de entrevista y una puntuación de afinidad.")

# Divide la interfaz en dos columnas para una mejor organización
col1, col2 = st.columns(2)

with col1:
    st.header("1. Cargar Currículum (CV)")
    # Widget para subir archivos, acepta PDF y DOCX
    uploaded_cv = st.file_uploader("Sube el archivo del CV (PDF o DOCX)", type=["pdf", "docx"])

    cv_text = None
    if uploaded_cv is not None:
        # Determina la extensión del archivo para llamar a la función de extracción correcta
        file_extension = uploaded_cv.name.split(".")[-1].lower()
        if file_extension == "pdf":
            cv_text = extract_text_from_pdf(uploaded_cv)
        elif file_extension == "docx":
            # Pasa el objeto uploaded_file directamente a la función
            cv_text = extract_text_from_docx(uploaded_cv) 

        if cv_text:
            st.success("CV cargado y texto extraído correctamente.")
            # Permite al usuario ver el texto extraído
            with st.expander("Ver texto extraído del CV"):
                st.text_area("Texto del CV", cv_text, height=300, disabled=True) # Deshabilitado para edición
        else:
            st.error("No se pudo extraer el texto del CV. Asegúrate de que el archivo no esté corrupto o protegido con contraseña.")

with col2:
    st.header("2. Descripción del Puesto")
    # Área de texto para que el usuario pegue la descripción del puesto
    job_description = st.text_area(
        "Pega aquí la descripción completa del puesto de trabajo o el perfil que buscas:",
        height=300,
        placeholder="Ej: Buscamos un Desarrollador Full-Stack con 5+ años de experiencia en React, Node.js y bases de datos SQL. Capacidad para trabajar en equipo y resolver problemas complejos."
    )

st.markdown("---")

# Botón para iniciar el análisis
if st.button("🚀 Analizar Candidato con IA Gemini", type="primary"):
    # Verifica que tanto el CV como la descripción del puesto estén presentes
    if cv_text and job_description:
        st.info("Analizando el CV con IA Gemini. Esto puede tardar unos segundos...")
        
        # Importar asyncio solo cuando sea necesario, para evitar errores de importación circular
        import asyncio
        
        # Muestra un spinner mientras se realiza el análisis
        with st.spinner("Generando análisis..."):
            analysis_result = asyncio.run(get_gemini_analysis(cv_text, job_description))

        if analysis_result:
            st.success("Análisis completado!")
            st.markdown("---")
            st.header("📊 Informe de Análisis del Candidato")

            # Muestra la puntuación de afinidad y su razonamiento
            affinity_score = analysis_result.get("affinity_score", "N/A")
            reasoning_score = analysis_result.get("reasoning_score", "No disponible.")
            
            st.subheader(f"Puntuación de Afinidad: {affinity_score}/10")
            st.markdown(f"**Razonamiento:** {reasoning_score}")
            st.progress(affinity_score / 10.0) # Barra de progreso para la puntuación

            # Muestra el análisis del perfil
            st.subheader("Análisis del Perfil")
            st.write(analysis_result.get("profile_analysis", "No disponible."))

            # Muestra las fortalezas y debilidades en dos columnas
            st.subheader("Fortalezas y Debilidades")
            col_s, col_w = st.columns(2)
            with col_s:
                st.markdown("#### ✅ Fortalezas")
                for strength in analysis_result.get("strengths", []):
                    st.write(f"- {strength}")
            with col_w:
                st.markdown("#### ⚠️ Debilidades / Áreas de Mejora")
                for weakness in analysis_result.get("weaknesses", []):
                    st.write(f"- {weakness}")

            # Muestra las preguntas de entrevista sugeridas con respuestas óptimas
            st.subheader("Preguntas de Entrevista Sugeridas")
            interview_questions = analysis_result.get("interview_questions", [])
            if interview_questions:
                for i, qa in enumerate(interview_questions):
                    st.markdown(f"**Pregunta {i+1}:** {qa.get('question', 'N/A')}")
                    st.markdown(f"**Respuesta Óptima:** {qa.get('optimal_answer', 'N/A')}")
                    st.markdown("---")
            else:
                st.write("No se pudieron generar preguntas de entrevista.")
        else:
            st.error("No se pudo obtener un análisis de Gemini. Por favor, verifica los datos o intenta de nuevo.")
    else:
        st.warning("Por favor, carga un CV y proporciona la descripción del puesto antes de analizar.")

st.markdown("---")
st.caption("Desarrollado con Streamlit y Google Gemini AI.")

