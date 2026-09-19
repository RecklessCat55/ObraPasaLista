# ObraPasaLista v1.2 — Resumen de cambios de diseño

Este documento describe los cambios funcionales y técnicos propuestos sobre el repo original `RecklessCat55/ObraPasaLista` (estado v1.1), para que el siguiente desarrollador (Claude Sonnet 5) pueda implementarlos de forma ordenada.

## 1. Contexto del repo original

- Monolito Flask (`src/app.py`) usando `sqlite3` directo, `sqlite3.Row` y PRAGMA `foreign_keys=ON` por conexión.
- Base de datos `app.db` en el directorio de código (`src/`), sin distinción formal entre producción y pruebas.
- Módulo de backup usando la Online Backup API de SQLite, con copias en una carpeta `backups/` al lado de la BD.
- Modelo de datos centrado en:
  - `obra`, `empresa`, `persona`, `rango`.
  - `diario` + `diario_linea` como parte diario de obra.
  - `mensual` + `mensual_persona` como snapshot mensual de horas por persona/empresa/obra.
  - `config` para parámetros globales (p.ej. límite de horas/día).
- Sin metas de horas por persona/empresa/obra, sin tarifas/costes, sin módulo de documentación por obra/partida y sin sistema de auditoría de acciones administrativas.

## 2. Cambios estructurales

### 2.1. Carpeta de datos y modos de entorno

**Objetivo**: separar código y datos, y preparar la distinción producción/pruebas.

Cambios:

- Crear carpeta `data/` dentro de `src/` y mover la BD ahí.
- En `app.py`, sustituir las constantes de BD por:
  - `BASE_DIR = os.path.dirname(os.path.abspath(__file__))`
  - `DATA_DIR = os.path.join(BASE_DIR, "data")` + `os.makedirs(DATA_DIR, exist_ok=True)`.
  - `mode = os.environ.get("OBRAPL_MODE", "prod")`.
  - `DB_NAME = "app_test.db" if mode == "test" else "app.db"`.
  - `DB_PATH = os.path.join(DATA_DIR, DB_NAME)`.
  - `BACKUP_DIR = os.path.join(DATA_DIR, "backups")`.
- El resto del código que usa `DB_PATH` y `BACKUP_DIR` no cambia, pero ahora los datos quedan en `data/` y puedes tener una BD de pruebas (`app_test.db`) sin tocar la de producción.

### 2.2. Módulos de servicios

**Objetivo**: separar lógica de negocio de rutas Flask, preparando terreno para una futura migración a SQLAlchemy.

Cambios:

- Crear módulo `services/horas.py` con helpers que ahora están en `app.py`:
  - `get_lim(db)` → lee `config.limite_horas_dia`.
  - `chk_horas(id_persona, fecha, h_new, excl, db)` → valida límite diario, lanzando `ValueError` con mensaje de negocio (no jerga de BBDD).
  - `chk_mes_cerrado(id_obra, id_empresa, fecha, db)` → valida si el mensual está cerrado para esa obra/empresa/mes.
  - `get_rango_activo(id_persona, fecha, db)` → devuelve el rango activo para esa persona en esa fecha.
- Importar estos helpers en `app.py` y usarlos en las rutas de diario/mensual en lugar de tener la lógica duplicada.
- (Más adelante) crear otros módulos de servicio: `services/metas.py`, `services/asignacion.py`, `services/docs.py`, `services/logs.py`.

### 2.3. Tabla de auditoría de acciones sobre obras

**Objetivo**: registrar eventos administrativos importantes relacionados con las obras, sin romper la transacción principal.

Cambios:

- Nueva tabla `log_auditoria`:

  ```sql
  CREATE TABLE IF NOT EXISTS log_auditoria (
      id_log      INTEGER PRIMARY KEY AUTOINCREMENT,
      fecha       TEXT    NOT NULL,
      tipo_evento TEXT    NOT NULL,   -- CIERRE_MENSUAL, REABRIR_MENSUAL, CERRAR_OBRA, REACTIVAR_OBRA, DOC_ARCHIVAR_PARTIDA, ...
      entidad     TEXT    NOT NULL,   -- 'mensual', 'obra', 'partida', ...
      entidad_id  INTEGER NOT NULL,   -- id_mensual, id_obra, id_partida, ...
      obra_id     INTEGER NOT NULL,   -- siempre relleno para eventos de obra
      detalle     TEXT    NOT NULL    -- JSON con contexto (siempre incluye obra_id y obra_nombre)
  );
  ```

