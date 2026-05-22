# =============================================================================
# 体重測定記録アプリ
# グループホーム 入居者 体重測定記録管理システム
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
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "weight_backups")
APP_DIR      = os.path.join(BASE_DIR, "weight_app")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
WEIGHT_DB    = os.path.join(DATA_DIR, "weight_records.db")
MAX_BACKUPS  = 10

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 行背景色
ROW_BG_EVEN = "#FFFFFF"
ROW_BG_ODD  = "#F0F4FA"

# グラフのY軸余白（kg単位）。データの最小・最大値にこの値を上下に加えて表示する
GRAPH_Y_MARGIN = 3.0

# グラフのデフォルト表示範囲（データがない場合に使用）
GRAPH_DEFAULT_MIN = 40.0
GRAPH_DEFAULT_MAX = 80.0


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
    """
    体重記録DBのテーブルを作成する（なければ作成）。

    weight_records テーブルの各列：
        id          : 自動採番（連番）
        resident_id : 入居者ID（residents.db の id と対応）
        record_date : 記録日（YYYY-MM-DD 形式）
        weight_kg   : 体重（kg、小数あり）
        memo        : メモ。看護記録アプリから記録した場合は「看護記録」などの識別文字を入れる
        created_at  : 初回保存日時
        updated_at  : 最終更新日時
    """
    conn = sqlite3.connect(WEIGHT_DB)
    c = conn.cursor()
    # 体重測定記録テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS weight_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            record_date TEXT    NOT NULL,
            weight_kg   REAL,
            memo        TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
            updated_at  TEXT    DEFAULT (datetime('now', 'localtime')),
            UNIQUE(resident_id, record_date)
        )
    """)
    # 体重測定の対象者を管理するテーブル（ONにした人だけドロップダウンに表示する）
    c.execute("""
        CREATE TABLE IF NOT EXISTS weight_targets (
            resident_id INTEGER PRIMARY KEY,
            enabled     INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


def _backup_db():
    """起動時にDBをバックアップする。MAX_BACKUPS を超えた分は古い順に削除する"""
    if not os.path.exists(WEIGHT_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(WEIGHT_DB, backup_file)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


def get_conn():
    """体重記録DB への接続を返す（列名アクセス対応）"""
    conn = sqlite3.connect(WEIGHT_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_residents_conn():
    """入居者マスターDB への接続を返す（読み取り専用）"""
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# Y 軸スケール計算ヘルパー
# =============================================================================

def calc_y_scale(weight_vals):
    """
    体重値のリストから、グラフのY軸範囲（整数kg単位）を計算して返す。
    データがない場合はデフォルト範囲を返す。

    戻り値: (y_min, y_max) どちらも int
    """
    if weight_vals:
        y_min = int(max(0.0, min(weight_vals) - GRAPH_Y_MARGIN))
        y_max = int(max(weight_vals) + GRAPH_Y_MARGIN) + 1
    else:
        y_min = int(GRAPH_DEFAULT_MIN)
        y_max = int(GRAPH_DEFAULT_MAX)
    return y_min, y_max


# =============================================================================
# 印刷用 HTML 生成
# =============================================================================

def _build_svg_month_graph(data, year, month, y_min, y_max, width=520, height=260):
    """
    月間体重データ（{day: weight_kg}）から SVG グラフを生成して返す。

    引数:
        data   : {日: 体重(float)} の辞書
        year   : 年（int）
        month  : 月（int）
        y_min  : グラフY軸の最小値（int）
        y_max  : グラフY軸の最大値（int）
    """
    days_in_month = calendar.monthrange(year, month)[1]
    ml = 50; mr = 20; mt = 20; mb = 34
    gw = width - ml - mr
    gh = height - mt - mb

    def yp(kg):
        if y_max == y_min:
            return mt + gh / 2
        return mt + (y_max - kg) / (y_max - y_min) * gh

    def xp(day):
        return ml + (day - 1) / max(days_in_month - 1, 1) * gw

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="font-family:\'MS Gothic\',sans-serif;font-size:10px;">']
    lines.append(f'<rect x="{ml}" y="{mt}" width="{gw}" height="{gh}" '
                 f'fill="white" stroke="#BBBBBB" stroke-width="1"/>')

    kg_val = float(y_min)
    while kg_val <= y_max + 0.01:
        y = yp(kg_val)
        lines.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+gw}" y2="{y:.1f}" '
                     f'stroke="#E0E0E0" stroke-dasharray="2,4" stroke-width="1"/>')
        lines.append(f'<text x="{ml-4}" y="{y+3:.1f}" text-anchor="end" fill="#666">{kg_val:.1f}</text>')
        kg_val = round(kg_val + 1.0, 1)

    for day in range(1, days_in_month + 1, 5):
        x = xp(day)
        lines.append(f'<line x1="{x:.1f}" y1="{mt+gh}" x2="{x:.1f}" y2="{mt+gh+4}" '
                     f'stroke="#888" stroke-width="1"/>')
        lines.append(f'<text x="{x:.1f}" y="{mt+gh+16}" text-anchor="middle" fill="#555">{day}日</text>')

    pts = [(xp(d), yp(v)) for d, v in sorted(data.items()) if v is not None]
    if len(pts) >= 2:
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        lines.append(f'<polyline points="{polyline}" fill="none" stroke="#2E7D32" stroke-width="2"/>')
    for x, y in pts:
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2E7D32" stroke="#2E7D32"/>')

    lines.append('</svg>')
    return "\n".join(lines)


def _build_svg_year_graph(year_data, year, current_month, y_min, y_max, width=520, height=260):
    """
    年間体重データ（{"YYYY-MM-DD": weight_kg}）から SVG グラフを生成して返す。

    引数:
        year_data     : {"YYYY-MM-DD": 体重(float)} の辞書
        year          : 年（int）
        current_month : ハイライトする月（int）
        y_min         : Y軸最小値（int）
        y_max         : Y軸最大値（int）
    """
    is_leap     = calendar.isleap(year)
    total_days  = 366 if is_leap else 365
    year_start  = date(year, 1, 1)
    ml = 50; mr = 20; mt = 20; mb = 34
    gw = width - ml - mr
    gh = height - mt - mb

    def doy(date_str):
        """日付文字列を年初からの経過日数（1始まり）に変換する"""
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (d - year_start).days + 1

    def yp(kg):
        if y_max == y_min:
            return mt + gh / 2
        return mt + (y_max - kg) / (y_max - y_min) * gh

    def xp(day_num):
        return ml + (day_num - 1) / max(total_days - 1, 1) * gw

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="font-family:\'MS Gothic\',sans-serif;font-size:10px;">']

    # 現在の月の背景ハイライト
    m_start_doy = (date(year, current_month, 1) - year_start).days + 1
    m_end_day   = calendar.monthrange(year, current_month)[1]
    m_end_doy   = (date(year, current_month, m_end_day) - year_start).days + 1
    lines.append(f'<rect x="{xp(m_start_doy):.1f}" y="{mt}" '
                 f'width="{xp(m_end_doy)-xp(m_start_doy):.1f}" height="{gh}" '
                 f'fill="#E8F5E9" opacity="0.7"/>')

    lines.append(f'<rect x="{ml}" y="{mt}" width="{gw}" height="{gh}" '
                 f'fill="none" stroke="#BBBBBB" stroke-width="1"/>')

    # Y 軸グリッドと目盛り
    kg_val = float(y_min)
    while kg_val <= y_max + 0.01:
        y = yp(kg_val)
        lines.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml+gw}" y2="{y:.1f}" '
                     f'stroke="#E0E0E0" stroke-dasharray="2,4" stroke-width="1"/>')
        lines.append(f'<text x="{ml-4}" y="{y+3:.1f}" text-anchor="end" fill="#666">{kg_val:.1f}</text>')
        kg_val = round(kg_val + 1.0, 1)

    # 月の区切り線とラベル
    for m in range(1, 13):
        d1   = (date(year, m, 1) - year_start).days + 1
        x    = xp(d1)
        color = "#AAAAAA" if m == current_month else "#DDDDDD"
        lines.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{mt+gh}" '
                     f'stroke="{color}" stroke-width="1"/>')
        lines.append(f'<text x="{x+2:.1f}" y="{mt+gh+15}" fill="#555">{m}月</text>')

    # 折れ線グラフ
    pts = [(xp(doy(ds)), yp(kg)) for ds, kg in sorted(year_data.items()) if kg is not None]
    if len(pts) >= 2:
        polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        lines.append(f'<polyline points="{polyline}" fill="none" stroke="#2E7D32" stroke-width="2"/>')
    for x, y in pts:
        lines.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#2E7D32" stroke="#2E7D32"/>')

    lines.append('</svg>')
    return "\n".join(lines)


