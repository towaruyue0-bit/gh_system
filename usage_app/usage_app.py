# シェアホームすみか - 利用実績入力アプリ
# usage_app.py

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import calendar
from datetime import datetime, date, timedelta
import glob

# ============================================================
# パス設定
# ============================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"  # 個人情報を保管する安全フォルダ（OneDrive・Claude非対応）
DATA_DIR = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR = os.path.join(PRIVATE_ROOT, "usage_backups")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
DAILY_DB = os.path.join(DATA_DIR, "daily_records.db")

# ============================================================
# 初期セットアップ（フォルダ・DBの自動作成）
# ============================================================
def setup():
    """アプリ起動時にフォルダとDBを自動作成する"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    _create_daily_db()
    _backup_db()

def _create_daily_db():
    """daily_records.db のテーブルを作成する（なければ）"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()

    # 日別利用実績テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            record_date TEXT NOT NULL,
            breakfast INTEGER DEFAULT 1,
            lunch INTEGER DEFAULT 0,
            dinner INTEGER DEFAULT 1,
            stay INTEGER DEFAULT 1,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(resident_id, record_date)
        )
    """)

    # 外泊記録テーブル
    c.execute("""
        CREATE TABLE IF NOT EXISTS absence_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            leave_date TEXT NOT NULL,
            return_date TEXT NOT NULL,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 昼食提供曜日設定テーブル（0=月 〜 6=日）
    c.execute("""
        CREATE TABLE IF NOT EXISTS lunch_days (
            weekday INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 0
        )
    """)

    # 昼食曜日の初期データ（水=2, 木=3 のみON）
    c.execute("SELECT COUNT(*) FROM lunch_days")
    if c.fetchone()[0] == 0:
        for wd in range(7):
            active = 1 if wd in (2, 3) else 0
            c.execute("INSERT INTO lunch_days (weekday, is_active) VALUES (?, ?)", (wd, active))

    conn.commit()
    conn.close()

def _backup_db():
    """起動時にdaily_records.dbをバックアップ（最大10個）"""
    if not os.path.exists(DAILY_DB):
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_daily_{timestamp}.db")
    shutil.copy2(DAILY_DB, backup_path)

    # 10個を超えたら古いものを削除
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_daily_*.db")))
    while len(backups) > 10:
        os.remove(backups.pop(0))

# ============================================================
# DB操作ヘルパー
# ============================================================
def get_residents():
    """residents.dbから入居中の入居者一覧を取得する"""
    if not os.path.exists(RESIDENTS_DB):
        messagebox.showerror("エラー", f"入居者マスターDBが見つかりません。\n{RESIDENTS_DB}")
        return []
    try:
        conn = sqlite3.connect(RESIDENTS_DB)
        c = conn.cursor()
        # statusカラムで「入居中」を絞り込む（カラム名はマスターアプリに合わせて調整可能）
        c.execute("SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id")
        rows = c.fetchall()
        conn.close()
        return rows
    except Exception as e:
        messagebox.showerror("エラー", f"入居者情報の読み込みに失敗しました。\n{e}")
        return []

def get_lunch_days():
    """昼食提供曜日の設定を取得する（アクティブな曜日番号のセット）"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    c.execute("SELECT weekday FROM lunch_days WHERE is_active = 1")
    result = {row[0] for row in c.fetchall()}
    conn.close()
    return result

def get_absence_dates(resident_id, year, month):
    """指定月の外泊日付セットを取得する"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    c.execute("""
        SELECT leave_date, return_date FROM absence_records
        WHERE resident_id = ?
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()

    absence_dates = set()
    for leave_str, return_str in rows:
        leave = date.fromisoformat(leave_str)
        ret = date.fromisoformat(return_str)
        # 外泊開始日・帰宅日は編集できるよう除外し、その間の日だけを外泊扱いにする
        current = leave + timedelta(days=1)
        while current < ret:
            if current.year == year and current.month == month:
                absence_dates.add(current.day)
            current += timedelta(days=1)
    return absence_dates