- Alter para añadir `obra_id` si la tabla ya existiera:

  ```sql
  ALTER TABLE log_auditoria ADD COLUMN obra_id INTEGER;
  ```

- Helper `log_event(tipo_evento, entidad, entidad_id, obra_id, detalle_dict)` en `services/logs.py` que:
  - Serializa `detalle_dict` a JSON (añadiendo siempre `obra_id`).
  - Ejecuta `INSERT` en `log_auditoria` dentro de la transacción abierta.
  - Si falla el logging, captura la excepción y muestra un `flash` o un mensaje en consola, **sin lanzar** la excepción hacia arriba (la operación principal no debe romperse porque el log falle).

Eventos a implementar en primera iteración:

- `CERRAR_OBRA`: al finalizar obra.
- `REACTIVAR_OBRA`: al reabrir obra finalizada.
- `CIERRE_MENSUAL`: al cerrar mensual.
- `REABRIR_MENSUAL`: al reabrir mensual.
- `DOC_ARCHIVAR_PARTIDA`: al archivar documentación al borrar una partida.

## 3. Cambios de esquema SQLite

### 3.1. Metas de horas

**Objetivo**: tener metas de horas por persona, empresa y obra, con prioridad a la más específica.

Cambios:

```sql
ALTER TABLE persona ADD COLUMN meta_horas_dia REAL;
ALTER TABLE empresa ADD COLUMN meta_horas_dia REAL;
ALTER TABLE obra    ADD COLUMN meta_horas_dia REAL;

ALTER TABLE config  ADD COLUMN umbral_desajuste_meta REAL
    DEFAULT 2.0 CHECK(umbral_desajuste_meta >= 0);
```

- Regla de negocio: meta efectiva = persona.meta_horas_dia si no es `NULL`, si no empresa.meta_horas_dia, si no obra.meta_horas_dia, si no valor por defecto (8h).
- `umbral_desajuste_meta` se usa para detectar desajustes persona/empresa (ej. persona 6h vs empresa 8h), generando warnings en momentos clave (no en cada fichaje).

### 3.2. Tarifas y costes

**Objetivo**: poder calcular coste de horas por persona/obra en informes administrativos, sin mostrar precios en la UI operativa de diario.

Cambios:

```sql
CREATE TABLE IF NOT EXISTS tarifa_rango (
    id_rango INTEGER PRIMARY KEY,
    precio_hora REAL NOT NULL CHECK(precio_hora >= 0)
);

ALTER TABLE persona ADD COLUMN precio_hora_override REAL;
```

- Regla de negocio:
  - Precio efectivo por persona = `precio_hora_override` si no es `NULL`, si no `tarifa_rango.precio_hora` para su rango activo.
  - Moneda: euro.
- Cálculo de coste se hace en informes (mensual, por día/obra) multiplicando `horas * precio_hora`; no se almacenan los costes en la tabla, se recomputan bajo demanda.

### 3.3. Documentación por obra/partida

**Objetivo**: almacenar documentación (planos, fotos, PDFs) por obra y partida, con capacidad de archivo cuando se borra una partida.

Cambios:

```sql
CREATE TABLE IF NOT EXISTS carpeta_obra (
    id_carpeta   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_obra      INTEGER NOT NULL REFERENCES obra(id_obra) ON DELETE RESTRICT,
    id_partida   INTEGER REFERENCES partida_obra(id_partida) ON DELETE SET NULL,
    nombre       TEXT    NOT NULL,
    ruta_relativa TEXT   NOT NULL,
    id_padre     INTEGER REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE,
    archivada    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS archivo_obra (
    id_archivo   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_carpeta   INTEGER NOT NULL REFERENCES carpeta_obra(id_carpeta) ON DELETE CASCADE,
    nombre       TEXT    NOT NULL,
    ruta_relativa TEXT   NOT NULL,
    tipo_mime    TEXT,
    fecha_subida TEXT    NOT NULL,
    notas        TEXT
);
```

