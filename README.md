<div align="center">

# 🛠️ ObraPasaLista

**Control de presencia y partes de obra — local, sin servidores, sin complicaciones.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-embedded-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?style=for-the-badge&logo=bootstrap&logoColor=white)
![Estado](https://img.shields.io/badge/Estado-v1.0_activo-f97316?style=for-the-badge)

</div>

---

## 📌 ¿Qué es ObraPasaLista?

ObraPasaLista es una **aplicación web local** diseñada para sustituir el control manual en papel en obras de construcción. Permite registrar la presencia diaria del personal, gestionar empresas subcontratadas, cerrar meses y exportar partes, todo desde el navegador y sin necesidad de internet ni servidores externos.

> **Pensada para un único puesto de trabajo on-premise.** Un ordenador, un ejecutable, una base de datos local.

---

## ⚡ Arranque rápido

```bash
# 1. Clonar el repositorio
git clone https://github.com/RecklessCat55/ObraPasaLista.git
cd ObraPasaLista

# 2. Crear entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / Mac
pip install flask

# 3. Ejecutar la aplicación
python app.py
```

Abre tu navegador en **http://127.0.0.1:5000** y listo.

---

## 📂 Estructura del proyecto

```
ObraPasaLista/
├── app.py              ← Aplicación principal (Flask + lógica + plantillas)
├── app.db              ← Base de datos SQLite (se crea al primer arranque)
├── backups/            ← Snapshots automáticos de la BD
├── README.md
└── .venv/              ← Entorno virtual Python (no subir al repo)
```

---

## 🧱 Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3 + Flask |
| Base de datos | SQLite (embebida, sin configuración) |
| Frontend | Jinja2 + Bootstrap 5 (oscuro) |
| Backups | API nativa `Connection.backup()` de SQLite |

---

## 🗄️ Módulos funcionales

### 🏗️ Obras
Gestión de obras activas con código único. Panel de control con acceso directo al parte del día.

### 🏢 Empresas
Alta de empresas subcontratadas con estados `activa / finalizada / baja`. Relación many-to-many con obras.

### 👷 Personas
Registro de operarios con DNI, oficio y empresa actual. Soft delete: nunca se borran si tienen histórico.

### 🗓️ Diario
Parte diario por obra y fecha. Cada línea registra empresa, persona, asunto y horas trabajadas. Validación de límite diario de horas configurable.

### 📅 Mensual
Acumulado mensual por combinación **obra + empresa + mes**. Permite cerrar el mes generando un snapshot inmutable con nombre, DNI y horas por día.

### 💾 Backups
Creación y restauración de copias de seguridad desde la propia interfaz. Recomendado antes de cada cierre mensual.

---

## 🛡️ Reglas de integridad

- `PRAGMA foreign_keys = ON` activado en cada conexión.
- Consultas siempre parametrizadas `(?)` — sin riesgo de SQL injection.
- **Soft delete** en personas y empresas: los registros con histórico nunca se eliminan físicamente.
- El snapshot mensual **congela** nombre, DNI y horas en el momento del cierre, protegiendolos frente a cambios futuros en los maestros.
- Un mes **cerrado** bloquea cualquier modificación sobre sus partes diarios.

---

## ⚙️ Configuración

Desde la sección **Config** de la app puedes ajustar:

| Parámetro | Descripción | Valor por defecto |
|---|---|---|
| `limite_horas_dia` | Máximo de horas que puede acumular una persona en un día | `24.0` h |

---

## 📊 Esquema de base de datos

```
[empresa] ──< [obra_empresa] >── [obra]
    |                               |
    |                           [diario]
    |                               |
[persona] ──────────────────< [diario_linea]

[mensual] ──< [mensual_persona]
```

**Tablas maestras:** `empresa`, `persona`, `obra`, `obra_empresa`, `config`  
**Tablas operativas:** `diario`, `diario_linea`, `mensual`, `mensual_persona`

---

## 🚧 Hoja de ruta

### v1.0 ✅ (actual)
- [x] CRUD obras, empresas y personas
- [x] Parte diario por obra y fecha
- [x] Arrastre inteligente desde último parte con datos
- [x] Mensual por obra / empresa / mes
- [x] Cierre mensual con snapshot
- [x] Exportación CSV
- [x] Backups y restauración

### v1.1 🔧 (próxima)
- [ ] Separación en módulos (`db.py`, `routes_*.py`, `schema.sql`)
- [ ] Plantillas externas en carpeta `templates/`
- [ ] Mejor validación de errores y mensajes de integridad
- [ ] FAQ integrada y ampliada

### v2.0 💫 (futuro)
- [ ] Auditoría de cambios
- [ ] Historial formal de empresa por persona
- [ ] Reportes avanzados
- [ ] Instalador `.exe` con persistencia en `%LOCALAPPDATA%`

---

## ❓ FAQ

**¿Qué pasa si una persona cambia de empresa a mitad de mes?**  
Los partes antiguos conservan la empresa que tenían en `diario_linea` en ese momento. El histórico de facturación nunca se altera.

**¿Puedo borrar una empresa que tiene operarios?**  
No si tiene histórico vinculado. El sistema lo bloquea con un aviso. Lo correcto es marcarla como `baja`.

**¿Cómo se muestran las horas?**  
Internamente se almacenan como `REAL` (decimal). En pantalla y en exportación se muestran como `HH:MM`.

**¿Puedo modificar un parte de un mes ya cerrado?**  
No. El sistema bloquea cualquier modificación sobre partes cuyo mes esté en estado `cerrado`.

---

## 📝 Licencia

Proyecto privado — uso interno. Sin licencia pública por el momento.

---

<div align="center">

Hecho con ☕ y mucho SQLite por **RecklessCat55**

</div>
