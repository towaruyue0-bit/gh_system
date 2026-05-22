#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利用者日用品管理アプリ

利用者ごとの日用品（シャンプー・歯ブラシ等）の在庫を管理する。
入庫（購入）記録を積み重ねることで、だいたい何日おきに補充が必要か
（平均スパン）を把握できる。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
from datetime import datetime, date

# ─── パス定義 ───────────────────────────────────────────────
# 個人情報はセキュリティのため gh_system 外のフォルダに保管する
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "backups")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
ITEMS_DB     = os.path.join(DATA_DIR, "daily_items.db")
MAX_BACKUPS  = 10

# ─── フォント定義 ────────────────────────────────────────────
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)

# ─── カラー定義 ──────────────────────────────────────────────
C_BG       = "#F0F4FA"
C_WHITE    = "#FFFFFF"
C_ROW_ODD  = "#FFFFFF"
C_ROW_EVEN = "#F0F4FA"
C_ZERO_BG  = "#FDECEA"   # 在庫0の行背景（赤系）
C_ZERO_FG  = "#C0392B"   # 在庫0の行文字
C_PRIMARY  = "#2C5F8A"   # 品目追加ボタン
C_GREEN    = "#1E8449"   # 入庫記録ボタン
C_ORANGE   = "#CA6F1E"   # 払い出し記録ボタン
C_PURPLE   = "#7D3C98"   # 数量変更ボタン
C_TEAL     = "#148F77"   # 在庫チェック記録ボタン
C_GRAY2    = "#555555"   # 履歴ボタン
C_DANGER   = "#C0392B"   # 削除ボタン
C_BTN_FG   = "#FFFFFF"
C_SELECTED = "#D0E4F7"


# ═══════════════════════════════════════════════════════════════
#  DB・バックアップ 初期化処理
# ═══════════════════════════════════════════════════════════════

def init_dirs():
    """必要なディレクトリが存在しなければ作成する。"""
    for d in [DATA_DIR, BACKUP_DIR]:
        os.makedirs(d, exist_ok=True)


def backup_db():
    """
    アプリ起動時に daily_items.db をバックアップする。
    バックアップ数が MAX_BACKUPS を超えたら古い順に削除する。
    """
    if not os.path.exists(ITEMS_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"daily_items_backup_{timestamp}.db")
    shutil.copy2(ITEMS_DB, backup_path)

    # 古いバックアップを削除
    backups = sorted([
        f for f in os.listdir(BACKUP_DIR)
        if f.startswith("daily_items_backup_") and f.endswith(".db")
    ])
    while len(backups) > MAX_BACKUPS:
        os.remove(os.path.join(BACKUP_DIR, backups.pop(0)))


