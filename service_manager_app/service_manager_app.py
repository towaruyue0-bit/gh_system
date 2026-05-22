# =============================================================================
# サービス管理アプリ
# 外部サービス・アカウント一覧を管理する
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import datetime

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR     = r"C:\Users\Public\gh_system"
APP_DIR      = os.path.join(BASE_DIR, "service_manager_app")
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
DB_PATH      = os.path.join(DATA_DIR, "services.db")

FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 15, "bold")
FONT_SMALL = ("MS Gothic", 10)

COLOR_BG         = "#F5F7FA"
COLOR_HEADER_BG  = "#2C3E50"
COLOR_HEADER_TXT = "#FFFFFF"
COLOR_BTN_ADD    = "#27AE60"
COLOR_BTN_EDIT   = "#2980B9"
COLOR_BTN_DEL    = "#E74C3C"
COLOR_BTN_TXT    = "#FFFFFF"
COLOR_ROW_EVEN   = "#FFFFFF"
COLOR_ROW_ODD    = "#EBF5FB"
COLOR_SELECT     = "#D6EAF8"

CATEGORIES = ["コード管理", "ホスティング", "クラウドストレージ", "認証・ログイン", "メール", "その他"]
STATUSES   = ["使用中", "未設定", "停止中", "検討中"]
LOGIN_METHODS = ["Google連携", "メール＋パスワード", "GitHub連携", "Microsoftアカウント", "Apple ID", "その他"]

# =============================================================================
# DB セットアップ
# =============================================================================

def setup_database():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT    NOT NULL,
            category       TEXT,
            purpose        TEXT,
            account_email  TEXT,
            account_user   TEXT,
            login_method   TEXT,
            url            TEXT,
            connected_to   TEXT,
            status         TEXT    DEFAULT '使用中',
            memo           TEXT,
            created_at     TEXT,
            updated_at     TEXT
        )
    """)
    conn.commit()

    # 初期データ（空なら挿入）
    c.execute("SELECT COUNT(*) FROM services")
    if c.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial = [
            ("GitHub", "コード管理",
             "GHシステムのコードをクラウドに保存・バックアップ",
             "towaruyue0@gmail.com", "towaruyue0-bit",
             "Google連携", "https://github.com", "", "使用中",
             "GHシステム全体のバックアップ先。パソコンが壊れても復元できる", now, now),
            ("Netlify", "ホスティング",
             "HTMLアプリをインターネットに公開するサービス",
             "", "",
             "GitHub連携", "https://netlify.com", "GitHub", "未設定",
             "GitHubと連携してHTMLアプリを自動公開できる。アカウント・設定を要確認", now, now),
        ]
        c.executemany("""
            INSERT INTO services
              (name, category, purpose, account_email, account_user,
               login_method, url, connected_to, status, memo, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, initial)
    conn.commit()
    conn.close()

# =============================================================================
# DB 操作
# =============================================================================

def db_get_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM services ORDER BY category, name")
    rows = c.fetchall()
    conn.close()
    return rows

