"""Indicadores de la ENDES (INEI) por departamento, leídos del informe oficial.

Uso:
    python .claude/skills/datos-publicos-propuesta/scripts/endes.py --anio 2024

Baja el informe «Indicadores de Resultados de los Programas Presupuestales» de la ENDES,
lee los cuadros por departamento elegidos (CUADROS) y guarda el valor del año de cada
departamento en data/contexto/endes_<anio>.csv, en formato largo.

No se recalcula nada: se copian las cifras oficiales del INEI. La validación revisa que
estén los 25 departamentos más el total, que cada valor caiga dentro de su intervalo de
confianza y que el total nacional coincida con REFERENCIA (cifras de las notas de prensa).
"""
import argparse
import csv
import re
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[4]
URL = "https://proyectos.inei.gob.pe/endes/{anio}/ppr2/indicadores_de_resultados_de_los_programas_presupuestales_endes_{anio}.pdf"
DESPLAZAMIENTO = 2  # página del PDF = página impresa + 2

# cuadro: (página impresa, tema, indicador, unidad)
CUADROS = {
    "01A": (42, "agua y saneamiento", "Hogares con acceso a agua tratada", "%"),
    "02A": (44, "agua y saneamiento", "Hogares con saneamiento básico", "%"),
    "04A": (50, "nutrición e infancia", "Desnutrición crónica en menores de 5 años (patrón OMS)", "%"),
    "06A": (54, "nutrición e infancia", "Anemia en niñas y niños de 6 a 35 meses (RM 363-2022-MINSA)", "%"),
    "17A": (80, "nutrición e infancia", "Menores de 36 meses con controles CRED completos para su edad", "%"),
    "27A": (102, "salud materna", "Parto institucional (último nacimiento, 5 años antes de la encuesta)", "%"),
    "33A": (113, "salud materna", "Gestantes con 6 o más controles prenatales", "%"),
    "37A": (126, "violencia de género", "Mujeres con violencia física y/o sexual del esposo o compañero en los últimos 12 meses", "%"),
}
# Cuadros que no son de un solo año.
NOTAS = {"37A": "promedio 2023-2024"}
# Totales nacionales publicados por el INEI para el año (sirven de control del lector).
REFERENCIA = {"2024": {"04A": 12.1, "06A": 43.7}}

CCDD = {"Amazonas": "01", "Áncash": "02", "Apurímac": "03", "Arequipa": "04", "Ayacucho": "05", "Cajamarca": "06",
        "Prov. Const. del Callao": "07", "Cusco": "08", "Huancavelica": "09", "Huánuco": "10", "Ica": "11",
        "Junín": "12", "La Libertad": "13", "Lambayeque": "14", "Lima Metropolitana": "15", "Loreto": "16",
        "Madre de Dios": "17", "Moquegua": "18", "Pasco": "19", "Piura": "20", "Puno": "21", "San Martín": "22",
        "Tacna": "23", "Tumbes": "24", "Ucayali": "25", "Total": "00"}
NOMBRE_CCDD = {v: k for k, v in CCDD.items()}
NOMBRE_CCDD.update({"00": "Perú (nacional)", "07": "Callao", "15": "Lima"})


def numero(token: str):
    """'12.1' -> (12.1, False); '(6,1)' -> (6.1, True) = estimación referencial (muestra chica)."""
    referencial = token.startswith("(")
    limpio = token.strip("()").replace(",", ".")
    return float(limpio), referencial


def es_casos(token: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}(,\d{3})*", token)) and "." not in token


def leer_cuadro(pagina_texto: str) -> dict:
    """{ccdd: (valor del último año, referencial)} a partir del texto de la página."""
    lineas = [re.sub(r"\s+\d/$", "", l.strip()) for l in pagina_texto.split("\n") if l.strip()]
    filas = {}
    for i, linea in enumerate(lineas):
        nombre = re.sub(r"\s+\d/\s*$", "", linea).strip()
        if nombre.startswith("Total"):
            nombre = "Total"
        if nombre not in CCDD:
            continue
        valores = []
        for token in lineas[i + 1:i + 20]:
            if es_casos(token):
                break
            valores.append(token)
        if len(valores) < 4 or "-" in valores:
            continue
        ultimo, inferior, superior = valores[-4], valores[-3], valores[-2]
        valor, referencial = numero(ultimo)
        lo, _ = numero(inferior)
        hi, _ = numero(superior)
        if not lo - 0.05 <= valor <= hi + 0.05:
            raise ValueError(f"{nombre}: {valor} fuera de su intervalo [{lo}, {hi}]")
        filas[CCDD[nombre]] = (valor, referencial)
    return filas


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--anio", default="2024")
    args.add_argument("--pdf", help="Informe ya descargado (si no, se baja del INEI)")
    args.add_argument("--salida", default=str(RAIZ / "data" / "contexto"))
    a = args.parse_args()

    import fitz  # PyMuPDF

    if a.pdf:
        contenido = Path(a.pdf).read_bytes()
    else:
        url = URL.format(anio=a.anio)
        print(f"Descargando {url}")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=300) as r:
            contenido = r.read()
    doc = fitz.open(stream=contenido, filetype="pdf")

    filas, errores = [], []
    for cuadro, (pagina, tema, indicador, unidad) in CUADROS.items():
        texto = doc[pagina + DESPLAZAMIENTO - 1].get_text()
        try:
            valores = leer_cuadro(texto)
        except ValueError as error:
            errores.append(f"{cuadro}: {error}")
            continue
        faltan = [n for n, c in CCDD.items() if c not in valores and c != "07"]  # Callao suele venir vacío
        if faltan:
            errores.append(f"{cuadro}: faltan {', '.join(faltan)}")
        esperado = REFERENCIA.get(a.anio, {}).get(cuadro)
        if esperado is not None and abs(valores.get("00", (None,))[0] - esperado) > 0.05:
            errores.append(f"{cuadro}: total {valores.get('00')} y el INEI publicó {esperado}")
        print(f"{cuadro}: {len(valores)} filas · Perú {valores.get('00', ('?',))[0]} · {indicador}")
        for ccdd, (valor, referencial) in sorted(valores.items()):
            filas.append({"ccdd": ccdd, "departamento": NOMBRE_CCDD[ccdd], "tema": tema, "indicador": indicador,
                          "valor": valor, "unidad": unidad, "fuente": f"INEI, ENDES {a.anio}", "anio": a.anio,
                          "referencial": int(referencial),
                          "nota": "; ".join(x for x in ("Lima Metropolitana (43 distritos)" if ccdd == "15" else "",
                                                       NOTAS.get(cuadro, "")) if x)})
    if errores:
        sys.exit("VALIDACIÓN FALLIDA, no se guardó la tabla:\n- " + "\n- ".join(errores))
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / f"endes_{a.anio}.csv"
    with destino.open("w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=list(filas[0]))
        escritor.writeheader()
        escritor.writerows(filas)
    print(f"Guardado: {destino} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
