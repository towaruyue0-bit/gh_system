"""
封筒宛名印刷アプリ
長形40号（90mm × 225mm）の封筒に宛名を縦書きで印刷する。

住所帳に宛先を登録しておき、選択するだけで封筒プレビューと印刷ができる。
印刷はブラウザ経由（HTML/CSS の縦書き機能を利用）。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import tempfile
import webbrowser
from datetime import datetime


# ===== 定数定義 =====

APP_TITLE = "封筒宛名印刷"

# DB の保存先（このファイルと同じフォルダ）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "addresses.db")

# 対応している封筒サイズ一覧（表示名: (幅mm, 高さmm)）
PAPER_SIZES = {
    "長形4号  （90mm × 205mm）": (90, 205),
    "長形40号（90mm × 225mm）": (90, 225),
    "長形3号  （120mm × 235mm）": (120, 235),
}

# フォント定義（MS Gothic で日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 9)

# カラー定義
COLOR_BG          = "#F5F7FA"
COLOR_HEADER      = "#2C5F8A"
COLOR_BTN_PRIMARY = "#2C5F8A"
COLOR_BTN_EDIT    = "#5B8FA8"
COLOR_BTN_DANGER  = "#C0392B"
COLOR_BTN_PRINT   = "#27AE60"
COLOR_ROW_ODD     = "#FFFFFF"
COLOR_ROW_EVEN    = "#F0F4FA"


# ===== データベース初期化 =====

def init_db():
    """
    DB を初期化し、住所テーブルを作成する。
    テーブルがなければ新規作成、すでにあれば何もしない。
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS addresses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            label       TEXT NOT NULL,      -- 管理用ラベル（例：田中様、○○施設）
            postal_code TEXT NOT NULL,      -- 郵便番号（例：123-4567）
            address1    TEXT NOT NULL,      -- 住所1（都道府県〜町名）
            address2    TEXT,               -- 住所2（番地・建物名など、省略可）
            name        TEXT NOT NULL,      -- 宛名（氏名または会社名）
            honorific   TEXT DEFAULT '様',  -- 敬称（様・御中・先生など）
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# ===== メインアプリ =====