def init_db():
    """
    daily_items.db を初期化する。
    テーブルが存在しない場合のみ作成するため、既存データは消えない。
    """
    conn = sqlite3.connect(ITEMS_DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        -- 品目テーブル：利用者ごとの日用品を登録
        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            item_name   TEXT    NOT NULL,
            unit        TEXT    NOT NULL DEFAULT '個',
            current_qty INTEGER NOT NULL DEFAULT 0,
            memo        TEXT,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        );

        -- 入庫記録テーブル：いつ・なにを・何個買ったかを記録
        -- 品目を削除すると関連する入庫記録も自動削除（CASCADE）
        CREATE TABLE IF NOT EXISTS purchase_records (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id       INTEGER NOT NULL,
            purchase_date TEXT    NOT NULL,
            qty           INTEGER NOT NULL DEFAULT 1,
            memo          TEXT,
            created_at    TEXT    NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        -- 払い出し記録テーブル：利用者に日用品を渡した記録
        -- 品目を削除すると関連する払い出し記録も自動削除（CASCADE）
        CREATE TABLE IF NOT EXISTS payout_records (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id      INTEGER NOT NULL,
            payout_date  TEXT    NOT NULL,
            qty          INTEGER NOT NULL DEFAULT 1,
            memo         TEXT,
            created_at   TEXT    NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        -- 在庫チェックログ：いつ在庫確認を行ったかを利用者ごとに記録する
        CREATE TABLE IF NOT EXISTS stock_check_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            check_date  TEXT    NOT NULL,
            memo        TEXT,
            created_at  TEXT    NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════
#  データ取得関数
# ═══════════════════════════════════════════════════════════════

def get_residents():
    """
    residents.db から入居中の利用者一覧を取得する。

    Returns:
        list[dict]: id と name を持つ辞書のリスト。DB未存在時は空リスト。
    """
    if not os.path.exists(RESIDENTS_DB):
        return []
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_items_with_span(resident_id):
    """
    指定した利用者の品目一覧と払い出しスパン情報を取得する。

    平均スパン（avg_span）は払い出し記録が2件以上ある場合のみ計算する。
    連続する払い出し日の間隔（日数）の平均を「だいたい何日おきに払い出しているか」として返す。

    Args:
        resident_id (int): 利用者のID

    Returns:
        list[dict]: 各品目の情報（id, item_name, unit, current_qty,
                    memo, last_payout, avg_span）を含む辞書のリスト
    """
    conn = sqlite3.connect(ITEMS_DB)
    conn.row_factory = sqlite3.Row
    try:
        items = conn.execute(
            """
            SELECT id, item_name, unit, current_qty, memo
            FROM items
            WHERE resident_id = ?
            ORDER BY item_name
            """,
            (resident_id,)
        ).fetchall()

        result = []
        for item in items:
            item_dict = dict(item)

            # 払い出し日を古い順に取得してスパンを計算する
            records = conn.execute(
                """
                SELECT payout_date FROM payout_records
                WHERE item_id = ?
                ORDER BY payout_date ASC
                """,
                (item["id"],)
            ).fetchall()

            dates = [r["payout_date"] for r in records]

            if dates:
                item_dict["last_payout"] = dates[-1]
                if len(dates) >= 2:
                    # 連続する2つの払い出し日の差（日数）を計算して平均を求める
                    diffs = []
                    for i in range(1, len(dates)):
                        d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d").date()
                        d2 = datetime.strptime(dates[i],     "%Y-%m-%d").date()
                        diffs.append((d2 - d1).days)
                    item_dict["avg_span"] = round(sum(diffs) / len(diffs))
                else:
                    item_dict["avg_span"] = None  # 記録1件のみで計算不可
            else:
                item_dict["last_payout"] = None
                item_dict["avg_span"]    = None

            result.append(item_dict)

        return result
    finally:
        conn.close()


def get_zero_stock_items():
    """
    在庫が0の品目を全利用者分まとめて取得する。
    買い物リスト用。residents.db から利用者を取得してから
    daily_items.db を検索する。

    Returns:
        list[dict]: resident_name, item_name, unit を含む辞書のリスト
    """
    residents = get_residents()
    result    = []
    if not os.path.exists(ITEMS_DB):
        return result
    conn = sqlite3.connect(ITEMS_DB)
    conn.row_factory = sqlite3.Row
    try:
        for r in residents:
            rows = conn.execute(
                """
                SELECT item_name, unit FROM items
                WHERE resident_id = ? AND current_qty = 0
                ORDER BY item_name
                """,
                (r["id"],)
            ).fetchall()
            for row in rows:
                result.append({
                    "resident_name": r["name"],
                    "item_name":     row["item_name"],
                    "unit":          row["unit"],
                })
    finally:
        conn.close()
    return result


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：品目選択
# ═══════════════════════════════════════════════════════════════

class ItemSelectDialog(tk.Toplevel):
    """
    利用者の品目一覧から操作対象を選ぶダイアログ。

    品目を選択せずにボタンを押したときに表示する。
    確定すると self.result に品目の辞書（id, item_name, unit, current_qty, memo）が入る。
    キャンセルした場合は None のまま。
    """

    def __init__(self, parent, resident_id, resident_name, title="品目を選択してください"):
        super().__init__(parent)
        self.title(title)
        self.result       = None
        self._resident_id = resident_id
        self.resizable(False, False)
        self._build(resident_name)
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self, resident_name):
        tk.Label(
            self,
            text=f"{resident_name} さんの品目を選んでください",
            font=FONT_BOLD
        ).pack(padx=16, pady=(14, 6))

        # 品目一覧リストボックス（ダブルクリックでも確定できる）
        frame = tk.Frame(self)
        frame.pack(padx=16, pady=(0, 8))

        sb = ttk.Scrollbar(frame, orient="vertical")
        self._lb = tk.Listbox(
            frame, font=FONT, width=32, height=12,
            selectmode="browse", activestyle="none",
            yscrollcommand=sb.set, cursor="hand2"
        )
        sb.config(command=self._lb.yview)
        self._lb.pack(side="left")
        sb.pack(side="left", fill="y")

        self._lb.bind("<Double-Button-1>", lambda e: self._ok())

        # 品目データを読み込む
        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, item_name, unit, current_qty, memo
            FROM items
            WHERE resident_id = ?
            ORDER BY item_name
            """,
            (self._resident_id,)
        ).fetchall()
        conn.close()

        self._items = [dict(r) for r in rows]
        for item in self._items:
            self._lb.insert("end", f"{item['item_name']}　（在庫：{item['current_qty']} {item['unit']}）")

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=10)
        tk.Button(
            btn_frame, text="決定", font=FONT_BOLD,
            bg=C_PRIMARY, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._ok
        ).pack(side="left", padx=6)
        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _ok(self):
        """選択中の品目を self.result に格納して閉じる。"""
        sel = self._lb.curselection()
        if not sel:
            messagebox.showwarning("選択なし", "品目を選択してください。", parent=self)
            return
        self.result = self._items[sel[0]]
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：品目追加・編集
# ═══════════════════════════════════════════════════════════════

class ItemDialog(tk.Toplevel):
    """
    品目の追加・編集を行うダイアログ。

    item 引数に既存品目の dict を渡すと編集モードになる。
    保存後は self.result に入力内容が格納される（キャンセル時は None）。
    """

    def __init__(self, parent, title="品目追加", item=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self._item  = item
        self.resizable(False, False)
        self._build()
        self.bind("<Return>", lambda e: self._save())
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        pad = dict(padx=14, pady=7)

        tk.Label(self, text="品目名", font=FONT).grid(row=0, column=0, sticky="e", **pad)
        self._name_var = tk.StringVar(
            value=self._item["item_name"] if self._item else ""
        )
        tk.Entry(self, textvariable=self._name_var, font=FONT, width=20).grid(
            row=0, column=1, sticky="w", **pad
        )

        tk.Label(self, text="単位", font=FONT).grid(row=1, column=0, sticky="e", **pad)
        self._unit_var = tk.StringVar(
            value=self._item["unit"] if self._item else "個"
        )
        unit_cb = ttk.Combobox(
            self, textvariable=self._unit_var, font=FONT, width=8, state="normal"
        )
        unit_cb["values"] = ["個", "本", "枚", "袋", "箱", "セット", "パック"]
        unit_cb.grid(row=1, column=1, sticky="w", **pad)

        tk.Label(self, text="現在の数量", font=FONT).grid(row=2, column=0, sticky="e", **pad)
        self._qty_var = tk.IntVar(
            value=self._item["current_qty"] if self._item else 0
        )
        tk.Spinbox(
            self, from_=0, to=999, textvariable=self._qty_var, font=FONT, width=8
        ).grid(row=2, column=1, sticky="w", **pad)

        tk.Label(self, text="メモ", font=FONT).grid(row=3, column=0, sticky="e", **pad)
        self._memo_var = tk.StringVar(
            value=(self._item.get("memo") or "") if self._item else ""
        )
        tk.Entry(self, textvariable=self._memo_var, font=FONT, width=20).grid(
            row=3, column=1, sticky="w", **pad
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=12)

        tk.Button(
            btn_frame, text="保存", font=FONT_BOLD,
            bg=C_PRIMARY, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._save
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _save(self):
        """入力内容を検証して self.result に保存する。"""
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "品目名を入力してください。", parent=self)
            return
        self.result = {
            "item_name":   name,
            "unit":        self._unit_var.get().strip() or "個",
            "current_qty": self._qty_var.get(),
            "memo":        self._memo_var.get().strip() or None,
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：入庫記録（購入）
# ═══════════════════════════════════════════════════════════════

class PurchaseDialog(tk.Toplevel):
    """
    入庫（購入）を記録するダイアログ。

    購入日・数量・メモを入力する。
    保存すると current_qty が入力した数量分だけ増える。
    保存後は self.result に入力内容が格納される（キャンセル時は None）。
    """

    def __init__(self, parent, item_name, unit):
        super().__init__(parent)
        self.title(f"入庫記録（購入）― {item_name}")
        self.result     = None
        self._item_name = item_name
        self._unit      = unit
        self.resizable(False, False)
        self._build()
        self.bind("<Return>", lambda e: self._save())
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        pad = dict(padx=14, pady=7)

        tk.Label(
            self, text=f"品目：{self._item_name}", font=FONT_BOLD
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 4))

        tk.Label(self, text="購入日", font=FONT).grid(
            row=1, column=0, sticky="e", **pad
        )
        self._date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        tk.Entry(self, textvariable=self._date_var, font=FONT, width=14).grid(
            row=1, column=1, sticky="w", **pad
        )

        tk.Label(self, text=f"購入数（{self._unit}）", font=FONT).grid(
            row=2, column=0, sticky="e", **pad
        )
        self._qty_var = tk.IntVar(value=1)
        tk.Spinbox(
            self, from_=1, to=999, textvariable=self._qty_var, font=FONT, width=8
        ).grid(row=2, column=1, sticky="w", **pad)

        # 入庫後の在庫数は「現在の在庫数 ＋ 購入数」で自動計算されることを伝える
        tk.Label(
            self,
            text="※ 在庫数は購入数分だけ自動で増えます",
            font=FONT_SMALL, fg="#555"
        ).grid(row=3, column=0, columnspan=2, padx=14, pady=(0, 4))

        tk.Label(self, text="メモ", font=FONT).grid(row=4, column=0, sticky="e", **pad)
        self._memo_var = tk.StringVar()
        tk.Entry(self, textvariable=self._memo_var, font=FONT, width=22).grid(
            row=4, column=1, sticky="w", **pad
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=12)

        tk.Button(
            btn_frame, text="記録する", font=FONT_BOLD,
            bg=C_GREEN, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._save
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _save(self):
        """入力内容を検証して self.result に保存する。"""
        try:
            datetime.strptime(self._date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning(
                "入力エラー",
                "購入日は YYYY-MM-DD 形式で入力してください。\n例：2025-05-07",
                parent=self
            )
            return

        self.result = {
            "purchase_date": self._date_var.get().strip(),
            "qty":           self._qty_var.get(),
            "memo":          self._memo_var.get().strip() or None,
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：払い出し記録
# ═══════════════════════════════════════════════════════════════

class PayoutDialog(tk.Toplevel):
    """
    払い出しを記録するダイアログ。

    払い出し日・数量・払い出し後の在庫数（任意）・メモを入力する。
    保存後は self.result に入力内容が格納される（キャンセル時は None）。
    """

    def __init__(self, parent, item_name, unit):
        super().__init__(parent)
        self.title(f"払い出し記録 ― {item_name}")
        self.result     = None
        self._item_name = item_name
        self._unit      = unit
        self.resizable(False, False)
        self._build()
        self.bind("<Return>", lambda e: self._save())
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        pad = dict(padx=14, pady=7)

        tk.Label(
            self, text=f"品目：{self._item_name}", font=FONT_BOLD
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 4))

        tk.Label(self, text="払い出し日", font=FONT).grid(
            row=1, column=0, sticky="e", **pad
        )
        self._date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        tk.Entry(self, textvariable=self._date_var, font=FONT, width=14).grid(
            row=1, column=1, sticky="w", **pad
        )

        tk.Label(self, text=f"数量（{self._unit}）", font=FONT).grid(
            row=2, column=0, sticky="e", **pad
        )
        self._qty_var = tk.IntVar(value=1)
        tk.Spinbox(
            self, from_=1, to=999, textvariable=self._qty_var, font=FONT, width=8
        ).grid(row=2, column=1, sticky="w", **pad)

        tk.Label(
            self, text="※ 在庫数は払い出し数分だけ自動で減ります",
            font=FONT_SMALL, fg="#555"
        ).grid(row=3, column=0, columnspan=2, padx=14, pady=(0, 4))

        tk.Label(self, text="メモ", font=FONT).grid(row=4, column=0, sticky="e", **pad)
        self._memo_var = tk.StringVar()
        tk.Entry(self, textvariable=self._memo_var, font=FONT, width=22).grid(
            row=4, column=1, sticky="w", **pad
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=12)

        tk.Button(
            btn_frame, text="記録する", font=FONT_BOLD,
            bg=C_ORANGE, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._save
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _save(self):
        """入力内容を検証して self.result に保存する。"""
        try:
            datetime.strptime(self._date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning(
                "入力エラー",
                "日付は YYYY-MM-DD 形式で入力してください。\n例：2025-05-07",
                parent=self
            )
            return

        self.result = {
            "payout_date": self._date_var.get().strip(),
            "qty":         self._qty_var.get(),
            "memo":        self._memo_var.get().strip() or None,
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：在庫チェック記録
# ═══════════════════════════════════════════════════════════════

class StockCheckDialog(tk.Toplevel):
    """
    在庫チェックを記録するダイアログ。

    チェック日（デフォルトは今日）とメモを入力する。
    保存後は self.result に入力内容が格納される（キャンセル時は None）。
    """

    def __init__(self, parent, resident_name):
        super().__init__(parent)
        self.title(f"在庫チェック記録 ― {resident_name}")
        self.result = None
        self.resizable(False, False)
        self._build()
        self.bind("<Return>", lambda e: self._save())
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        pad = dict(padx=14, pady=7)

        tk.Label(
            self, text="在庫を確認した日を記録します", font=FONT_SMALL, fg="#555"
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 4))

        tk.Label(self, text="チェック日", font=FONT).grid(
            row=1, column=0, sticky="e", **pad
        )
        self._date_var = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        tk.Entry(self, textvariable=self._date_var, font=FONT, width=14).grid(
            row=1, column=1, sticky="w", **pad
        )

        tk.Label(self, text="メモ", font=FONT).grid(row=2, column=0, sticky="e", **pad)
        self._memo_var = tk.StringVar()
        tk.Entry(self, textvariable=self._memo_var, font=FONT, width=22).grid(
            row=2, column=1, sticky="w", **pad
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=12)

        tk.Button(
            btn_frame, text="記録する", font=FONT_BOLD,
            bg=C_TEAL, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._save
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _save(self):
        """入力内容を検証して self.result に保存する。"""
        try:
            datetime.strptime(self._date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning(
                "入力エラー",
                "日付は YYYY-MM-DD 形式で入力してください。\n例：2025-05-07",
                parent=self
            )
            return
        self.result = {
            "check_date": self._date_var.get().strip(),
            "memo":       self._memo_var.get().strip() or None,
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ウィンドウ：在庫チェック履歴
# ═══════════════════════════════════════════════════════════════

class StockCheckHistoryWindow(tk.Toplevel):
    """
    利用者ごとの在庫チェックログを一覧表示するウィンドウ。
    チェック日・メモを確認でき、誤って記録した行の削除も行える。
    """

    def __init__(self, parent, resident_id, resident_name):
        super().__init__(parent)
        self.title(f"在庫チェック履歴 ― {resident_name}")
        self.geometry("480x400")
        self.resizable(True, True)
        self._resident_id   = resident_id
        self._resident_name = resident_name
        self._build()
        self._load()
        self.grab_set()
        self.transient(parent)

    def _build(self):
        # ヘッダー行
        top = tk.Frame(self, bg=C_BG, pady=6)
        top.pack(fill="x", padx=10)
        tk.Label(
            top, text=f"{self._resident_name} さんの在庫チェック履歴",
            font=FONT_BOLD, bg=C_BG
        ).pack(side="left")

        # テーブル
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(4, 0))

        cols = ("チェック日", "メモ", "記録日時")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            height=14, selectmode="browse"
        )
        for col, w in zip(cols, [140, 210, 160]):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")
        self._tree.column("メモ", anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self._tree.tag_configure("row_odd",  background=C_ROW_ODD)
        self._tree.tag_configure("row_even", background=C_ROW_EVEN)

        # ボタン行
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=10, pady=8)
        tk.Button(
            btn_frame, text="選択した記録を削除", font=FONT_SMALL,
            bg=C_DANGER, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=10, pady=4, command=self._delete
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_frame, text="閉じる", font=FONT,
            relief="flat", cursor="hand2",
            padx=16, pady=4, command=self.destroy
        ).pack(side="right")

    def _load(self):
        """在庫チェックログをDBから読み込んでテーブルに表示する（新しい順）。"""
        for row in self._tree.get_children():
            self._tree.delete(row)

        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, check_date, memo, created_at
            FROM stock_check_logs
            WHERE resident_id = ?
            ORDER BY check_date DESC, created_at DESC
            """,
            (self._resident_id,)
        ).fetchall()
        conn.close()

        for i, r in enumerate(rows):
            tag = "row_odd" if i % 2 == 0 else "row_even"
            self._tree.insert(
                "", "end",
                iid=str(r["id"]),
                values=(r["check_date"], r["memo"] or "", r["created_at"]),
                tags=(tag,)
            )

    def _delete(self):
        """選択中の在庫チェックログを削除する。"""
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "削除する記録を選択してください。", parent=self)
            return
        if not messagebox.askyesno("削除確認", "選択した在庫チェック記録を削除しますか？", parent=self):
            return
        record_id = int(sel[0])
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("DELETE FROM stock_check_logs WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        self._load()


# ═══════════════════════════════════════════════════════════════
#  ウィンドウ：在庫なし一覧（買い物リスト）
# ═══════════════════════════════════════════════════════════════

class ZeroStockWindow(tk.Toplevel):
    """
    在庫が0の品目を全利用者分まとめて表示するウィンドウ。
    買い出し前の確認・買い物リスト作成に使う。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.title("在庫なし一覧（買い物リスト）")
        self.geometry("480x460")
        self.resizable(True, True)
        self._build()
        self._load()
        self.grab_set()
        self.transient(parent)

    def _build(self):
        # ヘッダー行（タイトル＋更新ボタン）
        top = tk.Frame(self, bg=C_BG, pady=6)
        top.pack(fill="x", padx=10)
        tk.Label(
            top, text="在庫が 0 の品目一覧", font=FONT_BOLD, bg=C_BG
        ).pack(side="left")
        tk.Button(
            top, text="更新", font=FONT_SMALL,
            relief="flat", cursor="hand2", padx=10, pady=3,
            command=self._load
        ).pack(side="right")

        # 件数ラベル
        self._count_var = tk.StringVar()
        tk.Label(
            self, textvariable=self._count_var,
            font=FONT_SMALL, fg="#888", anchor="w"
        ).pack(fill="x", padx=10)

        # テーブル
        cols = ("利用者名", "品目名", "単位")
        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            height=18, selectmode="none"
        )
        for col, w in zip(cols, [160, 220, 70]):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")
        self._tree.column("品目名", anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self._tree.tag_configure("row_odd",  background=C_ROW_ODD)
        self._tree.tag_configure("row_even", background=C_ROW_EVEN)

    def _load(self):
        """在庫なし品目を取得してテーブルに表示する。"""
        for row in self._tree.get_children():
            self._tree.delete(row)

        items = get_zero_stock_items()

        for i, item in enumerate(items):
            tag = "row_odd" if i % 2 == 0 else "row_even"
            self._tree.insert(
                "", "end",
                values=(item["resident_name"], item["item_name"], item["unit"]),
                tags=(tag,)
            )

        count = len(items)
        self._count_var.set(
            f"合計 {count} 品目" if count else "在庫なしの品目はありません"
        )


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：記録の編集（入庫・払い出し共用）
# ═══════════════════════════════════════════════════════════════

class RecordEditDialog(tk.Toplevel):
    """
    入庫記録または払い出し記録を編集するダイアログ。
    日付・数量・メモを変更できる。
    保存後は self.result に変更内容が格納される（キャンセル時は None）。
    """

    def __init__(self, parent, title, record):
        """
        Args:
            title  (str):  ダイアログのタイトル
            record (dict): 編集対象の記録（date, qty, memo を含む辞書）
        """
        super().__init__(parent)
        self.title(title)
        self.result  = None
        self._record = record
        self.resizable(False, False)
        self._build()
        self.bind("<Return>", lambda e: self._save())
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        pad = dict(padx=14, pady=7)

        tk.Label(self, text="日付", font=FONT).grid(row=0, column=0, sticky="e", **pad)
        self._date_var = tk.StringVar(value=self._record["date"])
        tk.Entry(self, textvariable=self._date_var, font=FONT, width=14).grid(
            row=0, column=1, sticky="w", **pad
        )

        tk.Label(self, text="数量", font=FONT).grid(row=1, column=0, sticky="e", **pad)
        self._qty_var = tk.IntVar(value=self._record["qty"])
        tk.Spinbox(
            self, from_=1, to=999, textvariable=self._qty_var, font=FONT, width=8
        ).grid(row=1, column=1, sticky="w", **pad)

        tk.Label(self, text="メモ", font=FONT).grid(row=2, column=0, sticky="e", **pad)
        self._memo_var = tk.StringVar(value=self._record.get("memo") or "")
        tk.Entry(self, textvariable=self._memo_var, font=FONT, width=22).grid(
            row=2, column=1, sticky="w", **pad
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=12)

        tk.Button(
            btn_frame, text="保存", font=FONT_BOLD,
            bg=C_PRIMARY, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=22, pady=6, command=self._save
        ).pack(side="left", padx=6)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", cursor="hand2",
            padx=22, pady=6, command=self.destroy
        ).pack(side="left", padx=6)

    def _save(self):
        """入力内容を検証して self.result に保存する。"""
        try:
            datetime.strptime(self._date_var.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning(
                "入力エラー",
                "日付は YYYY-MM-DD 形式で入力してください。\n例：2025-05-07",
                parent=self
            )
            return
        self.result = {
            "date": self._date_var.get().strip(),
            "qty":  self._qty_var.get(),
            "memo": self._memo_var.get().strip() or None,
        }
        self.destroy()


# ═══════════════════════════════════════════════════════════════
#  ダイアログ：履歴（入庫・払い出し 2タブ）
# ═══════════════════════════════════════════════════════════════

class HistoryDialog(tk.Toplevel):
    """
    入庫記録と払い出し記録を2つのタブで表示するダイアログ。
    記録の編集・削除もここから行う。
    """

    def __init__(self, parent, item_id, item_name):
        super().__init__(parent)
        self.title(f"履歴 ― {item_name}")
        self.geometry("520x420")
        self._item_id = item_id
        self._build()
        self._load_purchase()
        self._load_payout()
        self.grab_set()
        self.transient(parent)
        self.wait_window()

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 入庫タブ
        purchase_tab = tk.Frame(nb)
        nb.add(purchase_tab, text="  入庫記録（購入）  ")
        self._purchase_tree = self._build_tab(
            purchase_tab, self._edit_purchase, self._delete_purchase
        )

        # ── 払い出しタブ
        payout_tab = tk.Frame(nb)
        nb.add(payout_tab, text="  払い出し記録  ")
        self._payout_tree = self._build_tab(
            payout_tab, self._edit_payout, self._delete_payout
        )

        tk.Button(
            self, text="閉じる", font=FONT,
            relief="flat", cursor="hand2",
            padx=16, pady=4, command=self.destroy
        ).pack(pady=(0, 10))

    def _build_tab(self, parent, edit_cmd, delete_cmd):
        """
        タブ内にボタン行とツリーを配置して Treeview を返す。

        tkinter の pack では expand=True のウィジェットより先に
        side="bottom" のウィジェットを配置しないと表示されないため、
        ボタン → ツリー の順で pack する。
        """
        # ① ボタン行を先に bottom で確保する
        btn_frame = tk.Frame(parent)
        btn_frame.pack(side="bottom", fill="x", padx=8, pady=(4, 8))
        tk.Button(
            btn_frame, text="選択した記録を編集", font=FONT_SMALL,
            bg=C_PURPLE, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=10, pady=4, command=edit_cmd
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            btn_frame, text="選択した記録を削除", font=FONT_SMALL,
            bg=C_DANGER, fg=C_BTN_FG, relief="flat", cursor="hand2",
            padx=10, pady=4, command=delete_cmd
        ).pack(side="left")

        # ② ツリーを残りのスペースに配置する
        tree_frame = tk.Frame(parent)
        tree_frame.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 0))

        cols = ("日付", "数量", "メモ")
        tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=10, selectmode="browse"
        )
        for col, w in zip(cols, [150, 80, 250]):
            tree.heading(col, text=col)
            tree.column(col, width=w, anchor="center")
        tree.column("メモ", anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        return tree

    def _fill_tree(self, tree, rows):
        """Treeview の全行を一度クリアしてから rows で再描画する。"""
        for row in tree.get_children():
            tree.delete(row)
        tree.tag_configure("row_odd",  background=C_ROW_ODD)
        tree.tag_configure("row_even", background=C_ROW_EVEN)
        for i, r in enumerate(rows):
            tag = "row_odd" if i % 2 == 0 else "row_even"
            tree.insert(
                "", "end",
                iid=str(r["id"]),
                values=(r["date"], f"{r['qty']}", r["memo"] or ""),
                tags=(tag,)
            )

    def _load_purchase(self):
        """入庫記録を読み込む（日付の新しい順）。"""
        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, purchase_date AS date, qty, memo
            FROM purchase_records
            WHERE item_id = ?
            ORDER BY purchase_date DESC
            """,
            (self._item_id,)
        ).fetchall()
        conn.close()
        self._fill_tree(self._purchase_tree, [dict(r) for r in rows])

    def _load_payout(self):
        """払い出し記録を読み込む（日付の新しい順）。"""
        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, payout_date AS date, qty, memo
            FROM payout_records
            WHERE item_id = ?
            ORDER BY payout_date DESC
            """,
            (self._item_id,)
        ).fetchall()
        conn.close()
        self._fill_tree(self._payout_tree, [dict(r) for r in rows])

    def _get_selected_record(self, tree):
        """
        選択中の行のデータを辞書で返す。
        選択がなければ警告して None を返す。
        """
        sel = tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "編集または削除する記録を選択してください。", parent=self)
            return None, None
        record_id = int(sel[0])
        values    = tree.item(sel[0], "values")
        return record_id, {"date": values[0], "qty": int(values[1]), "memo": values[2] or None}

    def _edit_purchase(self):
        """選択中の入庫記録を編集する。"""
        record_id, record = self._get_selected_record(self._purchase_tree)
        if record_id is None:
            return
        dlg = RecordEditDialog(self, "入庫記録を編集", record)
        if not dlg.result:
            return
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute(
            "UPDATE purchase_records SET purchase_date = ?, qty = ?, memo = ? WHERE id = ?",
            (dlg.result["date"], dlg.result["qty"], dlg.result["memo"], record_id)
        )
        conn.commit()
        conn.close()
        self._load_purchase()

    def _edit_payout(self):
        """選択中の払い出し記録を編集する。"""
        record_id, record = self._get_selected_record(self._payout_tree)
        if record_id is None:
            return
        dlg = RecordEditDialog(self, "払い出し記録を編集", record)
        if not dlg.result:
            return
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute(
            "UPDATE payout_records SET payout_date = ?, qty = ?, memo = ? WHERE id = ?",
            (dlg.result["date"], dlg.result["qty"], dlg.result["memo"], record_id)
        )
        conn.commit()
        conn.close()
        self._load_payout()

    def _delete_purchase(self):
        """選択中の入庫記録を削除する。"""
        record_id, record = self._get_selected_record(self._purchase_tree)
        if record_id is None:
            return
        if not messagebox.askyesno("削除確認", "選択した入庫記録を削除しますか？", parent=self):
            return
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("DELETE FROM purchase_records WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        self._load_purchase()

    def _delete_payout(self):
        """選択中の払い出し記録を削除する。"""
        record_id, record = self._get_selected_record(self._payout_tree)
        if record_id is None:
            return
        if not messagebox.askyesno("削除確認", "選択した払い出し記録を削除しますか？", parent=self):
            return
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("DELETE FROM payout_records WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        self._load_payout()


# ═══════════════════════════════════════════════════════════════
#  メインアプリ
# ═══════════════════════════════════════════════════════════════

class MainApp(tk.Tk):
    """
    利用者日用品管理アプリのメインウィンドウ。

    左パネルに利用者一覧、右パネルに選択中の利用者の品目一覧を表示する。
    品目の追加・削除、入庫（購入）記録、払い出し記録、履歴確認ができる。
    """

    def __init__(self):
        super().__init__()
        self.title("利用者日用品管理")
        self.geometry("1000x620")
        self.configure(bg=C_BG)
        self.resizable(True, True)

        self._selected_resident = None   # 現在選択中の利用者
        self._selected_item_id  = None   # 現在選択中の品目ID

        self._build_ui()
        self._load_residents()

    # ── UI 構築 ──────────────────────────────────────────────

    def _build_ui(self):
        """メイン画面のレイアウトを組み立てる。"""

        # タイトルバー（右端に在庫なし一覧ボタンを配置）
        title_bar = tk.Frame(self, bg=C_PRIMARY, pady=8)
        title_bar.pack(fill="x")
        tk.Label(
            title_bar, text="利用者日用品管理",
            font=FONT_TITLE, bg=C_PRIMARY, fg=C_BTN_FG
        ).pack(side="left", padx=16)
        tk.Button(
            title_bar, text="在庫なし一覧（買い物リスト）",
            font=FONT_SMALL, bg=C_WHITE, fg=C_PRIMARY,
            relief="flat", cursor="hand2", padx=10, pady=4,
            command=self._show_zero_stock
        ).pack(side="right", padx=12)

        # メインコンテンツ（左＋右）
        content = tk.Frame(self, bg=C_BG)
        content.pack(fill="both", expand=True, padx=10, pady=10)

        # ── 左パネル：利用者リスト ──────────────────────────
        left = tk.Frame(content, bg=C_WHITE, bd=1, relief="solid", width=180)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(
            left, text="利用者", font=FONT_BOLD, bg=C_BG, pady=6
        ).pack(fill="x")

        self._resident_lb = tk.Listbox(
            left, font=FONT,
            selectbackground=C_SELECTED, selectforeground="#000",
            relief="flat", activestyle="none", cursor="hand2"
        )
        self._resident_lb.pack(fill="both", expand=True)
        self._resident_lb.bind("<<ListboxSelect>>", self._on_resident_select)

        # ── 右パネル：品目管理 ──────────────────────────────
        right = tk.Frame(content, bg=C_BG)
        right.pack(side="left", fill="both", expand=True)

        # 選択中の利用者名を表示するラベル
        self._resident_label = tk.Label(
            right, text="← 利用者を選択してください",
            font=FONT_BOLD, bg=C_BG, fg="#777", anchor="w"
        )
        self._resident_label.pack(fill="x", pady=(0, 2))

        # 最終チェック日を表示するサブラベル
        self._last_check_var = tk.StringVar(value="")
        tk.Label(
            right, textvariable=self._last_check_var,
            font=FONT_SMALL, fg="#148F77", bg=C_BG, anchor="w"
        ).pack(fill="x", pady=(0, 4))

        # ── ボタンエリア：「品目」グループと「記録」グループに分けて配置
        btn_area = tk.Frame(right, bg=C_BG)
        btn_area.pack(fill="x", pady=(0, 8))

        def btn(parent, text, color, cmd):
            return tk.Button(
                parent, text=text, font=FONT,
                bg=color, fg=C_BTN_FG, relief="flat",
                cursor="hand2", padx=10, pady=5, command=cmd
            )

        # 【品目】グループ：品目の追加・変更・削除
        item_group = tk.LabelFrame(
            btn_area, text="品目", font=FONT_SMALL,
            bg=C_BG, padx=6, pady=4
        )
        item_group.pack(side="left", padx=(0, 12))

        self._btn_add  = btn(item_group, "＋ 追加",  C_PRIMARY, self._add_item)
        self._btn_edit = btn(item_group, "変更",     C_PURPLE,  self._edit_item)
        self._btn_del  = btn(item_group, "削除",     C_DANGER,  self._delete_item)
        for b in (self._btn_add, self._btn_edit, self._btn_del):
            b.pack(side="left", padx=3)

        # 【記録】グループ：入庫・払い出し・履歴
        record_group = tk.LabelFrame(
            btn_area, text="記録", font=FONT_SMALL,
            bg=C_BG, padx=6, pady=4
        )
        record_group.pack(side="left", padx=(0, 12))

        self._btn_purchase = btn(record_group, "入庫（購入）",  C_GREEN,  self._record_purchase)
        self._btn_payout   = btn(record_group, "払い出し",      C_ORANGE, self._record_payout)
        self._btn_hist     = btn(record_group, "履歴を見る",    C_GRAY2,  self._show_history)
        for b in (self._btn_purchase, self._btn_payout, self._btn_hist):
            b.pack(side="left", padx=3)

        # 【チェック】グループ：在庫チェックの記録・履歴
        check_group = tk.LabelFrame(
            btn_area, text="在庫チェック", font=FONT_SMALL,
            bg=C_BG, padx=6, pady=4
        )
        check_group.pack(side="left")

        self._btn_check      = btn(check_group, "チェック記録",  C_TEAL,  self._record_stock_check)
        self._btn_check_hist = btn(check_group, "チェック履歴",  C_GRAY2, self._show_check_history)
        for b in (self._btn_check, self._btn_check_hist):
            b.pack(side="left", padx=3)

        # ── 品目テーブル
        tree_frame = tk.Frame(right, bg=C_BG)
        tree_frame.pack(fill="both", expand=True)

        cols = ("品目名", "在庫数", "最終払い出し日", "払い出しスパン（日）")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            height=18, selectmode="browse"
        )
        for col, w in zip(cols, [220, 90, 150, 170]):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")
        self._tree.column("品目名", anchor="w")

        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        self._tree.bind("<<TreeviewSelect>>", self._on_item_select)

        # タグ設定（在庫0の行は赤系、通常行は白／薄青の交互）
        self._tree.tag_configure("row_zero", background=C_ZERO_BG, foreground=C_ZERO_FG)
        self._tree.tag_configure("row_odd",  background=C_ROW_ODD)
        self._tree.tag_configure("row_even", background=C_ROW_EVEN)

        # ステータスバー
        self._status_var = tk.StringVar(value="起動完了")
        tk.Label(
            self, textvariable=self._status_var,
            font=FONT_SMALL, bg="#DDD", anchor="w", padx=8, pady=3
        ).pack(fill="x", side="bottom")

    # ── データ読み込み ────────────────────────────────────────

    def _load_residents(self):
        """residents.db から入居中の利用者を読み込んでリストボックスに表示する。"""
        self._residents = get_residents()
        self._resident_lb.delete(0, "end")
        for r in self._residents:
            self._resident_lb.insert("end", r["name"])

        if not self._residents:
            self._status_var.set(
                "利用者データが見つかりません。residents.db の場所を確認してください。"
            )

    def _on_resident_select(self, _event):
        """利用者リストの選択が変わったとき品目一覧を更新する。"""
        sel = self._resident_lb.curselection()
        if not sel:
            return
        self._selected_resident = self._residents[sel[0]]
        self._selected_item_id  = None
        self._resident_label.config(
            text=f"▶ {self._selected_resident['name']} さんの日用品"
        )
        self._refresh_last_check()
        self._load_items()

    def _load_items(self):
        """選択中の利用者の品目一覧を取得してテーブルに表示する。"""
        if not self._selected_resident:
            return

        for row in self._tree.get_children():
            self._tree.delete(row)

        items      = get_items_with_span(self._selected_resident["id"])
        zero_count = 0

        for i, item in enumerate(items):
            qty_text    = f"{item['current_qty']} {item['unit']}"
            last_payout = item["last_payout"] or "記録なし"

            if item["avg_span"] is not None:
                span_text = f"約 {item['avg_span']} 日"
            elif item["last_payout"]:
                span_text = "記録 1 件"   # 2件以上ないと計算不可
            else:
                span_text = "―"

            if item["current_qty"] == 0:
                tag = "row_zero"
                zero_count += 1
            elif i % 2 == 0:
                tag = "row_odd"
            else:
                tag = "row_even"

            self._tree.insert(
                "", "end",
                iid=str(item["id"]),
                values=(item["item_name"], qty_text, last_payout, span_text),
                tags=(tag,)
            )

        total = len(items)
        msg   = f"{self._selected_resident['name']} さん：{total} 品目"
        if zero_count:
            msg += f"　⚠ 在庫なし {zero_count} 品目"
        self._status_var.set(msg)

    def _on_item_select(self, _event):
        """品目テーブルの選択が変わったとき品目IDを保持する。"""
        sel = self._tree.selection()
        self._selected_item_id = int(sel[0]) if sel else None

    # ── ガード関数 ────────────────────────────────────────────

    def _require_resident(self):
        """利用者が選択されていない場合に警告して False を返す。"""
        if not self._selected_resident:
            messagebox.showwarning("選択なし", "先に利用者を選択してください。")
            return False
        return True

    def _require_item(self):
        """品目が選択されていない場合に警告して False を返す。"""
        if not self._selected_item_id:
            messagebox.showwarning("選択なし", "先に品目を選択してください。")
            return False
        return True

    def _fetch_item(self):
        """
        現在選択中の品目を DB から取得する。

        Returns:
            dict または None
        """
        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, item_name, unit, current_qty, memo FROM items WHERE id = ?",
            (self._selected_item_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ── 操作：品目追加 ───────────────────────────────────────

    def _add_item(self):
        """新しい品目を利用者に追加する。"""
        if not self._require_resident():
            return

        dlg = ItemDialog(self, title="品目追加")
        if not dlg.result:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute(
            """
            INSERT INTO items
                (resident_id, item_name, unit, current_qty, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._selected_resident["id"],
                dlg.result["item_name"],
                dlg.result["unit"],
                dlg.result["current_qty"],
                dlg.result["memo"],
                now, now,
            )
        )
        conn.commit()
        conn.close()
        self._load_items()
        self._status_var.set(f"「{dlg.result['item_name']}」を追加しました")

    # ── 操作：入庫記録（購入） ───────────────────────────────

    def _record_purchase(self):
        """
        選択中の品目に入庫（購入）を記録する。
        品目が未選択の場合は先に品目選択ダイアログを表示する。
        在庫数は購入数分だけ自動で増える。
        """
        if not self._require_resident():
            return

        # 品目が選択済みならそのまま取得、未選択なら選択ダイアログを出す
        if self._selected_item_id:
            item = self._fetch_item()
        else:
            sel_dlg = ItemSelectDialog(
                self, self._selected_resident["id"], self._selected_resident["name"],
                title="入庫する品目を選択"
            )
            if not sel_dlg.result:
                return
            item = sel_dlg.result

        if not item:
            return

        dlg = PurchaseDialog(self, item["item_name"], item["unit"])
        if not dlg.result:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_qty = item["current_qty"] + dlg.result["qty"]

        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("PRAGMA foreign_keys = ON")

        # 入庫記録を保存
        conn.execute(
            """
            INSERT INTO purchase_records (item_id, purchase_date, qty, memo, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                dlg.result["purchase_date"],
                dlg.result["qty"],
                dlg.result["memo"],
                now,
            )
        )
        # 在庫数を更新（現在の数量 ＋ 購入数）
        conn.execute(
            "UPDATE items SET current_qty = ?, updated_at = ? WHERE id = ?",
            (new_qty, now, item["id"])
        )
        conn.commit()
        conn.close()

        self._load_items()
        self._status_var.set(
            f"「{item['item_name']}」を {dlg.result['qty']} {item['unit']} 入庫しました"
            f"（在庫：{item['current_qty']} → {new_qty} {item['unit']}）"
        )

    # ── 操作：払い出し記録 ───────────────────────────────────

    def _record_payout(self):
        """
        選択中の品目に払い出しを記録する。
        品目が未選択の場合は先に品目選択ダイアログを表示する。
        在庫数は払い出し数分だけ自動で減る。
        """
        if not self._require_resident():
            return

        # 品目が選択済みならそのまま取得、未選択なら選択ダイアログを出す
        if self._selected_item_id:
            item = self._fetch_item()
        else:
            sel_dlg = ItemSelectDialog(
                self, self._selected_resident["id"], self._selected_resident["name"],
                title="払い出しする品目を選択"
            )
            if not sel_dlg.result:
                return
            item = sel_dlg.result

        if not item:
            return

        dlg = PayoutDialog(self, item["item_name"], item["unit"])
        if not dlg.result:
            return

        # 在庫数を払い出し数分だけ引く（0未満にはならないよう下限を0にする）
        new_qty = max(0, item["current_qty"] - dlg.result["qty"])

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute(
            """
            INSERT INTO payout_records (item_id, payout_date, qty, memo, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item["id"],
                dlg.result["payout_date"],
                dlg.result["qty"],
                dlg.result["memo"],
                now,
            )
        )
        # 在庫数を自動更新（現在の数量 － 払い出し数）
        conn.execute(
            "UPDATE items SET current_qty = ?, updated_at = ? WHERE id = ?",
            (new_qty, now, item["id"])
        )
        conn.commit()
        conn.close()

        self._load_items()
        self._status_var.set(
            f"「{item['item_name']}」を {dlg.result['qty']} {item['unit']} 払い出しました"
            f"（在庫：{item['current_qty']} → {new_qty} {item['unit']}）"
        )

    # ── 操作：数量・情報変更 ─────────────────────────────────

    def _edit_item(self):
        """選択中の品目の名前・単位・数量・メモを直接編集する。"""
        if not self._require_resident() or not self._require_item():
            return

        item = self._fetch_item()
        if not item:
            return

        dlg = ItemDialog(self, title=f"情報変更 ― {item['item_name']}", item=item)
        if not dlg.result:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(ITEMS_DB)
        conn.execute(
            """
            UPDATE items
            SET item_name = ?, unit = ?, current_qty = ?, memo = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                dlg.result["item_name"],
                dlg.result["unit"],
                dlg.result["current_qty"],
                dlg.result["memo"],
                now,
                self._selected_item_id,
            )
        )
        conn.commit()
        conn.close()
        self._load_items()
        self._status_var.set(f"「{dlg.result['item_name']}」の情報を更新しました")

    # ── 操作：履歴 ───────────────────────────────────────────

    def _show_history(self):
        """
        選択中の品目の入庫・払い出し履歴ダイアログを開く。
        品目が未選択の場合は先に品目選択ダイアログを表示する。
        """
        if not self._require_resident():
            return

        # 品目が選択済みならそのまま取得、未選択なら選択ダイアログを出す
        if self._selected_item_id:
            item = self._fetch_item()
        else:
            sel_dlg = ItemSelectDialog(
                self, self._selected_resident["id"], self._selected_resident["name"],
                title="履歴を見る品目を選択"
            )
            if not sel_dlg.result:
                return
            item = sel_dlg.result

        if not item:
            return

        HistoryDialog(self, item["id"], item["item_name"])
        # 履歴削除後にスパン表示を更新するため再読み込み
        self._load_items()

    # ── 操作：品目削除 ───────────────────────────────────────

    def _delete_item(self):
        """選択中の品目と入庫・払い出し履歴をすべて削除する。"""
        if not self._require_resident() or not self._require_item():
            return

        item = self._fetch_item()
        if not item:
            return

        if not messagebox.askyesno(
            "削除確認",
            f"「{item['item_name']}」と入庫・払い出しの全履歴を削除します。\n"
            "この操作は元に戻せません。続けますか？"
        ):
            return

        conn = sqlite3.connect(ITEMS_DB)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM items WHERE id = ?", (self._selected_item_id,))
        conn.commit()
        conn.close()

        self._selected_item_id = None
        self._load_items()
        self._status_var.set(f"「{item['item_name']}」を削除しました")


    # ── 操作：在庫なし一覧 ──────────────────────────────────

    def _show_zero_stock(self):
        """在庫なし一覧ウィンドウを開く。"""
        ZeroStockWindow(self)

    # ── 操作：在庫チェック記録 ──────────────────────────────

    def _refresh_last_check(self):
        """
        選択中の利用者の最終チェック日をDBから読み込み、
        画面上部のラベルに表示する。
        """
        if not self._selected_resident:
            self._last_check_var.set("")
            return

        conn = sqlite3.connect(ITEMS_DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT check_date FROM stock_check_logs
            WHERE resident_id = ?
            ORDER BY check_date DESC, created_at DESC
            LIMIT 1
            """,
            (self._selected_resident["id"],)
        ).fetchone()
        conn.close()

        if row:
            self._last_check_var.set(f"✓ 最終チェック日：{row['check_date']}")
        else:
            self._last_check_var.set("（在庫チェックの記録なし）")

    def _record_stock_check(self):
        """在庫チェックを行った日をログとして記録する。ダイアログなしで本日の日付を即記録する。"""
        if not self._require_resident():
            return

        today = date.today().strftime("%Y-%m-%d")
        now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn  = sqlite3.connect(ITEMS_DB)
        conn.execute(
            """
            INSERT INTO stock_check_logs (resident_id, check_date, memo, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (self._selected_resident["id"], today, None, now)
        )
        conn.commit()
        conn.close()

        self._refresh_last_check()
        self._status_var.set(
            f"{self._selected_resident['name']} さん：{today} の在庫チェックを記録しました"
        )

    def _show_check_history(self):
        """在庫チェックの履歴ウィンドウを開く。"""
        if not self._require_resident():
            return

        StockCheckHistoryWindow(
            self,
            self._selected_resident["id"],
            self._selected_resident["name"],
        )
        # 削除操作があった場合に最終チェック日表示を更新する
        self._refresh_last_check()


# ═══════════════════════════════════════════════════════════════
#  エントリーポイント
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_dirs()   # 必要なフォルダを作成
    backup_db()   # DB をバックアップ
    init_db()     # テーブルを初期化（初回のみ作成）
    app = MainApp()
    app.mainloop()
