# =============================================================================
# グループホーム管理システム ランチャー v2
# すべての管理アプリをここから起動できる
# カテゴリ・順番は「表示設定」ボタンから変更できる
# =============================================================================

import tkinter as tk
from tkinter import messagebox, simpledialog
import subprocess
import sys
import os
import json
import copy

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
SETTINGS_PATH = os.path.join(BASE_DIR, "launcher_settings.json")

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 15, "bold")
FONT_SMALL = ("MS Gothic", 10)
FONT_CAT   = ("MS Gothic", 10, "bold")

# 色設定（共通）
COLOR_BG         = "#F5F7FA"   # 画面全体の背景
COLOR_HEADER_TXT = "#FFFFFF"   # カテゴリヘッダーの文字色（白）
COLOR_ROW_ODD    = "#FFFFFF"   # 奇数行の背景（白）
COLOR_BTN_TXT    = "#FFFFFF"   # 起動ボタンの文字色
COLOR_TITLE_BG   = "#2C5FA8"   # タイトルバーの背景
COLOR_SUB_BTN    = "#E8EDF5"   # 設定ダイアログ内のサブボタン背景
COLOR_HEADER     = "#2C5FA8"   # ダイアログ内リストボックスの選択行の背景色
COLOR_BTN        = "#2C5FA8"   # ダイアログ内の主要ボタン（保存など）の背景色

# カテゴリごとの色パレット（インデックス順に自動で割り当てられる）
# header: ヘッダー背景・ボタン・左ボーダーの色
# light : 偶数行の薄い背景色
CATEGORY_PALETTE = [
    {"header": "#3A9E72", "light": "#EDF7F3"},   # 緑（入居者管理）
    {"header": "#D4762A", "light": "#FDF2E9"},   # オレンジ（請求・実績）
    {"header": "#7B5EA7", "light": "#F3F0F8"},   # 紫（書類・印刷）
    {"header": "#2E8B9A", "light": "#E8F6F8"},   # ティール（勤務管理）
    {"header": "#C05555", "light": "#FBEDED"},   # 赤（予備5番目以降）
    {"header": "#5B7FA6", "light": "#EEF3F8"},   # 青（予備6番目以降）
]

def get_palette(cat_index):
    """カテゴリのインデックスから色パレットを返す（色が足りない場合は循環する）"""
    return CATEGORY_PALETTE[cat_index % len(CATEGORY_PALETTE)]


