from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import unicodedata
import re

app = Flask(__name__)
app.secret_key = "uninpahu_chatbot_2026"

RUTA_EXCEL = "data/notas.xlsx"
HOJA_EXCEL = "Sheet 1"


def normalizar_texto(texto):
    if texto is None:
        return ""
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    texto = re.sub(r"\s+", " ", texto)
    return texto


def contiene_coincidencia(texto_base, texto_busqueda):
    texto_base = normalizar_texto(texto_base)
    texto_busqueda = normalizar_texto(texto_busqueda)

    palabras = [p for p in texto_busqueda.split() if len(p) > 2]

    if not palabras:
        return False

    return all(palabra in texto_base for palabra in palabras)


def cargar_datos():
    df = pd.read_excel(RUTA_EXCEL, sheet_name=HOJA_EXCEL)

    columnas_texto = [
        "MAT_NOMBRE",
        "DOCENTE",
        "EPG_DESCRIPCION",
        "PORCEN",
        "CLI_NOMBRES",
        "CLI_APELLIDOS"
    ]

    for col in columnas_texto:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)

    columnas_obligatorias = [
        "EST_CODIGO",
        "MAT_NOMBRE",
        "NT_NUMERICA",
        "CLI_APELLIDOS",
        "CLI_NOMBRES"
    ]

    for col in columnas_obligatorias:
        if col not in df.columns:
            raise ValueError(f"El Excel no contiene la columna obligatoria: {col}")

    if "DOCENTE" not in df.columns:
        df["DOCENTE"] = ""

    if "EPG_DESCRIPCION" not in df.columns:
        df["EPG_DESCRIPCION"] = ""

    if "PORCEN" not in df.columns:
        df["PORCEN"] = ""

    df["EST_CODIGO"] = df["EST_CODIGO"].astype(str).str.strip()

    df["CLI_APELLIDOS"] = df["CLI_APELLIDOS"].astype(str).str.strip()
    df["CLI_NOMBRES"] = df["CLI_NOMBRES"].astype(str).str.strip()
    df["NOMBRE_COMPLETO"] = (df["CLI_NOMBRES"] + " " + df["CLI_APELLIDOS"]).str.strip()

    df["MAT_NOMBRE"] = df["MAT_NOMBRE"].astype(str).str.strip()
    df["DOCENTE"] = df["DOCENTE"].astype(str).str.strip()
    df["EPG_DESCRIPCION"] = df["EPG_DESCRIPCION"].astype(str).str.strip()
    df["PORCEN"] = df["PORCEN"].astype(str).str.strip()

    df["MAT_NOMBRE_NORM"] = df["MAT_NOMBRE"].apply(normalizar_texto)
    df["DOCENTE_NORM"] = df["DOCENTE"].apply(normalizar_texto)

    df["NT_NUMERICA"] = pd.to_numeric(df["NT_NUMERICA"], errors="coerce")
    df["NOTA_5"] = df["NT_NUMERICA"] / 10.0

    return df


try:
    df_notas = cargar_datos()
except Exception as e:
    print(f"Error cargando el Excel: {e}")
    df_notas = pd.DataFrame()


def buscar_por_codigo(est_codigo):
    if df_notas.empty:
        return pd.DataFrame()

    est_codigo = str(est_codigo).strip()
    return df_notas[df_notas["EST_CODIGO"] == est_codigo].copy()


def buscar_materia_para_codigo(est_codigo, materia):
    registros = buscar_por_codigo(est_codigo)

    if registros.empty:
        return pd.DataFrame()

    materia_norm = normalizar_texto(materia)

    return registros[
        registros["MAT_NOMBRE_NORM"].apply(
            lambda x: contiene_coincidencia(x, materia_norm) or contiene_coincidencia(materia_norm, x)
        )
    ].copy()


def menu_opciones():
    return (
        "📌 Puedo ayudarte con los siguientes temas:\n"
        "1. Qué materias tengo matriculadas\n"
        "2. Qué notas tengo hasta el momento\n"
        "3. Promedio que tienes a hoy\n"
        "4. Quién dicta una materia\n"
        "5. Dame la nota de una materia\n"
        "6. Cambiar código"
    )


def respuesta_bienvenida():
    return (
        "Hola, soy el asistente virtual de UNINPAHU.\n\n"
        "Puedes saludarme o escribir directamente tu código de estudiante para iniciar la consulta."
    )


def es_codigo_valido(mensaje):
    mensaje = str(mensaje).strip()
    return bool(re.fullmatch(r"\d{12}", mensaje))