def get_records_for_month(resident_id, year, month):
    """指定月の日別実績を取得する（{日: {breakfast,lunch,dinner,stay,note}}）"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    prefix = f"{year:04d}-{month:02d}-"
    c.execute("""
        SELECT record_date, breakfast, lunch, dinner, stay, note
        FROM daily_records
        WHERE resident_id = ? AND record_date LIKE ?
    """, (resident_id, prefix + "%"))
    rows = c.fetchall()
    conn.close()

    records = {}
    for row in rows:
        d = int(row[0].split("-")[2])
        records[d] = {
            "breakfast": bool(row[1]),
            "lunch": bool(row[2]),
            "dinner": bool(row[3]),
            "stay": bool(row[4]),
            "note": row[5] or "",
        }
    return records

def save_records(resident_id, year, month, day_data):
    """月次データを一括保存する（UPSERT）"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for day, data in day_data.items():
        record_date = f"{year:04d}-{month:02d}-{day:02d}"
        c.execute("""
            INSERT INTO daily_records
                (resident_id, record_date, breakfast, lunch, dinner, stay, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resident_id, record_date) DO UPDATE SET
                breakfast = excluded.breakfast,
                lunch = excluded.lunch,
                dinner = excluded.dinner,
                stay = excluded.stay,
                note = excluded.note,
                updated_at = excluded.updated_at
        """, (
            resident_id,
            record_date,
            int(data["breakfast"].get()),
            int(data["lunch"].get()),
            int(data["dinner"].get()),
            int(data["stay"].get()),
            data["note"].get(),
            now,
        ))
    conn.commit()
    conn.close()

# ============================================================
# 外泊記録のDB操作
# ============================================================
def get_all_absences(resident_id):
    """指定入居者の外泊記録を全件取得する"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    c.execute("""
        SELECT id, leave_date, return_date, note
        FROM absence_records
        WHERE resident_id = ?
        ORDER BY leave_date
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_absence(resident_id, leave_date, return_date, note):
    """外泊記録を登録する"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO absence_records (resident_id, leave_date, return_date, note)
        VALUES (?, ?, ?, ?)
    """, (resident_id, leave_date, return_date, note))
    conn.commit()
    conn.close()

