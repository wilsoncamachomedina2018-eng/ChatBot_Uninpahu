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

    if "EST_CODIGO" not in df.columns:
        raise ValueError("El Excel no contiene la columna EST_CODIGO.")

    if "MAT_NOMBRE" not in df.columns:
        raise ValueError("El Excel no contiene la columna MAT_NOMBRE.")

    if "NT_NUMERICA" not in df.columns:
        raise ValueError("El Excel no contiene la columna NT_NUMERICA.")

    if "DOCENTE" not in df.columns:
        df["DOCENTE"] = ""

    if "EPG_DESCRIPCION" not in df.columns:
        df["EPG_DESCRIPCION"] = ""

    if "PORCEN" not in df.columns:
        df["PORCEN"] = ""

    df["EST_CODIGO"] = df["EST_CODIGO"].astype(str).str.strip()
    df["MAT_NOMBRE_NORM"] = df["MAT_NOMBRE"].apply(normalizar_texto)
    df["DOCENTE_NORM"] = df["DOCENTE"].apply(normalizar_texto)

    df["NT_NUMERICA"] = pd.to_numeric(df["NT_NUMERICA"], errors="coerce")
    df["NOTA_5"] = df["NT_NUMERICA"] / 10.0

    if "CLI_NOMBRES" in df.columns and "CLI_APELLIDOS" in df.columns:
        df["NOMBRE_COMPLETO"] = (df["CLI_NOMBRES"] + " " + df["CLI_APELLIDOS"]).str.strip()
    else:
        df["NOMBRE_COMPLETO"] = ""

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
    return df_notas[df_notas["EST_CODIGO"] == est_codigo]


def buscar_materia_para_codigo(est_codigo, materia):
    registros = buscar_por_codigo(est_codigo)

    if registros.empty:
        return pd.DataFrame()

    return registros[
        registros["MAT_NOMBRE_NORM"].apply(lambda x: contiene_coincidencia(x, materia))
    ]


def respuesta_bienvenida():
    return (
        "Hola, soy el asistente virtual de UNINPAHU.\n\n"
        "Puedo ayudarte con los siguientes temas:\n"
        "1. Materias que estás cursando\n"
        "2. Notas de cada materia\n"
        "3. Profesores de tus asignaturas\n\n"
        "Para entregarte esta información, por favor escribe tu código de estudiante."
    )


def registrar_codigo_si_aplica(mensaje):
    mensaje = mensaje.strip()

    # Limpiar todo lo que no sea número
    mensaje_limpio = re.sub(r"\D", "", mensaje)

    # Validación flexible
    if len(mensaje_limpio) >= 8:
        registros = buscar_por_codigo(mensaje_limpio)

        if not registros.empty:
            session["codigo_estudiante"] = mensaje_limpio
            nombre = registros.iloc[0]["NOMBRE_COMPLETO"]

            if nombre:
                return (
                    f"✅ Código registrado correctamente\n\n"
                    f"Estudiante: {nombre}\n"
                    f"Código: {mensaje_limpio}\n\n"
                    "Ahora puedes preguntarme:\n"
                    "• ¿Qué materias tengo?\n"
                    "• ¿Qué notas tengo?\n"
                    "• Promedio\n"
                    "• ¿Quién dicta una materia?\n"
                    "• Dame la nota de una materia\n"
                    "• Cambiar código"
                )
            else:
                return (
                    f"✅ Código registrado correctamente: {mensaje_limpio}\n\n"
                    "Ahora puedes preguntarme:\n"
                    "• ¿Qué materias tengo?\n"
                    "• ¿Qué notas tengo?\n"
                    "• Promedio\n"
                    "• ¿Quién dicta una materia?\n"
                    "• Dame la nota de una materia\n"
                    "• Cambiar código"
                )

        return "❌ No encontré información para ese código. Verifica e inténtalo nuevamente."

    return None