def registrar_codigo_si_aplica(mensaje):
    mensaje = str(mensaje).strip()

    if not es_codigo_valido(mensaje):
        return None

    registros = buscar_por_codigo(mensaje)

    if registros.empty:
        return "❌ No encontré información para ese código. Verifica e inténtalo nuevamente."

    session["codigo_estudiante"] = mensaje
    session.pop("accion_esperada", None)

    fila = registros.iloc[0]
    nombre = fila["NOMBRE_COMPLETO"]

    return (
        "✅ Código registrado correctamente\n\n"
        f"Estudiante: {nombre}\n"
        f"Código: {mensaje}\n\n"
        f"{menu_opciones()}"
    )


def obtener_materias(registros):
    materias = (
        registros["MAT_NOMBRE"]
        .dropna()
        .astype(str)
        .str.strip()
        .drop_duplicates()
        .tolist()
    )

    if not materias:
        return "No encontré materias matriculadas para tu código."

    respuesta = "Las materias matriculadas para tu código son:\n"
    for i, materia in enumerate(materias, start=1):
        respuesta += f"{i}. {materia}\n"

    return respuesta.strip()


def obtener_notas(registros):
    if registros.empty:
        return "No encontré notas registradas para tu código."

    respuesta = "Estas son las notas registradas hasta el momento:\n"

    for _, fila in registros.iterrows():
        materia = str(fila["MAT_NOMBRE"]).strip()
        descripcion = str(fila["EPG_DESCRIPCION"]).strip() if pd.notna(fila["EPG_DESCRIPCION"]) else ""
        porcentaje = str(fila["PORCEN"]).strip() if pd.notna(fila["PORCEN"]) else ""
        nota = fila["NOTA_5"]

        nota_txt = "Sin nota" if pd.isna(nota) else f"{nota:.1f}/5.0"

        detalle = f"- {materia}: {nota_txt}"
        if descripcion:
            detalle += f" | {descripcion}"
        if porcentaje:
            detalle += f" | {porcentaje}"

        respuesta += detalle + "\n"

    return respuesta.strip()


def obtener_promedio(registros):
    notas = registros["NOTA_5"].dropna()

    if notas.empty:
        return "No hay notas disponibles para calcular el promedio."

    suma = notas.sum()
    promedio = notas.mean()

    return (
        f"La suma acumulada de tus notas es {suma:.2f} y el promedio global a hoy es {promedio:.2f} / 5.0."
    )


def obtener_docente_materia(codigo, materia):
    resultado = buscar_materia_para_codigo(codigo, materia)

    if resultado.empty:
        return f"No encontré la materia '{materia}' para tu código de estudiante."

    fila = resultado.iloc[0]
    docente = str(fila["DOCENTE"]).strip() if pd.notna(fila["DOCENTE"]) else ""

    if not docente:
        docente = "No registrado"

    return f"La materia {fila['MAT_NOMBRE']} es orientada por {docente}."


def obtener_nota_materia(codigo, materia):
    resultado = buscar_materia_para_codigo(codigo, materia)

    if resultado.empty:
        return f"No encontré la materia '{materia}' para tu código de estudiante."

    coincidencias = []
    for _, fila in resultado.iterrows():
        materia_nombre = str(fila["MAT_NOMBRE"]).strip()
        nota = fila["NOTA_5"]
        tipo_nota = str(fila["EPG_DESCRIPCION"]).strip() if pd.notna(fila["EPG_DESCRIPCION"]) else ""
        porcentaje = str(fila["PORCEN"]).strip() if pd.notna(fila["PORCEN"]) else ""

        nota_txt = "Sin nota" if pd.isna(nota) else f"{nota:.1f} / 5.0"

        detalle = f"- {materia_nombre}: {nota_txt}"
        if tipo_nota:
            detalle += f" | {tipo_nota}"
        if porcentaje:
            detalle += f" | Ponderación: {porcentaje}"

        coincidencias.append(detalle)

    if len(coincidencias) == 1:
        return f"Encontré esta nota para la materia consultada:\n{coincidencias[0]}"

    respuesta = "Encontré estos registros para la materia consultada:\n"
    respuesta += "\n".join(coincidencias)
    return respuesta


