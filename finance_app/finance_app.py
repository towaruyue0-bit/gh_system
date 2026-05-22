"""
グループホーム 収支計算アプリ（介護サービス包括型）
月次の報酬試算と人件費計算を行い、収支の概算を確認するためのツール。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sqlite3
import datetime
import tempfile
import webbrowser


# ===== 定数定義 =====

APP_TITLE          = "収支計算アプリ（グループホーム）"
SETTINGS_PATH      = os.path.join(os.path.dirname(__file__), "settings.json")
SHIFTS_PATH        = os.path.join(os.path.dirname(__file__), "shifts.json")
FIXED_STAFF_PATH   = os.path.join(os.path.dirname(__file__), "fixed_staff.json")
RESIDENTS_DB_PATH  = r"C:\GH_Data\data\residents.db"  # 入居者マスターDB（residents_app と共有）

FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)
FONT_MONO  = ("MS Gothic", 9)

# 地域区分ごとの1単位あたり単価（円）
REGION_PRICES = {
    "1級地": 11.40,
    "2級地": 11.12,
    "3級地": 10.84,
    "4級地": 10.70,
    "5級地": 10.55,
    "6級地": 10.41,
    "7級地": 10.27,
    "その他": 10.00,
}

# 障害支援区分ごとの1日あたり基本報酬単位数（介護サービス包括型）
SERVICE_UNITS = {
    "区分なし": 532,
    "区分1":    532,
    "区分2":    587,
    "区分3":    682,
    "区分4":    772,
    "区分5":    876,
    "区分6":    979,
}

# 報酬一覧データ（令和6年4月改定・介護サービス包括型）
# ※ 各セクションは (タイトル, 注記, 列名タプル, 幅タプル, アンカータプル, 行データリスト) の辞書で構成
REWARD_SECTIONS = [
    {
        "title":   "基本報酬（1日あたり）",
        "note":    "障害支援区分ごとの1日単価。月の報酬額 ＝ 単位数 × 利用日数 × 地域単価（円）",
        "cols":    ("区分",           "単位数/日", "備考"),
        "widths":  (180,              110,         380),
        "anchors": ("w",              "center",    "w"),
        "rows": [
            ("区分なし・区分1", "532単位", ""),
            ("区分2",           "587単位", ""),
            ("区分3",           "682単位", ""),
            ("区分4",           "772単位", ""),
            ("区分5",           "876単位", ""),
            ("区分6",           "979単位", ""),
        ],
    },
    {
        "title":   "主な加算",
        "note":    "算定には都道府県等への届出が必要。要件の詳細は告示・通知を必ず確認してください。",
        "cols":    ("加算名",                       "単位・割合",    "算定要件の概要"),
        "widths":  (240,                             130,            430),
        "anchors": ("w",                             "center",       "w"),
        "rows": [
            ("夜間支援等体制加算(Ⅰ)",               "最大54単位/日",  "夜間・深夜に世話人等が住居に常駐する体制。対象利用者数で按分"),
            ("夜間支援等体制加算(Ⅱ)",               "最大27単位/日",  "複数住居を巡回して夜間支援を行う体制"),
            ("夜間支援等体制加算(Ⅲ)",               "16単位/日",      "警備会社等への委託で緊急時対応体制を確保"),
            ("医療的ケア対応支援加算",               "116単位/日",     "看護職員を配置し、たんの吸引等の医療的ケアを提供できる体制"),
            ("強度行動障害支援加算(Ⅰ)",             "180単位/日",     "区分6・行動関連項目10点以上。専門研修（実践研修）修了者が支援"),
            ("強度行動障害支援加算(Ⅱ)",             "125単位/日",     "区分5以上または行動関連項目5点以上。専門研修（基礎研修）修了者が支援"),
            ("重度障害者支援加算(Ⅰ)",               "70単位/日",      "区分6かつ喀痰吸引等が必要。認定特定行為業務従事者が支援"),
            ("重度障害者支援加算(Ⅱ)",               "25単位/日",      "区分6の利用者に一定研修修了者が支援"),
            ("自立生活支援加算",                     "7単位/日",       "地域移行を目指す利用者への個別の生活支援・相談を実施"),
            ("入院時支援特別加算",                   "18単位/日",      "入院中の利用者に事業所職員が支援（上限30日）"),
            ("長期入院時支援特別加算",               "4単位/日",       "入院31日目以降も継続して支援（上限180日）"),
            ("帰宅時支援加算",                       "800単位/月",     "帰宅・外泊時の支援を実施（月最大4回まで）"),
            ("体験利用支援加算(Ⅰ)",                 "700単位/日",     "施設入所者・精神科病院入院者等の体験利用（上限30日）"),
            ("体験利用支援加算(Ⅱ)",                 "300単位/日",     "一般の体験利用（上限30日）"),
            ("食事提供体制加算",                     "42単位/日",      "事業所内に食事提供体制がある場合"),
            ("通勤者生活支援加算",                   "7単位/日",       "就労・就労移行支援等を利用する通勤者への生活支援"),
            ("口腔衛生管理体制加算",                 "30単位/月",      "歯科医師または歯科衛生士による口腔衛生管理の指導体制"),
            ("栄養マネジメント加算",                 "11単位/日",      "管理栄養士による栄養ケア・マネジメントを実施"),
            ("自立支援促進加算",                     "300単位/月",     "医師と連携した自立生活のための支援計画を策定・実施"),
            ("地域生活移行個別支援特別加算",         "500単位/日",     "施設・病院からの移行後180日以内の利用者に集中的支援"),
            ("精神障害者退院支援施設加算",           "300単位/日",     "精神科病院退院者を受け入れる指定を受けた施設"),
            ("サービス提供体制強化加算(Ⅰ)",         "6単位/日",       "介護福祉士等を所定割合以上配置"),
            ("サービス提供体制強化加算(Ⅱ)",         "4単位/日",       "上位要件には満たないが一定割合以上配置"),
            ("サービス提供体制強化加算(Ⅲ)",         "2単位/日",       "常勤割合・経験年数割合等が一定以上"),
            ("福祉専門職員配置等加算(Ⅰ)",           "15単位/日",      "社会福祉士・介護福祉士等を35%以上配置"),
            ("福祉専門職員配置等加算(Ⅱ)",           "10単位/日",      "同25%以上配置"),
            ("福祉専門職員配置等加算(Ⅲ)",           "6単位/日",       "常勤職員が75%以上、または3年以上経験者が30%以上"),
        ],
    },
    {
        "title":   "処遇改善加算（基本報酬等合計に対する割合）",
        "note":    "令和6年4月より新体系に一本化。基本報酬・各加算合計に割合を乗じた額が加算される。",
        "cols":    ("加算名",                              "加算率",  "主な要件"),
        "widths":  (280,                                   80,        430),
        "anchors": ("w",                                   "center",  "w"),
        "rows": [
            ("福祉・介護職員等処遇改善加算(Ⅰ)", "24.5%", "職場環境・キャリアパス等の全要件を満たす"),
            ("福祉・介護職員等処遇改善加算(Ⅱ)", "22.4%", "Ⅰに準じる（一部要件の緩和あり）"),
            ("福祉・介護職員等処遇改善加算(Ⅲ)", "18.2%", "Ⅱの要件のうち一部を満たす"),
            ("福祉・介護職員等処遇改善加算(Ⅳ)", "12.9%", "Ⅲの要件のうち一部を満たす"),
        ],
    },
    {
        "title":   "減算",
        "note":    "要件を満たさない場合や不適切な運営が行われた場合に適用される。",
        "cols":    ("減算名",                          "内容",                                  "適用条件"),
        "widths":  (230,                               220,                                     330),
        "anchors": ("w",                               "w",                                     "w"),
        "rows": [
            ("定員超過利用減算",               "所定単位数 × 70%",            "登録定員を超えて利用させた期間"),
            ("サービス管理責任者欠如減算",     "所定単位数 × 70%（4月目以降は50%）", "サービス管理責任者の配置基準を満たさない状態が継続"),
            ("身体拘束廃止未実施減算",         "−5単位/日",                   "身体拘束適正化委員会の設置・指針整備等が未実施"),
            ("虐待防止措置未実施減算",         "−10単位/日",                  "虐待防止のための措置が講じられていない場合（令和6年4月より）"),
            ("業務継続計画未策定減算",         "所定単位数 × 99%",            "感染症・非常災害時の業務継続計画（BCP）が未策定（令和6年4月より）"),
        ],
    },
]

NIGHT_START_H   = 22    # 深夜割増の開始（労働基準法：22時〜翌5時は基本時給+25%）
NIGHT_END_H     = 5
NIGHT_PREMIUM   = 0.25  # 深夜割増率
OVERTIME_LIMIT  = 8.0   # 時間外割増が発生する1日の所定労働時間（時間）
OVERTIME_PREMIUM = 0.25 # 時間外割増率（基本時給に対して+25%）


# ===== ユーティリティ関数 =====

def calc_shift_hours(start_h: int, start_m: int,
                     end_h: int,   end_m: int,
                     break_min: int,
                     night_start_h: int = 22, night_start_m: int = 0,
                     night_end_h:   int = 5,  night_end_m:   int = 0,
                     night_break_min: int = 0) -> tuple:
    """
    シフトの時間を「正規通常・正規深夜・時間外通常・時間外深夜」の4種に分類して返す。

    ルール：
    - 有給時間が8時間を超えた分を「時間外」とする
    - 深夜時間帯（設定値、デフォルト22:00〜翌5:00）は深夜割増の対象
    - 深夜帯休憩（設定値）を深夜から差し引き、残りの休憩を通常帯から差し引く
    - 時間外時間は「シフトの終端側」から割り当てる
      （日中開始のシフトは深夜側が時間外、深夜開始のシフトは日中側が時間外）

    Args:
        start_h/m:       開始時刻
        end_h/m:         終了時刻（翌日の場合も同じ時計表記で入力）
        break_min:       シフト全体の休憩時間（分）
        night_start_h/m: 深夜帯の開始時刻（設定値）
        night_end_h/m:   深夜帯の終了時刻（設定値、翌日の場合は自動調整）
        night_break_min: 深夜帯の休憩時間（分）。break_min から先に差し引く

    Returns:
        (正規通常h, 正規深夜h, 時間外通常h, 時間外深夜h) のタプル
    """
    start = start_h * 60 + start_m
    end   = end_h   * 60 + end_m
    if end <= start:
        end += 24 * 60  # 日またぎ

    night_s     = night_start_h * 60 + night_start_m
    night_e_raw = night_end_h   * 60 + night_end_m
    # 深夜終了が深夜開始と同時刻または前（例:22時開始→5時終了）の場合は翌日扱い
    if night_e_raw <= night_s:
        night_e_raw += 24 * 60
    night_e = night_e_raw

    raw_night  = max(0, min(end, night_e) - max(start, night_s))
    raw_normal = (end - start) - raw_night

    # 深夜帯の休憩（設定値）を先に差し引き、残りを通常帯に割り当てる
    # 深夜休憩（設定値）と通常休憩（フォーム入力）は独立して差し引く
    night_brk  = min(night_break_min, raw_night)   # 設定の深夜休憩を深夜から差し引く
    normal_brk = min(break_min, raw_normal)         # フォームの休憩を通常帯から差し引く

    night_paid  = max(0, raw_night  - night_brk)
    normal_paid = max(0, raw_normal - normal_brk)
    total_paid  = night_paid + normal_paid  # 分単位

    # 時間外 = 有給8時間を超えた分
    ot_min = max(0, total_paid - int(OVERTIME_LIMIT * 60))

    # 時間外の割り当て：シフトの「終端」が深夜帯か通常帯かで決める
    # 終端が深夜帯内（night_s〜night_e）→ 深夜が最後 → 深夜から時間外を割り当て
    # 終端が深夜帯外（night_e以降など） → 通常が最後 → 通常から時間外を割り当て
    ends_in_night = (night_s < end <= night_e)

    if ends_in_night:
        ot_night  = min(ot_min, night_paid)
        ot_normal = ot_min - ot_night
    else:
        ot_normal = min(ot_min, normal_paid)
        ot_night  = ot_min - ot_normal

    reg_normal = normal_paid - ot_normal
    reg_night  = night_paid  - ot_night

    return (
        round(reg_normal / 60, 3),
        round(reg_night  / 60, 3),
        round(ot_normal  / 60, 3),
        round(ot_night   / 60, 3),
    )


def fmt_yen(amount: float) -> str:
    """金額を「1,234,567円」形式にフォーマットする"""
    return f"{int(amount):,}円"


def load_settings() -> dict:
    """設定ファイルを読み込む。なければデフォルト値を返す"""
    defaults = {
        "region":              "7級地",
        "year":                datetime.date.today().year,
        "month":               datetime.date.today().month,
        "default_wage":        1150,
        "treatment_allowance": 250,
        "breakfast_price":     300,
        "lunch_price":         500,
        "dinner_price":        500,
        "night_start_h":       22,   # 深夜割増の開始時刻（時）
        "night_start_m":       0,
        "night_end_h":         5,    # 深夜割増の終了時刻（時、翌日）
        "night_end_m":         0,
        "night_break_min":     0,    # 深夜帯に取る休憩（分）。この分は深夜時給の対象外
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except (json.JSONDecodeError, IOError):
            pass
    return defaults


def save_settings(settings: dict):
    """設定をファイルに保存する"""
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except IOError as e:
        messagebox.showerror("保存エラー", f"設定の保存に失敗しました：\n{e}")


def load_shifts() -> list:
    """シフトデータを shifts.json から読み込む。なければ空リストを返す"""
    if os.path.exists(SHIFTS_PATH):
        try:
            with open(SHIFTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_shifts(shifts: list):
    """シフトデータを shifts.json に保存する"""
    try:
        with open(SHIFTS_PATH, "w", encoding="utf-8") as f:
            json.dump(shifts, f, ensure_ascii=False, indent=2)
    except IOError as e:
        messagebox.showerror("保存エラー", f"シフトの保存に失敗しました：\n{e}")


def load_fixed_staff() -> list:
    """固定給職員データを fixed_staff.json から読み込む。なければ空リストを返す"""
    if os.path.exists(FIXED_STAFF_PATH):
        try:
            with open(FIXED_STAFF_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


def save_fixed_staff(staff: list):
    """固定給職員データを fixed_staff.json に保存する"""
    try:
        with open(FIXED_STAFF_PATH, "w", encoding="utf-8") as f:
            json.dump(staff, f, ensure_ascii=False, indent=2)
    except IOError as e:
        messagebox.showerror("保存エラー", f"固定給職員データの保存に失敗しました：\n{e}")


# ===== ダイアログ：利用者入力 =====

class ResidentDialog(tk.Toplevel):
    """利用者（入居者）の情報を入力するダイアログ"""

    def __init__(self, parent, title="利用者を追加", initial=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.result = None
        self._build(initial or {})
        self.wait_window()

    def _build(self, initial):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="利用者名（任意）", font=FONT).grid(row=0, column=0, sticky="w", pady=4)
        self.name_var = tk.StringVar(value=initial.get("name", ""))
        ttk.Entry(frame, textvariable=self.name_var, font=FONT, width=16).grid(
            row=0, column=1, pady=4, padx=(8, 0))

        ttk.Label(frame, text="障害支援区分", font=FONT).grid(row=1, column=0, sticky="w", pady=4)
        self.cat_var = tk.StringVar(value=initial.get("category", "区分3"))
        ttk.Combobox(frame, textvariable=self.cat_var, values=list(SERVICE_UNITS.keys()),
                     state="readonly", font=FONT, width=10).grid(
            row=1, column=1, pady=4, padx=(8, 0), sticky="w")

        ttk.Label(frame, text="月の利用日数（日）", font=FONT).grid(row=2, column=0, sticky="w", pady=4)
        self.days_var = tk.StringVar(value=str(initial.get("days", 30)))
        ttk.Entry(frame, textvariable=self.days_var, font=FONT, width=6).grid(
            row=2, column=1, pady=4, padx=(8, 0), sticky="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(14, 0))
        ttk.Button(btn_frame, text="OK",       command=self._ok,     width=8).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="キャンセル", command=self.destroy, width=10).pack(side="left", padx=4)

    def _ok(self):
        try:
            days = int(self.days_var.get())
            if not (0 <= days <= 31):
                raise ValueError
        except ValueError:
            messagebox.showwarning("入力エラー", "利用日数は0〜31の整数で入力してください", parent=self)
            return
        self.result = {
            "name":     self.name_var.get() or "利用者",
            "category": self.cat_var.get(),
            "days":     days,
        }
        self.destroy()


# ===== メインアプリ =====

class FinanceApp(tk.Tk):
    """グループホーム収支計算アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(920, 600)

        self.settings  = load_settings()
        self.residents = []
        self.shifts    = load_shifts()

        self._build_ui()
        self._refresh_all()

    def _night_kwargs(self) -> dict:
        """設定から深夜計算パラメータを取り出して calc_shift_hours に渡せる形で返す"""
        return {
            "night_start_h":   self.settings.get("night_start_h",   22),
            "night_start_m":   self.settings.get("night_start_m",   0),
            "night_end_h":     self.settings.get("night_end_h",     5),
            "night_end_m":     self.settings.get("night_end_m",     0),
            "night_break_min": self.settings.get("night_break_min", 0),
        }

    def _build_ui(self):
        """全体のUIを組み立てる"""
        header = ttk.Frame(self, padding=(12, 8))
        header.pack(fill="x")

        ttk.Label(header, text="対象年月：", font=FONT_BOLD).pack(side="left")
        self.year_var  = tk.StringVar(value=str(self.settings.get("year",  datetime.date.today().year)))
        self.month_var = tk.StringVar(value=str(self.settings.get("month", datetime.date.today().month)))
        ttk.Entry(header, textvariable=self.year_var,  width=6, font=FONT).pack(side="left")
        ttk.Label(header, text="年", font=FONT).pack(side="left")
        ttk.Entry(header, textvariable=self.month_var, width=4, font=FONT).pack(side="left")
        ttk.Label(header, text="月  ", font=FONT).pack(side="left")

        ttk.Label(header, text="地域区分：", font=FONT_BOLD).pack(side="left")
        self.region_var = tk.StringVar(value=self.settings.get("region", "7級地"))
        region_cb = ttk.Combobox(header, textvariable=self.region_var,
                                 values=list(REGION_PRICES.keys()),
                                 state="readonly", width=8, font=FONT)
        region_cb.pack(side="left", padx=(0, 2))
        region_cb.bind("<<ComboboxSelected>>", lambda e: self._on_header_changed())

        self.unit_price_label = ttk.Label(header, font=FONT_SMALL, foreground="gray")
        self.unit_price_label.pack(side="left")
        self._update_unit_price_label()

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.revenue_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.revenue_frame, text="  報酬試算  ")
        self._build_revenue_tab()

        self.labor_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.labor_frame, text="  人件費計算  ")
        self._build_labor_tab()

        self.summary_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.summary_frame, text="  収支概要  ")
        self._build_summary_tab()

        self.reward_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.reward_frame, text="  報酬一覧  ")
        self._build_reward_tab()

        self.config_frame = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.config_frame, text="  設定  ")
        self._build_config_tab()

        self.notebook.bind("<<NotebookTabChanged>>", lambda e: self._refresh_summary())

    # ===== 報酬試算タブ =====

    def _build_revenue_tab(self):
        frame = self.revenue_frame

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill="x", pady=(0, 6))
        ttk.Button(btn_frame, text="＋ 利用者を追加",       command=self._add_resident).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="編集",                  command=self._edit_resident).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="削除",                  command=self._delete_resident).pack(side="left", padx=(0, 6))
        ttk.Separator(btn_frame, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(btn_frame, text="入居者マスターから読み込む",
                   command=self._import_from_residents_db).pack(side="left")

        cols = ("name", "category", "days", "units", "amount")
        self.resident_tree = ttk.Treeview(frame, columns=cols, show="headings", height=10)
        self.resident_tree.heading("name",     text="利用者名")
        self.resident_tree.heading("category", text="障害支援区分")
        self.resident_tree.heading("days",     text="利用日数")
        self.resident_tree.heading("units",    text="単位数（月計）")
        self.resident_tree.heading("amount",   text="報酬額（暫定）")
        self.resident_tree.column("name",     width=130)
        self.resident_tree.column("category", width=100, anchor="center")
        self.resident_tree.column("days",     width=80,  anchor="center")
        self.resident_tree.column("units",    width=110, anchor="e")
        self.resident_tree.column("amount",   width=130, anchor="e")
        self.resident_tree.tag_configure("even", background="#F0F4FA")
        self.resident_tree.tag_configure("odd",  background="#FFFFFF")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self.resident_tree.yview)
        self.resident_tree.configure(yscroll=sb.set)
        self.resident_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        tf = ttk.Frame(frame)
        tf.pack(fill="x", pady=(8, 0))
        self.rev_total_label = ttk.Label(tf, text="報酬合計（暫定）：0円",
                                         font=FONT_BOLD, foreground="#1a6fb5")
        self.rev_total_label.pack(anchor="e")
        ttk.Label(tf, text="※ 自己負担分（利用者負担）は含みません。実際の請求額・入金額とは異なります。",
                  font=FONT_SMALL, foreground="gray").pack(anchor="w", pady=(4, 0))

    def _add_resident(self):
        dlg = ResidentDialog(self, "利用者を追加")
        if dlg.result:
            self.residents.append(dlg.result)
            self._refresh_revenue()

    def _edit_resident(self):
        sel = self.resident_tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "編集する利用者を選んでください")
            return
        idx = self.resident_tree.index(sel[0])
        dlg = ResidentDialog(self, "利用者を編集", initial=self.residents[idx])
        if dlg.result:
            self.residents[idx] = dlg.result
            self._refresh_revenue()

    def _delete_resident(self):
        sel = self.resident_tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "削除する利用者を選んでください")
            return
        idx  = self.resident_tree.index(sel[0])
        name = self.residents[idx]["name"]
        if messagebox.askyesno("削除確認", f"「{name}」を削除しますか？"):
            del self.residents[idx]
            self._refresh_revenue()

    def _import_from_residents_db(self):
        """
        入居者マスターDB（residents.db）から入居中の利用者を読み込む。
        すでにリストに利用者がいる場合は上書き確認を行う。
        利用日数はデフォルト30日で設定し、あとから個別に編集できる。
        """
        if not os.path.exists(RESIDENTS_DB_PATH):
            messagebox.showwarning(
                "DBが見つかりません",
                f"入居者マスターのDBが見つかりませんでした。\n"
                f"パス：{RESIDENTS_DB_PATH}\n\n"
                f"residents_app を一度起動してDBを作成してください。"
            )
            return

        try:
            conn = sqlite3.connect(RESIDENTS_DB_PATH)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT name, disability_grade FROM residents "
                "WHERE status = '入居中' ORDER BY disability_grade, name"
            )
            rows = cur.fetchall()
            conn.close()
        except sqlite3.Error as e:
            messagebox.showerror("読み込みエラー", f"DBの読み込みに失敗しました：\n{e}")
            return

        if not rows:
            messagebox.showinfo("データなし", "入居中の利用者が登録されていません。")
            return

        if self.residents:
            if not messagebox.askyesno(
                "上書き確認",
                f"現在のリスト（{len(self.residents)}件）を消去して\n"
                f"マスターから読み込みますか？\n\n"
                f"読み込み件数：{len(rows)}件（入居中のみ）"
            ):
                return

        # disability_grade（整数1〜6）を「区分X」の文字列に変換
        def grade_to_category(grade):
            if grade is None:
                return "区分なし"
            return f"区分{grade}"

        self.residents = [
            {
                "name":     row["name"],
                "category": grade_to_category(row["disability_grade"]),
                "days":     30,  # デフォルト30日（あとから編集可）
            }
            for row in rows
        ]
        self._refresh_revenue()
        messagebox.showinfo(
            "読み込み完了",
            f"{len(self.residents)}件の利用者を読み込みました。\n"
            f"利用日数はすべて30日に設定しています。\n"
            f"必要に応じて「編集」から変更してください。"
        )

    def _refresh_revenue(self):
        for item in self.resident_tree.get_children():
            self.resident_tree.delete(item)

        unit_price = REGION_PRICES.get(self.region_var.get(), 10.00)
        total = 0.0
        for i, r in enumerate(self.residents):
            upd    = SERVICE_UNITS.get(r["category"], 532)
            units  = upd * r["days"]
            amount = units * unit_price
            total += amount
            tag = "even" if i % 2 == 0 else "odd"
            self.resident_tree.insert("", "end", values=(
                r["name"], r["category"], f"{r['days']}日",
                f"{units:,}単位", fmt_yen(amount),
            ), tags=(tag,))

        self.rev_total_label.config(text=f"報酬合計（暫定）：{fmt_yen(total)}")
        self._refresh_summary()

    # ===== 人件費計算タブ =====

    def _build_labor_tab(self):
        """人件費計算タブ：左にシフト一覧、右に入力フォームと計算内訳"""
        frame = self.labor_frame

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ---- 左：シフト一覧 ----
        left = ttk.Frame(paned, padding=(0, 0, 6, 0))
        paned.add(left, weight=1)

        ttk.Label(left, text="保存済みシフト", font=FONT_BOLD).pack(anchor="w", pady=(0, 4))

        cols = ("name", "time", "sessions", "count", "monthly")
        self.shift_tree = ttk.Treeview(left, columns=cols, show="headings", height=12)
        self.shift_tree.heading("name",     text="シフト名")
        self.shift_tree.heading("time",     text="時間帯")
        self.shift_tree.heading("sessions", text="回数/月")
        self.shift_tree.heading("count",    text="人数")
        self.shift_tree.heading("monthly",  text="月額（賃金＋食費）")
        self.shift_tree.column("name",     width=75)
        self.shift_tree.column("time",     width=110, anchor="center")
        self.shift_tree.column("sessions", width=55,  anchor="center")
        self.shift_tree.column("count",    width=42,  anchor="center")
        self.shift_tree.column("monthly",  width=110, anchor="e")
        self.shift_tree.tag_configure("even", background="#F0F4FA")
        self.shift_tree.tag_configure("odd",  background="#FFFFFF")
        self.shift_tree.bind("<<TreeviewSelect>>", self._on_shift_selected)

        sb = ttk.Scrollbar(left, orient="vertical", command=self.shift_tree.yview)
        self.shift_tree.configure(yscroll=sb.set)
        self.shift_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        br = ttk.Frame(left)
        br.pack(fill="x", pady=(6, 0))
        ttk.Button(br, text="選択行を削除",   command=self._delete_shift).pack(side="left")
        ttk.Button(br, text="新規入力に戻す", command=self._clear_labor_form).pack(side="left", padx=(8, 0))

        self.labor_total_label = ttk.Label(left, text="人件費合計：0円",
                                           font=FONT_BOLD, foreground="#c0392b")
        self.labor_total_label.pack(anchor="e", pady=(6, 0))
        self.labor_note_label = ttk.Label(left, text="", font=FONT_SMALL, foreground="gray")
        self.labor_note_label.pack(anchor="w")

        # ---- 右：入力フォーム ----
        right = ttk.Frame(paned, padding=(6, 0, 0, 0))
        paned.add(right, weight=1)

        self._editing_idx = None

        # フォーム
        form = ttk.LabelFrame(right, text=" シフト入力 ", padding=(10, 6))
        form.pack(fill="x", pady=(0, 4))

        def lbl(text, r):
            ttk.Label(form, text=text, font=FONT).grid(row=r, column=0, sticky="w", pady=2)

        lbl("シフト名", 0)
        self.lf_name = tk.StringVar(value="日勤")
        ttk.Entry(form, textvariable=self.lf_name, font=FONT, width=12).grid(
            row=0, column=1, columnspan=5, sticky="w", padx=(8, 0))

        lbl("開始時刻", 1)
        self.lf_sh = tk.StringVar(value="9")
        self.lf_sm = tk.StringVar(value="00")
        ttk.Entry(form, textvariable=self.lf_sh, width=4, font=FONT).grid(row=1, column=1, padx=(8, 0))
        ttk.Label(form, text="時", font=FONT).grid(row=1, column=2)
        ttk.Entry(form, textvariable=self.lf_sm, width=4, font=FONT).grid(row=1, column=3, padx=(4, 0))
        ttk.Label(form, text="分", font=FONT).grid(row=1, column=4)

        lbl("終了時刻", 2)
        self.lf_eh = tk.StringVar(value="18")
        self.lf_em = tk.StringVar(value="00")
        ttk.Entry(form, textvariable=self.lf_eh, width=4, font=FONT).grid(row=2, column=1, padx=(8, 0))
        ttk.Label(form, text="時", font=FONT).grid(row=2, column=2)
        ttk.Entry(form, textvariable=self.lf_em, width=4, font=FONT).grid(row=2, column=3, padx=(4, 0))
        ttk.Label(form, text="分", font=FONT).grid(row=2, column=4)

        ttk.Label(form, text="※日またぎは翌日の時刻で入力（例：夜勤22時〜翌9時）",
                  font=FONT_SMALL, foreground="gray").grid(row=3, column=0, columnspan=5, sticky="w")

        lbl("通常休憩", 4)
        self.lf_break = tk.StringVar(value="60")
        ttk.Entry(form, textvariable=self.lf_break, width=6, font=FONT).grid(
            row=4, column=1, padx=(8, 0), sticky="w")
        ttk.Label(form, text="分　※深夜休憩は設定タブで設定", font=FONT_SMALL,
                  foreground="gray").grid(row=4, column=2, columnspan=3, sticky="w")

        lbl("月の勤務回数", 5)
        self.lf_sessions = tk.StringVar(value="20")
        ttk.Entry(form, textvariable=self.lf_sessions, width=6, font=FONT).grid(
            row=5, column=1, padx=(8, 0), sticky="w")
        ttk.Label(form, text="回 / 月", font=FONT).grid(row=5, column=2, columnspan=2, sticky="w")

        lbl("人数", 6)
        self.lf_count = tk.StringVar(value="1")
        ttk.Entry(form, textvariable=self.lf_count, width=6, font=FONT).grid(
            row=6, column=1, padx=(8, 0), sticky="w")
        ttk.Label(form, text="人", font=FONT).grid(row=6, column=2)

        lbl("基本時給", 7)
        self.lf_wage = tk.StringVar(value=str(self.settings.get("default_wage", 1150)))
        ttk.Entry(form, textvariable=self.lf_wage, width=8, font=FONT).grid(
            row=7, column=1, padx=(8, 0), sticky="w")
        ttk.Label(form, text="円", font=FONT).grid(row=7, column=2)

        # 食費チェックボックス
        ttk.Label(form, text="食費支給", font=FONT).grid(row=8, column=0, sticky="w", pady=(4, 2))
        meal_frame = ttk.Frame(form)
        meal_frame.grid(row=8, column=1, columnspan=5, sticky="w", padx=(8, 0))

        self.lf_breakfast = tk.BooleanVar(value=False)
        self.lf_lunch     = tk.BooleanVar(value=False)
        self.lf_dinner    = tk.BooleanVar(value=False)

        # チェックボックスのラベルは設定値の価格を表示する（設定変更時に更新）
        self.ck_breakfast = ttk.Checkbutton(meal_frame, variable=self.lf_breakfast,
                                            command=self._update_labor_preview)
        self.ck_lunch     = ttk.Checkbutton(meal_frame, variable=self.lf_lunch,
                                            command=self._update_labor_preview)
        self.ck_dinner    = ttk.Checkbutton(meal_frame, variable=self.lf_dinner,
                                            command=self._update_labor_preview)
        self.ck_breakfast.pack(side="left")
        self.lbl_breakfast = ttk.Label(meal_frame, font=FONT)
        self.lbl_breakfast.pack(side="left", padx=(0, 10))
        self.ck_lunch.pack(side="left")
        self.lbl_lunch = ttk.Label(meal_frame, font=FONT)
        self.lbl_lunch.pack(side="left", padx=(0, 10))
        self.ck_dinner.pack(side="left")
        self.lbl_dinner = ttk.Label(meal_frame, font=FONT)
        self.lbl_dinner.pack(side="left")

        self._update_meal_labels()  # 食費チェックボックスのラベルを初期化

        # 計算内訳表示
        preview_frame = ttk.LabelFrame(right, text=" 計算内訳（自動更新） ", padding=6)
        preview_frame.pack(fill="both", expand=True, pady=(0, 4))

        self.preview_text = tk.Text(preview_frame, font=FONT_MONO, height=14,
                                    state="disabled", bg="#f7f9fc",
                                    relief="flat", wrap="none")
        self.preview_text.pack(fill="both", expand=True)

        self.save_shift_btn = ttk.Button(right, text="保存してリストに追加",
                                         command=self._save_shift)
        self.save_shift_btn.pack(fill="x", ipady=4)

        # 入力変更を検知してプレビューを更新する
        for var in [self.lf_sh, self.lf_sm, self.lf_eh, self.lf_em,
                    self.lf_break, self.lf_sessions, self.lf_count, self.lf_wage]:
            var.trace_add("write", lambda *_: self._update_labor_preview())

        self._update_labor_preview()

    def _update_meal_labels(self):
        """食費チェックボックスのラベルを設定値の価格で更新する"""
        bp = self.settings.get("breakfast_price", 300)
        lp = self.settings.get("lunch_price",     500)
        dp = self.settings.get("dinner_price",    500)
        self.lbl_breakfast.config(text=f"朝食 {bp:,}円")
        self.lbl_lunch.config(    text=f"昼食 {lp:,}円")
        self.lbl_dinner.config(   text=f"夕食 {dp:,}円")

    def _update_labor_preview(self):
        """入力値から計算内訳をリアルタイムで更新する"""
        allow = self.settings.get("treatment_allowance", 0)
        bp    = self.settings.get("breakfast_price", 300)
        lp    = self.settings.get("lunch_price",     500)
        dp    = self.settings.get("dinner_price",    500)

        try:
            sh  = int(self.lf_sh.get())
            sm  = int(self.lf_sm.get())
            eh  = int(self.lf_eh.get())
            em  = int(self.lf_em.get())
            brk = int(self.lf_break.get())
            ses = int(self.lf_sessions.get())
            cnt = int(self.lf_count.get())
            wg  = int(self.lf_wage.get())

            if not (0 <= sh <= 23 and 0 <= sm <= 59 and
                    0 <= eh <= 23 and 0 <= em <= 59 and
                    brk >= 0 and ses > 0 and cnt > 0 and wg > 0):
                raise ValueError

        except ValueError:
            self._set_preview("（入力が完了すると計算内訳が表示されます）")
            return

        nk = self._night_kwargs()
        rn, rd, on, od = calc_shift_hours(sh, sm, eh, em, brk, **nk)
        paid_h   = rn + rd + on + od

        # 実際に深夜帯から差し引かれた休憩分を算出（拘束時間の計算用）
        _s = sh * 60 + sm
        _e = eh * 60 + em
        if _e <= _s: _e += 1440
        _ns = nk["night_start_h"] * 60 + nk["night_start_m"]
        _ne = nk["night_end_h"]   * 60 + nk["night_end_m"]
        if _ne <= _ns: _ne += 1440
        _raw_night = max(0, min(_e, _ne) - max(_s, _ns))
        night_brk_applied = min(nk["night_break_min"], _raw_night)

        total_h  = paid_h + (brk + night_brk_applied) / 60  # 深夜休憩＋通常休憩の合計が拘束

        # 賃金計算（1回あたり）
        w_rn = rn * wg                                       # 正規通常
        w_rd = rd * wg * (1 + NIGHT_PREMIUM)                 # 正規深夜
        w_on = on * wg * (1 + OVERTIME_PREMIUM)              # 時外通常
        w_od = od * wg * (1 + NIGHT_PREMIUM + OVERTIME_PREMIUM)  # 時外深夜
        w_allow = paid_h * allow                             # 処遇改善手当

        # 食費（チェックが入っている分を加算）
        food_once = (bp if self.lf_breakfast.get() else 0) + \
                    (lp if self.lf_lunch.get()     else 0) + \
                    (dp if self.lf_dinner.get()    else 0)

        wage_once  = w_rn + w_rd + w_on + w_od + w_allow
        total_once = wage_once + food_once

        # 月額・30日分の内訳（賃金と食費を分けて計算）
        wage_month = wage_once * ses * cnt
        food_month = food_once * ses * cnt
        cost_month = wage_month + food_month

        wage_30d = wage_once * 30 * cnt
        food_30d = food_once * 30 * cnt
        cost_30d = wage_30d + food_30d

        # 食費の内訳テキスト
        meal_parts = []
        if self.lf_breakfast.get(): meal_parts.append(f"朝食{bp:,}円")
        if self.lf_lunch.get():     meal_parts.append(f"昼食{lp:,}円")
        if self.lf_dinner.get():    meal_parts.append(f"夕食{dp:,}円")
        meal_str = "＋".join(meal_parts) if meal_parts else "なし"

        # 深夜帯の設定値（表示用）
        ns_h = nk["night_start_h"]; ns_m = nk["night_start_m"]
        ne_h = nk["night_end_h"];   ne_m = nk["night_end_m"]
        nb   = nk["night_break_min"]
        night_range_str = f"{ns_h:02d}:{ns_m:02d}〜翌{ne_h:02d}:{ne_m:02d}"

        # 時間外の割り当て方針（注釈用）：終了時刻で判定
        _end_m = eh * 60 + em
        if _end_m <= sh * 60 + sm: _end_m += 1440
        _ns = ns_h * 60 + ns_m
        _ne_adj = ne_h * 60 + ne_m + (1440 if ne_h * 60 + ne_m <= _ns else 0)
        ends_in_night_disp = (_ns < _end_m <= _ne_adj)
        ot_note = f"終端が深夜帯：深夜側が時間外（×1.50）" if ends_in_night_disp \
                  else f"終端が通常帯：通常側が時間外（×1.25）"

        sep = "─" * 34

        night_brk_disp = f"深夜休憩 {night_brk_applied}分＋通常休憩 {brk}分" \
                         if night_brk_applied > 0 else f"休憩 {brk}分"

        lines = [
            f"【 勤務時間 】",
            f"  {sh:02d}:{sm:02d}〜{eh:02d}:{em:02d}　{night_brk_disp}",
            f"  拘束 {total_h:.2f}h　有給 {paid_h:.2f}h",
            f"  　正規：通常 {rn:.2f}h  深夜 {rd:.2f}h",
            f"  　時外：通常 {on:.2f}h  深夜 {od:.2f}h",
            f"  ※ 有給 {OVERTIME_LIMIT:.0f}h超が時間外 / {ot_note}",
            f"  ※ 深夜帯 {night_range_str}：時外深夜×1.50、正規深夜×1.25",
            f"",
            f"【 賃金計算（1回あたり） 】",
            f"  正規通常  {rn:.2f}h × {wg:,}円            ＝ {fmt_yen(w_rn)}",
            f"  正規深夜  {rd:.2f}h × {wg:,}円 × 1.25    ＝ {fmt_yen(w_rd)}",
            f"  時外通常  {on:.2f}h × {wg:,}円 × 1.25    ＝ {fmt_yen(w_on)}",
            f"  時外深夜  {od:.2f}h × {wg:,}円 × 1.50    ＝ {fmt_yen(w_od)}",
            f"  処遇手当  {paid_h:.2f}h × {allow:,}円（割増なし）＝ {fmt_yen(w_allow)}",
            f"  食  費    {meal_str}              ＝ {fmt_yen(food_once)}",
            f"  {sep}",
            f"  1回の合計                         ＝ {fmt_yen(total_once)}",
            f"",
            f"【 月額（{ses}回 × {cnt}人） 】",
            f"  賃金  {fmt_yen(wage_once)} × {ses}回 × {cnt}人  ＝ {fmt_yen(wage_month)}",
            f"  食費  {fmt_yen(food_once)} × {ses}回 × {cnt}人  ＝ {fmt_yen(food_month)}",
            f"  {sep}",
            f"  合計                              ＝ {fmt_yen(cost_month)}",
            f"",
            f"【 参考：月30回の場合（{cnt}人） 】",
            f"  賃金  {fmt_yen(wage_once)} × 30回 × {cnt}人  ＝ {fmt_yen(wage_30d)}",
            f"  食費  {fmt_yen(food_once)} × 30回 × {cnt}人  ＝ {fmt_yen(food_30d)}",
            f"  {sep}",
            f"  合計                              ＝ {fmt_yen(cost_30d)}",
        ]

        if self._editing_idx is not None:
            self.save_shift_btn.config(text="変更を保存する")
        else:
            self.save_shift_btn.config(text="保存してリストに追加")

        self._set_preview("\n".join(lines))

    def _set_preview(self, text: str):
        """計算内訳テキストエリアを書き換える"""
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", text)
        self.preview_text.config(state="disabled")

    def _save_shift(self):
        """フォームの内容を検証してシフトリストに追加（または上書き）し、ファイルに保存する"""
        errors = []
        try:
            sh = int(self.lf_sh.get()); sm = int(self.lf_sm.get())
            eh = int(self.lf_eh.get()); em = int(self.lf_em.get())
            if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
                errors.append("時刻は 時: 0〜23、分: 0〜59 で入力してください")
        except ValueError:
            errors.append("時刻は半角数字で入力してください")

        try:
            brk = int(self.lf_break.get())
            if brk < 0: raise ValueError
        except ValueError:
            errors.append("休憩時間は0以上の整数（分）で入力してください")

        try:
            ses = int(self.lf_sessions.get())
            if ses <= 0: raise ValueError
        except ValueError:
            errors.append("月の勤務回数は1以上の整数で入力してください")

        try:
            cnt = int(self.lf_count.get())
            if cnt <= 0: raise ValueError
        except ValueError:
            errors.append("人数は1以上の整数で入力してください")

        try:
            wg = int(self.lf_wage.get())
            if wg <= 0: raise ValueError
        except ValueError:
            errors.append("時給は正の整数で入力してください")

        if errors:
            messagebox.showwarning("入力エラー", "\n".join(errors))
            return

        shift = {
            "name":      self.lf_name.get() or "シフト",
            "start_h":   sh, "start_m": sm,
            "end_h":     eh, "end_m":   em,
            "break_min": brk,
            "sessions":  ses,
            "count":     cnt,
            "wage":      wg,
            "breakfast": self.lf_breakfast.get(),
            "lunch":     self.lf_lunch.get(),
            "dinner":    self.lf_dinner.get(),
        }

        if self._editing_idx is not None:
            self.shifts[self._editing_idx] = shift
            self._editing_idx = None
        else:
            self.shifts.append(shift)

        save_shifts(self.shifts)
        self._refresh_labor()
        self._clear_labor_form()

    def _on_shift_selected(self, event):
        """一覧で行を選択したとき、フォームに内容を読み込む"""
        sel = self.shift_tree.selection()
        if not sel:
            return
        idx = self.shift_tree.index(sel[0])
        if idx >= len(self.shifts):
            return

        s = self.shifts[idx]
        self._editing_idx = idx

        self.lf_name.set(s.get("name", ""))
        self.lf_sh.set(str(s.get("start_h", 9)))
        self.lf_sm.set(f"{s.get('start_m', 0):02d}")
        self.lf_eh.set(str(s.get("end_h", 18)))
        self.lf_em.set(f"{s.get('end_m', 0):02d}")
        self.lf_break.set(str(s.get("break_min", 60)))
        self.lf_sessions.set(str(s.get("sessions", 20)))
        self.lf_count.set(str(s.get("count", 1)))
        self.lf_wage.set(str(s.get("wage", self.settings.get("default_wage", 1150))))
        self.lf_breakfast.set(s.get("breakfast", False))
        self.lf_lunch.set(    s.get("lunch",     False))
        self.lf_dinner.set(   s.get("dinner",    False))

    def _clear_labor_form(self):
        """フォームを新規入力の初期状態に戻す"""
        self._editing_idx = None
        self.lf_name.set("日勤")
        self.lf_sh.set("9");  self.lf_sm.set("00")
        self.lf_eh.set("18"); self.lf_em.set("00")
        self.lf_break.set("60")
        self.lf_sessions.set("20")
        self.lf_count.set("1")
        self.lf_wage.set(str(self.settings.get("default_wage", 1150)))
        self.lf_breakfast.set(False)
        self.lf_lunch.set(False)
        self.lf_dinner.set(False)
        self.shift_tree.selection_remove(self.shift_tree.selection())

    def _delete_shift(self):
        """選択中のシフトを削除する"""
        sel = self.shift_tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "削除するシフトを選んでください")
            return
        idx  = self.shift_tree.index(sel[0])
        name = self.shifts[idx].get("name", "シフト")
        if messagebox.askyesno("削除確認", f"「{name}」を削除しますか？"):
            del self.shifts[idx]
            save_shifts(self.shifts)
            self._editing_idx = None
            self._clear_labor_form()
            self._refresh_labor()

    def _calc_shift_cost(self, s: dict) -> tuple:
        """
        シフト1件の月額人件費（賃金＋食費）を計算する。

        Returns:
            (月額賃金, 月額食費, 月額合計) のタプル
        """
        allow = self.settings.get("treatment_allowance", 0)
        bp    = self.settings.get("breakfast_price", 300)
        lp    = self.settings.get("lunch_price",     500)
        dp    = self.settings.get("dinner_price",    500)

        rn, rd, on, od = calc_shift_hours(
            s["start_h"], s["start_m"],
            s["end_h"],   s["end_m"],
            s.get("break_min", 0),
            **self._night_kwargs(),
        )
        paid_h = rn + rd + on + od

        wage_once = (
            rn * s["wage"] +
            rd * s["wage"] * (1 + NIGHT_PREMIUM) +
            on * s["wage"] * (1 + OVERTIME_PREMIUM) +
            od * s["wage"] * (1 + NIGHT_PREMIUM + OVERTIME_PREMIUM) +
            paid_h * allow
        )
        food_once = (
            (bp if s.get("breakfast") else 0) +
            (lp if s.get("lunch")     else 0) +
            (dp if s.get("dinner")    else 0)
        )

        sessions = s["sessions"] * s["count"]
        return wage_once * sessions, food_once * sessions, (wage_once + food_once) * sessions

    def _refresh_labor(self):
        """シフト一覧と合計を更新する"""
        for item in self.shift_tree.get_children():
            self.shift_tree.delete(item)

        total = 0.0
        for i, s in enumerate(self.shifts):
            _, _, monthly = self._calc_shift_cost(s)
            tag      = "even" if i % 2 == 0 else "odd"
            time_str = f"{s['start_h']:02d}:{s['start_m']:02d}〜{s['end_h']:02d}:{s['end_m']:02d}"
            self.shift_tree.insert("", "end", values=(
                s.get("name", ""),
                time_str,
                f"{s['sessions']}回",
                f"{s['count']}人",
                fmt_yen(monthly),
            ), tags=(tag,))
            total += monthly

        allow = self.settings.get("treatment_allowance", 0)
        self.labor_total_label.config(text=f"人件費合計：{fmt_yen(total)}")
        self.labor_note_label.config(
            text=f"処遇改善手当 {allow:,}円/時（割増なし）/ 時間外・深夜割増あり / 食費含む")

        self._refresh_summary()

    # ===== 収支概要タブ =====

    def _build_summary_tab(self):
        frame = self.summary_frame

        display = ttk.Frame(frame, padding=(24, 16))
        display.pack(fill="both", expand=True)

        ttk.Label(display, text="月次収支概算", font=FONT_TITLE).pack(pady=(0, 16))

        lw = {"font": FONT, "anchor": "w"}
        self.s_year_month = ttk.Label(display, text="", font=FONT_BOLD)
        self.s_total_rev  = ttk.Label(display, text="", font=FONT_BOLD)
        self.s_sep1       = ttk.Separator(display, orient="horizontal")
        self.s_labor      = ttk.Label(display, text="", **lw)
        self.s_total_cost = ttk.Label(display, text="", font=FONT_BOLD)
        self.s_sep2       = ttk.Separator(display, orient="horizontal")
        self.s_balance    = ttk.Label(display, text="", font=FONT_TITLE)

        for w in [self.s_year_month, self.s_total_rev, self.s_sep1,
                  self.s_labor, self.s_total_cost, self.s_sep2, self.s_balance]:
            if isinstance(w, ttk.Separator):
                w.pack(fill="x", pady=4)
            else:
                w.pack(fill="x", pady=3)

        ttk.Label(display,
                  text="※ この試算は概算です。実際の入金額は自己負担・加算・減算・給付費の審査により変わります。\n"
                       "   人件費以外の支出（家賃・水道光熱費等）は含まれていません。",
                  font=FONT_SMALL, foreground="gray", justify="left").pack(anchor="w", pady=(12, 0))

        ttk.Button(frame, text="印刷（ブラウザで開く）", command=self._print).pack(pady=8)

    def _refresh_summary(self):
        unit_price = REGION_PRICES.get(self.region_var.get(), 10.00)
        base_rev   = sum(
            SERVICE_UNITS.get(r["category"], 532) * r["days"] * unit_price
            for r in self.residents
        )
        labor_cost = sum(self._calc_shift_cost(s)[2] for s in self.shifts)
        balance    = base_rev - labor_cost

        year  = self.year_var.get()
        month = self.month_var.get()
        color  = "#1a6fb5" if balance >= 0 else "#c0392b"
        b_sign = "▲ " if balance < 0 else ""

        self.s_year_month.config(text=f"対象年月：{year}年{month}月")
        self.s_total_rev.config( text=f"報酬合計（暫定）：　　　　　{fmt_yen(base_rev)}")
        self.s_labor.config(     text=f"    人件費（賃金＋食費）：　{fmt_yen(labor_cost)}")
        self.s_total_cost.config(text=f"支出合計（人件費のみ）：　　{fmt_yen(labor_cost)}")
        self.s_balance.config(   text=f"収支差：　{b_sign}{fmt_yen(abs(balance))}",
                                 foreground=color)

    # ===== 報酬一覧タブ =====

    def _build_reward_tab(self):
        """
        報酬一覧タブを構築する。
        基本報酬・加算・処遇改善加算・減算をセクションごとにスクロール表示する（参照用）。
        """
        frame = self.reward_frame

        # 免責注記（改定年度と参照元の確認を促す）
        ttk.Label(
            frame,
            text="※ 令和6年4月改定・介護サービス包括型の概要です。"
                 "必ず最新の厚生労働省告示・通知でご確認ください。",
            font=FONT_SMALL, foreground="#c0392b",
            wraplength=820, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        # スクロール可能なキャンバス
        canvas = tk.Canvas(frame, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)

        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner  = ttk.Frame(canvas)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        # inner フレームのサイズが変わったらスクロール範囲を更新する
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # キャンバス自体のサイズが変わったら inner の幅を追従させる
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win_id, width=e.width))

        # マウスホイールはこのキャンバスにカーソルが乗っている間だけ有効にする
        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        for section in REWARD_SECTIONS:
            self._build_reward_section(inner, section)

    def _build_reward_section(self, parent, section: dict):
        """
        報酬一覧の1セクション（LabelFrame + Treeview）を描画する。

        Args:
            parent:  配置先の親フレーム
            section: REWARD_SECTIONS の各要素辞書
        """
        lf = ttk.LabelFrame(parent, text=f"  {section['title']}  ", padding=(8, 4))
        lf.pack(fill="x", padx=4, pady=(4, 10))

        if section.get("note"):
            ttk.Label(lf, text=section["note"], font=FONT_SMALL,
                      foreground="gray", wraplength=780, justify="left").pack(
                anchor="w", pady=(0, 4))

        cols    = section["cols"]
        widths  = section.get("widths",  tuple(150 for _ in cols))
        anchors = section.get("anchors", tuple("w"  for _ in cols))

        # 行数に合わせた高さ（最大20行まで）
        tree = ttk.Treeview(lf, columns=cols, show="headings",
                             height=min(len(section["rows"]), 20),
                             selectmode="none")

        for col, w, a in zip(cols, widths, anchors):
            # 最終列だけ stretch=True にして余白を埋める
            tree.heading(col, text=col, anchor=a)
            tree.column(col,  width=w,  anchor=a, stretch=(col == cols[-1]))

        tree.tag_configure("even", background="#F0F4FA")
        tree.tag_configure("odd",  background="#FFFFFF")

        for i, row in enumerate(section["rows"]):
            tree.insert("", "end", values=row,
                        tags=("even" if i % 2 == 0 else "odd",))

        tree.pack(fill="x")

    # ===== 設定タブ =====

    def _build_config_tab(self):
        outer = ttk.Frame(self.config_frame, padding=(20, 12))
        outer.pack(fill="both", expand=True)

        # ---- 人件費デフォルト ----
        ttk.Label(outer, text="【 シフトのデフォルト値 】", font=FONT_BOLD).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))

        ttk.Label(outer, text="デフォルト時給", font=FONT).grid(row=1, column=0, sticky="w", pady=4)
        self.cfg_wage_var = tk.StringVar(value=str(self.settings.get("default_wage", 1150)))
        ttk.Entry(outer, textvariable=self.cfg_wage_var, width=8, font=FONT).grid(
            row=1, column=1, sticky="w", padx=(10, 0))
        ttk.Label(outer, text="円　※ シフト入力フォームの初期値",
                  font=FONT_SMALL, foreground="gray").grid(row=1, column=2, sticky="w", padx=(8, 0))

        ttk.Label(outer, text="処遇改善手当", font=FONT).grid(row=2, column=0, sticky="w", pady=4)
        self.cfg_allow_var = tk.StringVar(value=str(self.settings.get("treatment_allowance", 250)))
        ttk.Entry(outer, textvariable=self.cfg_allow_var, width=8, font=FONT).grid(
            row=2, column=1, sticky="w", padx=(10, 0))
        ttk.Label(outer, text="円 / 時　※ 全シフトの有給時間に一律加算（割増なし）",
                  font=FONT_SMALL, foreground="gray").grid(row=2, column=2, sticky="w", padx=(8, 0))

        ttk.Separator(outer, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=10)

        # ---- 食費 ----
        ttk.Label(outer, text="【 食費（手当として支給） 】", font=FONT_BOLD).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(0, 4))

        def meal_row(label, key, default, r):
            ttk.Label(outer, text=label, font=FONT).grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=str(self.settings.get(key, default)))
            ttk.Entry(outer, textvariable=var, width=8, font=FONT).grid(
                row=r, column=1, sticky="w", padx=(10, 0))
            ttk.Label(outer, text="円 / 食", font=FONT).grid(row=r, column=2, sticky="w", padx=(4, 0))
            return var

        self.cfg_breakfast_var = meal_row("朝食", "breakfast_price", 300, 5)
        self.cfg_lunch_var     = meal_row("昼食", "lunch_price",     500, 6)
        self.cfg_dinner_var    = meal_row("夕食", "dinner_price",    500, 7)

        ttk.Separator(outer, orient="horizontal").grid(
            row=8, column=0, columnspan=3, sticky="ew", pady=10)

        # ---- 深夜帯設定 ----
        ttk.Label(outer, text="【 深夜時間帯の設定 】", font=FONT_BOLD).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(0, 4))

        # 深夜開始時刻
        ttk.Label(outer, text="深夜帯　開始", font=FONT).grid(row=10, column=0, sticky="w", pady=4)
        night_start_frame = ttk.Frame(outer)
        night_start_frame.grid(row=10, column=1, columnspan=2, sticky="w", padx=(10, 0))
        self.cfg_ns_h = tk.StringVar(value=str(self.settings.get("night_start_h", 22)))
        self.cfg_ns_m = tk.StringVar(value=f"{self.settings.get('night_start_m', 0):02d}")
        ttk.Entry(night_start_frame, textvariable=self.cfg_ns_h, width=4, font=FONT).pack(side="left")
        ttk.Label(night_start_frame, text="時", font=FONT).pack(side="left")
        ttk.Entry(night_start_frame, textvariable=self.cfg_ns_m, width=4, font=FONT).pack(side="left", padx=(4, 0))
        ttk.Label(night_start_frame, text="分", font=FONT).pack(side="left")

        # 深夜終了時刻
        ttk.Label(outer, text="深夜帯　終了", font=FONT).grid(row=11, column=0, sticky="w", pady=4)
        night_end_frame = ttk.Frame(outer)
        night_end_frame.grid(row=11, column=1, columnspan=2, sticky="w", padx=(10, 0))
        self.cfg_ne_h = tk.StringVar(value=str(self.settings.get("night_end_h", 5)))
        self.cfg_ne_m = tk.StringVar(value=f"{self.settings.get('night_end_m', 0):02d}")
        ttk.Entry(night_end_frame, textvariable=self.cfg_ne_h, width=4, font=FONT).pack(side="left")
        ttk.Label(night_end_frame, text="時", font=FONT).pack(side="left")
        ttk.Entry(night_end_frame, textvariable=self.cfg_ne_m, width=4, font=FONT).pack(side="left", padx=(4, 0))
        ttk.Label(night_end_frame, text="分　（翌日）", font=FONT).pack(side="left")

        # 深夜帯休憩
        ttk.Label(outer, text="深夜帯の休憩", font=FONT).grid(row=12, column=0, sticky="w", pady=4)
        night_brk_frame = ttk.Frame(outer)
        night_brk_frame.grid(row=12, column=1, columnspan=2, sticky="w", padx=(10, 0))
        self.cfg_night_brk = tk.StringVar(value=str(self.settings.get("night_break_min", 0)))
        ttk.Entry(night_brk_frame, textvariable=self.cfg_night_brk, width=6, font=FONT).pack(side="left")
        ttk.Label(night_brk_frame, text="分　※ シフトの休憩時間からこの分を深夜に割り当て",
                  font=FONT_SMALL, foreground="gray").pack(side="left", padx=(6, 0))

        ttk.Separator(outer, orient="horizontal").grid(
            row=13, column=0, columnspan=3, sticky="ew", pady=10)

        # ---- 保存ボタン ----
        sf = ttk.Frame(outer)
        sf.grid(row=14, column=0, columnspan=3, sticky="w")
        ttk.Button(sf, text="設定を保存する", command=self._save_config, width=16).pack(side="left")
        self.cfg_saved_label = ttk.Label(sf, text="", font=FONT_SMALL, foreground="#1a6fb5")
        self.cfg_saved_label.pack(side="left", padx=(12, 0))

    def _save_config(self):
        """設定タブの値を保存し、人件費計算と食費ラベルに反映する"""
        errors = []

        def parse_int(val, label, minimum=0):
            try:
                v = int(val)
                if v < minimum:
                    raise ValueError
                return v
            except ValueError:
                errors.append(f"{label}は{minimum}以上の整数で入力してください")
                return None

        wage  = parse_int(self.cfg_wage_var.get(),     "デフォルト時給", 1)
        allow = parse_int(self.cfg_allow_var.get(),    "処遇改善手当",   0)
        bp    = parse_int(self.cfg_breakfast_var.get(),"朝食の食費",     0)
        lp    = parse_int(self.cfg_lunch_var.get(),    "昼食の食費",     0)
        dp    = parse_int(self.cfg_dinner_var.get(),   "夕食の食費",     0)

        def parse_time_part(val, label, max_val):
            try:
                v = int(val)
                if not (0 <= v <= max_val):
                    raise ValueError
                return v
            except ValueError:
                errors.append(f"{label}の値が不正です（0〜{max_val}で入力してください）")
                return None

        ns_h  = parse_time_part(self.cfg_ns_h.get(),     "深夜開始（時）", 23)
        ns_m  = parse_time_part(self.cfg_ns_m.get(),     "深夜開始（分）", 59)
        ne_h  = parse_time_part(self.cfg_ne_h.get(),     "深夜終了（時）", 23)
        ne_m  = parse_time_part(self.cfg_ne_m.get(),     "深夜終了（分）", 59)
        n_brk = parse_int(self.cfg_night_brk.get(),      "深夜帯の休憩",   0)

        if errors:
            messagebox.showwarning("入力エラー", "\n".join(errors))
            return

        self.settings.update({
            "default_wage":        wage,
            "treatment_allowance": allow,
            "breakfast_price":     bp,
            "lunch_price":         lp,
            "dinner_price":        dp,
            "night_start_h":       ns_h,
            "night_start_m":       ns_m,
            "night_end_h":         ne_h,
            "night_end_m":         ne_m,
            "night_break_min":     n_brk,
        })
        save_settings(self.settings)

        # フォームのデフォルト時給・食費ラベルを更新する
        self.lf_wage.set(str(wage))
        self._update_meal_labels()
        self._refresh_labor()
        self._update_labor_preview()

        self.cfg_saved_label.config(text="保存しました")
        self.after(2000, lambda: self.cfg_saved_label.config(text=""))

    # ===== 印刷 =====

    def _print(self):
        """計算結果をHTMLに出力してブラウザで開く。Ctrl+Pで印刷できる"""
        unit_price = REGION_PRICES.get(self.region_var.get(), 10.00)
        year  = self.year_var.get()
        month = self.month_var.get()
        allow = self.settings.get("treatment_allowance", 0)
        bp    = self.settings.get("breakfast_price", 300)
        lp    = self.settings.get("lunch_price",     500)
        dp    = self.settings.get("dinner_price",    500)

        # 報酬
        resident_rows = []
        base_rev = 0.0
        for r in self.residents:
            upd   = SERVICE_UNITS.get(r["category"], 532)
            units = upd * r["days"]
            amt   = units * unit_price
            base_rev += amt
            resident_rows.append((r["name"], r["category"], r["days"], units, amt))

        # 人件費
        shift_rows = []
        labor_cost = 0.0
        for s in self.shifts:
            rn, rd, on, od = calc_shift_hours(
                s["start_h"], s["start_m"], s["end_h"], s["end_m"], s.get("break_min", 0),
                **self._night_kwargs())
            paid_h = rn + rd + on + od
            w_rn = rn * s["wage"]
            w_rd = rd * s["wage"] * (1 + NIGHT_PREMIUM)
            w_on = on * s["wage"] * (1 + OVERTIME_PREMIUM)
            w_od = od * s["wage"] * (1 + NIGHT_PREMIUM + OVERTIME_PREMIUM)
            w_al = paid_h * allow
            food_once = ((bp if s.get("breakfast") else 0) +
                         (lp if s.get("lunch")     else 0) +
                         (dp if s.get("dinner")    else 0))
            wage_once  = w_rn + w_rd + w_on + w_od + w_al
            total_once = wage_once + food_once
            sessions   = s["sessions"] * s["count"]
            monthly    = total_once * sessions
            labor_cost += monthly
            time_str = f"{s['start_h']:02d}:{s['start_m']:02d}〜{s['end_h']:02d}:{s['end_m']:02d}"
            meal_parts = ([f"朝食{bp}円"] if s.get("breakfast") else []) + \
                         ([f"昼食{lp}円"] if s.get("lunch")     else []) + \
                         ([f"夕食{dp}円"] if s.get("dinner")    else [])
            meal_str = "＋".join(meal_parts) if meal_parts else "なし"
            shift_rows.append((s.get("name",""), time_str, rn, rd, on, od, paid_h,
                                s["sessions"], s["count"], s["wage"],
                                w_rn, w_rd, w_on, w_od, w_al, food_once, total_once, monthly,
                                meal_str))

        balance       = base_rev - labor_cost
        bal_color     = "#1a6fb5" if balance >= 0 else "#c0392b"
        bal_str       = ("▲ " if balance < 0 else "") + fmt_yen(abs(balance))

        res_html = "".join(
            f"<tr><td>{r[0]}</td><td class='c'>{r[1]}</td>"
            f"<td class='r'>{r[2]}日</td><td class='r'>{r[3]:,}単位</td>"
            f"<td class='r'>{fmt_yen(r[4])}</td></tr>\n"
            for r in resident_rows
        )
        shift_html = "".join(
            f"<tr><td>{r[0]}</td><td class='c'>{r[1]}</td>"
            f"<td class='r'>{r[2]:.2f}h</td><td class='r'>{r[3]:.2f}h</td>"
            f"<td class='r'>{r[4]:.2f}h</td><td class='r'>{r[5]:.2f}h</td>"
            f"<td class='r'>{r[7]}回</td><td class='r'>{r[8]}人</td>"
            f"<td class='r'>{r[9]:,}円</td>"
            f"<td class='r' style='font-size:9pt'>{fmt_yen(r[10])}<br>{fmt_yen(r[11])}<br>"
            f"{fmt_yen(r[12])}<br>{fmt_yen(r[13])}<br>手当{fmt_yen(r[14])}<br>食費{fmt_yen(r[15])}</td>"
            f"<td class='r'>{fmt_yen(r[17])}</td></tr>\n"
            for r in shift_rows
        )

        html = f"""<!DOCTYPE html><html lang="ja">
<head><meta charset="UTF-8"><title>収支概算 {year}年{month}月</title>
<style>
  body {{ font-family:"MS Gothic","Meiryo",monospace; font-size:11pt; margin:20px; }}
  h1   {{ font-size:15pt; border-bottom:2px solid #333; padding-bottom:6px; }}
  h2   {{ font-size:12pt; margin-top:18px; border-left:4px solid #1a6fb5; padding-left:8px; }}
  table {{ border-collapse:collapse; width:100%; margin-bottom:10px; }}
  th {{ background:#dce8f5; padding:4px 8px; border:1px solid #aaa; text-align:center; }}
  td {{ padding:3px 8px; border:1px solid #ccc; vertical-align:middle; }}
  .c {{ text-align:center; }} .r {{ text-align:right; }}
  .tot {{ font-weight:bold; background:#f5f5f5; }}
  .bal {{ font-size:14pt; font-weight:bold; color:{bal_color}; }}
  .note {{ font-size:9pt; color:#888; margin-top:14px; line-height:1.8; }}
  @media print {{ body {{ margin:8mm; }} }}
</style></head>
<body>
<h1>月次収支概算　{year}年{month}月</h1>
<p>地域区分：{self.region_var.get()}（{unit_price}円/単位）</p>
<h2>報酬試算</h2>
<table>
  <tr><th>利用者名</th><th>区分</th><th>利用日数</th><th>単位数</th><th>報酬額</th></tr>
  {res_html}
  <tr class="tot"><td colspan="4" class="r">報酬合計（暫定）</td><td class="r">{fmt_yen(base_rev)}</td></tr>
</table>
<h2>人件費</h2>
<p style="font-size:9pt;color:#555">処遇改善手当 {allow:,}円/時（割増なし）／深夜×1.25／時間外×1.25／時間外深夜×1.50</p>
<table>
  <tr><th>シフト名</th><th>時間帯</th><th>正規通常</th><th>正規深夜</th><th>時外通常</th><th>時外深夜</th>
      <th>回数/月</th><th>人数</th><th>基本時給</th><th>内訳（1回）</th><th>月額</th></tr>
  {shift_html}
  <tr class="tot"><td colspan="10" class="r">人件費合計（賃金＋食費）</td><td class="r">{fmt_yen(labor_cost)}</td></tr>
</table>
<h2>収支概要</h2>
<table>
  <tr><td>報酬合計（暫定）</td><td class="r">{fmt_yen(base_rev)}</td></tr>
  <tr><td>人件費合計（賃金＋食費）</td><td class="r">{fmt_yen(labor_cost)}</td></tr>
  <tr class="tot"><td>収支差</td><td class="r bal">{bal_str}</td></tr>
</table>
<p class="note">
  ※ 概算です。実際の入金額は自己負担・加算・減算・給付費の審査等により異なります。<br>
  ※ 家賃・水道光熱費・備品費等は含まれていません。<br>
  出力日時：{datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M")}
</p></body></html>"""

        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".html", encoding="utf-8",
                delete=False, prefix=f"収支_{year}{month}_"
            ) as f:
                f.write(html)
            webbrowser.open(f"file:///{f.name.replace(os.sep, '/')}")
        except Exception as e:
            messagebox.showerror("印刷エラー", f"ファイルの作成に失敗しました：\n{e}")

    # ===== 共通処理 =====

    def _update_unit_price_label(self):
        price = REGION_PRICES.get(self.region_var.get(), 10.00)
        self.unit_price_label.config(text=f"（{price}円/単位）")

    def _on_header_changed(self):
        self._update_unit_price_label()
        self.settings.update({
            "region": self.region_var.get(),
            "year":   self.year_var.get(),
            "month":  self.month_var.get(),
        })
        save_settings(self.settings)
        self._refresh_all()

    def _refresh_all(self):
        self._refresh_revenue()
        self._refresh_labor()
        self._refresh_summary()


# ===== エントリーポイント =====

if __name__ == "__main__":
    app = FinanceApp()
    app.mainloop()
