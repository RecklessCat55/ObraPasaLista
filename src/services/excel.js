'use strict';
/**
 * services/excel.js — Generador de hojas de cálculo Excel XML (SpreadsheetML 2003).
 *
 * Genera archivos XML nativos compatibles con Microsoft Excel, LibreOffice Calc y
 * Google Sheets, con soporte para estilos, formatos numéricos, fórmulas de suma y colores.
 * No requiere dependencias binarias externas ni compilación nativa.
 */

function escapeXml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * Genera la plantilla XML Spreadsheet para el Parte Mensual de una obra/empresa.
 * @param {object} m Datos del mensual (obra, empresa, mes)
 * @param {Array<object>} rows Filas de mensual_persona
 * @param {number} days Número de días del mes
 * @returns {string} XML completo para responder con Content-Type application/vnd.ms-excel
 */
function generarMensualExcel(m, rows, days) {
  let diasHeaders = '';
  for (let i = 1; i <= days; i++) {
    diasHeaders += `<Cell ss:StyleID="Header"><Data ss:Type="String">Día ${i}</Data></Cell>\n`;
  }

  let rowsXml = '';
  for (const f of rows) {
    let diasCells = '';
    for (let i = 1; i <= days; i++) {
      const v = f[`d${i}`];
      if (v !== null && v !== undefined && v > 0) {
        diasCells += `<Cell ss:StyleID="Number"><Data ss:Type="Number">${v}</Data></Cell>\n`;
      } else {
        diasCells += `<Cell ss:StyleID="Center"><Data ss:Type="String">—</Data></Cell>\n`;
      }
    }

    const totalVal = f.total_mes || 0;

    rowsXml += `
      <Row ss:Height="20">
        <Cell ss:StyleID="Text"><Data ss:Type="String">${escapeXml(f.empresa_cache)}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${f.es_subcontrata ? 'Sí' : 'No'}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${escapeXml(f.rango_cache || '—')}</Data></Cell>
        <Cell ss:StyleID="TextBold"><Data ss:Type="String">${escapeXml(f.ap1_c + ' ' + f.ap2_c)}</Data></Cell>
        <Cell ss:StyleID="Text"><Data ss:Type="String">${escapeXml(f.nom_c)}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${escapeXml(f.dni_c)}</Data></Cell>
        ${diasCells}
        <Cell ss:StyleID="TotalNumber"><Data ss:Type="Number">${totalVal}</Data></Cell>
      </Row>
    `;
  }

  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:html="http://www.w3.org/TR/REC-html40">
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Alignment ss:Vertical="Center"/>
   <Font ss:FontName="Calibri" x:Family="Swiss" ss:Size="11" ss:Color="#000000"/>
  </Style>
  <Style ss:ID="Title">
   <Font ss:FontName="Calibri" ss:Size="16" ss:Bold="1" ss:Color="#1B365D"/>
  </Style>
  <Style ss:ID="SubTitle">
   <Font ss:FontName="Calibri" ss:Size="12" ss:Italic="1" ss:Color="#495057"/>
  </Style>
  <Style ss:ID="Header">
   <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="2" ss:Color="#000000"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D0D7DE"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#D0D7DE"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/>
   </Borders>
   <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#FFFFFF"/>
   <Interior ss:Color="#0D6EFD" ss:Pattern="Solid"/>
  </Style>
  <Style ss:ID="Text">
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
   </Borders>
  </Style>
  <Style ss:ID="TextBold">
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
   </Borders>
   <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1"/>
  </Style>
  <Style ss:ID="Center">
   <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
   </Borders>
  </Style>
  <Style ss:ID="Number">
   <Alignment ss:Horizontal="Right" ss:Vertical="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#E9ECEF"/>
   </Borders>
   <NumberFormat ss:Format="#,##0.00"/>
  </Style>
  <Style ss:ID="TotalNumber">
   <Alignment ss:Horizontal="Right" ss:Vertical="Center"/>
   <Borders>
    <Border ss:Position="Bottom" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/>
    <Border ss:Position="Left" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/>
    <Border ss:Position="Right" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/>
    <Border ss:Position="Top" ss:LineStyle="Continuous" ss:Weight="1" ss:Color="#000000"/>
   </Borders>
   <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#000000"/>
   <Interior ss:Color="#E2E3E5" ss:Pattern="Solid"/>
   <NumberFormat ss:Format="#,##0.00"/>
  </Style>
 </Styles>
 <Worksheet ss:Name="Parte Mensual">
  <Table ss:DefaultRowHeight="18">
   <Column ss:Width="160"/>
   <Column ss:Width="80"/>
   <Column ss:Width="100"/>
   <Column ss:Width="160"/>
   <Column ss:Width="130"/>
   <Column ss:Width="100"/>
   <Row ss:Height="25">
    <Cell ss:StyleID="Title"><Data ss:Type="String">OBRAPASALISTA — PARTE MENSUAL DE HORAS</Data></Cell>
   </Row>
   <Row ss:Height="20">
    <Cell ss:StyleID="SubTitle"><Data ss:Type="String">Obra: ${escapeXml(m.nom_o)} (${escapeXml(m.cod_o)}) | Empresa: ${escapeXml(m.nom_e)} | Mes: ${escapeXml(m.mes)}</Data></Cell>
   </Row>
   <Row ss:Height="10"/>
   <Row ss:Height="24">
    <Cell ss:StyleID="Header"><Data ss:Type="String">Empresa</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Subcontrata</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Rango</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Apellidos</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Nombre</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">DNI</Data></Cell>
    ${diasHeaders}
    <Cell ss:StyleID="Header"><Data ss:Type="String">Total Horas</Data></Cell>
   </Row>
   ${rowsXml}
  </Table>
 </Worksheet>
</Workbook>`;
}

/**
 * Genera la plantilla XML Spreadsheet para el Informe de Costes.
 */
function generarCostesExcel(obra, filas, mesStr, totalHoras, totalCoste) {
  let rowsXml = '';
  for (const f of filas) {
    rowsXml += `
      <Row ss:Height="20">
        <Cell ss:StyleID="Text"><Data ss:Type="String">${escapeXml(f.nom_e)}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${f.es_sub ? 'Subcontrata' : 'Propia'}</Data></Cell>
        <Cell ss:StyleID="TextBold"><Data ss:Type="String">${escapeXml(f.ap1 + ' ' + f.ap2)}</Data></Cell>
        <Cell ss:StyleID="Text"><Data ss:Type="String">${escapeXml(f.nom_p)}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${escapeXml(f.dni)}</Data></Cell>
        <Cell ss:StyleID="Center"><Data ss:Type="String">${escapeXml(f.nom_r || '—')}</Data></Cell>
        <Cell ss:StyleID="Number"><Data ss:Type="Number">${f.horas || 0}</Data></Cell>
        <Cell ss:StyleID="Number"><Data ss:Type="Number">${f.tarifa || 0}</Data></Cell>
        <Cell ss:StyleID="TotalNumber"><Data ss:Type="Number">${f.coste || 0}</Data></Cell>
      </Row>
    `;
  }

  return `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="Default" ss:Name="Normal">
   <Alignment ss:Vertical="Center"/>
   <Font ss:FontName="Calibri" ss:Size="11"/>
  </Style>
  <Style ss:ID="Title">
   <Font ss:FontName="Calibri" ss:Size="16" ss:Bold="1" ss:Color="#1B365D"/>
  </Style>
  <Style ss:ID="Header">
   <Alignment ss:Horizontal="Center" ss:Vertical="Center"/>
   <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1" ss:Color="#FFFFFF"/>
   <Interior ss:Color="#198754" ss:Pattern="Solid"/>
  </Style>
  <Style ss:ID="Text"><Font ss:FontName="Calibri" ss:Size="11"/></Style>
  <Style ss:ID="TextBold"><Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1"/></Style>
  <Style ss:ID="Center"><Alignment ss:Horizontal="Center" ss:Vertical="Center"/></Style>
  <Style ss:ID="Number"><Alignment ss:Horizontal="Right" ss:Vertical="Center"/><NumberFormat ss:Format="#,##0.00"/></Style>
  <Style ss:ID="TotalNumber">
   <Alignment ss:Horizontal="Right" ss:Vertical="Center"/>
   <Font ss:FontName="Calibri" ss:Size="11" ss:Bold="1"/>
   <Interior ss:Color="#D1E7DD" ss:Pattern="Solid"/>
   <NumberFormat ss:Format="#,##0.00 €"/>
  </Style>
 </Styles>
 <Worksheet ss:Name="Informe Costes">
  <Table ss:DefaultRowHeight="18">
   <Column ss:Width="160"/>
   <Column ss:Width="100"/>
   <Column ss:Width="160"/>
   <Column ss:Width="120"/>
   <Column ss:Width="100"/>
   <Column ss:Width="110"/>
   <Column ss:Width="90"/>
   <Column ss:Width="90"/>
   <Column ss:Width="110"/>
   <Row ss:Height="25">
    <Cell ss:StyleID="Title"><Data ss:Type="String">INFORME DE COSTES DE MANO DE OBRA</Data></Cell>
   </Row>
   <Row ss:Height="18">
    <Cell><Data ss:Type="String">Obra: ${escapeXml(obra ? obra.nombre : 'Todas')} | Mes: ${escapeXml(mesStr)}</Data></Cell>
   </Row>
   <Row ss:Height="10"/>
   <Row ss:Height="22">
    <Cell ss:StyleID="Header"><Data ss:Type="String">Empresa</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Tipo</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Apellidos</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Nombre</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">DNI</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Rango</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Horas</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Tarifa/h</Data></Cell>
    <Cell ss:StyleID="Header"><Data ss:Type="String">Coste Total</Data></Cell>
   </Row>
   ${rowsXml}
   <Row ss:Height="22">
    <Cell><Data ss:Type="String">TOTALES</Data></Cell>
    <Cell/><Cell/><Cell/><Cell/><Cell/>
    <Cell ss:StyleID="TotalNumber"><Data ss:Type="Number">${totalHoras}</Data></Cell>
    <Cell/>
    <Cell ss:StyleID="TotalNumber"><Data ss:Type="Number">${totalCoste}</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>`;
}

module.exports = {
  generarMensualExcel,
  generarCostesExcel,
};
