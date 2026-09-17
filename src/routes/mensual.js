'use strict';
/**
 * routes/mensual.js — cierre mensual: creación/apertura, vista (con snapshot
 * o cálculo en vivo), cierre, reapertura y exportación CSV.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { fs: fsDate, hhmm, norm } = require('../services/fechas');
const { calcularFilasMensual, chkObraActiva } = require('../services/negocio');
const { generarMensualExcel } = require('../services/excel');
const { logEvent } = require('../services/logs');
const { ValidationError } = require('../utils');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const mens = conn
    .prepare(
      `SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
       FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       ORDER BY m.mes DESC, o.nombre, e.nombre`
    )
    .all();
  const obras = conn.prepare("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").all();
  const emps = conn.prepare("SELECT * FROM empresa WHERE estado='activa' ORDER BY nombre").all();
  const hoyMes = fsDate(new Date()).slice(0, 7);
  renderPage(req, res, 'mensual/sel', { title: 'Mensuales', active: 'mas', mens, obras, emps, hoy_mes: hoyMes });
});

router.post('/nuevo', (req, res) => {
  const conn = db.getDb();
  const io = parseInt(req.body.id_obra, 10) || null;
  const ie = parseInt(req.body.id_empresa, 10) || null;
  const m = (req.body.mes || '').trim();
  if (!io || !ie || !m) {
    req.flash('Todos los campos son obligatorios.', 'error');
    return res.redirect('/mensual/');
  }
  try {
    chkObraActiva(conn, io);
    conn.prepare('INSERT OR IGNORE INTO mensual(id_obra,id_empresa,mes) VALUES(?,?,?)').run(io, ie, m);
    const row = conn
      .prepare('SELECT id_mensual FROM mensual WHERE id_obra=? AND id_empresa=? AND mes=?')
      .get(io, ie, m);
    return res.redirect(`/mensual/${row.id_mensual}`);
  } catch (e) {
    if (e instanceof ValidationError) {
      req.flash(e.message, 'error');
    } else {
      req.flash(`Error: ${e.message}`, 'error');
    }
    return res.redirect('/mensual/');
  }
});

router.get('/:id_m(\\d+)', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT m.*, o.nombre nom_o, o.codigo cod_o, o.estado estado_obra, e.nombre nom_e
       FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }

  const year = parseInt(m.mes.slice(0, 4), 10);
  const month = parseInt(m.mes.slice(5, 7), 10);
  const days = new Date(year, month, 0).getDate();

  let filas;
  if (m.estado === 'cerrado') {
    const rows = conn
      .prepare(
        `SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=?
         ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c`
      )
      .all(idM);
    filas = rows.map((f) => {
      const diasArr = [];
      for (let i = 1; i <= days; i++) diasArr.push(f[`d${i}`]);
      return { ...f, dias_arr: diasArr };
    });
  } else {
    filas = calcularFilasMensual(conn, m.id_obra, m.id_empresa, m.mes).filas;
  }

  const diasNum = Array.from({ length: days }, (_, i) => i + 1);
  renderPage(req, res, 'mensual/ver', { title: `Mensual ${m.mes}`, active: 'mas', m, filas, days, hhmm, dias_num: diasNum });
});

router.post('/:id_m/cerrar', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT mn.*, o.nombre nom_o, e.nombre nom_e FROM mensual mn
       JOIN obra o ON mn.id_obra=o.id_obra JOIN empresa e ON mn.id_empresa=e.id_empresa
       WHERE mn.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }
  if (m.estado === 'cerrado') {
    req.flash('Este mes ya está cerrado.', 'warning');
    return res.redirect(`/mensual/${idM}`);
  }
  const { filas } = calcularFilasMensual(conn, m.id_obra, m.id_empresa, m.mes);
  const dcols = Array.from({ length: 31 }, (_, i) => `d${i + 1}`).join(',');
  const dmarks = Array.from({ length: 31 }, () => '?').join(',');
  const insertSql = `INSERT INTO mensual_persona
      (id_mensual,id_persona,id_rango,id_empresa,nom_c,ap1_c,ap2_c,dni_c,
       rango_cache,empresa_cache,es_subcontrata,${dcols},total_mes)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,${dmarks},?)`;
  const insertStmt = conn.prepare(insertSql);
  const tx = conn.transaction(() => {
    conn.prepare('DELETE FROM mensual_persona WHERE id_mensual=?').run(idM);
    for (const g of filas) {
      const diasVals = [];
      for (let i = 0; i < 31; i++) diasVals.push(i < g.dias_arr.length ? g.dias_arr[i] : null);
      insertStmt.run(
        idM,
        g.id_persona,
        g.id_rango,
        g.id_empresa,
        g.nom_c,
        g.ap1_c,
        g.ap2_c,
        g.dni_c,
        g.rango_cache,
        g.empresa_cache,
        g.es_subcontrata,
        ...diasVals,
        g.total_mes
      );
    }
    conn.prepare("UPDATE mensual SET estado='cerrado' WHERE id_mensual=?").run(idM);
  });
  tx();
  logEvent(
    conn,
    'CIERRE_MENSUAL',
    'mensual',
    idM,
    m.id_obra,
    { obra_nombre: m.nom_o, empresa_id: m.id_empresa, empresa_nombre: m.nom_e, mes: m.mes },
    req.flash
  );
  req.flash('Mes cerrado. Snapshot generado.', 'success');
  res.redirect(`/mensual/${idM}`);
});

router.post('/:id_m/reabrir', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT mn.*, o.nombre nom_o, e.nombre nom_e FROM mensual mn
       JOIN obra o ON mn.id_obra=o.id_obra JOIN empresa e ON mn.id_empresa=e.id_empresa
       WHERE mn.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }
  try {
    chkObraActiva(conn, m.id_obra);
  } catch (e) {
    req.flash(e.message, 'error');
    return res.redirect(`/mensual/${idM}`);
  }
  const motivo = (req.body.motivo || '').trim();
  const tx = conn.transaction(() => {
    conn.prepare("UPDATE mensual SET estado='abierto' WHERE id_mensual=?").run(idM);
    conn.prepare('DELETE FROM mensual_persona WHERE id_mensual=?').run(idM);
  });
  tx();
  const detalle = { obra_nombre: m.nom_o, empresa_id: m.id_empresa, empresa_nombre: m.nom_e, mes: m.mes };
  if (motivo) detalle.motivo = motivo;
  logEvent(conn, 'REABRIR_MENSUAL', 'mensual', idM, m.id_obra, detalle, req.flash);
  req.flash('Mes reabierto. El snapshot anterior fue eliminado.', 'warning');
  res.redirect(`/mensual/${idM}`);
});

function csvField(v) {
  const s = v === null || v === undefined ? '' : String(v);
  if (/[;"\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

router.get('/:id_m/csv', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
       FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }
  if (m.estado !== 'cerrado') {
    req.flash('Cierra el mes antes de exportar.', 'warning');
    return res.redirect(`/mensual/${idM}`);
  }

  const year = parseInt(m.mes.slice(0, 4), 10);
  const month = parseInt(m.mes.slice(5, 7), 10);
  const days = new Date(year, month, 0).getDate();

  const lines = [];
  const header = ['Empresa', 'Subcontrata', 'Rango', 'Apellidos', 'Nombre', 'DNI'];
  for (let i = 1; i <= days; i++) header.push(`Dia_${i}`);
  header.push('Total_mes');
  lines.push(header.map(csvField).join(';'));

  const rows = conn
    .prepare(
      `SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=?
       ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c`
    )
    .all(idM);
  for (const f of rows) {
    const fila = [f.empresa_cache, f.es_subcontrata ? 'Sí' : 'No', f.rango_cache, `${f.ap1_c} ${f.ap2_c}`, f.nom_c, f.dni_c];
    for (let i = 1; i <= days; i++) fila.push(hhmm(f[`d${i}`]));
    fila.push(hhmm(f.total_mes));
    lines.push(fila.map(csvField).join(';'));
  }

  const nombre = `mensual_${m.mes}_${norm(m.nom_o)}_${norm(m.nom_e)}.csv`;
  // BOM (utf-8-sig) para que Excel detecte UTF-8 y muestre bien los acentos.
  const body = `\uFEFF${lines.join('\r\n')}\r\n`;
  res.set('Content-Type', 'text/csv; charset=utf-8');
  res.set('Content-Disposition', `attachment; filename="${nombre}"`);
  res.send(body);
});

// EXPORTACIÓN A EXCEL ESTRUCTURADO (SPREADSHEET XML)
router.get('/:id_m/excel', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
       FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }

  const year = parseInt(m.mes.slice(0, 4), 10);
  const month = parseInt(m.mes.slice(5, 7), 10);
  const days = new Date(year, month, 0).getDate();

  let rows;
  if (m.estado === 'cerrado') {
    rows = conn
      .prepare(
        `SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=?
         ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c`
      )
      .all(idM);
  } else {
    // Si aún está abierto, calculamos al vuelo
    const filasCalc = calcularFilasMensual(conn, m.id_obra, m.id_empresa, m.mes, days);
    rows = filasCalc.map((f) => {
      const row = {
        empresa_cache: f.empresa_cache,
        es_subcontrata: f.es_subcontrata,
        rango_cache: f.rango_cache,
        ap1_c: f.ap1_c,
        ap2_c: f.ap2_c,
        nom_c: f.nom_c,
        dni_c: f.dni_c,
        total_mes: f.total_mes,
      };
      for (let i = 1; i <= days; i++) {
        row[`d${i}`] = f.dias_arr[i - 1];
      }
      return row;
    });
  }

  const xml = generarMensualExcel(m, rows, days);
  const nombre = `mensual_${m.mes}_${norm(m.nom_o)}_${norm(m.nom_e)}.xls`;
  res.set('Content-Type', 'application/vnd.ms-excel; charset=utf-8');
  res.set('Content-Disposition', `attachment; filename="${nombre}"`);
  res.send(xml);
});

// VISTA IMPRIMIBLE / PDF DE LIQUIDACIÓN MENSUAL CON FIRMAS
router.get('/:id_m/imprimir', (req, res) => {
  const conn = db.getDb();
  const idM = parseInt(req.params.id_m, 10);
  const m = conn
    .prepare(
      `SELECT m.*, o.nombre nom_o, o.codigo cod_o, e.nombre nom_e
       FROM mensual m JOIN obra o ON m.id_obra=o.id_obra JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_mensual=?`
    )
    .get(idM);
  if (!m) {
    req.flash('No encontrado.', 'error');
    return res.redirect('/mensual/');
  }

  const year = parseInt(m.mes.slice(0, 4), 10);
  const month = parseInt(m.mes.slice(5, 7), 10);
  const days = new Date(year, month, 0).getDate();

  let rows;
  if (m.estado === 'cerrado') {
    rows = conn
      .prepare(
        `SELECT mp.* FROM mensual_persona mp WHERE mp.id_mensual=?
         ORDER BY mp.es_subcontrata,mp.empresa_cache,mp.ap1_c,mp.nom_c`
      )
      .all(idM);
  } else {
    const filasCalc = calcularFilasMensual(conn, m.id_obra, m.id_empresa, m.mes, days);
    rows = filasCalc.map((f) => {
      const row = {
        empresa_cache: f.empresa_cache,
        es_subcontrata: f.es_subcontrata,
        rango_cache: f.rango_cache,
        ap1_c: f.ap1_c,
        ap2_c: f.ap2_c,
        nom_c: f.nom_c,
        dni_c: f.dni_c,
        total_mes: f.total_mes,
      };
      for (let i = 1; i <= days; i++) {
        row[`d${i}`] = f.dias_arr[i - 1];
      }
      return row;
    });
  }

  res.render('mensual/imprimir', {
    m,
    rows,
    days,
    hhmm,
  });
});

module.exports = router;
