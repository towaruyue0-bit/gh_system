#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contract_app.py - 契約書一括印刷アプリ

通常入居・体験利用の契約書ファイルを選択された順に
両面（または片面）印刷するためのツールです。
入居者を選ぶと {{氏名}} {{入居日}} を自動で置き換えます。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sqlite3
import threading
from datetime import datetime

# pywin32 の確認（Officeを操作するために必要なライブラリ）
try:
    import win32com.client
    import win32print
    import pythoncom  # 別スレッドでCOMを使うために必要
    PYWIN32_OK = True
except ImportError:
    PYWIN32_OK = False

# pypdf の確認（複数PDFを1ファイルに結合するために使う）
try:
    import pypdf
    PYPDF_OK = True
except ImportError:
    PYPDF_OK = False

# ─── 定数 ────────────────────────────────────────────────────────────
APP_TITLE     = "契約書一括印刷"
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
PRIVATE_ROOT  = r"C:\GH_Data"  # 個人情報を保管する安全フォルダ（OneDrive・Claude非対応）
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DB_PATH       = os.path.join(PRIVATE_ROOT, "data", "residents.db")
TEMP_DIR      = os.path.join(BASE_DIR, "temp")  # 印刷プレビュー用の一時ファイル置き場

FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)

# Word の両面印刷モード定数
WD_DUPLEX_LONG  = 3  # 長辺綴じ（縦向き書類の通常の両面印刷）
WD_DUPLEX_SHORT = 2  # 短辺綴じ（横向き書類向け）
WD_SIMPLEX      = 1  # 片面印刷

# wdReplaceAll: Wordの「すべて置換」を表す定数
WD_REPLACE_ALL = 2

CONTRACT_TYPES = ["通常入居", "体験利用"]

# 行の背景色（偶数行・奇数行で交互に）
ROW_COLORS   = ("#FFFFFF", "#F0F4FA")
SELECT_COLOR = "#D0E8FF"  # 選択行の背景色

# チェック状態の表示文字
CHK_ON  = "☑"
CHK_OFF = "☐"

# 差し込みなしの選択肢ラベル
NO_RESIDENT_LABEL = "（差し込みなし）"