class EnvelopeApp(tk.Tk):
    """封筒宛名印刷アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("960x640")
        self.minsize(800, 520)
        self.configure(bg=COLOR_BG)

        # 選択中の宛先データ（辞書 or None）
        self.selected_data = None

        # 用紙サイズの選択（初期値：長形4号）
        self.paper_size_var = tk.StringVar(
            value="長形4号  （90mm × 205mm）"
        )

        self._build_ui()
        self._load_addresses()

    def _build_ui(self):
        """UI 全体を構築する"""
        # ---- ヘッダーバー ----
        header = tk.Frame(self, bg=COLOR_HEADER, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="封筒宛名印刷",
            font=FONT_TITLE, fg="white", bg=COLOR_HEADER
        ).pack(side="left", padx=16, pady=10)

        # ---- メインコンテンツ（左右分割） ----
        content = tk.Frame(self, bg=COLOR_BG)
        content.pack(fill="both", expand=True, padx=12, pady=12)

        self._build_left_panel(content)
        self._build_right_panel(content)

    # ------------------------------------------------------------------ #
    #  左パネル：住所リスト
    # ------------------------------------------------------------------ #

    def _build_left_panel(self, parent):
        """左パネル（住所リスト + CRUD ボタン）を構築する"""
        left = tk.Frame(parent, bg=COLOR_BG, width=390)
        left.pack(side="left", fill="both", expand=False, padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="住所帳", font=FONT_BOLD, bg=COLOR_BG).pack(
            anchor="w", pady=(0, 6)
        )

        # 検索バー
        sf = tk.Frame(left, bg=COLOR_BG)
        sf.pack(fill="x", pady=(0, 6))
        tk.Label(sf, text="検索：", font=FONT_SMALL, bg=COLOR_BG).pack(side="left")
        self.search_var = tk.StringVar()
        # 入力が変わるたびにリストを再読み込み
        self.search_var.trace_add("write", lambda *_: self._load_addresses())
        tk.Entry(sf, textvariable=self.search_var, font=FONT).pack(
            side="left", fill="x", expand=True
        )

        # 一覧テーブル（Treeview）
        tf = tk.Frame(left, bg=COLOR_BG)
        tf.pack(fill="both", expand=True)

        cols = ("label", "name", "postal_code")
        self.tree = ttk.Treeview(
            tf, columns=cols, show="headings",
            selectmode="browse", height=18
        )
        self.tree.heading("label",       text="ラベル")
        self.tree.heading("name",        text="宛名")
        self.tree.heading("postal_code", text="郵便番号")
        self.tree.column("label",       width=140)
        self.tree.column("name",        width=130)
        self.tree.column("postal_code", width=90)

        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # スタイル設定
        style = ttk.Style()
        style.configure("Treeview", font=FONT, rowheight=28)
        style.configure("Treeview.Heading", font=FONT_BOLD)
        self.tree.tag_configure("odd",  background=COLOR_ROW_ODD)
        self.tree.tag_configure("even", background=COLOR_ROW_EVEN)

        # クリックで選択 → プレビュー更新
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        # ダブルクリックで編集
        self.tree.bind("<Double-1>", lambda _: self._edit_address())

        # CRUD ボタン
        bf = tk.Frame(left, bg=COLOR_BG)
        bf.pack(fill="x", pady=(8, 0))

        btn_cfg = dict(font=FONT, relief="flat", cursor="hand2",
                       fg="white", padx=10, pady=6)
        tk.Button(
            bf, text="＋ 新規登録", bg=COLOR_BTN_PRIMARY,
            command=self._add_address, **btn_cfg
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            bf, text="✎ 編集", bg=COLOR_BTN_EDIT,
            command=self._edit_address, **btn_cfg
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            bf, text="✕ 削除", bg=COLOR_BTN_DANGER,
            command=self._delete_address, **btn_cfg
        ).pack(side="left")

    # ------------------------------------------------------------------ #
    #  右パネル：プレビュー + 印刷ボタン
    # ------------------------------------------------------------------ #

    def _build_right_panel(self, parent):
        """右パネル（封筒プレビュー + 印刷ボタン）を構築する"""
        right = tk.Frame(parent, bg=COLOR_BG)
        right.pack(side="left", fill="both", expand=True)

        # タイトルと用紙サイズ選択を横並び
        top_row = tk.Frame(right, bg=COLOR_BG)
        top_row.pack(fill="x", pady=(0, 6))

        tk.Label(
            top_row, text="封筒プレビュー", font=FONT_BOLD, bg=COLOR_BG
        ).pack(side="left")

        # 用紙サイズ選択ドロップダウン
        tk.Label(
            top_row, text="  用紙サイズ：",
            font=FONT_SMALL, fg="#555555", bg=COLOR_BG
        ).pack(side="left")
        size_combo = ttk.Combobox(
            top_row,
            textvariable=self.paper_size_var,
            values=list(PAPER_SIZES.keys()),
            state="readonly",
            font=FONT_SMALL,
            width=24
        )
        size_combo.pack(side="left")
        # サイズ変更時にプレビューを再描画
        size_combo.bind("<<ComboboxSelected>>", lambda _: self._draw_preview())

        # キャンバスを囲む外枠（影っぽい見た目）
        canvas_outer = tk.Frame(right, bg="#AAAAAA", relief="sunken", bd=2)
        canvas_outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_outer, bg="#DDDDDD")
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)
        # ウィンドウリサイズ時にプレビューを再描画
        self.canvas.bind("<Configure>", lambda _: self._draw_preview())

        # 印刷エリア
        pf = tk.Frame(right, bg=COLOR_BG)
        pf.pack(fill="x", pady=(10, 0))

        self.btn_print = tk.Button(
            pf, text="🖨  印刷する", font=FONT_BOLD,
            bg=COLOR_BTN_PRINT, fg="white", relief="flat",
            cursor="hand2", padx=20, pady=10,
            command=self._print_envelope,
            state="disabled"
        )
        self.btn_print.pack(side="right")

        tk.Label(
            pf, text="← リストから宛先を選択すると印刷できます",
            font=FONT_SMALL, fg="#888888", bg=COLOR_BG
        ).pack(side="left", padx=4)

    # ------------------------------------------------------------------ #
    #  住所リスト操作
    # ------------------------------------------------------------------ #

    def _load_addresses(self):
        """DB から住所一覧を読み込んでリストに表示する"""
        keyword = self.search_var.get().strip()

        # いったんリストをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        if keyword:
            rows = conn.execute(
                """SELECT id, label, name, honorific, postal_code
                   FROM addresses
                   WHERE label LIKE ? OR name LIKE ? OR address1 LIKE ?
                   ORDER BY label""",
                (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%")
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, label, name, honorific, postal_code
                   FROM addresses ORDER BY label"""
            ).fetchall()
        conn.close()

        for i, row in enumerate(rows):
            tag = "odd" if i % 2 == 0 else "even"
            # 宛名列には敬称も一緒に表示
            self.tree.insert(
                "", "end",
                iid=str(row["id"]),
                values=(row["label"],
                        row["name"] + row["honorific"],
                        row["postal_code"]),
                tags=(tag,)
            )

    def _on_select(self, _event):
        """リストで宛先を選択したときにプレビューを更新する"""
        sel = self.tree.selection()
        if not sel:
            return

        addr_id = int(sel[0])
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM addresses WHERE id = ?", (addr_id,)
        ).fetchone()
        conn.close()

        if row:
            self.selected_data = dict(row)
            self._draw_preview()
            self.btn_print.config(state="normal")

    def _add_address(self):
        """新規住所登録ダイアログを開く"""
        dlg = AddressDialog(self, title="住所を登録する")
        self.wait_window(dlg)
        self._load_addresses()

    def _edit_address(self):
        """選択中の住所を編集するダイアログを開く"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("確認",
                                "編集する住所をリストから選択してください。",
                                parent=self)
            return

        addr_id = int(sel[0])
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM addresses WHERE id = ?", (addr_id,)
        ).fetchone()
        conn.close()

        if row:
            dlg = AddressDialog(self, title="住所を編集する", data=dict(row))
            self.wait_window(dlg)
            self._load_addresses()

            # 編集後、プレビューも更新する
            if self.selected_data and self.selected_data["id"] == addr_id:
                self._on_select(None)

    def _delete_address(self):
        """選択中の住所を削除する（確認ダイアログあり）"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("確認",
                                "削除する住所をリストから選択してください。",
                                parent=self)
            return

        addr_id  = int(sel[0])
        label    = self.tree.item(sel[0], "values")[0]

        if not messagebox.askyesno(
            "削除の確認",
            f"「{label}」を削除しますか？\nこの操作は元に戻せません。",
            parent=self
        ):
            return

        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM addresses WHERE id = ?", (addr_id,))
        conn.commit()
        conn.close()

        # 削除した宛先が選択中だったら選択状態を解除
        if self.selected_data and self.selected_data["id"] == addr_id:
            self.selected_data = None
            self.btn_print.config(state="disabled")
            self._draw_preview()

        self._load_addresses()

    # ------------------------------------------------------------------ #
    #  封筒プレビュー描画
    # ------------------------------------------------------------------ #

    def _draw_preview(self):
        """封筒プレビューをキャンバスに描画する"""
        self.canvas.delete("all")

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return  # ウィンドウが最小化されている等

        # 選択中の用紙サイズを取得
        env_w, env_h = PAPER_SIZES[self.paper_size_var.get()]

        # 封筒の縦横比を維持してスケーリング
        ratio = env_w / env_h

        if cw / ch < ratio:
            ew = int(cw * 0.85)
            eh = int(ew / ratio)
        else:
            eh = int(ch * 0.85)
            ew = int(eh * ratio)

        # 封筒を中央に配置する座標
        ex = (cw - ew) // 2
        ey = (ch - eh) // 2

        # 封筒の白い面
        self.canvas.create_rectangle(
            ex, ey, ex + ew, ey + eh,
            fill="white", outline="#999999", width=2
        )

        # 宛先が未選択のときはガイドテキストを表示
        if not self.selected_data:
            self.canvas.create_text(
                cw // 2, ch // 2,
                text="← リストから宛先を選択してください",
                font=FONT, fill="#AAAAAA"
            )
            return

        data = self.selected_data

        # mm → ピクセル変換ヘルパー
        def to_x(mm): return ex + int(mm / env_w * ew)
        def to_y(mm): return ey + int(mm / env_h * eh)

        # ---- 郵便番号（横書き・上部右寄り） ----
        font_postal_size = max(8, int(ew / ENVELOPE_W_MM * 5))
        self.canvas.create_text(
            to_x(86), to_y(7),
            text=f"〒 {data['postal_code']}",
            font=("MS Gothic", font_postal_size),
            fill="#333333", anchor="e"
        )

        # 郵便番号と本文の区切り線（薄いグレー）
        self.canvas.create_line(
            to_x(4), to_y(13),
            to_x(86), to_y(13),
            fill="#DDDDDD", width=1
        )

        # ---- 住所（縦書き・右寄り） ----
        full_address = (data.get("address1") or "") + (data.get("address2") or "")
        font_addr_size = max(7, int(ew / ENVELOPE_W_MM * 3.5))
        self._draw_vertical_text(
            x=to_x(78), y=to_y(16),
            text=full_address,
            font_size=font_addr_size,
            max_height=eh * 0.80,
            color="#333333"
        )

        # ---- 宛名（縦書き・中央） ----
        font_name_size = max(10, int(ew / ENVELOPE_W_MM * 6))
        self._draw_vertical_text(
            x=to_x(44), y=to_y(18),
            text=data["name"],
            font_size=font_name_size,
            max_height=eh * 0.76,
            color="#111111"
        )

        # ---- 敬称（宛名の直下） ----
        font_honor_size = max(8, int(ew / ENVELOPE_W_MM * 4))
        # 宛名の最終文字の下端を計算
        name_bottom = to_y(18) + font_name_size * 1.3 * len(data["name"])
        self.canvas.create_text(
            to_x(44), name_bottom + font_honor_size * 0.3,
            text=data.get("honorific", "様"),
            font=("MS Gothic", font_honor_size),
            fill="#111111", anchor="n"
        )

    def _draw_vertical_text(self, x, y, text, font_size, max_height, color):
        """
        テキストを縦書き（1文字ずつ縦に並べる）でキャンバスに描画する。

        Args:
            x:          描画するX座標（文字の中心）
            y:          描画開始Y座標（最初の文字の上端）
            text:       描画するテキスト
            font_size:  フォントサイズ（pt）
            max_height: この高さを超えたら描画を打ち切る（px）
            color:      文字色
        """
        font        = ("MS Gothic", font_size)
        line_height = font_size * 1.35  # 行間

        current_y = y
        for char in text:
            # 封筒の端をはみ出すなら描画を止める
            if current_y + font_size > y + max_height:
                break
            self.canvas.create_text(
                x, current_y,
                text=char, font=font, fill=color, anchor="n"
            )
            current_y += line_height

    # ------------------------------------------------------------------ #
    #  印刷処理
    # ------------------------------------------------------------------ #

    def _print_envelope(self):
        """
        印刷用 HTML を一時ファイルに書き出し、ブラウザで開く。
        ブラウザの印刷ダイアログが自動的に開く。
        """
        if not self.selected_data:
            return

        data      = self.selected_data
        postal    = data["postal_code"]
        address1  = data.get("address1") or ""
        address2  = data.get("address2") or ""
        name      = data["name"]
        honorific = data.get("honorific", "様")

        # 選択中の用紙サイズを取得
        size_name = self.paper_size_var.get()
        env_w, env_h = PAPER_SIZES[size_name]

        html = _generate_print_html(
            postal, address1, address2, name, honorific, env_w, env_h
        )

        # 一時 HTML ファイルを作成してブラウザで開く
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html",
            delete=False, encoding="utf-8"
        ) as f:
            f.write(html)
            tmp_path = f.name

        # Windows パスを URL 形式に変換（バックスラッシュをスラッシュに）
        url = "file:///" + tmp_path.replace(os.sep, "/")
        webbrowser.open(url)

        # 印刷時の注意をダイアログで案内（選択サイズを表示）
        messagebox.showinfo(
            "印刷の準備ができました",
            f"ブラウザが開き、印刷ダイアログが表示されます。\n\n"
            f"印刷設定を以下のように確認してください：\n"
            f"  ・用紙サイズ：{size_name.strip()}\n"
            f"  ・余白：なし（すべて 0mm）\n"
            f"  ・倍率：100%（縮小しない）\n\n"
            f"※ Chromeの場合：「詳細設定」→「用紙サイズ」で\n"
            f"  リストから選択するか、カスタムを設定してください。",
            parent=self
        )