def db_insert(data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO services
          (name, category, purpose, account_email, account_user,
           login_method, url, connected_to, status, memo, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (*data, now, now))
    conn.commit()
    conn.close()

def db_update(sid, data):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE services SET
          name=?, category=?, purpose=?, account_email=?, account_user=?,
          login_method=?, url=?, connected_to=?, status=?, memo=?, updated_at=?
        WHERE id=?
    """, (*data, now, sid))
    conn.commit()
    conn.close()

def db_delete(sid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM services WHERE id=?", (sid,))
    conn.commit()
    conn.close()

# =============================================================================
# 編集ダイアログ
# =============================================================================

class ServiceDialog(tk.Toplevel):
    def __init__(self, parent, title, data=None):
        super().__init__(parent)
        self.title(title)
        self.result = None
        self.resizable(False, False)
        self.grab_set()
        self.configure(bg=COLOR_BG)

        fields = [
            ("サービス名 *",     "name",          "entry"),
            ("カテゴリ",        "category",      "combo", CATEGORIES),
            ("用途・説明",       "purpose",       "text"),
            ("ログインメール",    "account_email", "entry"),
            ("ユーザー名",       "account_user",  "entry"),
            ("ログイン方法",      "login_method",  "combo", LOGIN_METHODS),
            ("URL",            "url",           "entry"),
            ("連携サービス",      "connected_to",  "entry"),
            ("状態",           "status",        "combo", STATUSES),
            ("メモ",           "memo",          "text"),
        ]

        self.vars = {}
        for i, field in enumerate(fields):
            label, key, ftype = field[0], field[1], field[2]
            tk.Label(self, text=label, font=FONT, bg=COLOR_BG, anchor="w").grid(
                row=i, column=0, sticky="w", padx=12, pady=4)

            if ftype == "entry":
                var = tk.StringVar()
                tk.Entry(self, textvariable=var, font=FONT, width=38).grid(
                    row=i, column=1, sticky="w", padx=8, pady=4)
                self.vars[key] = var
            elif ftype == "combo":
                var = tk.StringVar()
                ttk.Combobox(self, textvariable=var, values=field[3],
                             font=FONT, width=36, state="readonly").grid(
                    row=i, column=1, sticky="w", padx=8, pady=4)
                self.vars[key] = var
            elif ftype == "text":
                frame = tk.Frame(self, bg=COLOR_BG)
                frame.grid(row=i, column=1, sticky="w", padx=8, pady=4)
                txt = tk.Text(frame, font=FONT, width=38, height=3,
                              relief="solid", borderwidth=1)
                txt.pack()
                self.vars[key] = txt

        # 既存データを埋める
        if data:
            keys = ["name","category","purpose","account_email","account_user",
                    "login_method","url","connected_to","status","memo"]
            for k, v in zip(keys, data):
                widget = self.vars[k]
                if isinstance(widget, tk.Text):
                    widget.delete("1.0", tk.END)
                    widget.insert("1.0", v or "")
                else:
                    widget.set(v or "")

        # ボタン
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="保存", font=FONT_BOLD, bg=COLOR_BTN_ADD,
                  fg=COLOR_BTN_TXT, width=10, command=self._save).pack(side="left", padx=8)
        tk.Button(btn_frame, text="キャンセル", font=FONT, bg="#95A5A6",
                  fg=COLOR_BTN_TXT, width=10, command=self.destroy).pack(side="left", padx=8)

        self.wait_window()

    def _save(self):
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showwarning("入力エラー", "サービス名は必須です", parent=self)
            return
        keys = ["name","category","purpose","account_email","account_user",
                "login_method","url","connected_to","status","memo"]
        result = []
        for k in keys:
            w = self.vars[k]
            if isinstance(w, tk.Text):
                result.append(w.get("1.0", tk.END).strip())
            else:
                result.append(w.get().strip())
        self.result = result
        self.destroy()

# =============================================================================
# メインウィンドウ
# =============================================================================

class ServiceManagerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("サービス管理")
        self.geometry("1050x620")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self._build_header()
        self._build_filter()
        self._build_table()
        self._build_buttons()
        self._build_detail()
        self.load_table()

    # ------------------------------------------------------------------
    def _build_header(self):
        hdr = tk.Frame(self, bg=COLOR_HEADER_BG, height=52)
        hdr.pack(fill="x")
        tk.Label(hdr, text="外部サービス・アカウント管理",
                 font=FONT_TITLE, bg=COLOR_HEADER_BG,
                 fg=COLOR_HEADER_TXT).pack(side="left", padx=16, pady=10)

    def _build_filter(self):
        bar = tk.Frame(self, bg=COLOR_BG, pady=6)
        bar.pack(fill="x", padx=12)
        tk.Label(bar, text="カテゴリ絞込:", font=FONT, bg=COLOR_BG).pack(side="left")
        self.filter_var = tk.StringVar(value="すべて")
        cats = ["すべて"] + CATEGORIES
        ttk.Combobox(bar, textvariable=self.filter_var, values=cats,
                     font=FONT, width=16, state="readonly").pack(side="left", padx=6)
        self.filter_var.trace_add("write", lambda *_: self.load_table())

        tk.Label(bar, text="  状態:", font=FONT, bg=COLOR_BG).pack(side="left")
        self.status_var = tk.StringVar(value="すべて")
        ttk.Combobox(bar, textvariable=self.status_var,
                     values=["すべて"] + STATUSES,
                     font=FONT, width=10, state="readonly").pack(side="left", padx=6)
        self.status_var.trace_add("write", lambda *_: self.load_table())

    def _build_table(self):
        frame = tk.Frame(self, bg=COLOR_BG)
        frame.pack(fill="both", expand=True, padx=12, pady=4)

        cols = ("name","category","purpose","account_email","login_method","connected_to","status")
        headers = ("サービス名","カテゴリ","用途","ログインメール","ログイン方法","連携サービス","状態")
        widths  = (130, 110, 220, 160, 110, 90, 70)

        style = ttk.Style()
        style.configure("Treeview", font=FONT, rowheight=26)
        style.configure("Treeview.Heading", font=FONT_BOLD)

        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 selectmode="browse")
        for col, hdr, w in zip(cols, headers, widths):
            self.tree.heading(col, text=hdr)
            self.tree.column(col, width=w, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("even", background=COLOR_ROW_EVEN)
        self.tree.tag_configure("odd",  background=COLOR_ROW_ODD)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda e: self._edit())

    def _build_buttons(self):
        bar = tk.Frame(self, bg=COLOR_BG)
        bar.pack(fill="x", padx=12, pady=6)
        tk.Button(bar, text="＋ 追加", font=FONT_BOLD,
                  bg=COLOR_BTN_ADD, fg=COLOR_BTN_TXT, width=10,
                  command=self._add).pack(side="left", padx=4)
        tk.Button(bar, text="✎ 編集", font=FONT_BOLD,
                  bg=COLOR_BTN_EDIT, fg=COLOR_BTN_TXT, width=10,
                  command=self._edit).pack(side="left", padx=4)
        tk.Button(bar, text="✕ 削除", font=FONT_BOLD,
                  bg=COLOR_BTN_DEL, fg=COLOR_BTN_TXT, width=10,
                  command=self._delete).pack(side="left", padx=4)

    def _build_detail(self):
        self.detail_frame = tk.LabelFrame(self, text="詳細・メモ",
                                          font=FONT_BOLD, bg=COLOR_BG)
        self.detail_frame.pack(fill="x", padx=12, pady=(0, 8))
        self.detail_text = tk.Text(self.detail_frame, font=FONT_SMALL,
                                   height=4, state="disabled",
                                   bg="#FDFEFE", relief="flat")
        self.detail_text.pack(fill="x", padx=6, pady=4)

    # ------------------------------------------------------------------
    def load_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        cat_filter    = self.filter_var.get()
        status_filter = self.status_var.get()
        rows = db_get_all()

        visible = []
        for r in rows:
            if cat_filter != "すべて" and r[2] != cat_filter:
                continue
            if status_filter != "すべて" and r[9] != status_filter:
                continue
            visible.append(r)

        for i, r in enumerate(visible):
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert("", "end", iid=str(r[0]),
                             values=(r[1], r[2], r[3], r[4], r[6], r[8], r[9]),
                             tags=(tag,))

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        sid = int(sel[0])
        rows = db_get_all()
        row = next((r for r in rows if r[0] == sid), None)
        if not row:
            return
        lines = []
        if row[5]:  lines.append(f"ユーザー名　: {row[5]}")
        if row[7]:  lines.append(f"URL　　　　: {row[7]}")
        if row[8]:  lines.append(f"連携サービス: {row[8]}")
        if row[10]: lines.append(f"メモ　　　　: {row[10]}")
        if row[12]: lines.append(f"更新日時　　: {row[12]}")
        text = "\n".join(lines) if lines else "（詳細なし）"
        self.detail_text.config(state="normal")
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.insert("1.0", text)
        self.detail_text.config(state="disabled")

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "操作するサービスを選択してください")
            return None
        return int(sel[0])

    def _add(self):
        dlg = ServiceDialog(self, "サービスを追加")
        if dlg.result:
            db_insert(dlg.result)
            self.load_table()

    def _edit(self):
        sid = self._get_selected_id()
        if sid is None:
            return
        rows = db_get_all()
        row = next((r for r in rows if r[0] == sid), None)
        if not row:
            return
        existing = list(row[1:11])  # name〜memo
        dlg = ServiceDialog(self, "サービスを編集", data=existing)
        if dlg.result:
            db_update(sid, dlg.result)
            self.load_table()

    def _delete(self):
        sid = self._get_selected_id()
        if sid is None:
            return
        rows = db_get_all()
        row = next((r for r in rows if r[0] == sid), None)
        if not row:
            return
        if messagebox.askyesno("削除確認", f"「{row[1]}」を削除しますか？"):
            db_delete(sid)
            self.detail_text.config(state="normal")
            self.detail_text.delete("1.0", tk.END)
            self.detail_text.config(state="disabled")
            self.load_table()

# =============================================================================
# 起動
# =============================================================================

if __name__ == "__main__":
    setup_database()
    app = ServiceManagerApp()
    app.mainloop()
