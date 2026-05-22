# =============================================================================
# 入居者ダッシュボード
# 1人の入居者に関する情報を複数のDBから集めて一覧表示する
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import datetime, date

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")

RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
BP_DB        = os.path.join(DATA_DIR, "bp_records.db")
WEIGHT_DB    = os.path.join(DATA_DIR, "weight_records.db")
NURSING_DB   = os.path.join(DATA_DIR, "nursing_records.db")
VISITS_DB    = os.path.join(DATA_DIR, "visits.db")
MEDICINE_DB  = os.path.join(DATA_DIR, "medicine.db")
DEPOSIT_DB   = os.path.join(DATA_DIR, "deposit.db")

# お薬残日数がこれ以下になると警告を表示する（日数）
MEDICINE_LOW_THRESHOLD = 14

# フォント設定（日本語対応）
FONT            = ("MS Gothic", 11)
FONT_BOLD       = ("MS Gothic", 11, "bold")
FONT_TITLE      = ("MS Gothic", 14, "bold")
FONT_SMALL      = ("MS Gothic", 10)
FONT_SMALL_BOLD = ("MS Gothic", 10, "bold")

# カラー設定
COLOR_BG  = "#F5F7FA"
TITLE_BG  = "#2C5FA8"
TITLE_FG  = "#FFFFFF"

# パネルごとのテーマカラー（header: ヘッダー背景、bg: コンテンツ背景）
PANEL_CFG = {
    "基本情報": {"header": "#3A9E72", "bg": "#EDF7F3"},
    "血圧":     {"header": "#C05555", "bg": "#FBEDED"},
    "体重":     {"header": "#2E8B9A", "bg": "#E8F6F8"},
    "看護記録": {"header": "#4A8F80", "bg": "#E8F3F0"},
    "通院記録": {"header": "#7B5EA7", "bg": "#F3F0F8"},
    "お薬在庫": {"header": "#D4762A", "bg": "#FDF2E9"},
    "預かり金": {"header": "#5B7FA6", "bg": "#EEF3F8"},
}


# =============================================================================
# ユーティリティ関数
# =============================================================================

def open_db(path):
    """DBファイルが存在すれば接続を返す。存在しなければ None を返す"""
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def calc_age(birthdate_str):
    """生年月日文字列（YYYY-MM-DD）から現在の年齢を計算して返す"""
    if not birthdate_str:
        return "—"
    try:
        bd    = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
        today = date.today()
        age   = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        return f"{age}歳"
    except ValueError:
        return "—"


def fmt_date(date_str):
    """YYYY-MM-DD を M/D 形式に変換する。空・None の場合は '—' を返す"""
    if not date_str:
        return "—"
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return f"{d.month}/{d.day}"
    except ValueError:
        return date_str


# =============================================================================
# パネル作成ヘルパー
# =============================================================================

def make_panel(parent, title, row, col, rowspan=1, colspan=1):
    """
    タイトルバー付きのカードパネルを作って grid に配置する。

    引数:
        parent   : 配置先の親フレーム
        title    : パネルタイトル（PANEL_CFG のキーと一致させる）
        row, col : grid の行・列
    戻り値:
        content_frame: パネル内にウィジェットを置く場所
    """
    cfg   = PANEL_CFG.get(title, {"header": "#555555", "bg": "#F5F5F5"})
    outer = tk.Frame(parent, bg=cfg["bg"], bd=1, relief="solid")
    outer.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan,
               sticky="nsew", padx=6, pady=6)

    # 上部のカラーライン（アクセント）
    tk.Frame(outer, bg=cfg["header"], height=3).pack(fill="x")

    # ヘッダー行
    hdr = tk.Frame(outer, bg=cfg["header"], pady=4)
    hdr.pack(fill="x")
    tk.Label(hdr, text=f"  {title}",
             font=FONT_SMALL_BOLD, bg=cfg["header"], fg="white").pack(side="left")

    # コンテンツエリア
    content = tk.Frame(outer, bg=cfg["bg"], padx=10, pady=8)
    content.pack(fill="both", expand=True)
    return content


