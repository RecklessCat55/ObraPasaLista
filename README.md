# 📋 ObraPasaLista

**Control de presencia, coordinación CAE/PRL y gestión integral de personal en obra civil**, aplicación web local y offline diseñada específicamente para jefes de obra, encargados y administrativos que necesitan registrar asistencia diaria, gestionar documentación preventiva de subcontratas y supervisar costes de mano de obra en tiempo real sin depender de conexión a internet ni de la nube.

> **Versión actual**: `v1.5.2` · **Arquitectura**: Node.js (Express 5) + SQLite (`better-sqlite3`) · **Tests**: 73/73 superados (100% passing)

---

## 📖 Bitácora de Evolución del Proyecto (Diario de Desarrollo)

Esta bitácora narra la evolución del repositorio desde su prototipo inicial hasta convertirse en una plataforma de gestión de obra de grado industrial.

### 📓 Entrada 1: La era de Python y Flask (v1.0 – v1.2)
> *"Construir rápido para solucionar el barro de la obra: papel y boli ya no servían."*

- **El Origen**: ObraPasaLista nació como una herramienta de escritorio monolítica en Python usando Flask y Jinja2 en un solo archivo masivo (`app.py` de más de 3.200 líneas).
- **El reto de la obra**: En la caseta de obra no siempre hay internet, y la gente no quería instalar Node ni bases de datos complejas. Se empaquetó con **PyInstaller** en un ejecutable `ObraPasaLista.exe` de Windows acompañado de scripts `.bat`.
- **Límites encontrados**: A medida que crecía el catálogo de subcontratas y documentación, el ejecutable monolítico empezó a presentar problemas: bloqueos de concurrencia en ficheros SQLite, tiempos lentos de arranque, dificultad para actualizar parches de seguridad y errores con los controladores gráficos en Windows antiguos.

---

### 📓 Entrada 2: La Gran Migración a Node.js y Modularización (v1.3 – v1.4)
> *"Reescribir con base firme: velocidad síncrona, cero dependencias pesadas y arquitectura modular."*

- **Decisión arquitectónica**: Se reescribió por completo el motor de la aplicación en **Node.js (Express 5)** apoyado en el driver síncrono nativo **`better-sqlite3`**.
- **Separación de responsabilidades**:
  - Rutas desacopladas en [`src/routes/`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/src/routes/) (`diario`, `mensual`, `obras`, `personas`, `empresas`, `cae`, `informes`, etc.).
  - Lógica pura de negocio en [`src/services/`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/src/services/) (`negocio.js`, `horas.js`, `fechas.js`, `carryover.js`).
- **El legado seguro**: Todo el código fuente histórico de Python fue archivado en [`legacy-python/`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/legacy-python) para permitir auditorías y consultas retrospectivas.
- **Integridad y blindaje**:
  - **Soft Deletes**: Inclusión de `deleted_at` para evitar que la eliminación de un trabajador o contrata rompa los históricos de meses cerrados.
  - **Guardas de Meses Cerrados**: Imposibilidad técnica de modificar imputaciones de periodos ya certificados contablemente.
  - **Arrastre Temporal Inteligente**: Algoritmo que duplica la cuadrilla del último día laborable real, saltando automáticamente fines de semana y festivos de [`config_festivo`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/src/routes/config.js).

---

### 📓 Entrada 3: Blindaje de Seguridad, RGPD y Auditoría (v1.4.1)
> *"Los datos de personal son sagrados: cumplimiento normativo y robustez técnica."*

- **Derecho al olvido y RGPD**: Creación de la ruta transaccional de anonimización (`POST /personas/:id/anonimizar`) que borra los datos identificativos del trabajador tanto en la ficha viva como en las copias congeladas de cierres mensuales (`mensual_persona`).
- **Prevención de Directory Traversal**: Sanitización estricta de rutas en la restauración de backups (`secureFilename`) para bloquear cualquier intento de path traversal o nombres maliciosos.
- **Corrección de cálculos con subcontratas**: Evita duplicidades en cómputos de horas cuando conviven contratos de empresa principal y subcontratas en meses cerrados.
- **Reactivación limpia de personal**: Recuperación de trabajadores dados de baja preservando su ID y sin duplicar históricos.

---

