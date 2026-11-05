"""Crea una propuesta anterior FICTICIA para probar el modo "Desde mis propuestas anteriores".

Uso: python data/casos/crear_propuesta_previa.py
Todo el contenido es inventado: organización, donante, cifras y resultados.
"""
from pathlib import Path

from docx import Document

SALIDA = Path(__file__).with_name("propuesta_previa_ficticia.docx")

SECCIONES = [
    ("1. Datos de la organización",
     "La Asociación Juventud Emprende Norte (organización ficticia) es una ONG con sede en Chiclayo que desde 2017 "
     "promueve la empleabilidad y el emprendimiento de jóvenes de zonas periurbanas de Lambayeque. Cuenta con un equipo "
     "de 9 personas y una red de 45 voluntarios. Ha ejecutado proyectos con cooperación internacional, gobiernos locales "
     "y empresas privadas, siempre en alianza con organizaciones juveniles de base."),
    ("2. Antecedentes y justificación",
     "Los jóvenes de 18 a 29 años de los distritos periurbanos de Chiclayo enfrentan altos niveles de informalidad laboral. "
     "En nuestro diagnóstico participativo de 2022 (dato ficticio), 2 de cada 3 jóvenes no contaba con formación técnica "
     "certificada y la mayoría de sus emprendimientos no llevaba registros contables. La oferta de los CETPRO públicos es "
     "poco conocida por los jóvenes y no se articula con las necesidades del mercado local."),
    ("3. Estrategia de intervención",
     "La estrategia combina tres líneas probadas por la organización: (a) formación técnica certificada en alianza con "
     "CETPRO públicos, que aportan docentes y certificación, mientras el proyecto cubre materiales y movilidad; "
     "(b) un fondo concursable de capital semilla entregado en bienes, con plan de negocio aprobado por un comité mixto "
     "con participación de jóvenes; y (c) el fortalecimiento de organizaciones juveniles de base mediante una Escuela de "
     "Líderes, para que asuman la incidencia ante la municipalidad y den continuidad a las acciones. "
     "El acompañamiento posterior a la entrega del capital (mentorías mensuales durante 6 meses) es la clave para que "
     "los negocios sobrevivan, lección aprendida de proyectos anteriores."),
    ("4. Enfoques transversales",
     "Enfoque de género: al menos 60% de participantes mujeres, horarios compatibles con tareas de cuidado y un espacio "
     "de cuidado infantil durante los talleres. Enfoque intercultural y de juventudes: los jóvenes participan en el "
     "comité del fondo y en la evaluación de medio término."),
    ("5. Sistema de monitoreo",
     "Línea de base y evaluación final con fichas socioeconómicas, reportes trimestrales, tablero de seguimiento en línea "
     "y visitas de verificación a los negocios. Los indicadores se miden por sexo y edad."),
    ("6. Sostenibilidad",
     "Convenios con dos CETPRO para mantener la oferta formativa, una mesa de juventudes reconocida por ordenanza "
     "municipal y la vinculación de los mejores negocios con cajas municipales para su primer crédito formal."),
]

MATRIZ = [
    ("Propósito", "Jóvenes emprendedores mejoran la sostenibilidad de sus negocios",
     "% de negocios activos a los 12 meses", "35%", "65%", "Fichas de seguimiento"),
    ("Resultado 1", "Jóvenes cuentan con competencias técnicas certificadas",
     "% de jóvenes con certificación de CETPRO que aplica lo aprendido en su negocio", "10%", "70%", "Certificados y visitas"),
    ("Resultado 2", "Negocios juveniles capitalizados y con acompañamiento",
     "% de negocios con capital semilla que lleva registros de ventas", "15%", "75%", "Cuaderno de ventas"),
    ("Resultado 3", "Organizaciones juveniles fortalecidas hacen incidencia",
     "N° de propuestas juveniles incorporadas en el plan municipal", "0 propuestas (2022)", "3 propuestas", "Actas municipales"),
]

PRESUPUESTO = [
    ("R1", "Formación técnica con CETPRO (materiales y movilidad)", "curso", 6, 4500),
    ("R2", "Capital semilla en bienes", "negocio", 50, 2500),
    ("R2", "Mentorías mensuales por 6 meses", "mentoría", 300, 80),
    ("R3", "Escuela de Líderes juveniles", "módulo", 5, 3200),
    ("GEN", "Coordinador(a) del proyecto", "mes", 18, 4200),
    ("GEN", "Línea de base y evaluación final", "estudio", 1, 18000),
]


def main():
    doc = Document()
    doc.add_heading("Propuesta técnica y económica (FICTICIA)", level=0)
    doc.add_paragraph("Proyecto: «Jóvenes Productivos Lambayeque» · Presentado en 2023 a un fondo de cooperación "
                      "(ficticio) · Monto: S/ 480,000 · Duración: 18 meses.")
    for titulo, texto in SECCIONES:
        doc.add_heading(titulo, level=1)
        doc.add_paragraph(texto)

    doc.add_heading("7. Marco lógico", level=1)
    tabla = doc.add_table(rows=1, cols=6)
    tabla.style = "Table Grid"
    for celda, t in zip(tabla.rows[0].cells, ["Nivel", "Objetivo", "Indicador", "Línea de base", "Meta", "Medio"]):
        celda.text = t
    for fila in MATRIZ:
        for celda, t in zip(tabla.add_row().cells, fila):
            celda.text = t

    doc.add_heading("8. Presupuesto (soles)", level=1)
    tabla = doc.add_table(rows=1, cols=6)
    tabla.style = "Table Grid"
    for celda, t in zip(tabla.rows[0].cells, ["Resultado", "Rubro", "Unidad", "Cantidad", "Costo unitario", "Total"]):
        celda.text = t
    for r, rubro, unidad, cant, cu in PRESUPUESTO:
        for celda, t in zip(tabla.add_row().cells, [r, rubro, unidad, str(cant), f"{cu:,}", f"{cant * cu:,}"]):
            celda.text = t
    doc.add_paragraph("Contrapartida: la organización aporta 12% (local, equipos y voluntariado valorizado).")
    doc.save(SALIDA)
    print(f"Creado: {SALIDA}")


if __name__ == "__main__":
    main()
