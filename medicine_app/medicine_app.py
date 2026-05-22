# =============================================================================
# お薬在庫管理アプリ
# グループホーム 入居者別お薬在庫管理システム
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
from datetime import datetime, date, timedelta

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "medicine_backups")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
MEDICINE_DB  = os.path.join(DATA_DIR, "medicine.db")
VISIT_DB     = os.path.join(DATA_DIR, "visits.db")
MAX_BACKUPS  = 10

TIME_SLOTS = ["朝", "昼", "夕", "寝る前"]

# 各時間帯の服薬時刻（この時刻を過ぎたら当日分を消費済みとみなす）
SLOT_TIMES = {
    "朝":    "07:00",
    "昼":    "12:00",
    "夕":    "19:00",
    "寝る前": "21:00",
}

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 色設定
COLOR_BG        = "#F5F7FA"
COLOR_HEADER    = "#4A6FA5"
COLOR_HEADER_FG = "#FFFFFF"
COLOR_ROW_ODD   = "#FFFFFF"
COLOR_ROW_EVEN  = "#F0F4FA"
COLOR_ACCENT    = "#4A6FA5"
COLOR_WARN      = "#E74C3C"
COLOR_BTN       = "#4A6FA5"
COLOR_BTN_FG    = "#FFFFFF"

# =============================================================================
# 初期セットアップ
# =============================================================================

def setup():
    """アプリ起動時にフォルダとDBを準備する"""
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    _migrate_db()
    _backup_db()


def _migrate_db():
    """
    medicine.db のテーブルを作成・マイグレーションする。
    旧バージョン（stock_pillsカラム）から新バージョン（stock_daysカラム）への
    移行も自動で行う。
    """
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()

    # 時間帯設定テーブル（入居者ごとの朝/昼/夕/寝る前のON/OFF）
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicine_settings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            time_slot   TEXT    NOT NULL,
            enabled     INTEGER DEFAULT 0,
            dose_count  INTEGER DEFAULT 1,
            UNIQUE(resident_id, time_slot)
        )
    """)

    # 在庫テーブル（カレンダー日数＋残薬ストック日数で管理）
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicine_inventory (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id   INTEGER NOT NULL,
            time_slot     TEXT    NOT NULL,
            calendar_days INTEGER DEFAULT 0,
            stock_days    INTEGER DEFAULT 0,
            updated_at    TEXT,
            UNIQUE(resident_id, time_slot)
        )
    """)

    # stock_pills カラムが残っていれば stock_days へ移行して削除
    c.execute("PRAGMA table_info(medicine_inventory)")
    cols = [row[1] for row in c.fetchall()]
    if "stock_pills" in cols and "stock_days" not in cols:
        # dose_countを使って日数に換算する（旧データ移行）
        try:
            c.execute("ALTER TABLE medicine_inventory ADD COLUMN stock_days INTEGER DEFAULT 0")
            c.execute("""
                UPDATE medicine_inventory SET stock_days = (
                    SELECT CASE WHEN ms.dose_count > 0
                                THEN mi2.stock_pills / ms.dose_count
                                ELSE 0 END
                    FROM medicine_settings ms, medicine_inventory mi2
                    WHERE ms.resident_id = medicine_inventory.resident_id
                      AND ms.time_slot   = medicine_inventory.time_slot
                      AND mi2.id         = medicine_inventory.id
                )
            """)
        except Exception as e:
            conn.rollback()
            conn.close()
            from tkinter import messagebox
            messagebox.showerror(
                "データ移行エラー",
                f"お薬在庫データの形式更新に失敗しました。\n"
                f"データは変更されていません。\n\n"
                f"エラー内容: {e}")
            return

    # 操作履歴テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS medicine_history (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id    INTEGER NOT NULL,
            time_slot      TEXT    NOT NULL,
            operation_type TEXT    NOT NULL,
            quantity       INTEGER NOT NULL,
            note           TEXT    DEFAULT '',
            created_at     TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 操作前の在庫値を保持するカラムを追加（履歴削除時に元の値へ戻すために使用）
    c.execute("PRAGMA table_info(medicine_history)")
    hist_cols = [row[1] for row in c.fetchall()]
    if "prev_cal" not in hist_cols:
        c.execute("ALTER TABLE medicine_history ADD COLUMN prev_cal INTEGER DEFAULT NULL")
    if "prev_stk" not in hist_cols:
        c.execute("ALTER TABLE medicine_history ADD COLUMN prev_stk INTEGER DEFAULT NULL")

    conn.commit()
    conn.close()


