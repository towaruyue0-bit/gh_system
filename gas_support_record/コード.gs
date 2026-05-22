// ==========================================
// WebApp エントリーポイント
// ==========================================
function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
    .setTitle('支援記録入力')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

// ==========================================
// マスターデータ取得（クライアントから呼び出し）
// ==========================================
function getMasterData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // ---- 利用者マスター読み込み ----
  // シート列構成: [コード, 服薬, 喫煙]  ※名前でなく利用者コード（A01 など）
  var residents = [];
  var residentSheet = ss.getSheetByName('利用者マスター');
  if (residentSheet) {
    var resData = residentSheet.getDataRange().getValues();
    for (var i = 1; i < resData.length; i++) {
      var code = String(resData[i][0] || '').trim();
      if (!code) continue;
      residents.push({
        code:       code,
        medication: String(resData[i][1] || 'なし').trim(),
        smoking:    String(resData[i][2] || 'なし').trim()
      });
    }
  }

  // ---- 業務チェックマスター読み込み ----
  // シート列構成: [利用者コード, チェック項目]  ※名前でなくコード（A01 など）
  // 利用者1人につき複数行書ける
  var checkItems = {};
  var checkSheet = ss.getSheetByName('業務チェックマスター');
  if (checkSheet) {
    var checkData = checkSheet.getDataRange().getValues();
    for (var j = 1; j < checkData.length; j++) {
      var cCode = String(checkData[j][0] || '').trim();
      var cItem = String(checkData[j][1] || '').trim();
      if (!cCode || !cItem) continue;
      if (!checkItems[cCode]) checkItems[cCode] = [];
      checkItems[cCode].push(cItem);
    }
  }

  // ---- 定型文マスター読み込み ----
  // シート列構成: [利用者コード, 種別, 定型文]  ※名前でなくコード（A01 など）
  // 種別は「本人の様子」または「対応」
  // 利用者1人につき何行でも追加できる
  // 例:
  //   A01 | 本人の様子 | 自室にて過ごす
  //   A01 | 本人の様子 | 穏やかに過ごす
  //   A01 | 対応       | 声かけのみ
  var presets = {};
  var presetSheet = ss.getSheetByName('定型文マスター');
  if (presetSheet) {
    var presetData = presetSheet.getDataRange().getValues();
    for (var k = 1; k < presetData.length; k++) {
      var pCode = String(presetData[k][0] || '').trim();
      var pType = String(presetData[k][1] || '').trim();
      var pText = String(presetData[k][2] || '').trim();
      if (!pCode || !pType || !pText) continue;
      if (!presets[pCode])        presets[pCode] = {};
      if (!presets[pCode][pType]) presets[pCode][pType] = [];
      presets[pCode][pType].push(pText);
    }
  }

  return { residents: residents, checkItems: checkItems, presets: presets };
}

// ==========================================
// 支援記録を保存（クライアントから呼び出し）
// ==========================================
function saveRecords(data) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName('支援記録');

  // シートがなければ新規作成してヘッダーを設定
  if (!sheet) {
    sheet = ss.insertSheet('支援記録');
    var headers = [
      '送信日時', '日付', '勤務時間', '記録者名', '利用者コード',
      '外出時間', '帰宅時間', '服薬確認', '洗面援助', '入浴',
      '喫煙', '業務チェック', '食事（何割）', '本人の様子・対応'
    ];
    sheet.appendRow(headers);
    var hr = sheet.getRange(1, 1, 1, headers.length);
    hr.setBackground('#4a86e8');
    hr.setFontColor('#ffffff');
    hr.setFontWeight('bold');
    sheet.setFrozenRows(1);
  }

  var now = new Date();
  var timestamp = Utilities.formatDate(now, 'Asia/Tokyo', 'yyyy/MM/dd HH:mm:ss');

  data.residents.forEach(function(r) {
    sheet.appendRow([
      timestamp,
      data.date,
      data.workHours,
      data.recorder,
      r.code,
      r.leaveTime  || '－',
      r.returnTime || '－',
      r.medication,
      r.washing ? '○' : '－',
      r.bathing ? '○' : '－',
      r.smoking,
      r.checkItems || '－',
      r.meals,
      r.record || '－'
    ]);
  });

  sheet.autoResizeColumns(1, 14);

  // 利用者別参照シート更新
  updateResidentSheets_(ss);

  return { success: true };
}

// ==========================================
// 利用者別参照シートの生成・更新（内部用）
// ==========================================
function updateResidentSheets_(ss) {
  var mainSheet = ss.getSheetByName('支援記録');
  if (!mainSheet) return;

  var allData = mainSheet.getDataRange().getValues();
  if (allData.length <= 1) return;

  var headers    = allData[0];
  var codeColIdx = 4; // '利用者コード' 列（0始まり）

  // 利用者マスターからコード一覧を取得
  var residentSheet = ss.getSheetByName('利用者マスター');
  if (!residentSheet) return;

  var resData = residentSheet.getDataRange().getValues();
  var codes = [];
  for (var i = 1; i < resData.length; i++) {
    var c = String(resData[i][0] || '').trim();
    if (c) codes.push(c);
  }

  codes.forEach(function(code) {
    var ws = ss.getSheetByName(code);
    if (!ws) {
      ws = ss.insertSheet(code);
    } else {
      ws.clearContents();
      ws.clearFormats();
    }

    // ヘッダー
    ws.appendRow(headers);
    var hr = ws.getRange(1, 1, 1, headers.length);
    hr.setBackground('#e8a84a');
    hr.setFontColor('#ffffff');
    hr.setFontWeight('bold');
    ws.setFrozenRows(1);

    // 該当行を抽出
    var rows = allData.filter(function(row, idx) {
      return idx > 0 && row[codeColIdx] === code;
    });
    rows.forEach(function(row) { ws.appendRow(row); });

    ws.autoResizeColumns(1, headers.length);
  });
}
