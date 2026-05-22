"""
お出かけのお知らせ作成アプリ

グループホームの外出行事のお知らせ文書を作成する。
行き先・日程・時刻などを入力すると、印刷用のお知らせ文書が自動生成される。
ブラウザ経由でHTML形式のお知らせを表示・印刷できる。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
import json
import tempfile
import webbrowser
from datetime import datetime


# ===== 定数定義 =====

APP_TITLE = "お出かけのお知らせ作成"

# 設定ファイルの保存先（このファイルと同じフォルダ）
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

# フォント定義（MS Gothic で日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 9)

# カラー定義
COLOR_BG          = "#F5F7FA"
COLOR_HEADER      = "#2C5F8A"
COLOR_SECTION     = "#E8F0F8"
COLOR_BTN_PRIMARY = "#2C5F8A"
COLOR_BTN_GREEN   = "#27AE60"
COLOR_BTN_ORANGE  = "#E67E22"
COLOR_WHITE       = "#FFFFFF"
COLOR_BORDER      = "#C8D4E0"
COLOR_CALC_BG     = "#EAF4FF"   # 自動計算で埋まったフィールドの背景色


# ===== 設定の読み書き =====

def load_settings():
    """
    設定ファイル（settings.json）を読み込む。
    ファイルが存在しない場合はデフォルト値を返す。
    """
    defaults = {"facility_name": "", "staff_name": ""}
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults


def save_settings(data):
    """
    設定をファイルに保存する。

    Args:
        data (dict): 保存する設定内容（施設名など）
    """
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        messagebox.showerror("エラー", f"設定の保存に失敗しました。\n{e}")


# ===== 時刻・時間のユーティリティ =====

def parse_time_to_min(s):
    """
    「HH:MM」「H時M分」「H時」などの文字列を「深夜0時から何分か」に変換する。
    変換できない場合は None を返す。

    Args:
        s (str): 時刻文字列（例: "9:30", "14:00", "9時30分"）

    Returns:
        int or None: 深夜0時からの経過分数
    """
    s = s.strip()
    # HH:MM 形式
    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # ○時○分
    m = re.match(r'^(\d{1,2})時(\d{1,2})分$', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # ○時
    m = re.match(r'^(\d{1,2})時$', s)
    if m:
        return int(m.group(1)) * 60
    return None


def parse_duration_to_min(s):
    """
    「○時間○分」「H:MM」「○分」「○時間」などの所要時間文字列を分数に変換する。
    変換できない場合は None を返す。

    Args:
        s (str): 所要時間文字列（例: "1:30", "2時間", "45分", "1時間30分"）

    Returns:
        int or None: 分数（整数）
    """
    s = s.strip()
    # H:MM 形式
    m = re.match(r'^(\d+):(\d{2})$', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # ○時間○分
    m = re.match(r'^(\d+)時間(\d+)分$', s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    # ○時間
    m = re.match(r'^(\d+)時間$', s)
    if m:
        return int(m.group(1)) * 60
    # ○分
    m = re.match(r'^(\d+)分$', s)
    if m:
        return int(m.group(1))
    # 数字のみ（分として解釈）
    m = re.match(r'^(\d+)$', s)
    if m:
        return int(m.group(1))
    return None


def min_to_time_str(minutes):
    """
    深夜0時からの経過分数を「HH:MM」形式の文字列に変換する。

    Args:
        minutes (int): 経過分数

    Returns:
        str: 「HH:MM」形式（例: "09:30"）
    """
    h = (minutes // 60) % 24
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def min_to_duration_str(minutes):
    """
    分数を「○時間○分」形式の文字列に変換する。

    Args:
        minutes (int): 分数

    Returns:
        str: 「○時間○分」形式（例: "1時間30分"）
    """
    h = minutes // 60
    m = minutes % 60
    if h > 0 and m > 0:
        return f"{h}時間{m}分"
    elif h > 0:
        return f"{h}時間"
    else:
        return f"{m}分"


# ===== スケジュール自動計算ソルバー =====

def solve_schedule(D, Tg, A, E, L, Tb, R):
    """
    7つの値のうち入力されているものから残りを計算して返す。

    変数と関係式:
      D  = 出発時刻（分）
      Tg = 移動時間・行き（分）        →  A = D + Tg
      A  = 現地到着時刻（分）
      E  = 現地滞在時間（分）          →  L = A + E
      L  = 現地出発時刻（分）
      Tb = 移動時間・帰り（分）        →  R = L + Tb
      R  = 帰宅時刻（分）

    Args:
        D, Tg, A, E, L, Tb, R: それぞれ int または None

    Returns:
        tuple: (D, Tg, A, E, L, Tb, R) 計算後の値（計算できなかった箇所は None のまま）
    """
    # 矛盾なく解ける限りループで繰り返し導出する
    changed = True
    while changed:
        changed = False

        # 関係式1: A = D + Tg
        if A is None and D is not None and Tg is not None:
            A = D + Tg; changed = True
        elif Tg is None and D is not None and A is not None:
            Tg = A - D; changed = True
        elif D is None and A is not None and Tg is not None:
            D = A - Tg; changed = True

        # 関係式2: L = A + E
        if L is None and A is not None and E is not None:
            L = A + E; changed = True
        elif E is None and A is not None and L is not None:
            E = L - A; changed = True
        elif A is None and L is not None and E is not None:
            A = L - E; changed = True

        # 関係式3: R = L + Tb
        if R is None and L is not None and Tb is not None:
            R = L + Tb; changed = True
        elif Tb is None and L is not None and R is not None:
            Tb = R - L; changed = True
        elif L is None and R is not None and Tb is not None:
            L = R - Tb; changed = True

    return D, Tg, A, E, L, Tb, R


# ===== 費用計算ユーティリティ =====

def parse_amount(s):
    """
    金額文字列を整数に変換する。カンマや「円」を除去して数値を取り出す。
    変換できない場合は None を返す。

    Args:
        s (str): 金額文字列（例: "500", "1,000", "800円"）

    Returns:
        int or None
    """
    s = re.sub(r'[,円\s]', '', s.strip())
    if re.match(r'^\d+$', s):
        return int(s)
    return None


def format_amount(n):
    """
    整数の金額を「1,000円」形式の文字列に変換する。

    Args:
        n (int): 金額

    Returns:
        str: 「○,○○○円」形式
    """
    return f"{n:,}円"


# ===== HTML 生成 =====

def build_html(data):
    """
    入力データをもとにお知らせのHTML文書を生成する。

    Args:
        data (dict): フォームの入力値が入った辞書

    Returns:
        str: HTML文字列
    """
    facility  = data.get("facility_name", "")
    date_str  = data.get("date", "")
    dest      = data.get("destination", "")
    purpose   = data.get("purpose", "")
    depart    = data.get("depart_time", "")
    travel_go = data.get("travel_go", "")
    arrive    = data.get("arrive_time", "")
    stay      = data.get("stay_duration", "")
    leave     = data.get("leave_time", "")
    travel_bk = data.get("travel_back", "")
    ret       = data.get("return_time", "")
    gather    = data.get("gather_place", "")
    items     = data.get("items", "")
    cost_items = data.get("cost_items", [])   # [{name, amount}, ...]
    notes     = data.get("notes", "")
    staff     = data.get("staff_name", "")
    issued    = data.get("issued_date", "")

    def row(label, value, note=""):
        """テーブルの1行分のHTMLを生成するヘルパー"""
        if not value:
            return ""
        note_html = f'<span class="note">（{note}）</span>' if note else ""
        return f"""
        <tr>
            <th>{label}</th>
            <td>{value}{note_html}</td>
        </tr>"""

    # スケジュール行を組み立てる（値があるものだけ表示）
    schedule_rows = ""
    schedule_rows += row("出発",         depart, f"移動時間 約{travel_go}" if travel_go else "")
    schedule_rows += row("現地到着予定", arrive)
    schedule_rows += row("現地滞在時間", stay)
    schedule_rows += row("現地出発予定", leave, f"移動時間 約{travel_bk}" if travel_bk else "")
    schedule_rows += row("帰宅予定",     ret)

    # その他情報行
    other_rows = ""
    other_rows += row("集合場所", gather)
    other_rows += row("持ち物",   items)

    # 費用の表示テキストを組み立てる
    cost_display = ""
    valid_items = [(ci["name"], parse_amount(ci["amount"])) for ci in cost_items
                   if ci["name"].strip() or ci["amount"].strip()]
    if valid_items:
        parts = []
        total = 0
        for name, amt in valid_items:
            if amt is not None:
                parts.append(f"{name}：{format_amount(amt)}" if name else format_amount(amt))
                total += amt
            elif name:
                parts.append(name)
        cost_display = "　".join(parts)
        if len(valid_items) > 1 and any(a is not None for _, a in valid_items):
            cost_display += f"　（合計：{format_amount(total)}）"
    other_rows += row("費用", cost_display)

    # 備考欄（改行を <br> に変換）
    notes_html = ""
    if notes:
        notes_html = f"""
        <div class="notes-section">
            <p class="notes-label">■ 備考</p>
            <p class="notes-text">{notes.replace(chr(10), '<br>')}</p>
        </div>"""

    purpose_html = f'<p class="purpose">{purpose}</p>' if purpose else ""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>お出かけのお知らせ</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "MS Gothic", "游明朝", "Meiryo", sans-serif;
    font-size: 13pt;
    background: #fff;
    color: #222;
  }}
  .page {{
    width: 190mm;
    margin: 10mm auto;
    padding: 10mm 12mm;
  }}
  .header {{
    text-align: right;
    font-size: 11pt;
    color: #555;
    margin-bottom: 6mm;
  }}
  .title-block {{
    text-align: center;
    margin-bottom: 6mm;
  }}
  .title {{
    font-size: 20pt;
    font-weight: bold;
    letter-spacing: 4px;
    border-bottom: 3px solid #2C5F8A;
    display: inline-block;
    padding-bottom: 2mm;
    color: #1a3d5c;
  }}
  .facility {{
    font-size: 12pt;
    margin-top: 2mm;
    color: #444;
  }}
  .dest-block {{
    background: #EEF4FB;
    border-left: 6px solid #2C5F8A;
    padding: 4mm 6mm;
    margin-bottom: 5mm;
    border-radius: 0 4px 4px 0;
  }}
  .dest-label {{ font-size: 10pt; color: #666; margin-bottom: 1mm; }}
  .dest-name  {{ font-size: 16pt; font-weight: bold; color: #1a3d5c; }}
  .dest-date  {{ font-size: 12pt; color: #333; margin-top: 1mm; }}
  .purpose    {{ font-size: 11pt; color: #444; margin: 4mm 0; line-height: 1.7; }}
  .section-title {{
    font-size: 12pt;
    font-weight: bold;
    color: #2C5F8A;
    border-bottom: 1px solid #C8D4E0;
    padding-bottom: 1mm;
    margin: 4mm 0 2mm 0;
  }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 4mm; }}
  th, td {{
    padding: 2.5mm 4mm;
    border: 1px solid #C8D4E0;
    vertical-align: top;
    line-height: 1.5;
  }}
  th {{
    background: #EEF4FB;
    font-weight: bold;
    white-space: nowrap;
    width: 38mm;
    color: #2C5F8A;
  }}
  td {{ background: #fff; }}
  .note {{ font-size: 10pt; color: #666; margin-left: 3mm; }}
  .notes-section {{
    border: 1px solid #C8D4E0;
    padding: 3mm 5mm;
    margin-top: 4mm;
    border-radius: 4px;
    background: #FAFBFD;
  }}
  .notes-label {{ font-weight: bold; color: #2C5F8A; margin-bottom: 1mm; font-size: 11pt; }}
  .notes-text  {{ font-size: 11pt; line-height: 1.8; color: #333; }}
  .footer {{
    margin-top: 6mm;
    text-align: right;
    font-size: 11pt;
    color: #555;
    border-top: 1px solid #C8D4E0;
    padding-top: 3mm;
  }}
  @media print {{
    body {{ background: #fff; }}
    .page {{ margin: 0; padding: 8mm 10mm; }}
  }}
</style>
</head>
<body>
<div class="page">

  <div class="header">{issued}</div>

  <div class="title-block">
    <div class="title">お出かけのお知らせ</div>
    <div class="facility">{facility}</div>
  </div>

  <div class="dest-block">
    <div class="dest-label">行き先</div>
    <div class="dest-name">🚌 {dest}</div>
    <div class="dest-date">📅 {date_str}</div>
  </div>

  {purpose_html}

  <p class="section-title">■ スケジュール</p>
  <table>{schedule_rows}</table>

  {'<p class="section-title">■ その他</p><table>' + other_rows + '</table>' if other_rows.strip() else ''}

  {notes_html}

  <div class="footer">
    担当：{staff}&nbsp;&nbsp;
    ご不明な点はスタッフにお声がけください
  </div>

</div>
</body>
</html>"""

    return html