def responder_con_codigo(codigo, mensaje):
    mensaje_norm = normalizar_texto(mensaje)
    registros = buscar_por_codigo(codigo)

    if registros.empty:
        session.pop("codigo_estudiante", None)
        session.pop("accion_esperada", None)
        return "No encontré información para el código registrado. Por favor ingresa nuevamente tu código."

    accion_esperada = session.get("accion_esperada")

    if mensaje_norm in ["menu", "menú", "ayuda"]:
        session.pop("accion_esperada", None)
        return f"📌 Código activo: {codigo}\n\n{menu_opciones()}"

    if (
        mensaje_norm == "6"
        or "cambiar codigo" in mensaje_norm
        or "cambiar código" in mensaje_norm
        or "cambiar codigo de estudiante" in mensaje_norm
    ):
        session.pop("codigo_estudiante", None)
        session.pop("accion_esperada", None)
        return "He eliminado el código actual. Por favor escribe el nuevo código de estudiante."

    if (
        mensaje_norm == "1"
        or "que materias tengo matriculadas" in mensaje_norm
        or "qué materias tengo matriculadas" in mensaje_norm
        or "que materias tengo" in mensaje_norm
        or "qué materias tengo" in mensaje_norm
        or mensaje_norm == "materias"
        or "ver materias" in mensaje_norm
    ):
        session.pop("accion_esperada", None)
        return obtener_materias(registros)

    if (
        mensaje_norm == "2"
        or "que notas tengo hasta el momento" in mensaje_norm
        or "qué notas tengo hasta el momento" in mensaje_norm
        or "que notas tengo" in mensaje_norm
        or "qué notas tengo" in mensaje_norm
        or "cuales son mis notas" in mensaje_norm
        or "cuáles son mis notas" in mensaje_norm
        or mensaje_norm == "notas"
        or "ver notas" in mensaje_norm
    ):
        session.pop("accion_esperada", None)
        return obtener_notas(registros)

    if (
        mensaje_norm == "3"
        or "promedio" in mensaje_norm
        or "promedio que tienes a hoy" in mensaje_norm
        or "promedio que tengo hoy" in mensaje_norm
    ):
        session.pop("accion_esperada", None)
        return obtener_promedio(registros)

    if mensaje_norm == "4":
        session["accion_esperada"] = "consultar_docente"
        return (
            "Por favor escribe el nombre de la materia.\n\n"
            "Ejemplo:\n"
            "METODOLOGÍA DE SOFTWARE"
        )

    if accion_esperada == "consultar_docente":
        session.pop("accion_esperada", None)
        return obtener_docente_materia(codigo, mensaje)

    patron_docente = r"(quien dicta|quién dicta|quien ensena|quien enseña|docente de|profesor de)\s+(.+)"
    match_docente = re.search(patron_docente, mensaje_norm)

    if match_docente:
        session.pop("accion_esperada", None)
        materia = match_docente.group(2).strip()
        return obtener_docente_materia(codigo, materia)

    if mensaje_norm == "5":
        session["accion_esperada"] = "consultar_nota"
        return (
            "Por favor escribe el nombre de la materia.\n\n"
            "Ejemplo:\n"
            "METODOLOGÍA DE SOFTWARE"
        )

    if accion_esperada == "consultar_nota":
        session.pop("accion_esperada", None)
        return obtener_nota_materia(codigo, mensaje)

    patron_nota = r"(nota de|dame la nota de|que nota tengo en|qué nota tengo en)\s+(.+)"
    match_nota = re.search(patron_nota, mensaje_norm)

    if match_nota:
        session.pop("accion_esperada", None)
        materia = match_nota.group(2).strip()
        return obtener_nota_materia(codigo, materia)

    return (
        f"📌 Código activo: {codigo}\n\n"
        "No entendí la consulta.\n\n"
        f"{menu_opciones()}"
    )


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    mensaje = data.get("mensaje", "").strip()

    if not mensaje:
        return jsonify({"respuesta": "Por favor escribe una consulta."})

    if df_notas.empty:
        return jsonify({
            "respuesta": "No pude cargar el archivo Excel. Verifica la ruta, el nombre del archivo y la hoja."
        })

    respuesta_codigo = registrar_codigo_si_aplica(mensaje)
    if respuesta_codigo:
        return jsonify({"respuesta": respuesta_codigo})

    mensaje_norm = normalizar_texto(mensaje)

    if mensaje_norm in ["hola", "buenas", "buen dia", "buenos dias", "inicio", "empezar", "saludar"]:
        return jsonify({"respuesta": respuesta_bienvenida()})

    codigo_activo = session.get("codigo_estudiante")
    if codigo_activo:
        return jsonify({"respuesta": responder_con_codigo(codigo_activo, mensaje)})

    return jsonify({
        "respuesta": (
            "Para consultar información académica, primero debes escribir tu código de estudiante de 12 dígitos."
        )
    })


if __name__ == "__main__":
    app.run(debug=True)