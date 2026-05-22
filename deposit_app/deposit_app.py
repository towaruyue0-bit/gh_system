# =============================================================================
# 預かり金管理アプリ
# グループホーム 利用者預かり金収支管理システム
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
import json
from datetime import datetime, date

# PDF生成ライブラリの読み込み（未インストールの場合はフラグを立てて後でエラー表示）
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# カレンダーウィジェットの読み込み（未インストールでも直接入力で動作する）
try:
    from tkcalendar import Calendar as TkCalendar
    TKCALENDAR_OK = True
except ImportError:
    TKCALENDAR_OK = False

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT  = r"C:\GH_Data"  # 個人情報を保管する安全フォルダ（OneDrive・Claude非対応）
DATA_DIR      = os.path.join(PRIVATE_ROOT, "data")
APP_DIR       = os.path.join(BASE_DIR, "deposit_app")
BACKUP_DIR    = os.path.join(PRIVATE_ROOT, "deposit_backups")
OUTPUT_DIR    = os.path.join(APP_DIR, "output")
RESIDENTS_DB  = os.path.join(DATA_DIR, "residents.db")
DEPOSIT_DB    = os.path.join(DATA_DIR, "deposit.db")
SETTINGS_PATH = os.path.join(BASE_DIR, "billing_app", "settings.json")
MAX_BACKUPS   = 10

# =============================================================================
# フォント設定（日本語対応）
# =============================================================================
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 一覧テーブルの行背景色（交互表示）
ROW_ODD  = "#FFFFFF"
ROW_EVEN = "#F0F4FA"

# =============================================================================
# 初期セットアップ関数
# =============================================================================

def setup_directories():
    """起動時に必要なフォルダが無ければ自動作成する"""
    for d in [DATA_DIR, APP_DIR, BACKUP_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)


def setup_database():
    """預かり金DBとテーブルが無ければ自動作成する"""
    conn = sqlite3.connect(DEPOSIT_DB)
    c = conn.cursor()
    # 収支明細テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS deposit_transactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id      INTEGER NOT NULL,
            transaction_date TEXT    NOT NULL,
            description      TEXT    NOT NULL,
            income           INTEGER DEFAULT 0,
            expense          INTEGER DEFAULT 0,
            created_at       TEXT,
            updated_at       TEXT
        )
    """)
    # 通院費ポーチ残高テーブル（利用者ごとに1件だけ保持する）
    # resident_id を PRIMARY KEY にすることで、同じ利用者のデータは必ず1件になる
    c.execute("""
        CREATE TABLE IF NOT EXISTS medical_reserve (
            resident_id INTEGER PRIMARY KEY,
            amount      INTEGER DEFAULT 0,
            updated_at  TEXT
        )
    """)
    # 金銭チェックログテーブル（預かり金合計と金庫現金が一致したときの記録）
    c.execute("""
        CREATE TABLE IF NOT EXISTS cash_check_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at    TEXT    NOT NULL,
            deposit_total INTEGER NOT NULL,
            safe_total    INTEGER NOT NULL,
            denominations TEXT    NOT NULL,
            created_at    TEXT
        )
    """)
    conn.commit()
    conn.close()


def do_backup():
    """
    起動時に預かり金DBをバックアップする。
    BACKUP_DIR 内のファイルが MAX_BACKUPS を超えたら古い順に削除する。
    """
    if not os.path.exists(DEPOSIT_DB):
        return  # DBがまだ存在しない場合はスキップ

    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(DEPOSIT_DB, backup_file)

    # 古いバックアップを削除
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


# =============================================================================
# 施設情報の読み込み
# =============================================================================

def load_issuer_info():
    """
    billing_app/settings.json から施設情報を読み込む。
    ファイルが見つからない場合は空の辞書を返す。
    """
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("issuer", {})
    except Exception:
        return {}


# =============================================================================
# PDF生成関数
# =============================================================================

def _to_wareki(year, month=None, day=None):
    """
    西暦を和暦（令和／平成）に変換する。

    Args:
        year  (int): 西暦年
        month (int): 月（省略可）
        day   (int): 日（省略可）
    Returns:
        str: 「令和8年5月13日」のような和暦文字列
    """
    if year >= 2019:
        era      = "令和"
        era_year = year - 2018
    else:
        era      = "平成"
        era_year = year - 1988

    if month is None:
        return f"{era}{era_year}年"
    if day is None:
        return f"{era}{era_year}年{month}月"
    return f"{era}{era_year}年{month}月{day}日"


def generate_pdf(resident_name, year, month, transactions, opening_balance,
                 medical_reserve=0):
    """
    月次の預かり金収支明細PDFを生成する。

    Args:
        resident_name   (str):  利用者名
        year            (int):  対象年
        month           (int):  対象月
        transactions    (list): その月の取引リスト（sqlite3.Row のリスト）
        opening_balance (int):  月初残高（前月末までの累計）
        medical_reserve (int):  通院費ポーチ残高（別保管分）。0 の場合は表示しない。

    Returns:
        str: 生成したPDFのファイルパス。失敗した場合は None。
    """
    if not REPORTLAB_OK:
        messagebox.showerror(
            "ライブラリ未インストール",
            "PDF生成には reportlab が必要です。\n\n"
            "コマンドプロンプトで以下を実行してください：\n"
            "pip install reportlab"
        )
        return None

    # Windows の MS Gothic フォントを登録（日本語を正しく表示するため）
    font_path = r"C:\Windows\Fonts\msgothic.ttc"
    try:
        pdfmetrics.registerFont(TTFont("MSGothic", font_path, subfontIndex=0))
        font_name = "MSGothic"
    except Exception:
        # フォント登録に失敗した場合はデフォルトフォントで続行
        font_name = "Helvetica"

    # 出力ファイルパス
    filename = f"金銭管理収支報告書_{resident_name}_{year}{month:02d}.pdf"
    filepath = os.path.join(OUTPUT_DIR, filename)

    # 施設情報の取得
    issuer    = load_issuer_info()
    org_name  = issuer.get("org",   "")
    home_name = issuer.get("name",  "")
    addr      = issuer.get("addr",  "")
    tel       = issuer.get("tel",   "")
    email     = issuer.get("email", "")

    # PDFドキュメント設定（A4縦）
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    # スタイル定義
    s_normal  = ParagraphStyle("normal",  fontName=font_name, fontSize=10, leading=16)
    s_title   = ParagraphStyle("title",   fontName=font_name, fontSize=15, leading=22, alignment=1)
    s_right   = ParagraphStyle("right",   fontName=font_name, fontSize=10, leading=16, alignment=2)
    s_small   = ParagraphStyle("small",   fontName=font_name, fontSize=8,  leading=13)
    s_sign_hd = ParagraphStyle("sign_hd", fontName=font_name, fontSize=9,  leading=16)

    elements = []

    # --- タイトル ---
    elements.append(Paragraph("金銭管理収支報告書", s_title))
    elements.append(Spacer(1, 5 * mm))

    # --- 利用者名（左）・発行日（右） ---
    today     = datetime.now()
    today_str = _to_wareki(today.year, today.month, today.day)
    name_date_data = [[
        Paragraph(f"利用者氏名　{resident_name}　様", s_normal),
        Paragraph(today_str, s_right),
    ]]
    name_date_table = Table(name_date_data, colWidths=[120 * mm, 60 * mm])
    name_date_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("VALIGN",   (0, 0), (-1, -1), "BOTTOM"),
        # 利用者名の下に下線
        ("LINEBELOW", (0, 0), (0, 0), 0.5, colors.black),
    ]))
    elements.append(name_date_table)
    elements.append(Spacer(1, 4 * mm))

    # --- 挨拶文 ---
    target_wareki = _to_wareki(year, month)
    greeting = (f"{target_wareki}分　金銭管理の収支報告をさせていただきます。"
                "ご確認のほど、よろしくお願いいたします。")
    elements.append(Paragraph(greeting, s_normal))
    elements.append(Spacer(1, 4 * mm))

    # --- 収支明細テーブル ---
    # テンプレートに合わせた列幅・列名
    col_widths = [23 * mm, 73 * mm, 25 * mm, 25 * mm, 34 * mm]
    header = ["日付", "摘要", "入金額", "出金額", "残高"]

    table_data = [header]

    # 通院費ポーチ残高を月初残高に含めて表示する
    display_opening = opening_balance + medical_reserve

    # 前月繰越金行（日付なし）
    table_data.append(["", "前月繰越金", "", "", f"¥{display_opening:,}"])

    # 取引明細行（残高を累計しながら追加）
    balance       = display_opening
    total_income  = 0
    total_expense = 0
    for row in transactions:
        balance       += row["income"] - row["expense"]
        total_income  += row["income"]
        total_expense += row["expense"]
        # 日付を「M月D日」形式に変換（例: 2026-03-25 → 3月25日）
        try:
            parts    = row["transaction_date"].split("-")
            date_str = f"{int(parts[1])}月{int(parts[2])}日"
        except Exception:
            date_str = row["transaction_date"]
        table_data.append([
            date_str,
            row["description"],
            f"¥{row['income']:,}"  if row["income"]  > 0 else "",
            f"¥{row['expense']:,}" if row["expense"] > 0 else "",
            f"¥{balance:,}",
        ])

    # テンプレートに合わせて空行を追加し、最低行数を確保する（当月合計行を除く）
    MIN_DATA_ROWS = 16
    while len(table_data) - 1 < MIN_DATA_ROWS:
        table_data.append(["", "", "", "", ""])

    # 当月合計行
    table_data.append(["", "当月合計",
                        f"¥{total_income:,}",
                        f"¥{total_expense:,}",
                        f"¥{balance:,}"])

    # ティール系の配色（テンプレートに近い色）
    COLOR_HEADER = colors.HexColor("#31849B")   # ダークティール（ヘッダー）
    COLOR_ALT    = colors.HexColor("#DAEEF3")   # 薄いティール（偶数行）
    COLOR_TOTAL  = colors.HexColor("#BDD7EE")   # やや濃いティール（合計行）

    row_count      = len(table_data)
    alternating_bg = [
        ("BACKGROUND", (0, i), (-1, i), COLOR_ALT)
        for i in range(2, row_count - 1, 2)
    ]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # フォント
        ("FONTNAME",   (0, 0), (-1, -1), font_name),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        # ヘッダー行
        ("BACKGROUND", (0, 0), (-1, 0),  COLOR_HEADER),
        ("TEXTCOLOR",  (0, 0), (-1, 0),  colors.white),
        ("ALIGN",      (0, 0), (-1, 0),  "CENTER"),
        # 前月繰越金行の背景
        ("BACKGROUND", (0, 1), (-1, 1),  COLOR_ALT),
        # 当月合計行の背景
        ("BACKGROUND", (0, -1), (-1, -1), COLOR_TOTAL),
        # 金額列（入金・出金・残高）は右寄せ
        ("ALIGN",      (2, 1), (-1, -1), "RIGHT"),
        # 日付列は中央寄せ
        ("ALIGN",      (0, 1), (0, -1),  "CENTER"),
        # 縦方向は中央
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        # 行の高さ
        ("ROWHEIGHT",  (0, 0), (-1, -1), 7.5 * mm),
        # 罫線
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#A0A0A0")),
        ("LINEBELOW",  (0, 0), (-1, 0),  1.0, COLOR_HEADER),
        *alternating_bg,
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5 * mm))

    # --- フッター：左に施設情報、右に確認欄 ---
    s_footer = ParagraphStyle("footer", fontName=font_name, fontSize=8, leading=13)

    # 左カラム：施設情報
    left_lines = []
    if org_name:
        left_lines.append(org_name)
    if home_name:
        left_lines.append(home_name)
    if addr:
        left_lines.append(f"住所：{addr}")
    if tel:
        left_lines.append(f"電話：{tel}")
    if email:
        left_lines.append(f"email: {email}")
    left_text = "<br/>".join(left_lines)

    # 右カラム：確認欄
    right_content = [
        [Paragraph("預り金出納帳の内容を確認しました。", s_sign_hd), ""],
        [Paragraph("確認年月日", s_footer),  ""],
        [Paragraph("管理者",     s_footer),  ""],
        [Paragraph("職員",       s_footer),  ""],
    ]
    confirm_table = Table(right_content, colWidths=[24 * mm, 56 * mm])
    confirm_table.setStyle(TableStyle([
        ("FONTNAME",  (0, 0), (-1, -1), font_name),
        ("FONTSIZE",  (0, 0), (-1, -1), 9),
        ("VALIGN",    (0, 0), (-1, -1), "BOTTOM"),
        # 確認欄の記入スペースに下線
        ("LINEBELOW", (1, 1), (1, 1), 0.5, colors.black),
        ("LINEBELOW", (1, 2), (1, 2), 0.5, colors.black),
        ("LINEBELOW", (1, 3), (1, 3), 0.5, colors.black),
        # 「預り金出納帳の内容を確認しました。」は2列結合
        ("SPAN",      (0, 0), (1, 0)),
        ("ROWHEIGHT", (0, 0), (-1, -1), 8 * mm),
    ]))

    footer_data = [[
        Paragraph(left_text, s_footer),
        confirm_table,
    ]]
    footer_table = Table(footer_data, colWidths=[90 * mm, 90 * mm])
    footer_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("VALIGN",   (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(footer_table)

    # PDFを生成して保存
    doc.build(elements)
    return filepath


# =============================================================================
# 通院費ポーチ残高設定ダイアログ
# =============================================================================

class MedicalReserveDialog(tk.Toplevel):
    """
    通院費ポーチの残高を設定するダイアログ。
    金庫内に別保管している通院費用の現在額を登録する。

    result には設定後の金額（int）が入る。キャンセル時は None。
    """

    def __init__(self, parent, resident_name, current_amount):
        super().__init__(parent)
        self.title(f"通院費ポーチ残高の設定 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        self.result = None  # 設定した金額（int）。キャンセル時は None

        self._amount_var = tk.StringVar(value=str(current_amount))
        self._build_ui(resident_name, current_amount)
        self._center()

    def _center(self):
        self.update_idletasks()
        px = self.master.winfo_x() + self.master.winfo_width()  // 2
        py = self.master.winfo_y() + self.master.winfo_height() // 2
        self.geometry(f"+{px - 180}+{py - 100}")

    def _build_ui(self, resident_name, current_amount):
        frame = tk.Frame(self, padx=24, pady=20)
        frame.pack()

        tk.Label(frame, text="通院費ポーチ残高の設定", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=3, pady=(0, 10))

        # 説明文
        note = (
            "金庫内で別保管している通院費用の現在額を入力してください。\n"
            "PDF報告書では預かり金と合算して「お預かり合計」に表示されます。\n"
            "使用しない場合は 0 のまま保存してください。"
        )
        tk.Label(frame, text=note, font=FONT_SMALL, fg="#555555",
                 justify="left").grid(row=1, column=0, columnspan=3, pady=(0, 14), sticky="w")

        # 金額入力
        tk.Label(frame, text="現在残高：", font=FONT).grid(row=2, column=0, sticky="e", pady=6)
        amount_frame = tk.Frame(frame)
        amount_frame.grid(row=2, column=1, sticky="w", pady=6)
        self._entry = tk.Entry(amount_frame, textvariable=self._amount_var,
                               font=FONT, width=12, bg="#FFF8E1")
        self._entry.pack(side="left")
        tk.Label(amount_frame, text="円", font=FONT).pack(side="left", padx=(6, 0))

        # ボタン
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=(18, 0))
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg="#795548", fg="white", relief="flat", cursor="hand2",
                  padx=14, pady=6, command=self._on_ok).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2", padx=14, pady=6,
                  command=self.destroy).pack(side="left")

        # 入力欄を全選択状態にしてすぐ入力できるようにする
        self._entry.select_range(0, "end")
        self._entry.focus_set()

    def _on_ok(self):
        try:
            amount = int(self._amount_var.get().strip())
            if amount < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "入力エラー", "0以上の整数で入力してください。\n使用しない場合は 0 を入力してください。",
                parent=self)
            return
        self.result = amount
        self.destroy()


# =============================================================================
# 月選択ダイアログ
# =============================================================================

class MonthSelectDialog(tk.Toplevel):
    """PDF出力する対象月を選択するダイアログ"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("PDF出力 — 対象月の選択")
        self.resizable(False, False)
        self.grab_set()  # 他のウィンドウを操作できないようにモーダル化

        self.result = None  # (year, month) のタプル。キャンセル時は None

        today = date.today()
        # デフォルトは先月（1月の場合は前年12月）
        if today.month == 1:
            prev_year, prev_month = today.year - 1, 12
        else:
            prev_year, prev_month = today.year, today.month - 1
        self._year_var  = tk.IntVar(value=prev_year)
        self._month_var = tk.IntVar(value=prev_month)

        self._build_ui()
        self._center()

    def _center(self):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        px = self.master.winfo_x() + self.master.winfo_width()  // 2
        py = self.master.winfo_y() + self.master.winfo_height() // 2
        self.geometry(f"+{px - 160}+{py - 80}")

    def _build_ui(self):
        frame = tk.Frame(self, padx=24, pady=20)
        frame.pack()

        tk.Label(frame, text="対象年月を選択してください", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=4, pady=(0, 14))

        # 年
        tk.Label(frame, text="年：", font=FONT).grid(row=1, column=0, sticky="e")
        tk.Spinbox(frame, from_=2020, to=2099, textvariable=self._year_var,
                   width=6, font=FONT).grid(row=1, column=1, padx=(2, 10))

        # 月
        tk.Label(frame, text="月：", font=FONT).grid(row=1, column=2, sticky="e")
        tk.Spinbox(frame, from_=1, to=12, textvariable=self._month_var,
                   width=4, font=FONT).grid(row=1, column=3, padx=(2, 0))

        # ボタン
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=4, pady=(18, 0))
        tk.Button(btn_frame, text="PDF出力", font=FONT_BOLD,
                  bg="#2E7D32", fg="white", relief="flat", cursor="hand2",
                  padx=14, pady=6, command=self._on_ok).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2", padx=14, pady=6,
                  command=self.destroy).pack(side="left")

    def _on_ok(self):
        self.result = (self._year_var.get(), self._month_var.get())
        self.destroy()


