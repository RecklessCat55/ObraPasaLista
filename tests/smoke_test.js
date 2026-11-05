#!/usr/bin/env node
'use strict';
/**
 * tests/smoke_test.js — smoke test funcional del backend Node.js.
 *
 * Ejecuta los módulos de servicio y la capa de datos directamente (sin
 * levantar el servidor HTTP) contra una BD de pruebas en memoria.
 * Cubre: esquema, migraciones, servicios de horas, carryover inteligente,
 * negocio (metas, costes, estado de obra) y backup/integridad.
 *
 * Uso:
 *   npm test
 *   node tests/smoke_test.js
 */
const assert = require('assert');
const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');

// --- Bootstrap: crear BD en memoria con el esquema completo ---
const {
  SCHEMA,
  RANGOS_DEFAULT,
  MIGRATION_V12,
  MIGRATION_V13,
  MIGRATION_V14,
  MIGRATION_V15,
  seedRangos,
  aplicarMigracion,
} = require('../src/db');

const db = new Database(':memory:');
db.pragma('foreign_keys = ON');
db.pragma('journal_mode = WAL');
db.exec(SCHEMA);
aplicarMigracion(db, MIGRATION_V12, 'v1.2 (test)');
aplicarMigracion(db, MIGRATION_V13, 'v1.3 (test)');
aplicarMigracion(db, MIGRATION_V14, 'v1.4 (test)');
aplicarMigracion(db, MIGRATION_V15, 'v1.5 (test)');
db.prepare('INSERT OR IGNORE INTO config(id_config,limite_horas_dia,umbral_desajuste_meta) VALUES(1,24.0,2.0)').run();
seedRangos(db);

let passed = 0;
let failed = 0;

function test(label, fn) {
  try {
    fn();
    console.log(`  ✓ ${label}`);
    passed++;
  } catch (e) {
    console.error(`  ✗ ${label}`);
    console.error(`    ${e.message}`);
    failed++;
  }
}

// ======================== 1. ESQUEMA ========================
console.log('\n1. Esquema y datos base');

test('La tabla empresa existe', () => {
  db.prepare('SELECT count(*) FROM empresa').get();
});

test('La tabla log_auditoria existe con obra_id', () => {
  const info = db.prepare("PRAGMA table_info('log_auditoria')").all();
  assert(info.some((c) => c.name === 'obra_id'), 'Falta columna obra_id');
});

test('Rangos por defecto sembrados', () => {
  const n = db.prepare('SELECT count(*) c FROM rango').get().c;
  assert(n >= RANGOS_DEFAULT.length, `Esperados >= ${RANGOS_DEFAULT.length}, obtenidos ${n}`);
});

test('Tabla config_festivo existe', () => {
  db.prepare('SELECT count(*) FROM config_festivo').get();
});

test('Columnas deleted_at existen en persona, empresa y obra', () => {
  const colsP = db.prepare("PRAGMA table_info('persona')").all();
  assert(colsP.some((c) => c.name === 'deleted_at'), 'Falta deleted_at en persona');
  const colsE = db.prepare("PRAGMA table_info('empresa')").all();
  assert(colsE.some((c) => c.name === 'deleted_at'), 'Falta deleted_at en empresa');
  const colsO = db.prepare("PRAGMA table_info('obra')").all();
  assert(colsO.some((c) => c.name === 'deleted_at'), 'Falta deleted_at en obra');
});

// ======================== 2. DATOS DE PRUEBA ========================
console.log('\n2. Datos de prueba');

test('Crear empresa, obra, persona y diario', () => {
  db.prepare("INSERT INTO empresa(nombre) VALUES('Test Corp')").run();
  db.prepare("INSERT INTO obra(codigo,nombre) VALUES('T01','Obra test')").run();
  db.prepare("INSERT INTO obra_empresa(id_obra,id_empresa) VALUES(1,1)").run();
  const sinEsp = db.prepare("SELECT id_rango FROM rango WHERE codigo='SIN_ESPECIFICAR'").get();
  db.prepare(
    "INSERT INTO persona(nombre,apellido1,dni,id_empresa) VALUES('Ana','García','12345678A',1)"
  ).run();
  db.prepare(
    "INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(1,?,?)"
  ).run(sinEsp.id_rango, '2020-01-01');
  // Diario del viernes 12 sept 2026
  db.prepare("INSERT INTO diario(id_obra,fecha) VALUES(1,'2026-09-11')").run();
  db.prepare(
    "INSERT INTO diario_linea(id_diario,id_empresa,id_persona,horas,asunto) VALUES(1,1,1,8,'Prueba viernes')"
  ).run();
});