- Ruta física base configurable en código:

  ```python
  DOCS_DIR = os.environ.get("OBRAPL_DOCS_DIR") or os.path.join(BASE_DIR, "docs")
  os.makedirs(DOCS_DIR, exist_ok=True)
  ```

- Política de borrado/archivo:
  - Al borrar una partida con documentación, los archivos se mueven físicamente a una carpeta de archivo (`docs/archivado/obra_X/partida_Y_fecha/`).
  - En BD, `archivo_obra.ruta_relativa` se actualiza, `archivada=1` y `id_partida` se pone a `NULL` si procede.
  - No se borran registros de documentación; quedan siempre recuperables.

## 4. Nuevas reglas de negocio

### 4.1. Estado de obra y relación con mensuales

**Reglas clave**:

- No se puede marcar una obra como `finalizada` si tiene algún mensual `abierto` para cualquier empresa.
- Acción "Cerrar obra":
  - Comprueba mensuales abiertos.
  - Si hay abiertos, lista cuáles son y redirige al usuario a la pantalla de mensuales para cerrarlos primero.
  - Si todos están cerrados, hace `UPDATE obra SET estado='finalizada'` y registra `CERRAR_OBRA` en `log_auditoria`.
- Obra `finalizada` implica congelación global:
  - Diarios: no se pueden crear nuevos ni modificar/borrar líneas.
  - Mensuales: no se pueden crear nuevos ni reabrir mientras la obra esté finalizada.
  - Documentación: solo lectura (ver/descargar), sin crear, borrar ni renombrar.
- Acción "Reactivar obra":
  - Solo aplicable si `estado='finalizada'`.
  - Hace `UPDATE obra SET estado='activa'`.
  - Registra `REACTIVAR_OBRA` en `log_auditoria`.
  - No reabre automáticamente mensuales; la reapertura de mes sigue siendo una acción explícita.

### 4.2. Cierre y reapertura de mensuales

- Cierre mensual (`CIERRE_MENSUAL`):
  - Mantiene la lógica actual de snapshot (`mensual_persona`).
  - Registra evento en `log_auditoria` con JSON que incluye `obra_id`, `obra_nombre`, `empresa_id`, `empresa_nombre`, `mes`.
- Reapertura mensual (`REABRIR_MENSUAL`):
  - Borra snapshot, marca `estado='abierto'` y vuelve a permitir cambios.
  - Registra evento en `log_auditoria` con los mismos campos y, opcionalmente, `motivo`.

### 4.3. Asignación múltiple en el diario

**Objetivo**: permitir asignar la misma jornada (horas, partida, asunto) a una cuadrilla de personas de una empresa en una obra y fecha dadas.

Reglas:

- Nueva pantalla `GET/POST /diario/<id_diario>/asignacion-masiva`:
  - Selección de empresa fija.
  - Listado de personas activas de esa empresa con checkbox.
  - Formularios para: horas comunes, partida común, asunto común.
- Lógica de asignación:
  - Para cada persona seleccionada:
    - Validar mes cerrado con `chk_mes_cerrado` (bloquea si el mensual está cerrado).
    - Validar límite diario con `chk_horas` (bloquea si supera el máximo diario).
    - Calcular meta efectiva (persona>empresa>obra) y generar warning no bloqueante si queda por debajo.
    - Insertar línea con rango automático (`get_rango_activo`), `id_empresa` fijo, `id_partida` común y asunto común.
  - Resultado: estructura con líneas `creadas` y `bloqueadas` y motivos textuales claros (sin jerga de BBDD) para mostrar en la UI.

### 4.4. Metas de horas: UI y comportamiento

- Pantalla "Config → metas de horas":
  - Tabla con metas por persona, empresa y obra.
  - Campo global `umbral_desajuste_meta`.
  - Obras con `estado='finalizada'`: metas solo visibles, no editables.
