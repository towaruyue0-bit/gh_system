# =============================================================================
# 入居管理マスターアプリ
# グループホーム 入居者情報管理システム
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
PRIVATE_ROOT  = r"C:\GH_Data"  # 個人情報を保管する安全フォルダ（OneDrive・Claude非対応）
DATA_DIR      = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR    = os.path.join(PRIVATE_ROOT, "backups")
APP_DIR       = os.path.join(BASE_DIR, "residents_app")
DB_PATH       = os.path.join(DATA_DIR, "residents.db")
MAX_BACKUPS   = 10  # バックアップの最大保持数

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# =============================================================================
# 初期セットアップ関数
# =============================================================================

def setup_directories():
    """起動時に必要なフォルダが無ければ自動作成する"""
    for d in [DATA_DIR, BACKUP_DIR, APP_DIR]:
        os.makedirs(d, exist_ok=True)


def setup_database():
    """データベースとテーブルが無ければ自動作成する"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS residents (
            id                        INTEGER PRIMARY KEY AUTOINCREMENT,
            name                      TEXT    NOT NULL,
            furigana                  TEXT,
            room_number               TEXT,
            birthdate                 TEXT,
            move_in_date              TEXT,
            move_out_date             TEXT,
            disability_grade          INTEGER,
            rent                      INTEGER,
            housing_subsidy           INTEGER DEFAULT 0,
            recipient_number          TEXT,
            emergency_contact_name    TEXT,
            emergency_contact_phone   TEXT,
            emergency_contact_relation TEXT,
            memo                      TEXT,
            status                    TEXT    DEFAULT '入居中',
            created_at                TEXT,
            updated_at                TEXT
        )
    """)
    # resident_code カラムを後から追加（すでに存在する場合はスキップ）
    try:
        c.execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()


def do_backup():
    """
    起動時にDBをバックアップする。
    backups フォルダ内のファイルが MAX_BACKUPS を超えたら古い順に削除する。
    """
    if not os.path.exists(DB_PATH):
        return  # DBがまだ存在しない場合はスキップ

    # タイムスタンプ付きのバックアップファイル名を生成
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(DB_PATH, backup_file)

    # 古いバックアップを削除（MAX_BACKUPS 個を超えた分）
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))

# =============================================================================
# ユーティリティ関数
# =============================================================================

def calc_age(birthdate_str):
    """
    生年月日の文字列（YYYY-MM-DD）から現在の年齢を計算して返す。
    計算できない場合は空文字を返す。
    """
    if not birthdate_str:
        return ""
    try:
        bd    = date.fromisoformat(birthdate_str.strip())
        today = date.today()
        age   = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        return age
    except ValueError:
        return ""


def get_conn():
    """SQLite への接続を返す（行を辞書形式で取得できるよう Row ファクトリを設定）"""
    conn             = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def generate_next_code(conn):
    """
    DB に登録済みのコードを確認し、次の利用者コードを生成して返す。
    形式は A01, A02, A03... の連番。
    すでに割り当てた最大番号の次を返すので、欠番は埋めない。

    引数:
        conn: sqlite3 の接続（row_factory=sqlite3.Row 必須）

    戻り値:
        str: 次のコード（例: 'A03'）
    """
    rows = conn.execute(
        "SELECT resident_code FROM residents WHERE resident_code LIKE 'A%'"
    ).fetchall()
    max_num = 0
    for row in rows:
        code = row["resident_code"]
        if code and len(code) >= 2:
            try:
                num = int(code[1:])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"A{max_num + 1:02d}"


# =============================================================================
# 退居処理ダイアログ
# =============================================================================