def row_label(parent, label_text, value_text, label_width=9,
              label_fg="#3A6B50", value_fg="#222"):
    """
    「ラベル：値」形式の1行を作る（基本情報パネルで使う）。

    引数:
        parent      : 配置先フレーム
        label_text  : 左側の項目名
        value_text  : 右側の値
        label_width : 左側ラベルの文字幅（桁揃え用）
    """
    bg  = parent.cget("bg")
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=1)
    tk.Label(row, text=f"{label_text}：",
             font=FONT_SMALL_BOLD, bg=bg, fg=label_fg,
             width=label_width, anchor="e").pack(side="left")
    tk.Label(row, text=value_text,
             font=FONT_SMALL, bg=bg, fg=value_fg, anchor="w").pack(side="left")


# =============================================================================
# DBからデータを取得する関数群
# =============================================================================

def fetch_resident(resident_id):
    """入居者マスターから1人分の基本情報を辞書で返す"""
    conn = open_db(RESIDENTS_DB)
    if not conn:
        return None
    row  = conn.execute(
        "SELECT * FROM residents WHERE id = ?", (resident_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_bp_recent(resident_id, limit=5):
    """直近の血圧記録を新しい順で返す"""
    conn = open_db(BP_DB)
    if not conn:
        return []
    rows = conn.execute(
        """SELECT record_date, systolic, diastolic
           FROM bp_records
           WHERE resident_id = ?
           ORDER BY record_date DESC LIMIT ?""",
        (resident_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_weight_recent(resident_id, limit=5):
    """直近の体重記録を新しい順で返す"""
    conn = open_db(WEIGHT_DB)
    if not conn:
        return []
    rows = conn.execute(
        """SELECT record_date, weight_kg
           FROM weight_records
           WHERE resident_id = ?
           ORDER BY record_date DESC LIMIT ?""",
        (resident_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_nursing_latest(resident_id):
    """最新の看護記録を1件返す"""
    conn = open_db(NURSING_DB)
    if not conn:
        return None
    row  = conn.execute(
        """SELECT * FROM nursing_records
           WHERE resident_id = ?
           ORDER BY record_date DESC LIMIT 1""",
        (resident_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_visits_recent(resident_id, limit=3):
    """直近の通院記録を新しい順で返す"""
    conn = open_db(VISITS_DB)
    if not conn:
        return []
    try:
        rows = conn.execute(
            """SELECT v.visit_date, h.name AS hospital_name, v.content
               FROM visits v
               JOIN hospitals h ON h.id = v.hospital_id
               WHERE v.resident_id = ?
               ORDER BY v.visit_date DESC LIMIT ?""",
            (resident_id, limit)
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]


def fetch_next_visit(resident_id):
    """
    次回受診予定（next_visit_date が今日以降で最も近いもの）を1件返す。
    対応するカラムが存在しない旧バージョンのDBでも例外を出さないよう try/except で囲む。
    """
    conn = open_db(VISITS_DB)
    if not conn:
        return None
    today = date.today().strftime("%Y-%m-%d")
    try:
        row = conn.execute(
            """SELECT v.next_visit_date, v.next_appointment_time, h.name AS hospital_name
               FROM visits v
               JOIN hospitals h ON h.id = v.hospital_id
               WHERE v.resident_id = ? AND v.next_visit_date >= ?
               ORDER BY v.next_visit_date ASC LIMIT 1""",
            (resident_id, today)
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    return dict(row) if row else None


def fetch_medicine(resident_id):
    """有効な時間帯のお薬在庫日数を返す（medicine_settings で enabled=1 のもの）"""
    conn = open_db(MEDICINE_DB)
    if not conn:
        return []
    rows = conn.execute(
        """SELECT ms.time_slot, mi.stock_days
           FROM medicine_settings ms
           LEFT JOIN medicine_inventory mi
             ON mi.resident_id = ms.resident_id AND mi.time_slot = ms.time_slot
           WHERE ms.resident_id = ? AND ms.enabled = 1
           ORDER BY ms.id""",
        (resident_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_deposit_balance(resident_id):
    """預かり金の現在残高（収入合計 - 支出合計）を返す"""
    conn = open_db(DEPOSIT_DB)
    if not conn:
        return None
    row  = conn.execute(
        """SELECT SUM(income) - SUM(expense) AS balance
           FROM deposit_transactions
           WHERE resident_id = ?""",
        (resident_id,)
    ).fetchone()
    conn.close()
    return row["balance"] if row and row["balance"] is not None else 0


def fetch_deposit_recent(resident_id, limit=3):
    """直近の預かり金取引を新しい順で返す"""
    conn = open_db(DEPOSIT_DB)
    if not conn:
        return []
    rows = conn.execute(
        """SELECT transaction_date, description, income, expense
           FROM deposit_transactions
           WHERE resident_id = ?
           ORDER BY transaction_date DESC, id DESC LIMIT ?""",
        (resident_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =============================================================================
# メインアプリ
# =============================================================================

class DashboardApp(tk.Tk):
    """入居者ダッシュボード — 1人分の情報を複数DBから集めて表示する"""

    def __init__(self):
        super().__init__()
        self.title("入居者ダッシュボード")
        self.geometry("1100x780")
        self.resizable(True, True)
        self.configure(bg=COLOR_BG)

        self.selected_id   = None
        self.selected_name = ""
        self._residents    = {}

        self._build_header()
        self._build_scroll_area()
        self._load_residents()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_header(self):
        """タイトルバーと利用者選択バーを作る"""
        # タイトル
        header = tk.Frame(self, bg=TITLE_BG, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="入居者ダッシュボード",
                 font=FONT_TITLE, bg=TITLE_BG, fg=TITLE_FG).pack(side="left", padx=20)
        tk.Label(header, text="各アプリの最新情報をまとめて確認",
                 font=FONT_SMALL, bg=TITLE_BG, fg="#BDD4F0").pack(side="left", padx=4)

        # 利用者選択バー
        ctrl = tk.Frame(self, bg="#E8EDF5", pady=6)
        ctrl.pack(fill="x", padx=10, pady=(4, 0))

        tk.Label(ctrl, text="利用者：", font=FONT, bg="#E8EDF5").pack(side="left", padx=(10, 2))
        self.resident_cb = ttk.Combobox(ctrl, font=FONT, width=16, state="readonly")
        self.resident_cb.pack(side="left", padx=(0, 10))
        self.resident_cb.bind("<<ComboboxSelected>>", self._on_resident_changed)

        tk.Button(ctrl, text="  更 新  ", font=FONT, relief="flat",
                  bg=TITLE_BG, fg=TITLE_FG, padx=10, pady=2,
                  cursor="hand2", command=self._refresh).pack(side="left")

        # 最終更新日時ラベル
        self.updated_lbl = tk.Label(ctrl, text="", font=FONT_SMALL,
                                    bg="#E8EDF5", fg="#888")
        self.updated_lbl.pack(side="right", padx=10)

    def _build_scroll_area(self):
        """ダッシュボードパネルを収めるスクロール可能エリアを作る"""
        container = tk.Frame(self, bg=COLOR_BG)
        container.pack(fill="both", expand=True)

        vsb = tk.Scrollbar(container, orient="vertical")
        vsb.pack(side="right", fill="y")

        self.canvas = tk.Canvas(container, bg=COLOR_BG,
                                yscrollcommand=vsb.set, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=self.canvas.yview)

        self.inner = tk.Frame(self.canvas, bg=COLOR_BG)
        self._win  = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._win, width=e.width)
        )
        self.canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        )

    # ------------------------------------------------------------------
    # データ読み込みと表示の切り替え
    # ------------------------------------------------------------------

    def _load_residents(self):
        """入居中の利用者をドロップダウンに読み込む"""
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "DBが見つかりません",
                "入居者マスターDBが見つかりません。\n先に入居管理マスターアプリを起動してください。"
            )
            return
        conn = open_db(RESIDENTS_DB)
        if not conn:
            return
        rows = conn.execute(
            "SELECT id, name FROM residents WHERE status='入居中' ORDER BY room_number"
        ).fetchall()
        conn.close()

        self._residents = {r["name"]: r["id"] for r in rows}
        self.resident_cb["values"] = list(self._residents.keys())
        if self._residents:
            self.resident_cb.current(0)
            self._on_resident_changed(None)

    def _on_resident_changed(self, event):
        """ドロップダウンで利用者が変わったとき"""
        name = self.resident_cb.get()
        self.selected_id   = self._residents.get(name)
        self.selected_name = name
        self._refresh()

    def _refresh(self):
        """選択中利用者のダッシュボードを再描画する"""
        for w in self.inner.winfo_children():
            w.destroy()
        if not self.selected_id:
            return
        self._draw_dashboard()
        now = datetime.now().strftime("%H:%M 更新")
        self.updated_lbl.config(text=now)
        # 再描画後に先頭へスクロール
        self.canvas.yview_moveto(0)

    # ------------------------------------------------------------------
    # ダッシュボード全体の組み立て
    # ------------------------------------------------------------------

    def _draw_dashboard(self):
        """
        2カラムのパネルグリッドを組み立てる。
        左右均等なカラムにパネルを配置し、最下段の預かり金だけ横幅いっぱいに広げる。
        """
        grid = tk.Frame(self.inner, bg=COLOR_BG, padx=8, pady=8)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        rid = self.selected_id

        # 行0：基本情報 / 看護記録（最新）
        c = make_panel(grid, "基本情報", row=0, col=0)
        self._draw_basic(c, fetch_resident(rid))

        c = make_panel(grid, "看護記録", row=0, col=1)
        self._draw_nursing(c, fetch_nursing_latest(rid))

        # 行1：血圧 / 体重
        c = make_panel(grid, "血圧", row=1, col=0)
        self._draw_bp(c, fetch_bp_recent(rid))

        c = make_panel(grid, "体重", row=1, col=1)
        self._draw_weight(c, fetch_weight_recent(rid))

        # 行2：通院記録 / お薬在庫
        c = make_panel(grid, "通院記録", row=2, col=0)
        self._draw_visits(c, fetch_visits_recent(rid), fetch_next_visit(rid))

        c = make_panel(grid, "お薬在庫", row=2, col=1)
        self._draw_medicine(c, fetch_medicine(rid))

        # 行3：預かり金（横幅いっぱい）
        c = make_panel(grid, "預かり金", row=3, col=0, colspan=2)
        self._draw_deposit(c, fetch_deposit_balance(rid), fetch_deposit_recent(rid))

    # ------------------------------------------------------------------
    # 各パネルの描画
    # ------------------------------------------------------------------

    def _draw_basic(self, c, data):
        """基本情報パネルを描画する"""
        if not data:
            tk.Label(c, text="データなし", font=FONT_SMALL,
                     bg=c.cget("bg"), fg="#999").pack()
            return

        grade_str = (f"{data['disability_grade']} 区"
                     if data.get("disability_grade") else "—")
        rows_data = [
            ("氏名",       f"{data['name']}  （{data.get('furigana') or '—'}）"),
            ("部屋番号",   data.get("room_number") or "—"),
            ("生年月日",   f"{data.get('birthdate') or '—'}  {calc_age(data.get('birthdate'))}"),
            ("障害支援区分", grade_str),
            ("入居日",     data.get("move_in_date") or "—"),
            ("緊急連絡先", (f"{data.get('emergency_contact_name') or '—'}"
                            f"  {data.get('emergency_contact_relation') or ''}")),
            ("TEL",        data.get("emergency_contact_phone") or "—"),
        ]
        for label, val in rows_data:
            row_label(c, label, val)

    def _draw_bp(self, c, rows):
        """血圧パネルを描画する"""
        bg = c.cget("bg")
        if not rows:
            tk.Label(c, text="記録なし", font=FONT_SMALL, bg=bg, fg="#999").pack()
            return

        # 最新値を大きく表示する
        latest  = rows[0]
        sys_v   = latest.get("systolic")
        dia_v   = latest.get("diastolic")
        val_str = f"{sys_v} / {dia_v}" if sys_v and dia_v else "—"
        tk.Label(c, text=val_str, font=("MS Gothic", 20, "bold"),
                 bg=bg, fg=PANEL_CFG["血圧"]["header"]).pack(anchor="w")
        tk.Label(c, text=f"収縮期 / 拡張期 (mmHg)  {fmt_date(latest['record_date'])}",
                 font=FONT_SMALL, bg=bg, fg="#666").pack(anchor="w")

        # 区切り線
        tk.Frame(c, bg="#DDCCCC", height=1).pack(fill="x", pady=(6, 4))
        tk.Label(c, text="直近の記録", font=FONT_SMALL_BOLD,
                 bg=bg, fg="#555").pack(anchor="w")
        for r in rows:
            f     = tk.Frame(c, bg=bg)
            f.pack(fill="x")
            sys_s = str(r["systolic"])  if r["systolic"]  is not None else "—"
            dia_s = str(r["diastolic"]) if r["diastolic"] is not None else "—"
            tk.Label(f, text=fmt_date(r["record_date"]),
                     font=FONT_SMALL, bg=bg, fg="#555", width=6, anchor="w").pack(side="left")
            tk.Label(f, text=f"{sys_s} / {dia_s} mmHg",
                     font=FONT_SMALL, bg=bg, fg="#333").pack(side="left", padx=4)

    def _draw_weight(self, c, rows):
        """体重パネルを描画する"""
        bg = c.cget("bg")
        if not rows:
            tk.Label(c, text="記録なし", font=FONT_SMALL, bg=bg, fg="#999").pack()
            return

        latest = rows[0]
        kg_v   = latest.get("weight_kg")
        tk.Label(c, text=f"{kg_v:.1f} kg" if kg_v else "—",
                 font=("MS Gothic", 20, "bold"),
                 bg=bg, fg=PANEL_CFG["体重"]["header"]).pack(anchor="w")
        tk.Label(c, text=fmt_date(latest["record_date"]),
                 font=FONT_SMALL, bg=bg, fg="#666").pack(anchor="w")

        tk.Frame(c, bg="#BBDDDD", height=1).pack(fill="x", pady=(6, 4))
        tk.Label(c, text="直近の記録", font=FONT_SMALL_BOLD,
                 bg=bg, fg="#555").pack(anchor="w")
        for r in rows:
            f  = tk.Frame(c, bg=bg)
            f.pack(fill="x")
            kg = f"{r['weight_kg']:.1f}" if r["weight_kg"] is not None else "—"
            tk.Label(f, text=fmt_date(r["record_date"]),
                     font=FONT_SMALL, bg=bg, fg="#555", width=6, anchor="w").pack(side="left")
            tk.Label(f, text=f"{kg} kg",
                     font=FONT_SMALL, bg=bg, fg="#333").pack(side="left", padx=4)

    def _draw_nursing(self, c, data):
        """看護記録（最新）パネルを描画する"""
        bg = c.cget("bg")
        if not data:
            tk.Label(c, text="記録なし", font=FONT_SMALL, bg=bg, fg="#999").pack()
            return

        # 記録日
        tk.Label(c, text=data.get("record_date") or "—",
                 font=FONT_SMALL_BOLD, bg=bg, fg="#3A6B60").pack(anchor="w")

        # バイタル（体温・脈拍）
        temp_str  = f"{data['temperature']} ℃" if data.get("temperature") else "—"
        pulse_str = f"{data['pulse']} 回/分"   if data.get("pulse")        else "—"
        vf = tk.Frame(c, bg=bg)
        vf.pack(fill="x", pady=(2, 4))
        for label, val in [("体温", temp_str), ("脈拍", pulse_str)]:
            tk.Label(vf, text=f"{label}：",
                     font=FONT_SMALL_BOLD, bg=bg, fg="#3A6B60").pack(side="left", padx=(0, 2))
            tk.Label(vf, text=val,
                     font=FONT_SMALL, bg=bg, fg="#222").pack(side="left", padx=(0, 14))

        # 睡眠・食事・排便の3項目（問題あれば赤・橙で表示）
        STATUS_COLOR = {
            "問題なし": "#2E7D32",
            "やや不良": "#E65100", "不眠気味":  "#C62828",
            "食欲低下": "#C62828", "不規則":    "#E65100",
            "便秘傾向": "#C62828",
        }
        for label, key in [
            ("睡眠", "sleep_status"),
            ("食事", "appetite_status"),
            ("排便", "bowel_status"),
        ]:
            status = data.get(key) or "—"
            color  = STATUS_COLOR.get(status, "#333")
            f = tk.Frame(c, bg=bg)
            f.pack(fill="x", pady=1)
            tk.Label(f, text=f"{label}：",
                     font=FONT_SMALL_BOLD, bg=bg, fg="#3A6B60",
                     width=5, anchor="e").pack(side="left")
            tk.Label(f, text=status,
                     font=FONT_SMALL_BOLD, bg=bg, fg=color).pack(side="left")

        # アセスメント（長い場合は末尾を省略）
        assessment = data.get("assessment") or ""
        if assessment:
            tk.Frame(c, bg="#AACCAA", height=1).pack(fill="x", pady=(6, 2))
            tk.Label(c, text=assessment[:60] + ("…" if len(assessment) > 60 else ""),
                     font=FONT_SMALL, bg=bg, fg="#444",
                     wraplength=280, justify="left", anchor="w").pack(fill="x")

    def _draw_visits(self, c, rows, next_visit):
        """通院記録パネルを描画する"""
        bg = c.cget("bg")

        # 次回受診予定
        if next_visit:
            tk.Label(c, text="次回受診予定",
                     font=FONT_SMALL_BOLD, bg=bg, fg="#555").pack(anchor="w")
            f = tk.Frame(c, bg=bg)
            f.pack(fill="x", pady=(0, 6))
            time_str = (f"  {next_visit['next_appointment_time']}"
                        if next_visit.get("next_appointment_time") else "")
            tk.Label(f, text=f"  {next_visit['next_visit_date']}{time_str}",
                     font=FONT_BOLD, bg=bg,
                     fg=PANEL_CFG["通院記録"]["header"]).pack(side="left")
            tk.Label(f, text=f"  {next_visit['hospital_name']}",
                     font=FONT_SMALL, bg=bg, fg="#444").pack(side="left")

        tk.Frame(c, bg="#CCBBDD", height=1).pack(fill="x", pady=(0, 4))
        tk.Label(c, text="直近の記録",
                 font=FONT_SMALL_BOLD, bg=bg, fg="#555").pack(anchor="w")

        if not rows:
            tk.Label(c, text="記録なし", font=FONT_SMALL, bg=bg, fg="#999").pack(anchor="w")
            return

        for r in rows:
            f = tk.Frame(c, bg=bg, pady=1)
            f.pack(fill="x")
            tk.Label(f, text=fmt_date(r["visit_date"]),
                     font=FONT_SMALL, bg=bg, fg="#555",
                     width=6, anchor="w").pack(side="left")
            tk.Label(f, text=r["hospital_name"],
                     font=FONT_SMALL_BOLD, bg=bg, fg="#444",
                     width=12, anchor="w").pack(side="left")
            content_short = (r.get("content") or "")[:20]
            tk.Label(f, text=content_short,
                     font=FONT_SMALL, bg=bg, fg="#555", anchor="w").pack(side="left")

    def _draw_medicine(self, c, rows):
        """お薬在庫パネルを描画する。残日数が少ない場合は赤文字で警告を表示する"""
        bg = c.cget("bg")
        if not rows:
            tk.Label(c, text="設定なし", font=FONT_SMALL, bg=bg, fg="#999").pack()
            return

        for r in rows:
            stock = r.get("stock_days")
            f     = tk.Frame(c, bg=bg, pady=2)
            f.pack(fill="x")

            tk.Label(f, text=f"  {r['time_slot']}：",
                     font=FONT_SMALL_BOLD, bg=bg, fg="#555",
                     width=8, anchor="w").pack(side="left")

            if stock is None:
                stock_str = "未記録"
                stock_fg  = "#999"
            elif stock <= MEDICINE_LOW_THRESHOLD:
                stock_str = f"残 {stock} 日  ⚠ 補充確認"
                stock_fg  = "#C62828"
            else:
                stock_str = f"残 {stock} 日"
                stock_fg  = "#2E7D32"

            tk.Label(f, text=stock_str, font=FONT_SMALL_BOLD,
                     bg=bg, fg=stock_fg).pack(side="left")

    def _draw_deposit(self, c, balance, recent_rows):
        """預かり金パネルを描画する（横並びレイアウト：残高 + 直近の取引）"""
        bg = c.cget("bg")

        # 左：残高
        left = tk.Frame(c, bg=bg)
        left.pack(side="left", padx=(0, 24), anchor="n")
        tk.Label(left, text="現在残高",
                 font=FONT_SMALL_BOLD, bg=bg, fg="#555").pack(anchor="w")
        bal_str = f"¥ {balance:,}" if balance is not None else "—"
        tk.Label(left, text=bal_str, font=("MS Gothic", 18, "bold"),
                 bg=bg, fg=PANEL_CFG["預かり金"]["header"]).pack(anchor="w")

        # 右：直近の取引
        right = tk.Frame(c, bg=bg)
        right.pack(side="left", fill="x", expand=True, anchor="n")
        tk.Label(right, text="直近の取引",
                 font=FONT_SMALL_BOLD, bg=bg, fg="#555").pack(anchor="w")

        if not recent_rows:
            tk.Label(right, text="記録なし", font=FONT_SMALL, bg=bg, fg="#999").pack(anchor="w")
            return

        for r in recent_rows:
            f = tk.Frame(right, bg=bg)
            f.pack(fill="x", pady=1)

            # 収入・支出どちらかを表示する
            if r.get("income") and r["income"] > 0:
                amount_str = f"+¥{r['income']:,}"
                amount_fg  = "#2E7D32"
            elif r.get("expense") and r["expense"] > 0:
                amount_str = f"-¥{r['expense']:,}"
                amount_fg  = "#C62828"
            else:
                amount_str = "—"
                amount_fg  = "#999"

            tk.Label(f, text=fmt_date(r["transaction_date"]),
                     font=FONT_SMALL, bg=bg, fg="#555",
                     width=6, anchor="w").pack(side="left")
            tk.Label(f, text=r["description"][:16],
                     font=FONT_SMALL, bg=bg, fg="#333").pack(side="left", padx=4)
            tk.Label(f, text=amount_str, font=FONT_SMALL_BOLD,
                     bg=bg, fg=amount_fg).pack(side="left")


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    app = DashboardApp()
    app.mainloop()
