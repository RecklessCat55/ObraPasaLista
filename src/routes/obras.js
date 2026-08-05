'use strict';
/**
 * routes/obras.js — CRUD de obras, empresas/partidas participantes, y
 * estado de obra (activa/finalizada) con auditoría.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { mensualesAbiertos } = require('../services/negocio');
const { archivarDocsPartida } = require('../services/docs');
const { logEvent } = require('../services/logs');
const { ValidationError } = require('../utils');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const obras = conn.prepare('SELECT * FROM obra ORDER BY estado, nombre').all();
  renderPage(req, res, 'obras/index', { title: 'Obras', active: 'mas', obras });
});

router.get('/nueva', (req, res) => {
  renderPage(req, res, 'obras/form', { title: 'Nueva obra', active: 'mas', ob: null, oes: [], emps_disp: [], parts: [] });
});

router.post('/nueva', (req, res) => {
  const conn = db.getDb();
  const cod = (req.body.codigo || '').trim();
  const nom = (req.body.nombre || '').trim();
  if (!cod || !nom) {
    req.flash('Código y nombre obligatorios.', 'error');
  } else {
    try {
      conn.prepare('INSERT INTO obra(codigo,nombre) VALUES(?,?)').run(cod, nom);
      req.flash(`Obra "${nom}" creada.`, 'success');
      return res.redirect('/obras/');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  renderPage(req, res, 'obras/form', { title: 'Nueva obra', active: 'mas', ob: null, oes: [], emps_disp: [], parts: [] });
});

function loadObraFormExtras(conn, id) {
  const oes = conn
    .prepare(
      `SELECT oe.id_oe,e.nombre,e.id_empresa FROM obra_empresa oe
       JOIN empresa e ON oe.id_empresa=e.id_empresa WHERE oe.id_obra=?`
    )
    .all(id);
  const disp = conn
    .prepare(
      `SELECT * FROM empresa WHERE estado='activa' AND id_empresa NOT IN
       (SELECT id_empresa FROM obra_empresa WHERE id_obra=?) ORDER BY nombre`
    )
    .all(id);
  const parts = conn.prepare('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo').all(id);
  return { oes, disp, parts };
}

router.get('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const ob = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(id);
  if (!ob) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/obras/');
  }
  const { oes, disp, parts } = loadObraFormExtras(conn, id);
  renderPage(req, res, 'obras/form', { title: 'Editar obra', active: 'mas', ob, oes, emps_disp: disp, parts });
});

router.post('/:id/editar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  const ob = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(id);
  if (!ob) {
    req.flash('No encontrada.', 'error');
    return res.redirect('/obras/');
  }
  const nom = (req.body.nombre || '').trim();
  const cod = (req.body.codigo || '').trim();
  const metaRaw = (req.body.meta_horas_dia || '').trim();
  try {
    let meta;
    const metaActualStr = ob.meta_horas_dia !== null && ob.meta_horas_dia !== undefined ? String(ob.meta_horas_dia) : '';
    if (ob.estado === 'finalizada' && metaRaw !== metaActualStr) {
      // las metas de una obra finalizada son de solo lectura (4.4)
      req.flash('La obra está finalizada: la meta de horas no es editable.', 'warning');
      meta = ob.meta_horas_dia;
    } else {
      meta = metaRaw ? parseFloat(metaRaw) : null;
      if (metaRaw && Number.isNaN(meta)) throw new ValidationError('Meta de horas inválida.');
    }
    conn.prepare('UPDATE obra SET nombre=?,codigo=?,meta_horas_dia=? WHERE id_obra=?').run(nom, cod, meta, id);
    req.flash(`Obra "${nom}" actualizada.`, 'success');
    return res.redirect('/obras/');
  } catch (e) {
    if (e instanceof ValidationError) {
      req.flash(e.message, 'error');
    } else {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  const { oes, disp, parts } = loadObraFormExtras(conn, id);
  renderPage(req, res, 'obras/form', { title: 'Editar obra', active: 'mas', ob, oes, emps_disp: disp, parts });
});

router.post('/:id_obra/add-empresa', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const ie = parseInt(req.body.id_empresa, 10) || null;
  if (ie) {
    try {
      conn.prepare('INSERT OR IGNORE INTO obra_empresa(id_obra,id_empresa) VALUES(?,?)').run(idObra, ie);
      req.flash('Empresa añadida.', 'success');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect(`/obras/${idObra}/editar`);
});

router.post('/:id_obra/rem-empresa/:id_oe', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  conn.prepare('DELETE FROM obra_empresa WHERE id_oe=?').run(parseInt(req.params.id_oe, 10));
  req.flash('Empresa eliminada de la obra.', 'success');
  res.redirect(`/obras/${idObra}/editar`);
});

router.post('/:id_obra/add-partida', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const cod = (req.body.codigo || '').trim();
  const desc = (req.body.descripcion || '').trim();
  if (!cod) {
    req.flash('Código obligatorio.', 'error');
  } else {
    try {
      conn.prepare('INSERT INTO partida_obra(id_obra,codigo,descripcion) VALUES(?,?,?)').run(idObra, cod, desc);
      req.flash(`Partida ${cod} añadida.`, 'success');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect(`/obras/${idObra}/editar`);
});

router.post('/:id_obra/rem-partida/:id_p', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const idP = parseInt(req.params.id_p, 10);
  const part = conn.prepare('SELECT * FROM partida_obra WHERE id_partida=?').get(idP);
  try {
    const nDocs = part ? archivarDocsPartida(conn, idObra, idP) : 0;
    if (nDocs) {
      const obraNombre = conn.prepare('SELECT nombre FROM obra WHERE id_obra=?').get(idObra).nombre;
      logEvent(
        conn,
        'DOC_ARCHIVAR_PARTIDA',
        'partida',
        idP,
        idObra,
        { obra_nombre: obraNombre, partida_codigo: part.codigo, n_archivos: nDocs },
        req.flash
      );
    }
    conn.prepare('DELETE FROM partida_obra WHERE id_partida=?').run(idP);
    if (nDocs) {
      req.flash(`Partida eliminada. Se archivaron ${nDocs} archivo(s) de documentación asociados.`, 'success');
    } else {
      req.flash('Partida eliminada.', 'success');
    }
  } catch (e) {
    req.flash(`Error al eliminar la partida: ${e.message}`, 'error');
  }
  res.redirect(`/obras/${idObra}/editar`);
});

router.post('/:id/eliminar', (req, res) => {
  const conn = db.getDb();
  const id = parseInt(req.params.id, 10);
  try {
    const ob = conn.prepare('SELECT nombre FROM obra WHERE id_obra=?').get(id);
    conn.prepare('DELETE FROM obra WHERE id_obra=?').run(id);
    req.flash(`Obra "${ob ? ob.nombre : ''}" eliminada.`, 'success');
  } catch (e) {
    req.flash('No se puede eliminar: tiene registros vinculados.', 'error');
  }
  res.redirect('/obras/');
});

// -- ESTADO DE OBRA / CIERRE-REACTIVACIÓN (4.1, 5) --

router.post('/:id_obra/cerrar', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const ob = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!ob) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/obras/');
  }
  if (ob.estado === 'finalizada') {
    req.flash('La obra ya está finalizada.', 'warning');
    return res.redirect(`/obras/${idObra}/estado`);
  }
  const abiertos = mensualesAbiertos(conn, idObra);
  if (abiertos.length) {
    const lista = abiertos.map((m) => `${m.mes} (${m.nom_e})`).join(', ');
    req.flash(`No se puede finalizar: hay mensuales abiertos — ${lista}. Ciérralos primero.`, 'error');
    return res.redirect(`/obras/${idObra}/estado`);
  }
  conn.prepare("UPDATE obra SET estado='finalizada' WHERE id_obra=?").run(idObra);
  logEvent(conn, 'CERRAR_OBRA', 'obra', idObra, idObra, { obra_nombre: ob.nombre }, req.flash);
  req.flash(`Obra "${ob.nombre}" finalizada.`, 'success');
  res.redirect(`/obras/${idObra}/estado`);
});

router.post('/:id_obra/reactivar', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const ob = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!ob) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/obras/');
  }
  if (ob.estado !== 'finalizada') {
    req.flash('La obra no está finalizada.', 'warning');
    return res.redirect(`/obras/${idObra}/estado`);
  }
  conn.prepare("UPDATE obra SET estado='activa' WHERE id_obra=?").run(idObra);
  logEvent(conn, 'REACTIVAR_OBRA', 'obra', idObra, idObra, { obra_nombre: ob.nombre }, req.flash);
  req.flash(`Obra "${ob.nombre}" reactivada. Los mensuales siguen cerrados hasta que los reabras explícitamente.`, 'success');
  res.redirect(`/obras/${idObra}/estado`);
});

router.get('/:id_obra/estado', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  const ob = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!ob) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/obras/');
  }
  const mensuales = conn
    .prepare(
      `SELECT m.*, e.nombre nom_e FROM mensual m
       JOIN empresa e ON m.id_empresa=e.id_empresa
       WHERE m.id_obra=? ORDER BY m.mes DESC, e.nombre`
    )
    .all(idObra);
  const abiertos = mensuales.filter((m) => m.estado === 'abierto');
  const logs = conn
    .prepare('SELECT * FROM log_auditoria WHERE obra_id=? ORDER BY id_log DESC LIMIT 30')
    .all(idObra);
  const logsParsed = logs.map((l) => {
    let detalle = {};
    try {
      detalle = JSON.parse(l.detalle);
    } catch (e) {
      detalle = {};
    }
    return { ...l, detalle_obj: detalle };
  });
  const puedeFinalizar = ob.estado === 'activa' && abiertos.length === 0;
  renderPage(req, res, 'obras/estado', {
    title: `Estado ${ob.nombre}`,
    active: 'mas',
    ob,
    mensuales,
    abiertos,
    logs: logsParsed,
    puede_finalizar: puedeFinalizar,
  });
});

module.exports = router;
