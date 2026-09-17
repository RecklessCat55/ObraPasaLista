'use strict';
/**
 * routes/diario.js — parte diario de obra: selector, vista/edición de
 * líneas, meteorología, arrastre del día anterior y asignación masiva.
 */
const express = require('express');
const router = express.Router();
const db = require('../db');
const { renderPage } = require('../middleware/render');
const { fs: fsDate, nf, hhmm } = require('../services/fechas');
const { chkHoras, chkMesCerrado, getRangoActivo } = require('../services/horas');
const { nombrePersona, getMetaEfectiva, chkObraActiva } = require('../services/negocio');
const { buscarDiarioParaArrastre } = require('../services/carryover');
const { obtenerSemaforoDiario, evaluarDocPersona } = require('../services/cae');
const { toJsonScript, ValidationError } = require('../utils');

const METEO = [
  ['soleado', 'soleado'],
  ['nublado', 'nublado'],
  ['lluvioso', 'lluvioso'],
  ['tormentoso', 'tormentoso'],
  ['nevando', 'nevando'],
  ['ventoso', 'ventoso'],
  ['niebla', 'niebla'],
];
const M_ICO = Object.fromEntries(METEO);

router.get('/', (req, res) => {
  const conn = db.getDb();
  const obras = conn.prepare("SELECT * FROM obra WHERE estado='activa' ORDER BY nombre").all();
  renderPage(req, res, 'diario/sel', { title: 'Diario', active: 'diario', obras });
});

router.get('/ir', (req, res) => {
  const idObra = parseInt(req.query.id_obra, 10) || null;
  const fecha = req.query.fecha || fsDate(new Date());
  if (!idObra) return res.redirect('/diario/');
  res.redirect(`/diario/${idObra}/${fecha}`);
});

function loadPersXEmp(conn, empsObra) {
  const persXEmp = {};
  for (const e of empsObra) {
    persXEmp[e.id_empresa] = conn
      .prepare("SELECT * FROM persona WHERE id_empresa=? AND estado='activa' ORDER BY apellido1,nombre")
      .all(e.id_empresa);
  }
  return persXEmp;
}

router.get('/:id_obra(\\d+)/:fecha_raw([0-9-]+)', (req, res) => {
  const conn = db.getDb();
  const idObra = parseInt(req.params.id_obra, 10);
  let fecha;
  try {
    fecha = fsDate(nf(req.params.fecha_raw));
  } catch (e) {
    req.flash('Fecha inválida.', 'error');
    return res.redirect('/diario/');
  }

  const obra = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(idObra);
  if (!obra) {
    req.flash('Obra no encontrada.', 'error');
    return res.redirect('/diario/');
  }

  let d = conn.prepare('SELECT * FROM diario WHERE id_obra=? AND fecha=?').get(idObra, fecha);
  if (!d) {
    if (obra.estado === 'finalizada') {
      req.flash(
        `La obra "${obra.nombre}" está finalizada: no existe parte para ${fecha} y no se pueden crear nuevos.`,
        'error'
      );
      return res.redirect(`/obras/${idObra}/estado`);
    }
    conn.prepare('INSERT INTO diario(id_obra,fecha) VALUES(?,?)').run(idObra, fecha);
    d = conn.prepare('SELECT * FROM diario WHERE id_obra=? AND fecha=?').get(idObra, fecha);
  }

  const lineas = conn
    .prepare(
      `SELECT dl.*, p.nombre nom_p, p.apellido1 ap1, p.apellido2 ap2, p.dni,
              e.nombre nom_e, r.codigo cod_r, pa.codigo cod_pa, pa.descripcion desc_pa
       FROM diario_linea dl
       JOIN persona p  ON dl.id_persona = p.id_persona
       JOIN empresa e  ON dl.id_empresa = e.id_empresa
       LEFT JOIN rango r        ON dl.id_rango   = r.id_rango
       LEFT JOIN partida_obra pa ON dl.id_partida = pa.id_partida
       WHERE dl.id_diario=?
       ORDER BY e.nombre, p.apellido1, p.nombre`
    )
    .all(d.id_diario);

  const empsObra = conn
    .prepare(
      `SELECT e.* FROM empresa e JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
       WHERE oe.id_obra=? ORDER BY e.nombre`
    )
    .all(idObra);

  const persXEmp = loadPersXEmp(conn, empsObra);
  const rangos = conn.prepare('SELECT * FROM rango ORDER BY codigo').all();
  const partidas = conn.prepare('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo').all(idObra);
  const ant = conn
    .prepare('SELECT fecha FROM diario WHERE id_obra=? AND fecha<? ORDER BY fecha DESC LIMIT 1')
    .get(idObra, fecha);
  const total = conn.prepare('SELECT COALESCE(SUM(horas),0) t FROM diario_linea WHERE id_diario=?').get(d.id_diario).t;

  renderPage(req, res, 'diario/ver', {
    title: `Parte ${fecha}`,
    active: 'diario',
    obra,
    d,
    lineas,
    fecha,
    emps_obra: empsObra,
    pers_x_emp: persXEmp,
    rangos,
    partidas,
    ant,
    total,
    hhmm,
    m_ico: M_ICO,
    METEO,
    toJsonScript,
    semaforo_cae: obtenerSemaforoDiario(conn, d.id_diario),
  });
});