// ======================== 3. SERVICIO DE HORAS ========================
console.log('\n3. Servicios de horas');

const { getLim, chkHoras, chkMesCerrado, getRangoActivo } = require('../src/services/horas');

test('getLim devuelve 24 por defecto', () => {
  assert.strictEqual(getLim(db), 24.0);
});

test('chkHoras no lanza con horas dentro del límite', () => {
  chkHoras(1, '2026-09-12', 8, db); // no debe lanzar
});

test('chkHoras lanza si se supera el límite', () => {
  assert.throws(() => chkHoras(1, '2026-09-11', 20, db), /supera/);
});

test('getRangoActivo devuelve SIN_ESPECIFICAR como fallback', () => {
  const r = getRangoActivo(1, '2026-09-12', db);
  assert(r !== null, 'Debería devolver un id_rango');
});

test('chkMesCerrado no lanza si no hay mensual', () => {
  chkMesCerrado(1, 1, '2026-09-12', db);
});

// ======================== 4. CARRYOVER INTELIGENTE ========================
console.log('\n4. Arrastre temporal inteligente');

const { ultimoDiaLaboral, buscarDiarioParaArrastre } = require('../src/services/carryover');

test('ultimoDiaLaboral salta fin de semana', () => {
  // Lunes 14 sept 2026 -> último laborable = viernes 11 sept 2026
  const result = ultimoDiaLaboral('2026-09-14');
  assert.strictEqual(result, '2026-09-11');
});

test('ultimoDiaLaboral salta festivos', () => {
  // Si viernes 11 es festivo, debe devolver jueves 10
  const result = ultimoDiaLaboral('2026-09-14', { holidaysList: ['2026-09-11'] });
  assert.strictEqual(result, '2026-09-10');
});

test('ultimoDiaLaboral devuelve null si no hay día laborable en rango', () => {
  const result = ultimoDiaLaboral('2026-09-14', { maxRetroceso: 2 });
  // Retrocede sab 13 y dom 12 — ambos fin de semana, no encuentra
  assert.strictEqual(result, null);
});

test('buscarDiarioParaArrastre encuentra el diario del viernes desde el lunes', () => {
  const d = buscarDiarioParaArrastre(db, 1, '2026-09-14');
  assert(d, 'Debería encontrar un diario');
  assert.strictEqual(d.fecha, '2026-09-11');
});

// ======================== 5. NEGOCIO ========================
console.log('\n5. Lógica de negocio');

const {
  getMetaEfectiva,
  chkObraActiva,
  mensualesAbiertos,
  precioEfectivoPersona,
} = require('../src/services/negocio');

test('getMetaEfectiva devuelve 8h por defecto', () => {
  const { valor, origen } = getMetaEfectiva(db, 1, 1, 1);
  assert.strictEqual(valor, 8.0);
  assert.strictEqual(origen, 'defecto');
});

test('getMetaEfectiva respeta persona > empresa > obra', () => {
  db.prepare('UPDATE persona SET meta_horas_dia=6.5 WHERE id_persona=1').run();
  const { valor, origen } = getMetaEfectiva(db, 1, 1, 1);
  assert.strictEqual(valor, 6.5);
  assert.strictEqual(origen, 'persona');
  db.prepare('UPDATE persona SET meta_horas_dia=NULL WHERE id_persona=1').run();
});

test('chkObraActiva no lanza para obra activa', () => {
  chkObraActiva(db, 1); // no debe lanzar
});

