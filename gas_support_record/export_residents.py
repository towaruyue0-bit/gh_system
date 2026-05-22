# =============================================================================
# 利用者マスター書き出しツール
# residents.db と medicine.db から入居中の利用者データを CSV に書き出す。
# 書き出した CSV を Google スプレッドシートの「利用者マスター」シートに
# コピー＆ペーストして使う。
# =============================================================================

import tkinter as tk
from tkinter import messagebox
import sqlite3
import os
import subprocess
from datetime import datetime

# =============================================================================
# パス設定
# =============================================================================
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
MEDICINE_DB  = os.path.join(DATA_DIR, "medicine.db")

# 書き出し先（support_record フォルダ内）
BASE_DIR = r"C:\Users\Public\gh_system\gas_support_record"
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# フォント
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")


def get_residents_with_medication():
    """
    residents.db から入居中の利用者を取得し、
    medicine.db から各利用者の服薬時間帯（朝・昼・夕・寝る前）を結合して返す。

    戻り値:
        list of dict: [{name, medication, smoking}, ...]
        - medication: 「朝・昼・夕」のような形式の文字列。なければ「なし」
        - smoking: 空文字（residents.db に喫煙情報がないため）
    """
    if not os.path.exists(RESIDENTS_DB):
        raise FileNotFoundError(f"入居者DBが見つかりません:\n{RESIDENTS_DB}")

    # ---- 入居中の利用者を取得 ----
    conn_r = sqlite3.connect(RESIDENTS_DB)
    conn_r.row_factory = sqlite3.Row
    cur_r = conn_r.cursor()
    cur_r.execute(
        "SELECT id, name, resident_code FROM residents WHERE status = '入居中' ORDER BY room_number, id"
    )
    residents = [dict(row) for row in cur_r.fetchall()]
    conn_r.close()

    if not residents:
        return []

    # コードが未設定の利用者がいる場合は警告用フラグを立てる
    no_code = [r["name"] for r in residents if not r.get("resident_code")]

    # ---- 服薬情報を取得（medicine.db が存在する場合のみ） ----
    med_map = {}  # {resident_id: ["朝", "昼", ...]}
    if os.path.exists(MEDICINE_DB):
        conn_m = sqlite3.connect(MEDICINE_DB)
        conn_m.row_factory = sqlite3.Row
        cur_m = conn_m.cursor()
        # enabled = 1 の時間帯だけ取得
        cur_m.execute(
            "SELECT resident_id, time_slot FROM medicine_settings WHERE enabled = 1 "
            "ORDER BY resident_id, CASE time_slot "
            "WHEN '朝' THEN 1 WHEN '昼' THEN 2 WHEN '夕' THEN 3 WHEN '寝る前' THEN 4 ELSE 5 END"
        )
        for row in cur_m.fetchall():
            rid = row["resident_id"]
            if rid not in med_map:
                med_map[rid] = []
            med_map[rid].append(row["time_slot"])
        conn_m.close()

    # ---- 結合 ----
    result = []
    for r in residents:
        slots = med_map.get(r["id"], [])
        medication = "・".join(slots) if slots else "なし"
        result.append({
            "code":       r["resident_code"] or "",   # 名前でなくコードを使用
            "medication": medication,
            "smoking":    "",   # スプレッドシート側で手動入力
        })

    # コード未設定の利用者名を呼び出し元に通知するためタプルで返す
    return result, no_code


def export_csv(residents):
    """
    利用者データを CSV ファイルに書き出す。
    スプレッドシートに貼り付けやすいよう BOM 付き UTF-8 で保存する。
    名前でなく利用者コードを使うことで個人情報がクラウドに残らない。

    引数:
        residents: get_residents_with_medication() の戻り値（code, medication, smoking）

    戻り値:
        str: 書き出したファイルのパス
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath  = os.path.join(OUTPUT_DIR, f"利用者マスター_{timestamp}.csv")

    # BOM 付き UTF-8 で書き出すと Excel / スプレッドシートで文字化けしない
    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        f.write("コード,服薬,喫煙\n")
        for r in residents:
            # カンマを含む可能性があるためダブルクォートで囲む
            code = r["code"].replace('"', '""')
            med  = r["medication"].replace('"', '""')
            smk  = r["smoking"].replace('"', '""')
            f.write(f'"{code}","{med}","{smk}"\n')

    return filepath


# =============================================================================
# GUI
# =============================================================================

class App(tk.Tk):
    """利用者マスター書き出しツールのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("利用者マスター書き出しツール")
        self.geometry("560x420")
        self.resizable(False, False)
        self.configure(bg="#F0F4FA")
        self._build_ui()

    def _build_ui(self):
        """画面を作成する"""
        # タイトル
        tk.Label(
            self, text="利用者マスター書き出しツール",
            font=FONT_TITLE, bg="#4A6FA5", fg="white",
            padx=10, pady=12
        ).pack(fill="x")

        # 説明
        desc = (
            "このツールは、入居者マスターDBから「入居中」の利用者データを\n"
            "CSV ファイルに書き出します。\n\n"
            "【重要】名前でなく利用者コード（A01 など）で書き出します。\n"
            "スプレッドシートに個人名が載らないようにするための対策です。\n\n"
            "書き出したファイルを Google スプレッドシートの\n"
            "「利用者マスター」シートに貼り付けてください。\n\n"
            "※ 喫煙欄は空白で書き出されます。\n"
            "　 必要な方はスプレッドシートで「あり」と入力してください。"
        )
        tk.Label(
            self, text=desc, font=FONT,
            bg="#F0F4FA", justify="left",
            wraplength=500, padx=20, pady=16
        ).pack()

        # 書き出しボタン
        tk.Button(
            self, text="CSV を書き出す",
            font=FONT_BOLD, bg="#4A6FA5", fg="white",
            relief="flat", cursor="hand2",
            padx=20, pady=10,
            command=self._on_export
        ).pack(pady=10)

        # 結果表示ラベル
        self.result_var = tk.StringVar(value="")
        tk.Label(
            self, textvariable=self.result_var,
            font=FONT, bg="#F0F4FA", fg="#276749",
            wraplength=500, justify="left", padx=20
        ).pack()

    def _on_export(self):
        """書き出しボタンが押されたときの処理"""
        try:
            residents, no_code = get_residents_with_medication()
        except FileNotFoundError as e:
            messagebox.showerror("エラー", str(e))
            return

        if not residents:
            messagebox.showinfo("確認", "入居中の利用者が見つかりませんでした。")
            return

        # コードが未設定の利用者がいる場合は警告を出す
        if no_code:
            names_str = "、".join(no_code)
            messagebox.showwarning(
                "利用者コード未設定",
                f"以下の利用者にコードが割り当てられていません:\n{names_str}\n\n"
                "入居管理マスターを開き「コード一括割り当て」ボタンを\n"
                "押してからもう一度書き出してください。"
            )
            return

        try:
            filepath = export_csv(residents)
        except Exception as e:
            messagebox.showerror("エラー", f"書き出しに失敗しました:\n{e}")
            return

        # 書き出し先フォルダを開く
        subprocess.Popen(f'explorer /select,"{filepath}"')

        self.result_var.set(
            f"✓ {len(residents)} 名分を書き出しました。\n"
            f"ファイル: {os.path.basename(filepath)}\n\n"
            "エクスプローラーでファイルが選択されています。\n"
            "Excel で開いてコピー → スプレッドシートに貼り付けてください。\n\n"
            "※ CSV には名前でなく利用者コード（A01 など）が入っています。"
        )


# =============================================================================
# 起動
# =============================================================================
if __name__ == "__main__":
    app = App()
    app.mainloop()
