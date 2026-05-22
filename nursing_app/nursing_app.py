# =============================================================================
# 看護記録アプリ
# グループホーム 入居者 定期看護記録（月2回程度の聞き取り）管理システム
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
from datetime import datetime, date

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "nursing_backups")
APP_DIR      = os.path.join(BASE_DIR, "nursing_app")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
NURSING_DB   = os.path.join(DATA_DIR, "nursing_records.db")
MAX_BACKUPS  = 10

# フォント設定（日本語対応）
FONT            = ("MS Gothic", 11)
FONT_BOLD       = ("MS Gothic", 11, "bold")
FONT_TITLE      = ("MS Gothic", 14, "bold")
FONT_SMALL      = ("MS Gothic", 10)
FONT_SMALL_BOLD = ("MS Gothic", 10, "bold")

# テーマカラー（医療系グリーン）
COLOR_HEADER    = "#2E7D6E"
COLOR_HEADER_FG = "#FFFFFF"
COLOR_BTN       = "#2E7D6E"
COLOR_BTN_FG    = "#FFFFFF"
COLOR_CTRL_BG   = "#E8F0EE"
COLOR_PREV_BG   = "#F0F4F0"   # 前回記録パネルの背景
COLOR_PREV_HEADER = "#4A8F80"

# 聞き取り項目の選択肢
SLEEP_OPTIONS    = ["問題なし", "やや不良", "不眠気味"]
APPETITE_OPTIONS = ["問題なし", "やや不良", "食欲低下"]
BOWEL_OPTIONS    = ["問題なし", "不規則", "便秘傾向"]

# ステータス別の表示色（一覧画面のタグ用）
STATUS_WARN_VALUES = {"やや不良", "不眠気味", "食欲低下", "不規則"}
STATUS_BAD_VALUES  = {"不眠気味", "食欲低下", "便秘傾向"}

