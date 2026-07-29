# 📋 ObraPasaLista v1.2 — Estado Actual del Proyecto

**Sistema de Gestión de Partes Diarios de Obra**
**Versión actual:** 1.2 (implementada, código real del repo)
**Stack:** Python 3 | Flask | SQLite3 (WAL) | `render_template_string` monolítico
**Fecha de actualización:** Julio 2026

> Este README refleja el estado actual (v1.2). El análisis histórico detallado de la v1.1 (esquema, arquitectura, problemas detectados) se conserva más abajo como referencia. Los cambios de diseño de la v1.2 están documentados en `cambios-obra-pasalista.md`.

---

## 🎯 OBJETIVO DEL SISTEMA

Aplicación web local (single-user, `127.0.0.1:5000`) para control diario y mensual de operarios en obras de construcción: empresas, subcontratas, personas, rangos/categorías laborales, partidas de obra, partes diarios con meteorología, y cierre mensual con snapshot para facturación.

## ✅ NOVEDADES DE LA v1.2 (ya implementadas)

- **Infraestructura y esquema**
  - BD movida a `src/data/`, separada del código, con `app_test.db` para pruebas vía `OBRAPL_MODE=test`.
  - `secret_key` ahora sale de la variable de entorno `SECRET_KEY` (con fallback aleatorio).
  - `start.sh` invoca `Launcher.py` con la mayúscula correcta.
  - Nuevas columnas: `meta_horas_dia` (persona/empresa/obra), `umbral_desajuste_meta` (config), `precio_hora_override` (persona).
  - Nuevas tablas: `tarifa_rango`, `carpeta_obra`, `archivo_obra`, `log_auditoria`.
- **Metas de horas**: meta efectiva por prioridad persona > empresa > obra, con detección de desajustes vía `umbral_desajuste_meta`.
- **Tarifas y costes**: precio/hora por rango o por persona (`precio_hora_override`), cálculo de coste solo en informes administrativos (no en el diario operativo).
- **Documentación por obra/partida**: árbol de carpetas y archivos por obra/partida, con política de archivo (no borrado) al eliminar una partida.
- **Auditoría**: tabla `log_auditoria` que registra eventos administrativos (`CERRAR_OBRA`, `REACTIVAR_OBRA`, `CIERRE_MENSUAL`, `REABRIR_MENSUAL`, `DOC_ARCHIVAR_PARTIDA`) sin romper la transacción principal si falla el log.
- **Estado de obra**: obra `finalizada` congela diarios, mensuales y documentación (solo lectura); acción "Reactivar obra" disponible con log.
- **Asignación masiva en el diario**: asignar horas/partida/asunto comunes a varias personas de una empresa a la vez, con validación de horas y mes cerrado por persona.

Detalles de diseño completos en `cambios-obra-pasalista.md`.

## 📝 PENDIENTE / ROADMAP FUTURO

- Alerta de ">3 días" en el arrastre de diario (mejora de UX, no bloqueante).
- Tabla `schema_version` para formalizar futuras migraciones.
- Diferenciar horas normales/nocturnas/extra si se factura distinto (`tipo_hora`).
- Separar `app.py` en blueprints (`empresas`, `personas`, `obras`, `diario`, `mensual`, `backup`) y mover `render_template_string` a plantillas Jinja reales.
- Tests básicos (arrastre, límite de horas, bloqueo de mes cerrado).
- Sistema de usuarios/roles para restringir acceso a vistas administrativas.
- Valorar migración a SQLAlchemy como capa de acceso a datos.

---

## 📚 Historial — Análisis original v1.1 (referencia)

> Análisis realizado en su momento sobre el código v1.1, verificado línea a línea contra `src/app.py`. Varios de los puntos de "Problemas reales detectados" ya quedaron resueltos con la v1.2 (ver sección superior); se conserva el texto tal cual para no perder el historial de decisiones.

### 🗄️ Esquema de datos (v1.1)

Modelo centrado en `empresa`, `empresa_relacion` (subcontratas), `rango`, `persona`, `persona_rango` (histórico de rango por fechas), `obra`, `obra_empresa`, `partida_obra`, `config`, `diario` (1 diario = 1 obra + 1 fecha), `diario_linea` (la empresa vive aquí, no en `diario`), `mensual` y `mensual_persona` (snapshot congelado con columnas d1..d31 + total_mes).

**Diferencia clave respecto al diseño inicial:** la empresa no cuelga de `diario` sino de `diario_linea`, lo que permite cambiar de empresa a mitad de mes sin conflicto.

### 🏗️ Arquitectura (v1.1)

Un único archivo `app.py` (~1840 líneas), sin blueprints, con vistas que devuelven `render_template_string`. 44 rutas agrupadas en los módulos: Empresas, Subcontratas, Rangos, Personas, Obras, Diario, Mensual, Backup y Config.

### ⚙️ Lógica de negocio clave (v1.1)

- **Arrastre** (`diario_arrastrar`): copia líneas del diario anterior de la misma obra con horas=0, resolviendo el rango vigente de la persona.
- **Validación de horas** (`chk_horas`): suma horas ya registradas ese día y rechaza si se supera `config.limite_horas_dia`.
- **Bloqueo de mes cerrado** (`chk_mes_cerrado`): impide escribir líneas si el mensual de esa obra+empresa+mes está `cerrado`.
- **Cierre de mes** (`mensual_cerrar`): recalcula y snapshotea filas de forma atómica (un solo commit final).
- **Rango vigente y subcontratas** (`get_rango_activo`, `get_subcontratas`): resuelven histórico de categoría y cadena de subcontratación.

### 🔥 Problemas históricos detectados en v1.1 (ya resueltos en su mayoría en v1.2)

| # | Problema | Estado |
|---|---|---|
| 1 | `.gitignore` de proyecto Java/IntelliJ, no ignoraba `.venv/`, `__pycache__/`, `app.db`, `build/` | ✅ Resuelto |
| 2 | `app.db` con datos reales de obra subido al repo | ✅ Resuelto |
| 3 | Carpeta `build/` de PyInstaller subida entera | ✅ Resuelto |
| 4 | Nombre de archivo real no coincidía con el esperado por `Launcher.py` | ✅ Resuelto |
| 5 | `secret_key` hardcodeada | ✅ Resuelto (ahora viene de `SECRET_KEY`) |
| 6 | Monolito de ~1840 líneas en un solo archivo | ⏳ Pendiente (Fase 2 mantenibilidad) |
| 7 | Sin alerta de ">3 días" en el arrastre | ⏳ Pendiente |
| 8 | Sin tabla `schema_version` para migraciones | ⏳ Pendiente |

### ✅ Lo que ya estaba bien hecho en v1.1

- `PRAGMA foreign_keys=ON` + `PRAGMA journal_mode=WAL` en cada conexión.
- `row_factory = sqlite3.Row` para acceso por nombre de columna.
- Consultas parametrizadas (`?`) en todo lo revisado, sin inyección SQL.
- Comandos `flask --app app init-db` / `upgrade-db` con migración real v1.0→v1.1.
- Soft delete en empresa/persona (`estado`), histórico de rango por fechas.
- Página de backup/restauración de `.db` funcionando.
- Exportación CSV con cabeceras de obra/empresa/mes.
- `requirements.txt` presente (`flask>=2.3.0`).

---

**Autor:** Revisión basada en lectura directa del código fuente real del repo `RecklessCat55/ObraPasaLista`. Última actualización del README: julio 2026 (estado v1.2).