// VISTA MÓVIL TÁCTIL PARA ENCARGADOS (PASALISTA TOUCH)
router.get('/:id_d(\\d+)/movil', (req, res) => {
  const conn = db.getDb();
  const idD = parseInt(req.params.id_d, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idD);
  if (!d) {
    req.flash('Parte diario no encontrado.', 'error');
    return res.redirect('/diario/');
  }
  const obra = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(d.id_obra);
  const fecha = d.fecha;

  const lineas = conn
    .prepare(
      `SELECT dl.*, p.nombre nom_p, p.apellido1 ap1, p.apellido2 ap2, p.dni, p.oficio,
              e.nombre nom_e, r.codigo cod_r, pa.codigo cod_pa
       FROM diario_linea dl
       JOIN persona p  ON dl.id_persona = p.id_persona
       JOIN empresa e  ON dl.id_empresa = e.id_empresa
       LEFT JOIN rango r        ON dl.id_rango   = r.id_rango
       LEFT JOIN partida_obra pa ON dl.id_partida = pa.id_partida
       WHERE dl.id_diario=?
       ORDER BY e.nombre, p.apellido1, p.nombre`
    )
    .all(d.id_diario);

  const personasEnDiario = new Set(lineas.map((l) => l.id_persona));

  const empsObra = conn
    .prepare(
      `SELECT e.id_empresa, e.nombre nom_e
       FROM empresa e JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
       WHERE oe.id_obra=? AND e.estado='activa'
       ORDER BY e.nombre`
    )
    .all(d.id_obra);

  const idEmps = empsObra.map((e) => e.id_empresa);
  let otrasPersonas = [];
  if (idEmps.length > 0) {
    const placeholders = idEmps.map(() => '?').join(',');
    const candidatas = conn
      .prepare(
        `SELECT p.id_persona, p.nombre nom_p, p.apellido1 ap1, p.apellido2 ap2, p.dni, p.oficio,
                p.id_empresa, e.nombre nom_e
         FROM persona p
         JOIN empresa e ON p.id_empresa=e.id_empresa
         WHERE p.id_empresa IN (${placeholders}) AND p.estado='activa'
         ORDER BY e.nombre, p.apellido1, p.nombre`
      )
      .all(...idEmps);
    otrasPersonas = candidatas.filter((p) => !personasEnDiario.has(p.id_persona));
  }

  const partidas = conn.prepare('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo').all(d.id_obra);
  const total = conn.prepare('SELECT COALESCE(SUM(horas),0) t FROM diario_linea WHERE id_diario=?').get(d.id_diario).t;
  const semaforo = obtenerSemaforoDiario(conn, d.id_diario);

  for (const op of otrasPersonas) {
    if (!semaforo.personas[op.id_persona]) {
      semaforo.personas[op.id_persona] = evaluarDocPersona(conn, op.id_persona, fecha);
    }
  }

  renderPage(req, res, 'diario/movil', {
    title: `PasaLista Móvil — ${obra.nombre} (${fecha})`,
    active: 'diario',
    obra,
    d,
    lineas,
    otras_personas: otrasPersonas,
    partidas,
    total,
    hhmm,
    semaforo,
    fecha,
  });
});

