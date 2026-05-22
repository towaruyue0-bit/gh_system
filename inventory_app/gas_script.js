/**
 * 在庫チェックアプリ 連携スクリプト
 * =====================================
 * このスクリプトを Google Apps Script に貼り付けて使用します。
 * 設定手順は下部の「【設定手順】」を参照してください。
 *
 * 受信データ形式（在庫チェックアプリから送られてくるJSON）:
 *   {
 *     date: "2026-04-07",       // チェック日
 *     memo: "備考テキスト",      // 備考欄
 *     rows: [
 *       { date, name, tab, cat, store, result },  // 各品目のチェック結果
 *       ...
 *     ]
 *   }
 */

// ===== 設定 =====
// データを記録するシート名（変更しても大丈夫です）
var SHEET_NAME = '在庫記録';

// ヘッダー行の内容（1行目に自動で追加されます）
// 「優先度」列は買い物リストアプリの急ぎ度分類用（high/mid/low/none）
var HEADERS = ['日付', '備考', '場所', 'カテゴリ', '品目名', 'チェック結果', '店舗', '優先度'];
// ================


/**
 * POSTリクエストを受け取るメイン関数
 * 在庫チェックアプリの「送信」ボタンが押されたときに自動で呼び出される
 *
 * @param {Object} e - リクエスト情報（アプリから送られたデータが含まれる）
 * @returns {TextOutput} - 処理結果のレスポンス
 */