test('chkObraActiva lanza para obra finalizada', () => {
  db.prepare("UPDATE obra SET estado='finalizada' WHERE id_obra=1").run();
  assert.throws(() => chkObraActiva(db, 1), /finalizada/);
  db.prepare("UPDATE obra SET estado='activa' WHERE id_obra=1").run();
});

test('mensualesAbiertos devuelve lista vacía sin mensuales', () => {
  const r = mensualesAbiertos(db, 1);
  assert.strictEqual(r.length, 0);
});

test('precioEfectivoPersona devuelve null sin tarifas', () => {
  const r = precioEfectivoPersona(db, 1);
  assert.strictEqual(r, null);
});

// ======================== 6. AUDITORÍA ========================
console.log('\n6. Auditoría');

const { logEvent } = require('../src/services/logs');

test('logEvent inserta evento correctamente', () => {
  logEvent(db, 'TEST_EVENT', 'obra', 1, 1, { nota: 'smoke test' });
  const r = db.prepare("SELECT * FROM log_auditoria WHERE tipo_evento='TEST_EVENT'").get();
  assert(r, 'Debería existir el evento');
  const det = JSON.parse(r.detalle);
  assert.strictEqual(det.nota, 'smoke test');
  assert.strictEqual(det.obra_id, 1);
});

test('logEvent no lanza aunque falle internamente', () => {
  // Pasar un db roto no debe explotar
  logEvent({}, 'BROKEN', 'test', 0, 0, {});
});

// ======================== 7. FECHAS ========================
console.log('\n7. Servicios de fechas');

const { nf, mes, dia, hhmm, norm } = require('../src/services/fechas');

test('nf normaliza Date a YYYY-MM-DD', () => {
  const d = new Date(2026, 8, 17); // sept = 8 (0-indexed)
  assert.strictEqual(nf(d), '2026-09-17');
});

test('nf normaliza string YYYY-MM-DD', () => {
  assert.strictEqual(nf('2026-09-17'), '2026-09-17');
});

test('nf rechaza fechas inválidas', () => {
  assert.throws(() => nf('2026-13-45'), /no soportado/);
});

test('hhmm formatea correctamente', () => {
  assert.strictEqual(hhmm(8.5), '08:30');
  assert.strictEqual(hhmm(0), '00:00');
  assert.strictEqual(hhmm(null), '--');
});

test('norm normaliza texto', () => {
  assert.strictEqual(norm('Café con leche'), 'CAFE_CON_LECHE');
});

// ======================== 8. UTILS ========================
console.log('\n8. Utils');

const { secureFilename, toJsonScript, ValidationError } = require('../src/utils');

test('secureFilename limpia nombres peligrosos', () => {
  assert.strictEqual(secureFilename('../../etc/passwd'), 'etc_passwd');
  assert.strictEqual(secureFilename('mi archivo (1).pdf'), 'mi_archivo_1_.pdf');
  assert.strictEqual(secureFilename(''), '');
});

test('toJsonScript escapa caracteres peligrosos', () => {
  const r = toJsonScript('</script>');
  assert(!r.includes('</script>'), 'No debería contener </script> literal');
});

test('ValidationError es un Error con nombre correcto', () => {
  const e = new ValidationError('test');
  assert(e instanceof Error);
  assert.strictEqual(e.name, 'ValidationError');
  assert.strictEqual(e.message, 'test');
});

// ======================== 9. SOFT DELETES ========================
console.log('\n9. Soft Deletes (v1.4)');