# =============================================================================
# カレンダーポップアップ
# =============================================================================

class CalendarPopup(tk.Toplevel):
    """
    日付をカレンダーUIで選択するポップアップ。
    tkcalendar がインストールされている場合にのみ使用する。

    result には選択した日付が "YYYY-MM-DD" 形式で入る。
    キャンセルした場合は None のまま。
    """

    def __init__(self, parent, initial_date_str):
        super().__init__(parent)
        self.title("日付を選択")
        self.resizable(False, False)
        self.grab_set()

        self.result = None  # "YYYY-MM-DD" 文字列。キャンセル時は None

        # 初期表示する日付を解析する（失敗したら今日）
        try:
            init_date = datetime.strptime(initial_date_str, "%Y-%m-%d").date()
        except ValueError:
            init_date = date.today()

        self._build_ui(init_date)
        self._center()

    def _center(self):
        """ポップアップを親ウィンドウの中央付近に配置する"""
        self.update_idletasks()
        px = self.master.winfo_x() + self.master.winfo_width()  // 2
        py = self.master.winfo_y() + self.master.winfo_height() // 2
        self.geometry(f"+{px - 140}+{py - 120}")

    def _build_ui(self, init_date):
        frame = tk.Frame(self, padx=12, pady=12)
        frame.pack()

        # カレンダーウィジェット（tkcalendar）
        # date_pattern="yyyy-mm-dd" で get_date() が "YYYY-MM-DD" を返すよう設定
        self._cal = TkCalendar(
            frame,
            selectmode="day",
            year=init_date.year,
            month=init_date.month,
            day=init_date.day,
            date_pattern="yyyy-mm-dd",
            font=FONT_SMALL,
            locale="ja_JP",  # 月・曜日を日本語表示にする
        )
        self._cal.pack()

        # ボタン
        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=(10, 0))
        tk.Button(btn_frame, text="選択", font=FONT_BOLD,
                  bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                  padx=14, pady=5, command=self._on_ok).pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2", padx=14, pady=5,
                  command=self.destroy).pack(side="left")

    def _on_ok(self):
        self.result = self._cal.get_date()  # "YYYY-MM-DD" 形式で返る
        self.destroy()


