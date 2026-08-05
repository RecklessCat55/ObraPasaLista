'use strict';
/**
 * services/negocio.js — helpers de negocio que en app.py (Python) vivían
 * como funciones sueltas a nivel de módulo (get_subcontratas,
 * _calcular_filas_mensual, get_meta_efectiva, chk_desajuste_meta,
 * _informe_costes, _chk_obra_activa, _mensuales_abiertos, nombre_persona,
 * _uso_persona...). Aquí se agrupan en un módulo propio porque no son
 * "rutas" sino lógica compartida entre varias rutas.
 *
 * Todas reciben `db` explícitamente (better-sqlite3 Database).
 */
const { fs, hhmm } = require('./fechas');
const { getRangoActivo } = require('./horas');
const { ValidationError } = require('../utils');

function nombrePersona(db, idPersona) {
  const p = db
    .prepare('SELECT nombre,apellido1 FROM persona WHERE id_persona=?')
    .get(idPersona);
  return p ? `${p.nombre} ${p.apellido1}` : '(persona no encontrada)';
}

/** Nº de usos de una persona en diario, mensual y su historial de rangos. */
function usoPersona(db, idPersona) {
  const nDl = db
    .prepare('SELECT count(*) c FROM diario_linea WHERE id_persona=?')
    .get(idPersona).c;
  const nMp = db
    .prepare('SELECT count(*) c FROM mensual_persona WHERE id_persona=?')
    .get(idPersona).c;
  const nHist = db
    .prepare('SELECT count(*) c FROM persona_rango WHERE id_persona=?')
    .get(idPersona).c;
  return { diario: nDl, mensual: nMp, hist: nHist };
}

function getSubcontratas(db, idEmpresa) {
  const rows = db
    .prepare('SELECT id_empresa_subcontrata FROM empresa_relacion WHERE id_empresa_principal=?')
    .all(idEmpresa);
  return rows.map((r) => r.id_empresa_subcontrata);
}

/** Calcula filas del mensual desde los diarios (estado abierto). */
function calcularFilasMensual(db, idObra, idEmpresa, mesStr) {
  const subs = getSubcontratas(db, idEmpresa);
  const empIds = [idEmpresa, ...subs];
  const ph = empIds.map(() => '?').join(',');
  const rows = db
    .prepare(
      `SELECT dl.id_persona, dl.id_empresa, dl.id_rango,
              p.nombre nom_c, p.apellido1 ap1_c, p.apellido2 ap2_c, p.dni dni_c,
              e.nombre emp_n, r.nombre ran_n,
              CAST(strftime('%d', d.fecha) AS INTEGER) ndia,
              SUM(dl.horas) horas
       FROM diario_linea dl
       JOIN diario   d ON dl.id_diario  = d.id_diario
       JOIN persona  p ON dl.id_persona = p.id_persona
       JOIN empresa  e ON dl.id_empresa = e.id_empresa
       LEFT JOIN rango r ON dl.id_rango = r.id_rango
       WHERE d.id_obra=? AND dl.id_empresa IN (${ph})
         AND strftime('%Y-%m', d.fecha)=?
       GROUP BY dl.id_persona, dl.id_empresa, dl.id_rango, ndia
       ORDER BY e.nombre, p.apellido1, p.nombre, ndia`
    )
    .all(idObra, ...empIds, mesStr);

  const grupos = new Map();
  for (const r of rows) {
    const k = `${r.id_persona}|${r.id_empresa}|${r.id_rango}`;
    if (!grupos.has(k)) {
      grupos.set(k, {
        nom_c: r.nom_c,
        ap1_c: r.ap1_c,
        ap2_c: r.ap2_c,
        dni_c: r.dni_c,
        empresa_cache: r.emp_n,
        rango_cache: r.ran_n || '',
        es_subcontrata: r.id_empresa !== idEmpresa ? 1 : 0,
        id_persona: r.id_persona,
        id_empresa: r.id_empresa,
        id_rango: r.id_rango,
        dias: {},
      });
    }
    grupos.get(k).dias[r.ndia] = r.horas;
  }

  const [year, month] = [parseInt(mesStr.slice(0, 4), 10), parseInt(mesStr.slice(5, 7), 10)];
  const days = new Date(year, month, 0).getDate();
  const result = [];
  for (const g of grupos.values()) {
    const diasArr = [];
    for (let i = 1; i <= days; i++) diasArr.push(g.dias[i] !== undefined ? g.dias[i] : null);
    const total = diasArr.reduce((acc, h) => acc + (h !== null ? h : 0), 0);
    result.push({ ...g, dias_arr: diasArr, total_mes: total, days });
  }
  result.sort((a, b) => {
    if (a.es_subcontrata !== b.es_subcontrata) return a.es_subcontrata - b.es_subcontrata;
    if (a.empresa_cache !== b.empresa_cache) return a.empresa_cache < b.empresa_cache ? -1 : 1;
    if (a.ap1_c !== b.ap1_c) return a.ap1_c < b.ap1_c ? -1 : 1;
    if (a.nom_c !== b.nom_c) return a.nom_c < b.nom_c ? -1 : 1;
    return 0;
  });
  return { filas: result, days };
}