# ===== 印刷用 HTML 生成（クラス外のモジュールレベル関数） =====

def _generate_print_html(postal, address1, address2, name, honorific,
                         env_w=90, env_h=205):
    """
    封筒宛名印刷用の HTML 文字列を生成する。
    CSS の writing-mode: vertical-rl を使って縦書きを実現する。

    Args:
        postal:    郵便番号（例：123-4567）
        address1:  住所1（都道府県〜町名）
        address2:  住所2（番地・建物名など、空文字可）
        name:      宛名
        honorific: 敬称（様・御中など）
        env_w:     封筒の幅（mm）
        env_h:     封筒の高さ（mm）

    Returns:
        印刷用 HTML 文字列
    """
    # 住所2がある場合だけ表示する
    address2_block = (
        f'<span class="address2">{address2}</span>'
        if address2 else ""
    )

    # 住所・宛名エリアの最大高さ（封筒高さから上部余白を引いた値）
    body_max_h = env_h - 20  # 上部20mm（郵便番号エリア）を除いた高さ

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>封筒宛名印刷</title>
<style>
  /* 印刷ページサイズを選択した封筒サイズに設定 */
  @page {{
    size: {env_w}mm {env_h}mm;
    margin: 0;
  }}

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    width: {env_w}mm;
    height: {env_h}mm;
    overflow: hidden;
    /* 明朝体のほうが宛名印刷らしい見た目になる */
    font-family: 'MS Mincho', '游明朝', 'Yu Mincho', 'HGS明朝E', serif;
    color: #000;
  }}

  .envelope {{
    position: relative;
    width: {env_w}mm;
    height: {env_h}mm;
  }}

  /* 郵便番号：横書き・右上 */
  .postal-code {{
    position: absolute;
    top: 7mm;
    right: 4mm;
    font-size: 13pt;
    letter-spacing: 1.5mm;
    writing-mode: horizontal-tb;
  }}

  /* 住所エリア：縦書き・右寄り */
  .address-area {{
    position: absolute;
    top: 18mm;
    right: 6mm;
    writing-mode: vertical-rl;
    font-size: 9pt;
    line-height: 1.9;
    max-height: {body_max_h}mm;
    overflow: hidden;
  }}

  .address1 {{
    display: block;
  }}

  .address2 {{
    display: block;
  }}

  /* 宛名エリア：縦書き・封筒の横中央に配置
     left: 50% + translateX(-50%) で要素自体を中央揃えにする */
  .name-area {{
    position: absolute;
    top: 18mm;
    left: 50%;
    transform: translateX(-50%);
    writing-mode: vertical-rl;
    max-height: {body_max_h}mm;
    overflow: hidden;
    white-space: nowrap;
  }}

  .name {{
    font-size: 20pt;
    letter-spacing: 3mm;
    display: block;
  }}

  .honorific {{
    font-size: 13pt;
    display: block;
    margin-top: 2mm;
  }}