# =============================================================================
# 収支記録ダイアログ（新規記録・修正 兼用）
# =============================================================================

class TransactionDialog(tk.Toplevel):
    """
    入金・出金を記録・修正するダイアログ。

    Args:
        parent        (tk.Tk):  親ウィンドウ
        resident_name (str):    利用者名（タイトルに表示）
        edit_data     (dict):   修正時に渡す既存データ。
                                None のとき「新規記録」モード。
                                修正時は {"id": int, "date": str,
                                          "description": str,
                                          "income": int, "expense": int} を渡す。
    """

    def __init__(self, parent, resident_name, edit_data=None, save_callback=None):
        """
        Args:
            edit_data     (dict): 修正時に渡す既存データ。None のとき新規記録モード。
            save_callback (func): 新規記録モードで「記録する」を押したときに呼ばれる関数。
                                  result dict を引数として受け取る。
        """
        super().__init__(parent)

        # 新規 or 修正の判定
        self._is_edit       = edit_data is not None
        self._save_callback = save_callback

        self.title(f"収支を修正 — {resident_name}" if self._is_edit else f"収支を記録 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        # 修正モードで使う：呼び出し元が参照する結果。キャンセル時は None
        self.result = None

        # 初期値：修正時は既存データ、新規時は今日の日付・空欄
        if self._is_edit:
            default_date    = edit_data["date"]
            default_desc    = edit_data["description"]
            default_income  = edit_data["income"]  if edit_data["income"]  > 0 else 0
            default_expense = edit_data["expense"] if edit_data["expense"] > 0 else 0
        else:
            default_date    = date.today().strftime("%Y-%m-%d")
            default_desc    = ""
            default_income  = 0
            default_expense = 0

        self._date_var        = tk.StringVar(value=default_date)
        self._description_var = tk.StringVar(value=default_desc)
        self._default_income  = default_income
        self._default_expense = default_expense

        self._build_ui(self._is_edit)
        self._center()

        # Enter キーで「記録する」「修正する」を実行する
        self.bind("<Return>", lambda e: self._on_ok())

    def _center(self):
        self.update_idletasks()
        px = self.master.winfo_x() + self.master.winfo_width()  // 2
        py = self.master.winfo_y() + self.master.winfo_height() // 2
        self.geometry(f"+{px - 200}+{py - 140}")

    def _build_ui(self, is_edit):
        frame = tk.Frame(self, padx=24, pady=20)
        frame.pack()

        # タイトルラベル
        title_text = "収支の修正" if is_edit else "収支の記録"
        tk.Label(frame, text=title_text, font=FONT_TITLE).grid(
            row=0, column=0, columnspan=3, pady=(0, 14))

        # 日付入力（テキスト入力 ＋ カレンダーボタン）
        tk.Label(frame, text="日付：", font=FONT).grid(row=1, column=0, sticky="e", pady=6)
        date_frame = tk.Frame(frame)
        date_frame.grid(row=1, column=1, sticky="w", pady=6)
        tk.Entry(date_frame, textvariable=self._date_var, font=FONT, width=13).pack(side="left")

        # tkcalendar がインストールされている場合のみカレンダーボタンを表示
        if TKCALENDAR_OK:
            tk.Button(date_frame, text="📅", font=FONT,
                      relief="flat", cursor="hand2", padx=4,
                      command=self._open_calendar).pack(side="left", padx=(4, 0))

        tk.Label(frame, text="例：2025-04-15", font=FONT_SMALL, fg="#888").grid(
            row=1, column=2, sticky="w", padx=(8, 0))

        # 摘要入力（後でフォーカスを戻すために参照を保存する）
        tk.Label(frame, text="摘要：", font=FONT).grid(row=2, column=0, sticky="e", pady=6)
        self._desc_entry = tk.Entry(frame, textvariable=self._description_var, font=FONT, width=24)
        self._desc_entry.grid(row=2, column=1, sticky="w", pady=6)
        tk.Label(frame, text="例：お小遣い精算", font=FONT_SMALL, fg="#888").grid(
            row=2, column=2, sticky="w", padx=(8, 0))

        # 入金額入力（薄緑）
        tk.Label(frame, text="入金額：", font=FONT).grid(row=3, column=0, sticky="e", pady=6)
        income_frame = tk.Frame(frame)
        income_frame.grid(row=3, column=1, sticky="w", pady=6)
        self._income_entry = tk.Entry(income_frame, font=FONT, width=12, bg="#E8F4E8")
        self._income_entry.pack(side="left")
        tk.Label(income_frame, text="円", font=FONT).pack(side="left", padx=(6, 0))
        tk.Label(frame, text="なければ 0", font=FONT_SMALL, fg="#888").grid(
            row=3, column=2, sticky="w", padx=(8, 0))

        # 出金額入力（薄赤）
        tk.Label(frame, text="出金額：", font=FONT).grid(row=4, column=0, sticky="e", pady=6)
        expense_frame = tk.Frame(frame)
        expense_frame.grid(row=4, column=1, sticky="w", pady=6)
        self._expense_entry = tk.Entry(expense_frame, font=FONT, width=12, bg="#FFF0F0")
        self._expense_entry.pack(side="left")
        tk.Label(expense_frame, text="円", font=FONT).pack(side="left", padx=(6, 0))
        tk.Label(frame, text="なければ 0", font=FONT_SMALL, fg="#888").grid(
            row=4, column=2, sticky="w", padx=(8, 0))

        # 修正時 or 初期値がある場合はセット（0 は空欄にして見やすくする）
        if self._default_income > 0:
            self._income_entry.insert(0, str(self._default_income))
        if self._default_expense > 0:
            self._expense_entry.insert(0, str(self._default_expense))

        # 記録完了フィードバックラベル（新規モード専用。記録後に「✓ 記録しました」と表示）
        self._feedback_label = tk.Label(frame, text="", font=FONT_BOLD,
                                        fg="#1B5E20", bg=frame["bg"])
        self._feedback_label.grid(row=5, column=0, columnspan=3, pady=(8, 0))

        # ボタン行
        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=3, pady=(10, 0))

        if is_edit:
            # 修正モード：「修正する」と「キャンセル」
            tk.Button(btn_frame, text="修正する（Enter）", font=FONT_BOLD,
                      bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                      padx=14, pady=6, command=self._on_ok).pack(side="left", padx=(0, 8))
            tk.Button(btn_frame, text="キャンセル", font=FONT,
                      relief="flat", cursor="hand2", padx=14, pady=6,
                      command=self.destroy).pack(side="left")
        else:
            # 新規記録モード：「記録する」で保存してリセット、「閉じる」で終了
            tk.Button(btn_frame, text="記録する（Enter）", font=FONT_BOLD,
                      bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                      padx=14, pady=6, command=self._on_ok).pack(side="left", padx=(0, 8))
            tk.Button(btn_frame, text="閉じる", font=FONT,
                      relief="flat", cursor="hand2", padx=14, pady=6,
                      command=self.destroy).pack(side="left")

    def _open_calendar(self):
        """カレンダーポップアップを開き、選択日を日付欄に反映する"""
        popup = CalendarPopup(self, self._date_var.get())
        self.wait_window(popup)
        if popup.result:
            self._date_var.set(popup.result)

    def _parse_amount(self, entry):
        """
        金額入力欄の文字列を整数に変換して返す。
        空欄または 0 は 0 として扱う。
        不正な値の場合は None を返す。
        """
        text = entry.get().strip()
        if text == "" or text == "0":
            return 0
        try:
            value = int(text)
            if value < 0:
                return None
            return value
        except ValueError:
            return None

    def _reset_fields(self):
        """記録後にフィールドをリセットして次の入力を受け付ける"""
        self._date_var.set(date.today().strftime("%Y-%m-%d"))
        self._description_var.set("")
        self._income_entry.delete(0, "end")
        self._expense_entry.delete(0, "end")
        # 摘要欄にフォーカスを移して Tab → Tab → Enter の流れで入力できるようにする
        self._desc_entry.focus_set()

    def _show_feedback(self):
        """「✓ 記録しました」を2秒間表示する"""
        self._feedback_label.configure(text="✓ 記録しました")
        self.after(2000, lambda: self._feedback_label.configure(text=""))

    def _on_ok(self):
        """入力内容を検証し、保存する。新規モードはリセットして連続入力を続ける。"""
        # 日付の検証
        date_str = self._date_var.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror(
                "入力エラー", "日付は YYYY-MM-DD 形式で入力してください。\n例：2025-04-15", parent=self)
            return

        # 摘要の検証
        description = self._description_var.get().strip()
        if not description:
            messagebox.showerror("入力エラー", "摘要を入力してください。", parent=self)
            return

        # 入金額・出金額の検証
        income  = self._parse_amount(self._income_entry)
        expense = self._parse_amount(self._expense_entry)

        if income is None or expense is None:
            messagebox.showerror(
                "入力エラー", "金額は 0 以上の整数で入力してください。\n使わない場合は 0 または空欄にしてください。",
                parent=self)
            return

        # 入金・出金どちらも 0 はエラー
        if income == 0 and expense == 0:
            messagebox.showerror(
                "入力エラー", "入金額と出金額の少なくとも一方を入力してください。", parent=self)
            return

        result = {"date": date_str, "description": description,
                  "income": income, "expense": expense}

        if self._is_edit:
            # 修正モード：結果をセットしてダイアログを閉じる
            self.result = result
            self.destroy()
        else:
            # 新規記録モード：コールバックで保存 → フィールドリセット → 連続入力へ
            if self._save_callback:
                self._save_callback(result)
            self._reset_fields()
            self._show_feedback()


# =============================================================================
# メインアプリクラス
# =============================================================================