// ============================ METAS DE HORAS (3.1, 4.4) =====================

/**
 * Meta de horas/día efectiva: persona > empresa > obra > 8h por defecto.
 * Devuelve { valor, origen } donde origen in {'persona','empresa','obra','defecto'}.
 */
function getMetaEfectiva(db, idPersona, idEmpresa, idObra) {
  if (idPersona) {
    const r = db.prepare('SELECT meta_horas_dia FROM persona WHERE id_persona=?').get(idPersona);
    if (r && r.meta_horas_dia !== null) return { valor: r.meta_horas_dia, origen: 'persona' };
  }
  if (idEmpresa) {
    const r = db.prepare('SELECT meta_horas_dia FROM empresa WHERE id_empresa=?').get(idEmpresa);
    if (r && r.meta_horas_dia !== null) return { valor: r.meta_horas_dia, origen: 'empresa' };
  }
  if (idObra) {
    const r = db.prepare('SELECT meta_horas_dia FROM obra WHERE id_obra=?').get(idObra);
    if (r && r.meta_horas_dia !== null) return { valor: r.meta_horas_dia, origen: 'obra' };
  }
  return { valor: 8.0, origen: 'defecto' };
}

function getUmbralDesajuste(db) {
  const r = db.prepare('SELECT umbral_desajuste_meta FROM config WHERE id_config=1').get();
  return r ? r.umbral_desajuste_meta : 2.0;
}

/**
 * Devuelve un mensaje de aviso (string) si la meta de la persona y la de su
 * empresa difieren en más del umbral configurado, o null si no aplica.
 * No bloquea nada: es solo informativo.
 */
function chkDesajusteMeta(db, idPersona, idEmpresa) {
  const p = db
    .prepare('SELECT meta_horas_dia, nombre, apellido1 FROM persona WHERE id_persona=?')
    .get(idPersona);
  const e = db.prepare('SELECT meta_horas_dia, nombre FROM empresa WHERE id_empresa=?').get(idEmpresa);
  if (!p || !e || p.meta_horas_dia === null || e.meta_horas_dia === null) return null;
  const umbral = getUmbralDesajuste(db);
  const diff = Math.abs(p.meta_horas_dia - e.meta_horas_dia);
  if (diff >= umbral) {
    return (
      `Desajuste de meta: ${p.nombre} ${p.apellido1} tiene meta ${hhmm(p.meta_horas_dia)} ` +
      `pero ${e.nombre} tiene meta ${hhmm(e.meta_horas_dia)} (diferencia ${hhmm(diff)}).`
    );
  }
  return null;
}

/** Recorre todas las personas con empresa asignada y devuelve avisos de desajuste. */
function listarDesajustesMeta(db) {
  const avisos = [];
  const personas = db
    .prepare("SELECT id_persona, id_empresa FROM persona WHERE id_empresa IS NOT NULL AND estado='activa'")
    .all();
  for (const p of personas) {
    const w = chkDesajusteMeta(db, p.id_persona, p.id_empresa);
    if (w) avisos.push(w);
  }
  return avisos;
}

// ============================ COSTES (3.2, 4.5) ==============================

/** Precio/hora efectivo = persona.precio_hora_override si existe, si no tarifa_rango de su rango activo. */
function precioEfectivoPersona(db, idPersona, fecha = null) {
  const p = db
    .prepare('SELECT precio_hora_override FROM persona WHERE id_persona=?')
    .get(idPersona);
  if (p && p.precio_hora_override !== null) return p.precio_hora_override;
  const f = fecha || fs(new Date());
  const idR = getRangoActivo(idPersona, f, db);
  if (idR) {
    const t = db.prepare('SELECT precio_hora FROM tarifa_rango WHERE id_rango=?').get(idR);
    if (t) return t.precio_hora;
  }
  return null;
}

/**
 * Calcula, para una obra y un mes:
 *   - filas: coste total por persona y mes (usa snapshot si el mensual de
 *     su empresa está cerrado, o el diario si sigue abierto).
 *   - diasTabla: coste total por obra/día (agregado de todas las personas).
 * Los costes NUNCA se almacenan; se recalculan bajo demanda con los precios
 * vigentes en el momento de generar el informe.
 */