def generate_print_html_month(resident_name, year, month, records):
    """
    月間の印刷用 HTML 文字列を生成して返す。

    引数:
        resident_name : 利用者名（文字列）
        year, month   : 対象年月（int）
        records       : {day: {"weight_kg": float|None, "memo": str}}
    """
    days_in_month = calendar.monthrange(year, month)[1]

    weight_vals = [r["weight_kg"] for r in records.values() if r.get("weight_kg") is not None]
    y_min, y_max = calc_y_scale(weight_vals)

    graph_data = {d: r.get("weight_kg") for d, r in records.items()}
    svg_graph  = _build_svg_month_graph(graph_data, year, month, y_min, y_max)

    table_rows = []
    for day in range(1, days_in_month + 1):
        r      = records.get(day, {})
        kg_v   = r.get("weight_kg")
        memo   = r.get("memo") or ""
        kg_str = f"{kg_v:.1f}" if kg_v is not None else ""
        table_rows.append(
            f'<tr><td class="date">{month}月{day}日</td>'
            f'<td class="num">{kg_str}</td>'
            f'<td class="memo">{memo}</td></tr>'
        )

    avg_w = f"{sum(weight_vals)/len(weight_vals):.1f}" if weight_vals else "—"
    max_w = f"{max(weight_vals):.1f}"                  if weight_vals else "—"
    min_w = f"{min(weight_vals):.1f}"                  if weight_vals else "—"

    return _html_template(
        title=f"体重測定記録 {resident_name} {year}年{month}月",
        h1=f"体重測定記録　{resident_name}　{year}年{month}月",
        table_rows=table_rows,
        summary=f"平均 {avg_w} kg　／　最大 {max_w} kg　／　最小 {min_w} kg",
        svg=svg_graph,
        legend="体重（kg）の月間推移",
    )


