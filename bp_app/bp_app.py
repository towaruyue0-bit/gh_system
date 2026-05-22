# =============================================================================
# 血圧測定記録アプリ
# グループホーム 入居者 血圧測定記録管理システム
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
import calendar
import webbrowser
import tempfile
from datetime import datetime, date, timedelta

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "bp_backups")
APP_DIR      = os.path.join(BASE_DIR, "bp_app")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
BP_DB        = os.path.join(DATA_DIR, "bp_records.db")
VISIT_DB     = os.path.join(DATA_DIR, "visits.db")
MEDICINE_DB  = os.path.join(DATA_DIR, "medicine.db")
MAX_BACKUPS  = 10

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 高血圧の警戒ライン
BP_SYS_WARN = 130
BP_DIA_WARN = 80

# グラフ Y 軸の固定範囲
GRAPH_BP_MIN = 40
GRAPH_BP_MAX = 180

# 行背景色
ROW_BG_EVEN = "#FFFFFF"
ROW_BG_ODD  = "#F0F4FA"
ROW_BG_HIGH = "#FFE8E8"

# 薬アプリと共通の服薬時刻（medicine_app.py と同じ定数）
TIME_SLOTS = ["朝", "昼", "夕", "寝る前"]
SLOT_TIMES = {"朝": "07:00", "昼": "12:00", "夕": "19:00", "寝る前": "21:00"}


# =============================================================================
# 初期セットアップ
# =============================================================================

def setup():
    """アプリ起動時にフォルダ・DBを自動作成し、バックアップを実行する"""
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(APP_DIR,    exist_ok=True)
    _create_db()
    _backup_db()