function informeCostes(db, idObra, mesStr) {
  const [year, month] = [parseInt(mesStr.slice(0, 4), 10), parseInt(mesStr.slice(5, 7), 10)];
  const days = new Date(year, month, 0).getDate();
  const cerrados = new Set(
    db
      .prepare("SELECT id_empresa FROM mensual WHERE id_obra=? AND mes=? AND estado='cerrado'")
      .all(idObra, mesStr)
      .map((r) => r.id_empresa)
  );

  const filas = [];
  const horasDia = new Array(days + 1).fill(0.0);
  const costeDia = new Array(days + 1).fill(0.0);

  // -- empresas con mensual ya cerrado: snapshot mensual_persona --
  const dcols = Array.from({ length: 31 }, (_, i) => `mp.d${i + 1}`).join(',');
  const cerradosRows = db
    .prepare(
      `SELECT mp.id_persona, mp.nom_c, mp.ap1_c, mp.ap2_c, mp.empresa_cache, mp.total_mes, ${dcols}
       FROM mensual_persona mp JOIN mensual m ON mp.id_mensual=m.id_mensual
       WHERE m.id_obra=? AND m.mes=? AND m.estado='cerrado'`
    )
    .all(idObra, mesStr);
  for (const r of cerradosRows) {
    const precio = precioEfectivoPersona(db, r.id_persona) || 0;
    const horas = r.total_mes || 0;
    filas.push({
      nombre: `${r.ap1_c} ${r.ap2_c}, ${r.nom_c}`,
      empresa: r.empresa_cache,
      horas,
      precio_hora: precio,
      coste: horas * precio,
    });
    for (let i = 1; i <= days; i++) {
      const h = r[`d${i}`];
      if (h) {
        horasDia[i] += h;
        costeDia[i] += h * precio;
      }
    }
  }

  // -- empresas con mensual abierto (o sin mensual): directamente del diario --
  let q = `SELECT dl.id_persona, dl.id_empresa, p.nombre nom, p.apellido1 ap1, p.apellido2 ap2, e.nombre emp,
                  CAST(strftime('%d', d.fecha) AS INTEGER) ndia, SUM(dl.horas) horas
           FROM diario_linea dl
           JOIN diario  d ON dl.id_diario=d.id_diario
           JOIN persona p ON dl.id_persona=p.id_persona
           JOIN empresa e ON dl.id_empresa=e.id_empresa
           WHERE d.id_obra=? AND strftime('%Y-%m', d.fecha)=?`;
  const params = [idObra, mesStr];
  if (cerrados.size) {
    q += ` AND dl.id_empresa NOT IN (${[...cerrados].map(() => '?').join(',')})`;
    params.push(...cerrados);
  }
  q += ' GROUP BY dl.id_persona, dl.id_empresa, ndia';

  const agg = new Map();
  for (const r of db.prepare(q).all(...params)) {
    const k = `${r.id_persona}|${r.id_empresa}`;
    if (!agg.has(k)) {
      agg.set(k, {
        nombre: `${r.ap1} ${r.ap2}, ${r.nom}`,
        empresa: r.emp,
        horas: 0.0,
        precio_hora: precioEfectivoPersona(db, r.id_persona) || 0,
      });
    }
    const v = agg.get(k);
    v.horas += r.horas;
    horasDia[r.ndia] += r.horas;
    costeDia[r.ndia] += r.horas * v.precio_hora;
  }
  for (const v of agg.values()) {
    v.coste = v.horas * v.precio_hora;
    filas.push(v);
  }

  filas.sort((a, b) => {
    if (a.empresa !== b.empresa) return a.empresa < b.empresa ? -1 : 1;
    if (a.nombre !== b.nombre) return a.nombre < b.nombre ? -1 : 1;
    return 0;
  });
  const totalHoras = filas.reduce((acc, f) => acc + f.horas, 0);
  const totalCoste = filas.reduce((acc, f) => acc + f.coste, 0);
  const diasTabla = [];
  for (let i = 1; i <= days; i++) diasTabla.push({ dia: i, horas: horasDia[i], coste: costeDia[i] });
  return { filas, diasTabla, totalHoras, totalCoste, days };
}

// ==================== ESTADO DE OBRA / AUDITORÍA (2.3, 4.1, 5) ================

/** Lanza Error si la obra está finalizada (para bloquear altas/bajas). */
function chkObraActiva(db, idObra) {
  const ob = db.prepare('SELECT estado FROM obra WHERE id_obra=?').get(idObra);
  if (ob && ob.estado === 'finalizada') {
    throw new ValidationError('La obra está finalizada: esta acción no está permitida.');
  }
}

/** Lista de mensuales en estado 'abierto' para una obra (cualquier empresa). */
function mensualesAbiertos(db, idObra) {
  return db
    .prepare(
      `SELECT m.*, e.nombre nom_e FROM mensual m
       JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_obra=? AND m.estado='abierto' ORDER BY m.mes, e.nombre`
    )
    .all(idObra);
}

module.exports = {
  nombrePersona,
  usoPersona,
  getSubcontratas,
  calcularFilasMensual,
  getMetaEfectiva,
  getUmbralDesajuste,
  chkDesajusteMeta,
  listarDesajustesMeta,
  precioEfectivoPersona,
  informeCostes,
  chkObraActiva,
  mensualesAbiertos,
};