# 一覧の行背景色
ROW_BG_EVEN = "#FFFFFF"
ROW_BG_ODD  = "#F0F4FA"
ROW_BG_WARN = "#FFF3CD"   # 注意
ROW_BG_HIGH = "#FFE8E8"   # 要注意


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
    """看護記録DBのテーブルを作成し、旧バージョンからの列追加も行う"""
    conn = sqlite3.connect(NURSING_DB)
    c = conn.cursor()

    # テーブルを新規作成する（すでにあれば何もしない）
    c.execute("""
        CREATE TABLE IF NOT EXISTS nursing_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id    INTEGER NOT NULL,
            record_date    TEXT    NOT NULL,
            temperature    REAL,
            pulse          INTEGER,
            sleep_status   TEXT    DEFAULT '',
            sleep_note     TEXT    DEFAULT '',
            appetite_status TEXT   DEFAULT '',
            appetite_note  TEXT    DEFAULT '',
            bowel_status   TEXT    DEFAULT '',
            bowel_note     TEXT    DEFAULT '',
            concerns       TEXT    DEFAULT '',
            condition      TEXT    DEFAULT '',
            assessment     TEXT    DEFAULT '',
            recorded_by    TEXT    DEFAULT '',
            created_at     TEXT    DEFAULT (datetime('now', 'localtime')),
            updated_at     TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 旧バージョンのDBに存在しない列を追加する（既存列への ALTER は無視される）
    existing_cols = {row[1] for row in c.execute("PRAGMA table_info(nursing_records)")}
    new_cols = {
        "sleep_status":    "TEXT DEFAULT ''",
        "sleep_note":      "TEXT DEFAULT ''",
        "appetite_status": "TEXT DEFAULT ''",
        "appetite_note":   "TEXT DEFAULT ''",
        "bowel_status":    "TEXT DEFAULT ''",
        "bowel_note":      "TEXT DEFAULT ''",
        "concerns":        "TEXT DEFAULT ''",
        "assessment":      "TEXT DEFAULT ''",
        "recorded_by":     "TEXT DEFAULT ''",
    }
    for col, typedef in new_cols.items():
        if col not in existing_cols:
            c.execute(f"ALTER TABLE nursing_records ADD COLUMN {col} {typedef}")

    conn.commit()
    conn.close()


def _backup_db():
    """起動時にDBをバックアップする。MAX_BACKUPS を超えた分は古い順に削除する"""
    if not os.path.exists(NURSING_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(NURSING_DB, backup_file)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


def get_conn():
    """看護記録DB への接続を返す（列名アクセス対応）"""
    conn = sqlite3.connect(NURSING_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_residents_conn():
    """入居者マスターDB への接続を返す（読み取り専用）"""
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# 記録入力ダイアログ
# =============================================================================

class NursingRecordDialog(tk.Toplevel):
    """
    看護記録の入力ダイアログ。
    左側に入力フォーム、右側に前回記録を並べて表示し、比較しながら記録できる。

    引数:
        parent        : 親ウィンドウ
        resident_id   : 利用者ID
        resident_name : 利用者氏名
        record_id     : 編集する記録のID（新規の場合は None）
        existing      : 編集時の現在の記録データ（辞書 or None）
        prev_record   : 前回記録のデータ（辞書 or None）
    """

    def __init__(self, parent, resident_id, resident_name,
                 record_id=None, existing=None, prev_record=None):
        super().__init__(parent)
        self.parent        = parent
        self.resident_id   = resident_id
        self.resident_name = resident_name
        self.record_id     = record_id
        self.existing      = existing or {}
        self.prev_record   = prev_record
        self.saved         = False

        mode = "編集" if record_id else "新規記録"
        self.title(f"看護記録 {mode} — {resident_name}")
        self.geometry("1040x720")
        self.resizable(True, True)
        self.grab_set()
        self._build()
        self._center(parent)
        self.wait_window()

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        # 画面外にはみ出さないようにする
        x = max(0, x)
        y = max(0, y)
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build(self):
        """ダイアログ全体の UI を構築する"""

        # ---- タイトルバー ----
        header = tk.Frame(self, bg=COLOR_HEADER, pady=6)
        header.pack(fill="x")
        mode_text = "（編集中）" if self.record_id else "（新規）"
        tk.Label(
            header,
            text=f"看護記録　{self.resident_name}　{mode_text}",
            font=FONT_BOLD, bg=COLOR_HEADER, fg=COLOR_HEADER_FG
        ).pack(side="left", padx=16)

        # ---- メインエリア（左：入力 / 右：前回記録）----
        main = tk.Frame(self)
        main.pack(fill="both", expand=True, padx=0, pady=0)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=2)
        main.rowconfigure(0, weight=1)

        # 左：入力フォーム（スクロール可能）
        self._build_input_panel(main)

        # 仕切り線
        ttk.Separator(main, orient="vertical").grid(
            row=0, column=1, sticky="ns", padx=1
        )

        # 右：前回記録表示
        self._build_prev_panel(main)

        # ---- フッター（保存・キャンセル）----
        footer = tk.Frame(self, bg="#EAEAEA", pady=10)
        footer.pack(fill="x", side="bottom")
        tk.Button(
            footer, text="  保存して閉じる  ", font=FONT_BOLD, relief="flat",
            bg=COLOR_BTN, fg=COLOR_BTN_FG, padx=14, pady=5, cursor="hand2",
            command=self._save
        ).pack(side="left", padx=(20, 8))
        tk.Button(
            footer, text="キャンセル", font=FONT, relief="flat",
            padx=10, pady=5, cursor="hand2",
            command=self.destroy
        ).pack(side="left")

    def _build_input_panel(self, parent):
        """左側の入力フォームパネルを構築する"""

        # スクロール可能なフレームを用意する
        container = tk.Frame(parent)
        container.grid(row=0, column=0, sticky="nsew")

        canvas = tk.Canvas(container, highlightthickness=0, bg="white")
        vsb    = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        form = tk.Frame(canvas, bg="white", padx=20, pady=12)
        win  = canvas.create_window((0, 0), window=form, anchor="nw")
        form.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(win, width=e.width)
        )
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        form.bind("<MouseWheel>",
                  lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._form = form

        # --- 記録日 ---
        self._build_section_header(form, "記録日")
        date_frame = tk.Frame(form, bg="white")
        date_frame.pack(fill="x", pady=(0, 8))

        default_date = self.existing.get("record_date") or date.today().strftime("%Y-%m-%d")
        self.date_var = tk.StringVar(value=default_date)
        tk.Entry(
            date_frame, textvariable=self.date_var,
            font=FONT, width=14, relief="solid", bd=1
        ).pack(side="left", ipady=3)
        tk.Label(
            date_frame, text="（例：2026-05-20）",
            font=FONT_SMALL, bg="white", fg="#888"
        ).pack(side="left", padx=6)

        # --- バイタル ---
        self._build_section_header(form, "バイタル")
        vital_frame = tk.Frame(form, bg="white")
        vital_frame.pack(fill="x", pady=(0, 8))

        tk.Label(vital_frame, text="体温", font=FONT, bg="white").pack(side="left")
        self.temp_var = tk.StringVar(
            value=str(self.existing.get("temperature") or "")
        )
        tk.Entry(
            vital_frame, textvariable=self.temp_var,
            font=FONT, width=6, justify="center", relief="solid", bd=1
        ).pack(side="left", padx=(4, 2), ipady=3)
        tk.Label(vital_frame, text="℃", font=FONT, bg="white").pack(side="left", padx=(0, 20))

        tk.Label(vital_frame, text="脈拍", font=FONT, bg="white").pack(side="left")
        self.pulse_var = tk.StringVar(
            value=str(self.existing.get("pulse") or "")
        )
        tk.Entry(
            vital_frame, textvariable=self.pulse_var,
            font=FONT, width=5, justify="center", relief="solid", bd=1
        ).pack(side="left", padx=(4, 2), ipady=3)
        tk.Label(vital_frame, text="回/分", font=FONT, bg="white").pack(side="left")

        # --- 睡眠 ---
        self.sleep_var, self.sleep_note_var = self._build_radio_section(
            form,
            label="睡眠（眠れていますか？）",
            options=SLEEP_OPTIONS,
            current_status=self.existing.get("sleep_status") or "問題なし",
            current_note=self.existing.get("sleep_note") or "",
        )

        # --- 食事 ---
        self.appetite_var, self.appetite_note_var = self._build_radio_section(
            form,
            label="食事（食べられていますか？）",
            options=APPETITE_OPTIONS,
            current_status=self.existing.get("appetite_status") or "問題なし",
            current_note=self.existing.get("appetite_note") or "",
        )

        # --- 排便 ---
        self.bowel_var, self.bowel_note_var = self._build_radio_section(
            form,
            label="排便（便は出ていますか？）",
            options=BOWEL_OPTIONS,
            current_status=self.existing.get("bowel_status") or "問題なし",
            current_note=self.existing.get("bowel_note") or "",
        )

        # --- 困りごと ---
        self._build_section_header(form, "困りごと（本人から聞いたこと）")
        self.concerns_text = self._build_textarea(
            form,
            default=self.existing.get("concerns") or "",
            height=3
        )

        # --- 最近の様子 ---
        self._build_section_header(form, "最近の様子（客観的な観察）")
        self.condition_text = self._build_textarea(
            form,
            default=self.existing.get("condition") or "",
            height=4
        )

        # --- アセスメント ---
        self._build_section_header(form, "アセスメント（総合的な評価・判断）")
        self.assessment_text = self._build_textarea(
            form,
            default=self.existing.get("assessment") or "",
            height=4
        )

        # --- 記録者 ---
        self._build_section_header(form, "記録者名")
        recorded_frame = tk.Frame(form, bg="white")
        recorded_frame.pack(fill="x", pady=(0, 12))
        self.recorded_by_var = tk.StringVar(
            value=self.existing.get("recorded_by") or ""
        )
        tk.Entry(
            recorded_frame, textvariable=self.recorded_by_var,
            font=FONT, width=18, relief="solid", bd=1
        ).pack(side="left", ipady=3)

    def _build_section_header(self, parent, text):
        """セクション見出しを作る"""
        frame = tk.Frame(parent, bg="#D5E8E0", pady=3)
        frame.pack(fill="x", pady=(10, 4))
        tk.Label(
            frame, text=f"  {text}",
            font=FONT_SMALL_BOLD, bg="#D5E8E0", fg="#1A5C4E"
        ).pack(side="left")

    def _build_radio_section(self, parent, label, options, current_status, current_note):
        """
        ラジオボタン＋詳細テキスト入力のセクションを作る。
        「問題なし」以外が選ばれると詳細入力欄がハイライトされる。

        戻り値: (status_var, note_var)
        """
        self._build_section_header(parent, label)

        frame = tk.Frame(parent, bg="white")
        frame.pack(fill="x", pady=(0, 2))

        status_var = tk.StringVar(value=current_status)

        # ラジオボタンの色（問題なし=緑、その他=橙/赤）
        RADIO_COLORS = {
            options[0]: "#2E7D32",   # 問題なし → 緑
            options[1]: "#E65100",   # 中間 → 橙
            options[2]: "#C62828",   # 最悪 → 赤
        }

        for opt in options:
            rb = tk.Radiobutton(
                frame, text=opt, variable=status_var, value=opt,
                font=FONT, bg="white",
                activebackground="white",
                selectcolor="#E8F5E9",
                fg=RADIO_COLORS.get(opt, "#333"),
                command=lambda: self._on_radio_changed(status_var, note_entry, options)
            )
            rb.pack(side="left", padx=(0, 12))

        # 詳細テキスト入力欄（「問題なし」以外のとき使う）
        note_var = tk.StringVar(value=current_note)
        note_entry = tk.Entry(
            parent, textvariable=note_var,
            font=FONT, width=44, relief="solid", bd=1
        )
        note_entry.pack(fill="x", pady=(0, 4), ipady=3)

        tk.Label(
            parent,
            text="↑ 問題あり・気になる点があれば詳しく記入",
            font=FONT_SMALL, bg="white", fg="#888"
        ).pack(anchor="w", pady=(0, 4))

        # 初期状態でハイライトを設定する
        self._on_radio_changed(status_var, note_entry, options)

        return status_var, note_var

    def _on_radio_changed(self, status_var, note_entry, options):
        """
        ラジオボタンが変更されたとき、詳細入力欄の背景色を変える。
        「問題なし」以外が選ばれると入力欄を黄色くして記入を促す。
        """
        if status_var.get() == options[0]:
            note_entry.configure(bg="white")
        else:
            note_entry.configure(bg="#FFF9C4")  # 淡い黄色でハイライト

    def _build_textarea(self, parent, default, height):
        """複数行テキスト入力欄を作って返す"""
        text = tk.Text(
            parent, font=FONT, width=44, height=height,
            relief="solid", bd=1, wrap="word"
        )
        text.pack(fill="x", pady=(0, 4), ipady=2)
        text.bind("<MouseWheel>", lambda e: "break")  # テキストエリア内のスクロールを横取りしない
        if default:
            text.insert("1.0", default)
        return text

    # ------------------------------------------------------------------
    # 前回記録パネル
    # ------------------------------------------------------------------

    def _build_prev_panel(self, parent):
        """右側の前回記録表示パネルを構築する"""

        container = tk.Frame(parent, bg=COLOR_PREV_BG)
        container.grid(row=0, column=2, sticky="nsew")
        parent.columnconfigure(2, weight=2)

        # パネルヘッダー
        ph = tk.Frame(container, bg=COLOR_PREV_HEADER, pady=6)
        ph.pack(fill="x")
        tk.Label(
            ph, text="  前回記録（参照用）",
            font=FONT_BOLD, bg=COLOR_PREV_HEADER, fg="white"
        ).pack(side="left")

        if not self.prev_record:
            tk.Label(
                container,
                text="\n前回の記録はありません",
                font=FONT, bg=COLOR_PREV_BG, fg="#888"
            ).pack(expand=True)
            return

        # スクロール可能エリア
        canvas = tk.Canvas(container, highlightthickness=0, bg=COLOR_PREV_BG)
        vsb    = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = tk.Frame(canvas, bg=COLOR_PREV_BG, padx=14, pady=10)
        win   = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(win, width=e.width)
        )
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        p = self.prev_record

        # 記録日
        self._prev_row(inner, "記録日", p.get("record_date", ""))

        # バイタル
        temp_str  = f"{p['temperature']}℃" if p.get("temperature") else "—"
        pulse_str = f"{p['pulse']} 回/分"  if p.get("pulse")       else "—"
        self._prev_row(inner, "体温", temp_str)
        self._prev_row(inner, "脈拍", pulse_str)

        # 聞き取り項目
        for field_label, status_key, note_key in [
            ("睡眠",   "sleep_status",    "sleep_note"),
            ("食事",   "appetite_status", "appetite_note"),
            ("排便",   "bowel_status",    "bowel_note"),
        ]:
            status = p.get(status_key) or "—"
            note   = p.get(note_key)   or ""
            self._prev_status_row(inner, field_label, status, note)

        # テキスト項目
        for label, key in [
            ("困りごと",   "concerns"),
            ("最近の様子", "condition"),
            ("アセスメント", "assessment"),
        ]:
            self._prev_text_row(inner, label, p.get(key) or "（記録なし）")

        # 記録者
        self._prev_row(inner, "記録者", p.get("recorded_by") or "—")

    def _prev_row(self, parent, label, value):
        """前回記録パネルの1行（ラベル：値 形式）を作る"""
        frame = tk.Frame(parent, bg=COLOR_PREV_BG)
        frame.pack(fill="x", pady=2)
        tk.Label(
            frame, text=f"{label}：",
            font=FONT_SMALL_BOLD, bg=COLOR_PREV_BG,
            fg="#3A6B60", width=8, anchor="e"
        ).pack(side="left")
        tk.Label(
            frame, text=value,
            font=FONT_SMALL, bg=COLOR_PREV_BG, fg="#222",
            anchor="w", justify="left"
        ).pack(side="left")

    def _prev_status_row(self, parent, label, status, note):
        """ステータス（色付き）＋詳細テキストの行を作る"""
        # ステータスの色
        if status in STATUS_BAD_VALUES:
            status_fg = "#C62828"
        elif status in STATUS_WARN_VALUES:
            status_fg = "#E65100"
        else:
            status_fg = "#2E7D32"

        frame = tk.Frame(parent, bg=COLOR_PREV_BG, pady=1)
        frame.pack(fill="x")
        tk.Label(
            frame, text=f"{label}：",
            font=FONT_SMALL_BOLD, bg=COLOR_PREV_BG,
            fg="#3A6B60", width=8, anchor="e"
        ).pack(side="left")
        tk.Label(
            frame, text=status,
            font=FONT_SMALL_BOLD, bg=COLOR_PREV_BG, fg=status_fg
        ).pack(side="left")

        if note:
            note_frame = tk.Frame(parent, bg=COLOR_PREV_BG)
            note_frame.pack(fill="x", padx=(80, 0))
            tk.Label(
                note_frame, text=note,
                font=FONT_SMALL, bg=COLOR_PREV_BG, fg="#555",
                anchor="w", justify="left", wraplength=260
            ).pack(anchor="w")

    def _prev_text_row(self, parent, label, text):
        """テキスト項目（ラベル＋複数行テキスト）の行を作る"""
        # セクション区切り
        sep_frame = tk.Frame(parent, bg="#B8D5CC", height=1)
        sep_frame.pack(fill="x", pady=(8, 4))

        tk.Label(
            parent, text=label,
            font=FONT_SMALL_BOLD, bg=COLOR_PREV_BG, fg="#3A6B60"
        ).pack(anchor="w", pady=(0, 2))

        # テキストが長い場合は読みやすく折り返して表示する
        tk.Label(
            parent, text=text or "（記録なし）",
            font=FONT_SMALL, bg=COLOR_PREV_BG, fg="#333",
            anchor="w", justify="left",
            wraplength=280
        ).pack(anchor="w", padx=4, pady=(0, 6))

    # ------------------------------------------------------------------
    # バリデーション・保存
    # ------------------------------------------------------------------

    def _parse_float(self, s):
        """文字列を浮動小数点数に変換する。空文字や変換不可なら None を返す"""
        s = s.strip()
        return float(s) if s else None

    def _parse_int(self, s):
        """文字列を整数に変換する。空文字や変換不可なら None を返す"""
        s = s.strip()
        return int(s) if s else None

    def _save(self):
        """入力内容をバリデーションしてDBに保存する"""
        record_date = self.date_var.get().strip()
        if not record_date:
            messagebox.showerror("入力エラー", "記録日を入力してください。", parent=self)
            return
        # 日付の形式チェック
        try:
            datetime.strptime(record_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "入力エラー",
                "記録日の形式が正しくありません。\n例：2026-05-20",
                parent=self
            )
            return

        # バイタルのパースとチェック
        try:
            temperature = self._parse_float(self.temp_var.get())
        except ValueError:
            messagebox.showerror("入力エラー", "体温は数値で入力してください。", parent=self)
            return
        try:
            pulse = self._parse_int(self.pulse_var.get())
        except ValueError:
            messagebox.showerror("入力エラー", "脈拍は整数で入力してください。", parent=self)
            return

        if temperature is not None and not (30.0 <= temperature <= 42.0):
            messagebox.showerror("入力エラー", "体温は 30.0〜42.0 の範囲で入力してください。", parent=self)
            return
        if pulse is not None and not (20 <= pulse <= 250):
            messagebox.showerror("入力エラー", "脈拍は 20〜250 の範囲で入力してください。", parent=self)
            return

        # テキスト項目を取得する（空文字は None に変換する）
        def get_text(widget):
            return widget.get("1.0", "end-1c").strip() or None

        sleep_status    = self.sleep_var.get()    or None
        sleep_note      = self.sleep_note_var.get().strip()    or None
        appetite_status = self.appetite_var.get() or None
        appetite_note   = self.appetite_note_var.get().strip() or None
        bowel_status    = self.bowel_var.get()    or None
        bowel_note      = self.bowel_note_var.get().strip()    or None
        concerns        = get_text(self.concerns_text)
        condition       = get_text(self.condition_text)
        assessment      = get_text(self.assessment_text)
        recorded_by     = self.recorded_by_var.get().strip() or None

        conn = get_conn()
        if self.record_id:
            # 既存レコードを更新する
            conn.execute(
                """UPDATE nursing_records SET
                       record_date     = ?,
                       temperature     = ?,
                       pulse           = ?,
                       sleep_status    = ?,
                       sleep_note      = ?,
                       appetite_status = ?,
                       appetite_note   = ?,
                       bowel_status    = ?,
                       bowel_note      = ?,
                       concerns        = ?,
                       condition       = ?,
                       assessment      = ?,
                       recorded_by     = ?,
                       updated_at      = datetime('now', 'localtime')
                   WHERE id = ?""",
                (record_date, temperature, pulse,
                 sleep_status, sleep_note,
                 appetite_status, appetite_note,
                 bowel_status, bowel_note,
                 concerns, condition, assessment, recorded_by,
                 self.record_id)
            )
        else:
            # 新しいレコードを追加する
            conn.execute(
                """INSERT INTO nursing_records
                       (resident_id, record_date, temperature, pulse,
                        sleep_status, sleep_note,
                        appetite_status, appetite_note,
                        bowel_status, bowel_note,
                        concerns, condition, assessment, recorded_by)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (self.resident_id, record_date, temperature, pulse,
                 sleep_status, sleep_note,
                 appetite_status, appetite_note,
                 bowel_status, bowel_note,
                 concerns, condition, assessment, recorded_by)
            )
        conn.commit()
        conn.close()
        self.saved = True
        self.destroy()