function doPost(e) {
  try {
    // 送られてきたJSONデータを解析する
    var data = JSON.parse(e.postData.contents);

    // スプレッドシートのシートを取得（なければ新規作成）
    var sheet = getOrCreateSheet(SHEET_NAME);

    // シートが空のとき（初回）はヘッダー行を追加する
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);

      // ヘッダー行を見やすく装飾する
      var headerRange = sheet.getRange(1, 1, 1, HEADERS.length);
      headerRange.setBackground('#4A6FA5');       // 背景色：青
      headerRange.setFontColor('#FFFFFF');         // 文字色：白
      headerRange.setFontWeight('bold');           // 太字
      sheet.setFrozenRows(1);                      // ヘッダー行を固定（スクロールしても見える）
    } else {
      // 既存シートに不足している列を自動で追加する（旧バージョンからのデータ移行対応）
      var headerRow = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
      ['店舗', '優先度'].forEach(function(colName) {
        if (headerRow.indexOf(colName) === -1) {
          var newCol = sheet.getLastColumn() + 1;
          var newHeader = sheet.getRange(1, newCol);
          newHeader.setValue(colName);
          newHeader.setBackground('#4A6FA5');
          newHeader.setFontColor('#FFFFFF');
          newHeader.setFontWeight('bold');
          // 追加した後のヘッダー行を再読込（次のループで正しく検出するため）
          headerRow = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
        }
      });
    }

    // 品目ごとに1行ずつスプレッドシートに追記する
    var rows = data.rows || [];

    // 送信された品目名に一致する行だけ削除してから追記する。
    // 全削除ではなく品目単位で上書きすることで、途中送信しても
    // 別の品目のデータが消えなくなる。
    var sentNames = rows.map(function(r) { return r.name || ''; });
    deleteRowsByDateAndNames(sheet, data.date, sentNames);
    rows.forEach(function(row) {
      sheet.appendRow([
        data.date,         // 日付
        data.memo || '',   // 備考
        row.tab   || '',   // 場所（例：引き出し、冷蔵庫）
        row.cat   || '',   // カテゴリ（例：調味料）
        row.name  || '',   // 品目名（例：醤油）
        row.result || '',  // チェック結果（例：ある、なし）
        row.store  || '',  // 購入店舗（例：ベルク）
        row.level  || ''   // 優先度（high/mid/low/none）
      ]);
    });

    // 列幅を自動調整して見やすくする
    sheet.autoResizeColumns(1, sheet.getLastColumn());

    // 成功レスポンスを返す
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'success', count: rows.length }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (error) {
    // エラーが起きた場合はエラー内容を返す
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', message: error.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}


/**
 * 指定した日付 かつ 指定した品目名に一致する行だけをシートから削除する。
 * 送信された品目だけを対象にすることで、途中送信しても他の品目のデータが
 * 消えないようにしている。同じ品目を再送信したときは上書きになる。
 *
 * @param {Sheet}    sheet    - 対象のシート
 * @param {string}   dateStr  - 削除したい日付（"YYYY-MM-DD" 形式）
 * @param {string[]} names    - 削除対象の品目名の配列
 */
function deleteRowsByDateAndNames(sheet, dateStr, names) {
  var lastRow = sheet.getLastRow();
  if (lastRow <= 1) return;  // ヘッダーしかない

  // 高速に検索できるよう品目名のセット（辞書）を作る
  var nameSet = {};
  names.forEach(function(n) { nameSet[n] = true; });

  // A列（日付）とE列（品目名）をまとめて読み込む
  var values = sheet.getRange(2, 1, lastRow - 1, 5).getValues();

  // 下の行から順に削除する（上から削除すると行番号がずれてしまうため）
  for (var i = values.length - 1; i >= 0; i--) {
    var rowDate = formatDateValue(values[i][0]);
    var rowName = String(values[i][4] || '');  // E列（5番目）= 品目名
    if (rowDate === dateStr && nameSet[rowName]) {
      sheet.deleteRow(i + 2);  // +2 = ヘッダー分+0始まり補正
    }
  }
}


/**
 * GETリクエストを受け取る関数
 * 買い物リストアプリが「データを取得」ボタンを押したときに呼び出される。
 * スプレッドシートから最新チェック日のデータを読み込んでJSONで返す。
 *
 * ★ JSONP対応：
 *   ブラウザのセキュリティ制限（CORS）により、ローカルHTMLファイル（file://）から
 *   通常のfetch()でデータを取得できないため、JSONP方式を採用している。
 *   URLに ?callback=関数名 を付けてリクエストされた場合は、
 *   「関数名({...データ...})」の形のJavaScriptとして返す。
 *
 * @param {Object} e - リクエスト情報（e.parameter.callback にコールバック関数名が入る）
 * @returns {TextOutput} - 最新チェック結果のJSONまたはJSONP
 */
function doGet(e) {
  try {
    // JSONP用のコールバック関数名を受け取る（ない場合は通常JSONで返す）
    var callback = e.parameter && e.parameter.callback ? e.parameter.callback : null;

    var sheet = getOrCreateSheet(SHEET_NAME);
    var lastRow = sheet.getLastRow();

    // データがない場合は空を返す
    if (lastRow <= 1) {
      return jsonpResponse({ date: null, memo: '', rows: [] }, callback);
    }

    // データを全行読み込む（ヘッダー行を除く）
    // 列数は最低8列（日付・備考・場所・カテゴリ・品目名・結果・店舗・優先度）を読む
    var numCols = Math.max(sheet.getLastColumn(), 8);
    var allData = sheet.getRange(2, 1, lastRow - 1, numCols).getValues();

    // 品目（品目名＋場所）ごとに最新の行を1件ずつ取得する。
    // 「最新日付のみ返す」ではなく「品目単位で最新を返す」ことで、
    // 一部の場所だけ送信した場合でも他の場所の古いデータが消えなくなる。
    var latestByItem = {};  // key: "品目名|場所" → その品目の最新行情報
    allData.forEach(function(row) {
      var d = formatDateValue(row[0]);
      if (!d) return;
      var key = String(row[4] || '') + '|' + String(row[2] || '');  // 品目名|場所
      // 同じ品目で複数の日付がある場合は日付が新しい方を残す
      if (!latestByItem[key] || d > latestByItem[key].date) {
        latestByItem[key] = {
          date:   d,
          memo:   String(row[1] || ''),
          tab:    String(row[2] || ''),  // 場所
          cat:    String(row[3] || ''),  // カテゴリ
          name:   String(row[4] || ''),  // 品目名
          result: String(row[5] || ''),  // チェック結果
          store:  String(row[6] || ''),  // 店舗
          level:  String(row[7] || '')   // 優先度（high/mid/low/none）
        };
      }
    });

    if (Object.keys(latestByItem).length === 0) {
      return jsonpResponse({ date: null, memo: '', rows: [] }, callback);
    }

    // 全品目の中で最も新しい日付とその備考をヘッダー用に取得する
    var latestDate = '';
    var memo = '';
    Object.keys(latestByItem).forEach(function(key) {
      var item = latestByItem[key];
      if (item.date > latestDate) {
        latestDate = item.date;
        memo = item.memo;
      }
    });

    // 品目ごとの最新行を配列に変換する
    var rows = Object.keys(latestByItem).map(function(key) {
      var item = latestByItem[key];
      return {
        tab:    item.tab,
        cat:    item.cat,
        name:   item.name,
        result: item.result,
        store:  item.store,
        level:  item.level
      };
    });

    return jsonpResponse({ date: latestDate, memo: memo, rows: rows }, callback);

  } catch (error) {
    return jsonpResponse({ error: error.toString() }, callback);
  }
}


/**
 * 日付の値を "YYYY-MM-DD" 形式の文字列に変換する。
 * スプレッドシートでは日付がDateオブジェクトになることがあるため
 * 文字列でも日付オブジェクトでも正しく処理できるようにする。
 *
 * @param {Date|string} val - 変換する値
 * @returns {string} - "YYYY-MM-DD" 形式の文字列
 */
function formatDateValue(val) {
  if (!val) return '';
  if (val instanceof Date) {
    // getDate() は GAS の実行タイムゾーン（UTC）に依存するため、
    // 日本時間（UTC+9）のスプレッドシートでは日付が1日ずれる場合がある。
    // Utilities.formatDate でスプレッドシートのタイムゾーンを明示することで正しく変換する。
    return Utilities.formatDate(
      val,
      SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone(),
      'yyyy-MM-dd'
    );
  }
  return String(val);
}


/**
 * レスポンス用のJSON出力を作成する。
 *
 * @param {Object} data - レスポンスとして返すデータ
 * @returns {TextOutput} - JSONのレスポンスオブジェクト
 */
/**
 * JSONP または通常JSONのレスポンスを作成する。
 * callbackがある場合はJSONP形式（JavaScriptとして返す）。
 * ない場合は通常のJSONとして返す。
 *
 * JSONP形式の例：myCallback({"date":"2026-04-07","rows":[...]})
 *   → ブラウザがこのJavaScriptを実行し、myCallback関数が呼ばれる
 *
 * @param {Object} data     - レスポンスとして返すデータ
 * @param {string|null} cb  - コールバック関数名（不要な場合はnull）
 * @returns {TextOutput}    - レスポンスオブジェクト
 */
function jsonpResponse(data, cb) {
  var json = JSON.stringify(data);
  if (cb) {
    // JSONP形式：コールバック関数名(データ) として返す
    return ContentService
      .createTextOutput(cb + '(' + json + ')')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  // 通常のJSON形式で返す
  return ContentService
    .createTextOutput(json)
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * 通常のJSONレスポンスを作成する（doPost用）。
 *
 * @param {Object} data - レスポンスとして返すデータ
 * @returns {TextOutput} - JSONのレスポンスオブジェクト
 */
function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}


/**
 * 指定した名前のシートを取得する。なければ新規作成する。
 *
 * @param {string} sheetName - シート名
 * @returns {Sheet} - スプレッドシートのシートオブジェクト
 */
function getOrCreateSheet(sheetName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(sheetName);

  // シートが存在しない場合は新規作成する
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  }

  return sheet;
}


/**
 * ========================================
 * 【設定手順】― 初回のみ行う作業
 * ========================================
 *
 * ▼ STEP 1: Googleスプレッドシートを新規作成する
 *   1. Googleドライブ（drive.google.com）を開く
 *   2. 左上の「＋新規」→「Googleスプレッドシート」をクリック
 *   3. ファイル名を「在庫チェック記録」などにする（何でもOK）
 *
 * ▼ STEP 2: Apps Scriptを開く
 *   1. スプレッドシートの上部メニュー「拡張機能」→「Apps Script」をクリック
 *   2. エディタが開いたら、最初から書いてあるコードをすべて削除する
 *   3. このファイルの内容（上のコード全部）を貼り付ける
 *   4. 左上のフロッピーアイコン（または Ctrl+S）で保存する
 *
 * ▼ STEP 3: ウェブアプリとして公開する
 *   1. 右上の「デプロイ」ボタン →「新しいデプロイ」をクリック
 *   2. 左側の歯車アイコン →「ウェブアプリ」を選択
 *   3. 以下のように設定する：
 *      - 説明：「在庫チェック連携」など（何でもOK）
 *      - 次のユーザーとして実行：「自分」
 *      - アクセスできるユーザー：「全員」  ← ★ここが重要
 *   4. 「デプロイ」ボタンをクリック
 *   5. Googleアカウントへのアクセス許可を求められたら「許可」する
 *   6. 「ウェブアプリのURL」が表示されるのでコピーする
 *      （例：https://script.google.com/macros/s/AKfyc.../exec）
 *
 * ▼ STEP 4: アプリにURLを設定する
 *   1. 在庫チェックアプリをブラウザで開く
 *   2. 右上の「⚙ 設定」を開く
 *   3. 「GAS送信先URL」の欄にコピーしたURLを貼り付ける
 *   4. 「URLを保存」をクリック
 *   5. 買い物リストアプリ（shopping_list.html）でも同じURLを設定する
 *   6. 完了！次回チェック送信時からスプレッドシートに記録されます
 *
 * ----------------------------------------
 * ★ 注意：コードを修正したときは「新しいデプロイ」ではなく
 *   「デプロイを管理」→「編集（鉛筆アイコン）」→「バージョン：新しいバージョン」
 *   で更新してください。URLは変わりません。
 * ----------------------------------------
 */
