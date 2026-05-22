# =============================================================================
# 簡易支援一覧アプリ
# 利用者ごとに「スタッフが何をしないといけないか」を9カテゴリで記録・印刷する。
# 特記事項がない項目は空欄のまま。受け入れ時の確認漏れ防止にも使える。
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
import webbrowser
import tempfile
from datetime import datetime, date

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR       = os.path.join(os.path.expanduser("~"), "Documents", "gh_system")
PRIVATE_ROOT   = r"C:\GH_Data"
DATA_DIR       = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR     = os.path.join(PRIVATE_ROOT, "support_summary_backups")
RESIDENTS_DB   = os.path.join(DATA_DIR, "residents.db")
SUMMARY_DB     = os.path.join(DATA_DIR, "support_summary.db")
MAX_BACKUPS    = 10

# =============================================================================
# 支援カテゴリの定義（固定9項目）
# key はDB保存用、label は画面表示用、hint は入力例
# =============================================================================
CATEGORIES = [
    {
        "key":   "food",
        "label": "食事・水分",
        "hint":  "例：とろみ剤使用（とろみ中）、麺類は刻む",
    },
    {
        "key":   "bath",
        "label": "入浴・清潔",
        "hint":  "例：浴槽移乗に一部介助、爪切りは毎週水曜",
    },
    {
        "key":   "medicine",
        "label": "服薬・医療",
        "hint":  "例：毎食後に職員が手渡し確認、自己管理不可",
    },
    {
        "key":   "money",
        "label": "金銭管理・買い物",
        "hint":  "例：職員が管理、週1,000円渡す、買い物は同行",
    },
    {
        "key":   "outing",
        "label": "外出・余暇",
        "hint":  "例：一人外出可・帰宅時に確認、毎週月曜デイ利用",
    },
    {
        "key":   "sleep",
        "label": "睡眠・夜間",
        "hint":  "例：夜間トイレ誘導あり、22時消灯、夜間不穏あり",
    },
    {
        "key":   "comm",
        "label": "コミュニケーション・特性",
        "hint":  "例：急な変更に不安、否定語を避ける、大きい声に過敏",
    },
    {
        "key":   "health",
        "label": "緊急・健康上の注意",
        "hint":  "例：卵アレルギー、血圧高め（140超で報告）、てんかん既往",
    },
    {
        "key":   "other",
        "label": "その他・特記",
        "hint":  "上記以外で特に伝えておきたいこと",
    },
]

# =============================================================================
# フォント・カラー設定
# =============================================================================
FONT            = ("MS Gothic", 11)
FONT_BOLD       = ("MS Gothic", 11, "bold")
FONT_TITLE      = ("MS Gothic", 14, "bold")
FONT_SMALL      = ("MS Gothic", 10)
FONT_SMALL_BOLD = ("MS Gothic", 10, "bold")

COLOR_BG        = "#F5F7FA"
COLOR_HEADER    = "#2E6B8A"    # 青系（他アプリと被らないテーマ色）
COLOR_HEADER_FG = "#FFFFFF"
COLOR_SECTION   = "#D6EAF5"
COLOR_SECTION_FG= "#1A4A6A"
COLOR_WARN      = "#FFF3CD"    # 未記入警告の背景色
COLOR_WARN_FG   = "#856404"


# =============================================================================
# 初期セットアップ
# =============================================================================

def setup():
    """アプリ起動時にフォルダ・DBを自動作成し、バックアップを実行する"""
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    _create_db()
    _backup_db()