class DepositApp(tk.Tk):
    """預かり金管理アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("預かり金管理")
        self.geometry("960x620")
        self.minsize(720, 480)
        self.configure(bg="#F5F7FA")

        # 現在選択中の利用者情報
        self._selected_resident_id   = None
        self._selected_resident_name = None
        self._resident_ids           = []  # リストボックスの表示順に対応するIDリスト
        self._medical_reserve        = 0   # 通院費ポーチ残高（現在選択中の利用者分）

        # 金銭チェックタブ用
        self._denom_vars        = {}   # {金額: StringVar} 金庫の枚数入力
        self._subtotal_labels   = {}   # {金額: Label}     小計ラベル
        self._check_deposit_total = None  # 利用者別残高合計（読み込み後にセット）
        self._safe_total          = 0     # 金庫合計

        # 計算機タブ用
        self._calc_resident_names = []  # 利用者名リスト（コンボボックスの選択肢）
        self._session_entries     = []  # 今回のセッションで入力した収支（計算機タブ用）

        self._build_ui()
        self.load_residents()

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def _build_ui(self):
        """メインUIを構築する"""
        # タイトルバー
        title_frame = tk.Frame(self, bg="#4472C4", pady=8)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text="預かり金管理", font=FONT_TITLE,
                 bg="#4472C4", fg="white").pack()

        # タブ切り替えウィジェット
        self._notebook = ttk.Notebook(self)
        self._notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # タブ1：収支管理（既存レイアウト）
        tab1 = tk.Frame(self._notebook, bg="#F5F7FA")
        self._notebook.add(tab1, text="  収支管理  ")

        paned = tk.PanedWindow(tab1, orient="horizontal", sashwidth=4, bg="#CCCCCC")
        paned.pack(fill="both", expand=True)
        paned.add(self._build_left_panel(paned),  minsize=150)
        paned.add(self._build_right_panel(paned), minsize=400)

        # タブ2：金銭チェック
        tab2 = tk.Frame(self._notebook, bg="#F5F7FA")
        self._notebook.add(tab2, text="  💰 金銭チェック  ")
        self._build_cash_check_tab(tab2)

        # タブ3：立替清算計算機
        tab3 = tk.Frame(self._notebook, bg="#F5F7FA")
        self._notebook.add(tab3, text="  🧮 計算機  ")
        self._build_calculator_tab(tab3)

        # タブ切り替えのたびに金銭チェックを自動更新
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_left_panel(self, parent):
        """左パネル：利用者一覧を返す"""
        frame = tk.Frame(parent, bg="#F5F7FA", width=190)

        tk.Label(frame, text="利用者一覧", font=FONT_BOLD,
                 bg="#4472C4", fg="white", pady=6).pack(fill="x")

        listbox_frame = tk.Frame(frame, bg="#F5F7FA")
        listbox_frame.pack(fill="both", expand=True, pady=4)

        sb = tk.Scrollbar(listbox_frame)
        sb.pack(side="right", fill="y")

        self._resident_listbox = tk.Listbox(
            listbox_frame,
            font=FONT,
            selectbackground="#4472C4",
            selectforeground="white",
            activestyle="none",
            cursor="hand2",
            yscrollcommand=sb.set,
        )
        self._resident_listbox.pack(fill="both", expand=True)
        sb.config(command=self._resident_listbox.yview)
        self._resident_listbox.bind("<<ListboxSelect>>", self._on_resident_select)

        return frame

    def _build_right_panel(self, parent):
        """右パネル：収支一覧と操作ボタンを返す"""
        frame = tk.Frame(parent, bg="#F5F7FA")

        # 情報バー（2行：1行目=利用者名、2行目=各種残高）
        info_frame = tk.Frame(frame, bg="#E8EDF5", pady=8, padx=14)
        info_frame.pack(fill="x")

        # 1行目：利用者名
        self._name_label = tk.Label(
            info_frame, text="← 利用者を選択してください",
            font=FONT_TITLE, bg="#E8EDF5")
        self._name_label.pack(anchor="w")

        # 2行目：残高情報（預かり金 ／ 通院費ポーチ ／ 合計）
        balance_row = tk.Frame(info_frame, bg="#E8EDF5")
        balance_row.pack(fill="x", pady=(4, 0))

        # 預かり金残高（緑）
        self._balance_label = tk.Label(
            balance_row, text="", font=FONT_BOLD, bg="#E8EDF5", fg="#2E7D32")
        self._balance_label.pack(side="left")

        # 区切り
        tk.Label(balance_row, text="　｜　", font=FONT, bg="#E8EDF5",
                 fg="#AAAAAA").pack(side="left")

        # 通院費ポーチ残高（茶色）
        self._medical_label = tk.Label(
            balance_row, text="", font=FONT_BOLD, bg="#E8EDF5", fg="#795548")
        self._medical_label.pack(side="left")

        # 通院費ポーチ変更ボタン（利用者選択後に有効化）
        self._medical_btn = tk.Button(
            balance_row, text="変更", font=FONT_SMALL,
            bg="#795548", fg="white", relief="flat", cursor="hand2",
            padx=6, pady=1, state="disabled",
            command=self._edit_medical_reserve)
        self._medical_btn.pack(side="left", padx=(6, 0))

        # 区切り
        tk.Label(balance_row, text="　｜　", font=FONT, bg="#E8EDF5",
                 fg="#AAAAAA").pack(side="left")

        # お預かり合計（紺）
        self._total_label = tk.Label(
            balance_row, text="", font=FONT_BOLD, bg="#E8EDF5", fg="#1A237E")
        self._total_label.pack(side="left")

        # 収支一覧テーブル
        tree_frame = tk.Frame(frame, bg="#F5F7FA")
        tree_frame.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        columns = ("date", "description", "income", "expense", "balance")
        self._tree = ttk.Treeview(tree_frame, columns=columns,
                                  show="headings", selectmode="browse")

        col_conf = [
            ("date",        "日付",       80,  "center"),
            ("description", "摘要",       240, "w"),
            ("income",      "入金（円）", 95,  "e"),
            ("expense",     "出金（円）", 95,  "e"),
            ("balance",     "残高（円）", 105, "e"),
        ]
        for col, heading, width, anchor in col_conf:
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, anchor=anchor, minwidth=60)

        # Treeview のスタイル設定
        style = ttk.Style()
        style.configure("Treeview",         font=FONT,      rowheight=28)
        style.configure("Treeview.Heading", font=FONT_BOLD, background="#4472C4")
        self._tree.tag_configure("odd",     background=ROW_ODD)
        self._tree.tag_configure("even",    background=ROW_EVEN)
        self._tree.tag_configure("income",  foreground="#1B5E20")  # 入金行：緑字
        self._tree.tag_configure("expense", foreground="#B71C1C")  # 出金行：赤字

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)

        # ダブルクリックで修正ダイアログを開く
        self._tree.bind("<Double-1>", lambda e: self._edit_transaction())

        # 操作ボタン
        btn_frame = tk.Frame(frame, bg="#F5F7FA", pady=8)
        btn_frame.pack(fill="x", padx=8)

        tk.Button(btn_frame, text="＋ 収支を記録", font=FONT_BOLD,
                  bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self._add_transaction).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="修正", font=FONT,
                  bg="#F57C00", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self._edit_transaction).pack(side="left", padx=(0, 8))

        tk.Button(btn_frame, text="削除", font=FONT,
                  bg="#E53935", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self._delete_transaction).pack(side="left")

        # side="right" でpackすると右から順に並ぶため、
        # 左側に来る「一括PDF出力」を後でpackする
        tk.Button(btn_frame, text="PDF出力", font=FONT_BOLD,
                  bg="#2E7D32", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self._export_pdf).pack(side="right")

        tk.Button(btn_frame, text="一括PDF出力", font=FONT_BOLD,
                  bg="#1A237E", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self._export_all_pdf).pack(side="right", padx=(0, 8))

        return frame

    # ------------------------------------------------------------------
    # データ操作
    # ------------------------------------------------------------------

    def load_residents(self):
        """residents.db から入居中の利用者を読み込んでリストに表示する"""
        self._resident_listbox.delete(0, "end")
        self._resident_ids = []

        try:
            conn = sqlite3.connect(RESIDENTS_DB)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id")
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("DB読み込みエラー",
                                 f"利用者DBの読み込みに失敗しました。\n{e}")
            return

        names = []
        for row in rows:
            self._resident_listbox.insert("end", row["name"])
            self._resident_ids.append(row["id"])
            names.append(row["name"])

        # 計算機タブのコンボボックスを更新する
        self._calc_resident_names = names
        if hasattr(self, "_calc_resident_combo"):
            self._calc_resident_combo["values"] = ["（全員）"] + names
            if not self._calc_resident_combo.get():
                self._calc_resident_combo.set("（全員）")

    def _on_resident_select(self, event):
        """リストボックスで利用者を選択したときに収支一覧を更新する"""
        selection = self._resident_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        self._selected_resident_id   = self._resident_ids[idx]
        self._selected_resident_name = self._resident_listbox.get(idx)
        self._name_label.configure(text=f"{self._selected_resident_name}　様")
        self.load_transactions()

    def load_transactions(self):
        """選択中の利用者の収支一覧と通院費ポーチ残高を読み込んで表示する"""
        if self._selected_resident_id is None:
            return

        self._tree.delete(*self._tree.get_children())

        conn = sqlite3.connect(DEPOSIT_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 収支明細を取得
        cur.execute("""
            SELECT id, transaction_date, description, income, expense
            FROM deposit_transactions
            WHERE resident_id = ?
            ORDER BY transaction_date, id
        """, (self._selected_resident_id,))
        rows = cur.fetchall()

        # 通院費ポーチ残高を取得（登録がない場合は 0）
        cur.execute("""
            SELECT COALESCE(amount, 0) AS amount
            FROM medical_reserve
            WHERE resident_id = ?
        """, (self._selected_resident_id,))
        med_row = cur.fetchone()
        self._medical_reserve = med_row["amount"] if med_row else 0
        conn.close()

        # 古い順に残高を積み上げて各行の残高を確定する
        balance = 0
        display_rows = []
        for row in rows:
            balance += row["income"] - row["expense"]
            display_rows.append((row, balance))

        # 新しい順（逆順）で一覧に挿入する
        for i, (row, row_balance) in enumerate(reversed(display_rows)):
            # 偶数/奇数行の背景色タグ
            tags = ["even" if i % 2 == 0 else "odd"]
            # 入金・出金に応じて文字色タグを追加
            if row["income"] > 0:
                tags.append("income")
            elif row["expense"] > 0:
                tags.append("expense")

            self._tree.insert("", "end",
                iid=str(row["id"]),
                values=(
                    row["transaction_date"],
                    row["description"],
                    f"¥{row['income']:,}"  if row["income"]  > 0 else "—",
                    f"¥{row['expense']:,}" if row["expense"] > 0 else "—",
                    f"¥{row_balance:,}",
                ),
                tags=tuple(tags),
            )

        # 預かり金残高ラベルを更新（マイナスは赤字で警告）
        bal_color = "#B71C1C" if balance < 0 else "#2E7D32"
        self._balance_label.configure(
            text=f"預かり金残高：¥{balance:,}", fg=bal_color)

        # 通院費ポーチラベルを更新
        if self._medical_reserve > 0:
            self._medical_label.configure(
                text=f"通院費ポーチ（別保管）：¥{self._medical_reserve:,}")
        else:
            self._medical_label.configure(text="通院費ポーチ：未設定")

        # 通院費変更ボタンを有効化
        self._medical_btn.configure(state="normal")

        # お預かり合計ラベルを更新
        total = balance + self._medical_reserve
        total_color = "#B71C1C" if total < 0 else "#1A237E"
        self._total_label.configure(
            text=f"お預かり合計：¥{total:,}", fg=total_color)

    def _edit_medical_reserve(self):
        """通院費ポーチ残高設定ダイアログを開いてDBを更新する"""
        if self._selected_resident_id is None:
            return

        dlg = MedicalReserveDialog(self, self._selected_resident_name, self._medical_reserve)
        self.wait_window(dlg)

        if dlg.result is None:
            return  # キャンセルされた

        now = datetime.now().isoformat(timespec="seconds")
        conn = sqlite3.connect(DEPOSIT_DB)
        # INSERT OR REPLACE：既にレコードがあれば上書き、なければ新規作成する
        conn.execute("""
            INSERT INTO medical_reserve (resident_id, amount, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(resident_id) DO UPDATE SET
                amount     = excluded.amount,
                updated_at = excluded.updated_at
        """, (self._selected_resident_id, dlg.result, now))
        conn.commit()
        conn.close()

        # 画面上の残高表示を再読み込みして更新する
        self.load_transactions()

    def _add_transaction(self):
        """収支記録ダイアログを開く。記録のたびにDBへ保存してダイアログは開いたまま継続する。"""
        if self._selected_resident_id is None:
            messagebox.showwarning("確認", "左の一覧から利用者を選択してください。")
            return

        def save_cb(result):
            """ダイアログから呼ばれる保存コールバック"""
            now = datetime.now().isoformat(timespec="seconds")
            conn = sqlite3.connect(DEPOSIT_DB)
            conn.execute("""
                INSERT INTO deposit_transactions
                    (resident_id, transaction_date, description, income, expense, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                self._selected_resident_id,
                result["date"], result["description"],
                result["income"], result["expense"],
                now, now,
            ))
            conn.commit()
            conn.close()

            # 今回のセッションで入力した記録としてリストに追加する
            # （計算機タブの「今回入力した分」機能で使用）
            self._session_entries.append({
                "resident_name": self._selected_resident_name,
                "date":          result["date"],
                "description":   result["description"],
                "income":        result["income"],
                "expense":       result["expense"],
            })
            self._calc_update_session_label()
            self.load_transactions()

        TransactionDialog(self, self._selected_resident_name, save_callback=save_cb)

    def _edit_transaction(self):
        """選択中の取引行を修正ダイアログで開いてDBを更新する"""
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("確認", "修正する行を選択してください。")
            return

        row_id = int(selected[0])

        # DBから修正対象の現在値を取得する
        conn = sqlite3.connect(DEPOSIT_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT transaction_date, description, income, expense FROM deposit_transactions WHERE id = ?",
            (row_id,)
        )
        row = cur.fetchone()
        conn.close()

        if row is None:
            messagebox.showerror("エラー", "対象のデータが見つかりませんでした。")
            return

        # 既存データを edit_data として渡し、修正モードでダイアログを開く
        edit_data = {
            "id":          row_id,
            "date":        row["transaction_date"],
            "description": row["description"],
            "income":      row["income"],
            "expense":     row["expense"],
        }
        dlg = TransactionDialog(self, self._selected_resident_name, edit_data=edit_data)
        self.wait_window(dlg)

        if dlg.result is None:
            return  # キャンセルされた

        # DBを更新する（updated_at も更新）
        now = datetime.now().isoformat(timespec="seconds")
        conn = sqlite3.connect(DEPOSIT_DB)
        conn.execute("""
            UPDATE deposit_transactions
            SET transaction_date = ?, description = ?, income = ?, expense = ?, updated_at = ?
            WHERE id = ?
        """, (
            dlg.result["date"],
            dlg.result["description"],
            dlg.result["income"],
            dlg.result["expense"],
            now,
            row_id,
        ))
        conn.commit()
        conn.close()

        self.load_transactions()

    def _delete_transaction(self):
        """選択中の取引行をDBから削除する"""
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("確認", "削除する行を選択してください。")
            return

        values = self._tree.item(selected[0])["values"]
        confirm_msg = (
            f"以下の記録を削除します。よろしいですか？\n\n"
            f"日付：{values[0]}\n"
            f"摘要：{values[1]}\n"
            f"入金：{values[2]}　出金：{values[3]}"
        )
        if not messagebox.askyesno("削除の確認", confirm_msg):
            return

        row_id = int(selected[0])
        conn = sqlite3.connect(DEPOSIT_DB)
        conn.execute("DELETE FROM deposit_transactions WHERE id = ?", (row_id,))
        conn.commit()
        conn.close()

        self.load_transactions()

    def _export_pdf(self):
        """月選択ダイアログを開いて月次の預かり金明細PDFを生成する"""
        if self._selected_resident_id is None:
            messagebox.showwarning("確認", "左の一覧から利用者を選択してください。")
            return

        dlg = MonthSelectDialog(self)
        self.wait_window(dlg)

        if dlg.result is None:
            return  # キャンセルされた

        year, month = dlg.result

        conn = sqlite3.connect(DEPOSIT_DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 月初残高：対象月の前日までの入出金合計
        cur.execute("""
            SELECT COALESCE(SUM(income) - SUM(expense), 0) AS opening
            FROM deposit_transactions
            WHERE resident_id = ?
              AND transaction_date < ?
        """, (self._selected_resident_id, f"{year}-{month:02d}-01"))
        opening_balance = cur.fetchone()["opening"]

        # 対象月の取引一覧
        cur.execute("""
            SELECT transaction_date, description, income, expense
            FROM deposit_transactions
            WHERE resident_id = ?
              AND strftime('%Y', transaction_date) = ?
              AND strftime('%m', transaction_date) = ?
            ORDER BY transaction_date, id
        """, (self._selected_resident_id, str(year), f"{month:02d}"))
        transactions = cur.fetchall()
        conn.close()

        filepath = generate_pdf(
            self._selected_resident_name, year, month, transactions,
            opening_balance, self._medical_reserve)

        if filepath:
            if messagebox.askyesno("PDF出力完了",
                                   f"PDFを出力しました。\n\n{filepath}\n\nファイルを開きますか？"):
                os.startfile(filepath)

    def _export_all_pdf(self):
        """
        入居中の全利用者を対象に、指定月のPDFを一括出力する。
        月選択ダイアログで対象月を選び、OUTPUT_DIR にまとめて保存する。
        """
        dlg = MonthSelectDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return  # キャンセルされた

        year, month = dlg.result

        # 入居中の利用者を取得
        try:
            conn_r = sqlite3.connect(RESIDENTS_DB)
            conn_r.row_factory = sqlite3.Row
            residents = conn_r.execute(
                "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id"
            ).fetchall()
            conn_r.close()
        except Exception as e:
            messagebox.showerror("エラー", f"利用者DBの読み込みに失敗しました。\n{e}")
            return

        if not residents:
            messagebox.showinfo("確認", "入居中の利用者が見つかりませんでした。")
            return

        conn_d = sqlite3.connect(DEPOSIT_DB)
        conn_d.row_factory = sqlite3.Row

        success_count = 0
        failed_names  = []

        for resident in residents:
            rid  = resident["id"]
            name = resident["name"]
            try:
                # 月初残高：対象月の前日までの累計
                opening = conn_d.execute("""
                    SELECT COALESCE(SUM(income) - SUM(expense), 0) AS opening
                    FROM deposit_transactions
                    WHERE resident_id = ? AND transaction_date < ?
                """, (rid, f"{year}-{month:02d}-01")).fetchone()["opening"]

                # 対象月の取引一覧
                txns = conn_d.execute("""
                    SELECT transaction_date, description, income, expense
                    FROM deposit_transactions
                    WHERE resident_id = ?
                      AND strftime('%Y', transaction_date) = ?
                      AND strftime('%m', transaction_date) = ?
                    ORDER BY transaction_date, id
                """, (rid, str(year), f"{month:02d}")).fetchall()

                # 通院費ポーチ残高
                med_row = conn_d.execute(
                    "SELECT COALESCE(amount, 0) AS amount FROM medical_reserve WHERE resident_id = ?",
                    (rid,)
                ).fetchone()
                medical = med_row["amount"] if med_row else 0

                fp = generate_pdf(name, year, month, txns, opening, medical)
                if fp:
                    success_count += 1
                else:
                    failed_names.append(name)
            except Exception as e:
                failed_names.append(f"{name}（{e}）")

        conn_d.close()

        # 結果メッセージ
        msg = (f"{year}年{month:02d}月分のPDFを {success_count} 件出力しました。\n\n"
               f"出力先：{OUTPUT_DIR}")
        if failed_names:
            msg += f"\n\n出力できなかった利用者：\n" + "\n".join(failed_names)

        if messagebox.askyesno("一括PDF出力完了", msg + "\n\n出力フォルダを開きますか？"):
            os.startfile(OUTPUT_DIR)

    # ------------------------------------------------------------------
    # 金銭チェックタブ
    # ------------------------------------------------------------------

    # 金庫に入れる紙幣・硬貨の一覧（単位：円）
    _DENOMINATIONS = [
        (10000, "紙幣"), (5000, "紙幣"), (2000, "紙幣"), (1000, "紙幣"),
        (500,   "硬貨"), (100,  "硬貨"), (50,   "硬貨"),
        (10,    "硬貨"), (5,    "硬貨"), (1,    "硬貨"),
    ]

    def _build_cash_check_tab(self, parent):
        """
        金銭チェックタブを構築する。
        全利用者の預かり金残高合計と金庫の現金を比較して過不足を確認する。
        """
        # --- 上部：タイトル＋再読み込みボタン ---
        top = tk.Frame(parent, bg="#F5F7FA", pady=6, padx=12)
        top.pack(fill="x")

        tk.Label(top, text="金銭チェック　― 預かり金と金庫の照合",
                 font=FONT_BOLD, bg="#F5F7FA").pack(side="left")
        tk.Button(top, text="再読み込み", font=FONT,
                  bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                  padx=10, pady=3,
                  command=self._load_cash_check_balances).pack(side="right")

        # --- 中部：左（利用者残高一覧）＋ 右（金庫カウンター） ---
        mid = tk.Frame(parent, bg="#F5F7FA")
        mid.pack(fill="both", expand=True, padx=12, pady=(4, 6))
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=4)
        mid.rowconfigure(0, weight=1)

        self._build_balance_list(mid)    # 左パネル
        self._build_safe_counter(mid)    # 右パネル

        # --- 下部：照合結果バー（ラベル左・記録ボタン右） ---
        self._result_bar = tk.Frame(parent, bg="#E8EDF5", pady=8, padx=16)
        self._result_bar.pack(fill="x", padx=12, pady=(0, 6))

        self._check_result_label = tk.Label(
            self._result_bar,
            text="「再読み込み」を押して利用者残高を取得してください。",
            font=FONT_BOLD, bg="#E8EDF5", fg="#777777")
        self._check_result_label.pack(side="left", fill="x", expand=True)

        # 一致したときだけ表示する記録ボタン（初期は非表示）
        self._record_btn = tk.Button(
            self._result_bar, text="✓ この状態を記録する", font=FONT_BOLD,
            bg="#2E7D32", fg="white", relief="flat", cursor="hand2",
            padx=14, pady=4,
            command=self._save_cash_check_log)
        # pack は _update_check_result が必要に応じて呼ぶ

        # --- 過去のチェック履歴 ---
        log_outer = tk.LabelFrame(parent, text="  チェック履歴  ",
                                  font=FONT_BOLD, bg="#F5F7FA", padx=8, pady=6)
        log_outer.pack(fill="x", padx=12, pady=(0, 10))

        log_cols = ("checked_at", "deposit_total", "detail")
        self._log_tree = ttk.Treeview(log_outer, columns=log_cols,
                                      show="headings", height=5,
                                      selectmode="none")
        self._log_tree.heading("checked_at",    text="記録日時")
        self._log_tree.heading("deposit_total", text="預かり金合計")
        self._log_tree.heading("detail",        text="内訳（枚数）")
        self._log_tree.column("checked_at",    width=148, anchor="center", minwidth=100)
        self._log_tree.column("deposit_total", width=115, anchor="center", minwidth=80)
        self._log_tree.column("detail",        width=400, anchor="w",      minwidth=100)
        self._log_tree.tag_configure("odd",  background=ROW_ODD)
        self._log_tree.tag_configure("even", background=ROW_EVEN)

        log_vsb = ttk.Scrollbar(log_outer, orient="vertical",
                                 command=self._log_tree.yview)
        self._log_tree.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side="right", fill="y")
        self._log_tree.pack(fill="x")

    def _build_balance_list(self, parent):
        """
        左パネル：利用者別 預かり金残高の一覧テーブルを構築する。
        通院費ポーチは別管理なので含めない。
        """
        frame = tk.LabelFrame(
            parent,
            text="  利用者別 預かり金残高（通院費ポーチ除く）  ",
            font=FONT_BOLD, bg="#F5F7FA", padx=8, pady=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        # Treeview（一覧テーブル）
        tree_wrap = tk.Frame(frame, bg="#F5F7FA")
        tree_wrap.pack(fill="both", expand=True)

        self._check_tree = ttk.Treeview(
            tree_wrap, columns=("name", "balance"),
            show="headings", selectmode="none")
        self._check_tree.heading("name",    text="利用者名")
        self._check_tree.heading("balance", text="預かり金残高")
        self._check_tree.column("name",    width=130, anchor="w",  minwidth=80)
        self._check_tree.column("balance", width=130, anchor="e",  minwidth=80)

        style = ttk.Style()
        style.configure("Treeview",         font=FONT,      rowheight=28)
        style.configure("Treeview.Heading", font=FONT_BOLD)

        self._check_tree.tag_configure("odd",      background=ROW_ODD)
        self._check_tree.tag_configure("even",     background=ROW_EVEN)
        self._check_tree.tag_configure("negative", foreground="#B71C1C")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical",
                             command=self._check_tree.yview)
        self._check_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._check_tree.pack(fill="both", expand=True)

        # 合計ラベル
        self._check_deposit_total_label = tk.Label(
            frame, text="預かり金合計：（未読込）",
            font=FONT_BOLD, bg="#D9E1F2", fg="#1A237E",
            anchor="e", padx=8, pady=5)
        self._check_deposit_total_label.pack(fill="x", pady=(8, 0))

    def _build_safe_counter(self, parent):
        """
        右パネル：金庫の現金カウンター（紙幣・硬貨の枚数入力）を構築する。
        枚数を入力すると即座に小計・合計が更新される。
        """
        frame = tk.LabelFrame(
            parent, text="  金庫　現金カウンター  ",
            font=FONT_BOLD, bg="#F5F7FA", padx=14, pady=10)
        frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        # 紙幣・硬貨の入力欄を並べる
        row_idx = 0
        prev_kind = None

        for denom, kind in self._DENOMINATIONS:
            # 種別が切り替わるタイミングで「紙幣」「硬貨」ヘッダーを挿入
            if kind != prev_kind:
                color = "#1A237E" if kind == "紙幣" else "#4E342E"
                tk.Label(frame, text=kind, font=FONT_BOLD,
                         bg="#F5F7FA", fg=color).grid(
                    row=row_idx, column=0, columnspan=6,
                    sticky="w", pady=(8 if row_idx > 0 else 0, 2))
                row_idx += 1
                prev_kind = kind

            # 枚数入力用変数（初期値 0）
            var = tk.StringVar(value="0")
            self._denom_vars[denom] = var

            # 金額ラベル（右寄せ）
            tk.Label(frame, text=f"{denom:,}円",
                     font=FONT, bg="#F5F7FA", anchor="e", width=9).grid(
                row=row_idx, column=0, sticky="e", padx=(0, 4), pady=1)

            # ×
            tk.Label(frame, text="×", font=FONT, bg="#F5F7FA").grid(
                row=row_idx, column=1, padx=2, pady=1)

            # 枚数入力欄
            ent = tk.Entry(frame, textvariable=var, font=FONT,
                           width=5, bg="#FFFDE7", justify="right")
            ent.grid(row=row_idx, column=2, padx=4, pady=1)
            ent.bind("<KeyRelease>", self._on_denom_changed)
            ent.bind("<FocusOut>",   self._on_denom_changed)

            # 枚
            tk.Label(frame, text="枚", font=FONT, bg="#F5F7FA").grid(
                row=row_idx, column=3, sticky="w", padx=(0, 8), pady=1)

            # ＝
            tk.Label(frame, text="＝", font=FONT, bg="#F5F7FA").grid(
                row=row_idx, column=4, padx=2, pady=1)

            # 小計ラベル（計算結果を表示）
            sub_lbl = tk.Label(frame, text="¥0",
                               font=FONT, bg="#F5F7FA", fg="#555555",
                               anchor="e", width=12)
            sub_lbl.grid(row=row_idx, column=5, sticky="e", pady=1)
            self._subtotal_labels[denom] = sub_lbl

            row_idx += 1

        # 区切り線
        sep = tk.Frame(frame, bg="#AAAAAA", height=1)
        sep.grid(row=row_idx, column=0, columnspan=6, sticky="ew", pady=(10, 6))
        row_idx += 1

        # 金庫合計ラベル
        self._safe_total_label = tk.Label(
            frame, text="金庫合計：¥0",
            font=FONT_BOLD, bg="#D9E1F2", fg="#1A237E",
            anchor="e", padx=8, pady=5)
        self._safe_total_label.grid(
            row=row_idx, column=0, columnspan=6, sticky="ew", pady=(0, 2))

    def _load_cash_check_balances(self):
        """
        全利用者（入居中）の預かり金残高を合計して一覧に表示する。
        通院費ポーチ（medical_reserve）は含めない。
        """
        self._check_tree.delete(*self._check_tree.get_children())

        # residents.db から入居中の利用者を取得
        try:
            conn_r = sqlite3.connect(RESIDENTS_DB)
            conn_r.row_factory = sqlite3.Row
            residents = conn_r.execute(
                "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id"
            ).fetchall()
            conn_r.close()
        except Exception as e:
            messagebox.showerror("読み込みエラー",
                                 f"利用者DBの読み込みに失敗しました。\n{e}")
            return

        # deposit.db から全利用者の残高を一括取得（通院費ポーチは除く）
        try:
            conn_d = sqlite3.connect(DEPOSIT_DB)
            conn_d.row_factory = sqlite3.Row
            balance_rows = conn_d.execute("""
                SELECT resident_id,
                       COALESCE(SUM(income) - SUM(expense), 0) AS balance
                FROM deposit_transactions
                GROUP BY resident_id
            """).fetchall()
            conn_d.close()
        except Exception as e:
            messagebox.showerror("読み込みエラー",
                                 f"預かり金DBの読み込みに失敗しました。\n{e}")
            return

        # resident_id をキーにした残高マップを作成
        balance_map = {r["resident_id"]: r["balance"] for r in balance_rows}

        grand_total = 0
        for i, r in enumerate(residents):
            bal = balance_map.get(r["id"], 0)
            grand_total += bal
            tags = ("even" if i % 2 == 0 else "odd",)
            if bal < 0:
                tags = tags + ("negative",)
            self._check_tree.insert("", "end",
                                    values=(r["name"], f"¥{bal:,}"),
                                    tags=tags)

        # 合計を保存してラベルに反映
        self._check_deposit_total = grand_total
        color = "#B71C1C" if grand_total < 0 else "#1A237E"
        self._check_deposit_total_label.configure(
            text=f"預かり金合計：¥{grand_total:,}", fg=color)

        self._update_check_result()
        self._load_cash_check_log()

    def _on_denom_changed(self, event=None):
        """
        金庫の枚数入力が変わるたびに各小計と金庫合計を再計算する。
        不正な値（空欄・マイナス・文字）は 0 として扱う。
        """
        safe_total = 0
        for denom, var in self._denom_vars.items():
            try:
                count = max(0, int(var.get().strip() or "0"))
            except ValueError:
                count = 0
            subtotal = denom * count
            safe_total += subtotal

            # 小計ラベルを更新（0 のときはグレー表示）
            lbl = self._subtotal_labels[denom]
            if subtotal > 0:
                lbl.configure(text=f"¥{subtotal:,}", fg="#1A237E")
            else:
                lbl.configure(text="¥0", fg="#AAAAAA")

        self._safe_total = safe_total
        self._safe_total_label.configure(text=f"金庫合計：¥{safe_total:,}")
        self._update_check_result()

    def _update_check_result(self):
        """
        預かり金合計と金庫合計を比較し、差額を結果バーに表示する。
        一致：緑（＋記録ボタン表示）　金庫過剰：オレンジ　金庫不足：赤
        """
        if self._check_deposit_total is None:
            # まだ残高を読み込んでいない
            self._result_bar.configure(bg="#E8EDF5")
            self._check_result_label.configure(
                text="「再読み込み」を押して利用者残高を取得してください。",
                bg="#E8EDF5", fg="#777777")
            self._record_btn.pack_forget()
            return

        deposit = self._check_deposit_total
        safe    = self._safe_total
        diff    = safe - deposit

        if diff == 0:
            msg = (f"✓ 一致しています　　"
                   f"預かり金合計：¥{deposit:,}　＝　金庫合計：¥{safe:,}")
            fg, bg = "#1B5E20", "#E8F5E9"
            # 一致しているときだけ記録ボタンを表示する
            self._record_btn.pack(side="right", padx=(12, 0))
        elif diff > 0:
            msg = (f"金庫が ¥{diff:,} 多い　　"
                   f"預かり金合計：¥{deposit:,}　　金庫合計：¥{safe:,}　　差額：＋¥{diff:,}")
            fg, bg = "#E65100", "#FFF3E0"
            self._record_btn.pack_forget()
        else:
            msg = (f"⚠ 金庫が ¥{abs(diff):,} 不足しています　　"
                   f"預かり金合計：¥{deposit:,}　　金庫合計：¥{safe:,}　　差額：▲¥{abs(diff):,}")
            fg, bg = "#B71C1C", "#FFEBEE"
            self._record_btn.pack_forget()

        self._result_bar.configure(bg=bg)
        self._check_result_label.configure(text=msg, fg=fg, bg=bg)

    def _save_cash_check_log(self):
        """
        一致した金銭チェックの結果をDBに保存する。
        記録日時・預かり金合計・金庫合計・各券種の枚数を記録する。
        """
        now = datetime.now().isoformat(timespec="seconds")

        # 各券種の枚数を辞書にまとめる（JSON として保存）
        denoms = {}
        for denom, var in self._denom_vars.items():
            try:
                count = max(0, int(var.get().strip() or "0"))
            except ValueError:
                count = 0
            denoms[str(denom)] = count

        conn = sqlite3.connect(DEPOSIT_DB)
        conn.execute("""
            INSERT INTO cash_check_log
                (checked_at, deposit_total, safe_total, denominations, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (now, self._check_deposit_total, self._safe_total,
              json.dumps(denoms, ensure_ascii=False), now))
        conn.commit()
        conn.close()

        messagebox.showinfo(
            "記録完了",
            f"金銭チェックを記録しました。\n\n"
            f"記録日時：{now.replace('T', ' ')}\n"
            f"預かり金合計：¥{self._check_deposit_total:,}")

        self._load_cash_check_log()

    def _load_cash_check_log(self):
        """
        チェック履歴をDBから読み込み、ログ一覧に表示する（新しい順・最大50件）。
        内訳は枚数が 0 の券種を省いた簡略文字列で表示する。
        """
        self._log_tree.delete(*self._log_tree.get_children())

        try:
            conn = sqlite3.connect(DEPOSIT_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT checked_at, deposit_total, denominations
                FROM cash_check_log
                ORDER BY checked_at DESC
                LIMIT 50
            """).fetchall()
            conn.close()
        except Exception:
            return

        for i, row in enumerate(rows):
            # 内訳文字列を組み立てる（0枚の券種は省略する）
            try:
                denoms = json.loads(row["denominations"])
                parts  = []
                for denom_str in sorted(denoms.keys(), key=lambda x: -int(x)):
                    count = int(denoms[denom_str])
                    if count > 0:
                        parts.append(f"{int(denom_str):,}円×{count}")
                detail = "　".join(parts) if parts else "—"
            except Exception:
                detail = "—"

            tag = "even" if i % 2 == 0 else "odd"
            self._log_tree.insert("", "end",
                values=(
                    row["checked_at"].replace("T", " "),
                    f"¥{row['deposit_total']:,}",
                    detail,
                ),
                tags=(tag,))

    # ------------------------------------------------------------------
    # 計算機タブ
    # ------------------------------------------------------------------

    def _build_calculator_tab(self, parent):
        """
        立替清算計算機タブを構築する。
        金額を手入力で積み上げたり、DBから期間・利用者を絞り込んで読み込んで合計を出せる。
        """
        # --- 上部：タイトル ---
        top = tk.Frame(parent, bg="#F5F7FA", pady=6, padx=12)
        top.pack(fill="x")
        tk.Label(top, text="立替清算 計算機　― 金額を積み上げて合計を確認",
                 font=FONT_BOLD, bg="#F5F7FA").pack(side="left")

        # --- メイン：左（入力）＋ 右（一覧＋合計） ---
        main = tk.Frame(parent, bg="#F5F7FA")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # ── 左カラム：入力パネル ──────────────────────────────
        left = tk.Frame(main, bg="#F5F7FA")
        left.pack(side="left", fill="y", padx=(0, 8))

        # ── 今回入力した分セクション ──────────────────────────
        session_frame = tk.LabelFrame(
            left, text="  今回入力した分  ",
            font=FONT_BOLD, bg="#FFF8E1", padx=12, pady=10)
        session_frame.pack(fill="x", pady=(0, 8))

        tk.Label(session_frame,
                 text="このアプリを起動してから記録した\n収支をまとめて読み込みます。\n日付や利用者がバラバラでも一覧になります。",
                 font=FONT_SMALL, bg="#FFF8E1", fg="#555555",
                 justify="left").pack(anchor="w", pady=(0, 6))

        self._session_count_label = tk.Label(
            session_frame, text="（まだ入力なし）",
            font=FONT_SMALL, bg="#FFF8E1", fg="#888888")
        self._session_count_label.pack(anchor="w", pady=(0, 6))

        tk.Button(session_frame, text="今回の出金分を読み込む", font=FONT_BOLD,
                  bg="#E65100", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self._calc_load_session).pack(fill="x")

        # 手入力セクション
        manual_frame = tk.LabelFrame(
            left, text="  手入力で追加  ",
            font=FONT_BOLD, bg="#F5F7FA", padx=12, pady=10)
        manual_frame.pack(fill="x", pady=(0, 8))

        tk.Label(manual_frame, text="メモ（任意）：", font=FONT, bg="#F5F7FA").grid(
            row=0, column=0, sticky="e", pady=5)
        self._calc_memo_var = tk.StringVar()
        tk.Entry(manual_frame, textvariable=self._calc_memo_var,
                 font=FONT, width=16).grid(row=0, column=1, sticky="w", pady=5)

        tk.Label(manual_frame, text="金額：", font=FONT, bg="#F5F7FA").grid(
            row=1, column=0, sticky="e", pady=5)
        amt_frm = tk.Frame(manual_frame, bg="#F5F7FA")
        amt_frm.grid(row=1, column=1, sticky="w", pady=5)
        self._calc_amount_var = tk.StringVar()
        self._calc_amount_entry = tk.Entry(
            amt_frm, textvariable=self._calc_amount_var,
            font=FONT, width=12, bg="#FFF8E1", justify="right")
        self._calc_amount_entry.pack(side="left")
        tk.Label(amt_frm, text="円", font=FONT, bg="#F5F7FA").pack(
            side="left", padx=(4, 0))

        tk.Button(manual_frame, text="＋ 追加（Enter）", font=FONT_BOLD,
                  bg="#4472C4", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self._calc_add_item).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # Enter キーで追加できるようにバインドする
        self._calc_amount_entry.bind("<Return>", lambda e: self._calc_add_item())

        # DB読み込みセクション
        db_frame = tk.LabelFrame(
            left, text="  DBから読み込む  ",
            font=FONT_BOLD, bg="#F5F7FA", padx=12, pady=10)
        db_frame.pack(fill="x", pady=(0, 8))

        tk.Label(db_frame, text="利用者：", font=FONT, bg="#F5F7FA").grid(
            row=0, column=0, sticky="e", pady=4)
        self._calc_resident_var = tk.StringVar(value="（全員）")
        self._calc_resident_combo = ttk.Combobox(
            db_frame, textvariable=self._calc_resident_var,
            font=FONT, width=14, state="readonly")
        self._calc_resident_combo["values"] = ["（全員）"] + self._calc_resident_names
        self._calc_resident_combo.set("（全員）")
        self._calc_resident_combo.grid(row=0, column=1, sticky="w", pady=4)

        tk.Label(db_frame, text="開始日：", font=FONT, bg="#F5F7FA").grid(
            row=1, column=0, sticky="e", pady=4)
        today = date.today()
        self._calc_from_var = tk.StringVar(
            value=f"{today.year}-{today.month:02d}-01")
        tk.Entry(db_frame, textvariable=self._calc_from_var,
                 font=FONT, width=12).grid(row=1, column=1, sticky="w", pady=4)

        tk.Label(db_frame, text="終了日：", font=FONT, bg="#F5F7FA").grid(
            row=2, column=0, sticky="e", pady=4)
        self._calc_to_var = tk.StringVar(value=today.strftime("%Y-%m-%d"))
        tk.Entry(db_frame, textvariable=self._calc_to_var,
                 font=FONT, width=12).grid(row=2, column=1, sticky="w", pady=4)

        tk.Label(db_frame, text="種別：", font=FONT, bg="#F5F7FA").grid(
            row=3, column=0, sticky="e", pady=4)
        self._calc_type_var = tk.StringVar(value="出金のみ")
        ttk.Combobox(db_frame, textvariable=self._calc_type_var,
                     values=["出金のみ", "入金のみ", "両方"],
                     font=FONT, width=10, state="readonly").grid(
            row=3, column=1, sticky="w", pady=4)

        tk.Button(db_frame, text="読み込む", font=FONT_BOLD,
                  bg="#795548", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self._calc_load_from_db).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # クリアボタン
        tk.Button(left, text="リストをすべてクリア", font=FONT,
                  bg="#E53935", fg="white", relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self._calc_clear).pack(fill="x")

        # ── 右カラム：一覧＋合計 ──────────────────────────────
        right = tk.Frame(main, bg="#F5F7FA")
        right.pack(side="left", fill="both", expand=True)

        list_frame = tk.LabelFrame(
            right, text="  追加した金額の一覧  ",
            font=FONT_BOLD, bg="#F5F7FA", padx=8, pady=8)
        list_frame.pack(fill="both", expand=True)

        cols = ("memo", "amount")
        self._calc_tree = ttk.Treeview(
            list_frame, columns=cols, show="headings", selectmode="browse")
        self._calc_tree.heading("memo",   text="メモ・内容")
        self._calc_tree.heading("amount", text="金額（円）")
        self._calc_tree.column("memo",   width=340, anchor="w", minwidth=100)
        self._calc_tree.column("amount", width=120, anchor="e", minwidth=80)
        self._calc_tree.tag_configure("odd",  background=ROW_ODD)
        self._calc_tree.tag_configure("even", background=ROW_EVEN)

        vsb = ttk.Scrollbar(list_frame, orient="vertical",
                             command=self._calc_tree.yview)
        self._calc_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._calc_tree.pack(fill="both", expand=True)

        tk.Button(list_frame, text="選択行を削除", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=8, pady=3,
                  command=self._calc_delete_item).pack(anchor="e", pady=(6, 0))

        # 件数・合計ラベル
        self._calc_count_label = tk.Label(
            right, text="0 件",
            font=FONT_SMALL, bg="#F5F7FA", fg="#888888",
            anchor="e", padx=8)
        self._calc_count_label.pack(fill="x", pady=(6, 0))

        self._calc_total_label = tk.Label(
            right, text="合　計：¥0",
            font=("MS Gothic", 16, "bold"), bg="#D9E1F2", fg="#1A237E",
            anchor="e", padx=20, pady=12)
        self._calc_total_label.pack(fill="x")

    def _calc_add_item(self):
        """手入力の金額をリストに追加する"""
        amount_str = self._calc_amount_var.get().strip()
        if not amount_str:
            messagebox.showwarning("入力エラー", "金額を入力してください。", parent=self)
            self._calc_amount_entry.focus_set()
            return
        try:
            amount = int(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "入力エラー", "金額は1以上の整数で入力してください。", parent=self)
            self._calc_amount_entry.focus_set()
            return

        memo = self._calc_memo_var.get().strip() or "（メモなし）"
        self._calc_insert_row(memo, amount)

        # 入力欄をリセットして連続入力できるようにする
        self._calc_amount_var.set("")
        self._calc_memo_var.set("")
        self._calc_amount_entry.focus_set()

    def _calc_insert_row(self, memo, amount):
        """リストに1行追加して合計を更新する"""
        count = len(self._calc_tree.get_children())
        tag = "even" if count % 2 == 0 else "odd"
        self._calc_tree.insert("", "end",
                                values=(memo, f"¥{amount:,}"),
                                tags=(tag,))
        self._calc_update_total()

    def _calc_update_total(self):
        """リスト内の金額をすべて合計してラベルに反映する"""
        total = 0
        count = 0
        for iid in self._calc_tree.get_children():
            val = self._calc_tree.item(iid, "values")[1]
            # "¥1,234" → 1234 に変換する
            try:
                total += int(val.replace("¥", "").replace(",", ""))
                count += 1
            except ValueError:
                pass
        color = "#B71C1C" if total < 0 else "#1A237E"
        self._calc_total_label.configure(text=f"合　計：¥{total:,}", fg=color)
        self._calc_count_label.configure(text=f"{count} 件")

    def _calc_delete_item(self):
        """選択中の行を削除して合計を更新する"""
        selected = self._calc_tree.selection()
        if not selected:
            return
        self._calc_tree.delete(selected[0])
        # 行を削除した後、偶数/奇数のストライプを振り直す
        for i, iid in enumerate(self._calc_tree.get_children()):
            tag = "even" if i % 2 == 0 else "odd"
            self._calc_tree.item(iid, tags=(tag,))
        self._calc_update_total()

    def _calc_clear(self):
        """リストをすべてクリアする"""
        if not self._calc_tree.get_children():
            return
        if messagebox.askyesno("確認", "リストをすべてクリアします。よろしいですか？",
                               parent=self):
            self._calc_tree.delete(*self._calc_tree.get_children())
            self._calc_update_total()

    def _calc_update_session_label(self):
        """今回入力した件数をセッションラベルに反映する"""
        if not hasattr(self, "_session_count_label"):
            return
        count = len(self._session_entries)
        if count == 0:
            self._session_count_label.configure(text="（まだ入力なし）", fg="#888888")
        else:
            # 出金・入金それぞれの件数を表示する
            expense_count = sum(1 for e in self._session_entries if e["expense"] > 0)
            income_count  = sum(1 for e in self._session_entries if e["income"]  > 0)
            parts = []
            if expense_count > 0:
                parts.append(f"出金 {expense_count} 件")
            if income_count > 0:
                parts.append(f"入金 {income_count} 件")
            self._session_count_label.configure(
                text=f"今回の入力：{' / '.join(parts)}（合計 {count} 件）",
                fg="#E65100")

    def _calc_load_session(self):
        """
        今回のセッションで入力した出金をまとめて計算機リストに追加する。
        日付や利用者がバラバラでもすべて一覧になる。
        """
        # 出金がある記録だけを対象にする
        targets = [e for e in self._session_entries if e["expense"] > 0]

        if not targets:
            messagebox.showinfo(
                "確認",
                "今回入力した出金がまだありません。\n\n"
                "収支管理タブで出金を記録してから、\nここで読み込んでください。",
                parent=self)
            return

        for entry in targets:
            memo = (f"[出金] {entry['resident_name']}　"
                    f"{entry['date']}　{entry['description']}")
            self._calc_insert_row(memo, entry["expense"])

        messagebox.showinfo(
            "読み込み完了",
            f"今回入力した出金 {len(targets)} 件を読み込みました。",
            parent=self)

    def _calc_load_from_db(self):
        """
        DBから出金・入金データを読み込んでリストに追加する。
        利用者・期間・種別でフィルタリングできる。既存のリストに追記される。
        """
        # 利用者名→IDのマッピングを residents.db から作る
        try:
            conn_r = sqlite3.connect(RESIDENTS_DB)
            conn_r.row_factory = sqlite3.Row
            all_residents = {r["id"]: r["name"] for r in conn_r.execute(
                "SELECT id, name FROM residents"
            ).fetchall()}
            conn_r.close()
        except Exception as e:
            messagebox.showerror("読み込みエラー",
                                 f"利用者DBの読み込みに失敗しました。\n{e}", parent=self)
            return

        # 利用者フィルタ：名前からIDを逆引きする
        resident_name = self._calc_resident_var.get()
        resident_id_filter = None
        if resident_name != "（全員）":
            for rid, rname in all_residents.items():
                if rname == resident_name:
                    resident_id_filter = rid
                    break

        # 日付フィルタ：空欄の場合は絞り込みなし
        from_date = self._calc_from_var.get().strip() or None
        to_date   = self._calc_to_var.get().strip()   or None
        for d in [from_date, to_date]:
            if d:
                try:
                    datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror(
                        "入力エラー",
                        f"日付の形式が正しくありません：{d}\n\n正しい形式の例：2026-04-01",
                        parent=self)
                    return

        # SQL の WHERE 句を動的に組み立てる
        type_sel   = self._calc_type_var.get()
        conditions = []
        params     = []

        if resident_id_filter is not None:
            conditions.append("resident_id = ?")
            params.append(resident_id_filter)
        if from_date:
            conditions.append("transaction_date >= ?")
            params.append(from_date)
        if to_date:
            conditions.append("transaction_date <= ?")
            params.append(to_date)
        if type_sel == "出金のみ":
            conditions.append("expense > 0")
        elif type_sel == "入金のみ":
            conditions.append("income > 0")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        try:
            conn = sqlite3.connect(DEPOSIT_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(f"""
                SELECT resident_id, transaction_date, description, income, expense
                FROM deposit_transactions
                {where}
                ORDER BY transaction_date, id
            """, params).fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("読み込みエラー",
                                 f"預かり金DBの読み込みに失敗しました。\n{e}", parent=self)
            return

        if not rows:
            messagebox.showinfo("結果",
                                "条件に一致するデータが見つかりませんでした。", parent=self)
            return

        # 既存のリストに追記する
        added = 0
        for row in rows:
            rname    = all_residents.get(row["resident_id"], "不明")
            date_str = row["transaction_date"]
            desc     = row["description"]

            if type_sel != "入金のみ" and row["expense"] > 0:
                memo = f"[出金] {rname}　{date_str}　{desc}"
                self._calc_insert_row(memo, row["expense"])
                added += 1

            if type_sel != "出金のみ" and row["income"] > 0:
                memo = f"[入金] {rname}　{date_str}　{desc}"
                self._calc_insert_row(memo, row["income"])
                added += 1

        messagebox.showinfo("読み込み完了",
                            f"{added} 件を一覧に追加しました。", parent=self)

    def _on_tab_changed(self, event):
        """タブが切り替わったとき、各タブの自動更新処理を実行する"""
        idx = self._notebook.index("current")
        if idx == 1:
            # 金銭チェックタブ：利用者残高を自動再読み込み
            self._load_cash_check_balances()
        elif idx == 2:
            # 計算機タブ：今回入力した件数ラベルを最新に更新
            self._calc_update_session_label()


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup_directories()
    setup_database()
    do_backup()
    app = DepositApp()
    app.mainloop()