# ===== メインアプリ =====

class OutingApp(tk.Tk):
    """
    お出かけのお知らせ作成アプリのメインウィンドウ。
    入力フォームと操作ボタンを提供する。
    """

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self.settings = load_settings()

        # 費用行のデータ（動的に追加・削除）
        # 各要素は {"frame": Frame, "v_name": StringVar, "v_amount": StringVar}
        self.cost_rows = []

        self._build_ui()

        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 660)
        h = min(self.winfo_reqheight() + 20, 900)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ------------------------------------------------------------------ #
    # UI 構築
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        """ウィンドウ全体の UI を組み立てる"""
        header = tk.Frame(self, bg=COLOR_HEADER, height=44)
        header.pack(fill="x")
        tk.Label(header, text=f"  {APP_TITLE}", font=FONT_TITLE,
                 bg=COLOR_HEADER, fg=COLOR_WHITE).pack(side="left", pady=8)

        container = tk.Frame(self, bg=COLOR_BG)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.form_frame = tk.Frame(canvas, bg=COLOR_BG, padx=20, pady=10)
        cw = canvas.create_window((0, 0), window=self.form_frame, anchor="nw")

        self.form_frame.bind("<Configure>",
            lambda e: (canvas.configure(scrollregion=canvas.bbox("all")),
                       canvas.itemconfig(cw, width=canvas.winfo_width())))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(cw, width=canvas.winfo_width()))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        self._build_basic_section()
        self._build_schedule_section()
        self._build_cost_section()
        self._build_detail_section()
        self._build_facility_section()
        self._build_buttons()

    def _section_label(self, text):
        """セクション見出しを作成する"""
        f = tk.Frame(self.form_frame, bg=COLOR_HEADER)
        f.pack(fill="x", pady=(14, 4))
        tk.Label(f, text=f"  {text}", font=FONT_BOLD,
                 bg=COLOR_HEADER, fg=COLOR_WHITE, anchor="w").pack(fill="x", pady=4)

    def _field(self, parent, label, var, hint="", width=20, label_width=18):
        """
        ラベル＋入力欄の1行を作成して Entry を返す。

        Args:
            parent: 配置先フレーム
            label (str): 項目名
            var (tk.StringVar): 入力値を保持する変数
            hint (str): 入力欄の右に表示するヒント
            width (int): 入力欄の文字幅
            label_width (int): ラベルの文字幅

        Returns:
            ttk.Entry
        """
        row = tk.Frame(parent, bg=COLOR_BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, font=FONT, bg=COLOR_BG,
                 anchor="w", width=label_width).pack(side="left")
        entry = ttk.Entry(row, textvariable=var, font=FONT, width=width)
        entry.pack(side="left", padx=(0, 6))
        if hint:
            tk.Label(row, text=hint, font=FONT_SMALL,
                     bg=COLOR_BG, fg="#888").pack(side="left")
        return entry

    # ------------------------------------------------------------------ #
    # 基本情報セクション
    # ------------------------------------------------------------------ #

    def _build_basic_section(self):
        """行き先・日付などの基本情報セクションを構築する"""
        self._section_label("■ 基本情報")

        today = datetime.now()
        wd    = "月火水木金土日"[today.weekday()]

        self.v_date        = tk.StringVar(value=today.strftime(f"%Y年%m月%d日（{wd}）"))
        self.v_destination = tk.StringVar()
        self.v_purpose     = tk.StringVar()
        self.v_issued_date = tk.StringVar(value=today.strftime("%Y年%m月%d日"))

        self._field(self.form_frame, "行き先 ★",       self.v_destination,
                    "例: ○○公園、△△ショッピングセンター", width=36)
        self._field(self.form_frame, "外出日 ★",       self.v_date,
                    "例: 2026年5月20日（水）", width=26)
        self._field(self.form_frame, "目的・一言コメント", self.v_purpose,
                    "例: 春の陽気を楽しみながら、みんなでお花見に行きます。", width=46)
        self._field(self.form_frame, "お知らせ発行日",  self.v_issued_date,
                    "例: 2026年5月16日", width=18)

    # ------------------------------------------------------------------ #
    # スケジュール・自動計算セクション
    # ------------------------------------------------------------------ #

    def _build_schedule_section(self):
        """
        スケジュール（時刻・移動時間）セクションを構築する。
        7つのフィールドのうち入力したものから残りを自動計算できる。
        """
        self._section_label("■ スケジュール（時刻・移動時間）")

        # 入力用の StringVar（7つ）
        self.v_depart    = tk.StringVar()   # 出発時刻
        self.v_travel_go = tk.StringVar()   # 移動時間（行き）
        self.v_arrive    = tk.StringVar()   # 現地到着
        self.v_stay      = tk.StringVar()   # 現地滞在時間
        self.v_leave     = tk.StringVar()   # 現地出発
        self.v_travel_bk = tk.StringVar()   # 移動時間（帰り）
        self.v_return    = tk.StringVar()   # 帰宅予定

        hint_time = "例: 9:30"
        hint_dur  = "例: 30分、1:00、1時間30分"

        def make_row(label, var, hint):
            """スケジュール行を作って Entry を返す"""
            e = self._field(self.form_frame, label, var, hint, width=14)
            # 手入力したら「自動計算済み」の色をリセット
            var.trace_add("write", lambda *_: self._reset_entry_color(e))
            return e

        # Entry ウィジェットを個別の変数で保持（背景色の変更に使う）
        self.e_depart    = make_row("出発時刻 ★",     self.v_depart,    hint_time)
        self.e_travel_go = make_row("移動時間（行き）", self.v_travel_go, hint_dur)
        self.e_arrive    = make_row("現地到着時間",    self.v_arrive,    hint_time)
        self.e_stay      = make_row("現地滞在時間",    self.v_stay,      hint_dur)
        self.e_leave     = make_row("現地出発時間",    self.v_leave,     hint_time)
        self.e_travel_bk = make_row("移動時間（帰り）", self.v_travel_bk, hint_dur)
        self.e_return    = make_row("帰宅予定 ★",     self.v_return,    hint_time)

        # 全 Entry をリストでまとめて持っておく（クリア時などに使う）
        self.all_schedule_entries = [
            self.e_depart, self.e_travel_go, self.e_arrive,
            self.e_stay, self.e_leave, self.e_travel_bk, self.e_return,
        ]

        # 自動計算ボタン＆結果ラベル
        calc_row = tk.Frame(self.form_frame, bg=COLOR_BG)
        calc_row.pack(fill="x", pady=(4, 2))
        tk.Label(calc_row, text=" " * 19, bg=COLOR_BG).pack(side="left")

        tk.Button(calc_row, text="↻ 空欄を自動計算",
                  font=FONT_BOLD, bg=COLOR_BTN_ORANGE, fg=COLOR_WHITE,
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._auto_calc_schedule).pack(side="left")

        self.lbl_calc_result = tk.Label(
            calc_row, text="", font=FONT_SMALL, bg=COLOR_BG, fg="#2C5F8A",
            wraplength=380, justify="left")
        self.lbl_calc_result.pack(side="left", padx=10)

        # ヒント文
        hint_lbl = tk.Label(
            self.form_frame,
            text="  ※ 時刻は「9:30」、所要時間は「30分」「1時間」「1:30」などで入力してください",
            font=FONT_SMALL, bg=COLOR_BG, fg="#888", anchor="w")
        hint_lbl.pack(fill="x", pady=(0, 4))

    def _reset_entry_color(self, entry):
        """
        Entry の背景色を標準（白）に戻す。
        ユーザーが手入力したとき、自動計算の色ハイライトを解除するために呼ぶ。
        """
        try:
            entry.configure(style="TEntry")
        except Exception:
            pass

    def _auto_calc_schedule(self):
        """
        入力済みの時刻・所要時間から空欄を自動計算して埋める。
        計算できた項目を水色でハイライトし、結果をラベルに表示する。
        """
        # 現在の入力値を読み取る（パースできないものは None）
        raw = {
            "D":  self.v_depart.get().strip(),
            "Tg": self.v_travel_go.get().strip(),
            "A":  self.v_arrive.get().strip(),
            "E":  self.v_stay.get().strip(),
            "L":  self.v_leave.get().strip(),
            "Tb": self.v_travel_bk.get().strip(),
            "R":  self.v_return.get().strip(),
        }

        # 入力済みフィールドをパース（None = 空欄 or 解析不能）
        D  = parse_time_to_min(raw["D"])  if raw["D"]  else None
        Tg = parse_duration_to_min(raw["Tg"]) if raw["Tg"] else None
        A  = parse_time_to_min(raw["A"])  if raw["A"]  else None
        E  = parse_duration_to_min(raw["E"])  if raw["E"]  else None
        L  = parse_time_to_min(raw["L"])  if raw["L"]  else None
        Tb = parse_duration_to_min(raw["Tb"]) if raw["Tb"] else None
        R  = parse_time_to_min(raw["R"])  if raw["R"]  else None

        # パースに失敗した入力値がある場合は警告
        parse_errors = []
        checks = [
            (raw["D"],  D,  "出発時刻", "時刻（例: 9:30）"),
            (raw["Tg"], Tg, "移動時間（行き）", "所要時間（例: 30分）"),
            (raw["A"],  A,  "現地到着時間", "時刻（例: 10:00）"),
            (raw["E"],  E,  "現地滞在時間", "所要時間（例: 2時間）"),
            (raw["L"],  L,  "現地出発時間", "時刻（例: 12:00）"),
            (raw["Tb"], Tb, "移動時間（帰り）", "所要時間（例: 30分）"),
            (raw["R"],  R,  "帰宅予定", "時刻（例: 12:30）"),
        ]
        for raw_val, parsed, field_name, fmt in checks:
            if raw_val and parsed is None:
                parse_errors.append(f"・{field_name}「{raw_val}」→ {fmt}で入力してください")
        if parse_errors:
            messagebox.showwarning(
                "入力形式エラー",
                "以下の入力を確認してください。\n\n" + "\n".join(parse_errors))
            return

        # 計算前の値を記録（計算後と比較して何が埋まったかを判定）
        before = (D, Tg, A, E, L, Tb, R)

        # ソルバーで計算
        D, Tg, A, E, L, Tb, R = solve_schedule(D, Tg, A, E, L, Tb, R)

        after = (D, Tg, A, E, L, Tb, R)

        # 負の値チェック（時刻の逆転や負の所要時間）
        invalid = []
        if Tg is not None and Tg < 0:
            invalid.append("移動時間（行き）が負になっています。出発時刻と到着時刻を確認してください。")
        if E is not None and E < 0:
            invalid.append("現地滞在時間が負になっています。到着・出発時刻を確認してください。")
        if Tb is not None and Tb < 0:
            invalid.append("移動時間（帰り）が負になっています。現地出発と帰宅時刻を確認してください。")
        if invalid:
            messagebox.showwarning("計算結果の確認", "\n".join(invalid))
            return

        # 計算結果をフィールドに書き戻す（元が空欄で計算できたもの）
        fill_info = []
        updates = [
            (before[0], after[0], self.v_depart,    self.e_depart,    "出発時刻",       "time"),
            (before[1], after[1], self.v_travel_go, self.e_travel_go, "移動時間（行き）", "dur"),
            (before[2], after[2], self.v_arrive,    self.e_arrive,    "現地到着時間",    "time"),
            (before[3], after[3], self.v_stay,      self.e_stay,      "現地滞在時間",    "dur"),
            (before[4], after[4], self.v_leave,     self.e_leave,     "現地出発時間",    "time"),
            (before[5], after[5], self.v_travel_bk, self.e_travel_bk, "移動時間（帰り）", "dur"),
            (before[6], after[6], self.v_return,    self.e_return,    "帰宅予定",        "time"),
        ]

        for b, a, var, entry, label, kind in updates:
            if b is None and a is not None:
                # 空欄だったが計算できた → フィールドに書き込んでハイライト
                val = min_to_time_str(a) if kind == "time" else min_to_duration_str(a)
                var.set(val)
                entry.configure(background=COLOR_CALC_BG)
                fill_info.append(f"{label}：{val}")

        # 結果メッセージ
        if fill_info:
            self.lbl_calc_result.config(
                text="✔ 計算しました　" + "　".join(fill_info),
                fg="#1a6a1a")
        else:
            # 何も埋まらなかった理由を診断
            filled_count = sum(1 for b in before if b is not None)
            if filled_count == 0:
                msg = "時刻や所要時間を1つ以上入力してから実行してください。"
            elif all(b is not None for b in after):
                msg = "すべての項目がすでに入力済みです。"
            else:
                msg = "計算するには情報が足りません。もう少し入力してみてください。"
            self.lbl_calc_result.config(text=msg, fg="#888")

    # ------------------------------------------------------------------ #
    # 費用計算セクション
    # ------------------------------------------------------------------ #

    def _build_cost_section(self):
        """
        費用計算セクションを構築する。
        複数の費用項目を入力すると合計が自動計算される。
        """
        self._section_label("■ 費用計算")

        # ヘッダー行
        header_row = tk.Frame(self.form_frame, bg=COLOR_BG)
        header_row.pack(fill="x", pady=(2, 0))
        tk.Label(header_row, text=" " * 19, bg=COLOR_BG).pack(side="left")
        tk.Label(header_row, text="項目名", font=FONT_SMALL, bg=COLOR_BG,
                 fg="#555", width=18, anchor="w").pack(side="left")
        tk.Label(header_row, text="金額（円）", font=FONT_SMALL, bg=COLOR_BG,
                 fg="#555", width=10, anchor="w").pack(side="left")

        # 費用行を配置するコンテナ
        self.cost_container = tk.Frame(self.form_frame, bg=COLOR_BG)
        self.cost_container.pack(fill="x")

        # 追加ボタン＆合計表示行
        ctrl_row = tk.Frame(self.form_frame, bg=COLOR_BG)
        ctrl_row.pack(fill="x", pady=(4, 2))
        tk.Label(ctrl_row, text=" " * 19, bg=COLOR_BG).pack(side="left")

        tk.Button(ctrl_row, text="＋ 項目を追加",
                  font=FONT, bg=COLOR_SECTION, fg=COLOR_HEADER,
                  relief="flat", cursor="hand2", padx=8, pady=3,
                  command=self._add_cost_row).pack(side="left")

        self.lbl_cost_total = tk.Label(
            ctrl_row, text="合計：－", font=FONT_BOLD,
            bg=COLOR_BG, fg=COLOR_HEADER)
        self.lbl_cost_total.pack(side="left", padx=20)

        # 最初から1行表示しておく
        self._add_cost_row()

    def _add_cost_row(self):
        """費用項目の入力行を1行追加する"""
        row_frame = tk.Frame(self.cost_container, bg=COLOR_BG)
        row_frame.pack(fill="x", pady=2)

        tk.Label(row_frame, text=" " * 19, bg=COLOR_BG).pack(side="left")

        v_name   = tk.StringVar()
        v_amount = tk.StringVar()

        # 金額が変わったら合計を再計算
        v_name.trace_add("write", lambda *_: self._update_cost_total())
        v_amount.trace_add("write", lambda *_: self._update_cost_total())

        e_name = ttk.Entry(row_frame, textvariable=v_name, font=FONT, width=18)
        e_name.pack(side="left", padx=(0, 4))

        e_amt = ttk.Entry(row_frame, textvariable=v_amount, font=FONT, width=10)
        e_amt.pack(side="left", padx=(0, 2))

        tk.Label(row_frame, text="円", font=FONT, bg=COLOR_BG).pack(side="left")

        # この行を削除するボタン
        row_info = {"frame": row_frame, "v_name": v_name, "v_amount": v_amount}

        tk.Button(row_frame, text="×",
                  font=FONT_SMALL, bg="#E8E8E8", fg="#555",
                  relief="flat", cursor="hand2", padx=4,
                  command=lambda ri=row_info: self._remove_cost_row(ri)
                  ).pack(side="left", padx=(6, 0))

        self.cost_rows.append(row_info)
        self._update_cost_total()

    def _remove_cost_row(self, row_info):
        """費用項目の行を1つ削除する"""
        if len(self.cost_rows) <= 1:
            # 最後の1行は削除せず内容だけクリア
            row_info["v_name"].set("")
            row_info["v_amount"].set("")
            return
        row_info["frame"].destroy()
        self.cost_rows.remove(row_info)
        self._update_cost_total()

    def _update_cost_total(self):
        """費用の合計を再計算してラベルに表示する"""
        total = 0
        valid = False
        for ri in self.cost_rows:
            amt = parse_amount(ri["v_amount"].get())
            if amt is not None:
                total += amt
                valid = True
        if valid:
            self.lbl_cost_total.config(
                text=f"合計：{format_amount(total)}", fg="#1a6a1a")
        else:
            self.lbl_cost_total.config(text="合計：－", fg=COLOR_HEADER)

    def _get_cost_items(self):
        """
        費用行の入力値をリストで返す。
        空行は除外する。

        Returns:
            list of dict: [{"name": str, "amount": str}, ...]
        """
        items = []
        for ri in self.cost_rows:
            name = ri["v_name"].get().strip()
            amt  = ri["v_amount"].get().strip()
            if name or amt:
                items.append({"name": name, "amount": amt})
        return items

    # ------------------------------------------------------------------ #
    # 詳細情報セクション
    # ------------------------------------------------------------------ #

    def _build_detail_section(self):
        """持ち物・集合場所・備考などの詳細情報セクションを構築する"""
        self._section_label("■ 詳細情報（任意）")

        self.v_gather = tk.StringVar()
        self.v_items  = tk.StringVar()

        self._field(self.form_frame, "集合場所", self.v_gather,
                    "例: グループホーム玄関前", width=30)
        self._field(self.form_frame, "持ち物",   self.v_items,
                    "例: 動きやすい服装、水分補給用の飲み物", width=36)

        notes_row = tk.Frame(self.form_frame, bg=COLOR_BG)
        notes_row.pack(fill="x", pady=3)
        tk.Label(notes_row, text="備考", font=FONT, bg=COLOR_BG,
                 anchor="nw", width=18).pack(side="left", anchor="n", pady=2)
        self.txt_notes = tk.Text(notes_row, font=FONT, width=44, height=3,
                                 relief="solid", bd=1)
        self.txt_notes.pack(side="left")

    # ------------------------------------------------------------------ #
    # 施設情報セクション
    # ------------------------------------------------------------------ #

    def _build_facility_section(self):
        """施設名・担当者名のセクションを構築する（次回起動時に引き継がれる）"""
        self._section_label("■ 施設情報（保存されます）")

        self.v_facility = tk.StringVar(value=self.settings.get("facility_name", ""))
        self.v_staff    = tk.StringVar(value=self.settings.get("staff_name", ""))

        self._field(self.form_frame, "施設名 ★", self.v_facility,
                    "例: グループホーム○○", width=28)
        self._field(self.form_frame, "担当者名", self.v_staff,
                    "例: 田中", width=18)

        tk.Label(self.form_frame,
                 text="  ※ 施設名・担当者名は次回起動時も引き継がれます",
                 font=FONT_SMALL, bg=COLOR_BG, fg="#888", anchor="w"
                 ).pack(fill="x", pady=(0, 6))

    # ------------------------------------------------------------------ #
    # 操作ボタン
    # ------------------------------------------------------------------ #

    def _build_buttons(self):
        """画面下部の操作ボタンエリアを構築する"""
        bar = tk.Frame(self, bg=COLOR_BORDER, pady=1)
        bar.pack(fill="x", side="bottom")
        inner = tk.Frame(bar, bg=COLOR_BG, pady=10)
        inner.pack(fill="x", padx=20)

        s = dict(font=FONT_BOLD, relief="flat", cursor="hand2", padx=14, pady=6)

        tk.Button(inner, text="クリア", bg="#BDC3C7", fg=COLOR_WHITE,
                  command=self._clear_form, **s).pack(side="left", padx=(0, 8))

        tk.Button(inner, text="印刷用HTMLを開く",
                  bg=COLOR_BTN_GREEN, fg=COLOR_WHITE,
                  command=self._open_for_print, **s).pack(side="right", padx=(8, 0))

        tk.Button(inner, text="プレビュー（ブラウザで確認）",
                  bg=COLOR_BTN_PRIMARY, fg=COLOR_WHITE,
                  command=self._preview, **s).pack(side="right", padx=(8, 0))

    # ------------------------------------------------------------------ #
    # フォーム操作
    # ------------------------------------------------------------------ #

    def _get_form_data(self):
        """
        フォームの入力値をまとめて辞書で返す。

        Returns:
            dict: 各入力フィールドの値を持つ辞書
        """
        return {
            "facility_name": self.v_facility.get().strip(),
            "date":          self.v_date.get().strip(),
            "destination":   self.v_destination.get().strip(),
            "purpose":       self.v_purpose.get().strip(),
            "issued_date":   self.v_issued_date.get().strip(),
            "depart_time":   self.v_depart.get().strip(),
            "travel_go":     self.v_travel_go.get().strip(),
            "arrive_time":   self.v_arrive.get().strip(),
            "stay_duration": self.v_stay.get().strip(),
            "leave_time":    self.v_leave.get().strip(),
            "travel_back":   self.v_travel_bk.get().strip(),
            "return_time":   self.v_return.get().strip(),
            "gather_place":  self.v_gather.get().strip(),
            "items":         self.v_items.get().strip(),
            "cost_items":    self._get_cost_items(),
            "notes":         self.txt_notes.get("1.0", "end").strip(),
            "staff_name":    self.v_staff.get().strip(),
        }

    def _validate(self, data):
        """
        必須項目が入力されているかチェックする。
        不足があればメッセージを表示して False を返す。

        Args:
            data (dict): フォームの入力値

        Returns:
            bool: バリデーション通過なら True
        """
        missing = []
        if not data["destination"]:
            missing.append("行き先")
        if not data["date"]:
            missing.append("外出日")
        if not data["depart_time"]:
            missing.append("出発時刻")
        if not data["return_time"]:
            missing.append("帰宅予定")
        if not data["facility_name"]:
            missing.append("施設名")

        if missing:
            messagebox.showwarning(
                "入力不足",
                "★ マークの項目を入力してください。\n\n"
                + "\n".join(f"・{m}" for m in missing))
            return False
        return True

    def _save_facility_settings(self, data):
        """施設名・担当者名を設定ファイルに保存する"""
        self.settings["facility_name"] = data["facility_name"]
        self.settings["staff_name"]    = data["staff_name"]
        save_settings(self.settings)

    def _preview(self):
        """入力内容をもとにHTMLを生成し、ブラウザでプレビュー表示する"""
        data = self._get_form_data()
        if not self._validate(data):
            return
        self._save_facility_settings(data)
        self._open_html(data)

    def _open_for_print(self):
        """
        印刷用の HTML をブラウザで開く。
        ブラウザの印刷機能（Ctrl+P）でそのまま印刷できる。
        """
        data = self._get_form_data()
        if not self._validate(data):
            return
        self._save_facility_settings(data)
        self._open_html(data, print_mode=True)

    def _open_html(self, data, print_mode=False):
        """
        HTML を一時ファイルとして保存してブラウザで開く。

        Args:
            data (dict): フォームの入力値
            print_mode (bool): True のとき印刷ダイアログを自動表示するスクリプトを追加
        """
        html = build_html(data)
        if print_mode:
            html = html.replace(
                "</body>",
                "<script>window.onload=function(){window.print();}</script></body>")

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".html",
            delete=False, prefix="outing_notice_"
        ) as f:
            f.write(html)
            path = f.name

        webbrowser.open(f"file:///{path.replace(os.sep, '/')}")

    def _clear_form(self):
        """フォームの入力内容をリセットする（施設名・担当者名は残す）"""
        if not messagebox.askyesno(
                "確認", "入力内容をすべてクリアしますか？\n（施設名・担当者名は残ります）"):
            return

        today = datetime.now()
        wd = "月火水木金土日"[today.weekday()]

        self.v_date.set(today.strftime(f"%Y年%m月%d日（{wd}）"))
        self.v_destination.set("")
        self.v_purpose.set("")
        self.v_issued_date.set(today.strftime("%Y年%m月%d日"))

        for v in (self.v_depart, self.v_travel_go, self.v_arrive,
                  self.v_stay, self.v_leave, self.v_travel_bk, self.v_return):
            v.set("")
        # 自動計算ハイライトを全解除
        for entry in self.all_schedule_entries:
            try:
                entry.configure(background="white")
            except Exception:
                pass
        self.lbl_calc_result.config(text="", fg="#2C5F8A")

        # 費用行をリセット（全削除して1行だけ残す）
        for ri in list(self.cost_rows):
            ri["frame"].destroy()
        self.cost_rows.clear()
        self._add_cost_row()

        self.v_gather.set("")
        self.v_items.set("")
        self.txt_notes.delete("1.0", "end")


# ===== 起動 =====

if __name__ == "__main__":
    app = OutingApp()
    app.mainloop()