def _create_db():
    """支援一覧DBのテーブルを作成する（なければ作成）"""
    conn = sqlite3.connect(SUMMARY_DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS support_items (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id  INTEGER NOT NULL,
            category_key TEXT    NOT NULL,
            content      TEXT,
            updated_at   TEXT    NOT NULL,
            UNIQUE(resident_id, category_key)
        )
    """)
    conn.commit()
    conn.close()


def _backup_db():
    """起動時にDBをバックアップする。MAX_BACKUPS を超えた分は古い順に削除する"""
    if not os.path.exists(SUMMARY_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(SUMMARY_DB, backup_file)
    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


def get_conn():
    """支援一覧DB への接続を返す（列名アクセス対応）"""
    conn = sqlite3.connect(SUMMARY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_residents_conn():
    """入居者マスターDB への接続を返す（読み取り専用）"""
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# 支援内容編集ダイアログ
# =============================================================================

class SupportEditDialog(tk.Toplevel):
    """
    利用者1名の全カテゴリの支援内容を一括で編集するダイアログ。

    引数:
        parent        : 親ウィンドウ
        resident_id   : 利用者ID
        resident_name : 利用者氏名
        existing      : 現在のDBデータ（{category_key: content} の辞書）
    """

    def __init__(self, parent, resident_id, resident_name, existing):
        super().__init__(parent)
        self.parent        = parent
        self.resident_id   = resident_id
        self.resident_name = resident_name
        self.existing      = existing
        self.saved         = False

        self.title(f"支援内容の編集 — {resident_name}")
        self.geometry("680x720")
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
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _build(self):
        """ダイアログ全体の UI を構築する"""
        # ヘッダー
        hdr = tk.Frame(self, bg=COLOR_HEADER, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {self.resident_name} さんの支援内容",
                 font=FONT_BOLD, bg=COLOR_HEADER, fg=COLOR_HEADER_FG).pack(side="left", padx=8)
        tk.Label(hdr, text="特記事項があるカテゴリだけ入力してください",
                 font=FONT_SMALL, bg=COLOR_HEADER, fg="#AACCDD").pack(side="left", padx=4)

        # スクロール可能な入力エリア
        outer = tk.Frame(self, bg=COLOR_BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=COLOR_BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        form = tk.Frame(canvas, bg=COLOR_BG, padx=16, pady=8)
        canvas_window = canvas.create_window((0, 0), window=form, anchor="nw")

        # フォームの幅をキャンバスに合わせて伸縮させる
        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        def _on_frame_resize(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        form.bind("<Configure>", _on_frame_resize)

        # マウスホイールでスクロールできるようにする
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # カテゴリごとの入力欄を作る
        self.text_vars = {}   # {category_key: tk.Text}

        for cat in CATEGORIES:
            key   = cat["key"]
            label = cat["label"]
            hint  = cat["hint"]
            value = self.existing.get(key) or ""

            # カテゴリ見出し
            sec = tk.Frame(form, bg=COLOR_SECTION, pady=3)
            sec.pack(fill="x", pady=(10, 2))
            tk.Label(sec, text=f"  {label}",
                     font=FONT_SMALL_BOLD, bg=COLOR_SECTION, fg=COLOR_SECTION_FG).pack(side="left")

            # ヒントラベル
            tk.Label(form, text=hint, font=FONT_SMALL, bg=COLOR_BG,
                     fg="#888888", anchor="w").pack(fill="x")

            # テキスト入力欄（2行）
            txt = tk.Text(form, font=FONT, height=2, relief="solid", bd=1,
                          wrap="word", undo=True)
            txt.pack(fill="x", pady=(2, 0))
            if value:
                txt.insert("1.0", value)

            self.text_vars[key] = txt

        # フッターボタン
        footer = tk.Frame(self, bg="#EAEAEA", pady=10)
        footer.pack(fill="x")
        tk.Button(footer, text="  保存して閉じる  ", font=FONT_BOLD, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=14, pady=5, cursor="hand2",
                  command=self._save).pack(side="left", padx=(20, 8))
        tk.Button(footer, text="キャンセル", font=FONT, relief="flat",
                  padx=10, pady=5, cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _save(self):
        """全カテゴリの入力内容をDBに保存する（UPSERT）"""
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_conn()
        for key, txt in self.text_vars.items():
            content = txt.get("1.0", "end-1c").strip() or None
            conn.execute(
                """INSERT INTO support_items (resident_id, category_key, content, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(resident_id, category_key)
                   DO UPDATE SET content = excluded.content, updated_at = excluded.updated_at""",
                (self.resident_id, key, content, now)
            )
        conn.commit()
        conn.close()
        self.saved = True
        self.destroy()


# =============================================================================
# 支援内容詳細ビューダイアログ
# =============================================================================

class SupportViewDialog(tk.Toplevel):
    """
    利用者1名の支援内容を読み取り専用で一覧表示するダイアログ。
    印刷ボタンからHTMLプレビューを開ける。

    引数:
        parent        : 親ウィンドウ
        resident_id   : 利用者ID
        resident_name : 利用者氏名
        room_number   : 部屋番号
    """

    def __init__(self, parent, resident_id, resident_name, room_number):
        super().__init__(parent)
        self.parent        = parent
        self.resident_id   = resident_id
        self.resident_name = resident_name
        self.room_number   = room_number

        self.title(f"支援一覧 — {resident_name}")
        self.geometry("620x680")
        self.resizable(True, True)
        self.grab_set()
        self._load_and_build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _load_and_build(self):
        """DBからデータを読み込んで画面を構築する"""
        conn = get_conn()
        rows = conn.execute(
            "SELECT category_key, content, updated_at FROM support_items WHERE resident_id = ?",
            (self.resident_id,)
        ).fetchall()
        conn.close()

        # {category_key: content} の辞書に変換する
        data       = {r["category_key"]: r["content"] for r in rows}
        updated_at = max((r["updated_at"] for r in rows), default=None)

        # ヘッダー
        hdr = tk.Frame(self, bg=COLOR_HEADER, pady=8)
        hdr.pack(fill="x")
        room_str = f"【{self.room_number}号室】" if self.room_number else ""
        tk.Label(hdr, text=f"  {room_str}{self.resident_name} さんの支援一覧",
                 font=FONT_BOLD, bg=COLOR_HEADER, fg=COLOR_HEADER_FG).pack(side="left", padx=8)

        # 更新日表示
        if updated_at:
            date_str = updated_at[:10]
            tk.Label(hdr, text=f"更新：{date_str}",
                     font=FONT_SMALL, bg=COLOR_HEADER, fg="#AACCDD").pack(side="right", padx=12)

        # スクロールエリア
        outer  = tk.Frame(self, bg=COLOR_BG)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=COLOR_BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        body = tk.Frame(canvas, bg=COLOR_BG, padx=16, pady=8)
        win  = canvas.create_window((0, 0), window=body, anchor="nw")

        def _resize(event):
            canvas.itemconfig(win, width=event.width)
        canvas.bind("<Configure>", _resize)

        def _scroll(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        # カテゴリ行を描画する
        # 「何も記入されていないカテゴリ」を数えて未記入警告を出す
        empty_count = sum(1 for cat in CATEGORIES if not data.get(cat["key"]))

        if empty_count == len(CATEGORIES):
            # まだ何も入力されていない場合はガイドメッセージを表示する
            msg_frame = tk.Frame(body, bg=COLOR_WARN, pady=12, padx=16,
                                 relief="flat", bd=1)
            msg_frame.pack(fill="x", pady=8)
            tk.Label(msg_frame, text="まだ支援内容が入力されていません。",
                     font=FONT_BOLD, bg=COLOR_WARN, fg=COLOR_WARN_FG).pack(anchor="w")
            tk.Label(msg_frame,
                     text="「編集」ボタンから必要なカテゴリに支援内容を入力してください。\n"
                          "特記事項がない項目は空欄のままで構いません。",
                     font=FONT_SMALL, bg=COLOR_WARN, fg=COLOR_WARN_FG, justify="left").pack(anchor="w")
        else:
            for cat in CATEGORIES:
                key     = cat["key"]
                label   = cat["label"]
                content = data.get(key)

                # カテゴリ見出し
                sec = tk.Frame(body, bg=COLOR_SECTION, pady=3)
                sec.pack(fill="x", pady=(8, 2))
                tk.Label(sec, text=f"  {label}",
                         font=FONT_SMALL_BOLD, bg=COLOR_SECTION, fg=COLOR_SECTION_FG).pack(side="left")

                # 内容テキスト
                if content:
                    tk.Label(body, text=content, font=FONT, bg=COLOR_BG,
                             fg="#1A1A1A", anchor="w", justify="left",
                             wraplength=560).pack(fill="x", padx=8, pady=(0, 4))
                else:
                    # 空欄のカテゴリは薄いグレーで「特になし」と表示する
                    tk.Label(body, text="特になし", font=FONT_SMALL, bg=COLOR_BG,
                             fg="#BBBBBB", anchor="w").pack(fill="x", padx=8, pady=(0, 4))

        # フッターボタン
        footer = tk.Frame(self, bg="#EAEAEA", pady=10)
        footer.pack(fill="x")
        tk.Button(footer, text="  印刷プレビュー  ", font=FONT_BOLD, relief="flat",
                  bg="#5B7FA6", fg="white", padx=12, pady=5, cursor="hand2",
                  command=lambda: self._print_preview(data)).pack(side="left", padx=(20, 8))
        tk.Button(footer, text="閉じる", font=FONT, relief="flat",
                  padx=10, pady=5, cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _print_preview(self, data):
        """支援一覧をHTMLでブラウザに表示して印刷できるようにする"""
        today_str = date.today().strftime("%Y年%m月%d日")
        room_str  = f"【{self.room_number}号室】" if self.room_number else ""

        # カテゴリ行のHTML生成
        rows_html = ""
        for i, cat in enumerate(CATEGORIES):
            content = data.get(cat["key"]) or ""
            bg      = "#FFFFFF" if i % 2 == 0 else "#F5FAFF"
            # 改行を<br>に変換する
            content_html = content.replace("\n", "<br>") if content else \
                           '<span style="color:#CCCCCC;">特になし</span>'
            rows_html += (
                f'<tr style="background:{bg};">'
                f'<td class="cat">{cat["label"]}</td>'
                f'<td>{content_html}</td>'
                f'</tr>\n'
            )

        html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>支援一覧 {self.resident_name}</title>
<style>
  @page {{ size: A4 portrait; margin: 15mm; }}
  body {{ font-family:"MS Gothic","Meiryo",sans-serif; font-size:10.5pt; color:#222; }}
  h1 {{ font-size:14pt; text-align:center; border-bottom:2px solid {COLOR_HEADER};
       padding-bottom:5px; color:{COLOR_HEADER}; margin-bottom:4px; }}
  .sub {{ text-align:right; font-size:9pt; color:#666; margin-bottom:12px; }}
  table {{ border-collapse:collapse; width:100%; font-size:10pt; }}
  th {{ background:{COLOR_HEADER}; color:white; padding:5px 10px;
       font-weight:normal; text-align:center; }}
  th.cat {{ width:140px; }}
  td {{ padding:6px 10px; border-bottom:1px solid #DDD; vertical-align:top; line-height:1.6; }}
  td.cat {{ font-weight:bold; color:{COLOR_SECTION_FG}; background:{COLOR_SECTION};
            white-space:nowrap; width:140px; }}
  @media print {{ .no-print {{ display:none; }} }}
</style>
</head>
<body>
<h1>簡易支援一覧　{room_str}{self.resident_name} さん</h1>
<p class="sub">出力日：{today_str}</p>
<table>
<thead>
  <tr><th class="cat">カテゴリ</th><th>支援内容・特記事項</th></tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
<p class="no-print" style="margin-top:14px;color:#888;font-size:9pt;">
  ※ 印刷するには Ctrl+P をお使いください。用紙：A4縦、余白：標準 を推奨します。
</p>
</body>
</html>"""

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", encoding="utf-8",
            delete=False, prefix="support_summary_print_"
        )
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")


# =============================================================================
# メインアプリ
# =============================================================================

class SupportSummaryApp(tk.Tk):
    """簡易支援一覧アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("簡易支援一覧")
        self.geometry("780x560")
        self.resizable(True, True)
        self.configure(bg=COLOR_BG)

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
        tk.Label(header, text="簡易支援一覧",
                 font=FONT_TITLE, bg=COLOR_HEADER, fg=COLOR_HEADER_FG).pack(side="left", padx=20)
        tk.Label(header, text="利用者ごとの支援方法・特記事項をまとめて確認・印刷する",
                 font=FONT_SMALL, bg=COLOR_HEADER, fg="#AACCDD").pack(side="left", padx=4)

        # ---- 操作バー ----
        ctrl = tk.Frame(self, bg="#E8EDF2", pady=6)
        ctrl.pack(fill="x", padx=10, pady=(0, 4))

        tk.Button(ctrl, text="  更新  ", font=FONT, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=10, pady=2, cursor="hand2",
                  command=self._load_residents).pack(side="left", padx=(10, 4))

        # 右側のアクションボタン
        tk.Button(ctrl, text="  印刷プレビュー  ", font=FONT, relief="flat",
                  bg="#5B7FA6", fg="white", padx=10, pady=3, cursor="hand2",
                  command=self._open_print).pack(side="right", padx=(4, 10))
        tk.Button(ctrl, text="  編 集  ", font=FONT_BOLD, relief="flat",
                  bg=COLOR_HEADER, fg="white", padx=10, pady=3, cursor="hand2",
                  command=self._open_edit).pack(side="right", padx=4)
        tk.Button(ctrl, text="  詳細を見る  ", font=FONT, relief="flat",
                  bg="#4A8A5A", fg="white", padx=10, pady=3, cursor="hand2",
                  command=self._open_view).pack(side="right", padx=4)

        # ---- 一覧テーブル ----
        list_frame = tk.Frame(self, bg=COLOR_BG)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        columns = ("room", "name", "filled", "empty", "updated_at")
        col_cfg = {
            "room":       ("部屋",       60, "center"),
            "name":       ("利用者名",  150, "w"),
            "filled":     ("記入済み",   80, "center"),
            "empty":      ("未記入",     80, "center"),
            "updated_at": ("最終更新日", 130, "center"),
        }

        self.tree = ttk.Treeview(
            list_frame, columns=columns,
            show="headings", selectmode="browse"
        )
        for col, (hd, w, anc) in col_cfg.items():
            self.tree.heading(col, text=hd)
            self.tree.column(col, width=w, anchor=anc, minwidth=30)

        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        # 行の背景色タグ
        self.tree.tag_configure("even",    background="#FFFFFF")
        self.tree.tag_configure("odd",     background="#F0F4FA")
        # 未記入が1件でもある行は薄い黄色で警告する
        self.tree.tag_configure("warn",    background=COLOR_WARN)
        # 全カテゴリ未入力は薄いグレー
        self.tree.tag_configure("all_empty", background="#EEEEEE")

        # ダブルクリックで詳細を開く
        self.tree.bind("<Double-1>", lambda e: self._open_view())

        # ---- ステータスバー ----
        self.status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self.status_var,
                 font=FONT_SMALL, bg="#E0E4E8", anchor="w",
                 padx=10, pady=2).pack(fill="x", side="bottom")

        # 利用者ID を iid に対応させるキャッシュ
        self._residents = []    # [{"id", "name", "room_number"}, ...]

    # ------------------------------------------------------------------
    # データ読み込み
    # ------------------------------------------------------------------

    def _load_residents(self):
        """入居者マスターと支援データを読み込んで一覧を更新する"""
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

        # 支援データの記入状況をまとめて取得する
        conn = get_conn()
        rows = conn.execute(
            """SELECT resident_id, category_key, content, updated_at
               FROM support_items"""
        ).fetchall()
        conn.close()

        # {resident_id: {category_key: content, "_updated_at": ...}} の形に変換する
        support_map = {}
        for r in rows:
            rid = r["resident_id"]
            if rid not in support_map:
                support_map[rid] = {"_updated_at": r["updated_at"]}
            support_map[rid][r["category_key"]] = r["content"]
            # 最新の updated_at を保持する
            if r["updated_at"] > support_map[rid]["_updated_at"]:
                support_map[rid]["_updated_at"] = r["updated_at"]

        # Treeview を更新する
        for item in self.tree.get_children():
            self.tree.delete(item)

        self._residents = []
        for i, res in enumerate(residents):
            rid     = res["id"]
            sdata   = support_map.get(rid, {})
            total   = len(CATEGORIES)
            filled  = sum(1 for cat in CATEGORIES if sdata.get(cat["key"]))
            empty   = total - filled
            updated = sdata.get("_updated_at", "")
            updated_disp = updated[:10] if updated else "未入力"

            # 行の色付け
            if filled == 0:
                tag = "all_empty"
            elif empty > 0:
                tag = "warn"
            elif i % 2 == 0:
                tag = "even"
            else:
                tag = "odd"

            self.tree.insert(
                "", "end",
                iid=str(rid),
                tags=(tag,),
                values=(
                    res["room_number"] or "—",
                    res["name"],
                    f"{filled} / {total}",
                    empty if empty > 0 else "—",
                    updated_disp,
                )
            )
            self._residents.append({
                "id":          rid,
                "name":        res["name"],
                "room_number": res["room_number"] or "",
            })

        count = len(residents)
        self.status_var.set(f"入居中の利用者：{count}名　　※ 黄色行は未記入カテゴリがあります")

    # ------------------------------------------------------------------
    # 選択行の取得
    # ------------------------------------------------------------------

    def _get_selected(self):
        """
        一覧で選択中の利用者情報を返す。
        未選択なら None を返す。
        """
        sel = self.tree.selection()
        if not sel:
            return None
        rid = int(sel[0])
        for r in self._residents:
            if r["id"] == rid:
                return r
        return None

    def _load_existing(self, resident_id):
        """
        指定した利用者の支援データを {category_key: content} 形式で返す。
        """
        conn = get_conn()
        rows = conn.execute(
            "SELECT category_key, content FROM support_items WHERE resident_id = ?",
            (resident_id,)
        ).fetchall()
        conn.close()
        return {r["category_key"]: r["content"] for r in rows}

    # ------------------------------------------------------------------
    # ボタンアクション
    # ------------------------------------------------------------------

    def _open_edit(self):
        """選択中の利用者の支援内容を編集するダイアログを開く"""
        res = self._get_selected()
        if res is None:
            messagebox.showwarning("未選択", "編集する利用者を選択してください。")
            return
        existing = self._load_existing(res["id"])
        dlg = SupportEditDialog(self, res["id"], res["name"], existing)
        if dlg.saved:
            self._load_residents()

    def _open_view(self):
        """選択中の利用者の支援内容詳細ダイアログを開く"""
        res = self._get_selected()
        if res is None:
            messagebox.showwarning("未選択", "詳細を見る利用者を選択してください。")
            return
        SupportViewDialog(self, res["id"], res["name"], res["room_number"])

    def _open_print(self):
        """選択中の利用者の印刷プレビューを直接開く"""
        res = self._get_selected()
        if res is None:
            messagebox.showwarning("未選択", "印刷する利用者を選択してください。")
            return
        data = self._load_existing(res["id"])
        dlg  = SupportViewDialog.__new__(SupportViewDialog)
        dlg.resident_name = res["name"]
        dlg.room_number   = res["room_number"]
        # _print_preview だけ呼ぶ（ウィンドウは開かない）
        SupportViewDialog._print_preview(dlg, data)


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = SupportSummaryApp()
    app.mainloop()