test('Soft delete en persona preserva histórico y la excluye de listados activos', () => {
  // Crear persona de prueba para soft delete
  db.prepare("INSERT INTO persona(nombre,apellido1,dni,id_empresa) VALUES('Luis','Borrable','99999999Z',1)").run();
  const p = db.prepare("SELECT id_persona FROM persona WHERE dni='99999999Z'").get();
  assert(p, 'Persona creada');

  // Añadir línea en diario_linea
  db.prepare("INSERT INTO diario_linea(id_diario,id_empresa,id_persona,horas,asunto) VALUES(1,1,?,4,'Tarea previa')").run(p.id_persona);

  // Soft delete
  const now = new Date().toISOString();
  db.prepare("UPDATE persona SET deleted_at=?, estado='inactiva' WHERE id_persona=?").run(now, p.id_persona);

  // Consulta activa no la debe devolver
  const activa = db.prepare("SELECT * FROM persona WHERE id_persona=? AND deleted_at IS NULL").get(p.id_persona);
  assert.strictEqual(activa, undefined, 'No debe aparecer como activa');

  // Histórico en diario_linea sigue existiendo
  const linea = db.prepare("SELECT * FROM diario_linea WHERE id_persona=?").get(p.id_persona);
  assert(linea, 'El registro histórico debe conservarse intacto');
  assert.strictEqual(linea.horas, 4);

  // La persona existe con deleted_at para auditoría
  const soft = db.prepare("SELECT * FROM persona WHERE id_persona=?").get(p.id_persona);
  assert(soft.deleted_at !== null, 'deleted_at debe tener timestamp');
  assert.strictEqual(soft.estado, 'inactiva');
});

test('Soft delete en obra preserva diarios e histórico', () => {
  db.prepare("INSERT INTO obra(codigo,nombre) VALUES('OBS01','Obra soft delete')").run();
  const ob = db.prepare("SELECT id_obra FROM obra WHERE codigo='OBS01'").get();
  db.prepare("INSERT INTO diario(id_obra,fecha) VALUES(?,'2026-09-15')").run(ob.id_obra);

  // Soft delete
  const now = new Date().toISOString();
  db.prepare("UPDATE obra SET deleted_at=?, estado='finalizada' WHERE id_obra=?").run(now, ob.id_obra);

  // Filtrada en listados normales
  const visible = db.prepare("SELECT * FROM obra WHERE id_obra=? AND deleted_at IS NULL").get(ob.id_obra);
  assert.strictEqual(visible, undefined);

  // Accesible para informes por id directo
  const persistente = db.prepare("SELECT * FROM obra WHERE id_obra=?").get(ob.id_obra);
  assert(persistente, 'Debe persistir en BD');
  assert.strictEqual(persistente.estado, 'finalizada');
  assert(persistente.deleted_at !== null);

  // El diario sigue existiendo
  const d = db.prepare("SELECT * FROM diario WHERE id_obra=?").get(ob.id_obra);
  assert(d, 'El diario debe preservarse');
});

// ======================== 10. VALIDACIONES V1.4.1 ========================
console.log('\n10. Validaciones y correcciones v1.4.1');

test('chkMesCerradoObra bloquea si hay mensual cerrado', () => {
  const { chkMesCerradoObra } = require('../src/services/horas');
  db.prepare("INSERT INTO mensual(id_obra,id_empresa,mes,estado) VALUES(1,1,'2026-09','cerrado')").run();
  assert.throws(() => chkMesCerradoObra(1, '2026-09-12', db), /partes cerrados/);
});

test('informeCostes no duplica horas de subcontratas con mensual cerrado', () => {
  const { informeCostes } = require('../src/services/negocio');
  db.prepare("INSERT INTO empresa(nombre) VALUES('Subcontrata Test')").run();
  const subEmp = db.prepare("SELECT id_empresa FROM empresa WHERE nombre='Subcontrata Test'").get();
  db.prepare("INSERT INTO persona(nombre,apellido1,dni,id_empresa) VALUES('Beto','Lopez','87654321B',?)").run(subEmp.id_empresa);
  const pSub = db.prepare("SELECT id_persona FROM persona WHERE dni='87654321B'").get();
  db.prepare("INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio) VALUES(?,1,'2020-01-01')").run(pSub.id_persona);
  db.prepare("INSERT OR REPLACE INTO tarifa_rango(id_rango,precio_hora) VALUES(1,20.0)").run();
  db.prepare("INSERT INTO diario_linea(id_diario,id_empresa,id_persona,horas,asunto) VALUES(1,?,?,6,'Trabajo sub')").run(subEmp.id_empresa, pSub.id_persona);
  const dcols = Array.from({ length: 31 }, (_, i) => `d${i + 1}`).join(',');
  const dmarks = Array.from({ length: 31 }, () => '?').join(',');
  const dvals = new Array(31).fill(null);
  dvals[11] = 6;
  db.prepare(
    `INSERT INTO mensual_persona(id_mensual,id_persona,id_rango,id_empresa,nom_c,ap1_c,ap2_c,dni_c,rango_cache,empresa_cache,es_subcontrata,${dcols},total_mes)
     VALUES(1,?,1,?,'Beto','Lopez','','87654321B','Peón','Subcontrata Test',1,${dmarks},6)`
  ).run(pSub.id_persona, subEmp.id_empresa, ...dvals);
  const rep = informeCostes(db, 1, '2026-09');
  const horasBeto = rep.filas.filter((f) => f.nombre.includes('Lopez')).reduce((acc, f) => acc + f.horas, 0);
  assert.strictEqual(horasBeto, 6, `Beto debe sumar 6 horas, no estar duplicado (obtenido ${horasBeto})`);
});