# =============================================================================
# 削除確認ダイアログ
# =============================================================================

def confirm_delete(parent, record_date, resident_name):
    """
    削除前の確認ダイアログを表示する。
    戻り値: True（削除する）/ False（キャンセル）
    """
    return messagebox.askyesno(
        "削除の確認",
        f"{resident_name} の {record_date} の記録を削除します。\nよろしいですか？",
        parent=parent,
        icon="warning"
    )


# =============================================================================
# メインアプリ
# =============================================================================

class NursingApp(tk.Tk):
    """看護記録アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("看護記録")
        self.geometry("900x620")
        self.resizable(True, True)
        self.configure(bg="#F5F7FA")

        self.selected_resident_id   = None
        self.selected_resident_name = ""
        self._residents = {}   # {表示名: resident_id}

        self._build_ui()
        self._load_residents()

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        """画面全体の UI を組み立てる"""

        # ---- ヘッダー ----
        header = tk.Frame(self, bg=COLOR_HEADER, pady=8)
        header.pack(fill="x")
        tk.Label(
            header, text="看護記録",
            font=FONT_TITLE, bg=COLOR_HEADER, fg=COLOR_HEADER_FG
        ).pack(side="left", padx=20)
        tk.Label(
            header,
            text="定期聞き取り（睡眠・食事・排便・困りごと）の記録",
            font=FONT_SMALL, bg=COLOR_HEADER, fg="#AADDCC"
        ).pack(side="left", padx=4)

        # ---- コントロールバー ----
        ctrl = tk.Frame(self, bg=COLOR_CTRL_BG, pady=7)
        ctrl.pack(fill="x", padx=10, pady=(6, 0))

        tk.Label(ctrl, text="利用者：", font=FONT, bg=COLOR_CTRL_BG).pack(side="left", padx=(10, 2))
        self.resident_cb = ttk.Combobox(ctrl, font=FONT, width=16, state="readonly")
        self.resident_cb.pack(side="left", padx=(0, 16))
        self.resident_cb.bind("<<ComboboxSelected>>", self._on_resident_changed)

        # 右側のボタン群
        tk.Button(
            ctrl, text="  ＋ 新規記録  ", font=FONT_BOLD, relief="flat",
            bg=COLOR_BTN, fg=COLOR_BTN_FG, padx=10, pady=3,
            cursor="hand2", command=self._new_record
        ).pack(side="right", padx=(4, 10))

        tk.Button(
            ctrl, text="  削 除  ", font=FONT, relief="flat",
            bg="#B71C1C", fg="white", padx=8, pady=3,
            cursor="hand2", command=self._delete_record
        ).pack(side="right", padx=4)

        tk.Button(
            ctrl, text="  編 集  ", font=FONT, relief="flat",
            bg="#1565C0", fg="white", padx=8, pady=3,
            cursor="hand2", command=self._edit_record
        ).pack(side="right", padx=4)

        # ---- 一覧テーブル ----
        list_frame = tk.Frame(self, bg="#F5F7FA")
        list_frame.pack(fill="both", expand=True, padx=10, pady=8)

        # ヘッダー列の定義
        columns = ("date", "temp", "pulse", "sleep", "appetite", "bowel",
                   "concerns", "condition", "recorded_by")
        col_config = {
            "date":        ("記録日",       100, "center"),
            "temp":        ("体温",          68, "center"),
            "pulse":       ("脈拍",          68, "center"),
            "sleep":       ("睡眠",          88, "center"),
            "appetite":    ("食事",          88, "center"),
            "bowel":       ("排便",          88, "center"),
            "concerns":    ("困りごと",     140, "w"),
            "condition":   ("最近の様子",   180, "w"),
            "recorded_by": ("記録者",        80, "center"),
        }

        self.tree = ttk.Treeview(
            list_frame, columns=columns,
            show="headings", selectmode="browse"
        )
        for col, (heading, width, anchor) in col_config.items():
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor=anchor, minwidth=40)

        # スクロールバー
        vsb = ttk.Scrollbar(list_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # 行の背景色タグを設定する
        self.tree.tag_configure("even",      background=ROW_BG_EVEN)
        self.tree.tag_configure("odd",       background=ROW_BG_ODD)
        self.tree.tag_configure("warn",      background=ROW_BG_WARN)
        self.tree.tag_configure("bad",       background=ROW_BG_HIGH)

        # ダブルクリックで編集を開く
        self.tree.bind("<Double-1>", lambda e: self._edit_record())

        # ---- ステータスバー ----
        self.status_var = tk.StringVar(value="利用者を選択してください")
        tk.Label(
            self, textvariable=self.status_var,
            font=FONT_SMALL, bg="#E0E4E8", anchor="w", padx=10, pady=2
        ).pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # データ読み込み
    # ------------------------------------------------------------------

    def _load_residents(self):
        """入居中の利用者をドロップダウンに読み込む"""
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "DBが見つかりません",
                f"入居者マスターDBが見つかりません。\n{RESIDENTS_DB}",
                parent=self
            )
            return
        try:
            conn = get_residents_conn()
            rows = conn.execute(
                "SELECT id, name FROM residents WHERE status='入居中' ORDER BY room_number"
            ).fetchall()
            conn.close()

            self._residents = {r["name"]: r["id"] for r in rows}
            names = list(self._residents.keys())
            self.resident_cb["values"] = names
            if names:
                self.resident_cb.current(0)
                self._on_resident_changed(None)
        except Exception as e:
            messagebox.showerror("読み込みエラー", str(e), parent=self)

    def _on_resident_changed(self, event):
        """ドロップダウンで利用者が変わったとき一覧を再読み込みする"""
        name = self.resident_cb.get()
        if name not in self._residents:
            return
        self.selected_resident_id   = self._residents[name]
        self.selected_resident_name = name
        self._reload_list()

    def _reload_list(self):
        """選択中の利用者の記録一覧を DB から読み込んで表示する（新しい順）"""
        for row in self.tree.get_children():
            self.tree.delete(row)

        if self.selected_resident_id is None:
            return

        conn    = get_conn()
        records = conn.execute(
            """SELECT id, record_date, temperature, pulse,
                      sleep_status, appetite_status, bowel_status,
                      concerns, condition, recorded_by
               FROM nursing_records
               WHERE resident_id = ?
               ORDER BY record_date DESC""",
            (self.selected_resident_id,)
        ).fetchall()
        conn.close()

        for i, r in enumerate(records):
            # 体温・脈拍の表示テキスト
            temp_str  = f"{r['temperature']}℃" if r["temperature"] is not None else "—"
            pulse_str = f"{r['pulse']}"         if r["pulse"]        is not None else "—"

            # 長いテキストは省略して表示する（一覧を見やすくする）
            concerns_short  = (r["concerns"]  or "")[:20]
            condition_short = (r["condition"] or "")[:30]

            values = (
                r["record_date"],
                temp_str,
                pulse_str,
                r["sleep_status"]    or "—",
                r["appetite_status"] or "—",
                r["bowel_status"]    or "—",
                concerns_short,
                condition_short,
                r["recorded_by"]     or "—",
            )

            # 問題のある項目があれば行を色づけする
            statuses = [r["sleep_status"], r["appetite_status"], r["bowel_status"]]
            if any(s in STATUS_BAD_VALUES  for s in statuses if s):
                tag = "bad"
            elif any(s in STATUS_WARN_VALUES for s in statuses if s):
                tag = "warn"
            elif i % 2 == 0:
                tag = "even"
            else:
                tag = "odd"

            # iid（行ID）として DB の id を使うと選択時に取得しやすい
            self.tree.insert("", "end", iid=str(r["id"]), values=values, tags=(tag,))

        self.status_var.set(
            f"{self.selected_resident_name}　記録件数：{len(records)}件"
        )

    # ------------------------------------------------------------------
    # 記録の取得ヘルパー
    # ------------------------------------------------------------------

    def _get_selected_record_id(self):
        """一覧で選択中の行の DB ID を返す。未選択なら None を返す"""
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _fetch_record(self, record_id):
        """DB から指定 ID のレコードを辞書で返す"""
        conn = get_conn()
        row  = conn.execute(
            "SELECT * FROM nursing_records WHERE id = ?", (record_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def _fetch_prev_record(self, record_date, exclude_id=None):
        """
        指定日付より前の直近の記録を返す（前回記録として参照するため）。
        exclude_id を指定すると、そのIDのレコードを除外する。
        """
        conn = get_conn()
        if exclude_id:
            row = conn.execute(
                """SELECT * FROM nursing_records
                   WHERE resident_id = ? AND record_date < ? AND id != ?
                   ORDER BY record_date DESC LIMIT 1""",
                (self.selected_resident_id, record_date, exclude_id)
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM nursing_records
                   WHERE resident_id = ? AND record_date < ?
                   ORDER BY record_date DESC LIMIT 1""",
                (self.selected_resident_id, record_date)
            ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # ボタンアクション
    # ------------------------------------------------------------------

    def _new_record(self):
        """新規記録ダイアログを開く。前回記録として最新のレコードを参照として渡す"""
        if self.selected_resident_id is None:
            messagebox.showwarning("未選択", "利用者を選択してください。", parent=self)
            return

        today = date.today().strftime("%Y-%m-%d")
        prev  = self._fetch_prev_record(today)

        dlg = NursingRecordDialog(
            self,
            resident_id=self.selected_resident_id,
            resident_name=self.selected_resident_name,
            prev_record=prev
        )
        if dlg.saved:
            self._reload_list()

    def _edit_record(self):
        """選択中の記録を編集ダイアログで開く。その直前の記録を参照として渡す"""
        record_id = self._get_selected_record_id()
        if record_id is None:
            messagebox.showwarning("未選択", "編集する記録を選んでください。", parent=self)
            return

        existing = self._fetch_record(record_id)
        if not existing:
            return

        prev = self._fetch_prev_record(
            record_date=existing["record_date"],
            exclude_id=record_id
        )

        dlg = NursingRecordDialog(
            self,
            resident_id=self.selected_resident_id,
            resident_name=self.selected_resident_name,
            record_id=record_id,
            existing=existing,
            prev_record=prev
        )
        if dlg.saved:
            self._reload_list()

    def _delete_record(self):
        """選択中の記録を削除する"""
        record_id = self._get_selected_record_id()
        if record_id is None:
            messagebox.showwarning("未選択", "削除する記録を選んでください。", parent=self)
            return

        existing = self._fetch_record(record_id)
        if not existing:
            return

        if not confirm_delete(self, existing["record_date"], self.selected_resident_name):
            return

        conn = get_conn()
        conn.execute("DELETE FROM nursing_records WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        self._reload_list()


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = NursingApp()
    app.mainloop()