class MoveOutDialog(tk.Toplevel):
    """退居日を入力して status を「退居済」に変更するダイアログ"""

    def __init__(self, parent, resident_id, resident_name):
        super().__init__(parent)
        self.parent       = parent
        self.resident_id  = resident_id
        self.resident_name = resident_name
        self.result       = False  # 処理が完了したか

        self.title("退居処理")
        self.resizable(False, False)
        self.grab_set()  # モーダルにする
        self._build()
        self._center(parent)

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        """UI を構築する"""
        pad = {"padx": 20, "pady": 8}

        # 説明メッセージ
        tk.Label(
            self,
            text=f"「{self.resident_name}」を退居処理します。\n退居日を入力してください。",
            font=FONT, justify="left"
        ).pack(**pad)

        # 退居日入力
        frame = tk.Frame(self)
        frame.pack(**pad)
        tk.Label(frame, text="退居日（YYYY-MM-DD）：", font=FONT).pack(side="left")
        self.date_var = tk.StringVar(value=date.today().isoformat())
        tk.Entry(frame, textvariable=self.date_var, font=FONT, width=14).pack(side="left")

        # ボタン
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=12)
        tk.Button(
            btn_frame, text="退居確定", font=FONT_BOLD,
            bg="#FF5722", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2", command=self._confirm
        ).pack(side="left", padx=10)
        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self.destroy
        ).pack(side="left", padx=10)

    def _confirm(self):
        """退居日を検証して DB を更新する"""
        move_out = self.date_var.get().strip()

        # 日付の形式チェック
        try:
            date.fromisoformat(move_out)
        except ValueError:
            messagebox.showwarning(
                "入力エラー", "退居日の形式が正しくありません。\n例: 2024-03-31", parent=self
            )
            return

        # 確認メッセージ
        ok = messagebox.askyesno(
            "確認",
            f"退居日：{move_out}\nで退居処理を行います。よろしいですか？",
            parent=self
        )
        if not ok:
            return

        try:
            now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = get_conn()
            conn.execute(
                """
                UPDATE residents
                SET status = '退居済', move_out_date = ?, updated_at = ?
                WHERE id = ?
                """,
                (move_out, now, self.resident_id)
            )
            conn.commit()
            conn.close()
            self.result = True
            self.destroy()
        except Exception as e:
            messagebox.showerror("エラー", f"退居処理に失敗しました。\n{e}", parent=self)

# =============================================================================
# 登録・編集フォームダイアログ
# =============================================================================