test('Reactivación de persona dada de baja conserva ID e histórico', () => {
  const p = db.prepare("SELECT * FROM persona WHERE dni='99999999Z'").get();
  assert(p.deleted_at !== null);
  db.prepare("UPDATE persona SET deleted_at=NULL, estado='activa', nombre='Luis Reactivado' WHERE id_persona=?").run(p.id_persona);
  const reactivada = db.prepare("SELECT * FROM persona WHERE id_persona=? AND deleted_at IS NULL").get(p.id_persona);
  assert(reactivada, 'Persona debe ser visible como activa');
  assert.strictEqual(reactivada.nombre, 'Luis Reactivado');
  const historial = db.prepare("SELECT count(*) c FROM diario_linea WHERE id_persona=?").get(p.id_persona).c;
  assert(historial > 0, 'Histórico debe persistir');
});

test('Anonimización RGPD limpia también los datos en mensual_persona', () => {
  const pSub = db.prepare("SELECT id_persona FROM persona WHERE dni='87654321B'").get();
  db.prepare("UPDATE mensual_persona SET nom_c='ANON', ap1_c='ANON', ap2_c='', dni_c='ANON' WHERE id_persona=?").run(pSub.id_persona);
  const mp = db.prepare("SELECT * FROM mensual_persona WHERE id_persona=?").get(pSub.id_persona);
  assert.strictEqual(mp.nom_c, 'ANON');
  assert.strictEqual(mp.ap1_c, 'ANON');
  assert.strictEqual(mp.dni_c, 'ANON');
  assert.strictEqual(mp.total_mes, 6, 'Conserva el total de horas contable');
});


// ======================== 11. NUEVAS FUNCIONALIDADES (v1.5) ========================
console.log('\n11. Nuevas funcionalidades v1.5');

test('Columna descripcion existe en obra y notas en diario', () => {
  const oCol = db.prepare("SELECT descripcion FROM obra LIMIT 1").all();
  assert(oCol !== undefined, 'Columna descripcion debe existir en obra');
  const dCol = db.prepare("SELECT notas FROM diario LIMIT 1").all();
  assert(dCol !== undefined, 'Columna notas debe existir en diario');
});

