# excel-bid-extractor

Extracción de cotizaciones desde informes de evaluación económica en Excel cuya estructura cambia en cada archivo.
**Claude identifica las hojas y ubica las celdas; el código copia, corrige y valida cada valor**, con trazabilidad
hasta su celda de origen.

## El problema

Cada informe es un libro de Excel con decenas de hojas (jurídica, técnica, puntajes…). La que importa, la
**revisión aritmética** de las ofertas, cambia de nombre, de posición y de forma en cada libro:

- proveedores en bloques de columnas, una o varias tablas por hoja, encabezados de 2 o 3 filas;
- plantillas vacías con la misma estructura que la hoja real, y hojas ocultas con datos útiles;
- textos con basura (`"\t\nPROVEEDOR SAS"`) y números con ruido de punto flotante (`12608509.200000001`).

Una regla por nombre de hoja o por texto no alcanza. Un modelo de lenguaje sí entiende la estructura, pero no se le
puede confiar la copia de los números.

## El enfoque

1. **Ningún número pasa por la IA.** La IA devuelve roles de hojas y direcciones de celdas; el código lee los valores.
2. **Contratos estrictos.** Las respuestas de la IA usan *structured outputs* con esquemas pydantic y se validan antes
   de usarlas.
3. **El Excel se verifica a sí mismo.** Las fórmulas del evaluador (`ROUND`, `SUM`, `IF(ofertado = corregido)`) dicen
   cómo se corrigió cada valor. El código recalcula esa corrección: si no coincide, el mapa de celdas está mal.
4. **Trazabilidad completa.** Cada valor guarda su hoja y su celda; cada valor calculado guarda además su regla.
5. **Revisión humana explícita.** Lo que no cuadra no se adivina: el documento queda en `HUMAN_REVIEW_REQUIRED` con
   el motivo y las celdas involucradas.

## Estado

| Etapa | Qué hace | Estado |
|---|---|---|
| 1. Identificación de hojas | Claude clasifica cada hoja como `principal`, `apoyo` o `descartada`; se guarda el JSON limpio | ✅ En el pipeline y el CLI |
| 2. Mapa de celdas | Claude ubica tablas, ítems, bloques por proveedor y totales de cada hoja principal | ✅ En el pipeline: verificación aritmética y reintento; se guarda en `cell_maps` |
| 3. Extracción y validación | El código extrae cotizaciones, aplica la regla del evaluador y valida R1–R11 | ✅ En el pipeline: `quotations`, `offer_totals` y reporte final (MongoDB + Excel) |
| 4. Modelo destino | Relación con proveedores, productos y cotizaciones finales | Pendiente |

## Requisitos