// API RÁPIDA AJAX PARA GUARDAR HORAS CON UN SOLO TOQUE
router.post('/linea/api/guardar-horas', express.json(), (req, res) => {
  const conn = db.getDb();
  try {
    let { id_dl, id_diario, id_persona, id_empresa, horas, id_partida, asunto } = req.body;
    horas = parseFloat(horas);
    if (isNaN(horas) || horas < 0 || horas > 24) {
      return res.status(400).json({ error: 'Las horas deben estar entre 0 y 24.' });
    }

    if (id_dl) {
      id_dl = parseInt(id_dl, 10);
      const dl = conn.prepare('SELECT * FROM diario_linea WHERE id_dl=?').get(id_dl);
      if (!dl) return res.status(404).json({ error: 'Línea no encontrada.' });
      const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(dl.id_diario);
      chkMesCerrado(conn, d.id_obra, dl.id_empresa, d.fecha);
      chkHoras(conn, dl.id_persona, d.fecha, horas, id_dl);

      conn.prepare('UPDATE diario_linea SET horas=? WHERE id_dl=?').run(horas, id_dl);
      const total = conn.prepare('SELECT COALESCE(SUM(horas),0) t FROM diario_linea WHERE id_diario=?').get(dl.id_diario).t;
      return res.json({ success: true, id_dl, horas, total: hhmm(total), totalRaw: total });
    } else {
      id_diario = parseInt(id_diario, 10);
      id_persona = parseInt(id_persona, 10);
      id_empresa = parseInt(id_empresa, 10);
      const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(id_diario);
      if (!d) return res.status(404).json({ error: 'Diario no encontrado.' });
      chkObraActiva(conn, d.id_obra);
      chkMesCerrado(conn, d.id_obra, id_empresa, d.fecha);
      chkHoras(conn, id_persona, d.fecha, horas);

      const idR = getRangoActivo(conn, id_persona, d.fecha);
      const resIns = conn
        .prepare(
          `INSERT INTO diario_linea(id_diario, id_empresa, id_persona, id_rango, id_partida, asunto, horas)
           VALUES(?,?,?,?,?,?,?)`
        )
        .run(id_diario, id_empresa, id_persona, idR, id_partida || null, asunto || '', horas);

      const total = conn.prepare('SELECT COALESCE(SUM(horas),0) t FROM diario_linea WHERE id_diario=?').get(id_diario).t;
      return res.json({ success: true, id_dl: resIns.lastInsertRowid, horas, total: hhmm(total), totalRaw: total });
    }
  } catch (err) {
    return res.status(400).json({ error: err.message });
  }
});