class ResidentFormDialog(tk.Toplevel):
    """入居者の新規登録・編集を行うフォームダイアログ"""

    def __init__(self, parent, resident_id=None):
        super().__init__(parent)
        self.parent      = parent
        self.resident_id = resident_id  # None なら新規登録、値があれば編集
        self.result      = False        # 保存が完了したか

        self.title("新規登録" if resident_id is None else "入居者編集")
        self.resizable(False, False)
        self.grab_set()  # モーダルにする

        self._build_form()
        self._load_data()   # 編集モード時にデータを読み込む
        # 新規登録でコードが未設定の場合は自動生成して表示する
        if resident_id is None:
            conn = get_conn()
            self.vars["resident_code"].set(generate_next_code(conn))
            conn.close()
        self._center(parent)

    def _center(self, parent):
        """ダイアログを親ウィンドウの中央に配置する"""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _build_form(self):
        """スクロール可能なフォームUIを構築する"""

        # --- スクロール可能なコンテナ ---
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)

        canvas    = tk.Canvas(container, width=500, height=560)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.sf   = tk.Frame(canvas)  # スクロール対象フレーム

        self.sf.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.sf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # マウスホイールでスクロール
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units")
        )

        # --- フィールドの定義 ---
        f   = self.sf
        pad = {"padx": 12, "pady": 4}
        LW  = 20  # ラベル幅

        self.vars = {}  # 各入力値を格納する変数辞書

        def lbl(text, row, bold=False):
            """ラベルを配置するヘルパー"""
            font = FONT_BOLD if bold else FONT
            tk.Label(f, text=text, font=font, anchor="e", width=LW).grid(
                row=row, column=0, **pad, sticky="e"
            )

        def entry(key, row, width=28):
            """テキスト入力フィールドを配置するヘルパー"""
            self.vars[key] = tk.StringVar()
            tk.Entry(f, textvariable=self.vars[key], font=FONT, width=width).grid(
                row=row, column=1, **pad, sticky="w"
            )

        # ── 基本情報 ──────────────────────────────────────────────
        tk.Label(f, text="── 基本情報 ──", font=FONT_BOLD, fg="#555").grid(
            row=0, column=0, columnspan=2, pady=(12, 4)
        )

        # 氏名（必須）
        lbl("氏名 *", 1)
        entry("name", 1)

        # ふりがな
        lbl("ふりがな", 2)
        entry("furigana", 2)

        # 利用者コード（スプレッドシート連携で名前の代わりに使う識別コード）
        lbl("利用者コード", 3)
        code_frame = tk.Frame(f)
        code_frame.grid(row=3, column=1, **pad, sticky="w")
        self.vars["resident_code"] = tk.StringVar()
        tk.Entry(
            code_frame, textvariable=self.vars["resident_code"],
            font=FONT, width=8
        ).pack(side="left")
        tk.Label(
            code_frame, text="  例：A01（クラウド連携用・自動割り当て）",
            font=FONT_SMALL, fg="gray"
        ).pack(side="left")

        # 部屋番号
        lbl("部屋番号", 4)
        entry("room_number", 4, width=10)

        # 生年月日 + 年齢の自動表示
        lbl("生年月日", 5)
        bd_frame = tk.Frame(f)
        bd_frame.grid(row=5, column=1, **pad, sticky="w")
        self.vars["birthdate"] = tk.StringVar()
        tk.Entry(
            bd_frame, textvariable=self.vars["birthdate"], font=FONT, width=14
        ).pack(side="left")
        tk.Label(bd_frame, text="  例：1980-04-01", font=FONT_SMALL, fg="gray").pack(side="left")
        self.age_label = tk.Label(bd_frame, text="", font=FONT, fg="#1565C0")
        self.age_label.pack(side="left", padx=6)
        # 入力のたびに年齢を自動計算
        self.vars["birthdate"].trace_add("write", self._update_age)

        # 入居日
        lbl("入居日", 6)
        id_frame = tk.Frame(f)
        id_frame.grid(row=6, column=1, **pad, sticky="w")
        self.vars["move_in_date"] = tk.StringVar()
        tk.Entry(
            id_frame, textvariable=self.vars["move_in_date"], font=FONT, width=14
        ).pack(side="left")
        tk.Label(id_frame, text="  例：2020-04-01", font=FONT_SMALL, fg="gray").pack(side="left")

        # 退居日
        lbl("退居日", 7)
        od_frame = tk.Frame(f)
        od_frame.grid(row=7, column=1, **pad, sticky="w")
        self.vars["move_out_date"] = tk.StringVar()
        tk.Entry(
            od_frame, textvariable=self.vars["move_out_date"], font=FONT, width=14
        ).pack(side="left")
        tk.Label(od_frame, text="  未入居中は空欄", font=FONT_SMALL, fg="gray").pack(side="left")

        # ── 障害・費用情報 ──────────────────────────────────────
        tk.Label(f, text="── 障害・費用情報 ──", font=FONT_BOLD, fg="#555").grid(
            row=8, column=0, columnspan=2, pady=(12, 4)
        )

        # 障害支援区分
        lbl("障害支援区分（1〜6）", 9)
        self.vars["disability_grade"] = tk.StringVar()
        ttk.Combobox(
            f, textvariable=self.vars["disability_grade"], font=FONT,
            values=["", "1", "2", "3", "4", "5", "6"], width=5, state="readonly"
        ).grid(row=9, column=1, **pad, sticky="w")

        # 家賃
        lbl("家賃（円）", 10)
        rent_frame = tk.Frame(f)
        rent_frame.grid(row=10, column=1, **pad, sticky="w")
        self.vars["rent"] = tk.StringVar()
        tk.Entry(
            rent_frame, textvariable=self.vars["rent"], font=FONT, width=12
        ).pack(side="left")

        # 住宅補助
        lbl("住宅補助", 11)
        self.vars["housing_subsidy"] = tk.IntVar()
        tk.Checkbutton(
            f, text="あり", variable=self.vars["housing_subsidy"], font=FONT
        ).grid(row=11, column=1, **pad, sticky="w")

        # 受給者証番号
        lbl("受給者証番号", 12)
        entry("recipient_number", 12, width=20)

        # ── 緊急連絡先 ──────────────────────────────────────────
        tk.Label(f, text="── 緊急連絡先 ──", font=FONT_BOLD, fg="#555").grid(
            row=13, column=0, columnspan=2, pady=(12, 4)
        )

        lbl("氏名", 14)
        entry("emergency_contact_name", 14, width=20)

        lbl("電話番号", 15)
        entry("emergency_contact_phone", 15, width=16)

        lbl("続柄", 16)
        entry("emergency_contact_relation", 16, width=12)

        # ── その他 ────────────────────────────────────────────
        tk.Label(f, text="── その他 ──", font=FONT_BOLD, fg="#555").grid(
            row=17, column=0, columnspan=2, pady=(12, 4)
        )

        # メモ
        lbl("メモ", 18)
        self.memo_text = tk.Text(f, font=FONT, width=28, height=4, relief="solid", bd=1)
        self.memo_text.grid(row=18, column=1, **pad, sticky="w")

        # ステータス
        lbl("ステータス", 19)
        self.vars["status"] = tk.StringVar(value="入居中")
        ttk.Combobox(
            f, textvariable=self.vars["status"], font=FONT,
            values=["入居中", "体験利用中", "退居済"], width=12, state="readonly"
        ).grid(row=19, column=1, **pad, sticky="w")

        # ── ボタンエリア ──────────────────────────────────────
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", pady=10)

        tk.Button(
            btn_frame, text="  保存  ", font=FONT_BOLD,
            bg="#388E3C", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2", command=self._save
        ).pack(side="left", padx=20)

        tk.Button(
            btn_frame, text="キャンセル", font=FONT,
            relief="flat", padx=10, pady=4, cursor="hand2",
            command=self.destroy
        ).pack(side="right", padx=20)

    def _update_age(self, *args):
        """生年月日が変更されるたびに年齢を自動計算して表示する"""
        age = calc_age(self.vars["birthdate"].get())
        self.age_label.config(text=f"（{age}歳）" if age != "" else "")

    def _load_data(self):
        """編集モード時に既存のデータをフォームに読み込む"""
        if self.resident_id is None:
            return
        try:
            conn = get_conn()
            row  = conn.execute(
                "SELECT * FROM residents WHERE id = ?", (self.resident_id,)
            ).fetchone()
            conn.close()

            if row is None:
                return

            # 文字列フィールドをセット
            str_keys = [
                "name", "furigana", "resident_code", "room_number", "birthdate",
                "move_in_date", "move_out_date", "recipient_number",
                "emergency_contact_name", "emergency_contact_phone",
                "emergency_contact_relation", "status"
            ]
            for key in str_keys:
                if row[key] is not None:
                    self.vars[key].set(row[key])

            # 障害支援区分（数値 → 文字列）
            if row["disability_grade"] is not None:
                self.vars["disability_grade"].set(str(row["disability_grade"]))

            # 家賃（数値 → 文字列）
            if row["rent"] is not None:
                self.vars["rent"].set(str(row["rent"]))

            # 住宅補助（0/1）
            self.vars["housing_subsidy"].set(row["housing_subsidy"] or 0)

            # メモ
            if row["memo"]:
                self.memo_text.insert("1.0", row["memo"])

        except Exception as e:
            messagebox.showerror("エラー", f"データの読み込みに失敗しました。\n{e}", parent=self)

    def _validate(self):
        """入力内容を検証する。問題があればメッセージを表示して False を返す"""

        # 氏名（必須）
        if not self.vars["name"].get().strip():
            messagebox.showwarning("入力エラー", "氏名は必須項目です。", parent=self)
            return False

        # 日付フィールドの形式チェック
        date_fields = {
            "birthdate":     "生年月日",
            "move_in_date":  "入居日",
            "move_out_date": "退居日",
        }
        for key, label in date_fields.items():
            val = self.vars[key].get().strip()
            if val:
                try:
                    date.fromisoformat(val)
                except ValueError:
                    messagebox.showwarning(
                        "入力エラー",
                        f"{label} の形式が正しくありません。\n例: 1980-04-01",
                        parent=self
                    )
                    return False

        # 家賃（数値チェック）
        rent_str = self.vars["rent"].get().strip()
        if rent_str:
            try:
                int(rent_str)
            except ValueError:
                messagebox.showwarning("入力エラー", "家賃は整数で入力してください。", parent=self)
                return False

        return True

    def _save(self):
        """フォームの内容を検証して DB に保存する"""
        if not self._validate():
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 各フィールドの値を収集（空文字は None に変換）
        def sv(key):
            v = self.vars[key].get().strip()
            return v if v else None

        data = {
            "name":                       self.vars["name"].get().strip(),
            "furigana":                   sv("furigana"),
            "room_number":                sv("room_number"),
            "birthdate":                  sv("birthdate"),
            "move_in_date":               sv("move_in_date"),
            "move_out_date":              sv("move_out_date"),
            "disability_grade":           int(self.vars["disability_grade"].get()) if sv("disability_grade") else None,
            "rent":                       int(sv("rent")) if sv("rent") else None,
            "housing_subsidy":            self.vars["housing_subsidy"].get(),
            "recipient_number":           sv("recipient_number"),
            "emergency_contact_name":     sv("emergency_contact_name"),
            "emergency_contact_phone":    sv("emergency_contact_phone"),
            "emergency_contact_relation": sv("emergency_contact_relation"),
            "memo":                       self.memo_text.get("1.0", "end-1c").strip() or None,
            "status":                     self.vars["status"].get(),
        }

        try:
            conn = get_conn()

            # resident_code が空欄の場合は自動生成する
            resident_code = sv("resident_code") or generate_next_code(conn)
            data["resident_code"] = resident_code

            if self.resident_id is None:
                # 新規登録
                conn.execute(
                    """
                    INSERT INTO residents (
                        name, furigana, resident_code, room_number, birthdate,
                        move_in_date, move_out_date, disability_grade,
                        rent, housing_subsidy, recipient_number,
                        emergency_contact_name, emergency_contact_phone,
                        emergency_contact_relation, memo, status,
                        created_at, updated_at
                    ) VALUES (
                        :name, :furigana, :resident_code, :room_number, :birthdate,
                        :move_in_date, :move_out_date, :disability_grade,
                        :rent, :housing_subsidy, :recipient_number,
                        :emergency_contact_name, :emergency_contact_phone,
                        :emergency_contact_relation, :memo, :status,
                        :now, :now
                    )
                    """,
                    {**data, "now": now}
                )
            else:
                # 既存レコードの更新
                conn.execute(
                    """
                    UPDATE residents SET
                        name                       = :name,
                        furigana                   = :furigana,
                        resident_code              = :resident_code,
                        room_number                = :room_number,
                        birthdate                  = :birthdate,
                        move_in_date               = :move_in_date,
                        move_out_date              = :move_out_date,
                        disability_grade           = :disability_grade,
                        rent                       = :rent,
                        housing_subsidy            = :housing_subsidy,
                        recipient_number           = :recipient_number,
                        emergency_contact_name     = :emergency_contact_name,
                        emergency_contact_phone    = :emergency_contact_phone,
                        emergency_contact_relation = :emergency_contact_relation,
                        memo                       = :memo,
                        status                     = :status,
                        updated_at                 = :now
                    WHERE id = :id
                    """,
                    {**data, "now": now, "id": self.resident_id}
                )

            conn.commit()
            conn.close()
            self.result = True
            self.destroy()

        except Exception as e:
            messagebox.showerror("エラー", f"保存に失敗しました。\n{e}", parent=self)

