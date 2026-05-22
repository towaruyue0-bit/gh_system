# =============================================================================
# 個別支援計画 期限管理アプリ
# 入居者ごとに個別支援計画の作成日・次回見直し日を記録し、
# 期限が迫っている利用者を一覧でわかりやすく表示する
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
import webbrowser
import tempfile
import calendar
from datetime import datetime, date
# relativedelta が使えない場合は標準ライブラリだけで代替する
try:
    from dateutil.relativedelta import relativedelta
    _HAS_DATEUTIL = True
except ImportError:
    _HAS_DATEUTIL = False

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT  = r"C:\GH_Data"
DATA_DIR      = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR    = os.path.join(PRIVATE_ROOT, "support_plan_backups")
APP_DIR       = os.path.join(BASE_DIR, "support_plan_app")
RESIDENTS_DB  = os.path.join(DATA_DIR, "residents.db")
PLAN_DB       = os.path.join(DATA_DIR, "support_plans.db")
MAX_BACKUPS   = 10

# 期限アラートの閾値（日数）
DAYS_EXPIRED  = 0    # これを下回ると「期限切れ」
DAYS_CRITICAL = 30   # これ以下だと「要対応」（赤）
DAYS_WARNING  = 60   # これ以下だと「注意」（橙）

# フォント設定
FONT            = ("MS Gothic", 11)
FONT_BOLD       = ("MS Gothic", 11, "bold")
FONT_TITLE      = ("MS Gothic", 14, "bold")
FONT_SMALL      = ("MS Gothic", 10)
FONT_SMALL_BOLD = ("MS Gothic", 10, "bold")

# カラー設定
COLOR_BG       = "#F5F7FA"
COLOR_HEADER   = "#5C6A2E"   # 個別支援計画アプリのテーマ色（落ち着いた緑）
COLOR_HEADER_FG = "#FFFFFF"

# 一覧行の背景色（状態別）
BG_EXPIRED  = "#FFCCCC"   # 期限切れ  → 赤
BG_CRITICAL = "#FFE5CC"   # 要対応    → 橙
BG_WARNING  = "#FFF8D6"   # 注意      → 黄
BG_OK       = "#FFFFFF"   # 正常      → 白
BG_NONE     = "#EEEEEE"   # 未記録    → グレー

# サマリーカードの色
SUMMARY_COLORS = {
    "期限切れ": {"bg": "#FFCCCC", "fg": "#8B0000"},
    "要対応":   {"bg": "#FFE5CC", "fg": "#B35900"},
    "注意":     {"bg": "#FFF8D6", "fg": "#7A6000"},
    "正常":     {"bg": "#D6F5D6", "fg": "#1A5C1A"},
    "未記録":   {"bg": "#E8E8E8", "fg": "#555555"},
}