# ─── メインアプリ ─────────────────────────────────────────────────────
class ContractPrintApp:
    """契約書一括印刷アプリのメインクラス"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.resizable(False, False)

        # ファイル一覧の状態
        # 各要素: {"path": str, "name": str, "checked": bool}
        self.file_items: list[dict] = []
        self.selected_idx: int | None = None  # 現在選択中の行インデックス

        # 入居者データ: [{"id": int, "name": str, "move_in_date": str, "label": str}, ...]
        self.residents: list[dict] = []

        # UI変数
        self.contract_type_var = tk.StringVar(value=CONTRACT_TYPES[0])
        self.resident_var      = tk.StringVar(value=NO_RESIDENT_LABEL)
        self.duplex_var        = tk.IntVar(value=WD_DUPLEX_LONG)
        self.printer_var       = tk.StringVar()
        self.status_var        = tk.StringVar(value="準備完了")

        # プリンター一覧を取得
        self.printers = self._get_printers()
        if self.printers:
            try:
                default = win32print.GetDefaultPrinter()
                self.printer_var.set(default if default in self.printers else self.printers[0])
            except Exception:
                self.printer_var.set(self.printers[0])

        # 入居者データを先に読み込んでからUIを構築する
        # （先に読み込まないとコンボボックスに入居者が表示されない）
        self._load_residents()
        self._build_ui()
        self._load_files()
        self._cleanup_temp_files()  # 前回の一時PDFファイルを起動時に削除

    # ── プリンター取得 ─────────────────────────────────────────────────
    def _get_printers(self) -> list[str]:
        """インストール済みプリンターの名前一覧を返す"""
        if not PYWIN32_OK:
            return []
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            return [p[2] for p in win32print.EnumPrinters(flags)]
        except Exception:
            return []

    # ── 入居者読み込み ────────────────────────────────────────────────
    def _load_residents(self):
        """入居者DBから「入居中」の入居者一覧を取得する"""
        self.residents = []
        db_path = os.path.normpath(DB_PATH)
        if not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, name, move_in_date
                FROM residents
                WHERE status = '入居中'
                ORDER BY move_in_date
            """)
            for row in cur.fetchall():
                date_str = self._format_date(row["move_in_date"])
                label = f"{row['name']}　（入居日: {date_str}）" if date_str else row["name"]
                self.residents.append({
                    "id":           row["id"],
                    "name":         row["name"],
                    "move_in_date": row["move_in_date"],
                    "label":        label,
                })
            conn.close()
        except Exception as e:
            self.status_var.set(f"入居者DB読み込みエラー: {e}")

    # ── UI 構築 ────────────────────────────────────────────────────────
    def _build_ui(self):
        """画面全体を構築する"""
        # ── タイトルバー ──
        tk.Frame(self.root, bg="#2C6EAB").pack(fill="x")
        title_bar = tk.Frame(self.root, bg="#2C6EAB")
        title_bar.pack(fill="x")
        tk.Label(title_bar, text=f"　{APP_TITLE}",
                 font=FONT_TITLE, bg="#2C6EAB", fg="white", pady=9).pack(side="left")

        # ── メインエリア ──
        main = tk.Frame(self.root, padx=14, pady=10)
        main.pack(fill="both", expand=True)

        # ── 契約種別 ──
        lf_type = tk.LabelFrame(main, text="契約種別", font=FONT_BOLD, padx=8, pady=6)
        lf_type.pack(fill="x", pady=(0, 8))
        for ct in CONTRACT_TYPES:
            tk.Radiobutton(lf_type, text=ct, variable=self.contract_type_var,
                           value=ct, font=FONT,
                           command=self._load_files).pack(side="left", padx=16)

        # ── 入居者選択（差し込み） ──
        lf_resident = tk.LabelFrame(
            main,
            text="入居者（選択すると {{氏名}} と {{入居日}} を自動で差し込みます）",
            font=FONT_BOLD, padx=8, pady=6)
        lf_resident.pack(fill="x", pady=(0, 8))

        resident_labels = [NO_RESIDENT_LABEL] + [r["label"] for r in self.residents]
        self.resident_cb = ttk.Combobox(
            lf_resident, textvariable=self.resident_var,
            values=resident_labels, state="readonly",
            font=FONT, width=50)
        self.resident_cb.pack(fill="x")

        # ── ファイル一覧 ──
        lf_files = tk.LabelFrame(
            main,
            text="印刷ファイル一覧　　クリックで選択 ／ ダブルクリックでチェック切替 ／ ↑↓で順番変更",
            font=FONT_BOLD, padx=8, pady=6)
        lf_files.pack(fill="both", pady=(0, 8))

        self.list_frame = tk.Frame(lf_files, bd=1, relief="sunken")
        self.list_frame.pack(side="left", fill="both", expand=True)

        btn_col = tk.Frame(lf_files)
        btn_col.pack(side="right", padx=(10, 0), anchor="center")
        tk.Button(btn_col, text="↑ 上へ", font=FONT, width=8,
                  relief="flat", bg="#4A90D9", fg="white", cursor="hand2",
                  pady=5, command=self._move_up).pack(pady=(0, 8))
        tk.Button(btn_col, text="↓ 下へ", font=FONT, width=8,
                  relief="flat", bg="#4A90D9", fg="white", cursor="hand2",
                  pady=5, command=self._move_down).pack()

        # ── プリンター選択 ──
        lf_printer = tk.LabelFrame(main, text="プリンター", font=FONT_BOLD, padx=8, pady=6)
        lf_printer.pack(fill="x", pady=(0, 8))
        ttk.Combobox(lf_printer, textvariable=self.printer_var,
                     values=self.printers, state="readonly",
                     font=FONT, width=50).pack(fill="x")

        # ── 印刷方法 ──
        lf_duplex = tk.LabelFrame(main, text="印刷方法", font=FONT_BOLD, padx=8, pady=6)
        lf_duplex.pack(fill="x", pady=(0, 10))
        for label, val in [
            ("両面印刷（長辺綴じ）― 縦向き書類の通常の両面", WD_DUPLEX_LONG),
            ("両面印刷（短辺綴じ）― 横向き書類向け",         WD_DUPLEX_SHORT),
            ("片面印刷",                                      WD_SIMPLEX),
        ]:
            tk.Radiobutton(lf_duplex, text=label, variable=self.duplex_var,
                           value=val, font=FONT).pack(anchor="w", padx=4)

        # ── ステータス ──
        tk.Label(main, textvariable=self.status_var,
                 font=FONT_SMALL, fg="#555555", anchor="w").pack(fill="x", pady=(0, 4))

        # ── ボタン行（印刷プレビュー・Wordで開く・印刷開始） ──
        btn_row = tk.Frame(main)
        btn_row.pack(pady=(0, 4))

        self.print_preview_btn = tk.Button(
            btn_row, text="　印刷プレビュー（全体）　",
            font=("MS Gothic", 11),
            relief="flat", bg="#5B8DB8", fg="white",
            cursor="hand2", padx=14, pady=8,
            command=self._print_preview_all)
        self.print_preview_btn.pack(side="left", padx=(0, 8))

        self.preview_btn = tk.Button(
            btn_row, text="Wordで開く",
            font=("MS Gothic", 10),
            relief="flat", bg="#6C757D", fg="white",
            cursor="hand2", padx=10, pady=8,
            command=self._preview_selected)
        self.preview_btn.pack(side="left", padx=(0, 12))

        self.print_btn = tk.Button(
            btn_row, text="　　印刷開始　　",
            font=("MS Gothic", 12, "bold"),
            relief="flat", bg="#2C9E4A", fg="white",
            cursor="hand2", padx=20, pady=8,
            command=self._start_print)
        self.print_btn.pack(side="left")

        tk.Label(main,
                 text="※ 印刷プレビュー：チェック済みファイルをすべてまとめてPDF化して表示します（差し込みも反映）。"
                      "　Wordで開く：選択中の1ファイルをWordで表示します。",
                 font=FONT_SMALL, fg="#888888").pack()

    # ── ファイル読み込み ───────────────────────────────────────────────
    def _load_files(self):
        """選択された契約種別フォルダからファイルを読み込み一覧を再描画する"""
        ct     = self.contract_type_var.get()
        folder = os.path.join(TEMPLATES_DIR, ct)

        self.file_items   = []
        self.selected_idx = None

        for w in self.list_frame.winfo_children():
            w.destroy()

        if not os.path.isdir(folder):
            self.status_var.set(f"フォルダが見つかりません: {folder}")
            return

        files = sorted([
            f for f in os.listdir(folder)
            if f.lower().endswith((".doc", ".docx", ".xls", ".xlsx"))
        ])
        for fname in files:
            self.file_items.append({
                "path":    os.path.join(folder, fname),
                "name":    fname,
                "checked": True,
            })

        self._redraw_list()
        self.status_var.set(f"{len(files)} ファイルを読み込みました")

    # ── 一覧の再描画 ──────────────────────────────────────────────────
    def _redraw_list(self):
        """file_items の内容でリストを再描画する"""
        for w in self.list_frame.winfo_children():
            w.destroy()

        for i, item in enumerate(self.file_items):
            bg = SELECT_COLOR if i == self.selected_idx else ROW_COLORS[i % 2]
            row = tk.Frame(self.list_frame, bg=bg)
            row.pack(fill="x")

            chk_text = CHK_ON if item["checked"] else CHK_OFF
            tk.Label(row, text=chk_text, font=FONT, bg=bg, width=2).pack(side="left", padx=6)
            tk.Label(row, text=item["name"], font=FONT, bg=bg,
                     anchor="w", width=48).pack(side="left", pady=4)

            for widget in (row, *row.winfo_children()):
                widget.bind("<Button-1>",        lambda e, idx=i: self._select_row(idx))
                widget.bind("<Double-Button-1>", lambda e, idx=i: self._toggle_check(idx))

    # ── 行操作 ────────────────────────────────────────────────────────
    def _select_row(self, idx: int):
        """指定インデックスの行を選択状態にする"""
        self.selected_idx = idx
        self._redraw_list()

    def _toggle_check(self, idx: int):
        """指定行のチェック状態を切り替える"""
        self.file_items[idx]["checked"] = not self.file_items[idx]["checked"]
        self.selected_idx = idx
        self._redraw_list()

    def _swap(self, i: int, j: int):
        """file_items の i 行目と j 行目を入れ替える"""
        self.file_items[i], self.file_items[j] = self.file_items[j], self.file_items[i]

    def _move_up(self):
        """選択行を1つ上へ移動する"""
        idx = self.selected_idx
        if idx is None or idx <= 0:
            return
        self._swap(idx - 1, idx)
        self.selected_idx = idx - 1
        self._redraw_list()

    def _move_down(self):
        """選択行を1つ下へ移動する"""
        idx = self.selected_idx
        if idx is None or idx >= len(self.file_items) - 1:
            return
        self._swap(idx, idx + 1)
        self.selected_idx = idx + 1
        self._redraw_list()

    # ── 差し込みデータ取得 ────────────────────────────────────────────
    def _get_replacements(self) -> dict[str, str] | None:
        """
        選択された入居者の差し込みデータを辞書で返す。
        「差し込みなし」が選択されている場合は None を返す。

        戻り値の例:
            {"{{氏名}}": "田中 太郎", "{{入居日}}": "2024年10月1日"}
        """
        label = self.resident_var.get()
        if label == NO_RESIDENT_LABEL:
            return None

        # ラベルから一致する入居者を探す
        for r in self.residents:
            if r["label"] == label:
                return {
                    "{{氏名}}":  r["name"],
                    "{{入居日}}": self._format_date(r["move_in_date"]),
                }
        return None

    # ── 日付フォーマット ──────────────────────────────────────────────
    def _format_date(self, date_str: str | None) -> str:
        """
        "YYYY-MM-DD" 形式の日付文字列を "YYYY年M月D日" に変換して返す。
        変換できない場合はそのまま返す。

        Args:
            date_str: "2024-10-01" のような文字列（または None）
        Returns:
            "2024年10月1日" のような文字列
        """
        if not date_str:
            return ""
        try:
            dt = datetime.strptime(date_str.strip(), "%Y-%m-%d")
            return f"{dt.year}年{dt.month}月{dt.day}日"
        except ValueError:
            return date_str

    # ── 印刷プレビュー（全ファイル結合PDF） ──────────────────────────
    def _print_preview_all(self):
        """
        チェック済みファイルをすべてPDFに変換・結合し、1つのPDFとして表示する。
        入居者が選択されていれば差し込みも反映した状態でプレビューできる。
        結合PDFは temp フォルダに保存され、次回起動時に自動削除される。
        """
        if not PYWIN32_OK:
            messagebox.showerror(
                "エラー",
                "pywin32 がインストールされていません。\n"
                "コマンドプロンプトで以下を実行してください:\n"
                "  pip install pywin32")
            return

        targets = [item for item in self.file_items if item["checked"]]
        if not targets:
            messagebox.showwarning("確認", "プレビューするファイルが選択されていません。")
            return

        replacements = self._get_replacements()
        self.print_preview_btn.config(state="disabled")
        self.status_var.set("印刷プレビュー用PDFを作成中...")

        def _convert_and_open():
            # 別スレッドでCOMを使うために初期化
            pythoncom.CoInitialize()
            try:
                os.makedirs(TEMP_DIR, exist_ok=True)

                pdf_paths = []  # 各ファイルを変換したPDFパスのリスト

                for i, item in enumerate(targets, 1):
                    self.root.after(0, self.status_var.set,
                                    f"PDF変換中... ({i}/{len(targets)})  {item['name']}")
                    ext     = os.path.splitext(item["name"])[1].lower()
                    # ファイル名には番号のみ使用（日本語文字でのパスエラーを防ぐ）
                    out_pdf = os.path.join(TEMP_DIR, f"prev_{i:02d}.pdf")

                    if ext in (".doc", ".docx"):
                        self._word_to_pdf(item["path"], out_pdf, replacements)
                        pdf_paths.append(out_pdf)
                    elif ext in (".xls", ".xlsx"):
                        self._excel_to_pdf(item["path"], out_pdf)
                        pdf_paths.append(out_pdf)

                if not pdf_paths:
                    self.root.after(0, messagebox.showwarning, "確認",
                                    "PDFに変換できるファイルがありませんでした。")
                    return

                if PYPDF_OK:
                    # 全PDFを1ファイルに結合して開く
                    self.root.after(0, self.status_var.set, "PDFを結合中...")
                    combined_path = os.path.join(TEMP_DIR, "preview_combined.pdf")
                    writer = pypdf.PdfWriter()
                    for p in pdf_paths:
                        writer.append(p)
                    with open(combined_path, "wb") as f:
                        writer.write(f)
                    os.startfile(combined_path)
                    self.root.after(0, self.status_var.set,
                                    f"印刷プレビューを表示中（{len(pdf_paths)} ファイル結合）")
                else:
                    # pypdf がない場合は各PDFを個別に開く
                    for p in pdf_paths:
                        os.startfile(p)
                    self.root.after(0, self.status_var.set,
                                    f"印刷プレビューを表示中（{len(pdf_paths)} ファイル、個別表示）")

            except Exception as e:
                self.root.after(0, messagebox.showerror, "エラー",
                                f"印刷プレビューに失敗しました:\n{e}")
                self.root.after(0, self.status_var.set, "印刷プレビューエラー")
            finally:
                pythoncom.CoUninitialize()
                self.root.after(0, self.print_preview_btn.config, {"state": "normal"})

        threading.Thread(target=_convert_and_open, daemon=True).start()

    def _word_to_pdf(self, filepath: str, out_pdf: str,
                     replacements: dict | None):
        """
        Wordファイルを差し込み置換してPDFに変換する。

        Args:
            filepath    : 元のWordファイルパス
            out_pdf     : 出力先PDFパス
            replacements: 差し込みデータ（Noneの場合は置換しない）
        """
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            doc = word.Documents.Open(filepath, ReadOnly=False)
            try:
                if replacements:
                    self._replace_word_placeholders(doc, replacements)
                # FileFormat=17 は wdFormatPDF を表す
                doc.SaveAs2(out_pdf, FileFormat=17)
            finally:
                doc.Close(False)  # 元ファイルを変更しないで閉じる
        finally:
            word.Quit()

    def _excel_to_pdf(self, filepath: str, out_pdf: str):
        """
        ExcelファイルをPDFに変換する。

        Args:
            filepath: 元のExcelファイルパス
            out_pdf : 出力先PDFパス
        """
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        try:
            wb = excel.Workbooks.Open(filepath, ReadOnly=True)
            try:
                # xlTypePDF=0: PDF形式でエクスポート
                wb.ExportAsFixedFormat(0, out_pdf)
            finally:
                wb.Close(False)
        finally:
            excel.Quit()

    # ── 一時ファイル削除 ──────────────────────────────────────────────
    def _cleanup_temp_files(self):
        """temp フォルダ内の前回の一時PDFファイルを削除する（起動時に呼ぶ）"""
        if not os.path.isdir(TEMP_DIR):
            return
        for fname in os.listdir(TEMP_DIR):
            if fname.startswith("preview_") and fname.endswith(".pdf"):
                try:
                    os.remove(os.path.join(TEMP_DIR, fname))
                except OSError:
                    pass  # 開いているファイルは削除できないので無視する

    # ── Wordで開く（既存プレビュー） ──────────────────────────────────
    def _preview_selected(self):
        """
        現在選択中の行のファイルをWordで直接開く。
        入居者が選択されていれば差し込みも適用した状態で表示する。
        Wordを閉じると変更は破棄され、元のファイルは変更されない。
        """
        if not PYWIN32_OK:
            messagebox.showerror(
                "エラー",
                "pywin32 がインストールされていません。\n"
                "コマンドプロンプトで以下を実行してください:\n"
                "  pip install pywin32")
            return

        if self.selected_idx is None:
            messagebox.showinfo("確認", "プレビューするファイルを一覧でクリックして選択してください。")
            return

        item = self.file_items[self.selected_idx]
        ext  = os.path.splitext(item["name"])[1].lower()

        if ext not in (".doc", ".docx"):
            messagebox.showinfo("確認",
                                "プレビューはWordファイル（.doc/.docx）のみ対応しています。\n"
                                f"選択中のファイル: {item['name']}")
            return

        replacements = self._get_replacements()

        self.status_var.set(f"プレビューを開いています... {item['name']}")
        self.preview_btn.config(state="disabled")

        def _open():
            # 別スレッドでCOMを使うために初期化
            pythoncom.CoInitialize()
            try:
                word = win32com.client.Dispatch("Word.Application")
                word.Visible = True  # Wordを画面に表示する
                doc = word.Documents.Open(item["path"], ReadOnly=False)

                # 差し込みデータがあれば置換する
                if replacements:
                    self._replace_word_placeholders(doc, replacements)

                # プレビュー表示後、ユーザーが手動でWordを閉じるまで待機
                # （このスレッドはここで終了。Wordはそのまま開いたまま）
                self.root.after(0, self.status_var.set,
                                f"プレビュー中: {item['name']}　（確認後にWordを閉じてください）")
            except Exception as e:
                self.root.after(0, messagebox.showerror, "エラー", f"プレビューに失敗しました:\n{e}")
                self.root.after(0, self.status_var.set, "プレビューエラー")
            finally:
                pythoncom.CoUninitialize()
                self.root.after(0, self.preview_btn.config, {"state": "normal"})

        threading.Thread(target=_open, daemon=True).start()

    # ── 印刷開始 ─────────────────────────────────────────────────────
    def _start_print(self):
        """印刷ボタンが押されたときの処理"""
        if not PYWIN32_OK:
            messagebox.showerror(
                "エラー",
                "pywin32 がインストールされていません。\n"
                "コマンドプロンプトで\n"
                "  pip install pywin32\n"
                "を実行してください。")
            return

        targets = [item for item in self.file_items if item["checked"]]
        if not targets:
            messagebox.showwarning("確認", "印刷するファイルが選択されていません。")
            return

        printer = self.printer_var.get()
        if not printer:
            messagebox.showwarning("確認", "プリンターを選択してください。")
            return

        replacements  = self._get_replacements()
        duplex_label  = {
            WD_DUPLEX_LONG:  "両面（長辺綴じ）",
            WD_DUPLEX_SHORT: "両面（短辺綴じ）",
            WD_SIMPLEX:      "片面",
        }[self.duplex_var.get()]

        names = "\n".join(f"  ・{t['name']}" for t in targets)
        insert_info = (
            f"\n差し込み  : {self.resident_var.get()}" if replacements else ""
        )
        msg = (f"以下 {len(targets)} ファイルを印刷します。\n\n"
               f"{names}\n\n"
               f"プリンター: {printer}\n"
               f"印刷方法 : {duplex_label}"
               f"{insert_info}\n\n"
               f"よろしいですか？")
        if not messagebox.askyesno("印刷確認", msg):
            return

        self.print_btn.config(state="disabled", text="印刷中...")
        thread = threading.Thread(
            target=self._print_all,
            args=(targets, printer, self.duplex_var.get(), replacements),
            daemon=True)
        thread.start()

    # ── 全ファイル印刷（別スレッド） ───────────────────────────────────
    def _print_all(self, targets: list[dict], printer: str,
                   duplex_mode: int, replacements: dict | None):
        """
        全ファイルを順番に印刷する（別スレッドで実行される）

        Args:
            targets      : 印刷対象ファイル情報のリスト
            printer      : プリンター名
            duplex_mode  : 両面モード定数
            replacements : 差し込みデータ（例: {"{{氏名}}": "田中 太郎"}）またはNone
        """
        # 別スレッドでWordやExcelをCOM経由で操作するには、スレッドごとに
        # CoInitialize() を呼ぶ必要がある。呼ばないと「CoInitialize は呼び出されていません」
        # エラーが発生する。
        pythoncom.CoInitialize()
        total  = len(targets)
        errors = []

        try:
            for i, item in enumerate(targets, 1):
                self.root.after(0, self.status_var.set,
                                f"印刷中... ({i}/{total})  {item['name']}")
                try:
                    ext = os.path.splitext(item["name"])[1].lower()
                    if ext in (".doc", ".docx"):
                        self._print_word(item["path"], printer, duplex_mode, replacements)
                    elif ext in (".xls", ".xlsx"):
                        self._print_excel(item["path"], printer, duplex_mode)
                except Exception as e:
                    errors.append(f"{item['name']}: {e}")
        finally:
            # 初期化したCOMを必ず解放する
            pythoncom.CoUninitialize()

        self.root.after(0, self._on_print_done, errors)

    # ── Word 印刷 ─────────────────────────────────────────────────────
    def _print_word(self, filepath: str, printer: str,
                    duplex_mode: int, replacements: dict | None):
        """
        Wordファイルを印刷する。差し込みデータがあれば印刷前に置換する。
        （元のファイルは保存しない）

        Args:
            filepath     : 印刷するファイルのパス
            printer      : プリンター名
            duplex_mode  : 両面モード定数
            replacements : 差し込みデータまたはNone
        """
        import time
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            doc = word.Documents.Open(filepath, ReadOnly=False)
            try:
                if replacements:
                    self._replace_word_placeholders(doc, replacements)
                doc.PrintOut(Copies=1, PrinterName=printer, Duplex=duplex_mode)
                time.sleep(1)  # スプールに転送されるまで少し待つ
            finally:
                doc.Close(False)  # 保存しないで閉じる（元のファイルを変更しない）
        finally:
            word.Quit()

    def _replace_word_placeholders(self, doc, replacements: dict[str, str]):
        """
        Wordドキュメント内のプレースホルダーを差し込みデータで置換する。

        Args:
            doc          : Word.Document オブジェクト
            replacements : {"{{氏名}}": "田中 太郎", ...} のような辞書
        """
        find = doc.Content.Find
        find.ClearFormatting()
        find.Replacement.ClearFormatting()

        for placeholder, value in replacements.items():
            find.Execute(
                FindText=placeholder,
                MatchCase=True,
                MatchWholeWord=False,
                MatchWildcards=False,
                MatchSoundsLike=False,
                MatchAllWordForms=False,
                Forward=True,
                Wrap=1,           # wdFindContinue: 末尾まで行ったら先頭に戻る
                Format=False,
                ReplaceWith=value,
                Replace=WD_REPLACE_ALL,
            )

    # ── Excel 印刷 ────────────────────────────────────────────────────
    def _print_excel(self, filepath: str, printer: str, duplex_mode: int):
        """
        Excelファイルをすべてのシートを対象に印刷する。

        Args:
            filepath    : 印刷するファイルのパス
            printer     : プリンター名
            duplex_mode : 両面モード定数
        """
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        try:
            wb = excel.Workbooks.Open(filepath, ReadOnly=True)
            try:
                for sheet in wb.Worksheets:
                    sheet.PrintOut(ActivePrinter=printer)
            finally:
                wb.Close(False)
        finally:
            excel.Quit()

    # ── 印刷完了後処理 ────────────────────────────────────────────────
    def _on_print_done(self, errors: list[str]):
        """印刷完了後の後処理（GUIスレッドで実行）"""
        self.print_btn.config(state="normal", text="　　印刷開始　　")

        if errors:
            err_msg = "\n".join(errors)
            messagebox.showerror(
                "印刷エラー",
                f"以下のファイルで印刷エラーが発生しました:\n\n{err_msg}")
            self.status_var.set("一部エラーあり")
        else:
            messagebox.showinfo("完了", "すべてのファイルの印刷が完了しました。")
            self.status_var.set("印刷完了")


# ─── 起動 ─────────────────────────────────────────────────────────────
def main():
    """アプリを起動する"""
    if not PYWIN32_OK:
        root_tmp = tk.Tk()
        root_tmp.withdraw()
        messagebox.showwarning(
            "ライブラリ不足",
            "pywin32 がインストールされていません。\n"
            "印刷・プレビュー機能は使えませんが、画面の確認はできます。\n\n"
            "インストール方法（コマンドプロンプトで実行）:\n  pip install pywin32")
        root_tmp.destroy()

    root = tk.Tk()
    ContractPrintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