def generate_print_html_year(resident_name, year, month, year_data):
    """
    年間の印刷用 HTML 文字列を生成して返す。

    引数:
        resident_name : 利用者名（文字列）
        year          : 対象年（int）
        month         : 現在選択中の月（ハイライト用）
        year_data     : {"YYYY-MM-DD": weight_kg} の辞書
    """
    weight_vals = [v for v in year_data.values() if v is not None]
    y_min, y_max = calc_y_scale(weight_vals)

    svg_graph = _build_svg_year_graph(year_data, year, month, y_min, y_max)

    # 月別平均テーブル
    monthly_avgs = {}
    for ds, kg in year_data.items():
        if kg is not None:
            m = int(ds[5:7])
            monthly_avgs.setdefault(m, []).append(kg)

    table_rows = []
    for m in range(1, 13):
        vals   = monthly_avgs.get(m, [])
        avg_s  = f"{sum(vals)/len(vals):.1f}" if vals else "—"
        max_s  = f"{max(vals):.1f}"           if vals else "—"
        min_s  = f"{min(vals):.1f}"           if vals else "—"
        count  = str(len(vals))               if vals else "—"
        hi = ' style="background:#E8F5E9;"' if m == month else ""
        table_rows.append(
            f'<tr{hi}><td class="date">{m}月</td>'
            f'<td class="num">{count}件</td>'
            f'<td class="num">{avg_s}</td>'
            f'<td class="num">{max_s}</td>'
            f'<td class="num">{min_s}</td></tr>'
        )

    avg_w = f"{sum(weight_vals)/len(weight_vals):.1f}" if weight_vals else "—"
    max_w = f"{max(weight_vals):.1f}"                  if weight_vals else "—"
    min_w = f"{min(weight_vals):.1f}"                  if weight_vals else "—"

    # 年間テーブルはヘッダーを変えるため別途組み立てる
    table_html = (
        '<table><thead><tr>'
        '<th>月</th><th>件数</th><th>平均(kg)</th><th>最大(kg)</th><th>最小(kg)</th>'
        '</tr></thead><tbody>'
        + "".join(table_rows)
        + '</tbody></table>'
    )

    return _html_template(
        title=f"体重測定記録 {resident_name} {year}年（年間）",
        h1=f"体重測定記録　{resident_name}　{year}年（年間）",
        table_rows=None,          # カスタムテーブルを使うので None
        summary=f"年間　平均 {avg_w} kg　最大 {max_w} kg　最小 {min_w} kg",
        svg=svg_graph,
        legend=f"体重（kg）の年間推移　（緑ハイライト＝{month}月）",
        custom_table=table_html,
    )