</style>
<script>
  /* ページ読み込み後、0.6秒後に印刷ダイアログを自動で開く */
  window.onload = function () {{
    setTimeout(function () {{ window.print(); }}, 600);
  }};
</script>
</head>
<body>
<div class="envelope">

  <!-- 郵便番号 -->
  <div class="postal-code">〒 {postal}</div>

  <!-- 住所（右寄り縦書き） -->
  <div class="address-area">
    <span class="address1">{address1}</span>
    {address2_block}
  </div>

  <!-- 宛名（横中央・縦書き） -->
  <div class="name-area">
    <span class="name">{name}</span>
    <span class="honorific">{honorific}</span>
  </div>

</div>
</body>
</html>"""


# ===== 住所登録・編集ダイアログ =====

class AddressDialog(tk.Toplevel):
    """
    住所の登録・編集ダイアログ。
    data=None のとき新規登録モード、dict を渡すと編集モードになる。
    """

    def __init__(self, parent, title, data=None):
        """
        Args:
            parent: 親ウィンドウ
            title:  ダイアログのタイトル
            data:   編集時は既存住所データの辞書、新規登録時は None
        """
        super().__init__(parent)
        self.title(title)
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)
        self.grab_set()  # モーダルにする（このダイアログを閉じるまで親を操作不可）

        self.edit_id = data["id"] if data else None

        self._build_ui(data)

        # ダイアログを親ウィンドウの中央付近に表示
        self.update_idletasks()
        self.geometry(
            f"+{parent.winfo_x() + 200}+{parent.winfo_y() + 80}"
        )

    def _build_ui(self, data):
        """ダイアログ内の UI を構築する"""
        frame = tk.Frame(self, bg=COLOR_BG, padx=28, pady=20)
        frame.pack(fill="both", expand=True)

        # ---- 入力フィールドの定義 ----
        # (フィールドキー, 表示ラベル, 必須かどうか, 入力ヒント)
        fields = [
            ("label",       "ラベル（管理用）",         True,
             "例：田中様、○○株式会社　← 一覧で区別するための名前"),
            ("postal_code", "郵便番号",                 True,
             "例：123-4567　（数字を入力するとハイフンが自動で入ります）"),
            ("address1",    "住所1（都道府県〜町名）",   True,
             "例：東京都新宿区西新宿1丁目"),
            ("address2",    "住所2（番地・建物名など）", False,
             "例：1-1 ○○ビル302号室　（省略できます）"),
            ("name",        "宛名（氏名または会社名）",  True,
             "例：田中 太郎、○○株式会社"),
            ("honorific",   "敬称",                     True,
             "例：様、御中、先生、ご担当者様"),
        ]

        self.vars = {}
        self._postal_formatting = False  # 無限ループ防止フラグ

        for key, label_text, required, hint in fields:
            # ラベル（必須項目には「＊」を付ける）
            row = tk.Frame(frame, bg=COLOR_BG)
            row.pack(fill="x", pady=(10, 2))
            marker = "  ＊必須" if required else "  （省略可）"
            tk.Label(
                row, text=label_text + marker,
                font=FONT_BOLD, bg=COLOR_BG, fg="#333333"
            ).pack(side="left")

            # 入力欄
            var = tk.StringVar()
            tk.Entry(
                frame, textvariable=var, font=FONT,
                width=38, relief="solid", bd=1
            ).pack(fill="x", ipady=5)

            # ヒントテキスト
            tk.Label(
                frame, text=hint,
                font=FONT_SMALL, fg="#888888", bg=COLOR_BG
            ).pack(anchor="w")

            self.vars[key] = var

        # 編集モード：既存データをフィールドにセット
        if data:
            for k, var in self.vars.items():
                var.set(data.get(k) or "")
        else:
            # 新規登録時の敬称デフォルト
            self.vars["honorific"].set("様")

        # 郵便番号フィールドの自動フォーマット（数字入力 → XXX-XXXX に変換）
        self.vars["postal_code"].trace_add("write", self._format_postal_code)

        # ---- ボタン ----
        bf = tk.Frame(frame, bg=COLOR_BG)
        bf.pack(fill="x", pady=(22, 0))

        tk.Button(
            bf, text="保存する", font=FONT_BOLD,
            bg=COLOR_BTN_PRIMARY, fg="white",
            relief="flat", cursor="hand2",
            padx=18, pady=9,
            command=self._save
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            bf, text="キャンセル", font=FONT,
            bg="#AAAAAA", fg="white",
            relief="flat", cursor="hand2",
            padx=18, pady=9,
            command=self.destroy
        ).pack(side="right")

    def _format_postal_code(self, *_):
        """
        郵便番号の入力欄を監視し、数字7桁が入力されると
        自動で「XXX-XXXX」の形式にフォーマットする。
        """
        # フォーマット中に再帰的に呼ばれないようにする
        if self._postal_formatting:
            return

        raw    = self.vars["postal_code"].get()
        digits = "".join(c for c in raw if c.isdigit())[:7]

        # 4桁以上入力されたらハイフンを挿入
        formatted = (digits[:3] + "-" + digits[3:]) if len(digits) >= 4 else digits

        self._postal_formatting = True
        self.vars["postal_code"].set(formatted)
        self._postal_formatting = False

    def _save(self):
        """入力内容をバリデーションし、DB に保存する"""
        # 必須項目チェック
        required = {
            "label":       "ラベル",
            "postal_code": "郵便番号",
            "address1":    "住所1",
            "name":        "宛名",
            "honorific":   "敬称",
        }
        for key, label in required.items():
            if not self.vars[key].get().strip():
                messagebox.showwarning(
                    "入力エラー",
                    f"「{label}」は必須項目です。入力してください。",
                    parent=self
                )
                return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 空文字は None に変換（DB では NULL で保存）
        def v(key):
            val = self.vars[key].get().strip()
            return val if val else None

        conn = sqlite3.connect(DB_PATH)

        if self.edit_id:
            # 既存レコードを更新
            conn.execute(
                """UPDATE addresses
                   SET label=?, postal_code=?, address1=?, address2=?,
                       name=?, honorific=?, updated_at=?
                   WHERE id=?""",
                (v("label"), v("postal_code"), v("address1"), v("address2"),
                 v("name"), v("honorific"), now, self.edit_id)
            )
        else:
            # 新規レコードを登録
            conn.execute(
                """INSERT INTO addresses
                       (label, postal_code, address1, address2,
                        name, honorific, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (v("label"), v("postal_code"), v("address1"), v("address2"),
                 v("name"), v("honorific"), now, now)
            )

        conn.commit()
        conn.close()

        self.destroy()  # 保存完了後にダイアログを閉じる


# ===== エントリーポイント =====

if __name__ == "__main__":
    init_db()
    app = EnvelopeApp()
    app.mainloop()
