# ObraPasaLista — puerto a Node.js / Express

Puerto completo de **ObraPasaLista v1.2** (originalmente Python/Flask +
`render_template_string` monolítico en un único `app.py` de ~3300 líneas) a
**Node.js + Express + EJS + better-sqlite3**, organizado en módulos en lugar
de un único fichero.

El esquema de base de datos es **idéntico** al de la versión Python: si ya
tienes una `app.db` de la app original, puedes copiarla tal cual a
`data/app.db` y funcionará sin migración de datos.

## Requisitos

- Node.js ≥ 18

## Instalación y arranque

```bash
npm install
npm start          # equivalente a `flask run`, escucha en http://127.0.0.1:5000
```

En el primer arranque, si `data/app.db` no existe, se crea automáticamente
con el esquema completo y los rangos por defecto (equivalente a que Flask
llamara a `_init_if_needed()` en el primer request).

Si vienes de una instalación v1.0/v1.1 y quieres aplicar las migraciones
explícitamente (opcional; también se aplican solas al arrancar):

```bash
npm run init-db       # equivalente a: flask --app app init-db  (instalación limpia)
npm run upgrade-db    # equivalente a: flask --app app upgrade-db (migra v1.0/v1.1 -> v1.2)
```

## Variables de entorno

Las mismas que la versión Python:

| Variable | Por defecto | Uso |
|---|---|---|
| `OBRAPL_MODE` | `prod` | `test` usa `data/app_test.db` en lugar de `data/app.db` |
| `OBRAPL_DOCS_DIR` | `docs/` | Carpeta donde se guardan los archivos de documentación de obra |
| `SECRET_KEY` | aleatoria | Clave de sesión Express (equivalente a `app.secret_key`) |
| `PORT` | `5000` | Puerto HTTP |

## Estructura del proyecto

```
src/
  app.js                  Punto de entrada: Express, sesión, montaje de rutas
  cli.js                  Comandos init-db / upgrade-db
  config.js                Rutas y variables de entorno
  db.js                    Esquema SQL completo + migraciones v1.1 y v1.2
  utils.js                 secure_filename() y utilidades varias
  services/                Lógica de negocio pura (sin Express), por módulo:
    fechas.js                normalización de fechas, HH:MM, slug
    horas.js                 límite h/día, mes cerrado, rango activo
    logs.js                  auditoría (log_auditoria)
    negocio.js                subcontratas, cálculo de mensual, metas de horas,
                              informe de costes, estado de obra
    docs.js                   carpetas/archivado de documentación por partida
  middleware/
    flash.js                 mensajes flash basados en sesión (equiv. a Flask flash())
    render.js                render en dos pasos (vista -> layout), equiv. a
                              {% extends %} / {% block %} de Jinja2
  routes/                   Un fichero por área, todas montadas en app.js:
    index, empresas, subcontratas, rangos, personas, obras,
    documentacion (+documentacionArchivo), diario, mensual,
    backup, config, informes, faq
  views/                    Plantillas EJS (una carpeta por módulo)
    layout.ejs                cabecera/nav/pie común (antes _BASE_HTML)

public/vendor/              Bootstrap y Bootstrap Icons vendorizados (offline)
data/                       app.db (o app_test.db) + backups/
docs/                       Documentación de obra subida desde la app
```

Esta separación es exactamente la reorganización que proponía la hoja de
ruta original (Fase 2: separar en blueprints, mover el HTML a plantillas de
verdad) — aquí ya está aplicada de fábrica.

## Verificación de correctitud

Este puerto se ha revisado a fondo comparando cada ruta, cada consulta SQL y
cada función de negocio contra el `app.py` original, línea a línea. Además:

- El **esquema SQL completo** y las **migraciones v1.1/v1.2** se compararon
  programáticamente contra el original: son idénticas, sin ninguna diferencia.
- Se probó contra la **base de datos real de producción** que venía en el
  proyecto original (con empresas, personas, partes diarios y meteorología
  reales), incluyendo un caso con cambio de rango a mitad de mes y una
  relación de subcontrata — el informe de costes calculado coincide al
  céntimo con el cálculo manual esperado.
- Se corrigieron varios problemas encontrados durante la revisión: un vector
  de XSS al inyectar datos en un `<script>` inline, varios usos de hora UTC
  donde el original usaba hora local del servidor, una validación de fechas
  demasiado laxa, y una categorización de errores inconsistente (ver clase
  `ValidationError` en `src/utils.js`, que replica la distinción que hace
  Python entre `ValueError` —error de negocio, mensaje limpio— y `Exception`
  genérica —con prefijo "Error:"—, para no enmascarar fallos inesperados
  como si fueran errores de validación).

## Diferencias de implementación respecto a la versión Python

- **SQLite**: `better-sqlite3` (API síncrona) en vez de `sqlite3` de Python.
  Se usa una única conexión compartida por proceso, igual que en Flask cada
  request apuntaba al mismo fichero de BD.
- **Plantillas**: EJS en vez de Jinja2. El patrón `{% extends %}` se sustituye
  por un render en dos pasos (ver `middleware/render.js`): cada vista de
  `views/` es un simple fragmento de HTML que se inyecta en `layout.ejs`.
- **Flash messages**: implementadas a mano sobre `express-session`
  (`middleware/flash.js`) para replicar exactamente la semántica de Flask
  (categorías `error/success/warning/info`, mensajes de un solo uso).
- **Subida de archivos**: `multer` en vez de `request.files` de Flask.
- **Backup/restauración**: `Database#backup()` de better-sqlite3 (backup
  online nativo de SQLite) en vez de `sqlite3.Connection.backup()` de Python.
- **CSV**: generado a mano con separador `;` y BOM UTF-8 (para que Excel
  detecte bien los acentos), igual que hacía la versión Python con
  `charset=utf-8-sig`.

## Lo que NO se ha portado (no aplica a Node.js)

- `Launcher.py` (creaba un venv e instalaba dependencias a mano): en Node
  esto es simplemente `npm install`.
- El `.spec` de PyInstaller / instalador `.sh` para generar un ejecutable:
  si en algún momento quieres un ejecutable standalone en Node, la
  herramienta equivalente sería [`pkg`](https://github.com/vercel/pkg) o
  [`nexe`](https://github.com/nexe/nexe), pero no se ha configurado aquí.

## Notas para desarrollo

- `npm run dev` arranca con `node --watch` (reinicio automático al guardar).
- No hay tests automatizados todavía (tampoco los había en la versión
  Python): la Fase 2 de la hoja de ruta original los dejaba como pendiente
  opcional. La estructura modular actual (servicios puros, sin Express) hace
  que sea sencillo añadirlos con Jest o node:test cuando se quiera.