def _html_template(title, h1, table_rows, summary, svg, legend, custom_table=None):
    """
    印刷用 HTML のひな形を組み立てて文字列で返す。
    table_rows が None のときは custom_table をそのまま使う。
    """
    if custom_table is not None:
        table_block = custom_table
    else:
        rows_html = "".join(table_rows)
        table_block = (
            '<table><thead><tr>'
            '<th>日付</th><th>体重 (kg)</th><th style="width:160px">メモ</th>'
            '</tr></thead><tbody>'
            + rows_html
            + '</tbody></table>'
        )

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "MS Gothic", "Meiryo", sans-serif; font-size: 10pt; color: #222; }}
  h1 {{ font-size: 13pt; text-align: center; margin-bottom: 10px;
        border-bottom: 2px solid #2E7D32; padding-bottom: 4px; color: #2E7D32; }}
  .main-area {{ display: flex; gap: 14px; align-items: flex-start; }}
  .table-wrap {{ flex: 0 0 auto; }}
  .graph-wrap {{ flex: 1 1 auto; }}
  table {{ border-collapse: collapse; font-size: 9pt; width: 100%; }}
  th {{ background: #2E7D32; color: white; padding: 3px 8px; text-align: center; font-weight: normal; }}
  td {{ padding: 2px 6px; border-bottom: 1px solid #DDD; }}
  td.date {{ text-align: center; white-space: nowrap; }}
  td.num  {{ text-align: center; width: 60px; }}
  td.memo {{ font-size: 8.5pt; color: #444; }}
  tr:nth-child(even) {{ background: #F5FFF5; }}
  .summary {{ margin-top: 6px; font-size: 9pt; text-align: right; color: #555; }}
  .legend  {{ font-size: 8.5pt; color: #666; margin-top: 4px; }}
  @media print {{ .no-print {{ display: none; }} }}
</style>
</head>
<body>
<h1>{h1}</h1>
<div class="main-area">
  <div class="table-wrap">
    {table_block}
    <div class="summary">{summary}</div>
  </div>
  <div class="graph-wrap">
    {svg}
    <div class="legend">{legend}</div>
  </div>
</div>
<p class="no-print" style="margin-top:16px;color:#888;font-size:9pt;">
  ※ 印刷するにはブラウザの Ctrl+P をお使いください。用紙サイズ：A4横、余白：最小 を推奨します。
</p>
</body>
</html>"""


# =============================================================================
# 対象者設定ダイアログ
# =============================================================================

class WeightTargetDialog(tk.Toplevel):
    """
    体重測定の対象者を選ぶダイアログ。
    入居中の全員をチェックボックスで表示し、ONにした人だけが
    メイン画面のドロップダウンに表示されるようになる。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("体重測定 対象者設定")
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self._center(parent)
        self.wait_window()

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        """UI を構築する"""
        tk.Label(self, text="体重測定の対象者を選んでください",
                 font=FONT_BOLD, padx=20, pady=10).pack()
        tk.Label(self,
                 text="チェックを入れた方がドロップダウンに表示されます。\n"
                      "（チェックを外しても、その方の記録データは消えません）",
                 font=FONT_SMALL, fg="#555", padx=20, justify="left").pack(anchor="w")

        frame_outer = tk.Frame(self, padx=20, pady=6)
        frame_outer.pack(fill="both")

        canvas = tk.Canvas(frame_outer, highlightthickness=0, width=280)
        vsb    = ttk.Scrollbar(frame_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both")
        vsb.pack(side="left", fill="y")

        inner = tk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        if not os.path.exists(RESIDENTS_DB):
            tk.Label(inner, text="入居者DBが見つかりません", font=FONT).pack()
            return

        r_conn   = get_residents_conn()
        all_rows = r_conn.execute(
            "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY room_number"
        ).fetchall()
        r_conn.close()

        w_conn      = get_conn()
        target_rows = w_conn.execute(
            "SELECT resident_id, enabled FROM weight_targets"
        ).fetchall()
        w_conn.close()

        saved      = {r["resident_id"]: bool(r["enabled"]) for r in target_rows}
        self._vars = {}

        for i, row in enumerate(all_rows):
            bg  = "#FFFFFF" if i % 2 == 0 else "#F0F4FA"
            var = tk.BooleanVar(value=saved.get(row["id"], True))
            self._vars[row["id"]] = var
            tk.Checkbutton(inner, text=row["name"], variable=var,
                           font=FONT, bg=bg, anchor="w",
                           activebackground=bg, padx=8, pady=3).pack(fill="x")

        row_h  = 30
        height = min(len(all_rows), 12) * row_h + 4
        canvas.configure(height=height)

        btn_row = tk.Frame(self, padx=20, pady=4)
        btn_row.pack()
        tk.Button(btn_row, text="全員選択", font=FONT_SMALL, relief="flat",
                  bg="#AAAAAA", fg="white", padx=6, pady=2, cursor="hand2",
                  command=lambda: [v.set(True)  for v in self._vars.values()]).pack(side="left", padx=4)
        tk.Button(btn_row, text="全員解除", font=FONT_SMALL, relief="flat",
                  bg="#AAAAAA", fg="white", padx=6, pady=2, cursor="hand2",
                  command=lambda: [v.set(False) for v in self._vars.values()]).pack(side="left", padx=4)

        footer = tk.Frame(self, pady=10)
        footer.pack()
        tk.Button(footer, text="保存して閉じる", font=FONT_BOLD, relief="flat",
                  bg="#2E7D32", fg="white", padx=12, pady=4, cursor="hand2",
                  command=self._save).pack(side="left", padx=8)
        tk.Button(footer, text="キャンセル", font=FONT, relief="flat",
                  padx=8, pady=4, cursor="hand2",
                  command=self.destroy).pack(side="left", padx=8)

    def _save(self):
        """チェックの状態を weight_targets テーブルに保存して閉じる"""
        conn = get_conn()
        for rid, var in self._vars.items():
            conn.execute(
                """INSERT INTO weight_targets (resident_id, enabled) VALUES (?, ?)
                   ON CONFLICT(resident_id) DO UPDATE SET enabled = excluded.enabled""",
                (rid, 1 if var.get() else 0)
            )
        conn.commit()
        conn.close()
        self.destroy()


# =============================================================================
# メインアプリ
# =============================================================================

class WeightApp(tk.Tk):
    """体重測定記録アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("体重測定記録")
        self.geometry("1050x730")
        self.resizable(True, True)
        self.configure(bg="#F5F7FA")

        self.selected_resident_id   = None
        self.selected_resident_name = ""
        self._residents  = {}
        self.selected_year  = tk.IntVar(value=date.today().year)
        self.selected_month = tk.IntVar(value=date.today().month)

        # グラフ表示モード："year"（年間）または "month"（月間）
        # デフォルトは年間表示
        self.graph_mode = "year"

        self._grid_rows = []

        self._build_ui()
        self._load_residents()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        """画面全体のUIを組み立てる"""

        # ---- ヘッダー ----
        header = tk.Frame(self, bg="#2E7D32", pady=8)
        header.pack(fill="x")
        tk.Label(header, text="体重測定記録", font=FONT_TITLE,
                 bg="#2E7D32", fg="white").pack(side="left", padx=20)

        # ---- コントロールバー ----
        ctrl = tk.Frame(self, bg="#E8EDF2", pady=6)
        ctrl.pack(fill="x", padx=10, pady=(6, 0))

        tk.Label(ctrl, text="利用者：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(10, 2))
        self.resident_cb = ttk.Combobox(ctrl, font=FONT, width=16, state="readonly")
        self.resident_cb.pack(side="left", padx=(0, 16))
        self.resident_cb.bind("<<ComboboxSelected>>", self._on_resident_changed)

        tk.Label(ctrl, text="年：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(0, 2))
        tk.Spinbox(ctrl, textvariable=self.selected_year,
                   from_=2020, to=2099, width=6, font=FONT,
                   command=self._refresh).pack(side="left", padx=(0, 4))

        tk.Label(ctrl, text="月：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(0, 2))
        month_cb = ttk.Combobox(ctrl, textvariable=self.selected_month,
                                values=list(range(1, 13)), width=4, font=FONT, state="readonly")
        month_cb.pack(side="left", padx=(0, 4))
        month_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh())

        tk.Button(ctrl, text="表示", font=FONT, relief="flat",
                  bg="#2E7D32", fg="white", padx=8, pady=2,
                  cursor="hand2", command=self._refresh).pack(side="left", padx=(4, 0))

        tk.Button(ctrl, text="対象者設定", font=FONT, relief="flat",
                  bg="#7B7B7B", fg="white", padx=8, pady=2,
                  cursor="hand2", command=self._open_target_settings).pack(side="left", padx=(10, 0))

        # 右側ボタン
        tk.Button(ctrl, text="  まとめて保存  ", font=FONT_BOLD, relief="flat",
                  bg="#1B5E20", fg="white", padx=10, pady=2,
                  cursor="hand2", command=self._save_all).pack(side="right", padx=(4, 10))

        tk.Button(ctrl, text="  印 刷  ", font=FONT_BOLD, relief="flat",
                  bg="#5C6BC0", fg="white", padx=10, pady=2,
                  cursor="hand2", command=self._print_preview).pack(side="right", padx=4)

        # ---- メイン部（左：入力グリッド、右：グラフ）----
        main = tk.Frame(self, bg="#F5F7FA")
        main.pack(fill="both", expand=True, padx=10, pady=6)

        # 左側：一覧入力グリッド
        left_frame = tk.Frame(main, bg="#F5F7FA")
        left_frame.pack(side="left", fill="y")

        # 列ヘッダー
        header_row = tk.Frame(left_frame, bg="#C8DCC8")
        header_row.pack(fill="x")
        for text in ["日付", "体重 (kg)", "メモ"]:
            tk.Label(header_row, text=text, font=FONT_BOLD,
                     bg="#C8DCC8", anchor="center",
                     relief="flat", padx=4, pady=3).pack(side="left")

        # スクロール可能グリッドエリア
        grid_container = tk.Frame(left_frame, bg="#F5F7FA")
        grid_container.pack(fill="y", expand=True)

        self.grid_canvas = tk.Canvas(grid_container, bg="#F5F7FA",
                                     highlightthickness=0, width=390)
        vsb = ttk.Scrollbar(grid_container, orient="vertical", command=self.grid_canvas.yview)
        self.grid_canvas.configure(yscrollcommand=vsb.set)
        self.grid_canvas.pack(side="left", fill="y", expand=True)
        vsb.pack(side="left", fill="y")

        self.grid_frame = tk.Frame(self.grid_canvas, bg="#F5F7FA")
        self.grid_canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        )
        self.grid_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.grid_frame.bind("<MouseWheel>",  self._on_mousewheel)

        # 右側：グラフエリア
        right_frame = tk.Frame(main, bg="#F5F7FA", padx=10)
        right_frame.pack(side="left", fill="both", expand=True)

        # グラフ切り替えボタン行
        graph_ctrl = tk.Frame(right_frame, bg="#F5F7FA")
        graph_ctrl.pack(fill="x", pady=(0, 4))

        tk.Label(graph_ctrl, text="グラフ：", font=FONT, bg="#F5F7FA").pack(side="left")

        self.btn_year = tk.Button(
            graph_ctrl, text="年間", font=FONT_BOLD, relief="flat",
            bg="#2E7D32", fg="white", padx=10, pady=2, cursor="hand2",
            command=self._switch_to_year
        )
        self.btn_year.pack(side="left", padx=(2, 0))

        self.btn_month = tk.Button(
            graph_ctrl, text="月間", font=FONT, relief="flat",
            bg="#AAAAAA", fg="white", padx=10, pady=2, cursor="hand2",
            command=self._switch_to_month
        )
        self.btn_month.pack(side="left", padx=(4, 0))

        self.graph_title_lbl = tk.Label(
            graph_ctrl, text="", font=FONT_SMALL, bg="#F5F7FA", fg="#555"
        )
        self.graph_title_lbl.pack(side="left", padx=(14, 0))

        self.canvas = tk.Canvas(right_frame, bg="white", relief="sunken", bd=1)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self._draw_graph())

        self.stat_label = tk.Label(right_frame, text="", font=FONT_SMALL, bg="#F5F7FA", fg="#555")
        self.stat_label.pack(anchor="w", pady=(4, 0))

    def _on_mousewheel(self, event):
        """マウスホイールでグリッドをスクロールする"""
        self.grid_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # グラフモード切り替え
    # ------------------------------------------------------------------

    def _switch_to_year(self):
        """年間グラフに切り替える"""
        self.graph_mode = "year"
        self.btn_year.configure(bg="#2E7D32", font=FONT_BOLD)
        self.btn_month.configure(bg="#AAAAAA", font=FONT)
        self._draw_graph()

    def _switch_to_month(self):
        """月間グラフに切り替える"""
        self.graph_mode = "month"
        self.btn_month.configure(bg="#2E7D32", font=FONT_BOLD)
        self.btn_year.configure(bg="#AAAAAA",  font=FONT)
        self._draw_graph()

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
            weight_var = tk.StringVar()
            memo_var   = tk.StringVar()
            bg         = ROW_BG_EVEN if day % 2 == 0 else ROW_BG_ODD
            row_frame  = tk.Frame(self.grid_frame, bg=bg, pady=1)
            row_frame.pack(fill="x")

            tk.Label(row_frame, text=f"{month}月{day}日",
                     font=FONT, bg=bg, width=7, anchor="center").pack(side="left", padx=(4, 2))

            tk.Entry(row_frame, textvariable=weight_var,
                     font=FONT, width=8, justify="center",
                     bg=bg, relief="solid", bd=1).pack(side="left", padx=2, ipady=2)

            tk.Entry(row_frame, textvariable=memo_var,
                     font=FONT, width=20, bg=bg, relief="solid", bd=1).pack(side="left", padx=(2, 4), ipady=2)

            for w in row_frame.winfo_children():
                w.bind("<MouseWheel>", self._on_mousewheel)
            row_frame.bind("<MouseWheel>", self._on_mousewheel)

            self._grid_rows.append({
                "day": day, "weight_var": weight_var,
                "memo_var": memo_var, "row_frame": row_frame,
            })

        self.grid_canvas.update_idletasks()
        self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all"))
        self.grid_canvas.yview_moveto(0)

    def _load_into_grid(self):
        """DBから当月データを読み込んで各行の Entry にセットする"""
        if not self.selected_resident_id or not self._grid_rows:
            return
        year  = self.selected_year.get()
        month = self.selected_month.get()
        conn  = get_conn()
        rows  = conn.execute(
            """SELECT record_date, weight_kg, memo FROM weight_records
               WHERE resident_id = ? AND record_date LIKE ?""",
            (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
        ).fetchall()
        conn.close()

        record_map = {int(r["record_date"].split("-")[2]): r for r in rows}

        for row in self._grid_rows:
            day = row["day"]
            if day in record_map:
                r  = record_map[day]
                kg = r["weight_kg"]
                row["weight_var"].set(f"{kg:.1f}" if kg is not None else "")
                row["memo_var"].set(r["memo"] or "")
            else:
                row["weight_var"].set("")
                row["memo_var"].set("")

    # ------------------------------------------------------------------
    # 表示の更新
    # ------------------------------------------------------------------

    def _refresh(self):
        """グリッドとグラフを最新データで再描画する"""
        self._build_grid()
        self._load_into_grid()
        self._draw_graph()

    def _draw_graph(self):
        """現在のモードに応じてグラフを描画する"""
        if self.graph_mode == "year":
            self._draw_year_graph()
        else:
            self._draw_month_graph()

    def _draw_year_graph(self):
        """
        年間グラフを Canvas に描画する。
        選択中の年の全体重データを折れ線で表示し、選択中の月を緑でハイライトする。
        """
        c = self.canvas
        c.delete("all")
        width  = c.winfo_width()
        height = c.winfo_height()
        if width < 100 or height < 100:
            return

        year          = self.selected_year.get()
        current_month = self.selected_month.get()
        is_leap       = calendar.isleap(year)
        total_days    = 366 if is_leap else 365
        year_start    = date(year, 1, 1)

        self.graph_title_lbl.config(text=f"{year}年（{current_month}月を選択中）")

        ml = 60; mr = 20; mt = 44; mb = 48
        gw = width  - ml - mr
        gh = height - mt - mb

        if not self.selected_resident_id:
            return

        conn = get_conn()
        rows = conn.execute(
            """SELECT record_date, weight_kg FROM weight_records
               WHERE resident_id = ? AND record_date LIKE ?
               ORDER BY record_date""",
            (self.selected_resident_id, f"{year:04d}-%")
        ).fetchall()
        conn.close()

        weight_vals = [r["weight_kg"] for r in rows if r["weight_kg"] is not None]
        y_min, y_max = calc_y_scale(weight_vals)

        def yp(kg):
            if y_max == y_min:
                return mt + gh / 2
            return mt + (y_max - kg) / (y_max - y_min) * gh

        def doy(date_str):
            """日付文字列を年初からの経過日数（1始まり）に変換する"""
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return (d - year_start).days + 1

        def xp(day_num):
            return ml + (day_num - 1) / max(total_days - 1, 1) * gw

        # 選択中の月をハイライト
        m_start_doy = (date(year, current_month, 1) - year_start).days + 1
        m_end_day   = calendar.monthrange(year, current_month)[1]
        m_end_doy   = (date(year, current_month, m_end_day) - year_start).days + 1
        c.create_rectangle(xp(m_start_doy), mt, xp(m_end_doy), mt + gh,
                           fill="#E8F5E9", outline="")

        # グラフ枠
        c.create_rectangle(ml, mt, ml + gw, mt + gh, fill="", outline="#CCCCCC")
        c.create_text(width // 2, 22,
                      text=f"{year}年　体重年間グラフ（{self.selected_resident_name}）",
                      font=FONT_BOLD, fill="#333")

        # Y 軸グリッドと目盛り
        kg_val = float(y_min)
        while kg_val <= y_max + 0.01:
            y = yp(kg_val)
            c.create_line(ml, y, ml + gw, y, fill="#E0E0E0", dash=(2, 4))
            c.create_text(ml - 6, y, text=f"{kg_val:.1f}",
                          font=FONT_SMALL, anchor="e", fill="#666")
            kg_val = round(kg_val + 1.0, 1)

        # 月の区切り線とラベル
        for m in range(1, 13):
            d1   = (date(year, m, 1) - year_start).days + 1
            x    = xp(d1)
            color = "#388E3C" if m == current_month else "#DDDDDD"
            width_line = 1.5 if m == current_month else 1
            c.create_line(x, mt, x, mt + gh, fill=color, dash=(4, 3), width=width_line)
            c.create_text(x + 3, mt + gh + 14, text=f"{m}月",
                          font=FONT_SMALL, anchor="w", fill="#555")

        # Y 軸ラベル
        c.create_text(14, mt + gh // 2, text="体重\n(kg)",
                      font=FONT_SMALL, fill="#666", justify="center")

        if not weight_vals:
            c.create_text(width // 2, mt + gh // 2,
                          text="データがありません", font=FONT, fill="#AAAAAA")
            self.stat_label.config(text="")
            return

        # データ点と折れ線
        data = {doy(r["record_date"]): r["weight_kg"]
                for r in rows if r["weight_kg"] is not None}
        pts = [(xp(d), yp(v)) for d, v in sorted(data.items())]

        if len(pts) >= 2:
            for i in range(len(pts) - 1):
                c.create_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                              fill="#2E7D32", width=2)
        for x, y in pts:
            c.create_oval(x - 3, y - 3, x + 3, y + 3,
                          fill="#2E7D32", outline="#2E7D32")

        # 統計
        avg_w = sum(weight_vals) / len(weight_vals)
        self.stat_label.config(
            text=(f"年間 {len(weight_vals)}件　"
                  f"平均 {avg_w:.1f} kg　最大 {max(weight_vals):.1f} kg　"
                  f"最小 {min(weight_vals):.1f} kg")
        )

    def _draw_month_graph(self):
        """
        月間グラフを Canvas に描画する。
        選択中の年月のデータを折れ線で表示する。
        """
        c = self.canvas
        c.delete("all")
        width  = c.winfo_width()
        height = c.winfo_height()
        if width < 100 or height < 100:
            return

        year          = self.selected_year.get()
        month         = self.selected_month.get()
        days_in_month = calendar.monthrange(year, month)[1]

        self.graph_title_lbl.config(text=f"{year}年{month}月")

        ml = 60; mr = 20; mt = 44; mb = 48
        gw = width  - ml - mr
        gh = height - mt - mb

        if not self.selected_resident_id:
            return

        conn = get_conn()
        rows = conn.execute(
            """SELECT record_date, weight_kg FROM weight_records
               WHERE resident_id = ? AND record_date LIKE ?
               ORDER BY record_date""",
            (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
        ).fetchall()
        conn.close()

        weight_vals = [r["weight_kg"] for r in rows if r["weight_kg"] is not None]
        y_min, y_max = calc_y_scale(weight_vals)

        def yp(kg):
            if y_max == y_min:
                return mt + gh / 2
            return mt + (y_max - kg) / (y_max - y_min) * gh

        def xp(day):
            return ml + (day - 1) / max(days_in_month - 1, 1) * gw

        # グラフ枠
        c.create_rectangle(ml, mt, ml + gw, mt + gh, fill="white", outline="#CCCCCC")
        c.create_text(width // 2, 22,
                      text=f"{year}年{month}月　体重グラフ（{self.selected_resident_name}）",
                      font=FONT_BOLD, fill="#333")

        # Y 軸グリッドと目盛り
        kg_val = float(y_min)
        while kg_val <= y_max + 0.01:
            y = yp(kg_val)
            c.create_line(ml, y, ml + gw, y, fill="#E0E0E0", dash=(2, 4))
            c.create_text(ml - 6, y, text=f"{kg_val:.1f}",
                          font=FONT_SMALL, anchor="e", fill="#666")
            kg_val = round(kg_val + 1.0, 1)

        # X 軸目盛り（5日ごと）
        for day in range(1, days_in_month + 1, 5):
            x = xp(day)
            c.create_line(x, mt + gh, x, mt + gh + 4, fill="#888")
            c.create_text(x, mt + gh + 16, text=f"{day}日", font=FONT_SMALL, fill="#555")

        # Y 軸ラベル
        c.create_text(14, mt + gh // 2, text="体重\n(kg)",
                      font=FONT_SMALL, fill="#666", justify="center")

        if not weight_vals:
            c.create_text(width // 2, mt + gh // 2,
                          text="データがありません", font=FONT, fill="#AAAAAA")
            self.stat_label.config(text="")
            return

        # データ点と折れ線
        data = {}
        for r in rows:
            if r["weight_kg"] is not None:
                day = int(r["record_date"].split("-")[2])
                data[day] = r["weight_kg"]

        pts = [(xp(d), yp(v)) for d, v in sorted(data.items())]
        if len(pts) >= 2:
            for i in range(len(pts) - 1):
                c.create_line(pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1],
                              fill="#2E7D32", width=2)
        for x, y in pts:
            c.create_oval(x - 3, y - 3, x + 3, y + 3,
                          fill="#2E7D32", outline="#2E7D32")

        # 統計
        avg_w = sum(weight_vals) / len(weight_vals)
        self.stat_label.config(
            text=(f"平均 {avg_w:.1f} kg　最大 {max(weight_vals):.1f} kg　"
                  f"最小 {min(weight_vals):.1f} kg")
        )

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
        weight_targets テーブルで enabled=1 に設定された人だけをドロップダウンに表示する。
        まだ一度も設定していない場合は全員を対象にする。
        """
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "注意",
                "入居者マスターDBが見つかりません。\n先に入居者マスターアプリを起動してください。"
            )
            return

        r_conn   = get_residents_conn()
        all_rows = r_conn.execute(
            "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY room_number"
        ).fetchall()
        r_conn.close()

        w_conn      = get_conn()
        target_rows = w_conn.execute(
            "SELECT resident_id, enabled FROM weight_targets"
        ).fetchall()
        w_conn.close()

        if target_rows:
            enabled_ids = {r["resident_id"] for r in target_rows if r["enabled"]}
            filtered    = [r for r in all_rows if r["id"] in enabled_ids]
        else:
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
            self.selected_resident_id   = None
            self.selected_resident_name = ""
            self._build_grid()
            self._draw_graph()

    def _open_target_settings(self):
        """対象者設定ダイアログを開く"""
        WeightTargetDialog(self)
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
            kg_str   = row["weight_var"].get().strip()
            memo_str = row["memo_var"].get().strip()

            if kg_str == "" and memo_str == "":
                to_delete.append(f"{year:04d}-{month:02d}-{day:02d}")
                continue

            kg_val = None
            if kg_str != "":
                try:
                    kg_val = float(kg_str)
                    if not (1.0 <= kg_val <= 300.0):
                        raise ValueError
                except ValueError:
                    errors.append(
                        f"{month}月{day}日：体重「{kg_str}」が正しくありません"
                        f"（1.0〜300.0 の数値で入力してください）"
                    )
                    continue

            record_date = f"{year:04d}-{month:02d}-{day:02d}"
            to_save.append((
                self.selected_resident_id, record_date,
                kg_val,
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
                """INSERT INTO weight_records
                       (resident_id, record_date, weight_kg, memo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(resident_id, record_date) DO UPDATE SET
                       weight_kg  = excluded.weight_kg,
                       memo       = excluded.memo,
                       updated_at = excluded.updated_at""",
                record
            )
        for record_date in to_delete:
            conn.execute(
                "DELETE FROM weight_records WHERE resident_id = ? AND record_date = ?",
                (self.selected_resident_id, record_date)
            )
        conn.commit()
        conn.close()

        self._draw_graph()
        messagebox.showinfo("保存完了", f"{len(to_save)}件の記録を保存しました。")

    # ------------------------------------------------------------------
    # 印刷プレビュー（現在のグラフモードに合わせて出力）
    # ------------------------------------------------------------------

    def _print_preview(self):
        """
        印刷用HTMLを一時ファイルに出力し、既定のブラウザで開く。
        年間グラフ表示中は年間の月別集計表＋年間グラフを、
        月間グラフ表示中は月間の日別表＋月間グラフを出力する。
        """
        if not self.selected_resident_id:
            messagebox.showwarning("確認", "利用者を選択してください。")
            return

        year  = self.selected_year.get()
        month = self.selected_month.get()

        if self.graph_mode == "year":
            # 年間の全データを取得
            conn = get_conn()
            rows = conn.execute(
                """SELECT record_date, weight_kg, memo FROM weight_records
                   WHERE resident_id = ? AND record_date LIKE ?
                   ORDER BY record_date""",
                (self.selected_resident_id, f"{year:04d}-%")
            ).fetchall()
            conn.close()

            year_data = {r["record_date"]: r["weight_kg"] for r in rows}
            html = generate_print_html_year(
                self.selected_resident_name, year, month, year_data
            )
            prefix = "weight_year_print_"
        else:
            # 月間データを取得
            conn = get_conn()
            rows = conn.execute(
                """SELECT record_date, weight_kg, memo FROM weight_records
                   WHERE resident_id = ? AND record_date LIKE ?
                   ORDER BY record_date""",
                (self.selected_resident_id, f"{year:04d}-{month:02d}-%")
            ).fetchall()
            conn.close()

            records = {}
            for r in rows:
                day = int(r["record_date"].split("-")[2])
                records[day] = {"weight_kg": r["weight_kg"], "memo": r["memo"] or ""}

            html = generate_print_html_month(
                self.selected_resident_name, year, month, records
            )
            prefix = "weight_month_print_"

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8",
            delete=False, prefix=prefix
        )
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = WeightApp()
    app.mainloop()