def _create_db():
    """血圧記録DBのテーブルを作成する（なければ作成）"""
    conn = sqlite3.connect(BP_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bp_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            record_date TEXT    NOT NULL,
            systolic    INTEGER,
            diastolic   INTEGER,
            memo        TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(resident_id, record_date)
        )
    """)
    # 血圧測定の対象者を管理するテーブル（チェックした人だけドロップダウンに表示する）
    c.execute("""
        CREATE TABLE IF NOT EXISTS bp_targets (
            resident_id INTEGER PRIMARY KEY,
            enabled     INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def _backup_db():
    """起動時にDBをバックアップする。MAX_BACKUPS を超えた分は古い順に削除する"""
    if not os.path.exists(BP_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(BP_DB, backup_file)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


def get_conn():
    """血圧記録DB への接続を返す（列名アクセス対応）"""
    conn = sqlite3.connect(BP_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_residents_conn():
    """入居者マスターDB への接続を返す（読み取り専用）"""
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# 医療情報取得ヘルパー
# =============================================================================

def get_next_visits(resident_id):
    """
    通院記録DBから、指定入居者の「次回通院予定日」を病院ごとに返す。
    各病院の最新の通院記録に登録されている next_visit_date を使用する。
    戻り値: [{"hospital": "○○病院（内科）", "date": "2026-05-20"}, ...]
    """
    if not os.path.exists(VISIT_DB):
        return []
    try:
        conn = sqlite3.connect(VISIT_DB)
        conn.row_factory = sqlite3.Row
        # 各病院の最新通院記録の next_visit_date を取得する
        rows = conn.execute("""
            SELECT h.name, h.department, v.next_visit_date
            FROM visits v
            JOIN hospitals h ON v.hospital_id = h.id
            WHERE v.resident_id = ?
              AND v.next_visit_date IS NOT NULL
              AND v.next_visit_date != ''
              AND v.id = (
                  SELECT id FROM visits
                  WHERE hospital_id = v.hospital_id
                    AND resident_id  = v.resident_id
                    AND next_visit_date IS NOT NULL
                    AND next_visit_date != ''
                  ORDER BY visit_date DESC LIMIT 1
              )
            ORDER BY v.next_visit_date
        """, (resident_id,)).fetchall()
        conn.close()
        result = []
        for r in rows:
            dept    = f"（{r['department']}）" if r["department"] else ""
            result.append({
                "hospital": f"{r['name']}{dept}",
                "date":     r["next_visit_date"],
            })
        return result
    except Exception:
        return []


def _count_consumed_since(updated_at_str, slot):
    """
    updated_at から現在までに、指定時間帯の服薬時刻を何回通過したかを返す。
    medicine_app.py の count_consumed_since と同じロジック。
    """
    if not updated_at_str or slot not in SLOT_TIMES:
        return 0
    try:
        updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0
    time_str   = SLOT_TIMES[slot]
    h, m       = int(time_str[:2]), int(time_str[3:])
    now        = datetime.now()
    consume_dt = updated_at.replace(hour=h, minute=m, second=0, microsecond=0)
    if consume_dt <= updated_at:
        consume_dt += timedelta(days=1)
    if consume_dt > now:
        return 0
    return (now - consume_dt).days + 1


def get_medicine_end_dates(resident_id):
    """
    薬アプリDBから、指定入居者の内服終了予定日を時間帯ごとに計算して返す。
    medicine_app.py の calc_available_until と同じロジックで算出する。
    戻り値: [{"slot": "朝", "end_date": date(...), "label": "5月25日"}, ...]
    有効（enabled=1）な時間帯のみ返す。
    """
    if not os.path.exists(MEDICINE_DB):
        return []
    try:
        conn = sqlite3.connect(MEDICINE_DB)
        conn.row_factory = sqlite3.Row
        settings_rows = conn.execute(
            "SELECT time_slot, enabled FROM medicine_settings WHERE resident_id = ?",
            (resident_id,)
        ).fetchall()
        inv_rows = conn.execute(
            "SELECT time_slot, calendar_days, stock_days, updated_at FROM medicine_inventory WHERE resident_id = ?",
            (resident_id,)
        ).fetchall()
        conn.close()

        settings  = {r["time_slot"]: r["enabled"] for r in settings_rows}
        inventory = {r["time_slot"]: dict(r) for r in inv_rows}

        result = []
        for slot in TIME_SLOTS:
            if not settings.get(slot):
                continue  # 無効な時間帯はスキップ
            inv       = inventory.get(slot, {})
            cal_days  = inv.get("calendar_days", 0) or 0
            stk_days  = inv.get("stock_days", 0) or 0
            updated   = inv.get("updated_at")
            consumed  = _count_consumed_since(updated, slot)
            remaining = cal_days - consumed + stk_days
            if remaining <= 0:
                label    = "なし"
                end_date = None
            else:
                # 今日の服薬時刻が過ぎているかで offset が変わる
                h, m = int(SLOT_TIMES[slot][:2]), int(SLOT_TIMES[slot][3:])
                today_consumed = (datetime.now().hour, datetime.now().minute) >= (h, m)
                offset   = remaining if today_consumed else remaining - 1
                end_date = date.today() + timedelta(days=offset)
                label    = end_date.strftime("%m月%d日")
            result.append({"slot": slot, "end_date": end_date, "label": label})
        return result
    except Exception:
        return []


# =============================================================================
# 印刷用 HTML 生成
# =============================================================================

def _build_svg_graph(data, year, month, width=520, height=300):
    """
    血圧データ（{day: (systolic, diastolic)}）から SVG 形式のグラフを生成して返す。
    印刷用 HTML に埋め込むために使う。
    """
    days_in_month = calendar.monthrange(year, month)[1]
    ml = 46; mr = 28; mt = 28; mb = 40
    gw = width  - ml - mr
    gh = height - mt - mb

    def yp(bp):
        return mt + (GRAPH_BP_MAX - bp) / (GRAPH_BP_MAX - GRAPH_BP_MIN) * gh

    def xp(day):
        return ml + (day - 1) / max(days_in_month - 1, 1) * gw

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="font-family:\'MS Gothic\',sans-serif;font-size:10px;">']

    # 背景
    lines.append(f'<rect x="{ml}" y="{mt}" width="{gw}" height="{gh}" '
                 f'fill="white" stroke="#BBBBBB" stroke-width="1"/>')

    # Y 軸グリッドと目盛り
    for bp in range(GRAPH_BP_MIN, GRAPH_BP_MAX + 1, 20):
        y = yp(bp)
        lines.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+gw}" y2="{y:.1f}" '
                     f'stroke="#E0E0E0" stroke-dasharray="2,4" stroke-width="1"/>')
        lines.append(f'<text x="{ml-4}" y="{y+3:.1f}" text-anchor="end" fill="#666">{bp}</text>')

    # 警戒ライン（130 / 80）
    for bp_line, color, label in [(BP_SYS_WARN, "#FF6666", str(BP_SYS_WARN)),
                                   (BP_DIA_WARN, "#4488CC", str(BP_DIA_WARN))]:
        y = yp(bp_line)
        lines.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+gw}" y2="{y:.1f}" '
                     f'stroke="{color}" stroke-dasharray="6,4" stroke-width="1.5"/>')
        lines.append(f'<text x="{ml+gw+4}" y="{y+3:.1f}" fill="{color}">{label}</text>')

    # X 軸目盛り（5日ごと）
    for day in range(1, days_in_month + 1, 5):
        x = xp(day)
        lines.append(f'<line x1="{x:.1f}" y1="{mt+gh}" x2="{x:.1f}" y2="{mt+gh+4}" '
                     f'stroke="#888" stroke-width="1"/>')
        lines.append(f'<text x="{x:.1f}" y="{mt+gh+16}" text-anchor="middle" fill="#555">{day}日</text>')

    # 折れ線グラフ（最高：赤、最低：青）
    for key_idx, color in enumerate(["#D94040", "#2288AA"]):
        pts = [(xp(d), yp(v[key_idx]))
               for d, v in sorted(data.items())
               if v[key_idx] is not None]
        if len(pts) >= 2:
            polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            lines.append(f'<polyline points="{polyline}" fill="none" '
                         f'stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" '
                         f'fill="{color}" stroke="{color}"/>')

    lines.append('</svg>')
    return "\n".join(lines)