def delete_absence(absence_id):
    """外泊記録を削除する"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    c.execute("DELETE FROM absence_records WHERE id = ?", (absence_id,))
    conn.commit()
    conn.close()

def save_lunch_days(active_weekdays):
    """昼食提供曜日の設定を保存する"""
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    for wd in range(7):
        active = 1 if wd in active_weekdays else 0
        c.execute("UPDATE lunch_days SET is_active = ? WHERE weekday = ?", (active, wd))
    conn.commit()
    conn.close()

# ============================================================
# メインウィンドウ
# ============================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("シェアホームすみか - 利用実績入力")
        self.geometry("900x700")
        self.configure(bg="#f0f4f8")
        self.resizable(True, True)

        # ノートブック（タブ）
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#f0f4f8")
        style.configure("TNotebook.Tab", font=("メイリオ", 11), padding=(12, 6))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # 各タブを作成
        self.tab_main = MainTab(self.notebook)
        self.tab_absence = AbsenceTab(self.notebook, on_change=self.tab_main.reload)
        self.tab_settings = SettingsTab(self.notebook, on_change=self.tab_main.reload)
        self.tab_summary = SummaryTab(self.notebook)

        self.notebook.add(self.tab_main, text="　月次入力　")
        self.notebook.add(self.tab_absence, text="　外泊登録　")
        self.notebook.add(self.tab_settings, text="　設定　")
        self.notebook.add(self.tab_summary, text="　月次集計　")

# ============================================================
# タブ1：月次入力
# ============================================================
class MainTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f0f4f8")

        # 年月初期値：billing_appから環境変数で受け取った月を優先
        import os as _os
        today = date.today()
        try:
            _y = int(_os.environ.get("GH_TARGET_YEAR",  today.year))
            _m = int(_os.environ.get("GH_TARGET_MONTH", today.month))
        except (ValueError, TypeError):
            _y, _m = today.year, today.month
        self.year  = tk.IntVar(value=_y)
        self.month = tk.IntVar(value=_m)
        self.resident_id = tk.IntVar()
        self.residents = []

        self._build_header()
        self._build_table_area()
        self._load_residents()

    def _build_header(self):
        """上部の選択エリアを作成する"""
        header = tk.Frame(self, bg="#2c5f8a")
        header.pack(fill="x", padx=0, pady=0)

        tk.Label(header, text="利用実績入力", font=("メイリオ", 14, "bold"),
                 bg="#2c5f8a", fg="white").pack(side="left", padx=16, pady=10)

        ctrl = tk.Frame(header, bg="#2c5f8a")
        ctrl.pack(side="right", padx=10, pady=8)

        # 前へボタン
        tk.Button(ctrl, text="◀ 前へ", font=("メイリオ", 10),
                  bg="#4a7fb5", fg="white", relief="flat", padx=8,
                  command=self._prev_resident).pack(side="left", padx=(0, 2))

        # 入居者選択
        tk.Label(ctrl, text="入居者：", bg="#2c5f8a", fg="white",
                 font=("メイリオ", 11)).pack(side="left")
        self.resident_cb = ttk.Combobox(ctrl, width=12, font=("メイリオ", 11),
                                         state="readonly")
        self.resident_cb.pack(side="left", padx=(0, 2))
        self.resident_cb.bind("<<ComboboxSelected>>", lambda e: self.reload())

        # 次へボタン
        tk.Button(ctrl, text="次へ ▶", font=("メイリオ", 10),
                  bg="#4a7fb5", fg="white", relief="flat", padx=8,
                  command=self._next_resident).pack(side="left", padx=(0, 16))

        # 年選択
        tk.Label(ctrl, text="年：", bg="#2c5f8a", fg="white",
                 font=("メイリオ", 11)).pack(side="left")
        year_spin = tk.Spinbox(ctrl, from_=2020, to=2099, textvariable=self.year,
                               width=6, font=("メイリオ", 11),
                               command=self.reload)
        year_spin.pack(side="left")

        # 月選択
        tk.Label(ctrl, text="月：", bg="#2c5f8a", fg="white",
                 font=("メイリオ", 11)).pack(side="left", padx=(8, 0))
        month_spin = tk.Spinbox(ctrl, from_=1, to=12, textvariable=self.month,
                                width=4, font=("メイリオ", 11),
                                command=self.reload)
        month_spin.pack(side="left")

        # 保存ボタン
        tk.Button(ctrl, text="💾 保存", font=("メイリオ", 11, "bold"),
                  bg="#4caf50", fg="white", relief="flat", padx=12,
                  command=self.save).pack(side="left", padx=(16, 0))

        # 入力状況バー（ヘッダー下）
        self.status_bar = tk.Label(self, text="", font=("メイリオ", 10),
                                   bg="#e8f4e8", fg="#2c5f2e", anchor="w",
                                   padx=16, pady=4)
        self.status_bar.pack(fill="x")

    def _build_table_area(self):
        """スクロール可能なテーブルエリアを作成する"""
        container = tk.Frame(self, bg="#f0f4f8")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # スクロールバー
        self.canvas = tk.Canvas(container, bg="#f0f4f8", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                   command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg="#f0f4f8")
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self.canvas_window, width=e.width))

        # マウスホイールでスクロール
        self.canvas.bind_all("<MouseWheel>",
                             lambda e: self.canvas.yview_scroll(
                                 int(-1 * (e.delta / 120)), "units"))

        self.day_data = {}  # {day: {breakfast, lunch, dinner, stay, note}}

        # ドラッグ操作の状態管理
        self._drag_value = None   # ドラッグ中に適用する値（True/False）
        self._dragging = False
        self._drag_targets = {}   # {Checkbuttonウィジェット: BooleanVar}

    def _load_residents(self):
        """入居者一覧を読み込んでコンボボックスに設定する"""
        self.residents = get_residents()
        if not self.residents:
            return
        names = [r[1] for r in self.residents]
        self.resident_cb["values"] = names
        self.resident_cb.current(0)
        self.resident_id.set(self.residents[0][0])
        self.reload()

    def reload(self, *args):
        """画面を再描画する"""
        # 選択中の入居者IDを更新
        idx = self.resident_cb.current()
        if idx >= 0 and self.residents:
            self.resident_id.set(self.residents[idx][0])

        year = self.year.get()
        month = self.month.get()
        res_id = self.resident_id.get()

        if not res_id:
            return

        # データ取得
        lunch_days = get_lunch_days()
        absence_days = get_absence_dates(res_id, year, month)
        saved = get_records_for_month(res_id, year, month)

        # テーブルを再構築
        for w in self.inner.winfo_children():
            w.destroy()
        self.day_data = {}
        self._drag_targets = {}  # ウィジェットが再生成されるので毎回リセット

        self._draw_table_header()
        self._update_status_bar()

        num_days = calendar.monthrange(year, month)[1]
        weekday_names = ["月", "火", "水", "木", "金", "土", "日"]

        for day in range(1, num_days + 1):
            d = date(year, month, day)
            wd = d.weekday()  # 0=月 〜 6=日
            wd_name = weekday_names[wd]
            is_absence = day in absence_days

            # デフォルト値の決定
            if is_absence:
                # 外泊中の日は既存データにかかわらず全てオフで表示する
                # （保存時に0が書き込まれ、請求計算に旧データが混入するのを防ぐ）
                bf = lc = dn = st = False
                nt = saved[day]["note"] if day in saved else ""
            elif day in saved:
                # 保存済みのデータを表示する
                bf = saved[day]["breakfast"]
                lc = saved[day]["lunch"]
                dn = saved[day]["dinner"]
                st = saved[day]["stay"]
                nt = saved[day]["note"]
            else:
                # 初期値：朝・夕・宿泊はON、昼は曜日設定に従う
                bf = True
                lc = wd in lunch_days
                dn = True
                st = True
                nt = ""

            self._draw_row(day, wd_name, wd, is_absence, bf, lc, dn, st, nt)

        self._draw_total_row()

    def _draw_table_header(self):
        """テーブルのヘッダー行を描画する"""
        cols = ["日", "曜", "宿泊", "朝食", "昼食", "夕食", "備考"]
        widths = [40, 30, 50, 50, 50, 50, 180]
        bg = "#2c5f8a"

        for col, (text, w) in enumerate(zip(cols, widths)):
            tk.Label(self.inner, text=text, bg=bg, fg="white",
                     font=("メイリオ", 10, "bold"),
                     width=w // 10, anchor="center",
                     relief="flat").grid(row=0, column=col,
                                         padx=1, pady=1, sticky="nsew")

    def _draw_row(self, day, wd_name, wd, is_absence,
                  bf, lc, dn, st, nt):
        """1日分の行を描画する"""
        row = day  # 行番号（0はヘッダー）

        # 土日・外泊の背景色
        if is_absence:
            bg = "#cccccc"
        elif wd == 5:  # 土
            bg = "#e8f0ff"
        elif wd == 6:  # 日
            bg = "#ffe8e8"
        else:
            bg = "white" if day % 2 == 0 else "#f9f9f9"

        # 変数を作成
        var_bf = tk.BooleanVar(value=bf)
        var_lc = tk.BooleanVar(value=lc)
        var_dn = tk.BooleanVar(value=dn)
        var_st = tk.BooleanVar(value=st)
        var_nt = tk.StringVar(value=nt)

        self.day_data[day] = {
            "breakfast": var_bf,
            "lunch": var_lc,
            "dinner": var_dn,
            "stay": var_st,
            "note": var_nt,
        }

        state = "disabled" if is_absence else "normal"

        # 日付・曜日
        tk.Label(self.inner, text=str(day), bg=bg,
                 font=("メイリオ", 10), width=4,
                 anchor="center").grid(row=row, column=0, padx=1, pady=1,
                                       sticky="nsew")
        tk.Label(self.inner, text=wd_name, bg=bg,
                 font=("メイリオ", 10), width=3,
                 anchor="center").grid(row=row, column=1, padx=1, pady=1,
                                       sticky="nsew")

        # チェックボックス（宿泊・朝・昼・夕）
        for col, var in enumerate([var_st, var_bf, var_lc, var_dn], start=2):
            cb = tk.Checkbutton(self.inner, variable=var, bg=bg,
                                state=state,
                                command=self._update_totals)
            cb.grid(row=row, column=col, padx=1, pady=1)
            # 有効なチェックボックスだけドラッグ対象に登録
            if state == "normal":
                cb.bind("<Button-1>",
                        lambda e, v=var: self._on_cb_press(e, v))
                cb.bind("<B1-Motion>", self._on_cb_motion)
                cb.bind("<ButtonRelease-1>", self._on_cb_release)
                self._drag_targets[cb] = var

        # 備考欄
        entry = tk.Entry(self.inner, textvariable=var_nt, bg=bg,
                         font=("メイリオ", 9), relief="flat",
                         state=state, width=22)
        entry.grid(row=row, column=6, padx=2, pady=1, sticky="ew")

    def _draw_total_row(self):
        """合計行を描画する"""
        row = 32  # 合計行は31日の下
        bg = "#2c5f8a"

        tk.Label(self.inner, text="合計", bg=bg, fg="white",
                 font=("メイリオ", 10, "bold"),
                 anchor="center").grid(row=row, column=0, columnspan=2,
                                       padx=1, pady=2, sticky="nsew")

        self.total_labels = []
        for col in range(4):
            lbl = tk.Label(self.inner, text="0", bg=bg, fg="white",
                           font=("メイリオ", 10, "bold"), anchor="center")
            lbl.grid(row=row, column=col + 2, padx=1, pady=2, sticky="nsew")
            self.total_labels.append(lbl)

        self._update_totals()

    def _on_cb_press(self, event, var):
        """チェックボックスを押したとき：ドラッグ開始。
        この時点ではまだ変数が切り替わっていないので、
        「押した後の値 = 現在の逆」をドラッグ値として記憶する。"""
        self._drag_value = not var.get()
        self._dragging = True

    def _on_cb_motion(self, event):
        """ドラッグ中：カーソル下のチェックボックスに同じ値を適用する"""
        if not self._dragging or self._drag_value is None:
            return
        # マウスの絶対座標からカーソル直下のウィジェットを取得
        widget = event.widget.winfo_containing(event.x_root, event.y_root)
        if widget in self._drag_targets:
            v = self._drag_targets[widget]
            # 値が変わる場合だけ更新（無駄な再描画を避ける）
            if v.get() != self._drag_value:
                v.set(self._drag_value)
                self._update_totals()

    def _on_cb_release(self, event):
        """マウスを離したとき：ドラッグ終了"""
        self._dragging = False
        self._drag_value = None

    def _update_totals(self):
        """合計を再計算して表示する"""
        if not hasattr(self, "total_labels"):
            return
        totals = [0, 0, 0, 0]  # 宿泊・朝・昼・夕
        for day, data in self.day_data.items():
            totals[0] += data["stay"].get()
            totals[1] += data["breakfast"].get()
            totals[2] += data["lunch"].get()
            totals[3] += data["dinner"].get()
        for lbl, val in zip(self.total_labels, totals):
            lbl.config(text=str(val))

    def _prev_resident(self):
        """前の入居者に切り替える"""
        idx = self.resident_cb.current()
        if idx > 0:
            self.resident_cb.current(idx - 1)
            self.reload()

    def _next_resident(self):
        """次の入居者に切り替える"""
        idx = self.resident_cb.current()
        if idx < len(self.residents) - 1:
            self.resident_cb.current(idx + 1)
            self.reload()

    def _update_status_bar(self):
        """入力状況バーを更新する（何名中何名入力済みか）"""
        if not self.residents:
            return
        year = self.year.get()
        month = self.month.get()
        prefix = f"{year:04d}-{month:02d}-"
        conn = sqlite3.connect(DAILY_DB)
        c = conn.cursor()
        done = 0
        total = len(self.residents)
        for res_id, _ in self.residents:
            c.execute("""
                SELECT COUNT(*) FROM daily_records
                WHERE resident_id = ? AND record_date LIKE ?
            """, (res_id, prefix + "%"))
            if c.fetchone()[0] > 0:
                done += 1
        conn.close()

        if done == total:
            self.status_bar.config(
                text=f"✅ 全員入力済み　{done} 名 / {total} 名",
                bg="#e8f4e8", fg="#2c5f2e")
        else:
            self.status_bar.config(
                text=f"⚠️ 入力済 {done} 名 / {total} 名　（未入力 {total - done} 名）",
                bg="#fff3cd", fg="#856404")

    def save(self):
        """現在の画面データを保存する"""
        res_id = self.resident_id.get()
        if not res_id:
            messagebox.showwarning("警告", "入居者を選択してください。")
            return
        save_records(res_id, self.year.get(), self.month.get(), self.day_data)
        self._update_status_bar()
        messagebox.showinfo("保存完了", "利用実績を保存しました。")

# ============================================================
# タブ2：外泊登録
# ============================================================
class AbsenceTab(tk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, bg="#f0f4f8")
        self.on_change = on_change
        self.residents = []
        self._build()

    def _build(self):
        """外泊登録画面を構築する"""
        # ヘッダー
        header = tk.Frame(self, bg="#2c5f8a")
        header.pack(fill="x")
        tk.Label(header, text="外泊登録", font=("メイリオ", 14, "bold"),
                 bg="#2c5f8a", fg="white").pack(side="left", padx=16, pady=10)

        body = tk.Frame(self, bg="#f0f4f8")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # 入力フォーム
        form = tk.LabelFrame(body, text="新規登録", bg="#f0f4f8",
                             font=("メイリオ", 11))
        form.pack(fill="x", pady=(0, 16))

        tk.Label(form, text="入居者：", bg="#f0f4f8",
                 font=("メイリオ", 11)).grid(row=0, column=0, padx=8, pady=8,
                                             sticky="e")
        self.res_cb = ttk.Combobox(form, width=14, font=("メイリオ", 11),
                                    state="readonly")
        self.res_cb.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.res_cb.bind("<<ComboboxSelected>>", lambda e: self._load_list())

        tk.Label(form, text="外泊開始日：", bg="#f0f4f8",
                 font=("メイリオ", 11)).grid(row=0, column=2, padx=8, pady=8,
                                             sticky="e")
        self.leave_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(form, textvariable=self.leave_var, width=12,
                 font=("メイリオ", 11)).grid(row=0, column=3, padx=8, pady=8)

        tk.Label(form, text="帰宅日：", bg="#f0f4f8",
                 font=("メイリオ", 11)).grid(row=0, column=4, padx=8, pady=8,
                                             sticky="e")
        self.return_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(form, textvariable=self.return_var, width=12,
                 font=("メイリオ", 11)).grid(row=0, column=5, padx=8, pady=8)

        tk.Label(form, text="備考：", bg="#f0f4f8",
                 font=("メイリオ", 11)).grid(row=1, column=0, padx=8, pady=8,
                                             sticky="e")
        self.note_var = tk.StringVar()
        tk.Entry(form, textvariable=self.note_var, width=40,
                 font=("メイリオ", 11)).grid(row=1, column=1, columnspan=4,
                                             padx=8, pady=8, sticky="ew")

        tk.Button(form, text="登録", font=("メイリオ", 11, "bold"),
                  bg="#2c5f8a", fg="white", relief="flat", padx=16,
                  command=self._add).grid(row=1, column=5, padx=8, pady=8)

        tk.Label(form, text="※日付はYYYY-MM-DD形式で入力してください",
                 bg="#f0f4f8", fg="#888", font=("メイリオ", 9)).grid(
            row=2, column=0, columnspan=6, padx=8, pady=2, sticky="w")

        # 登録済み一覧
        list_frame = tk.LabelFrame(body, text="登録済み外泊一覧", bg="#f0f4f8",
                                   font=("メイリオ", 11))
        list_frame.pack(fill="both", expand=True)

        cols = ("id", "開始日", "帰宅日", "備考")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings",
                                  height=12)
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("id", width=40)
        self.tree.column("開始日", width=120)
        self.tree.column("帰宅日", width=120)
        self.tree.column("備考", width=300)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Button(list_frame, text="選択した外泊を削除",
                  font=("メイリオ", 11), bg="#e53935", fg="white",
                  relief="flat", padx=12,
                  command=self._delete).pack(pady=(0, 8))

        self._load_residents()

    def _load_residents(self):
        """入居者をコンボボックスに読み込む"""
        self.residents = get_residents()
        if not self.residents:
            return
        self.res_cb["values"] = [r[1] for r in self.residents]
        self.res_cb.current(0)
        self._load_list()

    def _load_list(self):
        """選択中の入居者の外泊一覧を更新する"""
        idx = self.res_cb.current()
        if idx < 0 or not self.residents:
            return
        res_id = self.residents[idx][0]
        rows = get_all_absences(res_id)
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in rows:
            self.tree.insert("", "end", values=r)

    def _add(self):
        """外泊を登録する"""
        idx = self.res_cb.current()
        if idx < 0:
            messagebox.showwarning("警告", "入居者を選択してください。")
            return
        try:
            leave = date.fromisoformat(self.leave_var.get())
            ret = date.fromisoformat(self.return_var.get())
        except ValueError:
            messagebox.showerror("エラー", "日付はYYYY-MM-DD形式で入力してください。\n例：2026-04-15")
            return
        if ret < leave:
            messagebox.showerror("エラー", "帰宅日は外泊開始日以降にしてください。")
            return

        res_id = self.residents[idx][0]
        add_absence(res_id, leave.isoformat(), ret.isoformat(),
                    self.note_var.get())
        self._load_list()
        if self.on_change:
            self.on_change()
        messagebox.showinfo("登録完了", "外泊を登録しました。")

    def _delete(self):
        """選択した外泊記録を削除する"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("警告", "削除する外泊を選択してください。")
            return
        if not messagebox.askyesno("確認", "選択した外泊記録を削除しますか？"):
            return
        for item in selected:
            absence_id = self.tree.item(item)["values"][0]
            delete_absence(absence_id)
        self._load_list()
        if self.on_change:
            self.on_change()