def _darken(hex_color, amount=30):
    """
    16進数カラーコードを受け取り、RGB各値を amount だけ暗くして返す。
    ボタンのホバー時（activebackground）に使う。

    Args:
        hex_color: "#RRGGBB" 形式のカラーコード
        amount:    暗くする量（0〜255）
    Returns:
        暗くした "#RRGGBB" 形式のカラーコード
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    r = max(0, r - amount)
    g = max(0, g - amount)
    b = max(0, b - amount)
    return f"#{r:02X}{g:02X}{b:02X}"

# =============================================================================
# デフォルトのカテゴリ・アプリ設定
# （初回起動時や設定ファイルが無いときに使われる）
# =============================================================================
DEFAULT_SETTINGS = {
    "categories": [
        {
            "name": "入居者管理",
            "items": [
                {"name": "入居管理マスター",       "desc": "入居者の基本情報（氏名・部屋・入退居日など）を管理する",               "path": r"residents_app\main.py"},
                {"name": "血圧測定記録",           "desc": "入居者の血圧測定値を日ごとに記録・確認する",                           "path": r"bp_app\bp_app.py"},
                {"name": "体重測定記録",           "desc": "入居者の体重を日ごとに記録・グラフで確認する",                             "path": r"weight_app\weight_app.py"},
                {"name": "お薬在庫管理",           "desc": "入居者別のお薬在庫を管理する",                                         "path": r"medicine_app\medicine_app.py"},
                {"name": "日用品管理",             "desc": "入居者の日用品（シャンプー・歯ブラシ等）の在庫を管理する",             "path": r"residents_items_app\daily_items_app.py"},
                {"name": "通院記録",               "desc": "入居者の通院・処方内容を記録・管理する",                               "path": r"visit_app\visit_app.py"},
                {"name": "看護記録",               "desc": "入居者の体温・脈拍・SpO2・体調を日ごとに記録・確認する",               "path": r"nursing_app\nursing_app.py"},
                {"name": "入居者ダッシュボード",         "desc": "1人分の情報（血圧・体重・看護・通院・お薬・預かり金）をまとめて確認する", "path": r"dashboard_app\dashboard_app.py"},
                {"name": "個別支援計画 期限管理",   "desc": "個別支援計画の作成日・次回見直し日を記録し、期限切れ・期限迫りを一覧で管理する", "path": r"support_plan_app\support_plan_app.py"},
                {"name": "簡易支援一覧",             "desc": "利用者ごとの支援方法・特記事項を9カテゴリで記録・確認・印刷する",       "path": r"support_summary_app\support_summary_app.py"},
                {"name": "FP制度チェッカー",         "desc": "入居希望者のアセスメント支援。利用できる福祉制度を確認する",           "path": r"welfare_fp_tool\checker_app.py"},
            ],
        },
        {
            "name": "請求・実績",
            "items": [
                {"name": "利用実績入力",           "desc": "日々のサービス提供実績を入力する",                                     "path": r"usage_app\usage_app.py"},
                {"name": "請求書作成",             "desc": "月次の請求書を生成・印刷する",                                         "path": r"billing_app\billing_app.py"},
                {"name": "収支計算",               "desc": "月次の報酬試算と人件費を計算し、収支の概算を確認する",                 "path": r"finance_app\finance_app.py"},
                {"name": "預かり金管理",           "desc": "利用者の預かり金の収支を管理する",                                     "path": r"deposit_app\deposit_app.py"},
            ],
        },
        {
            "name": "書類・印刷",
            "items": [
                {"name": "書類差し込み印刷",       "desc": "利用者書類に氏名・日付などを差し込んで作成する",                       "path": r"documents_app\documents_app.py"},
                {"name": "契約書印刷",             "desc": "入居・体験利用の契約書ファイルを一括印刷する",                         "path": r"contract_app\contract_app.py"},
                {"name": "封筒宛名印刷",           "desc": "長形封筒に宛名を縦書きで印刷する",                                     "path": r"envelope_app\envelope_app.py"},
                {"name": "お出かけお知らせ作成",   "desc": "外出行事のお知らせ文書を入力するだけで自動作成する",                   "path": r"outing_app\outing_app.py"},
            ],
        },
        {
            "name": "勤務管理",
            "items": [
                {"name": "勤務表作成",             "desc": "職員の月次勤務表を作成・集計する",                                     "path": r"kintai_app\schedule_app.py"},
                {"name": "人員不足時間帯ビューア", "desc": "シフトパターンから人員が不足している時間帯を確認する",                 "path": r"kintai_app\vacancy_viewer.py"},
                {"name": "募集説明シート作成",     "desc": "未配置の時間帯をもとに職員募集用の説明シートを生成する",               "path": r"kintai_app\flyer_generator.py"},
            ],
        },
        {
            "name": "在庫管理",
            "items": [
                {"name": "在庫チェック（ブラウザ）",  "desc": "すみかの消耗品・備品の在庫をブラウザ画面で確認・更新する",         "path": r"inventory_app\sumika_inventory.html"},
                {"name": "お買い物リスト（ブラウザ）", "desc": "購入が必要な品目をブラウザ画面でリスト管理する",                   "path": r"inventory_app\shopping_list.html"},
            ],
        },
        {
            "name": "クイックアクセス",
            "items": [
                {"name": "書類フォルダ",           "desc": "コワークで作成した書類の保存フォルダを開く",                           "path": "書類"},
                {"name": "GH_Data フォルダ",       "desc": "入居者DBなど個人情報データの保存フォルダを開く",                       "path": r"C:\GH_Data"},
                {"name": "gh_system フォルダ",     "desc": "管理システム本体のフォルダを開く（アプリの場所を確認したいとき）",     "path": r"C:\Users\tanak\Documents\gh_system"},
            ],
        },
        {
            "name": "GAS・外部連携",
            "items": [
                {"name": "GASプロジェクト管理",       "desc": "登録済みのGASアプリをまとめて管理・更新する（一括プッシュ）",       "path": r"gas_push_app\gas_push_app.py"},
                {"name": "支援記録フォーム（ブラウザ）", "desc": "日々の支援記録をブラウザ画面から入力する（GASアプリ）",           "path": r"gas_support_record\index.html"},
                {"name": "利用者データCSV書き出し",   "desc": "入居者・お薬情報をCSVに書き出してGASへ連携する前処理ツール",       "path": r"gas_support_record\export_residents.py"},
                {"name": "サービス管理",               "desc": "GitHub・Netlifyなど外部サービスのアカウント・用途・ログイン方法を一覧管理する", "path": r"service_manager_app\service_manager_app.py"},
            ],
        },
    ]
}


# =============================================================================
# 設定ファイルの読み書き
# =============================================================================

def load_settings():
    """
    設定ファイルを読み込む。
    ファイルが存在しない・壊れている場合はデフォルト設定を返す。
    """
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass  # 読み込み失敗時はデフォルトを使う
    return copy.deepcopy(DEFAULT_SETTINGS)


def save_settings(data):
    """設定データをJSONファイルに書き込む"""
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# アプリ起動
# =============================================================================

def get_python_exe():
    """
    コンソール画面を表示しない pythonw.exe のパスを返す。
    見つからない場合は通常の python.exe を返す。
    """
    python = sys.executable
    pythonw = python.replace("python.exe", "pythonw.exe")
    return pythonw if os.path.exists(pythonw) else python


def launch_app(script_path):
    """
    指定したファイルまたはフォルダを開く。
    - 絶対パス（C:\\ 始まり）はそのまま使う
    - 相対パスは BASE_DIR と結合して解決する
    - .py  → pythonw で別プロセス起動
    - .html / フォルダ / その他 → os.startfile でOSに任せる

    Args:
        script_path: ファイルまたはフォルダのパス（絶対 or BASE_DIR からの相対）
    """
    # 絶対パスかどうかで結合方法を切り替える
    if os.path.isabs(script_path):
        full_path = script_path
    else:
        full_path = os.path.join(BASE_DIR, script_path)

    if not os.path.exists(full_path):
        messagebox.showerror("エラー", f"ファイルが見つかりません。\n\n{full_path}")
        return
    try:
        ext = os.path.splitext(full_path)[1].lower()
        if ext == ".py":
            # cwd をスクリプトのある場所にすることで相対パスが正常に動く
            subprocess.Popen([get_python_exe(), full_path], cwd=os.path.dirname(full_path))
        else:
            # .html・フォルダ・その他はOSのデフォルトアプリで開く
            # （フォルダ → エクスプローラー、.html → ブラウザ）
            os.startfile(full_path)
    except Exception as e:
        messagebox.showerror("起動エラー", f"起動に失敗しました。\n\n{e}")


# =============================================================================
# メインランチャー画面
# =============================================================================

class LauncherApp(tk.Tk):
    """ランチャーのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("グループホーム管理システム")
        self.configure(bg=COLOR_BG)
        self.minsize(580, 350)

        self.settings = load_settings()

        self._build_title()
        self._build_scrollable_area()
        self._build_footer()

        # 初期ウィンドウサイズを設定して画面中央に配置
        self.update_idletasks()
        w, h = 680, 620
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # -------------------------------------------------------------------------
    # 画面構築
    # -------------------------------------------------------------------------

    def _build_title(self):
        """タイトルバーを作成する"""
        bar = tk.Frame(self, bg=COLOR_TITLE_BG, pady=12)
        bar.pack(fill="x")

        # 右上に「表示設定」ボタン
        tk.Button(
            bar,
            text="⚙  表示設定",
            font=FONT_SMALL,
            bg="#4A5FA8",
            fg=COLOR_BTN_TXT,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=3,
            activebackground="#3A4F98",
            activeforeground=COLOR_BTN_TXT,
            command=self._open_settings,
        ).pack(side="right", padx=14, pady=2)

        tk.Label(
            bar,
            text="グループホーム 管理システム",
            font=FONT_TITLE,
            bg=COLOR_TITLE_BG,
            fg=COLOR_HEADER_TXT,
        ).pack()

        tk.Label(
            bar,
            text="起動したいアプリのボタンをクリックしてください",
            font=FONT_SMALL,
            bg=COLOR_TITLE_BG,
            fg="#BDD4F0",
        ).pack(pady=(2, 0))

    def _build_scrollable_area(self):
        """スクロール可能なアプリ一覧エリアを作成する"""
        container = tk.Frame(self, bg=COLOR_BG)
        container.pack(fill="both", expand=True)

        # スクロールバー
        scrollbar = tk.Scrollbar(container, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        # Canvas（スクロール対象）
        self.canvas = tk.Canvas(
            container,
            bg=COLOR_BG,
            yscrollcommand=scrollbar.set,
            highlightthickness=0,
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.canvas.yview)

        # Canvas の中に置くフレーム
        self.inner = tk.Frame(self.canvas, bg=COLOR_BG)
        self._canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        # フレームのサイズが変わったらスクロール範囲を更新
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        ))
        # Canvasの幅が変わったら内側フレームの幅も合わせる
        self.canvas.bind("<Configure>", self._on_canvas_resize)

        # マウスホイールでスクロール（Windows対応）
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(
            int(-1 * (e.delta / 120)), "units"
        ))

        # キーボードでスクロール
        # ↑↓キー：1行ずつ / PageUp・PageDown：1画面ずつ / Home・End：先頭・末尾
        self.bind_all("<Up>",       lambda e: self.canvas.yview_scroll(-1, "units"))
        self.bind_all("<Down>",     lambda e: self.canvas.yview_scroll( 1, "units"))
        self.bind_all("<Prior>",    lambda e: self.canvas.yview_scroll(-1, "pages"))  # PageUp
        self.bind_all("<Next>",     lambda e: self.canvas.yview_scroll( 1, "pages"))  # PageDown
        self.bind_all("<Home>",     lambda e: self.canvas.yview_moveto(0))
        self.bind_all("<End>",      lambda e: self.canvas.yview_moveto(1))

        self._draw_app_list()

    def _on_canvas_resize(self, event):
        """Canvas の幅変更に合わせて内側フレームを引き伸ばす"""
        self.canvas.itemconfig(self._canvas_win, width=event.width)

    def _build_footer(self):
        """フッターを作成する"""
        footer = tk.Frame(self, bg="#DDE4EF", pady=6)
        footer.pack(fill="x")
        tk.Label(
            footer,
            text="© グループホーム管理システム",
            font=FONT_SMALL,
            bg="#DDE4EF",
            fg="#888888",
        ).pack()

    # -------------------------------------------------------------------------
    # アプリ一覧の描画
    # -------------------------------------------------------------------------

    def _draw_app_list(self):
        """
        設定データをもとにカテゴリ＋アプリ一覧を描画する。
        設定変更後の再描画にも対応（既存ウィジェットを削除して描き直す）。
        カテゴリごとに色パレットを順番に割り当てる。
        """
        for widget in self.inner.winfo_children():
            widget.destroy()

        outer = tk.Frame(self.inner, bg=COLOR_BG, padx=20, pady=12)
        outer.pack(fill="both", expand=True)

        # enumerate でインデックスを取り、そのインデックスで色を決める
        for cat_idx, cat in enumerate(self.settings["categories"]):
            if cat.get("items"):   # アプリが0件のカテゴリは表示しない
                palette = get_palette(cat_idx)
                self._draw_category(outer, cat, palette)

    def _draw_category(self, parent, cat, palette):
        """
        カテゴリヘッダーとその配下のアプリ行を描画する。

        Args:
            palette: {"header": str, "light": str} の色辞書
        """
        items       = cat["items"]
        header_color = palette["header"]
        light_color  = palette["light"]

        # カテゴリヘッダー（アプリ件数も表示）
        header = tk.Frame(parent, bg=header_color, pady=7, padx=12)
        header.pack(fill="x", pady=(14, 0))
        tk.Label(
            header,
            text=f"  {cat['name']}  （{len(items)} 件）",
            font=FONT_CAT,
            bg=header_color,
            fg=COLOR_HEADER_TXT,
            anchor="w",
        ).pack(fill="x")

        # アプリ行（奇数行=白、偶数行=カテゴリの薄い色）
        for i, app in enumerate(items):
            bg = COLOR_ROW_ODD if i % 2 == 0 else light_color
            self._draw_app_row(parent, app, bg, header_color)

    def _draw_app_row(self, parent, app, bg, accent):
        """
        アプリ1件分の行を描画する。
        左端にカテゴリカラーのボーダーを付け、右端に起動ボタンを配置する。

        Args:
            accent: カテゴリカラー（左ボーダーと起動ボタンに使用）
        """
        row = tk.Frame(parent, bg=bg)
        row.pack(fill="x")

        # --- 左端：カテゴリカラーの縦ボーダー ---
        tk.Frame(row, bg=accent, width=5).pack(side="left", fill="y")

        # --- コンテンツ部分 ---
        content = tk.Frame(row, bg=bg, pady=8, padx=12)
        content.pack(side="left", fill="x", expand=True)

        # アプリ名
        tk.Label(
            content,
            text=app["name"],
            font=FONT_BOLD,
            bg=bg,
            fg="#1A2A4A",
            anchor="w",
        ).pack(fill="x")

        # 説明文ラベル（ウィンドウ幅に合わせて折り返す）
        desc_lbl = tk.Label(
            content,
            text=app["desc"],
            font=FONT_SMALL,
            bg=bg,
            fg="#666666",
            anchor="w",
            justify="left",
        )
        desc_lbl.pack(fill="x")

        # content フレームの幅が変わったら wraplength（折り返し幅）も更新する
        content.bind(
            "<Configure>",
            lambda e, lbl=desc_lbl: lbl.config(wraplength=max(e.width - 4, 100))
        )

        # --- 右側：起動ボタン（カテゴリカラー） ---
        path = app["path"]
        # ホバー時の色（少し暗くする）をあらかじめ計算
        active_color = _darken(accent)
        tk.Button(
            row,
            text="起  動",
            font=FONT,
            bg=accent,
            fg=COLOR_BTN_TXT,
            relief="flat",
            cursor="hand2",
            padx=16,
            pady=6,
            activebackground=active_color,
            activeforeground=COLOR_BTN_TXT,
            command=lambda p=path: launch_app(p),
        ).pack(side="right", padx=12, pady=6)

    # -------------------------------------------------------------------------
    # 設定ダイアログ
    # -------------------------------------------------------------------------

    def _open_settings(self):
        """表示設定ダイアログを開く"""
        dlg = SettingsDialog(self, self.settings)
        self.wait_window(dlg)
        # ダイアログが閉じたらアプリ一覧を再描画（設定変更を反映）
        self._draw_app_list()