test('Cálculo de costes aplica ascenso/cambio de rango a partir de la fecha de efecto', () => {
  const { informeCostes } = require('../src/services/negocio');
  // 1. Crear empresa y obra de prueba para costes
  const idEmp = db.prepare("INSERT INTO empresa(nombre) VALUES('Constructora Ascensos S.L.')").run().lastInsertRowid;
  const idOb = db.prepare("INSERT INTO obra(codigo,nombre,descripcion) VALUES('ASC-01','Edificio Ascenso','Edificio residencial de 10 plantas')").run().lastInsertRowid;
  db.prepare("INSERT INTO obra_empresa(id_obra,id_empresa) VALUES(?,?)").run(idOb, idEmp);

  // 2. Crear dos rangos con tarifas diferentes
  const idPeon = db.prepare("SELECT id_rango FROM rango WHERE codigo='PEON'").get().id_rango;
  const idOf1 = db.prepare("SELECT id_rango FROM rango WHERE codigo='OF1'").get().id_rango;
  
  db.prepare("INSERT OR REPLACE INTO tarifa_rango(id_rango,precio_hora) VALUES(?,10.0)").run(idPeon); // 10€/h
  db.prepare("INSERT OR REPLACE INTO tarifa_rango(id_rango,precio_hora) VALUES(?,20.0)").run(idOf1);  // 20€/h

  // 3. Crear trabajador y asignarle rango Peón desde el 1 de octubre
  const idPer = db.prepare(
    "INSERT INTO persona(nombre,apellido1,dni,id_empresa) VALUES('Carlos','Ascendido','11223344A',?)"
  ).run(idEmp).lastInsertRowid;

  db.prepare("INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio,fecha_fin) VALUES(?,?,'2026-10-01','2026-10-14')").run(idPer, idPeon);
  // Ascenso a Oficial 1ª el 15 de octubre
  db.prepare("INSERT INTO persona_rango(id_persona,id_rango,fecha_inicio,fecha_fin) VALUES(?,?,'2026-10-15',NULL)").run(idPer, idOf1);

  // 4. Crear partes diarios: 8h el día 5 (como Peón) y 8h el día 20 (como Oficial 1ª)
  const d1 = db.prepare("INSERT INTO diario(id_obra,fecha,notas) VALUES(?,'2026-10-05','Día normal de hormigonado')").run(idOb).lastInsertRowid;
  db.prepare("INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,horas) VALUES(?,?,?,?,8)").run(d1, idEmp, idPer, idPeon);

  const d2 = db.prepare("INSERT INTO diario(id_obra,fecha,notas) VALUES(?,'2026-10-20','Primera jornada tras ascenso')").run(idOb).lastInsertRowid;
  db.prepare("INSERT INTO diario_linea(id_diario,id_empresa,id_persona,id_rango,horas) VALUES(?,?,?,?,8)").run(d2, idEmp, idPer, idOf1);

  // 5. Calcular informe de costes para 2026-10
  const rCostes = informeCostes(db, idOb, '2026-10');
  
  assert.strictEqual(rCostes.totalHoras, 16, 'Total horas debe ser 16h');
  // Coste esperado: (8h * 10€) + (8h * 20€) = 80€ + 160€ = 240€
  assert.strictEqual(rCostes.totalCoste, 240, `Total coste debe ser 240€ exactamente, obtenido ${rCostes.totalCoste}€`);

  // Verificar coste por día en diasTabla
  const dia5 = rCostes.diasTabla.find(d => d.dia === 5);
  const dia20 = rCostes.diasTabla.find(d => d.dia === 20);
  assert.strictEqual(dia5.coste, 80, `Día 5 (Peón 10€/h) debe costar 80€, obtenido ${dia5.coste}€`);
  assert.strictEqual(dia20.coste, 160, `Día 20 (Oficial 20€/h) debe costar 160€, obtenido ${dia20.coste}€`);
});

test('Notas circunstanciales en diario persisten correctamente', () => {
  const d = db.prepare("SELECT * FROM diario WHERE notas LIKE '%hormigonado%'").get();
  assert(d, 'Debe existir diario con notas');
  assert.strictEqual(d.notas, 'Día normal de hormigonado');

  db.prepare("UPDATE diario SET notas='Lluvia torrencial, se para la obra a las 14:00' WHERE id_diario=?").run(d.id_diario);
  const dUpdated = db.prepare("SELECT notas FROM diario WHERE id_diario=?").get(d.id_diario);
  assert.strictEqual(dUpdated.notas, 'Lluvia torrencial, se para la obra a las 14:00');
});

test('Obra guarda y recupera la descripción', () => {
  const o = db.prepare("SELECT * FROM obra WHERE codigo='ASC-01'").get();
  assert(o, 'Obra debe existir');
  assert.strictEqual(o.descripcion, 'Edificio residencial de 10 plantas');
});

// ======================== RESUMEN ========================
console.log(`\n${'='.repeat(50)}`);
console.log(`RESULTADO: ${passed} pasados, ${failed} fallidos`);
if (failed > 0) {
  console.log('HAY FALLOS — revisar arriba.');
  process.exit(1);
} else {
  console.log('SMOKE TEST COMPLETO SIN ERRORES ✓');
}

db.close();
