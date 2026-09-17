'use strict';
/**
 * routes/informes.js — informes administrativos (por ahora, costes).
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { fs: fsDate, hhmm, norm } = require('../services/fechas');
const { informeCostes } = require('../services/negocio');
const { generarCostesExcel } = require('../services/excel');

router.get('/costes', (req, res) => {
  const conn = db.getDb();
  const obras = conn.prepare('SELECT * FROM obra ORDER BY nombre').all();
  const idObra = parseInt(req.query.id_obra, 10) || null;
  const mesStr = (req.query.mes || '').trim() || fsDate(new Date()).slice(0, 7);
  let filas = null;
  let diasTabla = null;
  let totalHoras = 0;
  let totalCoste = 0;
  let obraSel = null;
  if (idObra) {
    obraSel = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
    if (obraSel) {
      const r = informeCostes(conn, idObra, mesStr);
      filas = r.filas;
      diasTabla = r.diasTabla;
      totalHoras = r.totalHoras;
      totalCoste = r.totalCoste;
    }
  }
  renderPage(req, res, 'informes/costes', {
    title: 'Informe de costes',
    active: 'mas',
    obras,
    obra_sel: obraSel,
    mes_str: mesStr,
    filas,
    dias_tabla: diasTabla,
    total_horas: totalHoras,
    total_coste: totalCoste,
    hhmm,
  });
});

router.get('/costes/excel', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.query.id_obra, 10) || null;
  const mesStr = (req.query.mes || '').trim() || fsDate(new Date()).slice(0, 7);

  if (!idObra) {
    req.flash('Selecciona una obra para exportar costes.', 'warning');
    return res.redirect(`/informes/costes?mes=${mesStr}`);
  }

  const obraSel = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!obraSel) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/informes/costes');
  }

  const r = informeCostes(conn, idObra, mesStr);
  const xml = generarCostesExcel(obraSel, r.filas, mesStr, r.totalHoras, r.totalCoste);
  const nombre = `costes_${mesStr}_${norm(obraSel.nombre)}.xls`;
  res.set('Content-Type', 'application/vnd.ms-excel; charset=utf-8');
  res.set('Content-Disposition', `attachment; filename="${nombre}"`);
  res.send(xml);
});

module.exports = router;