# =============================================================================
# メインアプリケーション（一覧画面）
# =============================================================================

class MainApp(tk.Tk):
    """入居管理マスターアプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("入居管理マスター")
        self.geometry("900x600")
        self.resizable(True, True)
        self.configure(bg="#F5F5F5")

        # 退居済も表示するかどうかのフラグ
        self.show_all = tk.BooleanVar(value=False)

        self._build_ui()
        self._load_list()

    def _build_ui(self):
        """メインウィンドウのUIを構築する"""

        # Treeviewスタイル設定（行の高さ・フォント）
        style = ttk.Style()
        style.configure("Treeview", rowheight=28, font=FONT)
        style.configure("Treeview.Heading", font=FONT_BOLD)

        # ── タイトルバー ───────────────────────────────────
        title_frame = tk.Frame(self, bg="#1565C0", height=50)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        tk.Label(
            title_frame, text="入居管理マスター",
            font=FONT_TITLE, bg="#1565C0", fg="white"
        ).pack(side="left", padx=16, pady=10)

        # ── ツールバー（ボタン・フィルタ） ─────────────────
        toolbar = tk.Frame(self, bg="#E3F2FD", pady=6)
        toolbar.pack(fill="x", padx=0)

        tk.Button(
            toolbar, text="＋ 新規登録", font=FONT_BOLD,
            bg="#1976D2", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._open_new
        ).pack(side="left", padx=10, pady=4)

        tk.Button(
            toolbar, text="✎ 編集", font=FONT,
            bg="#FFA000", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._open_edit
        ).pack(side="left", padx=4, pady=4)

        tk.Button(
            toolbar, text="退居処理", font=FONT,
            bg="#E53935", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._open_moveout
        ).pack(side="left", padx=4, pady=4)

        tk.Button(
            toolbar, text="コード一括割り当て", font=FONT,
            bg="#5C6BC0", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._bulk_assign_codes
        ).pack(side="left", padx=4, pady=4)

        self.reinstate_btn = tk.Button(
            toolbar, text="入居中に戻す", font=FONT,
            bg="#00796B", fg="white", relief="flat",
            padx=10, pady=4, cursor="hand2",
            command=self._reinstate
        )
        # 退居済選択時のみ表示するため初期状態では pack しない

        # 退居済表示トグル
        tk.Checkbutton(
            toolbar, text="退居済も表示する",
            variable=self.show_all, font=FONT,
            bg="#E3F2FD", command=self._load_list
        ).pack(side="right", padx=16)

        # ── 入居者一覧テーブル ───────────────────────────
        list_frame = tk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # テーブルのカラム定義
        columns = ("id", "resident_code", "room_number", "name", "furigana", "birthdate",
                   "age", "move_in_date", "disability_grade", "status")

        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", selectmode="browse"
        )

        # カラムのヘッダーと幅を設定
        col_config = [
            ("id",               "ID",       40),
            ("resident_code",    "コード",   60),
            ("room_number",      "部屋",     55),
            ("name",             "氏名",    120),
            ("furigana",         "ふりがな", 130),
            ("birthdate",        "生年月日",  95),
            ("age",              "年齢",     50),
            ("move_in_date",     "入居日",   95),
            ("disability_grade", "区分",     45),
            ("status",           "状態",     70),
        ]
        for col, heading, width in col_config:
            self.tree.heading(col, text=heading, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor="center")

        # 氏名・ふりがなは左寄せ
        self.tree.column("name",     anchor="w")
        self.tree.column("furigana", anchor="w")

        # スクロールバー
        vsb = ttk.Scrollbar(list_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # 行の背景色（偶数/奇数で交互、体験利用中は橙色、退居済は文字色グレー）
        self.tree.tag_configure("even",    background="#FFFFFF")
        self.tree.tag_configure("odd",     background="#F0F4FA")
        self.tree.tag_configure("trial",   foreground="#8B6914")
        self.tree.tag_configure("moveout", foreground="#9E9E9E")

        # ダブルクリックで編集
        self.tree.bind("<Double-1>", lambda e: self._open_edit())

        # 選択変更で「入居中に戻す」ボタンの表示を切り替え
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # ── ステータスバー ────────────────────────────────
        self.status_var = tk.StringVar()
        tk.Label(
            self, textvariable=self.status_var,
            font=FONT_SMALL, anchor="w", bg="#E0E0E0", relief="sunken"
        ).pack(fill="x", side="bottom")

    def _load_list(self):
        """DBから入居者一覧を取得してテーブルに表示する"""
        # 既存の行を全削除
        for row in self.tree.get_children():
            self.tree.delete(row)

        try:
            conn = get_conn()

            if self.show_all.get():
                # 退居済を含む全件取得（入居中→体験利用中→退居済の順）
                rows = conn.execute(
                    """
                    SELECT * FROM residents
                    ORDER BY CASE status WHEN '入居中' THEN 0
                                        WHEN '体験利用中' THEN 1 ELSE 2 END,
                             furigana, name
                    """
                ).fetchall()
            else:
                # 入居中・体験利用中を取得（入居中を先に）
                rows = conn.execute(
                    """
                    SELECT * FROM residents
                    WHERE status IN ('入居中', '体験利用中')
                    ORDER BY CASE status WHEN '入居中' THEN 0 ELSE 1 END,
                             room_number, furigana, name
                    """
                ).fetchall()

            conn.close()

            # テーブルに行を追加
            for idx, r in enumerate(rows):
                age = calc_age(r["birthdate"])
                row_tag = "even" if idx % 2 == 0 else "odd"
                if r["status"] == "退居済":
                    tags = (row_tag, "moveout")
                elif r["status"] == "体験利用中":
                    tags = (row_tag, "trial")
                else:
                    tags = (row_tag,)
                self.tree.insert("", "end", iid=str(r["id"]), values=(
                    r["id"],
                    r["resident_code"] or "",
                    r["room_number"] or "",
                    r["name"],
                    r["furigana"] or "",
                    r["birthdate"] or "",
                    f"{age}歳" if age != "" else "",
                    r["move_in_date"] or "",
                    r["disability_grade"] or "",
                    r["status"],
                ), tags=tags)

            # ステータスバーに件数を表示
            count = len(rows)
            label = "全員" if self.show_all.get() else "入居中・体験利用中"
            self.status_var.set(f"  {label}：{count} 名")

        except Exception as e:
            messagebox.showerror("エラー", f"一覧の取得に失敗しました。\n{e}")

    def _get_selected_id(self):
        """一覧で選択中の入居者 ID を返す。未選択の場合は None を返す"""
        selected = self.tree.selection()
        if not selected:
            return None
        return int(selected[0])

    def _open_new(self):
        """新規登録ダイアログを開く"""
        dlg = ResidentFormDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            messagebox.showinfo("完了", "登録しました。")
            self._load_list()

    def _open_edit(self):
        """選択した入居者の編集ダイアログを開く"""
        rid = self._get_selected_id()
        if rid is None:
            messagebox.showwarning("未選択", "編集する入居者を一覧から選択してください。")
            return
        dlg = ResidentFormDialog(self, resident_id=rid)
        self.wait_window(dlg)
        if dlg.result:
            messagebox.showinfo("完了", "保存しました。")
            self._load_list()

    def _open_moveout(self):
        """選択した入居者の退居処理ダイアログを開く"""
        rid = self._get_selected_id()
        if rid is None:
            messagebox.showwarning("未選択", "退居処理する入居者を一覧から選択してください。")
            return

        # 対象者の氏名を取得
        try:
            conn  = get_conn()
            row   = conn.execute(
                "SELECT name, status FROM residents WHERE id = ?", (rid,)
            ).fetchone()
            conn.close()
        except Exception as e:
            messagebox.showerror("エラー", f"データの取得に失敗しました。\n{e}")
            return

        if row["status"] == "退居済":
            messagebox.showinfo("確認", "この入居者はすでに退居済です。")
            return

        dlg = MoveOutDialog(self, resident_id=rid, resident_name=row["name"])
        self.wait_window(dlg)
        if dlg.result:
            messagebox.showinfo("完了", "退居処理が完了しました。")
            self._load_list()

    def _on_select(self, event=None):
        """一覧の選択が変わったとき、退居済なら「入居中に戻す」ボタンを表示する"""
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0], "values")
            # values index 9 = status（resident_code 列追加により1つずれた）
            status = values[9] if len(values) > 9 else ""
            if status == "退居済":
                self.reinstate_btn.pack(side="left", padx=4, pady=4)
                return
        self.reinstate_btn.pack_forget()

    def _reinstate(self):
        """退居済の入居者を入居中に戻す（退居日をクリア、ステータスを入居中に変更）"""
        rid = self._get_selected_id()
        if rid is None:
            messagebox.showwarning("未選択", "入居者を一覧から選択してください。")
            return

        try:
            conn = get_conn()
            row  = conn.execute(
                "SELECT name, status FROM residents WHERE id = ?", (rid,)
            ).fetchone()
            conn.close()
        except Exception as e:
            messagebox.showerror("エラー", f"データの取得に失敗しました。\n{e}")
            return

        if row["status"] != "退居済":
            messagebox.showinfo("確認", "この入居者はすでに入居中です。")
            return

        ok = messagebox.askyesno(
            "確認",
            f"「{row['name']}」を入居中に戻します。\n退居日もクリアされます。よろしいですか？"
        )
        if not ok:
            return

        try:
            now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn = get_conn()
            conn.execute(
                """
                UPDATE residents
                SET status = '入居中', move_out_date = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, rid)
            )
            conn.commit()
            conn.close()
            messagebox.showinfo("完了", f"「{row['name']}」を入居中に戻しました。")
            self._load_list()
        except Exception as e:
            messagebox.showerror("エラー", f"処理に失敗しました。\n{e}")

    def _sort_by(self, col):
        """列ヘッダーをクリックしたときにその列でソートする"""
        rows = [(self.tree.set(item, col), item) for item in self.tree.get_children()]
        rows.sort(key=lambda x: x[0])
        for index, (_, item) in enumerate(rows):
            self.tree.move(item, "", index)

    def _bulk_assign_codes(self):
        """
        利用者コードが未設定の全利用者に A01, A02... を一括で割り当てる。
        初回導入時や新しい利用者をまとめて登録した後に使う。
        部屋番号 → ふりがなの順で並べてから番号を振る。
        """
        try:
            conn = get_conn()
            # コードが未設定（NULL または空文字）の利用者を取得
            rows = conn.execute(
                """
                SELECT id FROM residents
                WHERE (resident_code IS NULL OR resident_code = '')
                ORDER BY room_number, furigana, name, id
                """
            ).fetchall()

            if not rows:
                messagebox.showinfo("確認", "コードが未設定の利用者はいません。")
                conn.close()
                return

            count = len(rows)
            ok = messagebox.askyesno(
                "コード一括割り当て",
                f"コードが未設定の利用者が {count} 名います。\n"
                "A01, A02... の連番を自動で割り当てます。\n\n"
                "よろしいですか？"
            )
            if not ok:
                conn.close()
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for row in rows:
                code = generate_next_code(conn)
                conn.execute(
                    "UPDATE residents SET resident_code = ?, updated_at = ? WHERE id = ?",
                    (code, now, row["id"])
                )
                # コミットを都度行うことで generate_next_code が最新値を読める
                conn.commit()

            conn.close()
            messagebox.showinfo("完了", f"{count} 名に利用者コードを割り当てました。")
            self._load_list()

        except Exception as e:
            messagebox.showerror("エラー", f"一括割り当てに失敗しました。\n{e}")

# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    try:
        # 1. フォルダを自動作成
        setup_directories()

        # 2. DBとテーブルを自動作成
        setup_database()

        # 3. 起動時バックアップを実行
        do_backup()

        # 4. アプリを起動
        app = MainApp()
        app.mainloop()

    except Exception as e:
        # 予期しないエラーは日本語でメッセージを表示
        import traceback
        messagebox.showerror(
            "起動エラー",
            f"アプリの起動中にエラーが発生しました。\n\n{e}\n\n{traceback.format_exc()}"
        )
