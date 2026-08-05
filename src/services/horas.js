'use strict';
/**
 * services/horas.js — validaciones de negocio sobre horas y meses.
 *
 * Equivalente a services/horas.py. Cada función recibe la conexión `db`
 * (better-sqlite3 Database) explícitamente, igual que la versión Python
 * recibía la conexión sqlite3, para no depender de Express ni del resto
 * de la app.
 *
 * Los mensajes de error están pensados para mostrarse directamente al
 * usuario final (jefe de obra), no jerga de base de datos.
 */
const { fs, mes, hhmm } = require('./fechas');
const { ValidationError } = require('../utils');

/** Límite de horas/día configurado globalmente. */
function getLim(db) {
  const r = db.prepare('SELECT limite_horas_dia FROM config WHERE id_config=1').get();
  return r ? r.limite_horas_dia : 24.0;
}

/**
 * Valida que una persona no supere el límite de horas/día al sumar `hNew`
 * en `fecha` (contando todas las obras y empresas). Lanza Error con un
 * mensaje de negocio si se supera.
 * `excl` permite excluir una línea concreta (id_dl) al editar.
 */
function chkHoras(idPersona, fecha, hNew, db, excl = null) {
  const lim = getLim(db);
  let q = `SELECT COALESCE(SUM(dl.horas),0) t FROM diario_linea dl
           JOIN diario d ON dl.id_diario=d.id_diario
           WHERE dl.id_persona=? AND d.fecha=?`;
  const p = [idPersona, fs(fecha)];
  if (excl) {
    q += ' AND dl.id_dl!=?';
    p.push(excl);
  }
  const tot = db.prepare(q).get(...p).t;
  if (tot + hNew > lim) {
    const pr = db
      .prepare("SELECT nombre||' '||apellido1 n FROM persona WHERE id_persona=?")
      .get(idPersona);
    throw new ValidationError(
      `${pr ? pr.n : '?'} ya acumula ${hhmm(tot)} ese día. ` +
        `Añadir ${hhmm(hNew)} supera el límite de ${hhmm(lim)} h/día.`
    );
  }
}

/** Lanza Error si el mensual de esa obra/empresa/mes está cerrado. */
function chkMesCerrado(idObra, idEmpresa, fecha, db) {
  const m = db
    .prepare(
      `SELECT m.estado, o.nombre ob, e.nombre em FROM mensual m
       JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_obra=? AND m.id_empresa=? AND m.mes=?`
    )
    .get(idObra, idEmpresa, mes(fecha));
  if (m && m.estado === 'cerrado') {
    throw new ValidationError(`Mes ${mes(fecha)} para '${m.ob}'/'${m.em}' está CERRADO.`);
  }
}

/** Devuelve el id_rango activo de una persona en una fecha dada. */
function getRangoActivo(idPersona, fecha, db) {
  const f = fs(fecha);
  const r = db
    .prepare(
      `SELECT id_rango FROM persona_rango
       WHERE id_persona=? AND fecha_inicio<=? AND (fecha_fin IS NULL OR fecha_fin>=?)
       ORDER BY fecha_inicio DESC LIMIT 1`
    )
    .get(idPersona, f, f);
  if (r) return r.id_rango;
  const se = db.prepare("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").get();
  return se ? se.id_rango : null;
}

module.exports = { getLim, chkHoras, chkMesCerrado, getRangoActivo };