# 計画の種別選択肢
PLAN_TYPES = ["更新", "新規"]


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
    """個別支援計画DBのテーブルを作成する（なければ作成）"""
    conn = sqlite3.connect(PLAN_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS support_plans (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id  INTEGER NOT NULL,
            plan_date    TEXT    NOT NULL,
            review_date  TEXT    NOT NULL,
            plan_type    TEXT    DEFAULT '更新',
            author       TEXT    DEFAULT '',
            memo         TEXT    DEFAULT '',
            created_at   TEXT    DEFAULT (datetime('now', 'localtime')),
            updated_at   TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.commit()
    conn.close()


def _backup_db():
    """起動時にDBをバックアップする。MAX_BACKUPS を超えた分は古い順に削除する"""
    if not os.path.exists(PLAN_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(PLAN_DB, backup_file)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


def get_conn():
    """支援計画DB への接続を返す（列名アクセス対応）"""
    conn = sqlite3.connect(PLAN_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_residents_conn():
    """入居者マスターDB への接続を返す（読み取り専用）"""
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# ユーティリティ関数
# =============================================================================

def calc_days_remaining(review_date_str):
    """
    次回見直し日までの残日数を計算して返す。
    戻り値: int（負の値 = 期限切れ）、review_date_str が空なら None
    """
    if not review_date_str:
        return None
    try:
        review = datetime.strptime(review_date_str, "%Y-%m-%d").date()
        return (review - date.today()).days
    except ValueError:
        return None


def status_from_days(days):
    """
    残日数から状態文字列を返す。
    None の場合は「未記録」を返す。
    """
    if days is None:
        return "未記録"
    if days < DAYS_EXPIRED:
        return "期限切れ"
    if days <= DAYS_CRITICAL:
        return "要対応"
    if days <= DAYS_WARNING:
        return "注意"
    return "正常"


def bg_from_status(status):
    """状態文字列から行背景色を返す"""
    return {
        "期限切れ": BG_EXPIRED,
        "要対応":   BG_CRITICAL,
        "注意":     BG_WARNING,
        "正常":     BG_OK,
        "未記録":   BG_NONE,
    }.get(status, BG_OK)


def add_months(base_date_str, months):
    """
    日付文字列に指定した月数を加算して YYYY-MM-DD 形式で返す。
    dateutil が使えない場合は簡易計算（月末を超えた場合は月末に丸める）。
    """
    try:
        base = datetime.strptime(base_date_str, "%Y-%m-%d")
    except ValueError:
        return base_date_str

    if _HAS_DATEUTIL:
        result = base + relativedelta(months=months)
    else:
        # 標準ライブラリだけで月加算する
        month = base.month - 1 + months
        year  = base.year + month // 12
        month = month % 12 + 1
        day   = min(base.day, calendar.monthrange(year, month)[1])
        result = datetime(year, month, day)

    return result.strftime("%Y-%m-%d")


# =============================================================================
# 記録入力ダイアログ
# =============================================================================

class PlanRecordDialog(tk.Toplevel):
    """
    個別支援計画の記録入力ダイアログ。
    計画作成日・次回見直し日・種別・担当者・メモを入力する。

    引数:
        parent        : 親ウィンドウ
        resident_id   : 利用者ID
        resident_name : 利用者氏名
        record_id     : 編集する記録のID（新規の場合は None）
        existing      : 編集時の現在のデータ（辞書 or None）
    """

    def __init__(self, parent, resident_id, resident_name,
                 record_id=None, existing=None):
        super().__init__(parent)
        self.parent        = parent
        self.resident_id   = resident_id
        self.resident_name = resident_name
        self.record_id     = record_id
        self.existing      = existing or {}
        self.saved         = False

        mode = "編集" if record_id else "新規記録"
        self.title(f"個別支援計画 {mode} — {resident_name}")
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
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build(self):
        """ダイアログ全体の UI を構築する"""
        # ヘッダー
        hdr = tk.Frame(self, bg=COLOR_HEADER, pady=7)
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text=f"個別支援計画　{self.resident_name}",
                 font=FONT_BOLD, bg=COLOR_HEADER, fg=COLOR_HEADER_FG
                 ).pack(side="left", padx=16)

        # フォームエリア
        form = tk.Frame(self, bg="white", padx=28, pady=16)
        form.pack(fill="both")

        def section(text):
            """セクション見出しを作る"""
            f = tk.Frame(form, bg="#D8E8C8", pady=3)
            f.pack(fill="x", pady=(12, 4))
            tk.Label(f, text=f"  {text}",
                     font=FONT_SMALL_BOLD, bg="#D8E8C8", fg="#3A5A1A").pack(side="left")

        # --- 計画作成日 ---
        section("計画作成日")
        date_row = tk.Frame(form, bg="white")
        date_row.pack(fill="x")
        default_plan = self.existing.get("plan_date") or date.today().strftime("%Y-%m-%d")
        self.plan_date_var = tk.StringVar(value=default_plan)
        tk.Entry(date_row, textvariable=self.plan_date_var,
                 font=FONT, width=14, relief="solid", bd=1).pack(side="left", ipady=3)
        tk.Label(date_row, text="（例：2026-05-20）",
                 font=FONT_SMALL, bg="white", fg="#888").pack(side="left", padx=8)

        # --- 次回見直し日 ---
        section("次回見直し日（計画の期限）")
        review_row = tk.Frame(form, bg="white")
        review_row.pack(fill="x")
        default_review = self.existing.get("review_date") or ""
        self.review_date_var = tk.StringVar(value=default_review)
        tk.Entry(review_row, textvariable=self.review_date_var,
                 font=FONT, width=14, relief="solid", bd=1).pack(side="left", ipady=3)
        tk.Label(review_row, text="（例：2026-11-20）",
                 font=FONT_SMALL, bg="white", fg="#888").pack(side="left", padx=8)

        # 自動入力ボタン（+3ヶ月 / +6ヶ月）
        auto_row = tk.Frame(form, bg="white")
        auto_row.pack(fill="x", pady=(4, 0))
        tk.Label(auto_row, text="計画作成日から自動入力：",
                 font=FONT_SMALL, bg="white", fg="#555").pack(side="left")
        for months, label in [(3, "＋3ヶ月"), (6, "＋6ヶ月")]:
            tk.Button(auto_row, text=label, font=FONT_SMALL, relief="flat",
                      bg="#B8D8A0", fg="#2A4A10", padx=6, pady=1, cursor="hand2",
                      command=lambda m=months: self._autofill_review(m)
                      ).pack(side="left", padx=(4, 0))

        # --- 種別 ---
        section("種別")
        type_row = tk.Frame(form, bg="white")
        type_row.pack(fill="x")
        self.type_var = tk.StringVar(value=self.existing.get("plan_type") or "更新")
        for t in PLAN_TYPES:
            tk.Radiobutton(type_row, text=t, variable=self.type_var, value=t,
                           font=FONT, bg="white", activebackground="white",
                           selectcolor="#E8F5D8"
                           ).pack(side="left", padx=(0, 16))

        # --- 担当者名 ---
        section("担当者名")
        self.author_var = tk.StringVar(value=self.existing.get("author") or "")
        tk.Entry(form, textvariable=self.author_var,
                 font=FONT, width=20, relief="solid", bd=1).pack(anchor="w", ipady=3)

        # --- メモ ---
        section("メモ")
        self.memo_text = tk.Text(form, font=FONT, width=36, height=3,
                                 relief="solid", bd=1, wrap="word")
        self.memo_text.pack(fill="x", ipady=2)
        if self.existing.get("memo"):
            self.memo_text.insert("1.0", self.existing["memo"])

        # フッター（ボタン）
        footer = tk.Frame(self, bg="#EAEAEA", pady=10)
        footer.pack(fill="x")
        tk.Button(footer, text="  保存して閉じる  ", font=FONT_BOLD, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=14, pady=5, cursor="hand2",
                  command=self._save).pack(side="left", padx=(20, 8))
        tk.Button(footer, text="キャンセル", font=FONT, relief="flat",
                  padx=10, pady=5, cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _autofill_review(self, months):
        """計画作成日に指定月数を加算して次回見直し日を自動入力する"""
        plan_date = self.plan_date_var.get().strip()
        if not plan_date:
            messagebox.showwarning("入力エラー", "先に計画作成日を入力してください。", parent=self)
            return
        result = add_months(plan_date, months)
        self.review_date_var.set(result)

    def _save(self):
        """入力内容をバリデーションして DB に保存する"""
        plan_date   = self.plan_date_var.get().strip()
        review_date = self.review_date_var.get().strip()

        if not plan_date:
            messagebox.showerror("入力エラー", "計画作成日を入力してください。", parent=self)
            return
        if not review_date:
            messagebox.showerror("入力エラー", "次回見直し日を入力してください。", parent=self)
            return

        # 日付の書式チェック
        for label, val in [("計画作成日", plan_date), ("次回見直し日", review_date)]:
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError:
                messagebox.showerror(
                    "入力エラー",
                    f"{label} の形式が正しくありません。\n例：2026-05-20",
                    parent=self
                )
                return

        if plan_date > review_date:
            messagebox.showerror(
                "入力エラー",
                "次回見直し日は計画作成日より後の日付を入力してください。",
                parent=self
            )
            return

        author = self.author_var.get().strip() or None
        memo   = self.memo_text.get("1.0", "end-1c").strip() or None
        now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_conn()
        if self.record_id:
            conn.execute(
                """UPDATE support_plans SET
                       plan_date   = ?,
                       review_date = ?,
                       plan_type   = ?,
                       author      = ?,
                       memo        = ?,
                       updated_at  = ?
                   WHERE id = ?""",
                (plan_date, review_date, self.type_var.get(),
                 author, memo, now, self.record_id)
            )
        else:
            conn.execute(
                """INSERT INTO support_plans
                       (resident_id, plan_date, review_date, plan_type, author, memo, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.resident_id, plan_date, review_date,
                 self.type_var.get(), author, memo, now, now)
            )
        conn.commit()
        conn.close()
        self.saved = True
        self.destroy()


# =============================================================================
# 履歴ダイアログ
# =============================================================================

class PlanHistoryDialog(tk.Toplevel):
    """
    特定の利用者の個別支援計画履歴を一覧表示するダイアログ。

    引数:
        parent        : 親ウィンドウ
        resident_id   : 利用者ID
        resident_name : 利用者氏名
    """

    def __init__(self, parent, resident_id, resident_name):
        super().__init__(parent)
        self.title(f"計画履歴 — {resident_name}")
        self.geometry("640x400")
        self.resizable(True, True)
        self.grab_set()
        self._build(resident_id, resident_name)
        self._center(parent)

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build(self, resident_id, resident_name):
        """履歴一覧のUIを構築する"""
        hdr = tk.Frame(self, bg=COLOR_HEADER, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  計画履歴　{resident_name}",
                 font=FONT_BOLD, bg=COLOR_HEADER, fg="white").pack(side="left")

        frame = tk.Frame(self, bg=COLOR_BG)
        frame.pack(fill="both", expand=True, padx=10, pady=8)

        columns = ("plan_date", "review_date", "plan_type", "author", "memo")
        col_cfg = {
            "plan_date":   ("計画作成日", 100, "center"),
            "review_date": ("次回見直し日", 100, "center"),
            "plan_type":   ("種別",  70, "center"),
            "author":      ("担当者", 100, "center"),
            "memo":        ("メモ",  180, "w"),
        }
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for col, (hd, w, anc) in col_cfg.items():
            tree.heading(col, text=hd)
            tree.column(col, width=w, anchor=anc, minwidth=40)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # タグで行背景色を設定する
        tree.tag_configure("even", background="#FFFFFF")
        tree.tag_configure("odd",  background="#F0F4FA")

        # DBから履歴を取得して表示する（新しい順）
        conn = get_conn()
        rows = conn.execute(
            """SELECT plan_date, review_date, plan_type, author, memo
               FROM support_plans
               WHERE resident_id = ?
               ORDER BY plan_date DESC""",
            (resident_id,)
        ).fetchall()
        conn.close()

        for i, r in enumerate(rows):
            tag = "even" if i % 2 == 0 else "odd"
            tree.insert("", "end", tags=(tag,),
                        values=(r["plan_date"], r["review_date"],
                                r["plan_type"] or "",
                                r["author"]    or "—",
                                r["memo"]      or ""))

        if not rows:
            tk.Label(frame, text="記録がありません",
                     font=FONT, bg=COLOR_BG, fg="#999").grid(row=1, column=0)

        tk.Button(self, text="閉じる", font=FONT, relief="flat",
                  bg="#AAAAAA", fg="white", padx=14, pady=4, cursor="hand2",
                  command=self.destroy).pack(pady=8)


# =============================================================================
# メインアプリ
# =============================================================================

class SupportPlanApp(tk.Tk):
    """個別支援計画 期限管理アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("個別支援計画 期限管理")
        self.geometry("960x620")
        self.resizable(True, True)
        self.configure(bg=COLOR_BG)

        # 表示フィルター：None = 全員, それ以外は状態文字列でフィルタリング
        self.filter_status = None
        # 一覧データのキャッシュ（フィルタリングに使う）
        self._all_rows = []

        self._build_ui()
        self._load_data()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        """画面全体の UI を組み立てる"""

        # ---- ヘッダー ----
        header = tk.Frame(self, bg=COLOR_HEADER, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="個別支援計画  期限管理",
                 font=FONT_TITLE, bg=COLOR_HEADER, fg=COLOR_HEADER_FG).pack(side="left", padx=20)
        tk.Label(header, text="計画の見直し期限を一覧で確認・管理する",
                 font=FONT_SMALL, bg=COLOR_HEADER, fg="#CCDDBB").pack(side="left", padx=4)

        # ---- サマリーバー（状態別件数カード）----
        self.summary_frame = tk.Frame(self, bg=COLOR_BG, pady=6)
        self.summary_frame.pack(fill="x", padx=10)

        # ---- フィルター・操作バー ----
        ctrl = tk.Frame(self, bg="#E8EDF2", pady=6)
        ctrl.pack(fill="x", padx=10, pady=(0, 4))

        tk.Label(ctrl, text="絞り込み：", font=FONT, bg="#E8EDF2").pack(side="left", padx=(10, 4))

        self.filter_btns = {}
        filter_defs = [
            (None,      "すべて",  "#7B7B7B"),
            ("期限切れ", "期限切れ", "#8B0000"),
            ("要対応",   "要対応",  "#B35900"),
            ("注意",     "注意",   "#7A6000"),
            ("未記録",   "未記録",  "#444444"),
        ]
        for status, label, color in filter_defs:
            btn = tk.Button(
                ctrl, text=label, font=FONT_SMALL, relief="flat",
                bg=color, fg="white", padx=8, pady=2, cursor="hand2",
                command=lambda s=status: self._set_filter(s)
            )
            btn.pack(side="left", padx=(0, 4))
            self.filter_btns[status] = btn

        tk.Button(ctrl, text="  更新  ", font=FONT, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=10, pady=2,
                  cursor="hand2", command=self._load_data).pack(side="left", padx=(8, 0))

        # 右側のアクションボタン
        tk.Button(ctrl, text="  ＋ 新規記録  ", font=FONT_BOLD, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=10, pady=3,
                  cursor="hand2", command=self._new_record).pack(side="right", padx=(4, 10))
        tk.Button(ctrl, text="  削 除  ", font=FONT, relief="flat",
                  bg="#B71C1C", fg="white", padx=8, pady=3,
                  cursor="hand2", command=self._delete_record).pack(side="right", padx=4)
        tk.Button(ctrl, text="  編 集  ", font=FONT, relief="flat",
                  bg="#1565C0", fg="white", padx=8, pady=3,
                  cursor="hand2", command=self._edit_record).pack(side="right", padx=4)
        tk.Button(ctrl, text="  履 歴  ", font=FONT, relief="flat",
                  bg="#5C6A2E", fg="white", padx=8, pady=3,
                  cursor="hand2", command=self._show_history).pack(side="right", padx=4)
        tk.Button(ctrl, text="  印 刷  ", font=FONT, relief="flat",
                  bg="#5B7FA6", fg="white", padx=8, pady=3,
                  cursor="hand2", command=self._print_preview).pack(side="right", padx=4)

        # ---- 一覧テーブル ----
        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        columns = ("room", "name", "plan_date", "review_date", "days", "status",
                   "plan_type", "author")
        col_cfg = {
            "room":        ("部屋",     56, "center"),
            "name":        ("利用者名", 120, "w"),
            "plan_date":   ("計画作成日",  100, "center"),
            "review_date": ("次回見直し日", 100, "center"),
            "days":        ("残日数",   70, "center"),
            "status":      ("状態",     80, "center"),
            "plan_type":   ("種別",     60, "center"),
            "author":      ("担当者",  100, "center"),
        }

        self.tree = ttk.Treeview(
            list_frame, columns=columns,
            show="headings", selectmode="browse"
        )
        for col, (hd, w, anc) in col_cfg.items():
            self.tree.heading(col, text=hd,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anc, minwidth=30)

        vsb = ttk.Scrollbar(list_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # 行の背景色タグを設定する
        self.tree.tag_configure("expired",  background=BG_EXPIRED)
        self.tree.tag_configure("critical", background=BG_CRITICAL)
        self.tree.tag_configure("warning",  background=BG_WARNING)
        self.tree.tag_configure("ok",       background=BG_OK)
        self.tree.tag_configure("none",     background=BG_NONE)

        # ダブルクリックで編集を開く
        self.tree.bind("<Double-1>", lambda e: self._edit_record())

        # ---- ステータスバー ----
        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var,
                 font=FONT_SMALL, bg="#E0E4E8", anchor="w",
                 padx=10, pady=2).pack(fill="x", side="bottom")

        # ソート状態の管理
        self._sort_col = "days"
        self._sort_asc = True

        # 初期表示時にソートをデフォルトで「残日数の少ない順」にする
        self._highlight_filter_btn(None)

    # ------------------------------------------------------------------
    # データ読み込みと一覧表示
    # ------------------------------------------------------------------

    def _load_data(self):
        """DBから全データを読み込み、サマリーと一覧を更新する"""
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "DBが見つかりません",
                "入居者マスターDBが見つかりません。\n先に入居管理マスターアプリを起動してください。"
            )
            return

        r_conn = get_residents_conn()
        residents = r_conn.execute(
            "SELECT id, name, room_number FROM residents WHERE status='入居中' ORDER BY room_number"
        ).fetchall()
        r_conn.close()

        conn = get_conn()
        # 各入居者の最新計画（plan_date が最も新しいもの）を取得する
        latest_plans = conn.execute(
            """SELECT resident_id, plan_date, review_date, plan_type, author, id AS plan_id
               FROM support_plans
               WHERE id IN (
                   SELECT MAX(id) FROM support_plans GROUP BY resident_id
               )"""
        ).fetchall()
        conn.close()

        plan_map = {r["resident_id"]: dict(r) for r in latest_plans}

        self._all_rows = []
        for res in residents:
            plan = plan_map.get(res["id"])
            if plan:
                days        = calc_days_remaining(plan["review_date"])
                status      = status_from_days(days)
                days_disp   = (f"あと {days} 日" if days >= 0 else f"{abs(days)} 日超過")
                review_disp = plan["review_date"] or "—"
                plan_disp   = plan["plan_date"]   or "—"
                plan_type   = plan["plan_type"]   or "—"
                author      = plan["author"]      or "—"
                plan_id     = plan["plan_id"]
            else:
                days        = None
                status      = "未記録"
                days_disp   = "—"
                review_disp = "—"
                plan_disp   = "—"
                plan_type   = "—"
                author      = "—"
                plan_id     = None

            self._all_rows.append({
                "resident_id": res["id"],
                "room":        res["room_number"] or "—",
                "name":        res["name"],
                "plan_date":   plan_disp,
                "review_date": review_disp,
                "days":        days,
                "days_disp":   days_disp,
                "status":      status,
                "plan_type":   plan_type,
                "author":      author,
                "plan_id":     plan_id,
            })

        self._update_summary()
        self._apply_filter_and_sort()

    def _update_summary(self):
        """サマリーバーの件数カードを更新する"""
        for w in self.summary_frame.winfo_children():
            w.destroy()

        counts = {"期限切れ": 0, "要対応": 0, "注意": 0, "正常": 0, "未記録": 0}
        for r in self._all_rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1

        tk.Label(self.summary_frame, text="状態別：",
                 font=FONT_SMALL, bg=COLOR_BG, fg="#555").pack(side="left", padx=(4, 6))

        for status, count in counts.items():
            cfg = SUMMARY_COLORS.get(status, {"bg": "#EEE", "fg": "#333"})
            card = tk.Frame(self.summary_frame, bg=cfg["bg"],
                            bd=1, relief="solid", padx=10, pady=3)
            card.pack(side="left", padx=3)
            tk.Label(card, text=f"{status}  {count}件",
                     font=FONT_SMALL_BOLD, bg=cfg["bg"], fg=cfg["fg"]).pack()

    def _apply_filter_and_sort(self):
        """フィルターとソートを適用して一覧を再描画する"""
        # フィルタリング
        if self.filter_status is None:
            rows = list(self._all_rows)
        else:
            rows = [r for r in self._all_rows if r["status"] == self.filter_status]

        # ソート（残日数：None は最後に）
        col = self._sort_col
        asc = self._sort_asc

        def sort_key(r):
            if col == "days":
                # None（未記録）は末尾にする。期限切れ（負）は先頭にする
                v = r["days"]
                return (1, v) if v is not None else (2, 0)
            return str(r.get(col, ""))

        rows.sort(key=sort_key, reverse=not asc)

        # Treeview を再描画する
        for item in self.tree.get_children():
            self.tree.delete(item)

        for r in rows:
            tag = {
                "期限切れ": "expired",
                "要対応":   "critical",
                "注意":     "warning",
                "正常":     "ok",
                "未記録":   "none",
            }.get(r["status"], "ok")

            self.tree.insert(
                "", "end",
                iid=str(r["resident_id"]),
                tags=(tag,),
                values=(
                    r["room"], r["name"],
                    r["plan_date"], r["review_date"],
                    r["days_disp"], r["status"],
                    r["plan_type"], r["author"],
                )
            )

        count = len(rows)
        total = len(self._all_rows)
        suffix = f"（全{total}件中 {count}件表示）" if count != total else f"（{total}件）"
        self.status_var.set(f"入居中の利用者 {suffix}")

    def _set_filter(self, status):
        """フィルターを切り替えて一覧を更新する"""
        self.filter_status = status
        self._highlight_filter_btn(status)
        self._apply_filter_and_sort()

    def _highlight_filter_btn(self, active_status):
        """選択中のフィルターボタンを枠線で強調する"""
        for status, btn in self.filter_btns.items():
            if status == active_status:
                btn.configure(relief="sunken", bd=2)
            else:
                btn.configure(relief="flat", bd=0)

    def _sort_by(self, col):
        """列ヘッダーをクリックしたときにソートする"""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._apply_filter_and_sort()

    # ------------------------------------------------------------------
    # 選択行の情報取得
    # ------------------------------------------------------------------

    def _get_selected(self):
        """
        一覧で選択中の行データを返す。
        未選択なら None を返す。
        """
        sel = self.tree.selection()
        if not sel:
            return None
        resident_id = int(sel[0])
        for r in self._all_rows:
            if r["resident_id"] == resident_id:
                return r
        return None

    # ------------------------------------------------------------------
    # ボタンアクション
    # ------------------------------------------------------------------

    def _new_record(self):
        """選択中の利用者に新しい計画記録を追加する"""
        row = self._get_selected()
        if row is None:
            messagebox.showwarning("未選択", "記録を追加する利用者を選択してください。")
            return
        dlg = PlanRecordDialog(
            self, row["resident_id"], row["name"]
        )
        if dlg.saved:
            self._load_data()

    def _edit_record(self):
        """選択中の利用者の最新計画を編集する"""
        row = self._get_selected()
        if row is None:
            messagebox.showwarning("未選択", "編集する利用者を選択してください。")
            return
        if row["plan_id"] is None:
            # 計画がない場合は新規として開く
            self._new_record()
            return

        conn = get_conn()
        existing = conn.execute(
            "SELECT * FROM support_plans WHERE id = ?", (row["plan_id"],)
        ).fetchone()
        conn.close()

        dlg = PlanRecordDialog(
            self, row["resident_id"], row["name"],
            record_id=row["plan_id"],
            existing=dict(existing) if existing else None
        )
        if dlg.saved:
            self._load_data()

    def _delete_record(self):
        """選択中の利用者の最新計画記録を削除する"""
        row = self._get_selected()
        if row is None:
            messagebox.showwarning("未選択", "削除する利用者を選択してください。")
            return
        if row["plan_id"] is None:
            messagebox.showwarning("記録なし", "この利用者には計画記録がありません。")
            return

        ok = messagebox.askyesno(
            "削除の確認",
            f"{row['name']} の計画記録（作成日：{row['plan_date']}）を削除します。\nよろしいですか？",
            icon="warning"
        )
        if not ok:
            return
        conn = get_conn()
        conn.execute("DELETE FROM support_plans WHERE id = ?", (row["plan_id"],))
        conn.commit()
        conn.close()
        self._load_data()

    def _show_history(self):
        """選択中の利用者の計画履歴ダイアログを開く"""
        row = self._get_selected()
        if row is None:
            messagebox.showwarning("未選択", "履歴を確認する利用者を選択してください。")
            return
        PlanHistoryDialog(self, row["resident_id"], row["name"])

    # ------------------------------------------------------------------
    # 印刷プレビュー
    # ------------------------------------------------------------------

    def _print_preview(self):
        """現在表示中の一覧を印刷用HTMLとしてブラウザで開く"""
        rows = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            # (room, name, plan_date, review_date, days_disp, status, plan_type, author)
            rows.append(vals)

        today_str = date.today().strftime("%Y年%m月%d日")

        STATUS_BG = {
            "期限切れ": "#FFCCCC",
            "要対応":   "#FFE5CC",
            "注意":     "#FFF8D6",
            "正常":     "#FFFFFF",
            "未記録":   "#EEEEEE",
        }

        table_rows = ""
        for i, v in enumerate(rows):
            room, name, plan_date, review_date, days_disp, status, plan_type, author = v
            bg = STATUS_BG.get(status, "#FFFFFF")
            table_rows += (
                f'<tr style="background:{bg};">'
                f'<td class="c">{room}</td>'
                f'<td>{name}</td>'
                f'<td class="c">{plan_date}</td>'
                f'<td class="c">{review_date}</td>'
                f'<td class="c">{days_disp}</td>'
                f'<td class="c"><b>{status}</b></td>'
                f'<td class="c">{plan_type}</td>'
                f'<td class="c">{author}</td>'
                f'</tr>\n'
            )

        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>個別支援計画 期限一覧</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  body {{ font-family:"MS Gothic","Meiryo",sans-serif; font-size:10pt; color:#222; }}
  h1 {{ font-size:13pt; text-align:center; border-bottom:2px solid #5C6A2E;
       padding-bottom:4px; color:#5C6A2E; margin-bottom:8px; }}
  .sub {{ text-align:center; font-size:9pt; color:#666; margin-bottom:10px; }}
  table {{ border-collapse:collapse; width:100%; font-size:9pt; }}
  th {{ background:#5C6A2E; color:white; padding:4px 8px; text-align:center;
       font-weight:normal; }}
  td {{ padding:3px 6px; border-bottom:1px solid #DDD; }}
  td.c {{ text-align:center; }}
  @media print {{ .no-print {{ display:none; }} }}
</style>
</head>
<body>
<h1>個別支援計画　期限管理一覧</h1>
<p class="sub">出力日：{today_str}　　件数：{len(rows)} 件</p>
<table>
<thead><tr>
<th>部屋</th><th>利用者名</th><th>計画作成日</th><th>次回見直し日</th>
<th>残日数</th><th>状態</th><th>種別</th><th>担当者</th>
</tr></thead>
<tbody>
{table_rows}
</tbody>
</table>
<p class="no-print" style="margin-top:14px;color:#888;font-size:9pt;">
  ※ 印刷するにはブラウザの Ctrl+P をお使いください。用紙：A4横、余白：最小 を推奨します。
</p>
</body>
</html>"""

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8",
            delete=False, prefix="support_plan_print_"
        )
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = SupportPlanApp()
    app.mainloop()