# =============================================================================
# 表示設定ダイアログ
# =============================================================================

class SettingsDialog(tk.Toplevel):
    """
    カテゴリの追加・削除・並び替えと
    アプリの並び替え・カテゴリ移動を行うダイアログ。
    """

    def __init__(self, parent, settings):
        super().__init__(parent)
        self.title("表示設定")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self.minsize(680, 420)
        self.grab_set()  # このダイアログを閉じるまで親ウィンドウを操作できなくする

        # 設定データのコピーを編集する（キャンセル時に元データを汚さないため）
        self.work     = copy.deepcopy(settings)
        self.original = settings  # 保存時にここへ書き戻す

        self._build_ui()

        # 最初のカテゴリを選択状態にして右側のアプリ欄を表示する
        if self.work["categories"]:
            self.cat_lb.selection_set(0)
            self._on_cat_select()

        # 画面中央に配置
        self.update_idletasks()
        w, h = 780, 520
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # -------------------------------------------------------------------------
    # UI構築
    # -------------------------------------------------------------------------

    def _build_ui(self):
        # タイトル
        bar = tk.Frame(self, bg=COLOR_TITLE_BG, pady=10)
        bar.pack(fill="x")
        tk.Label(
            bar,
            text="表示設定  ―  カテゴリとアプリの並び順を変更できます",
            font=FONT_BOLD,
            bg=COLOR_TITLE_BG,
            fg=COLOR_HEADER_TXT,
        ).pack()

        # メインエリア（左：カテゴリ / 右：アプリ）
        main = tk.Frame(self, bg=COLOR_BG, padx=14, pady=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        self._build_cat_panel(main)
        self._build_app_panel(main)
        self._build_footer()

    def _build_cat_panel(self, parent):
        """左側：カテゴリ管理パネル"""
        frame = tk.LabelFrame(
            parent, text="  カテゴリ  ", font=FONT,
            bg=COLOR_BG, fg="#1A2A4A", padx=8, pady=8,
        )
        frame.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        frame.rowconfigure(0, weight=1)

        # カテゴリ一覧（Listbox）
        self.cat_lb = tk.Listbox(
            frame, font=FONT, width=17,
            selectbackground=COLOR_HEADER, selectforeground=COLOR_HEADER_TXT,
            relief="solid", bd=1, activestyle="none",
        )
        self.cat_lb.grid(row=0, column=0, sticky="ns")
        self.cat_lb.bind("<<ListboxSelect>>", lambda e: self._on_cat_select())
        self._refresh_cat_lb()

        # カテゴリ操作ボタン
        btn_area = tk.Frame(frame, bg=COLOR_BG)
        btn_area.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        for label, cmd in [
            ("＋ 追加",     self._add_cat),
            ("✎ 名前変更", self._rename_cat),
            ("✕ 削除",     self._delete_cat),
            ("↑  上へ",    self._move_cat_up),
            ("↓  下へ",    self._move_cat_down),
        ]:
            tk.Button(
                btn_area, text=label, font=FONT_SMALL,
                bg=COLOR_SUB_BTN, fg="#1A2A4A",
                relief="flat", cursor="hand2", padx=4, pady=3,
                command=cmd,
            ).pack(fill="x", pady=1)

    def _build_app_panel(self, parent):
        """右側：アプリ管理パネル"""
        self.app_frame = tk.LabelFrame(
            parent, text="  アプリ  ", font=FONT,
            bg=COLOR_BG, fg="#1A2A4A", padx=8, pady=8,
        )
        self.app_frame.grid(row=0, column=1, sticky="nsew")
        self.app_frame.rowconfigure(0, weight=1)
        self.app_frame.columnconfigure(0, weight=1)

        # アプリ一覧（Listbox）
        lb_wrap = tk.Frame(self.app_frame, bg=COLOR_BG)
        lb_wrap.grid(row=0, column=0, sticky="nsew")
        lb_wrap.rowconfigure(0, weight=1)
        lb_wrap.columnconfigure(0, weight=1)

        self.app_lb = tk.Listbox(
            lb_wrap, font=FONT,
            selectbackground=COLOR_HEADER, selectforeground=COLOR_HEADER_TXT,
            relief="solid", bd=1, activestyle="none",
        )
        self.app_lb.grid(row=0, column=0, sticky="nsew")

        sb = tk.Scrollbar(lb_wrap, orient="vertical", command=self.app_lb.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.app_lb.config(yscrollcommand=sb.set)

        # アプリ操作ボタン
        btn_area = tk.Frame(self.app_frame, bg=COLOR_BG)
        btn_area.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        for label, cmd in [
            ("↑  上へ",          self._move_app_up),
            ("↓  下へ",          self._move_app_down),
            ("→ 別カテゴリへ移動", self._move_app_to_cat),
        ]:
            tk.Button(
                btn_area, text=label, font=FONT_SMALL,
                bg=COLOR_SUB_BTN, fg="#1A2A4A",
                relief="flat", cursor="hand2", padx=8, pady=3,
                command=cmd,
            ).pack(side="left", padx=2)

    def _build_footer(self):
        """下部：保存・キャンセルボタン"""
        footer = tk.Frame(self, bg="#DDE4EF", pady=10, padx=14)
        footer.pack(fill="x")

        tk.Label(
            footer,
            text="「保存して閉じる」を押すと変更内容がランチャーへ反映されます",
            font=FONT_SMALL, bg="#DDE4EF", fg="#555555",
        ).pack(side="left")

        tk.Button(
            footer, text="キャンセル", font=FONT,
            bg="#AAAAAA", fg=COLOR_BTN_TXT,
            relief="flat", cursor="hand2", padx=12, pady=4,
            command=self.destroy,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            footer, text="保存して閉じる", font=FONT_BOLD,
            bg=COLOR_BTN, fg=COLOR_BTN_TXT,
            relief="flat", cursor="hand2", padx=12, pady=4,
            activebackground="#2C5FA8", activeforeground=COLOR_BTN_TXT,
            command=self._save_and_close,
        ).pack(side="right")

    # -------------------------------------------------------------------------
    # カテゴリ操作
    # -------------------------------------------------------------------------

    def _refresh_cat_lb(self, select=None):
        """カテゴリ一覧を再描画する。select に選択したいインデックスを渡す。"""
        self.cat_lb.delete(0, tk.END)
        for cat in self.work["categories"]:
            n = len(cat.get("items", []))
            self.cat_lb.insert(tk.END, f"  {cat['name']}  （{n}件）")
        if select is not None and self.work["categories"]:
            self.cat_lb.selection_set(select)
            self._on_cat_select()

    def _sel_cat(self):
        """選択中カテゴリのインデックス（なければ None）"""
        s = self.cat_lb.curselection()
        return s[0] if s else None

    def _on_cat_select(self):
        """カテゴリを選んだときにアプリ一覧を更新する"""
        idx = self._sel_cat()
        self.app_lb.delete(0, tk.END)
        if idx is None:
            return
        cat = self.work["categories"][idx]
        self.app_frame.config(text=f"  「{cat['name']}」のアプリ  ")
        for app in cat.get("items", []):
            self.app_lb.insert(tk.END, f"  {app['name']}  ─  {app['desc']}")

    def _add_cat(self):
        """新しいカテゴリを追加する"""
        name = simpledialog.askstring("カテゴリ追加", "新しいカテゴリ名を入力してください：", parent=self)
        if not name or not name.strip():
            return
        self.work["categories"].append({"name": name.strip(), "items": []})
        self._refresh_cat_lb(len(self.work["categories"]) - 1)

    def _rename_cat(self):
        """選択中のカテゴリ名を変更する"""
        idx = self._sel_cat()
        if idx is None:
            messagebox.showinfo("未選択", "名前を変更するカテゴリを選択してください。", parent=self)
            return
        current = self.work["categories"][idx]["name"]
        name = simpledialog.askstring("名前変更", "新しいカテゴリ名を入力してください：", initialvalue=current, parent=self)
        if not name or not name.strip():
            return
        self.work["categories"][idx]["name"] = name.strip()
        self._refresh_cat_lb(idx)

    def _delete_cat(self):
        """選択中のカテゴリを削除する（中のアプリも消える）"""
        idx = self._sel_cat()
        if idx is None:
            messagebox.showinfo("未選択", "削除するカテゴリを選択してください。", parent=self)
            return
        cat = self.work["categories"][idx]
        n   = len(cat.get("items", []))
        msg = f"「{cat['name']}」を削除しますか？\n中のアプリ（{n}件）も一緒に削除されます。"
        if not messagebox.askyesno("削除確認", msg, parent=self):
            return
        del self.work["categories"][idx]
        new_idx = min(idx, len(self.work["categories"]) - 1)
        self._refresh_cat_lb(new_idx if self.work["categories"] else None)

    def _move_cat_up(self):
        """選択中のカテゴリを1つ上に移動する"""
        idx = self._sel_cat()
        if idx is None or idx == 0:
            return
        cats = self.work["categories"]
        cats[idx - 1], cats[idx] = cats[idx], cats[idx - 1]
        self._refresh_cat_lb(idx - 1)

    def _move_cat_down(self):
        """選択中のカテゴリを1つ下に移動する"""
        idx  = self._sel_cat()
        cats = self.work["categories"]
        if idx is None or idx >= len(cats) - 1:
            return
        cats[idx], cats[idx + 1] = cats[idx + 1], cats[idx]
        self._refresh_cat_lb(idx + 1)

    # -------------------------------------------------------------------------
    # アプリ操作
    # -------------------------------------------------------------------------

    def _sel_app(self):
        """選択中アプリのインデックス（なければ None）"""
        s = self.app_lb.curselection()
        return s[0] if s else None

    def _move_app_up(self):
        """選択中のアプリを1つ上に移動する"""
        ci = self._sel_cat()
        ai = self._sel_app()
        if ci is None or ai is None or ai == 0:
            return
        items = self.work["categories"][ci]["items"]
        items[ai - 1], items[ai] = items[ai], items[ai - 1]
        self._on_cat_select()
        self.app_lb.selection_set(ai - 1)

    def _move_app_down(self):
        """選択中のアプリを1つ下に移動する"""
        ci    = self._sel_cat()
        ai    = self._sel_app()
        items = self.work["categories"][ci]["items"] if ci is not None else []
        if ci is None or ai is None or ai >= len(items) - 1:
            return
        items[ai], items[ai + 1] = items[ai + 1], items[ai]
        self._on_cat_select()
        self.app_lb.selection_set(ai + 1)

    def _move_app_to_cat(self):
        """選択中のアプリを別カテゴリへ移動するサブダイアログを開く"""
        ci = self._sel_cat()
        ai = self._sel_app()
        if ci is None or ai is None:
            messagebox.showinfo("未選択", "移動するアプリを選択してください。", parent=self)
            return

        # 移動先の候補（現在のカテゴリ以外）
        others = [(i, c["name"]) for i, c in enumerate(self.work["categories"]) if i != ci]
        if not others:
            messagebox.showinfo("移動先なし",
                "移動先のカテゴリがありません。\nまずカテゴリを追加してください。", parent=self)
            return

        # 移動先を選ぶ小ウィンドウ
        win = tk.Toplevel(self)
        win.title("移動先を選択")
        win.configure(bg=COLOR_BG)
        win.resizable(False, False)
        win.grab_set()

        tk.Label(
            win, text="どのカテゴリへ移動しますか？",
            font=FONT, bg=COLOR_BG, pady=12, padx=16,
        ).pack()

        dest_var = tk.IntVar(value=others[0][0])
        for idx, name in others:
            tk.Radiobutton(
                win, text=f"  {name}", variable=dest_var, value=idx,
                font=FONT, bg=COLOR_BG, anchor="w",
            ).pack(fill="x", padx=24, pady=2)

        def do_move():
            app = self.work["categories"][ci]["items"].pop(ai)
            self.work["categories"][dest_var.get()]["items"].append(app)
            win.destroy()
            self._refresh_cat_lb(ci)
            self._on_cat_select()

        tk.Button(
            win, text="移動する", font=FONT_BOLD,
            bg=COLOR_BTN, fg=COLOR_BTN_TXT,
            relief="flat", cursor="hand2", padx=14, pady=5,
            activebackground="#2C5FA8", activeforeground=COLOR_BTN_TXT,
            command=do_move,
        ).pack(pady=12)

    # -------------------------------------------------------------------------
    # 保存
    # -------------------------------------------------------------------------

    def _save_and_close(self):
        """変更を元の設定オブジェクトへ書き戻し、ファイルに保存してダイアログを閉じる"""
        self.original["categories"] = self.work["categories"]
        save_settings(self.original)
        self.destroy()


# =============================================================================
# 起動
# =============================================================================

if __name__ == "__main__":
    app = LauncherApp()
    app.mainloop()
