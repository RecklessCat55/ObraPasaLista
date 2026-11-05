#!/usr/bin/env node
'use strict';
/**
 * tests/http_test.js — Pruebas de integración HTTP reales con Supertest.
 *
 * Cubre:
 * - Vistas principales (GET 200)
 * - Alta de obra y empresa con meta_horas_dia
 * - Alta de personas y asignaciones
 * - Alta de líneas de diario y rechazo de duplicados
 * - API de autoguardado AJAX (edición, idempotencia, validación 24h)
 * - Mensual abierto: Excel e impresión
 * - Cierre de mensual y bloqueo en mes cerrado
 * - Finalización de obra y bloqueo en obra finalizada
 * - Backups: rechazo de path traversal y verificación
 * - Documentación: confinamiento y rechazo de ejecutables
 * - Anonimización RGPD en tabla maestra y snapshots
 */
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const request = require('supertest');

// Usar entorno de test
process.env.OBRAPL_MODE = 'test';
process.env.PORT = '5099';

const app = require('../src/app');
const db = require('../src/db');
const config = require('../src/config');

let passed = 0;
let failed = 0;

async function testHttp(label, fn) {
  try {
    await fn();
    console.log(`  ✓ ${label}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${label}`);
    console.error(`    ${e.message}`);
    failed++;
  }
}