router.post('/:id_d/linea/nueva', (req, res) => {
  const conn = db.getDb();
  const idD = parseInt(req.params.id_d, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idD);
  if (!d) {
    req.flash('Diario no encontrado.', 'error');
    return res.redirect('/diario/');
  }
  try {
    chkObraActiva(conn, d.id_obra);
    const idEmp = parseInt(req.body.id_empresa, 10);
    const idPer = parseInt(req.body.id_persona, 10);
    const horas = parseFloat(req.body.horas || '0');
    const asunto = (req.body.asunto || '').trim();
    const idR = req.body.id_rango || getRangoActivo(idPer, d.fecha, conn);
    const idPa = req.body.id_partida || null;
    chkMesCerrado(d.id_obra, idEmp, d.fecha, conn);
    chkHoras(idPer, d.fecha, horas, conn);
    conn
      .prepare(
        'INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas) VALUES(?,?,?,?,?,?,?)'
      )
      .run(idD, idEmp, idPer, idR, idPa, asunto, horas);
    req.flash(`Guardado: ${hhmm(horas)} para ${nombrePersona(conn, idPer)}.`, 'success');
  } catch (e) {
    if (e instanceof ValidationError) {
      req.flash(e.message, 'error');
    } else {
      req.flash(`Error: ${e.message}`, 'error');
    }
  }
  res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
});

router.post('/linea/:id_dl/editar', (req, res) => {
  const conn = db.getDb();
  const idDl = parseInt(req.params.id_dl, 10);
  const dl = conn
    .prepare(
      'SELECT dl.*,d.fecha,d.id_obra FROM diario_linea dl JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_dl=?'
    )
    .get(idDl);
  if (dl) {
    try {
      chkObraActiva(conn, dl.id_obra);
      const h = req.body.horas !== undefined && req.body.horas !== '' ? parseFloat(req.body.horas) : dl.horas;
      const as_ = (req.body.asunto !== undefined ? req.body.asunto : dl.asunto || '').trim();
      const ir = req.body.id_rango || dl.id_rango;
      const ip = req.body.id_partida || dl.id_partida;
      chkMesCerrado(dl.id_obra, dl.id_empresa, dl.fecha, conn);
      chkHoras(dl.id_persona, dl.fecha, h, conn, idDl);
      conn
        .prepare('UPDATE diario_linea SET horas=?,asunto=?,id_rango=?,id_partida=? WHERE id_dl=?')
        .run(h, as_, ir, ip, idDl);
      req.flash(`Guardado: ${hhmm(h)} para ${nombrePersona(conn, dl.id_persona)}.`, 'success');
    } catch (e) {
      if (e instanceof ValidationError) {
        req.flash(e.message, 'error');
      } else {
        req.flash(`Error: ${e.message}`, 'error');
      }
    }
    return res.redirect(`/diario/${dl.id_obra}/${fsDate(dl.fecha)}`);
  }
  res.redirect('/diario/');
});

router.post('/linea/:id_dl/eliminar', (req, res) => {
  const conn = db.getDb();
  const idDl = parseInt(req.params.id_dl, 10);
  const dl = conn
    .prepare(
      'SELECT dl.*,d.fecha,d.id_obra FROM diario_linea dl JOIN diario d ON dl.id_diario=d.id_diario WHERE dl.id_dl=?'
    )
    .get(idDl);
  if (dl) {
    try {
      chkObraActiva(conn, dl.id_obra);
      chkMesCerrado(dl.id_obra, dl.id_empresa, dl.fecha, conn);
      const nom = nombrePersona(conn, dl.id_persona);
      const hor = dl.horas;
      conn.prepare('DELETE FROM diario_linea WHERE id_dl=?').run(idDl);
      req.flash(`Eliminado: ${hhmm(hor)} de ${nom}.`, 'success');
    } catch (e) {
      req.flash(e.message, 'error');
    }
    return res.redirect(`/diario/${dl.id_obra}/${fsDate(dl.fecha)}`);
  }
  res.redirect('/diario/');
});