- Comportamiento:
  - Meta de persona prevalece sobre meta de empresa y obra.
  - Desajustes persona vs empresa (diferencia ≥ `umbral_desajuste_meta`) se avisan en momentos clave (ej. al vincular persona a empresa, en informes), no cada vez que se registran horas.

### 4.5. Costes: solo en vistas administrativas

- No se muestran costes ni precios/hora en el diario normal.
- Se habilita una vista/informe administrativo (por ejemplo `/informes/costes`) que usa las tarifas para calcular:
  - Coste total por persona y mes.
  - Coste total por obra/día.
- En esta fase no se introduce sistema de roles; se asume un único usuario con acceso completo, pero la separación de vistas está preparada para futuras restricciones.

### 4.6. Documentación y estado de obra

- Ficha de obra:
  - Panel "Documentación" con árbol `Partidas → carpetas → archivos`.
- Diario:
  - En líneas con `id_partida` asociado, icono que abre documentación de esa partida.
- Obra `finalizada`:
  - Panel de documentación pasa a solo lectura (sin botones de crear/subir/borrar).

## 5. Vista "Estado de obra" y auditoría por obra

**Objetivo**: dar al usuario una vista única del estado administrativo de la obra.

- Nueva ruta `GET /obra/<id_obra>/estado` que devuelve:
  - Datos básicos de la obra (`nombre`, `estado`).
  - Lista de mensuales por empresa (`mes`, `empresa`, `estado`).
  - Últimos N registros de `log_auditoria` para `obra_id`.
- Plantilla `obra_estado.html` muestra:
  - Banner de estado de obra (ACTIVA vs FINALIZADA) con mensaje claro.
  - Tabla de mensuales con badges de estado y botones "Cerrar mes" / "Reabrir mes" deshabilitados si la obra está finalizada.
  - Si la obra está activa y todos los mensuales están cerrados: botón "Finalizar obra".
  - Si la obra está finalizada: botón "Reabrir obra" con confirmación.
  - Panel "Actividad administrativa" con tabla de eventos (`fecha`, `tipo_evento`, `detalle` JSON o parseado).

## 6. Orden recomendado de implementación

Para Claude Sonnet 5, el orden de trabajo recomendado es:

1. **Fase 1 — Infraestructura y esquema**
   - Mover BD a `data/` y parametrizar `DB_PATH` según `OBRAPL_MODE` (`app.db` vs `app_test.db`).
   - Crear `services/horas.py` y mover allí helpers de validación de horas/mes.
   - Añadir columnas `meta_horas_dia`, `umbral_desajuste_meta`, `precio_hora_override` y tablas `tarifa_rango`, `carpeta_obra`, `archivo_obra`, `log_auditoria` via `upgrade-db`.

2. **Fase 2 — Reglas de negocio endurecidas**
   - Implementar pantalla "Config → metas de horas" y lógica de meta efectiva (persona>empresa>obra).
   - Implementar vista "Estado de obra" con listado de mensuales y banners de estado.
   - Añadir rutas `obra_cerrar` y `obra_reactivar` con comprobación de mensuales y logs `CERRAR_OBRA` / `REACTIVAR_OBRA`.
   - Añadir logs `CIERRE_MENSUAL` / `REABRIR_MENSUAL` en las rutas actuales de mensuales.
   - Implementar asignación múltiple en el diario apoyándose en `services/horas.py`.

3. **Fase 3 — Documentación y costes**
   - Implementar UI de documentación por obra/partida (`carpeta_obra`, `archivo_obra`), incluyendo política de archivo al borrar partida (`DOC_ARCHIVAR_PARTIDA`).
   - Implementar informes de coste usando `tarifa_rango` y `precio_hora_override` (solo en vistas administrativas).

4. **Fase 4 — Refinamiento y roles (futuro)**
   - Introducir sistema de usuarios/roles y restringir acceso a vistas administrativas (`/obra/<id>/estado`, `/admin/log`, informes de costes).
   - Valorar migración a SQLAlchemy como capa de acceso a datos una vez el modelo esté estable.