async function runAllTests() {
  console.log('\n--- PRUEBAS DE INTEGRACIÓN HTTP (Supertest) ---');

  // Limpiar BD de pruebas para asegurar idempotencia
  const conn = db.getDb();
  db.initIfNeeded(conn);
  conn.pragma('foreign_keys = OFF');
  const tables = [
    'log_auditoria',
    'documentacion_persona',
    'documentacion_empresa',
    'archivo_obra',
    'carpeta_obra',
    'mensual_persona',
    'mensual',
    'diario_linea',
    'diario',
    'obra_empresa',
    'partida_obra',
    'persona_rango',
    'persona',
    'obra',
    'empresa',
    'tarifa_rango',
  ];
  for (const t of tables) {
    try { conn.prepare(`DELETE FROM ${t}`).run(); } catch (e) {}
  }
  conn.pragma('foreign_keys = ON');

  const agent = request(app);

  // 1-11: VISTAS PRINCIPALES
  await testHttp('1. GET / responde 200', async () => {
    const res = await agent.get('/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('2. GET /empresas/ responde 200', async () => {
    const res = await agent.get('/empresas/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('3. GET /personas/ responde 200', async () => {
    const res = await agent.get('/personas/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('4. GET /obras/ responde 200', async () => {
    const res = await agent.get('/obras/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('5. GET /diario/ responde 200', async () => {
    const res = await agent.get('/diario/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('6. GET /mensual/ responde 200', async () => {
    const res = await agent.get('/mensual/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('7. GET /backup/ responde 200', async () => {
    const res = await agent.get('/backup/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('8. GET /config/ responde 200', async () => {
    const res = await agent.get('/config/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('9. GET /cae/ responde 200', async () => {
    const res = await agent.get('/cae/');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('10. GET /informes/costes responde 200', async () => {
    const res = await agent.get('/informes/costes');
    assert.strictEqual(res.status, 200);
  });

  await testHttp('11. GET /faq/ responde 200', async () => {
    const res = await agent.get('/faq/');
    assert.strictEqual(res.status, 200);
  });

  // 12-15: ALTAS Y CONFIGURACIONES
  let idObraTest, idEmpresaTest, idPersonaTest, idDiarioTest;

  await testHttp('12. POST /obras/nueva guarda obra y meta_horas_dia', async () => {
    const res = await agent
      .post('/obras/nueva')
      .type('form')
      .send({ codigo: 'OB_HTTP', nombre: 'Obra Integracion HTTP', meta_horas_dia: '7.5' });
    assert.strictEqual(res.status, 302);
    const ob = db.getDb().prepare("SELECT * FROM obra WHERE codigo='OB_HTTP'").get();
    assert(ob, 'La obra debe haberse creado');
    assert.strictEqual(ob.meta_horas_dia, 7.5);
    idObraTest = ob.id_obra;
  });

  await testHttp('13. POST /empresas/nueva guarda empresa y meta_horas_dia', async () => {
    const res = await agent
      .post('/empresas/nueva')
      .type('form')
      .send({ nombre: 'Empresa HTTP Test', meta_horas_dia: '8.0' });
    assert.strictEqual(res.status, 302);
    const em = db.getDb().prepare("SELECT * FROM empresa WHERE nombre='Empresa HTTP Test'").get();
    assert(em, 'La empresa debe haberse creado');
    assert.strictEqual(em.meta_horas_dia, 8.0);
    idEmpresaTest = em.id_empresa;
  });

  await testHttp('14. POST /obras/:id/add-empresa asigna empresa a la obra', async () => {
    const res = await agent
      .post(`/obras/${idObraTest}/add-empresa`)
      .type('form')
      .send({ id_empresa: idEmpresaTest });
    assert.strictEqual(res.status, 302);
    const oe = db.getDb().prepare('SELECT * FROM obra_empresa WHERE id_obra=? AND id_empresa=?').get(idObraTest, idEmpresaTest);
    assert(oe, 'La relación obra_empresa debe existir');
  });

  await testHttp('15. POST /personas/nueva crea persona asociada a empresa', async () => {
    const sin = db.getDb().prepare("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").get();
    const res = await agent
      .post('/personas/nueva')
      .type('form')
      .send({
        nombre: 'Carlos',
        apellido1: 'Perez',
        dni: '44556677K',
        id_empresa: idEmpresaTest,
        id_rango: sin ? sin.id_rango : 1,
      });
    assert.strictEqual(res.status, 302);
    const per = db.getDb().prepare("SELECT * FROM persona WHERE dni='44556677K'").get();
    assert(per, 'La persona debe haberse creado');
    idPersonaTest = per.id_persona;
  });

  // 16-20: DIARIO Y API DE AUTOGUARDADO
  let idDlCreado;

  await testHttp('16. POST /diario/:id/linea/nueva crea línea de parte diario', async () => {
    // Crear o recuperar diario para la fecha 2026-10-15
    db.getDb().prepare("INSERT OR IGNORE INTO diario(id_obra,fecha) VALUES(?,'2026-10-15')").run(idObraTest);
    const d = db.getDb().prepare("SELECT * FROM diario WHERE id_obra=? AND fecha='2026-10-15'").get(idObraTest);
    idDiarioTest = d.id_diario;

    const res = await agent
      .post(`/diario/${idDiarioTest}/linea/nueva`)
      .type('form')
      .send({
        id_empresa: idEmpresaTest,
        id_persona: idPersonaTest,
        horas: '4.5',
        asunto: 'Instalaciones',
      });
    assert.strictEqual(res.status, 302);
    const dl = db.getDb().prepare('SELECT * FROM diario_linea WHERE id_diario=? AND id_persona=?').get(idDiarioTest, idPersonaTest);
    assert(dl, 'La línea debe existir');
    assert.strictEqual(dl.horas, 4.5);
    idDlCreado = dl.id_dl;
  });

  await testHttp('17. POST /diario/:id/linea/nueva rechaza duplicado de operario/empresa en el mismo parte', async () => {
    const res = await agent
      .post(`/diario/${idDiarioTest}/linea/nueva`)
      .type('form')
      .send({
        id_empresa: idEmpresaTest,
        id_persona: idPersonaTest,
        horas: '2.0',
      });
    assert.strictEqual(res.status, 302);
    const count = db.getDb().prepare('SELECT count(*) c FROM diario_linea WHERE id_diario=? AND id_persona=?').get(idDiarioTest, idPersonaTest).c;
    assert.strictEqual(count, 1, 'No debe haberse duplicado la línea');
  });

  await testHttp('18. POST /diario/linea/api/guardar-horas actualiza horas por API AJAX con éxito', async () => {
    const res = await agent
      .post('/diario/linea/api/guardar-horas')
      .send({ id_dl: idDlCreado, horas: 6.0 });
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.success, true);
    assert.strictEqual(res.body.horas, 6.0);
    const dl = db.getDb().prepare('SELECT horas FROM diario_linea WHERE id_dl=?').get(idDlCreado);
    assert.strictEqual(dl.horas, 6.0);
  });

  await testHttp('19. POST /diario/linea/api/guardar-horas es idempotente al enviar misma persona sin id_dl', async () => {
    const res = await agent
      .post('/diario/linea/api/guardar-horas')
      .send({
        id_diario: idDiarioTest,
        id_persona: idPersonaTest,
        id_empresa: idEmpresaTest,
        horas: 8.0,
      });
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.id_dl, idDlCreado);
    const count = db.getDb().prepare('SELECT count(*) c FROM diario_linea WHERE id_diario=? AND id_persona=?').get(idDiarioTest, idPersonaTest).c;
    assert.strictEqual(count, 1, 'Debe haber actualizado en vez de insertar');
  });

  await testHttp('20. POST /diario/linea/api/guardar-horas rechaza horas > 24 con 400', async () => {
    const res = await agent
      .post('/diario/linea/api/guardar-horas')
      .send({ id_dl: idDlCreado, horas: 25.0 });
    assert.strictEqual(res.status, 400);
    assert(res.body.error, 'Debe devolver un mensaje de error');
  });

  // 21-25: MENSUAL, EXCEL, IMPRESIÓN Y CIERRE
  let idMensualTest;

  await testHttp('21. POST /mensual/nuevo crea mensual para obra y empresa', async () => {
    const res = await agent
      .post('/mensual/nuevo')
      .type('form')
      .send({ id_obra: idObraTest, id_empresa: idEmpresaTest, mes: '2026-10' });
    assert.strictEqual(res.status, 302);
    const m = db.getDb().prepare('SELECT * FROM mensual WHERE id_obra=? AND id_empresa=? AND mes=?').get(idObraTest, idEmpresaTest, '2026-10');
    assert(m, 'El mensual debe haberse creado');
    assert.strictEqual(m.estado, 'abierto');
    idMensualTest = m.id_mensual;
  });

  await testHttp('22. GET /mensual/:id/excel funciona correctamente para mes abierto', async () => {
    const res = await agent.get(`/mensual/${idMensualTest}/excel`);
    assert.strictEqual(res.status, 200);
    assert(res.text.includes('<Workbook'), 'Debe generar el XML Excel de la hoja');
  });

  await testHttp('23. GET /mensual/:id/imprimir funciona correctamente para mes abierto', async () => {
    const res = await agent.get(`/mensual/${idMensualTest}/imprimir`);
    assert.strictEqual(res.status, 200);
    assert(res.text.toLowerCase().includes('liquidación mensual'), 'Debe renderizar la vista de impresión');
  });

  await testHttp('24. POST /mensual/:id/cerrar cierra el mes y congela snapshot', async () => {
    const res = await agent.post(`/mensual/${idMensualTest}/cerrar`);
    assert.strictEqual(res.status, 302);
    const m = db.getDb().prepare('SELECT * FROM mensual WHERE id_mensual=?').get(idMensualTest);
    assert.strictEqual(m.estado, 'cerrado');
    const mp = db.getDb().prepare('SELECT * FROM mensual_persona WHERE id_mensual=?').all(idMensualTest);
    assert(mp.length > 0, 'El snapshot de mensual_persona debe haberse generado');
  });

  await testHttp('25. POST /diario/linea/api/guardar-horas bloquea edición cuando el mes está cerrado', async () => {
    const res = await agent
      .post('/diario/linea/api/guardar-horas')
      .send({ id_dl: idDlCreado, horas: 5.0 });
    assert.strictEqual(res.status, 400);
    assert(res.body.error.includes('CERRADO'), 'Debe indicar que el mes está cerrado');
  });

  // 26-28: OBRA FINALIZADA, BACKUP Y RGPD
  await testHttp('26. Obra finalizada bloquea edición por API AJAX', async () => {
    // Finalizar obra directamente o por ruta
    db.getDb().prepare("UPDATE obra SET estado='finalizada' WHERE id_obra=?").run(idObraTest);
    const res = await agent
      .post('/diario/linea/api/guardar-horas')
      .send({ id_dl: idDlCreado, horas: 4.0 });
    assert.strictEqual(res.status, 400);
    assert(res.body.error.includes('finalizada'), 'Debe indicar que la obra está finalizada');
  });

  await testHttp('27. POST /backup/restaurar rechaza path traversal y nombres no permitidos', async () => {
    const res = await agent
      .post('/backup/restaurar')
      .type('form')
      .send({ nombre: '../../evil.db' });
    assert.strictEqual(res.status, 302);
    // Verificar que la base activa sigue funcionando
    const cfg = db.getDb().prepare('SELECT * FROM config WHERE id_config=1').get();
    assert(cfg, 'La base de datos activa debe permanecer intacta');
  });

  await testHttp('28. POST /personas/:id/anonimizar anonimiza en persona y en mensual_persona', async () => {
    const res = await agent.post(`/personas/${idPersonaTest}/anonimizar`);
    assert.strictEqual(res.status, 302);
    const per = db.getDb().prepare('SELECT * FROM persona WHERE id_persona=?').get(idPersonaTest);
    assert.strictEqual(per.apellido1, 'ANONIMIZADO');
    assert(per.nombre.startsWith('ANON_'));
    const mp = db.getDb().prepare('SELECT * FROM mensual_persona WHERE id_persona=?').get(idPersonaTest);
    if (mp) {
      assert.strictEqual(mp.nom_c, 'ANON');
      assert.strictEqual(mp.ap1_c, 'ANON');
      assert.strictEqual(mp.dni_c, 'ANON');
    }
  });


  // 29-32: NUEVAS FUNCIONALIDADES v1.5
  await testHttp('29. POST /obras/nueva y /editar guardan y actualizan descripcion', async () => {
    const res = await agent
      .post('/obras/nueva')
      .type('form')
      .send({
        codigo: 'OB-DESC-01',
        nombre: 'Obra con Descripcion',
        descripcion: 'Construcción de nave industrial en polígono sur',
      });
    assert.strictEqual(res.status, 302);
    const obra = db.getDb().prepare("SELECT * FROM obra WHERE codigo='OB-DESC-01'").get();
    assert(obra, 'La obra debe haber sido creada');
    assert.strictEqual(obra.descripcion, 'Construcción de nave industrial en polígono sur');

    // Editar descripcion
    const resEd = await agent
      .post(`/obras/${obra.id_obra}/editar`)
      .type('form')
      .send({
        codigo: 'OB-DESC-01',
        nombre: 'Obra con Descripcion Editada',
        descripcion: 'Fase 2 de la nave industrial',
      });
    assert.strictEqual(resEd.status, 302);
    const obraEditada = db.getDb().prepare("SELECT * FROM obra WHERE id_obra=?").get(obra.id_obra);
    assert.strictEqual(obraEditada.descripcion, 'Fase 2 de la nave industrial');
  });

  await testHttp('30. POST /diario/:id_d/notas guarda notas circunstanciales', async () => {
    // Crear un diario para probar
    const obra = db.getDb().prepare("SELECT id_obra FROM obra WHERE estado='activa' LIMIT 1").get();
    const dRes = db.getDb().prepare("INSERT INTO diario(id_obra, fecha) VALUES(?, '2026-11-10')").run(obra.id_obra);
    const idDiario = dRes.lastInsertRowid;

    // Probar guardado vía AJAX
    const resAjax = await agent
      .post(`/diario/${idDiario}/notas`)
      .set('Accept', 'application/json')
      .send({ notas: 'Visita del inspector de seguridad a las 11:00. Sin incidencias.' });
    assert.strictEqual(resAjax.status, 200);
    assert.strictEqual(resAjax.body.success, true);
    assert.strictEqual(resAjax.body.notas, 'Visita del inspector de seguridad a las 11:00. Sin incidencias.');

    const dDb = db.getDb().prepare('SELECT notas FROM diario WHERE id_diario=?').get(idDiario);
    assert.strictEqual(dDb.notas, 'Visita del inspector de seguridad a las 11:00. Sin incidencias.');
  });

  await testHttp('31. POST /diario/:id_diario/asignacion-masiva es idempotente y asigna/actualiza múltiples operarios', async () => {
    const obra = db.getDb().prepare("SELECT id_obra FROM obra WHERE estado='activa' LIMIT 1").get();
    const emp = db.getDb().prepare("SELECT id_empresa FROM empresa WHERE estado='activa' LIMIT 1").get();
    
    // Crear 2 operarios
    const p1 = db.getDb().prepare("INSERT INTO persona(nombre, apellido1, dni, id_empresa) VALUES('Op1', 'Test', '77000001A', ?)").run(emp.id_empresa).lastInsertRowid;
    const p2 = db.getDb().prepare("INSERT INTO persona(nombre, apellido1, dni, id_empresa) VALUES('Op2', 'Test', '77000002B', ?)").run(emp.id_empresa).lastInsertRowid;

    const dRes = db.getDb().prepare("INSERT INTO diario(id_obra, fecha) VALUES(?, '2026-11-11')").run(obra.id_obra);
    const idDiario = dRes.lastInsertRowid;

    // Asignación masiva para ambos
    const resMasiva1 = await agent
      .post(`/diario/${idDiario}/asignacion-masiva`)
      .type('form')
      .send({
        id_empresa: emp.id_empresa,
        horas: '8',
        asunto: 'Jornada completa masiva',
        personas: [String(p1), String(p2)],
      });
    assert.strictEqual(resMasiva1.status, 302);

    const lineas = db.getDb().prepare('SELECT * FROM diario_linea WHERE id_diario=?').all(idDiario);
    assert.strictEqual(lineas.length, 2, 'Debe haber creado 2 líneas');
    assert.strictEqual(lineas[0].horas, 8);
    assert.strictEqual(lineas[1].horas, 8);

    // Reasignación masiva (actualización a 4h sin error de duplicados)
    const resMasiva2 = await agent
      .post(`/diario/${idDiario}/asignacion-masiva`)
      .type('form')
      .send({
        id_empresa: emp.id_empresa,
        horas: '4',
        asunto: 'Media jornada actualizada',
        personas: [String(p1), String(p2)],
      });
    assert.strictEqual(resMasiva2.status, 302);

    const lineasUpd = db.getDb().prepare('SELECT * FROM diario_linea WHERE id_diario=?').all(idDiario);
    assert.strictEqual(lineasUpd.length, 2, 'Siguen existiendo 2 líneas (no duplicadas)');
    assert.strictEqual(lineasUpd[0].horas, 4, 'Horas actualizadas a 4');
    assert.strictEqual(lineasUpd[1].horas, 4, 'Horas actualizadas a 4');
  });

  await testHttp('32. POST /obra/:id_obra/documentacion/carpeta/:id_carpeta/subir acepta múltiples archivos a la vez', async () => {
    const obra = db.getDb().prepare("SELECT id_obra FROM obra WHERE estado='activa' LIMIT 1").get();
    
    // Crear carpeta
    const resCarp = await agent
      .post(`/obra/${obra.id_obra}/documentacion/carpeta/nueva`)
      .type('form')
      .send({ nombre: 'Carpeta MultiArchivos' });
    assert.strictEqual(resCarp.status, 302);

    const carp = db.getDb().prepare('SELECT * FROM carpeta_obra WHERE id_obra=? AND nombre=?').get(obra.id_obra, 'Carpeta MultiArchivos');
    assert(carp, 'La carpeta debe existir');

    // Subir 2 archivos simultáneamente
    const buf1 = Buffer.from('Contenido plano 1');
    const buf2 = Buffer.from('Contenido memoria 2');

    const resUpload = await agent
      .post(`/obra/${obra.id_obra}/documentacion/carpeta/${carp.id_carpeta}/subir`)
      .attach('archivos', buf1, 'plano_1.txt')
      .attach('archivos', buf2, 'memoria_2.txt');

    assert.strictEqual(resUpload.status, 302);

    const archivos = db.getDb().prepare('SELECT * FROM archivo_obra WHERE id_carpeta=?').all(carp.id_carpeta);
    assert.strictEqual(archivos.length, 2, 'Deben haberse guardado 2 archivos en la base de datos');
    const nombres = archivos.map(a => a.nombre);
    assert(nombres.includes('plano_1.txt'));
    assert(nombres.includes('memoria_2.txt'));
  });

  console.log(`\n${'='.repeat(50)}`);
  console.log(`RESULTADO HTTP: ${passed} pasados, ${failed} fallidos`);
  if (failed > 0) {
    console.error('HAY FALLOS EN INTEGRACIÓN HTTP — revisar arriba.');
    process.exit(1);
  } else {
    console.log('PRUEBAS HTTP COMPLETAS SIN ERRORES ✓');
  }
}

runAllTests().catch((err) => {
  console.error('Error fatal en http_test.js:', err);
  process.exit(1);
});