- Python 3.13+ y [uv](https://docs.astral.sh/uv/)
- Docker (para MongoDB)
- Un deployment de Claude Sonnet en Microsoft Foundry (solo para `--classifier ai`)

## Puesta en marcha

```powershell
uv sync                     # dependencias
copy .env.example .env      # completar FOUNDRY_RESOURCE y FOUNDRY_API_KEY
docker compose up -d        # MongoDB en localhost:27017
```

El repositorio trae cuatro libros de muestra con datos inventados en `samples/` (ver [Libros de muestra](#libros-de-muestra)).
Tus propios Excel van en `scripts/fixture/`, que está ignorada en git.

## Uso

```powershell
make up       # MongoDB
make demo     # procesa los libros de muestra (samples/)
make run      # procesa los Excel pendientes de INPUT_DIR y deja su reporte en output/confidencial/
make fresh    # borra la base y procesa todo desde cero
make remap    # vuelve a mapear con IA solo las hojas que quedaron en revisión
make requote  # recalcula cotizaciones y reportes con los mapas guardados (sin IA, gratis)
make status   # tabla de resultados (también con solo "make")
```

Con el CLI, para el resto de opciones:

```powershell
uv run python -m app.cli run                          # procesa INPUT_DIR
uv run python -m app.cli run "ruta\al\archivo.xlsx"   # un solo archivo
uv run python -m app.cli run --classifier rules       # sin IA (clasificador por reglas)
uv run python -m app.cli run --force                  # reprocesa lo ya procesado
uv run python -m app.cli run --from map --force       # vuelve a mapear todas las hojas (no solo las pendientes)
uv run python -m app.cli status                       # tabla de resultados
uv run python -m app.cli show "40."                   # reporte de un documento en la consola
uv run python -m app.cli export "40."                 # vuelve a escribir su Excel de reporte
uv run python -m app.cli reset                        # borra la base (pide confirmación; --yes para no pedirla)
uv run pytest                                         # pruebas (no requieren MongoDB ni IA)
uv run python -m scripts.eval_maps --real            # mapeo con IA de muestras y Excel reales (con costo)
```

Un archivo ya procesado no se vuelve a procesar: el `_id` del documento es el sha256 del archivo. Un documento
que quedó a mitad de camino continúa desde donde quedó.

Al terminar cada documento se genera su reporte en `output/confidencial/<nombre del Excel> - reporte.xlsx`
(ignorada en git), con las hojas Resumen, Cotizaciones, Totales, Hallazgos y Revisión. Se sobrescribe al reprocesar.

## Cómo funciona

```
Excel ─► profile ─► classify ─► validate ─► extract ─► map ─► quotes ─► rules
         ficha de    rol de      hojas         JSON      mapa de   cotizaciones  R1–R11
         cada hoja   cada hoja   existen,      limpio    celdas    con su celda
                     (IA|reglas) confianza               (IA)      de origen
```

### 1. Identificación de hojas

El código arma una ficha pequeña de cada hoja (textos de encabezado, celdas numéricas, palabras clave) y Claude
asigna un rol en una sola llamada por libro:

| Rol | Significado |
|---|---|
| `principal` | Revisión aritmética: fuente de las cotizaciones |
| `apoyo` | Precios o ítems que dan contexto (detalle de ítems, tarifas) |
| `descartada` | Todo lo demás, incluidas las plantillas vacías |

Si Foundry no está disponible, el clasificador por reglas devuelve el mismo JSON (`CLASSIFIER=rules`).

### 2. Mapa de celdas

Por cada hoja principal, Claude recibe una cuadrícula compacta (una línea por fila, solo celdas con datos) y
devuelve dónde está cada dato: tablas, filas de ítems, columnas comunes, bloques por proveedor y filas de total.
El mapa se verifica antes de usarlo:

1. **Estructura:** direcciones dentro de la hoja, nombres de proveedor, columnas sin cruces, moneda.
2. **Prueba aritmética:** el mapa se aplica en seco y las reglas de integridad deben cuadrar con las cuentas del
   evaluador. Si una columna está corrida, no cuadran.
3. **Reintento:** si algo falla, Claude recibe el mapa anterior con los problemas exactos. Si tampoco cuadra,
   la hoja pasa a revisión humana.

### 3. Regla de corrección del evaluador

Las celdas corregidas del Excel tienen la regla escrita en su fórmula, y el código la reproduce:

| Paso | Fórmula del evaluador |
|---|---|
| Unitario corregido | `ROUND(unitario ofertado, d)` |
| Total corregido | `ROUND(cantidad × unitario corregido, d)` (con AIU: `+ cantidad × unitario × AIU × IVA`) |
| OK/ERROR | `IF(ofertado = corregido, "OK", "ERROR")` |

Los decimales `d` se leen de cada fórmula `ROUND(…, d)`; sin fórmula, 0 para COP y 2 para otras monedas.

### 4. Validaciones

Hay dos tipos que no significan lo mismo:

- **Hallazgo:** error o particularidad de la oferta. Es lo que la revisión busca; se reporta y no bloquea.
- **Integridad:** la extracción no cuadra con el evaluador. Casi siempre significa que el mapa está mal: bloquea.

| Regla | Tipo | Comprobación |
|---|---|---|
| R1 | Hallazgo | cantidad × unitario ofertado = total ofertado |
| R2 | Integridad | Nuestro recálculo da los valores corregidos del evaluador |
| R3 | Integridad | La suma de los ítems da el subtotal de la tabla |
| R4 | Integridad | subtotal + IVA, AIU, administración y utilidad = total |
| R5 | Integridad | Nuestro OK/ERROR coincide con el del evaluador |
| R6 | Integridad | Campos críticos presentes (proveedor, producto, cantidad, precio, moneda) |
| R7 | Integridad | Sin cotizaciones duplicadas (grupo + proveedor + ítem + producto + unidad con sede) |
| R8 | Hallazgo | Desviación frente al presupuesto |
| R9 | Hallazgo | Ítem cotizado en 0 |
| R10 | Integridad | La suma de las tablas da el total de la oferta |
| R11 | Hallazgo | Un total ofertado difiere del corregido |

## Libros de muestra

`samples/` trae cuatro libros generados por código (`make samples` o `uv run python -m scripts.samples`), con
datos inventados y semilla fija. Cada uno cubre un patrón distinto y trae errores sembrados a propósito:

| Libro | Patrón | Errores sembrados |
|---|---|---|
| `01_suministro_equipos_usd` | Bloques por proveedor en USD, "NO COTIZA", bloque INVITADO, plantilla oculta vacía, hoja de apoyo | Un total mal multiplicado (R1), un precio en 0 (R9), redondeos (R5, R11) |
| `02_servicios_aseo_aiu` | Un grupo por hoja, AIU e IVA por ítem, bloque oculto de un proveedor que no ofertó, totales parciales | Redondeos (R11) |
| `03_consultoria_bloques_desiguales` | Solo un proveedor trae unitario; los demás, solo total | Un IVA con un dígito de menos (R11) |
| `04_licencias_dos_grupos` | Dos tablas en una hoja (una por grupo), dos columnas de cantidad, total de la hoja | — |

Las fórmulas se guardan con su resultado ya calculado (XlsxWriter), como si Excel las hubiera guardado.
`samples/expected/` tiene, por libro, las hojas por rol, el mapa de celdas correcto, el número de cotizaciones
y los hallazgos esperados. `tests/test_samples.py` corre todo el flujo sobre ellos, sin MongoDB ni IA.

## Estructura

Arquitectura en capas: cada carpeta tiene una sola responsabilidad y solo `pipeline/` las combina.

```
app/
├── cli.py              comandos run / status / show / export / reset
├── pipeline/           orquesta las etapas, continúa desde donde quedó cada documento
│   ├── sheets.py         ficha, clasificación, validación y JSON limpio
│   ├── mapping.py        mapa de cada hoja principal (solo las pendientes)
│   ├── quotes.py         cotizaciones y reglas con los mapas aceptados
│   ├── outcome.py        estado final, revisión humana y resumen
│   └── reporting.py      reporte en MongoDB y en Excel
├── config.py           configuración (.env)
├── domain/             contratos pydantic: documento, clasificación, mapa de celdas, cotización, validación
├── excel/              openpyxl: lectura, ficha de cada hoja y JSON limpio
├── classifiers/        clasificación de hojas: ai | rules (misma interfaz) + validación
├── ai/                 cliente de Claude en Foundry + prompts versionados
├── mapping/            mapa de celdas con IA: cuadrícula, estructura, prueba aritmética y reintento
├── quotes/             mapa + JSON limpio → cotizaciones
│   ├── sheet.py          lectura por dirección, cada valor con su celda
│   ├── normalize.py      ROUND de Excel, "no cotiza", llaves de proveedor y producto, unidad
│   ├── item.py           valores de un ítem, si la fila es ítem y su estado (cotizado, en 0, sin oferta)
│   ├── refs.py           identidad de la cotización: proveedor, producto y unidad
│   ├── correction.py     regla del evaluador leída de las fórmulas
│   ├── fact.py, taxes.py precio, total, IVA y AIU para el modelo destino
│   ├── sites.py          sede de cada fila ("PATIO DE 230KV") para la unidad
│   ├── extractor.py      orquesta la extracción de una hoja
│   └── rules/            R1–R11 por ítem, por tabla y por hoja
├── report/             reporte final: armado (builder), Excel y consola
└── storage/            MongoDB: conexión, índices y repositorios
scripts/samples/        generador de los libros de muestra y su resultado esperado
samples/                libros de muestra (.xlsx) y expected/ (resultado esperado en JSON)
tests/                  pruebas unitarias y de punta a punta sobre los libros de muestra
```

## MongoDB

| Colección | Contenido |
|---|---|
| `documents` | Un registro por Excel: estado, ficha de cada hoja, clasificación, etapas y resumen de resultados |
| `source_sheets` | JSON limpio de cada hoja principal o de apoyo, con la dirección de cada celda |
| `ai_runs` | Cada llamada a la IA (clasificación y mapeo): deployment, intento, tokens, duración y respuesta |
| `cell_maps` | El mapa de cada hoja principal: aceptado o en revisión, con los problemas de cada intento |
| `quotations` | Una cotización por proveedor x ítem, con la celda de origen de cada valor y sus validaciones |
| `offer_totals` | Subtotal, IVA, AIU y total de cada proveedor, por tabla y por hoja |
| `reports` | **El reporte final de cada documento**: resumen, ofertas por grupo y proveedor, hallazgos y revisión |

## Configuración (`.env`)

| Variable | Uso |
|---|---|
| `MONGO_URI`, `MONGO_DB` | Conexión a MongoDB |
| `INPUT_DIR` | Carpeta por defecto de los Excel |
| `OUTPUT_DIR` | Carpeta de los reportes en Excel (por defecto `output/confidencial`) |
| `CLASSIFIER` | `ai` o `rules` |
| `FOUNDRY_RESOURCE`, `FOUNDRY_API_KEY` | Recurso de Microsoft Foundry y su clave (nunca va a git) |
| `MODEL_CLASSIFY`, `EFFORT_CLASSIFY` | Deployment de Claude y nivel de esfuerzo |
| `CONFIDENCE_AUTO` | Por debajo de este valor, una hoja principal pasa a revisión humana |
| `PROMPT_VERSION` | Versión del prompt de clasificación (`app/ai/prompts/`) |
| `MODEL_MAP`, `EFFORT_MAP`, `MAX_TOKENS_MAP` | Deployment, esfuerzo y tope de tokens del mapa de celdas |
| `PROMPT_MAP_VERSION`, `MAP_ATTEMPTS` | Prompt del mapa e intentos por hoja (el segundo recibe los problemas del primero) |
| `TOL_FINDING` | Diferencia mínima para reportar un hallazgo (por defecto 0,01) |
| `TOL_INTEGRITY_ABS`, `TOL_INTEGRITY_REL` | Tolerancia frente a los valores del evaluador (por defecto 1 y 0,0001) |

## Stack

Python 3.13 · uv · openpyxl · pydantic v2 · MongoDB 7 · SDK `anthropic` (`AnthropicFoundry`, structured outputs) ·
typer · pytest · ruff · pyrefly · XlsxWriter (libros de muestra)