router.post('/:id_d/meteo', (req, res) => {
  const conn = db.getDb();
  const idD = parseInt(req.params.id_d, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idD);
  if (!d) {
    req.flash('Diario no encontrado.', 'error');
    return res.redirect('/diario/');
  }
  try {
    chkObraActiva(conn, d.id_obra);
    const t = (req.body.meteo_temp_c || '').trim();
    const tVal = t ? parseFloat(t) : null;
    if (t && Number.isNaN(tVal)) throw new Error('Temperatura inválida.');
    conn
      .prepare('UPDATE diario SET meteo_estado=?,meteo_detalle=?,meteo_temp_c=? WHERE id_diario=?')
      .run(req.body.meteo_estado || 'soleado', (req.body.meteo_detalle || '').trim(), tVal, idD);
    req.flash('Meteorología actualizada.', 'success');
  } catch (e) {
    req.flash(e.message, 'error');
  }
  res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
});

router.post('/:id_d/arrastrar', (req, res) => {
  const conn = db.getDb();
  const idD = parseInt(req.params.id_d, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idD);
  if (!d) return res.redirect('/diario/');
  try {
    chkObraActiva(conn, d.id_obra);
  } catch (e) {
    req.flash(e.message, 'error');
    return res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
  }
  // Arrastre inteligente: busca el último día laborable (salta fines de semana)
  const ant = buscarDiarioParaArrastre(conn, d.id_obra, d.fecha);
  if (!ant) {
    req.flash('No hay parte anterior (laborable) para arrastrar.', 'warning');
    return res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
  }
  const lineas = conn.prepare('SELECT * FROM diario_linea WHERE id_diario=?').all(ant.id_diario);
  let ok = 0;
  const bloqueadas = [];
  for (const l of lineas) {
    const yaExiste = conn
      .prepare('SELECT 1 FROM diario_linea WHERE id_diario=? AND id_persona=? AND id_empresa=?')
      .get(idD, l.id_persona, l.id_empresa);
    if (yaExiste) continue;
    try {
      // Validar que la persona sigue activa
      const persona = conn.prepare('SELECT estado FROM persona WHERE id_persona=?').get(l.id_persona);
      if (!persona || persona.estado !== 'activa') {
        bloqueadas.push(`Persona #${l.id_persona}: inactiva o no encontrada.`);
        continue;
      }
      // Validar que la empresa sigue activa
      const empresa = conn.prepare('SELECT estado FROM empresa WHERE id_empresa=?').get(l.id_empresa);
      if (!empresa || empresa.estado !== 'activa') {
        bloqueadas.push(`Empresa #${l.id_empresa}: inactiva o no encontrada.`);
        continue;
      }
      chkMesCerrado(d.id_obra, l.id_empresa, d.fecha, conn);
      const ir = getRangoActivo(l.id_persona, d.fecha, conn);
      conn
        .prepare(
          'INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas) VALUES(?,?,?,?,?,?,0)'
        )
        .run(idD, l.id_empresa, l.id_persona, ir, l.id_partida, l.asunto);
      ok += 1;
    } catch (e) {
      bloqueadas.push(e.message);
    }
  }
  if (ok) req.flash(`${ok} línea(s) arrastradas desde ${ant.fecha}. Revisa y corrige las horas (están a 0).`, 'info');
  if (bloqueadas.length) {
    req.flash(`${bloqueadas.length} línea(s) no arrastradas: ${bloqueadas.join('; ')}`, 'warning');
  }
  if (!ok && !bloqueadas.length) req.flash('Sin líneas nuevas para arrastrar.', 'warning');
  res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
});

// -- ASIGNACIÓN MASIVA (4.3) --
router.get('/:id_diario/asignacion-masiva', (req, res) => {
  const conn = db.getDb();
  const idDiario = parseInt(req.params.id_diario, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idDiario);
  if (!d) {
    req.flash('Diario no encontrado.', 'error');
    return res.redirect('/diario/');
  }
  const obra = conn.prepare('SELECT * FROM obra WHERE id_obra=?').get(d.id_obra);
  try {
    chkObraActiva(conn, d.id_obra);
  } catch (e) {
    req.flash(e.message, 'error');
    return res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
  }
  const empsObra = conn
    .prepare(
      `SELECT e.* FROM empresa e JOIN obra_empresa oe ON e.id_empresa=oe.id_empresa
       WHERE oe.id_obra=? ORDER BY e.nombre`
    )
    .all(d.id_obra);
  const partidas = conn.prepare('SELECT * FROM partida_obra WHERE id_obra=? ORDER BY codigo').all(d.id_obra);
  const persXEmp = loadPersXEmp(conn, empsObra);
  renderPage(req, res, 'diario/asignacionMasiva', {
    title: 'Asignación masiva',
    active: 'diario',
    obra,
    d,
    emps_obra: empsObra,
    partidas,
    pers_x_emp: persXEmp,
  });
});