# ============================================================
# タブ3：設定
# ============================================================
class SettingsTab(tk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, bg="#f0f4f8")
        self.on_change = on_change
        self._build()

    def _build(self):
        """設定画面を構築する"""
        header = tk.Frame(self, bg="#2c5f8a")
        header.pack(fill="x")
        tk.Label(header, text="設定", font=("メイリオ", 14, "bold"),
                 bg="#2c5f8a", fg="white").pack(side="left", padx=16, pady=10)

        body = tk.Frame(self, bg="#f0f4f8")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        frame = tk.LabelFrame(body, text="昼食提供曜日",
                              bg="#f0f4f8", font=("メイリオ", 12))
        frame.pack(fill="x", pady=10)

        active = get_lunch_days()
        weekday_names = ["月", "火", "水", "木", "金", "土", "日"]
        self.wd_vars = []

        for wd, name in enumerate(weekday_names):
            var = tk.BooleanVar(value=(wd in active))
            self.wd_vars.append(var)
            tk.Checkbutton(frame, text=name, variable=var,
                           bg="#f0f4f8",
                           font=("メイリオ", 13)).pack(side="left", padx=12,
                                                        pady=12)

        tk.Button(body, text="保存", font=("メイリオ", 12, "bold"),
                  bg="#2c5f8a", fg="white", relief="flat", padx=20, pady=6,
                  command=self._save).pack(pady=16)

    def _save(self):
        """昼食曜日設定を保存する"""
        active = {wd for wd, var in enumerate(self.wd_vars) if var.get()}
        save_lunch_days(active)
        if self.on_change:
            self.on_change()
        messagebox.showinfo("保存完了", "昼食提供曜日を保存しました。")