### 📓 Entrada 4: Operatividad Real en Obra y Asignación Múltiple (v1.5.0)
> *"Escuchar a los encargados: subir varios planos a la vez, registrar incidencias y no cobrar ascensos antes de tiempo."*

- **Subida Multi-archivo en Documentación**: Adaptación del gestor documental para permitir arrastrar y subir simultáneamente múltiples planos, fotos o certificados en una sola acción (`upload.any()` con transacciones SQLite seguras).
- **Asignación Masiva Idempotente**: Rediseño integral de la pantalla [`asignacionMasiva.ejs`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/src/views/diario/asignacionMasiva.ejs). Ahora incluye buscador en tiempo real por DNI/nombre, botones globales de *"Marcar todos / Desmarcar todos"*, distintivos de horas previas y capacidad de reasignar sin duplicar líneas.
- **Cálculo de Costes con Ascensos por Fecha**: Corrección del algoritmo económico en [`negocio.js`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/src/services/negocio.js). Si un peón asciende a oficial el día 15 con mayor remuneración, la tarifa nueva aplica estrictamente a partir del día 15 en adelante, manteniendo las tarifas anteriores para los días 1 al 14.
- **Notas Circunstanciales en el Diario**: Inclusión de la columna `notas` en `diario` (Migración V15) con formulario directo y soporte AJAX para anotar retrasos de material, visitas facultativas o incidencias meteorológicas.
- **Descripción de Obra**: Inclusión de la columna `descripcion` en `obra` (Migración V15) visible en el panel general y en la cabecera del diario.
- **Navegación Fluida entre Días y Meses**: Selector de fechas integrado con botones de salto inmediato (*Ayer, Hoy, Mañana, Anterior, Siguiente*) y filtros dinámicos en la selección mensual.

---

### 📓 Entrada 5: Limpieza Profunda, Experiencia de Usuario y Modo Dual (v1.5.2 — Actual)
> *"Puliendo el producto: eliminación de peso muerto, modo claro/oscuro para el sol de obra y navegación ágil."*