router.post('/:id_diario/asignacion-masiva', (req, res) => {
  const conn = db.getDb();
  const idDiario = parseInt(req.params.id_diario, 10);
  const d = conn.prepare('SELECT * FROM diario WHERE id_diario=?').get(idDiario);
  if (!d) {
    req.flash('Diario no encontrado.', 'error');
    return res.redirect('/diario/');
  }
  try {
    chkObraActiva(conn, d.id_obra);
  } catch (e) {
    req.flash(e.message, 'error');
    return res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
  }

  const idEmp = parseInt(req.body.id_empresa, 10) || null;
  let horas = parseFloat(req.body.horas || '0');
  if (Number.isNaN(horas)) horas = 0;
  const idPa = req.body.id_partida || null;
  const asunto = (req.body.asunto || '').trim();
  const idsPRaw = req.body.personas;
  const idsP = (Array.isArray(idsPRaw) ? idsPRaw : idsPRaw ? [idsPRaw] : []).map((v) => parseInt(v, 10));

  if (!idEmp || !idsP.length) {
    req.flash('Selecciona una empresa y al menos una persona.', 'error');
    return res.redirect(`/diario/${idDiario}/asignacion-masiva`);
  }

  const creadas = [];
  const bloqueadas = [];
  for (const idPer of idsP) {
    const per = conn.prepare('SELECT nombre,apellido1 FROM persona WHERE id_persona=?').get(idPer);
    const nom = per ? `${per.apellido1}, ${per.nombre}` : `persona #${idPer}`;
    try {
      const yaExiste = conn
        .prepare('SELECT 1 FROM diario_linea WHERE id_diario=? AND id_persona=? AND id_empresa=?')
        .get(idDiario, idPer, idEmp);
      if (yaExiste) {
        bloqueadas.push([nom, 'ya tiene una línea en este parte para esta empresa.']);
        continue;
      }
      chkMesCerrado(d.id_obra, idEmp, d.fecha, conn);
      chkHoras(idPer, d.fecha, horas, conn);
      const idR = getRangoActivo(idPer, d.fecha, conn);
      conn
        .prepare(
          `INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,id_partida,asunto,horas)
           VALUES(?,?,?,?,?,?,?)`
        )
        .run(idDiario, idEmp, idPer, idR, idPa, asunto, horas);
      creadas.push(nom);
      const { valor: meta, origen } = getMetaEfectiva(conn, idPer, idEmp, d.id_obra);
      if (horas < meta) {
        req.flash(
          `${nom}: ${hhmm(horas)} asignadas, por debajo de su meta efectiva de ${hhmm(meta)} (origen: ${origen}).`,
          'warning'
        );
      }
    } catch (e) {
      bloqueadas.push([nom, e.message]);
    }
  }
  if (creadas.length) req.flash(`${creadas.length} línea(s) creadas para: ${creadas.join(', ')}.`, 'success');
  if (bloqueadas.length) {
    const detalle = bloqueadas.map(([n, m]) => `${n}: ${m}`).join('; ');
    req.flash(`${bloqueadas.length} línea(s) no creadas — ${detalle}`, 'warning');
  }
  res.redirect(`/diario/${d.id_obra}/${fsDate(d.fecha)}`);
});

module.exports = router;