def _backup_db():
    """起動時に medicine.db をバックアップする（最大10個保持）"""
    if not os.path.exists(MEDICINE_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(MEDICINE_DB, backup_path)

    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


# =============================================================================
# DB操作ヘルパー
# =============================================================================

def get_residents():
    """residents.db から入居中の入居者一覧を取得する"""
    if not os.path.exists(RESIDENTS_DB):
        messagebox.showerror("エラー", f"入居者マスターDBが見つかりません。\n{RESIDENTS_DB}")
        return []
    try:
        conn = sqlite3.connect(RESIDENTS_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id")
        rows = c.fetchall()
        conn.close()
        return [(r["id"], r["name"]) for r in rows]
    except Exception as e:
        messagebox.showerror("エラー", f"入居者情報の読み込みに失敗しました。\n{e}")
        return []


def get_settings(resident_id):
    """
    入居者の時間帯設定を取得する。
    DBに登録がない時間帯はデフォルト値（無効）で返す。
    """
    conn = sqlite3.connect(MEDICINE_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT time_slot, enabled, dose_count
        FROM medicine_settings WHERE resident_id = ?
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()

    db_s = {r["time_slot"]: dict(r) for r in rows}
    return {
        slot: db_s.get(slot, {"time_slot": slot, "enabled": 0, "dose_count": 1})
        for slot in TIME_SLOTS
    }


def save_settings(resident_id, settings):
    """入居者の時間帯設定を保存する（UPSERT）"""
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    for slot, s in settings.items():
        c.execute("""
            INSERT INTO medicine_settings (resident_id, time_slot, enabled, dose_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(resident_id, time_slot) DO UPDATE SET
                enabled    = excluded.enabled,
                dose_count = excluded.dose_count
        """, (resident_id, slot, s["enabled"], s["dose_count"]))
    conn.commit()
    conn.close()


def get_inventory(resident_id):
    """入居者の在庫状況を全時間帯分取得する"""
    conn = sqlite3.connect(MEDICINE_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT time_slot, calendar_days, stock_days, updated_at
        FROM medicine_inventory WHERE resident_id = ?
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()

    db_inv = {r["time_slot"]: dict(r) for r in rows}
    return {
        slot: db_inv.get(slot, {
            "time_slot": slot, "calendar_days": 0,
            "stock_days": 0, "updated_at": None
        })
        for slot in TIME_SLOTS
    }


def save_inventory(resident_id, time_slot, calendar_days, stock_days):
    """指定時間帯の在庫を保存する（UPSERT）"""
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
        INSERT INTO medicine_inventory
            (resident_id, time_slot, calendar_days, stock_days, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(resident_id, time_slot) DO UPDATE SET
            calendar_days = excluded.calendar_days,
            stock_days    = excluded.stock_days,
            updated_at    = excluded.updated_at
    """, (resident_id, time_slot, calendar_days, stock_days, now))
    conn.commit()
    conn.close()


def add_history(resident_id, time_slot, operation_type, quantity, note="",
                prev_cal=None, prev_stk=None):
    """
    操作履歴を追加する。
    prev_cal / prev_stk に操作前の在庫値を渡すと、
    履歴削除時にその値へ戻せるようになる。
    """
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO medicine_history
            (resident_id, time_slot, operation_type, quantity, note, prev_cal, prev_stk)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (resident_id, time_slot, operation_type, quantity, note, prev_cal, prev_stk))
    conn.commit()
    conn.close()


def get_history(resident_id, limit=15):
    """操作履歴をIDつきで新しい順に取得する"""
    conn = sqlite3.connect(MEDICINE_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, time_slot, operation_type, quantity, note, created_at,
               prev_cal, prev_stk
        FROM medicine_history
        WHERE resident_id = ?
        ORDER BY id DESC LIMIT ?
    """, (resident_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def update_history(history_id, time_slot, operation_type, quantity, note, created_at):
    """操作履歴を1件修正する"""
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    c.execute("""
        UPDATE medicine_history
        SET time_slot = ?, operation_type = ?, quantity = ?, note = ?, created_at = ?
        WHERE id = ?
    """, (time_slot, operation_type, quantity, note, created_at, history_id))
    conn.commit()
    conn.close()


def delete_history(history_id):
    """
    操作履歴を1件削除し、操作前の在庫値が記録されていれば在庫を元の値に戻す。
    戻り値: True = 在庫も復元した / False = 履歴のみ削除（復元できなかった）
    """
    conn = sqlite3.connect(MEDICINE_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM medicine_history WHERE id = ?", (history_id,))
    row = c.fetchone()

    reverted = False
    if row and row["prev_cal"] is not None and row["prev_stk"] is not None:
        # 操作前の値が記録されている → 在庫を元に戻す
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO medicine_inventory
                (resident_id, time_slot, calendar_days, stock_days, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(resident_id, time_slot) DO UPDATE SET
                calendar_days = excluded.calendar_days,
                stock_days    = excluded.stock_days,
                updated_at    = excluded.updated_at
        """, (row["resident_id"], row["time_slot"],
              row["prev_cal"], row["prev_stk"], now))
        reverted = True

    c.execute("DELETE FROM medicine_history WHERE id = ?", (history_id,))
    conn.commit()
    conn.close()
    return reverted


def get_active_temp_medicines(resident_id):
    """
    入居者の現在服薬中の臨時薬一覧を visits.db から取得する。
    各病院の「直近の臨時薬記録」から薬名別にグループ化して返す。
    いずれかのスロットの終了日が過去7日以内または未来のものを返す。

    戻り値: [{"hospital": str, "visit_date": str,
              "medicines": [{"name": str, "slots": {slot: {"days": N, "start_date": str}}}, ...]}, ...]
    """
    if not os.path.exists(VISIT_DB):
        return []

    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 病院ごとに最新の臨時薬記録を1件ずつ取得する
    c.execute("""
        SELECT v.id, v.visit_date, h.name AS hospital_name
        FROM visits v
        JOIN hospitals h ON v.hospital_id = h.id
        WHERE v.resident_id = ?
          AND v.temp_medicine IS NOT NULL AND v.temp_medicine != ''
          AND v.id IN (
              SELECT MAX(id) FROM visits
              WHERE resident_id = ?
                AND temp_medicine IS NOT NULL AND temp_medicine != ''
              GROUP BY hospital_id
          )
        ORDER BY v.visit_date DESC
    """, (resident_id, resident_id))
    rows = c.fetchall()

    result = []
    today = date.today()

    for row in rows:
        # 時間帯ごとの臨時薬行を取得（is_temp=1 の行、挿入順を維持）
        c.execute("""
            SELECT medicine_name, time_slot, days_prescribed, start_date
            FROM visit_prescriptions
            WHERE visit_id = ? AND is_temp = 1
            ORDER BY ROWID
        """, (row["id"],))
        presc_rows = c.fetchall()

        # 薬名ごとにグループ化（挿入順を保持）
        med_dict = {}
        order = []
        for pr in presc_rows:
            name = pr["medicine_name"] or ""
            if name not in med_dict:
                med_dict[name] = {}
                order.append(name)
            med_dict[name][pr["time_slot"]] = {
                "days": pr["days_prescribed"],
                "start_date": pr["start_date"],
            }
        medicines = [{"name": n, "slots": med_dict[n]} for n in order]

        if not medicines:
            continue

        # いずれかのスロットが8日以内に終了する（または未終了）かチェック
        max_remaining = None
        for med in medicines:
            for sd in med["slots"].values():
                if sd["days"] <= 0:
                    continue
                start_str = sd.get("start_date") or row["visit_date"]
                try:
                    start = date.fromisoformat(start_str)
                    rem = (start + timedelta(days=sd["days"] - 1) - today).days
                    if max_remaining is None or rem > max_remaining:
                        max_remaining = rem
                except ValueError:
                    continue

        # すべてのスロットの終了日が8日以上前なら表示しない
        if max_remaining is None or max_remaining < -7:
            continue

        result.append({
            "hospital":   row["hospital_name"],
            "visit_date": row["visit_date"],
            "medicines":  medicines,
        })

    conn.close()
    return result


def count_consumed_since(updated_at_str, slot):
    """
    updated_at から現時点までに、指定時間帯の服薬時刻を何回通過したかを返す。
    これがカレンダー日数の自動補正値になる。

    例：月曜10:00に記録、火曜14:00に参照（朝=07:00）の場合
        →「火曜07:00」を1回通過 → 1 を返す
    """
    if not updated_at_str or slot not in SLOT_TIMES:
        return 0
    try:
        updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0

    time_str = SLOT_TIMES[slot]
    h, m = int(time_str[:2]), int(time_str[3:])
    now = datetime.now()

    # 更新日当日の服薬時刻を起点にする
    consume_dt = updated_at.replace(hour=h, minute=m, second=0, microsecond=0)
    # 更新時刻より前（または同時）なら翌日の服薬時刻から数える
    if consume_dt <= updated_at:
        consume_dt += timedelta(days=1)

    if consume_dt > now:
        return 0

    # 最初の消費時刻から現在まで何日経過したか（1日＝1回消費）
    return (now - consume_dt).days + 1


def slot_consumed_today(slot):
    """
    今日の指定時間帯の服薬時刻が現時点で過ぎているかを返す。
    過ぎていれば「今日の分はもう飲んだ」とみなす。
    """
    if slot not in SLOT_TIMES:
        return False
    h, m = int(SLOT_TIMES[slot][:2]), int(SLOT_TIMES[slot][3:])
    now = datetime.now()
    return (now.hour, now.minute) >= (h, m)


def calc_available_until(total_days, today_consumed=False):
    """
    残り日数から「いつまであるか」の日付文字列を返す。
    today_consumed=True のとき（服薬時刻が過ぎている）は
    今日を含まず翌日から数えるため、offset を1日多くする。
    """
    if total_days <= 0:
        return "なし"
    offset = total_days if today_consumed else total_days - 1
    target = date.today() + timedelta(days=offset)
    return target.strftime("%m月%d日")


# =============================================================================
# 設定ダイアログ
# =============================================================================

class SettingsDialog(tk.Toplevel):
    """入居者ごとの時間帯設定（ON/OFF）を編集するダイアログ"""

    def __init__(self, parent, resident_id, resident_name):
        super().__init__(parent)
        self.title(f"薬の設定 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id = resident_id
        self.settings    = get_settings(resident_id)
        self.enabled_vars = {}

        self._build_ui()
        self._center(parent)

    def _build_ui(self):
        tk.Label(self, text="有効な時間帯を選択してください",
                 font=FONT_BOLD).grid(row=0, column=0, columnspan=2,
                                       padx=16, pady=(12, 6), sticky="w")

        for i, slot in enumerate(TIME_SLOTS):
            var = tk.BooleanVar(value=bool(self.settings[slot]["enabled"]))
            self.enabled_vars[slot] = var
            tk.Checkbutton(self, text=slot, variable=var, font=FONT).grid(
                row=i+1, column=0, padx=24, pady=4, sticky="w")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=len(TIME_SLOTS)+1, column=0, pady=12)
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

    def _save(self):
        new_settings = {
            slot: {"enabled": int(var.get()), "dose_count": 1}
            for slot, var in self.enabled_vars.items()
        }
        save_settings(self.resident_id, new_settings)
        messagebox.showinfo("保存完了", "設定を保存しました。", parent=self)
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 補充ダイアログ（一括・個別の切り替え対応）
# =============================================================================

class RefillDialog(tk.Toplevel):
    """
    カレンダーへの補充ダイアログ。
    「一括」モード：全時間帯に同じ日数をまとめて補充する（通常の補充）。
    「個別」モード：時間帯を指定して補充する（臨時対応）。
    """

    def __init__(self, parent, resident_id, resident_name, settings, inventory, on_done):
        super().__init__(parent)
        self.title(f"補充 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id  = resident_id
        self.settings     = settings
        self.inventory    = inventory
        self.on_done      = on_done
        self.active_slots = [s for s in TIME_SLOTS if settings[s]["enabled"]]

        # 一括用
        self.mode_var     = tk.StringVar(value="bulk")
        self.bulk_qty_var = tk.StringVar(value="1")

        # 個別用
        self.slot_var      = tk.StringVar()
        self.single_qty_var = tk.StringVar(value="")
        self.info_var      = tk.StringVar()

        self._build_ui()
        self._center(parent)
        if self.active_slots:
            self.slot_var.set(self.active_slots[0])
            self._update_info()

    def _build_ui(self):
        tk.Label(self, text="カレンダーへの補充", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(12, 2), sticky="w")
        tk.Label(self, text="残薬ボックスからカレンダーに補充します。",
                 font=FONT_SMALL, fg="#666666").grid(
            row=1, column=0, columnspan=2, padx=16, sticky="w")

        # 一括 / 個別 切り替え
        mode_frame = tk.Frame(self)
        mode_frame.grid(row=2, column=0, columnspan=2,
                        padx=16, pady=(10, 2), sticky="w")
        tk.Radiobutton(mode_frame, text="一括（全時間帯）",
                       variable=self.mode_var, value="bulk",
                       font=FONT, command=self._on_mode_change).pack(
            side="left", padx=(0, 20))
        tk.Radiobutton(mode_frame, text="個別（時間帯を選ぶ）",
                       variable=self.mode_var, value="single",
                       font=FONT, command=self._on_mode_change).pack(side="left")

        ttk.Separator(self, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=6)

        # 一括入力エリア（初期表示）
        self.bulk_frame = tk.Frame(self)
        self._build_bulk_area()

        # 個別入力エリア（初期は非表示）
        self.single_frame = tk.Frame(self)
        self._build_single_area()

        # ボタン
        btn_frame = tk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="補充する", font=FONT_BOLD,
                  bg="#27AE60", fg="white", relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._execute).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

        self._on_mode_change()

    def _build_bulk_area(self):
        """一括補充エリア：全時間帯の現状を一覧表示し、共通の補充日数を入力する"""
        qty_row = tk.Frame(self.bulk_frame)
        qty_row.pack(fill="x", pady=(0, 8))
        tk.Label(qty_row, text="補充する日数（全時間帯共通）：",
                 font=FONT).pack(side="left")
        tk.Entry(qty_row, textvariable=self.bulk_qty_var,
                 width=5, font=FONT).pack(side="left", padx=8)
        tk.Label(qty_row, text="日分", font=FONT).pack(side="left")

        # 在庫状況一覧ヘッダー
        tbl = tk.Frame(self.bulk_frame)
        tbl.pack(fill="x")
        for col, (h, w) in enumerate([("時間帯", 8), ("カレンダー", 12), ("残薬ボックス", 12)]):
            tk.Label(tbl, text=h, font=FONT_SMALL, bg="#E0E4EA",
                     width=w, anchor="center", relief="flat", pady=3).grid(
                row=0, column=col, padx=1, pady=(0, 1), sticky="ew")

        for i, slot in enumerate(self.active_slots):
            inv = self.inventory[slot]
            bg  = COLOR_ROW_ODD if i % 2 == 0 else COLOR_ROW_EVEN
            for col, (text, w) in enumerate([
                (slot,                          8),
                (f"{inv['calendar_days']}日分", 12),
                (f"{inv['stock_days']}日分",    12),
            ]):
                tk.Label(tbl, text=text, font=FONT_SMALL, bg=bg,
                         width=w, anchor="center", relief="flat", pady=3).grid(
                    row=i + 1, column=col, padx=1, pady=1, sticky="ew")

    def _build_single_area(self):
        """個別補充エリア：時間帯を選んで日数を入力する"""
        tk.Label(self.single_frame, text="時間帯：", font=FONT).grid(
            row=0, column=0, pady=6, sticky="e")
        cb = ttk.Combobox(self.single_frame, textvariable=self.slot_var,
                          values=self.active_slots, state="readonly",
                          width=10, font=FONT)
        cb.grid(row=0, column=1, padx=(8, 0), pady=6, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._update_info())

        tk.Label(self.single_frame, text="補充する日数：", font=FONT).grid(
            row=1, column=0, pady=6, sticky="e")
        tk.Entry(self.single_frame, textvariable=self.single_qty_var,
                 width=6, font=FONT).grid(row=1, column=1, padx=(8, 0), pady=6, sticky="w")

        tk.Label(self.single_frame, textvariable=self.info_var,
                 font=FONT_SMALL, fg="#666666").grid(
            row=2, column=0, columnspan=2, pady=4, sticky="w")

    def _on_mode_change(self):
        """一括 / 個別モードの表示を切り替える"""
        if self.mode_var.get() == "bulk":
            self.single_frame.grid_remove()
            self.bulk_frame.grid(row=4, column=0, columnspan=2,
                                 padx=16, pady=(0, 4), sticky="ew")
        else:
            self.bulk_frame.grid_remove()
            self.single_frame.grid(row=4, column=0, columnspan=2,
                                   padx=16, pady=(0, 4), sticky="ew")

    def _update_info(self):
        slot = self.slot_var.get()
        if not slot:
            return
        inv = self.inventory[slot]
        self.info_var.set(
            f"現在：カレンダー {inv['calendar_days']}日分 ／"
            f" 残薬ボックス {inv['stock_days']}日分"
        )

    def _execute(self):
        if self.mode_var.get() == "bulk":
            self._execute_bulk()
        else:
            self._execute_single()

    def _execute_bulk(self):
        """全時間帯に同じ日数をまとめて補充する"""
        try:
            days = int(self.bulk_qty_var.get())
            if days <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "日数は1以上の整数で入力してください。",
                                 parent=self)
            return

        # 全時間帯の在庫チェック
        short = [
            f"{slot}：残薬{self.inventory[slot]['stock_days']}日分しかありません"
            for slot in self.active_slots
            if self.inventory[slot]["stock_days"] < days
        ]
        if short:
            messagebox.showerror(
                "在庫不足",
                f"以下の時間帯の残薬ボックスが足りません。\n\n" + "\n".join(short),
                parent=self
            )
            return

        # 確認メッセージ
        lines = []
        for slot in self.active_slots:
            inv = self.inventory[slot]
            lines.append(
                f"  {slot}：カレンダー {inv['calendar_days']}日"
                f" → {inv['calendar_days'] + days}日分"
                f"　残薬 {inv['stock_days']}日"
                f" → {inv['stock_days'] - days}日分"
            )
        if not messagebox.askokcancel(
            "確認",
            f"全時間帯に {days} 日分補充します。\n\n" + "\n".join(lines),
            parent=self
        ):
            return

        for slot in self.active_slots:
            inv = self.inventory[slot]
            save_inventory(self.resident_id, slot,
                           inv["calendar_days"] + days,
                           inv["stock_days"]    - days)
            add_history(self.resident_id, slot, "補充", days,
                        f"カレンダーに{days}日分補充（一括）",
                        prev_cal=inv["calendar_days"],
                        prev_stk=inv["stock_days"])

        messagebox.showinfo("完了", "補充を記録しました。", parent=self)
        self.on_done()
        self.destroy()

    def _execute_single(self):
        """選択した時間帯だけ補充する"""
        slot = self.slot_var.get()
        try:
            days = int(self.single_qty_var.get())
            if days <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "日数は1以上の整数で入力してください。",
                                 parent=self)
            return

        inv = self.inventory[slot]
        if inv["stock_days"] < days:
            messagebox.showerror(
                "在庫不足",
                f"残薬ボックスの在庫が足りません。\n"
                f"必要：{days}日分　現在：{inv['stock_days']}日分",
                parent=self
            )
            return

        new_cal   = inv["calendar_days"] + days
        new_stock = inv["stock_days"]    - days

        if new_cal > 7:
            if not messagebox.askyesno(
                "確認",
                f"カレンダーが7日分を超えます（{new_cal}日分）。続けますか？",
                parent=self
            ):
                return

        if not messagebox.askokcancel(
            "確認",
            f"【{slot}】補充の確認\n\n"
            f"カレンダー：{inv['calendar_days']}日 → {new_cal}日分\n"
            f"残薬ボックス：{inv['stock_days']}日 → {new_stock}日分",
            parent=self
        ):
            return

        save_inventory(self.resident_id, slot, new_cal, new_stock)
        add_history(self.resident_id, slot, "補充", days,
                    f"カレンダーに{days}日分補充",
                    prev_cal=inv["calendar_days"],
                    prev_stk=inv["stock_days"])
        messagebox.showinfo("完了", "補充を記録しました。", parent=self)
        self.on_done()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 直接修正ダイアログ
# =============================================================================

class EditDialog(tk.Toplevel):
    """薬を数え直したときなど、現在の在庫日数を直接上書き修正するダイアログ"""

    def __init__(self, parent, resident_id, resident_name, settings, inventory, on_done):
        super().__init__(parent)
        self.title(f"直接修正 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id  = resident_id
        self.settings     = settings
        self.inventory    = inventory
        self.on_done      = on_done
        self.active_slots = [s for s in TIME_SLOTS if settings[s]["enabled"]]

        self.slot_var = tk.StringVar()
        self.cal_var  = tk.StringVar()
        self.stk_var  = tk.StringVar()

        self._build_ui()
        self._center(parent)
        if self.active_slots:
            self.slot_var.set(self.active_slots[0])
            self._load_current()

    def _build_ui(self):
        tk.Label(self, text="在庫の直接修正", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(12, 4), sticky="w")
        tk.Label(self, text="実際に数えた日数を直接入力して上書きします。",
                 font=FONT_SMALL, fg="#666666").grid(
            row=1, column=0, columnspan=2, padx=16, sticky="w")

        tk.Label(self, text="時間帯：", font=FONT).grid(
            row=2, column=0, padx=(16, 4), pady=6, sticky="e")
        cb = ttk.Combobox(self, textvariable=self.slot_var,
                          values=self.active_slots, state="readonly",
                          width=10, font=FONT)
        cb.grid(row=2, column=1, padx=(4, 16), pady=6, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._load_current())

        tk.Label(self, text="カレンダー（日数）：", font=FONT).grid(
            row=3, column=0, padx=(16, 4), pady=6, sticky="e")
        tk.Entry(self, textvariable=self.cal_var, width=6, font=FONT).grid(
            row=3, column=1, padx=(4, 16), pady=6, sticky="w")

        tk.Label(self, text="残薬ボックス（日数）：", font=FONT).grid(
            row=4, column=0, padx=(16, 4), pady=6, sticky="e")
        tk.Entry(self, textvariable=self.stk_var, width=6, font=FONT).grid(
            row=4, column=1, padx=(4, 16), pady=6, sticky="w")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._execute).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

    def _load_current(self):
        slot = self.slot_var.get()
        if not slot:
            return
        inv = self.inventory[slot]
        self.cal_var.set(str(inv["calendar_days"]))
        self.stk_var.set(str(inv["stock_days"]))

    def _execute(self):
        slot = self.slot_var.get()
        try:
            cal = int(self.cal_var.get())
            stk = int(self.stk_var.get())
            if cal < 0 or stk < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "0以上の整数で入力してください。",
                                 parent=self)
            return

        inv = self.inventory[slot]
        msg = (f"【{slot}】修正の確認\n\n"
               f"カレンダー：{inv['calendar_days']}日 → {cal}日分\n"
               f"残薬ボックス：{inv['stock_days']}日 → {stk}日分")
        if not messagebox.askokcancel("確認", msg, parent=self):
            return

        save_inventory(self.resident_id, slot, cal, stk)
        add_history(self.resident_id, slot, "修正", stk,
                    f"カレンダー{cal}日分・残薬{stk}日分に修正",
                    prev_cal=inv["calendar_days"],
                    prev_stk=inv["stock_days"])
        messagebox.showinfo("完了", "修正を保存しました。", parent=self)
        self.on_done()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 飲み忘れ・調整ダイアログ
# =============================================================================

class AdjustDialog(tk.Toplevel):
    """
    飲み忘れや処方の微調整により日数を増減するダイアログ。
    「朝を1日分多く処方された」「昨日飲み忘れた」など柔軟に対応する。
    """

    def __init__(self, parent, resident_id, resident_name, settings, inventory, on_done):
        super().__init__(parent)
        self.title(f"飲み忘れ・調整 — {resident_name}")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id  = resident_id
        self.settings     = settings
        self.inventory    = inventory
        self.on_done      = on_done
        self.active_slots = [s for s in TIME_SLOTS if settings[s]["enabled"]]

        self.slot_var   = tk.StringVar()
        # 対象：カレンダー or 残薬ボックス
        self.target_var = tk.StringVar(value="カレンダー")
        self.sign_var   = tk.StringVar(value="+")   # + 増やす / - 減らす
        self.days_var   = tk.StringVar(value="1")
        self.reason_var = tk.StringVar()
        self.info_var   = tk.StringVar()

        self._build_ui()
        self._center(parent)
        if self.active_slots:
            self.slot_var.set(self.active_slots[0])
            self._update_info()

    def _build_ui(self):
        tk.Label(self, text="飲み忘れ・調整", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=3, padx=16, pady=(12, 2), sticky="w")
        tk.Label(self,
                 text="飲み忘れや処方の微調整で日数を増減します。理由も記録されます。",
                 font=FONT_SMALL, fg="#666666").grid(
            row=1, column=0, columnspan=3, padx=16, sticky="w")

        tk.Label(self, text="時間帯：", font=FONT).grid(
            row=2, column=0, padx=(16, 4), pady=6, sticky="e")
        cb = ttk.Combobox(self, textvariable=self.slot_var,
                          values=self.active_slots, state="readonly",
                          width=10, font=FONT)
        cb.grid(row=2, column=1, padx=(4, 4), pady=6, sticky="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self._update_info())

        tk.Label(self, text="対象：", font=FONT).grid(
            row=3, column=0, padx=(16, 4), pady=6, sticky="e")
        target_frame = tk.Frame(self)
        target_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=(4, 16))
        for t in ["カレンダー", "残薬ボックス"]:
            tk.Radiobutton(target_frame, text=t, variable=self.target_var,
                           value=t, font=FONT).pack(side="left", padx=4)

        tk.Label(self, text="増減：", font=FONT).grid(
            row=4, column=0, padx=(16, 4), pady=6, sticky="e")
        sign_frame = tk.Frame(self)
        sign_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=(4, 16))
        tk.Radiobutton(sign_frame, text="＋ 増やす（飲み忘れ等）",
                       variable=self.sign_var, value="+", font=FONT).pack(
            side="left", padx=4)
        tk.Radiobutton(sign_frame, text="－ 減らす",
                       variable=self.sign_var, value="-", font=FONT).pack(
            side="left", padx=4)

        tk.Label(self, text="日数：", font=FONT).grid(
            row=5, column=0, padx=(16, 4), pady=6, sticky="e")
        tk.Spinbox(self, from_=1, to=30, textvariable=self.days_var,
                   width=5, font=FONT).grid(
            row=5, column=1, padx=(4, 4), pady=6, sticky="w")

        tk.Label(self, text="理由：", font=FONT).grid(
            row=6, column=0, padx=(16, 4), pady=6, sticky="e")
        tk.Entry(self, textvariable=self.reason_var, width=28, font=FONT).grid(
            row=6, column=1, columnspan=2, padx=(4, 16), pady=6, sticky="w")

        tk.Label(self, textvariable=self.info_var, font=FONT_SMALL,
                 fg="#666666").grid(row=7, column=0, columnspan=3,
                                     padx=16, pady=4, sticky="w")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=8, column=0, columnspan=3, pady=12)
        tk.Button(btn_frame, text="適用", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._execute).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

    def _update_info(self):
        slot = self.slot_var.get()
        if not slot:
            return
        inv = self.inventory[slot]
        self.info_var.set(
            f"現在：カレンダー {inv['calendar_days']}日分 ／"
            f" 残薬ボックス {inv['stock_days']}日分"
        )

    def _execute(self):
        slot = self.slot_var.get()
        try:
            days = int(self.days_var.get())
            if days <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("入力エラー", "日数は1以上の整数で入力してください。",
                                 parent=self)
            return

        inv    = self.inventory[slot]
        target = self.target_var.get()
        sign   = self.sign_var.get()
        reason = self.reason_var.get().strip() or "理由なし"

        # 変更前の値を取得
        cal_now = inv["calendar_days"]
        stk_now = inv["stock_days"]

        if target == "カレンダー":
            new_val = cal_now + days if sign == "+" else cal_now - days
            new_val = max(0, new_val)
            new_cal, new_stk = new_val, stk_now
            before, after = cal_now, new_val
        else:
            new_val = stk_now + days if sign == "+" else stk_now - days
            new_val = max(0, new_val)
            new_cal, new_stk = cal_now, new_val
            before, after = stk_now, new_val

        sign_label = "＋" if sign == "+" else "－"
        msg = (f"【{slot}】{target} の調整\n\n"
               f"{before}日分 {sign_label}{days}日 → {after}日分\n"
               f"理由：{reason}")
        if not messagebox.askokcancel("確認", msg, parent=self):
            return

        save_inventory(self.resident_id, slot, new_cal, new_stk)
        op_label = "調整(増)" if sign == "+" else "調整(減)"
        add_history(self.resident_id, slot, op_label, days,
                    f"{target} {sign_label}{days}日（{reason}）",
                    prev_cal=cal_now,
                    prev_stk=stk_now)
        messagebox.showinfo("完了", "調整を記録しました。", parent=self)
        self.on_done()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 履歴編集ダイアログ
# =============================================================================

class HistoryEditDialog(tk.Toplevel):
    """操作履歴を1件編集するダイアログ"""

    def __init__(self, parent, row, on_done):
        super().__init__(parent)
        self.title("履歴を編集")
        self.resizable(False, False)
        self.grab_set()

        self.row     = row
        self.on_done = on_done

        self.slot_var = tk.StringVar(value=row["time_slot"])
        self.op_var   = tk.StringVar(value=row["operation_type"])
        self.qty_var  = tk.StringVar(value=str(row["quantity"]))
        self.note_var = tk.StringVar(value=row["note"] or "")
        self.dt_var   = tk.StringVar(value=row["created_at"] or "")

        self._build_ui()
        self._center(parent)

    def _build_ui(self):
        tk.Label(self, text="履歴を編集", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=2, padx=16, pady=(12, 8), sticky="w")

        tk.Label(self, text="時間帯：", font=FONT).grid(
            row=1, column=0, padx=(16, 4), pady=4, sticky="e")
        ttk.Combobox(self, textvariable=self.slot_var,
                     values=TIME_SLOTS, width=10, font=FONT).grid(
            row=1, column=1, padx=(4, 16), pady=4, sticky="w")

        tk.Label(self, text="操作種別：", font=FONT).grid(
            row=2, column=0, padx=(16, 4), pady=4, sticky="e")
        ttk.Combobox(self, textvariable=self.op_var,
                     values=["処方", "補充", "調整(増)", "調整(減)", "修正", "処方取消"],
                     width=12, font=FONT).grid(
            row=2, column=1, padx=(4, 16), pady=4, sticky="w")

        tk.Label(self, text="数量（日数）：", font=FONT).grid(
            row=3, column=0, padx=(16, 4), pady=4, sticky="e")
        tk.Entry(self, textvariable=self.qty_var, width=8, font=FONT).grid(
            row=3, column=1, padx=(4, 16), pady=4, sticky="w")

        tk.Label(self, text="内容・備考：", font=FONT).grid(
            row=4, column=0, padx=(16, 4), pady=4, sticky="e")
        tk.Entry(self, textvariable=self.note_var, width=28, font=FONT).grid(
            row=4, column=1, padx=(4, 16), pady=4, sticky="w")

        tk.Label(self, text="日時：", font=FONT).grid(
            row=5, column=0, padx=(16, 4), pady=4, sticky="e")
        tk.Entry(self, textvariable=self.dt_var, width=20, font=FONT).grid(
            row=5, column=1, padx=(4, 16), pady=4, sticky="w")
        tk.Label(self, text="例：2025-05-13 09:00:00",
                 font=FONT_SMALL, fg="#888888").grid(
            row=6, column=1, padx=(4, 16), sticky="w")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

    def _save(self):
        slot = self.slot_var.get().strip()
        op   = self.op_var.get().strip()
        note = self.note_var.get().strip()
        dt   = self.dt_var.get().strip()
        try:
            qty = int(self.qty_var.get())
        except ValueError:
            messagebox.showerror("入力エラー", "数量は整数で入力してください。", parent=self)
            return
        if not slot or not op or not dt:
            messagebox.showerror("入力エラー", "時間帯・操作種別・日時は必須です。", parent=self)
            return
        update_history(self.row["id"], slot, op, qty, note, dt)
        messagebox.showinfo("完了", "履歴を修正しました。", parent=self)
        self.on_done()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# メインアプリ
# =============================================================================

class MedicineApp(tk.Tk):
    """お薬在庫管理アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("お薬在庫管理")
        self.geometry("980x660")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self.residents        = []
        self.selected_id      = None
        self.selected_name    = ""
        self.current_settings = {}
        self.current_inv      = {}

        self._build_ui()
        self._load_residents()

    def _build_ui(self):
        """メインウィンドウのUIを組み立てる"""

        # ---- タイトルバー ----
        title_frame = tk.Frame(self, bg=COLOR_HEADER, pady=10)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text="お薬在庫管理",
                 font=FONT_TITLE, bg=COLOR_HEADER, fg="white").pack(
            side="left", padx=16)

        # ---- メインエリア ----
        main_frame = tk.Frame(self, bg=COLOR_BG)
        main_frame.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- 左パネル（入居者一覧）----
        left = tk.Frame(main_frame, bg=COLOR_BG, width=200)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="入居者一覧", font=FONT_BOLD, bg=COLOR_BG).pack(
            anchor="w", pady=(0, 4))

        lf = tk.Frame(left)
        lf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(lf)
        self.resident_listbox = tk.Listbox(
            lf, font=FONT, yscrollcommand=sb.set,
            selectbackground=COLOR_ACCENT, selectforeground="white",
            relief="flat", bd=1, highlightthickness=1, activestyle="dotbox",
        )
        sb.config(command=self.resident_listbox.yview)
        sb.pack(side="right", fill="y")
        self.resident_listbox.pack(fill="both", expand=True)
        self.resident_listbox.bind("<<ListboxSelect>>", self._on_select_resident)

        # ---- 右パネル（在庫詳細）----
        self.right = tk.Frame(main_frame, bg=COLOR_BG)
        self.right.pack(side="left", fill="both", expand=True)
        self._build_right_placeholder()

    def _build_right_placeholder(self):
        for w in self.right.winfo_children():
            w.destroy()
        tk.Label(self.right, text="← 入居者を選択してください",
                 font=FONT, fg="#AAAAAA", bg=COLOR_BG).pack(expand=True)

    def _build_right_panel(self):
        """選択した入居者の在庫詳細パネルを構築する"""
        for w in self.right.winfo_children():
            w.destroy()

        # ---- ヘッダー ----
        hdr = tk.Frame(self.right, bg=COLOR_BG)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text=f"　{self.selected_name} さん",
                 font=FONT_TITLE, bg=COLOR_BG).pack(side="left")
        tk.Button(hdr, text="⚙ 設定", font=FONT,
                  relief="flat", cursor="hand2", padx=10, pady=4,
                  command=self._open_settings).pack(side="right")

        # ---- 在庫ステータステーブル ----
        self._build_status_table()

        # ---- 臨時薬パネル ----
        self._build_temp_medicine_panel()

        # ---- 操作ボタン ----
        btn_frame = tk.Frame(self.right, bg=COLOR_BG)
        btn_frame.pack(fill="x", pady=10)
        for label, cmd, color in [
            ("補 充",        self._open_refill,  "#27AE60"),
            ("飲み忘れ・調整", self._open_adjust,  "#E67E22"),
            ("直接修正",     self._open_edit,    "#7F8C8D"),
        ]:
            tk.Button(btn_frame, text=label, font=FONT_BOLD,
                      bg=color, fg="white", relief="flat", cursor="hand2",
                      padx=14, pady=7, command=cmd).pack(side="left", padx=6)

        tk.Label(btn_frame,
                 text="※入荷は通院記録アプリから自動追加されます",
                 font=FONT_SMALL, fg="#888888", bg=COLOR_BG).pack(
            side="left", padx=12)

        # ---- 操作履歴 ----
        self._build_history_panel()

    def _build_status_table(self):
        """時間帯ごとの在庫状況テーブルを構築する"""
        table_frame = tk.Frame(self.right, bg=COLOR_BG)
        table_frame.pack(fill="x")

        col_configs = [
            ("時間帯",       8),
            ("カレンダー",  10),
            ("残薬ボックス", 10),
            ("合  計",      10),
            ("いつまで",    14),
        ]

        # ヘッダー行
        for col, (label, width) in enumerate(col_configs):
            tk.Label(table_frame, text=label, font=FONT_BOLD,
                     bg=COLOR_HEADER, fg=COLOR_HEADER_FG,
                     width=width, anchor="center",
                     relief="flat", pady=6).grid(
                row=0, column=col, padx=1, pady=(0, 1), sticky="ew")

        enabled_count = 0
        for slot in TIME_SLOTS:
            s   = self.current_settings[slot]
            inv = self.current_inv[slot]
            if not s["enabled"]:
                continue

            bg    = COLOR_ROW_ODD if enabled_count % 2 == 0 else COLOR_ROW_EVEN
            cal   = inv["calendar_days"]
            stock = inv["stock_days"]
            total = cal + stock
            until = calc_available_until(total, slot_consumed_today(slot))

            # 残り7日以下は黄色、3日以下は赤
            if total == 0:
                until_fg = "#AAAAAA"
            elif total <= 3:
                until_fg = COLOR_WARN
            elif total <= 7:
                until_fg = "#E67E22"
            else:
                until_fg = "#222222"

            row_data = [
                (slot,                    "#333333"),
                (f"{cal}日分",            "#333333"),
                (f"{stock}日分",          "#333333"),
                (f"{total}日分",          "#333333"),
                (f"{until}まで" if total > 0 else "在庫なし", until_fg),
            ]
            row = enabled_count + 1
            for col, (text, fg) in enumerate(row_data):
                width = col_configs[col][1]
                tk.Label(table_frame, text=text, font=FONT,
                         bg=bg, fg=fg, width=width, anchor="center",
                         relief="flat", pady=9).grid(
                    row=row, column=col, padx=1, pady=1, sticky="ew")

            enabled_count += 1

        if enabled_count == 0:
            tk.Label(table_frame,
                     text="有効な時間帯がありません。「設定」から時間帯を有効にしてください。",
                     font=FONT_SMALL, fg="#AAAAAA", bg=COLOR_BG).grid(
                row=1, column=0, columnspan=5, padx=8, pady=16)

        # 自動差し引きの状況を注記として表示する
        consumed_slots = [
            f"{slot}（{SLOT_TIMES[slot]}）"
            for slot in TIME_SLOTS
            if self.current_settings[slot]["enabled"]
            and self.auto_consumed.get(slot, 0) > 0
        ]
        if consumed_slots:
            note = "※ 服薬済み時間帯を自動で差し引いています：" + "・".join(consumed_slots)
        else:
            # 服薬時刻が既に過ぎているスロットがあるか確認
            passed_today = [
                slot for slot in TIME_SLOTS
                if self.current_settings[slot]["enabled"]
                and slot_consumed_today(slot)
            ]
            if passed_today:
                note = "※ 本日の服薬分は前回の補充・修正時に反映済みです（差し引き不要）"
            else:
                note = "※ まだ本日の服薬時刻を迎えていません"
        tk.Label(table_frame, text=note, font=FONT_SMALL,
                 fg="#888888", bg=COLOR_BG).grid(
            row=enabled_count + 1, column=0, columnspan=5,
            padx=4, pady=(6, 0), sticky="w")

    def _build_temp_medicine_panel(self):
        """臨時薬情報を visits.db から取得して表示するパネル"""
        temp_list = get_active_temp_medicines(self.selected_id)
        if not temp_list:
            return

        frame = tk.Frame(self.right, bg="#FEF9EC", bd=1, relief="solid",
                         padx=10, pady=6)
        frame.pack(fill="x", pady=(6, 0))
        tk.Label(frame, text="臨時薬", font=FONT_BOLD, bg="#FEF9EC").pack(anchor="w", pady=(0, 4))

        today = date.today()

        for info in temp_list:
            # 病院名・処方日の見出し行
            head = tk.Frame(frame, bg="#FEF9EC")
            head.pack(fill="x", pady=(2, 0))
            tk.Label(head, text=f"【{info['hospital']}】処方日：{info['visit_date']}",
                     font=FONT_BOLD, fg="#5A3E00", bg="#FEF9EC").pack(side="left")

            # 薬ごとに表示する
            for med in info["medicines"]:
                med_row = tk.Frame(frame, bg="#FEF9EC")
                med_row.pack(fill="x", pady=(1, 0))
                med_label = f"  ■ {med['name']}：" if med["name"] else "  ■ （薬名未設定）："
                tk.Label(med_row, text=med_label,
                         font=FONT_BOLD, fg="#5A3E00", bg="#FEF9EC").pack(side="left")

                any_slot = False
                for slot in TIME_SLOTS:
                    sd = med["slots"].get(slot, {})
                    days = sd.get("days", 0)
                    if days <= 0:
                        continue
                    start_str = sd.get("start_date") or info["visit_date"]
                    try:
                        start = date.fromisoformat(start_str)
                    except ValueError:
                        continue
                    any_slot = True
                    end_date  = start + timedelta(days=days - 1)
                    remaining = (end_date - today).days

                    if remaining < 0:
                        fg = "#AAAAAA"
                        label_text = f"{slot}：終了済（{end_date.strftime('%m月%d日')}まで）"
                    elif remaining == 0:
                        fg = COLOR_WARN
                        label_text = f"{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"
                    elif remaining <= 3:
                        fg = "#E67E22"
                        label_text = f"{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"
                    else:
                        fg = "#2E7D6E"
                        label_text = f"{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"

                    tk.Label(med_row,
                             text=label_text,
                             font=FONT, fg=fg, bg="#FEF9EC").pack(side="left", padx=(0, 8))

                if not any_slot:
                    tk.Label(med_row, text="（日数の記録なし）",
                             font=FONT_SMALL, fg="#AAAAAA", bg="#FEF9EC").pack(side="left")

    def _build_history_panel(self):
        """操作履歴パネルを構築する（最新15件・編集・削除可能）"""
        frame = tk.Frame(self.right, bg=COLOR_BG)
        frame.pack(fill="both", expand=True, pady=(6, 0))

        # ヘッダー行：タイトル＋編集・削除ボタン
        hdr = tk.Frame(frame, bg=COLOR_BG)
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="操作履歴（最新15件）",
                 font=FONT_BOLD, bg=COLOR_BG).pack(side="left")
        tk.Button(hdr, text="削除", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  fg=COLOR_WARN, command=self._delete_selected_history).pack(
            side="right", padx=(4, 0))
        tk.Button(hdr, text="編集", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=8, pady=2,
                  command=self._edit_selected_history).pack(side="right")

        history = get_history(self.selected_id, limit=15)
        self.history_rows = list(history)

        if not history:
            tk.Label(frame, text="まだ記録がありません。",
                     font=FONT_SMALL, fg="#AAAAAA", bg=COLOR_BG).pack(anchor="w")
            self.history_tv = None
            return

        # Treeview で表示（クリックで行選択できる）
        tv_frame = tk.Frame(frame, bg=COLOR_BG)
        tv_frame.pack(fill="both", expand=True)

        cols = ("日時", "時間帯", "操作", "内容")
        tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                          height=8, selectmode="browse")
        self.history_tv = tv

        for col, width in [("日時", 140), ("時間帯", 60), ("操作", 72), ("内容", 260)]:
            tv.heading(col, text=col)
            tv.column(col, width=width, anchor="w", stretch=(col == "内容"))

        for row in history:
            dt = row["created_at"][:16] if row["created_at"] else ""
            tv.insert("", "end", iid=str(row["id"]),
                      values=(dt, row["time_slot"],
                              row["operation_type"], row["note"] or ""))

        sb = ttk.Scrollbar(tv_frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # =========================================================================
    # イベントハンドラ
    # =========================================================================

    def _load_residents(self):
        self.residents = get_residents()
        self.resident_listbox.delete(0, "end")
        for _, name in self.residents:
            self.resident_listbox.insert("end", f"  {name}")

    def _on_select_resident(self, event):
        sel = self.resident_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.selected_id   = self.residents[idx][0]
        self.selected_name = self.residents[idx][1]
        self._refresh_right()

    def _refresh_right(self):
        if self.selected_id is None:
            return
        self.current_settings = get_settings(self.selected_id)
        raw_inv = get_inventory(self.selected_id)

        # カレンダー日数を「服薬済み回数分」だけ差し引いて表示用在庫を作成する。
        # DBの値は書き換えず、表示とダイアログへの受け渡しのみ補正する。
        self.current_inv = {}
        self.auto_consumed = {}   # 時間帯ごとの自動補正数（ステータス表示で使う）
        for slot, inv in raw_inv.items():
            consumed = count_consumed_since(inv["updated_at"], slot)
            adj_cal  = max(0, inv["calendar_days"] - consumed)
            self.auto_consumed[slot] = consumed
            self.current_inv[slot]   = dict(inv)
            self.current_inv[slot]["calendar_days"] = adj_cal

        self._build_right_panel()

    def _open_settings(self):
        SettingsDialog(self, self.selected_id, self.selected_name)
        self.after(200, self._refresh_right)

    def _open_refill(self):
        RefillDialog(self, self.selected_id, self.selected_name,
                     self.current_settings, self.current_inv,
                     self._refresh_right)

    def _open_edit(self):
        EditDialog(self, self.selected_id, self.selected_name,
                   self.current_settings, self.current_inv,
                   self._refresh_right)

    def _open_adjust(self):
        AdjustDialog(self, self.selected_id, self.selected_name,
                     self.current_settings, self.current_inv,
                     self._refresh_right)

    def _edit_selected_history(self):
        """選択中の履歴を編集ダイアログで開く"""
        if not getattr(self, "history_tv", None) or not self.history_tv.selection():
            messagebox.showinfo("選択なし", "編集する履歴行をクリックして選択してください。")
            return
        iid = self.history_tv.selection()[0]
        row = next((r for r in self.history_rows if str(r["id"]) == iid), None)
        if not row:
            return
        HistoryEditDialog(self, row, self._refresh_right)

    def _delete_selected_history(self):
        """選択中の履歴を削除する（操作前の値が記録されていれば在庫も元に戻す）"""
        if not getattr(self, "history_tv", None) or not self.history_tv.selection():
            messagebox.showinfo("選択なし", "削除する履歴行をクリックして選択してください。")
            return
        iid = self.history_tv.selection()[0]
        row = next((r for r in self.history_rows if str(r["id"]) == iid), None)
        if not row:
            return
        dt = row["created_at"][:16] if row["created_at"] else ""
        # 操作前の値が保存されているか確認
        can_revert = (row.get("prev_cal") is not None and row.get("prev_stk") is not None)
        if can_revert:
            revert_note = (f"カレンダー → {row['prev_cal']}日分、"
                           f"残薬ボックス → {row['prev_stk']}日分 に戻ります。")
        else:
            revert_note = "※この履歴は操作前の値が記録されていないため、在庫は変更されません。"
        msg = (f"この履歴を削除しますか？\n\n"
               f"{dt}　{row['time_slot']}　{row['operation_type']}\n"
               f"{row['note'] or ''}\n\n"
               f"{revert_note}")
        if not messagebox.askyesno("削除の確認", msg):
            return
        reverted = delete_history(row["id"])
        if reverted:
            messagebox.showinfo("完了", "履歴を削除し、在庫を元の値に戻しました。")
        else:
            messagebox.showinfo("完了", "履歴を削除しました（在庫は変更していません）。")
        self._refresh_right()


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = MedicineApp()
    app.mainloop()