def responder_con_codigo(codigo, mensaje):
    mensaje_norm = normalizar_texto(mensaje)
    registros = buscar_por_codigo(codigo)

    if registros.empty:
        return "No encontré información para el código registrado. Puedes escribir otro código."

    # Cambiar código
    if "cambiar codigo" in mensaje_norm or "cambiar codigo de estudiante" in mensaje_norm:
        session.pop("codigo_estudiante", None)
        return "He eliminado el código actual. Por favor escribe el nuevo código de estudiante."

    # Materias
    if "que materias tengo" in mensaje_norm or "qué materias tengo" in mensaje_norm or mensaje_norm == "materias" or "ver materias" in mensaje_norm:
        materias = registros["MAT_NOMBRE"].dropna().astype(str).str.strip().unique().tolist()

        if not materias:
            return "No encontré materias registradas para tu código."

        return "Las materias registradas para tu código son: " + ", ".join(materias[:12]) + "."

    # Todas las notas
    if (
        "que notas tengo" in mensaje_norm or
        "qué notas tengo" in mensaje_norm or
        "cuales son mis notas" in mensaje_norm or
        "cuáles son mis notas" in mensaje_norm or
        "ver notas" in mensaje_norm or
        mensaje_norm == "notas"
    ):
        filas = []

        for _, fila in registros.iterrows():
            nota = fila["NOTA_5"]
            nota_txt = "Sin nota" if pd.isna(nota) else f"{nota:.1f}/5.0"
            filas.append(f"{fila['MAT_NOMBRE']}: {nota_txt}")

        if not filas:
            return "No encontré notas registradas para tu código."

        return "Estas son las notas registradas: " + " | ".join(filas[:12]) + "."

    # Promedio
    if "promedio" in mensaje_norm:
        promedio = registros["NOTA_5"].dropna().mean()

        if pd.isna(promedio):
            return "No hay notas disponibles para calcular el promedio."

        return f"El promedio registrado para tu código es {promedio:.2f} / 5.0."

    # Nota de una materia
    patron_nota = r"(nota de|dame la nota de|que nota tengo en|qué nota tengo en)\s+(.+)"
    match_nota = re.search(patron_nota, mensaje_norm)

    if match_nota:
        materia = match_nota.group(2).strip()
        resultado = buscar_materia_para_codigo(codigo, materia)

        if not resultado.empty:
            fila = resultado.iloc[0]
            nota = fila["NOTA_5"]
            tipo_nota = fila["EPG_DESCRIPCION"] if fila["EPG_DESCRIPCION"] else "Sin descripción"
            porcentaje = fila["PORCEN"] if fila["PORCEN"] else "Sin porcentaje"

            if pd.isna(nota):
                return f"Encontré la materia {fila['MAT_NOMBRE']}, pero no tiene una nota registrada."

            return (
                f"En {fila['MAT_NOMBRE']} tienes una nota de {nota:.1f} / 5.0. "
                f"Tipo de reporte: {tipo_nota}. "
                f"Ponderación: {porcentaje}."
            )

        return "No encontré esa materia para tu código de estudiante."

    # Docente de una materia
    patron_docente = r"(quien dicta|quién dicta|quien ensena|quien enseña|docente de|profesor de)\s+(.+)"
    match_docente = re.search(patron_docente, mensaje_norm)

    if match_docente:
        materia = match_docente.group(2).strip()
        resultado = buscar_materia_para_codigo(codigo, materia)

        if not resultado.empty:
            fila = resultado.iloc[0]
            docente = fila["DOCENTE"] if fila["DOCENTE"] else "No registrado"
            return f"La materia {fila['MAT_NOMBRE']} es orientada por {docente}."

        return "No encontré esa materia para tu código de estudiante."

    # Ayuda con código activo
    if "ayuda" in mensaje_norm:
        return (
            f"📌 Código activo: {codigo}\n\n"
            "Con tu código activo puedo ayudarte con:\n"
            "• ¿Qué materias tengo?\n"
            "• ¿Qué notas tengo?\n"
            "• Promedio\n"
            "• ¿Quién dicta Metodología de Software?\n"
            "• Dame la nota de Metodología de Software\n"
            "• Cambiar código"
        )

    return (
        f"📌 Código activo: {codigo}\n\n"
        "No entendí la consulta. Puedes preguntarme por:\n"
        "• materias\n"
        "• notas\n"
        "• promedio\n"
        "• docente de una materia\n"
        "• nota de una materia"
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

    # 1. Primero intentar registrar código SIEMPRE
    respuesta_codigo = registrar_codigo_si_aplica(mensaje)
    if respuesta_codigo:
        return jsonify({"respuesta": respuesta_codigo})

    mensaje_norm = normalizar_texto(mensaje)

    # 2. Saludo inicial
    if mensaje_norm in ["hola", "buenas", "buen dia", "buenos dias", "inicio", "empezar"]:
        return jsonify({"respuesta": respuesta_bienvenida()})

    # 3. Si ya hay código activo en sesión
    codigo_activo = session.get("codigo_estudiante")
    if codigo_activo:
        return jsonify({"respuesta": responder_con_codigo(codigo_activo, mensaje)})

    # 4. Si no hay código todavía
    return jsonify({
        "respuesta": (
            "Para ayudarte con materias, notas y profesores, primero necesito tu código de estudiante. "
            "Por favor escríbelo para continuar."
        )
    })


if __name__ == "__main__":
    app.run(debug=True)