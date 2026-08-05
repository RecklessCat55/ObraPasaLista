'use strict';
/**
 * routes/rangos.js — rangos profesionales (categorías laborales) y sus
 * tarifas por hora.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const rangos = conn
    .prepare(
      `SELECT r.*,
        (SELECT count(*) FROM persona_rango WHERE id_rango=r.id_rango) n_hist,
        (SELECT count(*) FROM diario_linea  WHERE id_rango=r.id_rango) n_diario,
        (SELECT count(*) FROM mensual_persona WHERE id_rango=r.id_rango) n_mensual,
        (SELECT precio_hora FROM tarifa_rango WHERE id_rango=r.id_rango) precio_hora
        FROM rango r ORDER BY r.codigo`
    )
    .all();
  renderPage(req, res, 'rangos/index', { title: 'Rangos', active: 'mas', rangos });
});

router.post('/nuevo', (req, res) => {
  const conn = db.getDb();
  const cod = (req.body.codigo || '').trim().toUpperCase();
  const nom = (req.body.nombre || '').trim();
  const desc = (req.body.descripcion || '').trim();
  if (!cod || !nom) {
    req.flash('Código y nombre obligatorios.', 'error');
  } else {
    try {
      conn.prepare('INSERT INTO rango(codigo,nombre,descripcion) VALUES(?,?,?)').run(cod, nom, desc);
      req.flash(`Rango ${cod} creado.`, 'success');
    } catch (e) {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect('/rangos/');
});

/**
 * Borrado seguro de un rango: nunca deja huérfanos ni rompe el histórico.
 * Se bloquea si el rango tiene cualquier uso (historial de personas, líneas
 * de diario o snapshots de mensual) o si es el rango de sistema
 * 'SIN_ESPECIFICAR' (usado como valor por defecto en toda la app).
 */
router.post('/:id/eliminar', (req, res) => {
  const conn = db.getDb();
  const idRango = parseInt(req.params.id, 10);
  const r = conn.prepare('SELECT * FROM rango WHERE id_rango=?').get(idRango);
  if (!r) {
    req.flash('Rango no encontrado.', 'error');
    return res.redirect('/rangos/');
  }
  if (r.codigo === 'SIN_ESPECIFICAR') {
    req.flash('"Sin especificar" es el rango por defecto del sistema y no se puede eliminar.', 'error');
    return res.redirect('/rangos/');
  }

  const nHist = conn.prepare('SELECT count(*) n FROM persona_rango WHERE id_rango=?').get(idRango).n;
  const nDiario = conn.prepare('SELECT count(*) n FROM diario_linea WHERE id_rango=?').get(idRango).n;
  const nMensual = conn.prepare('SELECT count(*) n FROM mensual_persona WHERE id_rango=?').get(idRango).n;
  if (nHist || nDiario || nMensual) {
    req.flash(
      `No se puede eliminar "${r.codigo}": está en uso (${nHist} en historial de personas, ` +
        `${nDiario} en líneas de diario, ${nMensual} en snapshots mensuales cerrados). ` +
        `Reasigna esos registros a otro rango antes de eliminarlo.`,
      'error'
    );
    return res.redirect('/rangos/');
  }

  try {
    const tx = conn.transaction(() => {
      conn.prepare('DELETE FROM tarifa_rango WHERE id_rango=?').run(idRango); // por claridad; ON DELETE CASCADE ya lo haría
      conn.prepare('DELETE FROM rango WHERE id_rango=?').run(idRango);
    });
    tx();
    req.flash(`Rango "${r.codigo}" eliminado.`, 'success');
  } catch (e) {
    // red de seguridad adicional por si algo lo referencia y no lo habíamos contado arriba
    req.flash(`No se puede eliminar "${r.codigo}": todavía hay registros que lo referencian.`, 'error');
  }
  res.redirect('/rangos/');
});

router.post('/:id/tarifa', (req, res) => {
  const conn = db.getDb();
  const idRango = parseInt(req.params.id, 10);
  const raw = (req.body.precio_hora || '').trim();
  try {
    if (!raw) {
      conn.prepare('DELETE FROM tarifa_rango WHERE id_rango=?').run(idRango);
      req.flash('Tarifa eliminada (sin precio definido para este rango).', 'success');
    } else {
      const precio = parseFloat(raw);
      if (Number.isNaN(precio) || precio < 0) throw new Error('Precio/hora inválido.');
      conn
        .prepare(
          `INSERT INTO tarifa_rango(id_rango,precio_hora) VALUES(?,?)
           ON CONFLICT(id_rango) DO UPDATE SET precio_hora=excluded.precio_hora`
        )
        .run(idRango, precio);
      req.flash('Tarifa actualizada.', 'success');
    }
  } catch (e) {
    req.flash('Precio/hora inválido.', 'error');
  }
  res.redirect('/rangos/');
});

module.exports = router;