# ============================================================
# タブ4：月次集計
# ============================================================
class SummaryTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f0f4f8")
        self._build()

    def _build(self):
        """月次集計画面を構築する"""
        header = tk.Frame(self, bg="#2c5f8a")
        header.pack(fill="x")
        tk.Label(header, text="月次集計", font=("メイリオ", 14, "bold"),
                 bg="#2c5f8a", fg="white").pack(side="left", padx=16, pady=10)

        ctrl = tk.Frame(header, bg="#2c5f8a")
        ctrl.pack(side="right", padx=10, pady=8)

        import os as _os
        today = date.today()
        try:
            _y = int(_os.environ.get("GH_TARGET_YEAR",  today.year))
            _m = int(_os.environ.get("GH_TARGET_MONTH", today.month))
        except (ValueError, TypeError):
            _y, _m = today.year, today.month
        self.year  = tk.IntVar(value=_y)
        self.month = tk.IntVar(value=_m)

        tk.Label(ctrl, text="年：", bg="#2c5f8a", fg="white",
                 font=("メイリオ", 11)).pack(side="left")
        tk.Spinbox(ctrl, from_=2020, to=2099, textvariable=self.year,
                   width=6, font=("メイリオ", 11)).pack(side="left")

        tk.Label(ctrl, text="月：", bg="#2c5f8a", fg="white",
                 font=("メイリオ", 11)).pack(side="left", padx=(8, 0))
        tk.Spinbox(ctrl, from_=1, to=12, textvariable=self.month,
                   width=4, font=("メイリオ", 11)).pack(side="left")

        tk.Button(ctrl, text="集計表示", font=("メイリオ", 11, "bold"),
                  bg="#4caf50", fg="white", relief="flat", padx=12,
                  command=self._show).pack(side="left", padx=(16, 0))

        # 入力状況サマリーバー
        self.status_bar = tk.Label(self, text="", font=("メイリオ", 11),
                                   bg="#e8f4e8", fg="#2c5f2e", anchor="w",
                                   padx=16, pady=6)
        self.status_bar.pack(fill="x")

        # 集計テーブル
        frame = tk.Frame(self, bg="#f0f4f8")
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("氏名", "宿泊日数", "朝食回数", "昼食回数", "夕食回数", "状況")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                  height=20)
        style = ttk.Style()
        style.configure("Treeview", font=("メイリオ", 11), rowheight=28)
        style.configure("Treeview.Heading", font=("メイリオ", 11, "bold"))

        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center", width=120)
        self.tree.column("氏名", width=180)
        self.tree.column("状況", width=90)
        self.tree.pack(fill="both", expand=True)

        # 未入力行の色設定
        self.tree.tag_configure("未入力", background="#fff3cd")

    def _show(self):
        """集計を実行して表示する"""
        year = self.year.get()
        month = self.month.get()
        residents = get_residents()

        for row in self.tree.get_children():
            self.tree.delete(row)

        prefix = f"{year:04d}-{month:02d}-"
        conn = sqlite3.connect(DAILY_DB)
        c = conn.cursor()

        total = len(residents)
        done = 0

        for res_id, name in residents:
            # 集計値を取得
            c.execute("""
                SELECT
                    SUM(stay), SUM(breakfast), SUM(lunch), SUM(dinner),
                    COUNT(*)
                FROM daily_records
                WHERE resident_id = ? AND record_date LIKE ?
            """, (res_id, prefix + "%"))
            row = c.fetchone()
            st = row[0] or 0
            bf = row[1] or 0
            lc = row[2] or 0
            dn = row[3] or 0
            count = row[4] or 0  # 保存済みレコード件数

            # 入力済み判定（1件以上保存されていれば入力済み）
            if count > 0:
                status = "✅ 入力済"
                done += 1
                tag = ""
            else:
                status = "⬜ 未入力"
                tag = "未入力"

            self.tree.insert("", "end", values=(name, st, bf, lc, dn, status),
                             tags=(tag,))

        conn.close()

        # 状況バーを更新
        if total == 0:
            self.status_bar.config(text="入居者が登録されていません")
        elif done == total:
            self.status_bar.config(
                text=f"✅ 全員入力済み　{done} 名 / {total} 名",
                bg="#e8f4e8", fg="#2c5f2e")
        else:
            remaining = total - done
            self.status_bar.config(
                text=f"⚠️ 未入力あり　入力済 {done} 名 / {total} 名　（未入力 {remaining} 名）",
                bg="#fff3cd", fg="#856404")

# ============================================================
# 起動
# ============================================================
if __name__ == "__main__":
    setup()
    app = App()
    app.mainloop()