def generate_print_html(resident_name, year, month, records,
                        next_visits, medicine_ends):
    """
    印刷用の HTML 文字列を生成して返す。
    ブラウザで開いて Ctrl+P で印刷する想定。

    引数:
        resident_name : 利用者名（文字列）
        year, month   : 対象年月（int）
        records       : {day: {"systolic": int|None, "diastolic": int|None, "memo": str}}
        next_visits   : get_next_visits() の戻り値
        medicine_ends : get_medicine_end_dates() の戻り値
    """
    days_in_month = calendar.monthrange(year, month)[1]

    # --- グラフ用データを辞書に変換 ---
    graph_data = {d: (r["systolic"], r["diastolic"]) for d, r in records.items()}
    svg_graph  = _build_svg_graph(graph_data, year, month)

    # --- 通院予定日のHTML ---
    if next_visits:
        visit_items = "　".join(
            f'<span class="info-item">{v["hospital"]}　'
            f'<b>{v["date"].replace("-", "/")[5:]}</b></span>'   # MM/DD 形式
            for v in next_visits
        )
        visit_html = f'<div class="info-row"><span class="info-label">次回通院予定</span>{visit_items}</div>'
    else:
        visit_html = ""

    # --- 内服終了日のHTML ---
    if medicine_ends:
        med_items = "　".join(
            f'<span class="info-item">{e["slot"]}　<b>{e["label"]}</b></span>'
            for e in medicine_ends
        )
        med_html = f'<div class="info-row"><span class="info-label">内服終了予定</span>{med_items}</div>'
    else:
        med_html = ""

    # --- 月間テーブルの行 ---
    table_rows = []
    sys_vals = [records[d]["systolic"]  for d in records if records[d]["systolic"]  is not None]
    dia_vals = [records[d]["diastolic"] for d in records if records[d]["diastolic"] is not None]
    for day in range(1, days_in_month + 1):
        r      = records.get(day, {})
        sys_v  = r.get("systolic")
        dia_v  = r.get("diastolic")
        memo   = r.get("memo") or ""
        sys_str = str(sys_v) if sys_v is not None else ""
        dia_str = str(dia_v) if dia_v is not None else ""
        table_rows.append(
            f'<tr>'
            f'<td class="date">{month}月{day}日</td>'
            f'<td class="num">{sys_str}</td>'
            f'<td class="num">{dia_str}</td>'
            f'<td class="memo">{memo}</td>'
            f'</tr>'
        )

    # --- 平均値 ---
    avg_sys = f"{sum(sys_vals)/len(sys_vals):.1f}" if sys_vals else "—"
    avg_dia = f"{sum(dia_vals)/len(dia_vals):.1f}" if dia_vals else "—"

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>血圧測定記録 {resident_name} {year}年{month}月</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "MS Gothic", "Meiryo", sans-serif;
    font-size: 10pt;
    color: #222;
  }}
  h1 {{
    font-size: 13pt;
    text-align: center;
    margin-bottom: 6px;
    border-bottom: 2px solid #2C5F8A;
    padding-bottom: 4px;
    color: #2C5F8A;
  }}
  .info-section {{
    margin-bottom: 6px;
    padding: 4px 8px;
    background: #F0F4FA;
    border-left: 4px solid #2C5F8A;
    font-size: 9.5pt;
  }}
  .info-row {{ margin: 2px 0; }}
  .info-label {{
    display: inline-block;
    width: 7em;
    font-weight: bold;
    color: #2C5F8A;
  }}
  .info-item {{ margin-right: 12px; }}
  .main-area {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
  }}
  .table-wrap {{ flex: 0 0 auto; }}
  .graph-wrap {{ flex: 1 1 auto; }}
  table {{
    border-collapse: collapse;
    font-size: 9pt;
    width: 100%;
  }}
  th {{
    background: #2C5F8A;
    color: white;
    padding: 3px 6px;
    text-align: center;
    font-weight: normal;
  }}
  td {{
    padding: 2px 6px;
    border-bottom: 1px solid #DDD;
  }}
  td.date {{ text-align: center; white-space: nowrap; }}
  td.num  {{ text-align: center; width: 48px; }}
  td.memo {{ font-size: 8.5pt; color: #444; }}
  tr:nth-child(even) {{ background: #F5F8FF; }}
  .summary {{
    margin-top: 6px;
    font-size: 9pt;
    text-align: right;
    color: #555;
  }}
  .legend {{
    font-size: 8.5pt;
    color: #666;
    margin-top: 4px;
  }}
  @media print {{
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
<h1>血圧測定記録　{resident_name}　{year}年{month}月</h1>

<div class="info-section">
{visit_html}
{med_html}
</div>

<div class="main-area">
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>日付</th><th>最高血圧</th><th>最低血圧</th><th style="width:140px">メモ</th>
        </tr>
      </thead>
      <tbody>
        {"".join(table_rows)}
      </tbody>
    </table>
    <div class="summary">
      平均　最高血圧 {avg_sys} mmHg　／　最低血圧 {avg_dia} mmHg
    </div>
  </div>
  <div class="graph-wrap">
    {svg_graph}
    <div class="legend">
      &#9644; 最高血圧（赤）　&#9644; 最低血圧（青）　点線：警戒ライン（130 / 80 mmHg）
    </div>
  </div>
</div>

<p class="no-print" style="margin-top:16px;color:#888;font-size:9pt;">
  ※ このページを印刷するには、ブラウザの印刷機能（Ctrl+P）をお使いください。
  　印刷設定で「用紙サイズ：A4横」「余白：最小」を選ぶときれいに出力されます。
</p>
</body>
</html>"""
    return html


# =============================================================================
# 対象者設定ダイアログ
# =============================================================================

class BpTargetDialog(tk.Toplevel):
    """
    血圧測定の対象者を選ぶダイアログ。
    入居中の全員をチェックボックスで表示し、ONにした人だけが
    メイン画面のドロップダウンに表示されるようになる。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("血圧測定 対象者設定")
        self.resizable(False, False)
        self.grab_set()   # モーダルにする（このダイアログを閉じるまで親を操作不可）
        self._build()
        self._center(parent)
        self.wait_window()  # ダイアログが閉じるまで呼び出し元を待機させる

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        """UI を構築する"""
        tk.Label(
            self, text="血圧測定の対象者を選んでください",
            font=FONT_BOLD, padx=20, pady=10
        ).pack()

        tk.Label(
            self,
            text="チェックを入れた方がドロップダウンに表示されます。\n"
                 "（チェックを外しても、その方の記録データは消えません）",
            font=FONT_SMALL, fg="#555", padx=20, justify="left"
        ).pack(anchor="w")

        # チェックボックスをスクロール可能エリアに並べる
        frame_outer = tk.Frame(self, padx=20, pady=6)
        frame_outer.pack(fill="both")

        canvas = tk.Canvas(frame_outer, highlightthickness=0, width=280)
        vsb    = ttk.Scrollbar(frame_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both")
        vsb.pack(side="left", fill="y")

        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # 入居中の全員と現在の設定を取得する
        if not os.path.exists(RESIDENTS_DB):
            tk.Label(inner, text="入居者DBが見つかりません", font=FONT).pack()
            return

        r_conn   = get_residents_conn()
        all_rows = r_conn.execute(
            "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY room_number"
        ).fetchall()
        r_conn.close()

        bp_conn     = get_conn()
        target_rows = bp_conn.execute(
            "SELECT resident_id, enabled FROM bp_targets"
        ).fetchall()
        bp_conn.close()

        # 設定済みの resident_id → enabled の辞書（未登録の人は True 扱い）
        saved = {r["resident_id"]: bool(r["enabled"]) for r in target_rows}

        self._vars     = {}   # {resident_id: BooleanVar}
        self._resident_ids = [r["id"] for r in all_rows]

        for i, row in enumerate(all_rows):
            bg  = "#FFFFFF" if i % 2 == 0 else "#F0F4FA"
            var = tk.BooleanVar(value=saved.get(row["id"], True))
            self._vars[row["id"]] = var
            tk.Checkbutton(
                inner, text=row["name"], variable=var,
                font=FONT, bg=bg, anchor="w",
                activebackground=bg, padx=8, pady=3
            ).pack(fill="x")

        # チェックボックスが多い場合のために高さを調整する（最大12行分）
        row_h  = 30
        height = min(len(all_rows), 12) * row_h + 4
        canvas.configure(height=height)

        # 全選択・全解除ボタン
        btn_row = tk.Frame(self, padx=20, pady=4)
        btn_row.pack()
        tk.Button(
            btn_row, text="全員選択", font=FONT_SMALL, relief="flat",
            bg="#AAAAAA", fg="white", padx=6, pady=2, cursor="hand2",
            command=lambda: [v.set(True)  for v in self._vars.values()]
        ).pack(side="left", padx=4)
        tk.Button(
            btn_row, text="全員解除", font=FONT_SMALL, relief="flat",
            bg="#AAAAAA", fg="white", padx=6, pady=2, cursor="hand2",
            command=lambda: [v.set(False) for v in self._vars.values()]
        ).pack(side="left", padx=4)

        # 保存・キャンセルボタン
        footer = tk.Frame(self, pady=10)
        footer.pack()
        tk.Button(
            footer, text="保存して閉じる", font=FONT_BOLD, relief="flat",
            bg="#2C5F8A", fg="white", padx=12, pady=4, cursor="hand2",
            command=self._save
        ).pack(side="left", padx=8)
        tk.Button(
            footer, text="キャンセル", font=FONT, relief="flat",
            padx=8, pady=4, cursor="hand2",
            command=self.destroy
        ).pack(side="left", padx=8)

    def _save(self):
        """チェックの状態を bp_targets テーブルに保存して閉じる"""
        conn = get_conn()
        for rid, var in self._vars.items():
            conn.execute(
                """INSERT INTO bp_targets (resident_id, enabled) VALUES (?, ?)
                   ON CONFLICT(resident_id) DO UPDATE SET enabled = excluded.enabled""",
                (rid, 1 if var.get() else 0)
            )
        conn.commit()
        conn.close()
        self.destroy()


# =============================================================================
# メインアプリ
# =============================================================================

class BpApp(tk.Tk):
    """血圧測定記録アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("血圧測定記録")
        self.geometry("1150x760")
        self.resizable(True, True)
        self.configure(bg="#F5F7FA")

        self.selected_resident_id   = None
        self.selected_resident_name = ""
        self._residents  = {}
        self.selected_year  = tk.IntVar(value=date.today().year)
        self.selected_month = tk.IntVar(value=date.today().month)

        # 一覧グリッドの行データ
        self._grid_rows = []

        self._build_ui()
        self._load_residents()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        """画面全体のUIを組み立てる"""

        # ---- ヘッダー ----
        header = tk.Frame(self, bg="#2C5F8A", pady=8)
        header.pack(fill="x")
        tk.Label(
            header, text="血圧測定記録", font=FONT_TITLE,
            bg="#2C5F8A", fg="white"
        ).pack(side="left", padx=20)

        # ---- コントロールバー ----
        ctrl = tk.Frame(self, bg="#E8EDF2", pady=6)
        ctrl.pack(fill="x", padx=10, pady=(6, 0))

        tk.Label(ctrl, text="利用者：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(10, 2))
        self.resident_cb = ttk.Combobox(ctrl, font=FONT, width=16, state="readonly")
        self.resident_cb.pack(side="left", padx=(0, 16))
        self.resident_cb.bind("<<ComboboxSelected>>", self._on_resident_changed)

        tk.Label(ctrl, text="年：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(0, 2))
        tk.Spinbox(
            ctrl, textvariable=self.selected_year,
            from_=2020, to=2099, width=6, font=FONT,
            command=self._refresh
        ).pack(side="left", padx=(0, 4))

        tk.Label(ctrl, text="月：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(0, 2))
        month_cb = ttk.Combobox(
            ctrl, textvariable=self.selected_month,
            values=list(range(1, 13)), width=4, font=FONT, state="readonly"
        )
        month_cb.pack(side="left", padx=(0, 4))
        month_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        tk.Button(
            ctrl, text="表示", font=FONT, relief="flat",
            bg="#2C5F8A", fg="white", padx=8, pady=2,
            cursor="hand2", command=self._refresh
        ).pack(side="left", padx=(4, 0))

        tk.Button(
            ctrl, text="対象者設定", font=FONT, relief="flat",
            bg="#7B7B7B", fg="white", padx=8, pady=2,
            cursor="hand2", command=self._open_target_settings
        ).pack(side="left", padx=(10, 0))

        # 右側ボタン（まとめて保存・印刷）
        tk.Button(
            ctrl, text="  まとめて保存  ", font=FONT_BOLD, relief="flat",
            bg="#2E7D32", fg="white", padx=10, pady=2,
            cursor="hand2", command=self._save_all
        ).pack(side="right", padx=(4, 10))

        tk.Button(
            ctrl, text="  印 刷  ", font=FONT_BOLD, relief="flat",
            bg="#5C6BC0", fg="white", padx=10, pady=2,
            cursor="hand2", command=self._print_preview
        ).pack(side="right", padx=4)

        # ---- 医療情報バー（通院予定日・内服終了日）----
        self.info_frame = tk.Frame(self, bg="#EFF4EE", pady=4,
                                   highlightbackground="#AAC8A8",
                                   highlightthickness=1)
        self.info_frame.pack(fill="x", padx=10, pady=(4, 0))

        self.visit_lbl = tk.Label(
            self.info_frame, text="次回通院予定：（読み込み中）",
            font=FONT_SMALL, bg="#EFF4EE", anchor="w"
        )
        self.visit_lbl.pack(side="left", padx=(10, 20))

        self.med_lbl = tk.Label(
            self.info_frame, text="内服終了予定：（読み込み中）",
            font=FONT_SMALL, bg="#EFF4EE", anchor="w"
        )
        self.med_lbl.pack(side="left", padx=(0, 10))

        # ---- メイン部（左：入力グリッド、右：グラフ）----
        main = tk.Frame(self, bg="#F5F7FA")
        main.pack(fill="both", expand=True, padx=10, pady=6)

        # 左側：一覧入力グリッド
        left_frame = tk.Frame(main, bg="#F5F7FA")
        left_frame.pack(side="left", fill="y")

        # 列ヘッダー
        header_row = tk.Frame(left_frame, bg="#D0D8E8")
        header_row.pack(fill="x")
        for text, w in [("日付", 72), ("最高血圧", 76), ("最低血圧", 76), ("メモ", 174)]:
            tk.Label(
                header_row, text=text, font=FONT_BOLD,
                bg="#D0D8E8", anchor="center",
                relief="flat", padx=4, pady=3, width=0
            ).pack(side="left")

        # スクロール可能グリッドエリア
        grid_container = tk.Frame(left_frame, bg="#F5F7FA")
        grid_container.pack(fill="y", expand=True)

        self.grid_canvas = tk.Canvas(
            grid_container, bg="#F5F7FA",
            highlightthickness=0, width=430
        )
        vsb = ttk.Scrollbar(grid_container, orient="vertical", command=self.grid_canvas.yview)
        self.grid_canvas.configure(yscrollcommand=vsb.set)
        self.grid_canvas.pack(side="left", fill="y", expand=True)
        vsb.pack(side="left", fill="y")

        self.grid_frame = tk.Frame(self.grid_canvas, bg="#F5F7FA")
        self.grid_canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.grid_canvas.configure(
                scrollregion=self.grid_canvas.bbox("all")
            )
        )
        self.grid_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.grid_frame.bind("<MouseWheel>",  self._on_mousewheel)

        # 右側：グラフ
        right_frame = tk.Frame(main, bg="#F5F7FA", padx=10)
        right_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            right_frame, text="血圧グラフ", font=FONT_BOLD, bg="#F5F7FA"
        ).pack(anchor="w", pady=(0, 4))

        self.canvas = tk.Canvas(right_frame, bg="white", relief="sunken", bd=1)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_graph())

        tk.Label(
            right_frame,
            text="━ 最高血圧（赤）  ━ 最低血圧（青）  ---- 警戒ライン（130/80）",
            font=FONT_SMALL, bg="#F5F7FA", fg="#666"
        ).pack(anchor="w", pady=(4, 0))

    def _on_mousewheel(self, event):
        """マウスホイールでグリッドをスクロールする"""
        self.grid_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # グリッド構築・データ読み込み
    # ------------------------------------------------------------------

    def _build_grid(self):
        """選択された月の日数分の入力行を作る。既存行は破棄してから再作成する"""
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        self._grid_rows = []

        year          = self.selected_year.get()
        month         = self.selected_month.get()
        days_in_month = calendar.monthrange(year, month)[1]

        for day in range(1, days_in_month + 1):
            sys_var  = tk.StringVar()
            dia_var  = tk.StringVar()
            memo_var = tk.StringVar()

            bg = ROW_BG_EVEN if day % 2 == 0 else ROW_BG_ODD

            row_frame = tk.Frame(self.grid_frame, bg=bg, pady=1)
            row_frame.pack(fill="x")

            tk.Label(
                row_frame, text=f"{month}月{day}日",
                font=FONT, bg=bg, width=7, anchor="center"
            ).pack(side="left", padx=(4, 2))

            sys_entry = tk.Entry(
                row_frame, textvariable=sys_var,
                font=FONT, width=6, justify="center", bg=bg, relief="solid", bd=1
            )
            sys_entry.pack(side="left", padx=2, ipady=2)

            dia_entry = tk.Entry(
                row_frame, textvariable=dia_var,
                font=FONT, width=6, justify="center", bg=bg, relief="solid", bd=1
            )
            dia_entry.pack(side="left", padx=2, ipady=2)

            tk.Entry(
                row_frame, textvariable=memo_var,
                font=FONT, width=18, bg=bg, relief="solid", bd=1
            ).pack(side="left", padx=(2, 4), ipady=2)

            sys_entry.bind("<FocusOut>", lambda e, d=day: self._check_row_color(d))
            dia_entry.bind("<FocusOut>", lambda e, d=day: self._check_row_color(d))

            for w in row_frame.winfo_children():
                w.bind("<MouseWheel>", self._on_mousewheel)
            row_frame.bind("<MouseWheel>", self._on_mousewheel)

            self._grid_rows.append({
                "day": day, "sys_var": sys_var, "dia_var": dia_var,
                "memo_var": memo_var, "row_frame": row_frame,
                "sys_entry": sys_entry, "dia_entry": dia_entry, "bg": bg,
            })

        self.grid_canvas.update_idletasks()
        self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        self.grid_canvas.yview_moveto(0)

    def _load_into_grid(self):
        """DBから当月データを読み込んで各行の Entry にセットする"""
        if not self.selected_resident_id or not self._grid_rows:
            return
        year      = self.selected_year.get()
        month     = self.selected_month.get()
        conn      = get_conn()
        rows      = conn.execute(
            """SELECT record_date, systolic, diastolic, memo FROM bp_records
               WHERE resident_id = ? AND record_date LIKE ?""",
            (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
        ).fetchall()
        conn.close()

        record_map = {}
        for r in rows:
            d = int(r["record_date"].split("-")[2])
            record_map[d] = r

        for row in self._grid_rows:
            day = row["day"]
            if day in record_map:
                r = record_map[day]
                row["sys_var"].set(r["systolic"]  if r["systolic"]  is not None else "")
                row["dia_var"].set(r["diastolic"] if r["diastolic"] is not None else "")
                row["memo_var"].set(r["memo"] or "")
            else:
                row["sys_var"].set("")
                row["dia_var"].set("")
                row["memo_var"].set("")
            self._check_row_color(day)

    def _check_row_color(self, day):
        """警戒値を超えている行の背景色を切り替える"""
        row = next((r for r in self._grid_rows if r["day"] == day), None)
        if row is None:
            return
        sys_str = row["sys_var"].get().strip()
        dia_str = row["dia_var"].get().strip()
        is_high = (sys_str.isdigit() and int(sys_str) >= BP_SYS_WARN) or \
                  (dia_str.isdigit() and int(dia_str) >= BP_DIA_WARN)
        bg = ROW_BG_HIGH if is_high else row["bg"]
        row["row_frame"].configure(bg=bg)
        for widget in row["row_frame"].winfo_children():
            if isinstance(widget, tk.Label):
                widget.configure(bg=bg)

    # ------------------------------------------------------------------
    # 医療情報バーの更新
    # ------------------------------------------------------------------

    def _load_medical_info(self):
        """通院予定日と内服終了日を取得して情報バーのラベルを更新する"""
        if not self.selected_resident_id:
            self.visit_lbl.config(text="次回通院予定：—")
            self.med_lbl.config(text="内服終了予定：—")
            return

        # 通院予定日
        visits = get_next_visits(self.selected_resident_id)
        if visits:
            parts = [
                f"{v['hospital']}　{v['date'].replace('-', '/')[5:]}"
                for v in visits
            ]
            self.visit_lbl.config(text="次回通院予定：" + "　／　".join(parts))
        else:
            self.visit_lbl.config(text="次回通院予定：（登録なし）")

        # 内服終了日
        ends = get_medicine_end_dates(self.selected_resident_id)
        if ends:
            parts = [f"{e['slot']} {e['label']}" for e in ends]
            self.med_lbl.config(text="内服終了予定：" + "　".join(parts))
        else:
            self.med_lbl.config(text="内服終了予定：（登録なし）")

    # ------------------------------------------------------------------
    # 表示の更新
    # ------------------------------------------------------------------

    def _refresh(self):
        """グリッド・グラフ・医療情報を最新データで再描画する"""
        self._build_grid()
        self._load_into_grid()
        self._draw_graph()
        self._load_medical_info()

    def _draw_graph(self):
        """Canvas に血圧グラフを描画する"""
        c = self.canvas
        c.delete("all")
        width  = c.winfo_width()
        height = c.winfo_height()
        if width < 100 or height < 100:
            return

        ml = 52; mr = 30; mt = 36; mb = 50
        gw = width - ml - mr
        gh = height - mt - mb

        def yp(bp):
            return mt + (GRAPH_BP_MAX - bp) / (GRAPH_BP_MAX - GRAPH_BP_MIN) * gh

        year          = self.selected_year.get()
        month         = self.selected_month.get()
        days_in_month = calendar.monthrange(year, month)[1]

        def xp(day):
            return ml + (day - 1) / max(days_in_month - 1, 1) * gw

        if not self.selected_resident_id:
            return

        conn = get_conn()
        rows = conn.execute(
            """SELECT record_date, systolic, diastolic FROM bp_records
               WHERE resident_id = ? AND record_date LIKE ?
               ORDER BY record_date""",
            (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
        ).fetchall()
        conn.close()

        c.create_rectangle(ml, mt, ml + gw, mt + gh, fill="white", outline="#CCCCCC")
        c.create_text(width // 2, 18, text=f"{year}年{month}月　血圧測定グラフ",
                      font=FONT_BOLD, fill="#333")

        for bp in range(GRAPH_BP_MIN, GRAPH_BP_MAX + 1, 20):
            y = yp(bp)
            c.create_line(ml, y, ml + gw, y, fill="#E0E0E0", dash=(2, 4))
            c.create_text(ml - 6, y, text=str(bp), font=FONT_SMALL, anchor="e", fill="#666")

        for bp_line, color in [(BP_SYS_WARN, "#FF7777"), (BP_DIA_WARN, "#5599CC")]:
            y = yp(bp_line)
            c.create_line(ml, y, ml + gw, y, fill=color, dash=(6, 4), width=1.5)
            c.create_text(ml + gw + 6, y, text=str(bp_line),
                          font=FONT_SMALL, anchor="w", fill=color)

        for day in range(1, days_in_month + 1, 5):
            x = xp(day)
            c.create_line(x, mt + gh, x, mt + gh + 4, fill="#888")
            c.create_text(x, mt + gh + 16, text=f"{day}日", font=FONT_SMALL, fill="#555")

        c.create_text(14, mt + gh // 2, text="血圧\n(mmHg)",
                      font=FONT_SMALL, fill="#666", justify="center")

        if not rows:
            c.create_text(width // 2, mt + gh // 2,
                          text="データがありません", font=FONT, fill="#AAAAAA")
            return

        data = {}
        for r in rows:
            day = int(r["record_date"].split("-")[2])
            data[day] = (r["systolic"], r["diastolic"])

        sys_pts = [(xp(d), yp(v[0])) for d, v in sorted(data.items()) if v[0] is not None]
        dia_pts = [(xp(d), yp(v[1])) for d, v in sorted(data.items()) if v[1] is not None]

        def draw_series(pts, color):
            if len(pts) >= 2:
                for i in range(len(pts) - 1):
                    c.create_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                                  fill=color, width=2)
            for x, y in pts:
                c.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color)

        draw_series(sys_pts, "#E05050")
        draw_series(dia_pts, "#3399AA")

    # ------------------------------------------------------------------
    # イベントハンドラ
    # ------------------------------------------------------------------

    def _on_resident_changed(self, event=None):
        """利用者ドロップダウンが変わったとき"""
        name = self.resident_cb.get()
        self.selected_resident_id   = self._residents.get(name)
        self.selected_resident_name = name
        self._refresh()

    def _load_residents(self):
        """
        入居者マスターから入居中の利用者を読み込む。
        bp_targets テーブルで enabled=1 に設定された人だけをドロップダウンに表示する。
        まだ一度も設定していない場合は全員を対象にする。
        """
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "注意",
                "入居者マスターDBが見つかりません。\n先に入居者マスターアプリを起動してください。"
            )
            return

        # 入居中の全員を取得
        r_conn = get_residents_conn()
        all_rows = r_conn.execute(
            "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY room_number"
        ).fetchall()
        r_conn.close()

        # 対象者設定を取得（enabled=1 の resident_id セット）
        bp_conn  = get_conn()
        target_rows = bp_conn.execute("SELECT resident_id, enabled FROM bp_targets").fetchall()
        bp_conn.close()

        if target_rows:
            # 設定済みの場合は enabled=1 の人だけ表示する
            enabled_ids = {r["resident_id"] for r in target_rows if r["enabled"]}
            filtered = [r for r in all_rows if r["id"] in enabled_ids]
        else:
            # 一度も設定していない場合は全員を対象にする
            filtered = list(all_rows)

        self._residents = {row["name"]: row["id"] for row in filtered}
        self.resident_cb["values"] = list(self._residents.keys())

        if self._residents:
            self.resident_cb.current(0)
            first_name = list(self._residents.keys())[0]
            self.selected_resident_id   = self._residents[first_name]
            self.selected_resident_name = first_name
            self._refresh()
        else:
            # 対象者が0人の場合は画面をリセットする
            self.selected_resident_id   = None
            self.selected_resident_name = ""
            self._build_grid()
            self._draw_graph()
            self._load_medical_info()

    def _open_target_settings(self):
        """対象者設定ダイアログを開く"""
        BpTargetDialog(self)
        # ダイアログが閉じられたらドロップダウンを再構築する
        self._load_residents()

    # ------------------------------------------------------------------
    # まとめて保存
    # ------------------------------------------------------------------

    def _save_all(self):
        """グリッドの全行をまとめてDBに保存する"""
        if not self.selected_resident_id:
            messagebox.showwarning("入力エラー", "利用者を選択してください。")
            return

        year  = self.selected_year.get()
        month = self.selected_month.get()
        now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        errors    = []
        to_save   = []
        to_delete = []

        for row in self._grid_rows:
            day      = row["day"]
            sys_str  = row["sys_var"].get().strip()
            dia_str  = row["dia_var"].get().strip()
            memo_str = row["memo_var"].get().strip()

            if sys_str == "" and dia_str == "" and memo_str == "":
                to_delete.append(f"{year:04d}-{month:02d}-{day:02d}")
                continue

            sys_val = None
            if sys_str != "":
                if not sys_str.isdigit() or not (1 <= int(sys_str) <= 299):
                    errors.append(f"{month}月{day}日：最高血圧「{sys_str}」が正しくありません")
                    continue
                sys_val = int(sys_str)

            dia_val = None
            if dia_str != "":
                if not dia_str.isdigit() or not (1 <= int(dia_str) <= 299):
                    errors.append(f"{month}月{day}日：最低血圧「{dia_str}」が正しくありません")
                    continue
                dia_val = int(dia_str)

            record_date = f"{year:04d}-{month:02d}-{day:02d}"
            to_save.append((
                self.selected_resident_id, record_date,
                sys_val, dia_val,
                memo_str if memo_str else None,
                now, now
            ))

        if errors:
            messagebox.showwarning(
                "入力エラー",
                "以下の行に問題があります。修正してから保存してください。\n\n" + "\n".join(errors)
            )
            return

        conn = get_conn()
        for record in to_save:
            conn.execute(
                """INSERT INTO bp_records
                       (resident_id, record_date, systolic, diastolic, memo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(resident_id, record_date) DO UPDATE SET
                       systolic   = excluded.systolic,
                       diastolic  = excluded.diastolic,
                       memo       = excluded.memo,
                       updated_at = excluded.updated_at""",
                record
            )
        for record_date in to_delete:
            conn.execute(
                "DELETE FROM bp_records WHERE resident_id = ? AND record_date = ?",
                (self.selected_resident_id, record_date)
            )
        conn.commit()
        conn.close()

        self._draw_graph()
        messagebox.showinfo("保存完了", f"{len(to_save)}件の記録を保存しました。")

    # ------------------------------------------------------------------
    # 印刷プレビュー
    # ------------------------------------------------------------------

    def _print_preview(self):
        """
        印刷用HTMLを一時ファイルに出力し、既定のブラウザで開く。
        ブラウザの印刷機能（Ctrl+P）で A4 横に印刷できる。
        """
        if not self.selected_resident_id:
            messagebox.showwarning("確認", "利用者を選択してください。")
            return

        year  = self.selected_year.get()
        month = self.selected_month.get()

        # DBから当月データを取得
        conn = get_conn()
        rows = conn.execute(
            """SELECT record_date, systolic, diastolic, memo FROM bp_records
               WHERE resident_id = ? AND record_date LIKE ?
               ORDER BY record_date""",
            (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
        ).fetchall()
        conn.close()

        records = {}
        for r in rows:
            day = int(r["record_date"].split("-")[2])
            records[day] = {
                "systolic":  r["systolic"],
                "diastolic": r["diastolic"],
                "memo":      r["memo"] or "",
            }

        # 医療情報を取得
        next_visits   = get_next_visits(self.selected_resident_id)
        medicine_ends = get_medicine_end_dates(self.selected_resident_id)

        # HTMLを生成して一時ファイルに保存
        html = generate_print_html(
            self.selected_resident_name, year, month,
            records, next_visits, medicine_ends
        )
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8",
            delete=False, prefix="bp_print_"
        )
        tmp.write(html)
        tmp.close()

        webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = BpApp()
    app.mainloop()
