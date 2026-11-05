'use strict';
/**
 * routes/index.js — página de inicio ('/'), equivalente a la ruta index()
 * de app.py enriquecida con información de estado de partes diarios y alertas CAE.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { hhmm, fs: fsDate } = require('../services/fechas');
const { getLim } = require('../services/horas');
const { renderPage } = require('../middleware/render');

router.get('/', (req, res) => {
  const conn = db.getDb();
  const hoy = fsDate(new Date());

  const obras = conn.prepare("SELECT * FROM obra WHERE estado='activa' AND deleted_at IS NULL ORDER BY nombre").all();

  const stmtDiario = conn.prepare(`
    SELECT d.id_diario, count(dl.id_dl) as personal_hoy, coalesce(sum(dl.horas), 0) as horas_hoy
    FROM diario d
    LEFT JOIN diario_linea dl ON d.id_diario = dl.id_diario
    WHERE d.id_obra = ? AND d.fecha = ?
    GROUP BY d.id_diario
  `);

  const obrasConEstado = obras.map((ob) => {
    const estadoDiario = stmtDiario.get(ob.id_obra, hoy);
    return {
      ...ob,
      diario_hoy: estadoDiario || null,
    };
  });

  // Alertas PRL / CAE (documentos vencidos o próximos a vencer en <= 15 días)
  const alertasCaeCount = conn.prepare(`
    SELECT (
      (SELECT count(*) FROM documentacion_persona dp 
       JOIN persona p ON dp.id_persona=p.id_persona 
       WHERE p.deleted_at IS NULL AND dp.fecha_caducidad IS NOT NULL AND dp.fecha_caducidad <= date(?, '+15 days'))
      +
      (SELECT count(*) FROM documentacion_empresa de 
       JOIN empresa e ON de.id_empresa=e.id_empresa 
       WHERE e.deleted_at IS NULL AND de.fecha_caducidad IS NOT NULL AND de.fecha_caducidad <= date(?, '+15 days'))
    ) as total
  `).get(hoy, hoy).total;

  const stats = [
    ['buildings', 'warning', conn.prepare("SELECT count(*) c FROM obra WHERE estado='activa' AND deleted_at IS NULL").get().c, 'Obras activas'],
    ['briefcase', 'info', conn.prepare("SELECT count(*) c FROM empresa WHERE estado='activa' AND deleted_at IS NULL").get().c, 'Empresas'],
    ['people', 'success', conn.prepare("SELECT count(*) c FROM persona WHERE estado='activa' AND deleted_at IS NULL").get().c, 'Personas activas'],
    ['clock', 'secondary', hhmm(getLim(conn)), 'Límite h/día'],
  ];

  renderPage(req, res, 'index', {
    title: 'Panel de Control',
    active: 'home',
    obras: obrasConEstado,
    stats,
    alertasCaeCount,
  });
});

module.exports = router;