- **Saneamiento del Repositorio**: 
  - Eliminación de más de **30 MB de archivos muertos**: binarios `.exe` obsoletos, cachés temporales de PyInstaller (`build/`, `dist/`), entornos virtuales Python huérfanos y scripts residuales en `src/`.
  - Desindexación de archivos locales de IDE (`.idea/`, `*.iml`) y ajuste de [`.gitignore`](file:///c:/inteliJ/ObraPasaLista/ObraPasaLista/.gitignore) para mantener el repositorio limpio y liviano.
- **Tema Dual (Modo Oscuro / Modo Claro)**:
  - Selector en barra de navegación con icono dinámico (<i class="bi bi-moon-stars-fill"></i> / <i class="bi bi-sun-fill"></i>).
  - Script anti-parpadeo (anti-flicker) en el `<head>` que lee `localStorage` y respeta las preferencias del sistema operativo.
  - **Modo Claro**: Pensado para máxima visibilidad en tablets al aire libre bajo la luz directa del sol.
  - **Modo Oscuro**: Estilo grafito industrial de alto contraste para baja fatiga visual y ahorro de batería en pantallas OLED.
- **Arquitectura de Navegación Rediseñada**:
  - Eliminación del menú "Más" saturado. Ahora los pilares operativos (*Inicio, Diario, Mensual, Obras*) y las **Alertas PRL** tienen visibilidad inmediata.
  - **Barra de Navegación Inferior Móvil (`opl-bottom-nav`)**: Fija al alcance del pulgar en pantallas de smartphone (`< 768px`).
- **Dashboard como "Centro de Operaciones"**:
  - Semáforo en vivo de cada obra indicando si el parte de hoy está en marcha (con recuento de operarios y horas totales acumuladas).
  - Banner proactivo de avisos si hay documentación preventiva próxima a vencer.
- **Gestión Documental Visual**:
  - Iconos automáticos según extensión de archivo (rojo para planos PDF, azul para fotos, amarillo para archivos CAD DWG y verde para hojas Excel).
- **Integración y Tests**: Suite ampliada a **73 tests automatizados** (41 smoke tests + 32 tests de integración HTTP con Supertest) superados al 100%.

---

## ✨ Funcionalidades principales

- **📅 Parte diario y asignación masiva optimizada**: Fichaje rápido por jornada con navegación entre días, selector de fecha interactivo y asignación masiva con filtro en tiempo real.
- **⚡ Arrastre temporal inteligente**: Duplicación automática de cuadrillas desde el último día laborable real, saltando fines de semana y festivos configurables.
- **🛡️ Coordinación CAE / PRL**: Semáforo preventivo que audita reconocimientos médicos, cursos PRL 20h, TC2 y pólizas de RC con alertas a 15 y 30 días vista.
- **🔒 Cierres mensuales inmutables**: Congelación de datos en instantáneas mensuales para auditorías y firmas sin riesgo de modificaciones accidentales.
- **🗑️ Integridad con Soft Deletes**: Bajas lógicas (`deleted_at`) que no rompen referencias en partes históricos ni violan claves foráneas.
- **💰 Cómputo exacto de costes con ascensos**: Cálculo diario considerando la fecha de entrada en vigor de los ascensos y variaciones tarifarias.
- **📁 Documentación técnica multi-archivo**: Carpetas jerárquicas con subida simultánea de planos y fotos organizadas por partida de obra.
- **📝 Notas circunstanciales**: Campo libre para documentar incidencias, climatología o visitas técnicas en el propio parte.
- **🌓 Modo Claro y Oscuro**: Alternancia instantánea con un toque y persistencia en memoria local.
- **📱 Optimizado para móviles y tablets**: Barra táctil inferior y zonas de contacto de mínimo 44px para uso con dedos sucios o guantes.
- **📊 Exportación y Reportes**: Generación de informes de costes y partes mensuales tabulares compatibles con Excel, LibreOffice y Google Sheets.

---

## 🛠️ Stack tecnológico

| Capa | Tecnología | Propósito |
|---|---|---|
| **Backend** | Node.js 18+ / Express 5 | Servidor HTTP monolítico rápido, robusto y local |
| **Base de datos** | SQLite 3 (`better-sqlite3`) | Motor relacional embebido en modo WAL con Foreign Keys |
| **Renderizado** | EJS (Embedded JavaScript) | Plantillas SSR sin latencia en cliente ni frameworks pesados |
| **Diseño / UI** | Bootstrap 5.3.2 + Icons 1.11.3 | Vendorizado en local (cero dependencias de CDNs externas) |
| **Archivos** | Multer | Subida y custodia local de planos, fotos y documentación técnica |
| **Sesiones** | express-session + flash | Mensajería contextual para el usuario |
| **Testing** | Node.js Test Runner + Supertest | Suite de 73 tests automatizados de unidad e integración |

---

## 🚀 Instalación y arranque rápido

### Requisitos previos
- [Node.js](https://nodejs.org/) **v18 o superior** (v20+ recomendado).
- `npm` (incluido con Node.js).

### Pasos de puesta en marcha
```bash
# 1. Clonar el repositorio
git clone https://github.com/RecklessCat55/ObraPasaLista.git
cd ObraPasaLista

# 2. Instalar dependencias
npm install

# 3. Inicializar esquema de base de datos
npm run init-db

# 4. Iniciar el servidor
npm start
```

La aplicación estará lista en **http://localhost:5000** (puerto configurable mediante la variable de entorno `PORT`).

---

## ⚙️ Comandos npm disponibles

| Comando | Acción |
|---|---|
| `npm start` | Inicia el servidor de producción en el puerto configurado |
| `npm run dev` | Inicia con reinicio automático al modificar ficheros (`node --watch`) |
| `npm run init-db` | Crea el esquema de base de datos completo y siembra datos base |
| `npm run upgrade-db` | Ejecuta las migraciones acumulativas idempotentes de forma segura |
| `npm run backup` | Ejecuta una copia de seguridad inmediata con verificación de integridad |
| `npm test` | Ejecuta la suite completa de 73 tests (smoke tests + HTTP integration) |

---

## 🗂️ Estructura del repositorio

```
ObraPasaLista/
├── public/                      # Assets estáticos servidos en local
│   └── vendor/                  # Bootstrap 5 y Bootstrap Icons (offline)
├── src/
│   ├── app.js                   # Configuración de Express y montaje de rutas
│   ├── config.js                # Variables de entorno y rutas en disco
│   ├── db.js                    # Esquema SQLite, migraciones v1.1-v1.5 y conexión WAL
│   ├── cli.js                   # Interfaz de línea de comandos (init, upgrade, backup)
│   ├── utils.js                 # Utilidades de seguridad, filtrado y serialización
│   ├── middleware/              # Helpers de renderizado EJS y sesiones flash
│   ├── routes/                  # Controladores de rutas HTTP modulares
│   │   ├── index.js             # Panel de control y centro de operaciones
│   │   ├── diario.js            # Partes diarios, arrastre inteligente y notas
│   │   ├── mensual.js           # Matriz mensual de horas y cierre de periodos
│   │   ├── obras.js             # Gestión de obras, empresas y partidas
│   │   ├── personas.js          # Fichas de trabajadores, ascensos y RGPD
│   │   ├── empresas.js          # Contratistas y subcontratas
│   │   ├── cae.js               # Alertas y semáforos de documentación PRL
│   │   ├── documentacion.js     # Explorador de archivos multi-subida de obra
│   │   ├── informes.js          # Informe económico y exportación Excel
│   │   ├── backup.js            # Centro web de copias de seguridad
│   │   ├── config.js            # Metas de jornada y festivos locales
│   │   └── rangos.js            # Categorías profesionales y tarifas horarias
│   ├── services/                # Lógica de cálculo y servicios desacoplados
│   │   ├── negocio.js           # Cómputo de costes dinámicos y metas efectivas
│   │   ├── carryover.js         # Algoritmo de arrastre entre días laborables
│   │   ├── cae.js               # Evaluación de vigencia documental
│   │   ├── excel.js             # Generador de hojas de cálculo
│   │   ├── backup.js            # Creación, verificación y rotación de backups
│   │   ├── horas.js             # Validaciones de límites y bloqueos de cierre
│   │   ├── fechas.js            # Normalización y formateo de fechas
│   │   └── logs.js              # Auditoría administrativa
│   └── views/                   # Vistas EJS responsivas con soporte dual claro/oscuro
├── tests/
│   ├── smoke_test.js            # 41 smoke tests funcionales en memoria
│   └── http_test.js             # 32 pruebas de integración HTTP (Supertest)
├── legacy-python/               # Archivo del proyecto original Python/Flask
├── package.json
└── README.md
```

---

## 🧪 Pruebas automatizadas de calidad

La suite de pruebas ejecuta **73 comprobaciones automáticas** sin requerir conexión a internet ni bases de datos externas:

```bash
npm test
```

### Cobertura de pruebas:
1. **Esquema y migraciones acumulativas**: Validación de esquemas hasta `v1.5` (`descripcion` en obra y `notas` en diario).
2. **Lógica de negocio y ascensos**: Verificación del cálculo de costes día por día aplicando el cambio de tarifa únicamente desde la fecha de efecto.
3. **Arrastre inteligente**: Comprobación del salto de festivos y fines de semana.
4. **Idempotencia en diario**: Asignación masiva y guardado de horas por API sin duplicaciones.
5. **Seguridad y RGPD**: Anonimización estricta de trabajadores en personas vivas y congeladas, y bloqueo de path traversal en copias de seguridad.
6. **Subida múltiple**: Aceptación simultánea de archivos en documentación técnica.

---

## 💾 Copias de seguridad y recuperación de desastres

### Crear una copia manual desde consola
```bash
npm run backup
```
Las copias se guardan con marca de tiempo en:
```
~/.obrapasalista/data/backups/backup_YYYYMMDD_HHMMSS_AUTO.db
```

### Política de retención y verificación
- **Rotación**: Almacena hasta **30 copias** y descarta las que superen los **90 días**.
- **Integridad**: Cada archivo de backup se somete a `PRAGMA integrity_check` antes de considerarse válido.

---

## ♿ Ergonomía para el trabajo a pie de obra

- **Diseño táctil accesible**: Todos los botones de acción rápida cuentan con una zona táctil mínima de **44px de altura**, adecuada para uso con guantes o dedos mojados.
- **Tipografía técnica**: Números de horas, importes, DNIs y fechas presentados con fuentes monoespaciadas legibles a distancia.
- **Modo Claro / Oscuro**: Adaptación inmediata para trabajar bajo sol radiante o en casetas con poca luz.

---

## 📄 Licencia

Proyecto privado — Todos los derechos reservados.  
*Diseñado y desarrollado para la gestión técnica de obra civil y edificación.*
