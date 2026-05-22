# =============================================================================
# シェアホームすみか - 請求書生成アプリ  v2
# billing_app.py
#
# 変更点：
#   ・黒いコンソール画面を非表示（pythonw で起動）
#   ・PDF生成後に自動でビューアを起動
#   ・実績確認・修正タブを追加
#   ・利用者ごとの家賃・特別給付金設定タブを追加
#   ・PDF明細の「光熱水費（宿泊）」→「光熱水費」に修正
#   ・PDF明細の「日用品費（宿泊）」→「日用品費」に修正
#
# 起動方法：
#   黒画面なし → pythonw billing_app.py
#   通常起動   → python billing_app.py
#   CLI        → python billing_app.py 2026 4
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import sys
import json
import re
import calendar
import subprocess
from datetime import datetime, date

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT  = r"C:\GH_Data"  # 個人情報を保管する安全フォルダ（OneDrive・Claude非対応）
DATA_DIR      = os.path.join(PRIVATE_ROOT, "data")
BILLING_DIR   = os.path.join(BASE_DIR, "billing_app")
OUTPUT_DIR        = os.path.join(PRIVATE_ROOT, "output")          # 請求書PDF（氏名・金額含む）は安全フォルダへ
ZENGIN_OUTPUT_DIR = os.path.join(PRIVATE_ROOT, "zengin_output")  # 全銀ファイル（口座番号含む）は安全フォルダへ
SETTINGS_FILE = os.path.join(BILLING_DIR, "settings.json")
RESIDENTS_DB  = os.path.join(DATA_DIR, "residents.db")
DAILY_DB      = os.path.join(DATA_DIR, "daily_records.db")
USAGE_APP_PATH = os.path.join(BASE_DIR, "usage_app", "usage_app.py")

FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)

# =============================================================================
# デフォルト設定
# =============================================================================
DEFAULT_SETTINGS = {
    "prices": {
        "breakfast":   230,
        "lunch":       260,
        "dinner":      330,
        "utility":     600,
        "daily":       100,
        "trial_daily": 1000,   # 体験利用 1日あたり利用料
    },
    "issuer": {
        "name":  "シェアホームすみか",
        "org":   "NPO法人ななさと",
        "rep":   "理事長　○○　○○",
        "addr":  "○○県○○市○○1-2-3",
        "tel":   "000-000-0000",
        "email": "example@example.com",
        "bank":  "XX信用金庫 XX支店 普通 0000000 NPO法人ななさと",
    },
    # 全銀（RP）口座振替ファイル用設定
    "zengin": {
        "contractor_code":      "0000000000",  # 委託者コード（リコーから発行される10桁）
        "contractor_name_kana": "",            # 委託者名（半角カナ・スペース含め最大40文字）
        "bank_code":            "0000",        # 取引銀行番号（委託者の回収口座）
        "bank_name_kana":       "",            # 取引銀行名（半角カナ15文字）
        "branch_code":          "000",         # 取引支店番号
        "branch_name_kana":     "",            # 取引支店名（半角カナ15文字）
        "account_type":         "1",           # 預金種目（1:普通 2:当座）
        "account_number":       "0000000",     # 口座番号（7桁）
        "debit_day":            20,            # 引落日（毎月何日か）
    },
}

# =============================================================================
# ユーティリティ：全角/ひらがな → 半角カナ変換（全銀フォーマット用）
# =============================================================================
_ZEN_TO_HAN = {
    'ア':'ｱ','イ':'ｲ','ウ':'ｳ','エ':'ｴ','オ':'ｵ',
    'カ':'ｶ','キ':'ｷ','ク':'ｸ','ケ':'ｹ','コ':'ｺ',
    'サ':'ｻ','シ':'ｼ','ス':'ｽ','セ':'ｾ','ソ':'ｿ',
    'タ':'ﾀ','チ':'ﾁ','ツ':'ﾂ','テ':'ﾃ','ト':'ﾄ',
    'ナ':'ﾅ','ニ':'ﾆ','ヌ':'ﾇ','ネ':'ﾈ','ノ':'ﾉ',
    'ハ':'ﾊ','ヒ':'ﾋ','フ':'ﾌ','ヘ':'ﾍ','ホ':'ﾎ',
    'マ':'ﾏ','ミ':'ﾐ','ム':'ﾑ','メ':'ﾒ','モ':'ﾓ',
    'ヤ':'ﾔ','ユ':'ﾕ','ヨ':'ﾖ',
    'ラ':'ﾗ','リ':'ﾘ','ル':'ﾙ','レ':'ﾚ','ロ':'ﾛ',
    'ワ':'ﾜ','ヲ':'ｦ','ン':'ﾝ',
    'ァ':'ｧ','ィ':'ｨ','ゥ':'ｩ','ェ':'ｪ','ォ':'ｫ',
    'ッ':'ｯ','ャ':'ｬ','ュ':'ｭ','ョ':'ｮ',
    'ガ':'ｶﾞ','ギ':'ｷﾞ','グ':'ｸﾞ','ゲ':'ｹﾞ','ゴ':'ｺﾞ',
    'ザ':'ｻﾞ','ジ':'ｼﾞ','ズ':'ｽﾞ','ゼ':'ｾﾞ','ゾ':'ｿﾞ',
    'ダ':'ﾀﾞ','ヂ':'ﾁﾞ','ヅ':'ﾂﾞ','デ':'ﾃﾞ','ド':'ﾄﾞ',
    'バ':'ﾊﾞ','ビ':'ﾋﾞ','ブ':'ﾌﾞ','ベ':'ﾍﾞ','ボ':'ﾎﾞ',
    'パ':'ﾊﾟ','ピ':'ﾋﾟ','プ':'ﾌﾟ','ペ':'ﾍﾟ','ポ':'ﾎﾟ',
    'ヴ':'ｳﾞ','ー':'ｰ','　':' ',
}

def to_halfwidth_kana(text):
    """ひらがな・全角カタカナを半角カタカナに変換する（全銀フォーマット用）"""
    if not text:
        return ""
    result = []
    for ch in text:
        code = ord(ch)
        # ひらがな（U+3041〜U+3096）をカタカナに変換してから半角化
        if 0x3041 <= code <= 0x3096:
            ch = chr(code + 0x60)
        result.append(_ZEN_TO_HAN.get(ch, ch))
    return "".join(result)

def yucho_to_zengin(kigo: str, bango: str) -> dict:
    """
    ゆうちょ銀行の通帳記号・番号を、全銀ファイル用の口座情報に変換する。

    引数:
        kigo:  通帳記号（5桁 例: "12340"）
        bango: 通帳番号（末尾「1」を含む形式 例: "00012341"）
    戻り値:
        bank_code / bank_name / branch_code / branch_name /
        account_type / account_number を格納した辞書
    例外:
        ValueError: 入力値が不正な場合
    """
    # 数字以外を除去して純粋な数字列にする
    kigo_d  = re.sub(r'\D', '', kigo)
    bango_d = re.sub(r'\D', '', bango)

    # 通帳記号は必ず5桁（例: 12340）
    if len(kigo_d) != 5:
        raise ValueError(f"通帳記号は5桁の数字で入力してください（入力値: {kigo}）")

    if not bango_d:
        raise ValueError("通帳番号を入力してください")

    # 引落支店番号: 通帳記号 "1★★★0" の中3桁を取り出す
    branch_code = kigo_d[1:4]

    # 口座番号: 末尾の「1」を除く（ゆうちょ仕様）→ 7桁に前ゼロ埋め
    if bango_d.endswith("1") and len(bango_d) > 1:
        bango_d = bango_d[:-1]
    account_number = bango_d.zfill(7)

    if len(account_number) > 7:
        raise ValueError(f"口座番号が7桁を超えています（変換後: {account_number}）")

    return {
        "bank_code":      "9900",
        "bank_name":      "ﾕｳﾁｮｷﾞﾝｺｳ",
        "branch_code":    branch_code,
        "branch_name":    "",           # ゆうちょは支店名不要
        "account_type":   "1",          # 普通のみ（固定）
        "account_number": account_number,
    }


PAYMENT_OPTIONS = ["口座振替（集金代行）", "口座振込", "窓口現金払い"]
PAYMENT_KEYS    = ["transfer", "bank", "cash"]

# =============================================================================
# 設定ファイル
# =============================================================================
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "prices": {**DEFAULT_SETTINGS["prices"], **data.get("prices", {})},
                "issuer": {**DEFAULT_SETTINGS["issuer"], **data.get("issuer", {})},
                "zengin": {**DEFAULT_SETTINGS["zengin"], **data.get("zengin", {})},
            }
        except Exception:
            messagebox.showwarning(
                "設定ファイル読み込みエラー",
                "設定ファイルが壊れているためデフォルト設定で起動します。\n"
                f"ファイル: {SETTINGS_FILE}")
    return {k: dict(v) for k, v in DEFAULT_SETTINGS.items()}

def save_settings(s):
    os.makedirs(BILLING_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

# =============================================================================
# DB：列追加（初回自動）
# =============================================================================
def ensure_columns():
    """residents.db に不足列を自動追加する"""
    conn = sqlite3.connect(RESIDENTS_DB)
    c = conn.cursor()
    c.execute("PRAGMA table_info(residents)")
    existing = {row[1] for row in c.fetchall()}
    additions = [
        ("payment_method",    "TEXT DEFAULT 'transfer'"),
        # 全銀（口座振替）用 口座情報
        ("bank_code",         "TEXT DEFAULT ''"),   # 引落銀行番号（4桁）
        ("bank_name",         "TEXT DEFAULT ''"),   # 引落銀行名（半角カナ）
        ("branch_code",       "TEXT DEFAULT ''"),   # 引落支店番号（3桁）
        ("branch_name",       "TEXT DEFAULT ''"),   # 引落支店名（半角カナ）
        ("account_type",      "TEXT DEFAULT '1'"),  # 預金種目（1:普通 2:当座）
        ("account_number",    "TEXT DEFAULT ''"),   # 口座番号（7桁）
        ("account_holder",    "TEXT DEFAULT ''"),   # 預金者名（半角カナ30文字）
        ("transfer_new_code", "TEXT DEFAULT '0'"),  # 新規コード（0:継続 1:初回 2:変更）
    ]
    for col, typedef in additions:
        if col not in existing:
            c.execute(f"ALTER TABLE residents ADD COLUMN {col} {typedef}")
    conn.commit()
    conn.close()

# =============================================================================
# DB：入居者
# =============================================================================
def get_residents():
    if not os.path.exists(RESIDENTS_DB):
        raise FileNotFoundError(f"入居者DBが見つかりません：\n{RESIDENTS_DB}")
    ensure_columns()
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, name, furigana, room_number, rent, housing_subsidy,
               move_in_date, payment_method, status,
               bank_code, bank_name, branch_code, branch_name,
               account_type, account_number, account_holder, transfer_new_code
        FROM residents
        WHERE status = '入居中'
        ORDER BY room_number, id
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_residents_for_trial():
    """体験利用請求書タブ用：体験利用中の入居者を取得する"""
    ensure_columns()
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, name, furigana
        FROM residents WHERE status = '体験利用中'
        ORDER BY id
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def get_residents_for_settings():
    """利用者設定タブ用：全項目取得"""
    ensure_columns()
    conn = sqlite3.connect(RESIDENTS_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, name, room_number, rent, housing_subsidy, payment_method, status,
               bank_code, bank_name, branch_code, branch_name,
               account_type, account_number, account_holder, transfer_new_code
        FROM residents WHERE status IN ('入居中', '体験利用中')
        ORDER BY CASE status WHEN '入居中' THEN 0 ELSE 1 END, room_number, id
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def save_resident_billing_info(resident_id, room_number, rent, housing_subsidy,
                                payment_method, bank_code, bank_name,
                                branch_code, branch_name, account_type,
                                account_number, account_holder, transfer_new_code):
    """利用者の請求関連情報（家賃・口座）を更新する"""
    conn = sqlite3.connect(RESIDENTS_DB)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE residents
        SET room_number = ?, rent = ?, housing_subsidy = ?,
            payment_method = ?,
            bank_code = ?, bank_name = ?, branch_code = ?, branch_name = ?,
            account_type = ?, account_number = ?, account_holder = ?,
            transfer_new_code = ?,
            updated_at = ?
        WHERE id = ?
    """, (room_number, rent, housing_subsidy, payment_method,
          bank_code or None, bank_name or None,
          branch_code or None, branch_name or None,
          account_type or "1", account_number or None,
          account_holder or None, transfer_new_code or "0",
          now, resident_id))
    conn.commit()
    conn.close()

# =============================================================================
# DB：利用実績
# =============================================================================
def get_monthly_totals(resident_id, year, month):
    if not os.path.exists(DAILY_DB):
        return {"breakfast": 0, "lunch": 0, "dinner": 0, "stay": 0, "has_data": False}
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    prefix = f"{year:04d}-{month:02d}-"
    c.execute("""
        SELECT SUM(breakfast), SUM(lunch), SUM(dinner), SUM(stay), COUNT(*)
        FROM daily_records
        WHERE resident_id = ? AND record_date LIKE ?
    """, (resident_id, prefix + "%"))
    row = c.fetchone()
    conn.close()
    return {
        "breakfast": row[0] or 0,
        "lunch":     row[1] or 0,
        "dinner":    row[2] or 0,
        "stay":      row[3] or 0,
        "has_data":  (row[4] or 0) > 0,
    }

def get_monthly_detail(resident_id, year, month):
    """日別の実績を取得（実績確認タブ用）"""
    if not os.path.exists(DAILY_DB):
        return {}
    conn = sqlite3.connect(DAILY_DB)
    c = conn.cursor()
    prefix = f"{year:04d}-{month:02d}-"
    c.execute("""
        SELECT record_date, breakfast, lunch, dinner, stay, note
        FROM daily_records
        WHERE resident_id = ? AND record_date LIKE ?
        ORDER BY record_date
    """, (resident_id, prefix + "%"))
    rows = c.fetchall()
    conn.close()
    result = {}
    for row in rows:
        day = int(row[0].split("-")[2])
        result[day] = {
            "breakfast": bool(row[1]),
            "lunch":     bool(row[2]),
            "dinner":    bool(row[3]),
            "stay":      bool(row[4]),
            "note":      row[5] or "",
        }
    return result

def upsert_daily_record(resident_id, year, month, day, breakfast, lunch, dinner, stay, note):
    """1日分の実績をUPSERT"""
    conn = sqlite3.connect(DAILY_DB)
    record_date = f"{year:04d}-{month:02d}-{day:02d}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO daily_records
            (resident_id, record_date, breakfast, lunch, dinner, stay, note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resident_id, record_date) DO UPDATE SET
            breakfast = excluded.breakfast,
            lunch     = excluded.lunch,
            dinner    = excluded.dinner,
            stay      = excluded.stay,
            note      = excluded.note,
            updated_at = excluded.updated_at
    """, (resident_id, record_date,
          int(breakfast), int(lunch), int(dinner), int(stay), note, now))
    conn.commit()
    conn.close()

# =============================================================================
# 請求計算
# =============================================================================
def calc_billing(resident, year, month, settings):
    prices   = settings["prices"]
    last_day = calendar.monthrange(year, month)[1]
    is_trial = resident.get("status") == "体験利用中"

    move_in_str  = resident.get("move_in_date") or ""
    days         = last_day
    move_in_date = None
    try:
        move_in_date = date.fromisoformat(move_in_str)
        if move_in_date.year == year and move_in_date.month == month:
            days = last_day - move_in_date.day + 1
    except ValueError:
        pass

    totals    = get_monthly_totals(resident["id"], year, month)
    food_sub  = (
        totals["breakfast"] * prices["breakfast"] +
        totals["lunch"]     * prices["lunch"]     +
        totals["dinner"]    * prices["dinner"]
    )
    util_sub  = totals["stay"] * prices["utility"]
    daily_sub = totals["stay"] * prices["daily"]

    if is_trial:
        # 体験利用：1日単価×利用日数で計算。家賃・補助金なし
        trial_daily = prices.get("trial_daily", 1000)
        trial_fee   = trial_daily * days
        total = trial_fee + food_sub + util_sub + daily_sub
        return {
            "days":           days,
            "last_day":       last_day,
            "move_in_date":   move_in_date,
            "breakfast":      totals["breakfast"],
            "lunch":          totals["lunch"],
            "dinner":         totals["dinner"],
            "stay":           totals["stay"],
            "has_data":       totals["has_data"],
            "rent_sub":       0,
            "subsidy_deduct": 0,
            "food_sub":       food_sub,
            "util_sub":       util_sub,
            "daily_sub":      daily_sub,
            "total":          total,
            "is_trial":       True,
            "trial_fee":      trial_fee,
            "trial_daily":    trial_daily,
        }

    rent    = resident.get("rent") or 0
    subsidy = resident.get("housing_subsidy") or 0

    rent_sub       = round(rent * days / last_day) if days < last_day else rent
    subsidy_deduct = round(subsidy * days / last_day) if days < last_day else subsidy
    total          = rent_sub - subsidy_deduct + food_sub + util_sub + daily_sub

    return {
        "days":           days,
        "last_day":       last_day,
        "move_in_date":   move_in_date,
        "breakfast":      totals["breakfast"],
        "lunch":          totals["lunch"],
        "dinner":         totals["dinner"],
        "stay":           totals["stay"],
        "has_data":       totals["has_data"],
        "rent_sub":       rent_sub,
        "subsidy_deduct": subsidy_deduct,
        "food_sub":       food_sub,
        "util_sub":       util_sub,
        "daily_sub":      daily_sub,
        "total":          total,
        "is_trial":       False,
        "trial_fee":      0,
        "trial_daily":    0,
    }

# =============================================================================
# 発行日
# =============================================================================
def calc_issue_date(year, month):
    now = datetime.now()
    if now.year == year and now.month == month:
        return date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return date(now.year, now.month, now.day)

def to_wareki(d):
    return f"令和{d.year - 2018}年{d.month}月{d.day}日"

def payment_label(key):
    m = {"transfer": "口座振替（集金代行）", "bank": "口座振込", "cash": "窓口現金払い"}
    return m.get(key or "transfer", "口座振替（集金代行）")

# =============================================================================
# PDF生成
# =============================================================================
def generate_pdf(year, month, settings, output_path, issue_date=None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, HRFlowable
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise RuntimeError(
            "reportlabがインストールされていません。\n"
            "コマンドプロンプトで：pip install reportlab"
        )

    # 日本語フォント登録
    font_name = None
    for name, path in [
        ("YuGothic",    r"C:\Windows\Fonts\YuGothM.ttc"),
        ("YuGothic",    r"C:\Windows\Fonts\YuGothR.ttc"),
        ("IPAexGothic", r"C:\Windows\Fonts\ipaexg.ttf"),
        ("Meiryo",      r"C:\Windows\Fonts\meiryo.ttc"),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                font_name = name
                break
            except Exception:
                continue
    if font_name is None:
        raise RuntimeError(
            "日本語フォントが見つかりません。\n"
            "IPAexゴシック（ipaexg.ttf）を C:\\Windows\\Fonts に配置してください。\n"
            "ダウンロード先：https://moji.or.jp/ipafont/"
        )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    residents  = get_residents()
    if issue_date is None:
        issue_date = calc_issue_date(year, month)
    issue_str  = to_wareki(issue_date)
    last_day   = calendar.monthrange(year, month)[1]
    issuer     = settings["issuer"]
    prices     = settings["prices"]

    # 支払期限（翌月末）
    if month == 12:
        due = date(year + 1, 1, 31)
    else:
        due = date(year, month + 1, calendar.monthrange(year, month + 1)[1])
    due_str = f"{due.year}年{due.month}月{due.day}日"

    W, H = A4
    M    = 10 * mm

    def sty(name, size, bold=False, align="LEFT", color=colors.black, leading=None):
        return ParagraphStyle(
            name,
            fontName=font_name,
            fontSize=size,
            textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            leading=leading or size * 1.4,
            wordWrap="CJK",
        )

    s_title  = sty("title",  15, bold=True, align="CENTER")
    s_body   = sty("body",   10)
    s_body_r = sty("body_r", 10, align="RIGHT")
    s_body_c = sty("body_c", 10, align="CENTER")
    s_small  = sty("small",   9, color=colors.black)
    s_small_r= sty("smr",     9, color=colors.black, align="RIGHT")
    s_amount = sty("amount", 17, bold=True)
    s_green  = sty("green",  10, bold=True, color=colors.HexColor("#2a5c45"))

    def base_ts():
        return TableStyle([
            ("FONTNAME",       (0, 0), (-1, -1), font_name),
            ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f7f6f2")]),
            # 罫線を薄いグレーに（目立たせすぎない）
            ("LINEBELOW",  (0, 0), (-1, 0),  0.5, colors.HexColor("#999999")),
            ("LINEABOVE",  (0, 0), (-1, 0),  0.5, colors.HexColor("#999999")),
            ("LINEBELOW",  (0, -1), (-1, -1), 0.5, colors.HexColor("#999999")),
            # ヘッダー背景は薄いグレー・文字は濃色（読みやすさ優先）
            ("BACKGROUND", (0, 0), (-1, 0),  colors.HexColor("#cccccc")),
            ("TEXTCOLOR",  (0, 0), (-1, 0),  colors.HexColor("#1a1a1a")),
            ("FONTSIZE",   (0, 0), (-1, 0),  8),
            # 行パディングを3ptに絞って項目が増えてもA4に収まりやすくする
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ])

    def build_invoice(resident, calc):
        story  = []
        bill_to = resident.get("name", "")
        room    = resident.get("room_number", "")
        payment = resident.get("payment_method") or "transfer"

        is_trial = calc.get("is_trial", False)
        if is_trial:
            start_str  = (calc["move_in_date"].strftime("%Y/%m/%d")
                          if calc["move_in_date"] else f"{year}/{month:02d}/01")
            end_str    = f"{year}/{month:02d}/{last_day:02d}"
            period_str = f"{start_str}〜{end_str}"
            rent_label = ""
        elif calc["move_in_date"]:
            move_str   = calc["move_in_date"].strftime("%Y/%m/%d")
            end_str    = f"{year}/{month:02d}/{last_day:02d}"
            period_str = f"{move_str}〜{end_str}（日割り）"
            rent_label = (
                f"日割り計算\n"
                f"（¥{resident['rent']:,}÷{last_day}日×{calc['days']}日）"
            )
        else:
            period_str = f"{year}年{month}月1日〜{year}年{month}月{last_day}日"
            rent_label = f"¥{resident['rent']:,}"

        # ヘッダー（幅190mmで右端を明細・金額ボックスに揃える）
        hdr_tbl = Table(
            [[Paragraph(
                f"<font size=15><b>{bill_to}　様</b></font><br/>"
                f"<font size=8>下記のとおりご請求申し上げます</font>",
                s_body),
              Paragraph(
                f"<b>{issuer['name']}</b><br/>"
                f"{issuer['org']}<br/>"
                f"{issuer.get('rep','')}<br/>"
                f"{issuer.get('addr','')}<br/>"
                f"TEL：{issuer['tel']}<br/>"
                f"{issuer.get('email','')}<br/>"
                f"{issue_str}　発行",
                s_small)]],
            colWidths=[110*mm, 80*mm]  # 合計190mm・右列を右寄りに配置
        )
        hdr_tbl.setStyle(TableStyle([
            ("FONTNAME", (0,0),(-1,-1), font_name),
            ("VALIGN",   (0,0),(-1,-1), "TOP"),
        ]))

        # 金額ボックス（幅190mmで明細テーブルの両端に揃える）
        amt_tbl = Table(
            [[Paragraph("ご請求金額", s_small),
              Paragraph(f"¥{calc['total']:,}", s_amount),
              Paragraph(
                f"{year}年{month}月分施設利用料<br/>お支払期限：{due_str}まで",
                s_small_r)]],
            colWidths=[28*mm, 85*mm, 77*mm]  # 合計190mm
        )
        amt_tbl.setStyle(TableStyle([
            ("FONTNAME",      (0,0),(-1,-1), font_name),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
            ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#f5f4f0")),
            ("BOX",           (0,0),(-1,-1), 0.5, colors.HexColor("#cccccc")),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ]))

        def row(label, unit, qty, amount):
            return [
                Paragraph(label, s_body),
                Paragraph(unit, s_body_r),
                Paragraph(qty, s_body_c),
                Paragraph(f"¥{amount:,}", s_body_r),
            ]

        det = [
            [Paragraph("品目",s_body_c), Paragraph("単価",s_body_r),
             Paragraph("数量",s_body_c), Paragraph("金額",s_body_r)],
        ]
        if is_trial:
            # 体験利用：1日単価×利用日数の行を追加
            det.append(row(
                "体験利用料",
                f"¥{calc['trial_daily']:,}/日",
                f"{calc['days']}日",
                calc["trial_fee"],
            ))
        else:
            det.append(row(
                f"家賃（{room}）", rent_label,
                f"{calc['days']}日分" if calc['move_in_date'] else "1ヶ月",
                calc["rent_sub"],
            ))
            if calc["subsidy_deduct"] > 0:
                det.append([
                    Paragraph("特別給付金による家賃補助", s_green),
                    Paragraph("", s_body_r),
                    Paragraph("", s_body_c),
                    Paragraph(f"−¥{calc['subsidy_deduct']:,}", s_green),
                ])
        det += [
            row("朝食", f"¥{prices['breakfast']}/回",
                f"{calc['breakfast']}回", prices['breakfast']*calc['breakfast']),
            row("昼食", f"¥{prices['lunch']}/回",
                f"{calc['lunch']}回",    prices['lunch']*calc['lunch']),
            row("夕食", f"¥{prices['dinner']}/回",
                f"{calc['dinner']}回",   prices['dinner']*calc['dinner']),
            # ★「（宿泊）」を削除
            row("光熱水費", f"¥{prices['utility']}/日",
                f"{calc['stay']}日", calc["util_sub"]),
            row("日用品費", f"¥{prices['daily']}/日",
                f"{calc['stay']}日", calc["daily_sub"]),
        ]
        det.append([
            Paragraph("合　計", s_body_c),
            Paragraph("", s_body),
            Paragraph("", s_body),
            Paragraph(f"¥{calc['total']:,}",
                      sty("tot",10,bold=True,align="RIGHT")),
        ])

        # 列幅をページ有効幅（190mm）に合わせて調整
        det_tbl = Table(det, colWidths=[85*mm, 55*mm, 25*mm, 25*mm])
        ts = base_ts()
        ts.add("SPAN",       (0,-1),(2,-1))
        ts.add("BACKGROUND", (0,-1),(-1,-1), colors.HexColor("#f0f0f0"))
        ts.add("FONTSIZE",   (0,-1),(-1,-1), 9.5)
        det_tbl.setStyle(ts)

        def chk(key):
            return "■" if payment == key else "□"

        pay_txt = (
            f"<b>お支払先・お支払方法</b><br/>"
            f"{chk('bank')} {issuer['bank']}<br/>"
            f"{chk('cash')} 当事業所窓口での現金払い（9時〜15時）<br/>"
            f"{chk('transfer')} 集金代行サービスによる口座振替"
            f"（毎月20日。金融機関休業日の場合は翌営業日）<br/>"
            f"※口座振替によるお支払いの場合、"
            f"当事業所からの領収書発行はいたしません。"
            f"金融機関の通帳記帳・利用明細が領収の証明となります。"
        )

        def receipt_box(title):
            # 年月日記入欄：セル幅いっぱい・下線付き・中央寄せ
            date_line = Table(
                [["　　　　年　　　月　　　日"]],
                colWidths=[68*mm]  # 枠内コンテンツ幅（90-8*2=74mm）に近づける
            )
            date_line.setStyle(TableStyle([
                ("FONTNAME",     (0,0),(-1,-1), font_name),
                ("FONTSIZE",     (0,0),(-1,-1), 10),
                ("ALIGN",        (0,0),(-1,-1), "CENTER"),
                ("LINEBELOW",    (0,0),(-1,-1), 0.5, colors.black),
                ("TOPPADDING",   (0,0),(-1,-1), 4),
                ("BOTTOMPADDING",(0,0),(-1,-1), 2),
            ]))
            date_line.hAlign = "CENTER"  # セル内で日付テーブルを中央配置
            return [
                Paragraph(f"<b>{title}</b>",
                          sty(f"rt{title}", 10, bold=True, align="CENTER")),
                Spacer(1, 2*mm),
                Paragraph(f"<b>{bill_to}　様</b>",
                          sty(f"rn{title}", 12, bold=True, align="CENTER")),
                Paragraph(f"{year}年{month}月分　施設利用料",
                          sty(f"rs{title}", 9, align="CENTER")),
                Spacer(1, 2*mm),
                Paragraph(f"¥{calc['total']:,}",
                          sty(f"ra{title}", 17, bold=True, align="CENTER")),
                Spacer(1, 2*mm),
                Paragraph("として上記正に領収いたしました。",
                          sty(f"rb{title}", 9, align="CENTER")),
                Spacer(1, 4*mm),
                date_line,
                Spacer(1, 3*mm),
                Paragraph(
                    f"{issuer['org']}<br/>"
                    f"{issuer['name']}<br/>"
                    f"{issuer.get('rep','')}　印",
                    sty(f"ri{title}", 9, align="CENTER")
                ),
            ]

        # 領収書2枚を均等幅で並べる（左右対称）
        r_tbl = Table(
            [[receipt_box("領収書（控）"), receipt_box("領収書")]],
            colWidths=[90*mm, 90*mm]
        )
        r_tbl.setStyle(TableStyle([
            ("FONTNAME",      (0,0),(-1,-1), font_name),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ("BOX",           (0,0),(0,0), 1.2, colors.black),
            ("BOX",           (1,0),(1,0), 1.2, colors.black),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ]))

        story += [
            Paragraph("請　求　書", s_title),
            HRFlowable(width="100%", thickness=1.5,
                       color=colors.HexColor("#1a1a1a")),
            Spacer(1, 2*mm),
            hdr_tbl,
            Spacer(1, 2*mm),
            amt_tbl,
            Spacer(1, 3*mm),  # ご請求金額ボックスの下の余白を広げる
            Paragraph(f"対象期間：{period_str}　（全{last_day}日）", s_small),
            Spacer(1, 2*mm),
            det_tbl,
            Spacer(1, 2*mm),
            Paragraph(pay_txt, sty("pay", 9, color=colors.black)),
            Spacer(1, 4*mm),
            # 切り取り線
            HRFlowable(width="100%", thickness=0.5,
                       color=colors.HexColor("#aaaaaa"), dash=(3, 4)),
            Paragraph("✂　切り取り線",
                      sty("cut", 7, color=colors.HexColor("#aaaaaa"))),
            Spacer(1, 4*mm),
            r_tbl,
            PageBreak(),
        ]
        return story

    all_story = []
    calcs = []
    for res in residents:
        c = calc_billing(res, year, month, settings)
        calcs.append(c)
        all_story += build_invoice(res, c)

    if all_story and isinstance(all_story[-1], PageBreak):
        all_story.pop()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
    )
    doc.build(all_story)

# =============================================================================
# 全銀（RP）口座振替ファイル生成
# =============================================================================
def generate_zengin_file(year, month, settings, output_path):
    """
    全銀（RP）フォーマットの口座振替ファイルを生成する。

    ファイル仕様（全銀協制定）:
    ・Shift-JIS固定長テキスト、1レコード=120バイト+CRLF
    ・ヘッダー(1) + データ(N) + トレーラー(1) + エンド(1)
    ・数字フィールド：右詰め・前ゼロ埋め
    ・文字フィールド：左詰め・残りスペース埋め（半角カナ）
    ・対象：payment_method = 'transfer'（口座振替）の入居者のみ

    戻り値: (対象件数, 合計金額, スキップした入居者名リスト) のタプル
    """

    def pn(value, width):
        """数字フィールド：右詰め前ゼロ埋め、bytes返却"""
        return str(int(value or 0)).zfill(width).encode("cp932")

    def ps(value, width):
        """文字フィールド（左詰め）：残りスペース埋め、bytes返却"""
        b = str(value or "").encode("cp932", errors="replace")
        b = b[:width]
        return b + b" " * (width - len(b))

    def psr(value, width):
        """文字フィールド（右詰め）：前スペース埋め、bytes返却（顧客番号用）"""
        b = str(value or "").encode("cp932", errors="replace")
        b = b[:width]
        return b" " * (width - len(b)) + b

    zengin = settings.get("zengin", DEFAULT_SETTINGS["zengin"])

    # 引落日（翌月の debit_day 日）
    debit_day = int(zengin.get("debit_day", 20))
    debit_m   = 1 if month == 12 else month + 1
    debit_mmdd = f"{debit_m:02d}{debit_day:02d}".encode("cp932")

    # 委託者名（上20バイト / 下20バイト）
    cname_b     = zengin.get("contractor_name_kana", "").encode("cp932", errors="replace")
    cname_upper = (cname_b[:20]).ljust(20)
    cname_lower = (cname_b[20:40]).ljust(20)

    records = []

    # ━━ ヘッダーレコード（120バイト）━━━━━━━━━━━━━━━━
    hdr  = b"1"                                              # データ区分(1)   固定"1"
    hdr += b"91"                                             # 種別コード(2)   91=口座振替
    hdr += b"0"                                              # コード区分(1)   0=JIS
    hdr += pn(zengin.get("contractor_code", "0"), 10)        # 委託者コード(10)
    hdr += cname_upper                                       # 委託者名上(20)
    hdr += cname_lower                                       # 委託者名下(20)
    hdr += debit_mmdd                                        # 引落日(4) MMDD
    hdr += pn(zengin.get("bank_code",   "0"), 4)             # 取引銀行番号(4)
    hdr += ps(zengin.get("bank_name_kana", ""), 15)          # 取引銀行名(15)
    hdr += pn(zengin.get("branch_code", "0"), 3)             # 取引支店番号(3)
    hdr += ps(zengin.get("branch_name_kana", ""), 15)        # 取引支店名(15)
    hdr += ps(zengin.get("account_type", "1"), 1)            # 預金種目(1)
    hdr += pn(zengin.get("account_number", "0"), 7)          # 口座番号(7)
    hdr += b" " * 17                                         # 余白(17)
    assert len(hdr) == 120, f"ヘッダー長エラー:{len(hdr)}バイト"
    records.append(hdr)

    # ━━ データレコード（入居者ごと）━━━━━━━━━━━━━━━━━
    all_residents = get_residents()
    targets = [r for r in all_residents if r.get("payment_method") == "transfer"]

    grand_total = 0
    count       = 0
    skipped     = []   # 口座未入力のためスキップした入居者名

    for res in targets:
        if not res.get("account_number"):
            skipped.append(res.get("name", ""))
            continue

        calc   = calc_billing(res, year, month, settings)
        amount = calc["total"]
        if amount <= 0:
            continue

        holder_raw = res.get("account_holder") or res.get("furigana", "")
        holder     = to_halfwidth_kana(holder_raw)
        customer_id = f"R{res['id']:05d}"

        dat  = b"2"                                          # データ区分(1)   固定"2"
        dat += pn(res.get("bank_code",   "0"), 4)           # 引落銀行番号(4)
        dat += ps(res.get("bank_name",   ""), 15)           # 引落銀行名(15)
        dat += pn(res.get("branch_code", "0"), 3)           # 引落支店番号(3)
        dat += ps(res.get("branch_name", ""), 15)           # 引落支店名(15)
        dat += b"    "                                       # 余白(4)
        dat += ps(res.get("account_type", "1"), 1)          # 預金種目(1)
        dat += pn(res.get("account_number", "0"), 7)        # 口座番号(7) 右詰前ゼロ
        dat += ps(holder, 30)                               # 預金者名(30) 半角カナ
        dat += pn(amount, 10)                               # 引落金額(10)
        dat += ps(res.get("transfer_new_code", "0"), 1)     # 新規コード(1)
        dat += psr(customer_id, 20)                         # 顧客番号(20) 右詰
        dat += b"0"                                          # 振替結果コード(1) 固定"0"
        dat += b" " * 8                                     # 余白(8)
        assert len(dat) == 120, f"データレコード長エラー:{len(dat)}バイト ({res['name']})"
        records.append(dat)
        grand_total += amount
        count       += 1

    if count == 0:
        msg = "出力対象の入居者がいません。\n\n"
        if not targets:
            msg += "「利用者設定」タブで支払い方法を\n「口座振替（集金代行）」に設定してください。"
        elif skipped:
            msg += f"以下の入居者の口座情報が未入力です：\n{'、'.join(skipped)}\n\n"
            msg += "「利用者設定」タブで口座情報を入力してください。"
        raise ValueError(msg)

    # ━━ トレーラレコード（120バイト）━━━━━━━━━━━━━━━━
    trl  = b"8"              # データ区分(1)    固定"8"
    trl += pn(count, 6)      # 合計件数(6)
    trl += pn(grand_total, 12)  # 合計金額(12)
    trl += b"0" * 6          # 振替済件数(6)    =000000
    trl += b"0" * 12         # 振替済金額(12)   =000000000000
    trl += b"0" * 6          # 振替不能件数(6)  =000000
    trl += b"0" * 12         # 振替不能金額(12) =000000000000
    trl += b" " * 65         # 余白(65)
    assert len(trl) == 120, f"トレーラ長エラー:{len(trl)}バイト"
    records.append(trl)

    # ━━ エンドレコード（120バイト）━━━━━━━━━━━━━━━━━
    end = b"9" + b" " * 119
    assert len(end) == 120
    records.append(end)

    # ファイル出力（各レコード末尾に CRLF を付加）
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        for rec in records:
            f.write(rec + b"\r\n")

    return count, grand_total, skipped


# =============================================================================
# PDF を OS のビューアで開く
# =============================================================================
def open_pdf(path):
    try:
        os.startfile(path)   # Windows
    except AttributeError:
        subprocess.run(["open", path])   # Mac fallback

# =============================================================================
# 体験利用請求書PDF生成
# =============================================================================
def generate_trial_pdf(resident, start_date, end_date, meals, settings, output_path,
                       housing_subsidy=0, issue_date=None):
    """
    体験利用者の請求書PDFを1枚生成する。

    引数:
        resident:         入居者情報の辞書（name, furigana）
        start_date:       体験利用開始日（date型）
        end_date:         体験利用終了日（date型）
        meals:            {"breakfast": int, "lunch": int, "dinner": int}
        settings:         設定辞書
        output_path:      出力先ファイルパス
        housing_subsidy:  家賃補助額（円）。上限は実費と10,000円の低い方
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise RuntimeError(
            "reportlabがインストールされていません。\n"
            "コマンドプロンプトで：pip install reportlab"
        )

    # 日本語フォント登録
    font_name = None
    for name, path in [
        ("YuGothic",    r"C:\Windows\Fonts\YuGothM.ttc"),
        ("YuGothic",    r"C:\Windows\Fonts\YuGothR.ttc"),
        ("IPAexGothic", r"C:\Windows\Fonts\ipaexg.ttf"),
        ("Meiryo",      r"C:\Windows\Fonts\meiryo.ttc"),
    ]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                font_name = name
                break
            except Exception:
                continue
    if font_name is None:
        raise RuntimeError(
            "日本語フォントが見つかりません。\n"
            "IPAexゴシック（ipaexg.ttf）を C:\\Windows\\Fonts に配置してください。"
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    issuer = settings["issuer"]
    prices = settings["prices"]

    # 泊数 = 終了日 − 開始日（例：1泊2日 → nights=1）
    # 日数 = 泊数 + 1（退所日当日も1日分として請求）
    nights = (end_date - start_date).days
    if nights <= 0:
        raise ValueError("終了日は開始日より後の日付を指定してください。")

    days = nights + 1  # 体験利用時家賃は退所日も含めた日数で計算

    trial_daily = prices.get("trial_daily", 1000)
    breakfast   = meals.get("breakfast", 0)
    lunch       = meals.get("lunch",     0)
    dinner      = meals.get("dinner",    0)

    trial_fee  = trial_daily * days
    food_cost  = (prices["breakfast"] * breakfast +
                  prices["lunch"]     * lunch +
                  prices["dinner"]    * dinner)
    util_cost  = prices["utility"] * nights
    daily_cost = prices["daily"]   * nights

    # 家賃補助：実費と10,000円の低い方が上限
    housing_subsidy_deduct = min(trial_fee, int(housing_subsidy or 0), 10000)

    total = trial_fee - housing_subsidy_deduct + food_cost + util_cost + daily_cost

    issue_str  = to_wareki(issue_date if issue_date is not None else date.today())
    start_str  = f"{start_date.year}年{start_date.month}月{start_date.day}日"
    end_str    = f"{end_date.year}年{end_date.month}月{end_date.day}日"
    period_str = f"{start_str}〜{end_str}（{nights}泊{days}日）"

    M = 10 * mm

    def sty(name, size, bold=False, align="LEFT", color=colors.black):
        return ParagraphStyle(
            name, fontName=font_name, fontSize=size, textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            leading=size * 1.4, wordWrap="CJK",
        )

    s_title  = sty("title",  15, bold=True, align="CENTER")
    s_body   = sty("body",   10)
    s_body_r = sty("body_r", 10, align="RIGHT")
    s_body_c = sty("body_c", 10, align="CENTER")
    s_small  = sty("small",   9)
    s_small_r= sty("smr",     9, align="RIGHT")
    s_amount = sty("amount", 17, bold=True)
    s_green  = sty("green",  10, bold=True, color=colors.HexColor("#2a5c45"))

    def base_ts():
        return TableStyle([
            ("FONTNAME",       (0, 0), (-1, -1), font_name),
            ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f7f6f2")]),
            ("LINEBELOW",     (0,  0), (-1,  0), 0.5, colors.HexColor("#999999")),
            ("LINEABOVE",     (0,  0), (-1,  0), 0.5, colors.HexColor("#999999")),
            ("LINEBELOW",     (0, -1), (-1, -1), 0.5, colors.HexColor("#999999")),
            ("BACKGROUND",    (0,  0), (-1,  0), colors.HexColor("#cccccc")),
            ("TEXTCOLOR",     (0,  0), (-1,  0), colors.HexColor("#1a1a1a")),
            ("FONTSIZE",      (0,  0), (-1,  0), 8),
            ("TOPPADDING",    (0,  0), (-1, -1), 3),
            ("BOTTOMPADDING", (0,  0), (-1, -1), 3),
            ("LEFTPADDING",   (0,  0), (-1, -1), 6),
            ("RIGHTPADDING",  (0,  0), (-1, -1), 6),
        ])

    def row(label, unit, qty, amount):
        return [
            Paragraph(label,              s_body),
            Paragraph(unit,               s_body_r),
            Paragraph(qty,                s_body_c),
            Paragraph(f"¥{amount:,}",    s_body_r),
        ]

    # ── ヘッダー（宛名 ＋ 発行者） ──
    hdr_tbl = Table(
        [[Paragraph(
            f"<font size=15><b>{resident['name']}　様</b></font><br/>"
            f"<font size=8>下記のとおりご請求申し上げます</font>",
            s_body),
          Paragraph(
            f"<b>{issuer['name']}</b><br/>"
            f"{issuer['org']}<br/>"
            f"{issuer.get('rep','')}<br/>"
            f"{issuer.get('addr','')}<br/>"
            f"TEL：{issuer['tel']}<br/>"
            f"{issuer.get('email','')}<br/>"
            f"{issue_str}　発行",
            s_small)]],
        colWidths=[110*mm, 80*mm]
    )
    hdr_tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("VALIGN",   (0, 0), (-1, -1), "TOP"),
    ]))

    # ── ご請求金額ボックス ──
    amt_tbl = Table(
        [[Paragraph("ご請求金額", s_small),
          Paragraph(f"¥{total:,}", s_amount),
          Paragraph("体験利用料", s_small_r)]],
        colWidths=[28*mm, 85*mm, 77*mm]
    )
    amt_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), font_name),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f5f4f0")),
        ("BOX",           (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))

    # ── 明細テーブル ──
    det = [
        [Paragraph("品目",   s_body_c), Paragraph("単価",   s_body_r),
         Paragraph("数量",   s_body_c), Paragraph("金額",   s_body_r)],
        row("家賃（体験利用）",
            f"¥{trial_daily:,}/日", f"{days}日",  trial_fee),
    ]
    if housing_subsidy_deduct > 0:
        det.append([
            Paragraph("特別給付金による家賃補助", s_green),
            Paragraph("", s_body_r),
            Paragraph("", s_body_c),
            Paragraph(f"−¥{housing_subsidy_deduct:,}", s_green),
        ])
    det += [
        row("朝食",
            f"¥{prices['breakfast']:,}/回", f"{breakfast}回",
            prices["breakfast"] * breakfast),
        row("昼食",
            f"¥{prices['lunch']:,}/回",     f"{lunch}回",
            prices["lunch"] * lunch),
        row("夕食",
            f"¥{prices['dinner']:,}/回",    f"{dinner}回",
            prices["dinner"] * dinner),
        row("光熱水費",
            f"¥{prices['utility']:,}/泊",   f"{nights}泊",  util_cost),
        row("日用品費",
            f"¥{prices['daily']:,}/泊",     f"{nights}泊",  daily_cost),
    ]
    det.append([
        Paragraph("合　計", s_body_c),
        Paragraph("", s_body), Paragraph("", s_body),
        Paragraph(f"¥{total:,}",
                  sty("tot", 10, bold=True, align="RIGHT")),
    ])

    det_tbl = Table(det, colWidths=[70*mm, 50*mm, 35*mm, 35*mm])
    ts = base_ts()
    ts.add("SPAN",       (0, -1), (2, -1))
    ts.add("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0"))
    det_tbl.setStyle(ts)

    # ── 領収書ボックス（切り取り線の下に2枚並べる） ──
    bill_to      = resident["name"]
    period_label = f"{start_str}〜{end_str}　体験利用料"

    def receipt_box(title):
        """領収書1枚分の要素リストを返す"""
        date_line = Table(
            [["　　　　年　　　月　　　日"]],
            colWidths=[68*mm]
        )
        date_line.setStyle(TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), font_name),
            ("FONTSIZE",      (0, 0), (-1, -1), 10),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.5, colors.black),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        date_line.hAlign = "CENTER"
        return [
            Paragraph(f"<b>{title}</b>",
                      sty(f"rt{title}", 10, bold=True, align="CENTER")),
            Spacer(1, 2*mm),
            Paragraph(f"<b>{bill_to}　様</b>",
                      sty(f"rn{title}", 12, bold=True, align="CENTER")),
            Paragraph(period_label,
                      sty(f"rs{title}", 9, align="CENTER")),
            Spacer(1, 2*mm),
            Paragraph(f"¥{total:,}",
                      sty(f"ra{title}", 17, bold=True, align="CENTER")),
            Spacer(1, 2*mm),
            Paragraph("として上記正に領収いたしました。",
                      sty(f"rb{title}", 9, align="CENTER")),
            Spacer(1, 4*mm),
            date_line,
            Spacer(1, 3*mm),
            Paragraph(
                f"{issuer['org']}<br/>"
                f"{issuer['name']}<br/>"
                f"{issuer.get('rep', '')}　印",
                sty(f"ri{title}", 9, align="CENTER")
            ),
        ]

    r_tbl = Table(
        [[receipt_box("領収書（控）"), receipt_box("領収書")]],
        colWidths=[90*mm, 90*mm]
    )
    r_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), font_name),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BOX",           (0, 0), (0, 0),  1.2, colors.black),
        ("BOX",           (1, 0), (1, 0),  1.2, colors.black),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    pay_txt = (
        f"<b>お支払先・お支払方法</b><br/>"
        f"□ {issuer['bank']}<br/>"
        f"□ 当事業所窓口での現金払い（9時〜15時）"
    )

    story = [
        Paragraph("体験利用請求書", s_title),
        HRFlowable(width="100%", thickness=1.5,
                   color=colors.HexColor("#1a1a1a")),
        Spacer(1, 4*mm),
        hdr_tbl,
        Spacer(1, 4*mm),
        amt_tbl,
        Spacer(1, 3*mm),
        Paragraph(f"体験利用期間：{period_str}", s_small),
        Spacer(1, 2*mm),
        det_tbl,
        Spacer(1, 2*mm),
        Paragraph(pay_txt, sty("pay", 9, color=colors.black)),
        Spacer(1, 4*mm),
        # 切り取り線
        HRFlowable(width="100%", thickness=0.5,
                   color=colors.HexColor("#aaaaaa"), dash=(3, 4)),
        Paragraph("✂　切り取り線",
                  sty("cut", 7, color=colors.HexColor("#aaaaaa"))),
        Spacer(1, 4*mm),
        r_tbl,
    ]

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
    )
    doc.build(story)


# =============================================================================
# GUI アプリ
# =============================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("すみか 請求書生成システム")
        self.geometry("820x680")
        self.resizable(False, False)
        self.settings = load_settings()
        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

    def _build(self):
        hdr = tk.Frame(self, bg="#1c1c1a")
        hdr.pack(fill="x")
        tk.Label(hdr, text="すみか 請求書生成システム",
                 font=FONT_TITLE, bg="#1c1c1a", fg="white").pack(
                     side="left", padx=16, pady=10)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_main     = tk.Frame(nb, bg="#f7f6f2")
        self.tab_record   = tk.Frame(nb, bg="#f7f6f2")
        self.tab_resident = tk.Frame(nb, bg="#f7f6f2")
        self.tab_trial    = tk.Frame(nb, bg="#f7f6f2")
        self.tab_settings = tk.Frame(nb, bg="#f7f6f2")

        nb.add(self.tab_main,     text="  請求書生成  ")
        nb.add(self.tab_record,   text="  実績確認・修正  ")
        nb.add(self.tab_resident, text="  利用者設定  ")
        nb.add(self.tab_trial,    text="  体験利用請求書  ")
        nb.add(self.tab_settings, text="  設定  ")

        self._build_main(self.tab_main)
        self._build_record(self.tab_record)
        self._build_resident(self.tab_resident)
        self._build_trial(self.tab_trial)
        self._build_settings(self.tab_settings)

    # ── タブ1：請求書生成 ──────────────────────────────────────
    def _build_main(self, parent):
        body = tk.Frame(parent, bg="#f7f6f2")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        today = date.today()
        if today.day >= 20:
            dy, dm = today.year, today.month
        else:
            dm = today.month - 1 if today.month > 1 else 12
            dy = today.year if today.month > 1 else today.year - 1

        ym_frame = tk.LabelFrame(body, text="対象年月", bg="#f7f6f2", font=FONT)
        ym_frame.pack(fill="x", pady=(0,12))
        inner = tk.Frame(ym_frame, bg="#f7f6f2")
        inner.pack(padx=12, pady=10)

        self.year_var  = tk.IntVar(value=dy)
        self.month_var = tk.IntVar(value=dm)

        tk.Label(inner, text="年：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner, from_=2020, to=2099, textvariable=self.year_var,
                   width=6, font=FONT).pack(side="left")
        tk.Label(inner, text="　月：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner, from_=1, to=12, textvariable=self.month_var,
                   width=4, font=FONT).pack(side="left")

        self.year_var.trace_add("write",  lambda *_: self._update_label())
        self.month_var.trace_add("write", lambda *_: self._update_label())

        # ── 請求書作成日 ──
        iss_frame = tk.LabelFrame(body, text="請求書作成日", bg="#f7f6f2", font=FONT)
        iss_frame.pack(fill="x", pady=(0, 12))
        inner_iss = tk.Frame(iss_frame, bg="#f7f6f2")
        inner_iss.pack(padx=12, pady=8)

        self.issue_y = tk.IntVar(value=today.year)
        self.issue_m = tk.IntVar(value=today.month)
        self.issue_d = tk.IntVar(value=today.day)

        tk.Label(inner_iss, text="年：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_iss, from_=2020, to=2099,
                   textvariable=self.issue_y, width=6, font=FONT).pack(side="left")
        tk.Label(inner_iss, text="　月：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_iss, from_=1, to=12,
                   textvariable=self.issue_m, width=4, font=FONT).pack(side="left")
        tk.Label(inner_iss, text="　日：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_iss, from_=1, to=31,
                   textvariable=self.issue_d, width=4, font=FONT).pack(side="left")
        tk.Label(inner_iss, text="　※ デフォルトは今日の日付",
                 font=FONT_SMALL, bg="#f7f6f2", fg="#888888").pack(side="left", padx=8)

        self.output_label = tk.Label(
            body, text=self._output_path_label(),
            font=FONT_SMALL, bg="#f7f6f2", fg="#555555",
            anchor="w", wraplength=540)
        self.output_label.pack(fill="x", pady=(0,8))

        chk_frame = tk.LabelFrame(body, text="利用実績入力状況",
                                   bg="#f7f6f2", font=FONT)
        chk_frame.pack(fill="x", pady=(0,10))
        self.check_text = tk.Label(
            chk_frame, text="（生成ボタンを押すと確認します）",
            font=FONT_SMALL, bg="#f7f6f2", fg="#888888",
            anchor="w", justify="left", wraplength=520)
        self.check_text.pack(padx=12, pady=8, fill="x")

        btn_frame = tk.Frame(body, bg="#f7f6f2")
        btn_frame.pack(pady=8)

        tk.Button(
            btn_frame, text="📄　請求書PDFを生成する",
            font=FONT_BOLD, bg="#2a5c45", fg="white",
            relief="flat", padx=20, pady=10,
            command=self._generate
        ).pack(side="left", padx=(0, 12))

        tk.Button(
            btn_frame, text="🏦　口座振替ファイルを出力する",
            font=FONT_BOLD, bg="#1a4a7a", fg="white",
            relief="flat", padx=20, pady=10,
            command=self._generate_zengin
        ).pack(side="left")

        self.status_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.status_var,
                 font=FONT_SMALL, bg="#f7f6f2", fg="#2a5c45",
                 wraplength=540, justify="left").pack(pady=4)

    def _pdf_output_path(self):
        y, m = self.year_var.get(), self.month_var.get()
        return os.path.join(OUTPUT_DIR, f"請求書_{y}年{m}月.pdf")

    def _zengin_output_path(self):
        # 全銀協推奨：半角英数字のみ・8.3形式（例：RP202604.TXT）
        # 口座番号を含むため、安全フォルダ（ZENGIN_OUTPUT_DIR）へ出力する
        y, m = self.year_var.get(), self.month_var.get()
        return os.path.join(ZENGIN_OUTPUT_DIR, f"RP{y:04d}{m:02d}.TXT")

    def _output_path_label(self):
        return (
            f"PDF出力先：{self._pdf_output_path()}\n"
            f"全銀出力先：{self._zengin_output_path()}"
        )

    def _update_label(self):
        try:
            self.output_label.config(text=self._output_path_label())
        except Exception:
            pass

    def _generate(self):
        year  = self.year_var.get()
        month = self.month_var.get()
        output_path = self._pdf_output_path()

        self.status_var.set("確認中...")
        self.update()

        try:
            residents = get_residents()
            if not residents:
                messagebox.showwarning("確認", "入居中の入居者が登録されていません。")
                self.status_var.set("")
                return

            # 実績チェック（詳細表示付き）
            check_lines = []
            no_data = []
            for r in residents:
                t = get_monthly_totals(r["id"], year, month)
                if t["has_data"]:
                    check_lines.append(
                        f"✅ {r['name']}：宿泊{t['stay']}日 朝{t['breakfast']} 昼{t['lunch']} 夕{t['dinner']}"
                    )
                else:
                    no_data.append(r["name"])
                    check_lines.append(f"⬜ {r['name']}：未入力")

            self.check_text.config(
                text="\n".join(check_lines),
                fg="#2a5c45" if not no_data else "#856404"
            )
            self.update()

            if no_data:
                names = "、".join(no_data)
                if not messagebox.askyesno(
                    "確認",
                    f"以下の入居者の利用実績が未入力です：\n{names}\n\nこのまま生成しますか？"
                ):
                    self.status_var.set("")
                    return

            self.status_var.set("生成中...")
            self.update()
            try:
                iss_date = date(self.issue_y.get(), self.issue_m.get(), self.issue_d.get())
            except ValueError:
                messagebox.showwarning("入力エラー", "請求書作成日が正しくありません。")
                self.status_var.set("")
                return
            generate_pdf(year, month, self.settings, output_path, issue_date=iss_date)
            self.status_var.set(f"✅ 生成完了：{output_path}")

            # ★ PDF を自動で開く
            open_pdf(output_path)

        except FileNotFoundError as e:
            messagebox.showerror("エラー", str(e))
            self.status_var.set("")
        except RuntimeError as e:
            messagebox.showerror("エラー", str(e))
            self.status_var.set("")
        except Exception as e:
            messagebox.showerror("エラー", f"生成に失敗しました。\n{e}")
            self.status_var.set("")

    def _generate_zengin(self):
        """全銀（RP）口座振替ファイルを出力する"""
        year  = self.year_var.get()
        month = self.month_var.get()
        output_path = self._zengin_output_path()

        self.status_var.set("全銀ファイル生成中...")
        self.update()

        try:
            residents = get_residents()
            if not residents:
                messagebox.showwarning("確認", "入居中の入居者が登録されていません。")
                self.status_var.set("")
                return

            count, total, skipped = generate_zengin_file(
                year, month, self.settings, output_path
            )

            fname = os.path.basename(output_path)
            self.status_var.set(
                f"✅ 全銀ファイル生成完了：{output_path}\n"
                f"　　{count}件　合計金額 ¥{total:,}"
            )

            skip_msg = ""
            if skipped:
                skip_msg = f"\n\n⚠ 口座情報未入力のため除外：{'、'.join(skipped)}"

            # 引落年月（翌月 YYYYMM）
            debit_m = 1 if month == 12 else month + 1
            debit_y = year + 1 if month == 12 else year
            debit_ym = f"{debit_y:04d}{debit_m:02d}"

            messagebox.showinfo(
                "全銀ファイル出力完了",
                f"{year}年{month}月分の口座振替ファイルを出力しました。\n\n"
                f"出力先：{output_path}\n"
                f"ファイル名：{fname}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"  アップロード時に入力する値\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"  請求データ合計金額：{total:,} 円\n"
                f"  請求データ合計件数：{count} 件\n"
                f"  引落年月（YYYYMM）：{debit_ym}\n"
                f"━━━━━━━━━━━━━━━━━━━━━"
                f"{skip_msg}"
            )

        except ValueError as e:
            messagebox.showwarning("確認", str(e))
            self.status_var.set("")
        except FileNotFoundError as e:
            messagebox.showerror("エラー", str(e))
            self.status_var.set("")
        except AssertionError as e:
            messagebox.showerror("フォーマットエラー", str(e))
            self.status_var.set("")
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル生成に失敗しました。\n{e}")
            self.status_var.set("")

    # ── タブ2：実績確認・修正 ──────────────────────────────────
    def _build_record(self, parent):
        body = tk.Frame(parent, bg="#f7f6f2")
        body.pack(fill="both", expand=True, padx=40, pady=40)

        tk.Label(body,
                 text="利用実績の入力・修正は\n「利用実績入力アプリ」で行います。",
                 font=FONT_TITLE, bg="#f7f6f2", justify="center").pack(pady=(40,20))

        tk.Label(body,
                 text="以下のボタンをクリックすると\n利用実績入力アプリが起動します。",
                 font=FONT, bg="#f7f6f2", fg="#555555", justify="center").pack(pady=(0,30))

        tk.Button(
            body,
            text="📋　利用実績入力アプリを開く",
            font=FONT_BOLD, bg="#2a5c45", fg="white",
            relief="flat", padx=30, pady=16,
            command=self._open_usage_app
        ).pack()

        tk.Label(body,
                 text=f"\n起動先：{USAGE_APP_PATH}",
                 font=FONT_SMALL, bg="#f7f6f2", fg="#aaaaaa").pack(pady=(16,0))

    def _open_usage_app(self):
        if not os.path.exists(USAGE_APP_PATH):
            messagebox.showerror(
                "エラー",
                f"利用実績アプリが見つかりません。\n{USAGE_APP_PATH}"
            )
            return
        try:
            year  = self.year_var.get()
            month = self.month_var.get()
            # 環境変数で対象年月を渡す（usage_app.py側が対応していれば自動選択される）
            import os as _os
            env = _os.environ.copy()
            env["GH_TARGET_YEAR"]  = str(year)
            env["GH_TARGET_MONTH"] = str(month)
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            subprocess.Popen(
                ["pythonw", USAGE_APP_PATH],
                env=env,
                creationflags=flags
            )
            messagebox.showinfo(
                "利用実績アプリを起動しました",
                f"対象月：{year}年{month}月\n\n入力完了後にこの画面に戻って請求書を生成してください。"
            )
        except Exception as e:
            messagebox.showerror("エラー", f"起動に失敗しました。\n{e}")

    def _load_records(self):
        for row in self.rec_tree.get_children():
            self.rec_tree.delete(row)
        year  = self.rec_year.get()
        month = self.rec_month.get()
        try:
            residents = get_residents()
        except Exception:
            return
        for res in residents:
            t = get_monthly_totals(res["id"], year, month)
            status = "✅入力済" if t["has_data"] else "⬜未入力"
            tag    = "" if t["has_data"] else "no_data"
            self.rec_tree.insert("", "end",
                iid=str(res["id"]),
                values=(res["name"], t["stay"], t["breakfast"],
                        t["lunch"], t["dinner"], status),
                tags=(tag,))

    def _edit_record(self, event):
        """ダブルクリックで月合計編集ダイアログを開く"""
        sel = self.rec_tree.selection()
        if not sel:
            return
        res_id = int(sel[0])
        year   = self.rec_year.get()
        month  = self.rec_month.get()
        totals = get_monthly_totals(res_id, year, month)
        name   = self.rec_tree.item(sel[0])["values"][0]

        dlg = tk.Toplevel(self)
        dlg.title(f"{name}　{year}年{month}月　実績編集")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg,
                 text=f"{name}さんの {year}年{month}月分 月合計を入力してください",
                 font=FONT, pady=8).pack(padx=20)

        fields = [
            ("宿泊日数", "stay"),
            ("朝食 回数", "breakfast"),
            ("昼食 回数", "lunch"),
            ("夕食 回数", "dinner"),
        ]
        vars_ = {}
        for label, key in fields:
            row = tk.Frame(dlg)
            row.pack(fill="x", padx=24, pady=4)
            tk.Label(row, text=label, font=FONT, width=14, anchor="w").pack(side="left")
            v = tk.IntVar(value=totals[key])
            vars_[key] = v
            tk.Spinbox(row, from_=0, to=99, textvariable=v,
                       width=6, font=FONT).pack(side="left")

        last_day = calendar.monthrange(year, month)[1]
        tk.Label(dlg,
                 text=f"（{year}年{month}月は全{last_day}日）",
                 font=FONT_SMALL, fg="#888888").pack(pady=(0,4))

        def save():
            stay = vars_["stay"].get()
            bf   = vars_["breakfast"].get()
            lc   = vars_["lunch"].get()
            dn   = vars_["dinner"].get()
            # 既存の日別データを一括上書き（1日分として保存）
            # すでにデータがある場合は全日クリアして再設定
            conn = sqlite3.connect(DAILY_DB)
            prefix = f"{year:04d}-{month:02d}-"
            conn.execute(
                "DELETE FROM daily_records WHERE resident_id = ? AND record_date LIKE ?",
                (res_id, prefix + "%")
            )
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 合計値を1日目にまとめて保存（集計用途なので日別でなくても可）
            conn.execute("""
                INSERT INTO daily_records
                    (resident_id, record_date, breakfast, lunch, dinner, stay, note, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, '', ?)
            """, (res_id, f"{year:04d}-{month:02d}-01", bf, lc, dn, stay, now))
            conn.commit()
            conn.close()
            dlg.destroy()
            self._load_records()
            messagebox.showinfo("保存", f"{name}さんの実績を保存しました。")

        btn_f = tk.Frame(dlg)
        btn_f.pack(pady=12)
        tk.Button(btn_f, text="保存", font=FONT_BOLD,
                  bg="#2a5c45", fg="white", relief="flat",
                  padx=16, pady=6, command=save).pack(side="left", padx=8)
        tk.Button(btn_f, text="キャンセル", font=FONT,
                  padx=16, pady=6, command=dlg.destroy).pack(side="left", padx=8)

        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width()  - dlg.winfo_width())  // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")

    # ── タブ3：利用者設定 ──────────────────────────────────────
    def _build_resident(self, parent):
        body = tk.Frame(parent, bg="#f7f6f2")
        body.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(body,
                 text="利用者ごとの居室・家賃・特別給付金・支払い方法を設定します。",
                 font=FONT_SMALL, bg="#f7f6f2", fg="#555555").pack(
                     anchor="w", pady=(0,8))

        # スクロールキャンバス
        canvas = tk.Canvas(body, bg="#f7f6f2", highlightthickness=0)
        sb     = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.res_inner = tk.Frame(canvas, bg="#f7f6f2")
        self._res_win  = canvas.create_window((0,0), window=self.res_inner, anchor="nw")
        self.res_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(self._res_win, width=e.width)
        )

        self.res_vars = {}
        self._load_resident_settings()

        tk.Button(
            body, text="利用者設定を保存",
            font=FONT_BOLD, bg="#2a5c45", fg="white",
            relief="flat", padx=16, pady=8,
            command=self._save_resident_settings
        ).pack(pady=10)

    def _load_resident_settings(self):
        for w in self.res_inner.winfo_children():
            w.destroy()
        self.res_vars = {}



        try:
            residents = get_residents_for_settings()
        except Exception:
            residents = []

        for res in residents:
            # 利用者ごとにカード形式で表示
            card = tk.LabelFrame(
                self.res_inner,
                text=f"  {res['name']}  ",
                font=FONT_BOLD, bg="#f7f6f2",
                padx=12, pady=8
            )
            card.pack(fill="x", pady=6, padx=4)

            v_room    = tk.StringVar(value=res.get("room_number", "") or "")
            v_rent    = tk.IntVar(value=res.get("rent", 0) or 0)
            v_subsidy = tk.IntVar(value=res.get("housing_subsidy", 0) or 0)
            v_payment = tk.StringVar(value=res.get("payment_method", "transfer") or "transfer")

            # 居室
            r1 = tk.Frame(card, bg="#f7f6f2")
            r1.pack(fill="x", pady=3)
            tk.Label(r1, text="居室名", font=FONT, bg="#f7f6f2",
                     width=16, anchor="w").pack(side="left")
            tk.Entry(r1, textvariable=v_room, font=FONT, width=20).pack(side="left")

            # 家賃
            r2 = tk.Frame(card, bg="#f7f6f2")
            r2.pack(fill="x", pady=3)
            tk.Label(r2, text="家賃（月額・円）", font=FONT, bg="#f7f6f2",
                     width=16, anchor="w").pack(side="left")
            tk.Spinbox(r2, from_=0, to=999999, textvariable=v_rent,
                       width=12, font=FONT).pack(side="left")

            # 特別給付金
            r3 = tk.Frame(card, bg="#f7f6f2")
            r3.pack(fill="x", pady=3)
            tk.Label(r3, text="特別給付金（月額・円）", font=FONT, bg="#f7f6f2",
                     width=16, anchor="w").pack(side="left")
            tk.Spinbox(r3, from_=0, to=999999, textvariable=v_subsidy,
                       width=12, font=FONT).pack(side="left")
            tk.Label(r3, text="※補助なしの場合は0",
                     font=FONT_SMALL, bg="#f7f6f2", fg="#888888").pack(
                         side="left", padx=8)

            # 支払い方法
            r4 = tk.Frame(card, bg="#f7f6f2")
            r4.pack(fill="x", pady=3)
            tk.Label(r4, text="支払い方法", font=FONT, bg="#f7f6f2",
                     width=16, anchor="w").pack(side="left")
            cb = ttk.Combobox(r4, textvariable=v_payment,
                              values=PAYMENT_OPTIONS,
                              state="readonly", width=24, font=FONT)
            try:
                cb.current(PAYMENT_KEYS.index(
                    res.get("payment_method", "transfer") or "transfer"))
            except ValueError:
                cb.current(0)
            cb.bind("<<ComboboxSelected>>",
                    lambda e, v=v_payment, c=cb: v.set(
                        PAYMENT_KEYS[PAYMENT_OPTIONS.index(c.get())]))
            cb.pack(side="left")

            # ── 口座振替情報（全銀ファイル用）──────────────────
            bank_lf = tk.LabelFrame(card, text="口座振替情報（全銀ファイル用）",
                                    font=FONT_SMALL, bg="#f7f6f2",
                                    fg="#1a4a7a", padx=8, pady=4)
            bank_lf.pack(fill="x", pady=(6, 2))

            v_bank_code    = tk.StringVar(value=res.get("bank_code", "") or "")
            v_bank_name    = tk.StringVar(value=res.get("bank_name", "") or "")
            v_branch_code  = tk.StringVar(value=res.get("branch_code", "") or "")
            v_branch_name  = tk.StringVar(value=res.get("branch_name", "") or "")
            v_acct_type    = tk.StringVar(value=res.get("account_type", "1") or "1")
            v_acct_num     = tk.StringVar(value=res.get("account_number", "") or "")
            v_acct_holder  = tk.StringVar(value=res.get("account_holder", "") or "")
            v_new_code     = tk.StringVar(value=res.get("transfer_new_code", "0") or "0")

            bank_fields = [
                ("引落銀行番号（4桁）",   v_bank_code,   6,  "例）0005"),
                ("引落銀行名（半角カナ）", v_bank_name,   20, "例）ﾐﾂﾋﾞｼUFJ"),
                ("引落支店番号（3桁）",   v_branch_code, 6,  "例）001"),
                ("引落支店名（半角カナ）", v_branch_name, 20, "例）ﾄｳｷｮｳ"),
            ]
            for lbl, var, w, hint in bank_fields:
                bf = tk.Frame(bank_lf, bg="#f7f6f2")
                bf.pack(fill="x", pady=2)
                tk.Label(bf, text=lbl, font=FONT_SMALL, bg="#f7f6f2",
                         width=20, anchor="w").pack(side="left")
                tk.Entry(bf, textvariable=var, font=FONT, width=w).pack(side="left")
                tk.Label(bf, text=hint, font=FONT_SMALL,
                         bg="#f7f6f2", fg="#888888").pack(side="left", padx=6)

            # ── ゆうちょ銀行自動入力ボタン ──────────────────────────
            def open_yucho_dialog(
                    vbc=v_bank_code, vbn=v_bank_name,
                    vbrc=v_branch_code, vbrn=v_branch_name,
                    vat=v_acct_type, van=v_acct_num):
                """
                ゆうちょ銀行の通帳記号・番号を入力し、
                全銀形式の口座情報に自動変換して各フィールドへ反映する。
                """
                dlg = tk.Toplevel()
                dlg.title("ゆうちょ銀行 口座情報の自動入力")
                dlg.resizable(False, False)
                dlg.grab_set()
                bg = "#f7f6f2"
                dlg.configure(bg=bg)

                tk.Label(dlg, text="通帳記号（5桁）", font=FONT, bg=bg).grid(
                    row=0, column=0, padx=12, pady=10, sticky="w")
                v_kigo = tk.StringVar()
                tk.Entry(dlg, textvariable=v_kigo, font=FONT, width=10).grid(
                    row=0, column=1, padx=8)
                tk.Label(dlg, text="例）12340", font=FONT_SMALL, bg=bg,
                         fg="#888888").grid(row=0, column=2, padx=4)

                tk.Label(dlg, text="通帳番号（末尾の1を含む）", font=FONT, bg=bg).grid(
                    row=1, column=0, padx=12, pady=10, sticky="w")
                v_bango = tk.StringVar()
                tk.Entry(dlg, textvariable=v_bango, font=FONT, width=10).grid(
                    row=1, column=1, padx=8)
                tk.Label(dlg, text="例）00012341", font=FONT_SMALL, bg=bg,
                         fg="#888888").grid(row=1, column=2, padx=4)

                # エラーメッセージ表示用ラベル
                msg_var = tk.StringVar()
                tk.Label(dlg, textvariable=msg_var, font=FONT_SMALL,
                         bg=bg, fg="red").grid(row=2, column=0, columnspan=3, padx=12)

                def apply():
                    """変換して各フィールドに値をセットする"""
                    try:
                        result = yucho_to_zengin(v_kigo.get(), v_bango.get())
                        vbc.set(result["bank_code"])
                        vbn.set(result["bank_name"])
                        vbrc.set(result["branch_code"])
                        vbrn.set(result["branch_name"])
                        vat.set(result["account_type"])
                        van.set(result["account_number"])
                        dlg.destroy()
                    except ValueError as e:
                        msg_var.set(str(e))

                btn_f = tk.Frame(dlg, bg=bg)
                btn_f.grid(row=3, column=0, columnspan=3, pady=12)
                tk.Button(btn_f, text="自動入力する", command=apply,
                          font=FONT_BOLD, bg="#1a4a7a", fg="white",
                          relief="flat", cursor="hand2",
                          padx=12, pady=4).pack(side="left", padx=8)
                tk.Button(btn_f, text="キャンセル", command=dlg.destroy,
                          font=FONT, bg="#e0e0e0", relief="flat",
                          cursor="hand2", padx=12, pady=4).pack(side="left")

            bf_yu = tk.Frame(bank_lf, bg="#f7f6f2")
            bf_yu.pack(fill="x", pady=(4, 2))
            tk.Button(bf_yu, text="ゆうちょ銀行の場合はこちら →",
                      command=open_yucho_dialog,
                      font=FONT_SMALL, bg="#e8f0fb", fg="#1a4a7a",
                      relief="flat", cursor="hand2",
                      padx=8, pady=3).pack(side="left")
            tk.Label(bf_yu,
                     text="通帳記号・番号を入力すると自動で変換します",
                     font=FONT_SMALL, bg="#f7f6f2",
                     fg="#888888").pack(side="left", padx=8)

            # 預金種目
            bf_at = tk.Frame(bank_lf, bg="#f7f6f2")
            bf_at.pack(fill="x", pady=2)
            tk.Label(bf_at, text="預金種目", font=FONT_SMALL, bg="#f7f6f2",
                     width=20, anchor="w").pack(side="left")
            for val, lbl in [("1", "1:普通"), ("2", "2:当座")]:
                tk.Radiobutton(bf_at, text=lbl, variable=v_acct_type, value=val,
                               font=FONT_SMALL, bg="#f7f6f2").pack(side="left", padx=4)

            # 口座番号
            bf_an = tk.Frame(bank_lf, bg="#f7f6f2")
            bf_an.pack(fill="x", pady=2)
            tk.Label(bf_an, text="口座番号（7桁）", font=FONT_SMALL, bg="#f7f6f2",
                     width=20, anchor="w").pack(side="left")
            tk.Entry(bf_an, textvariable=v_acct_num, font=FONT, width=10).pack(side="left")
            tk.Label(bf_an, text="ゆうちょは通帳番号の末尾「1」を除いた7桁",
                     font=FONT_SMALL, bg="#f7f6f2", fg="#888888").pack(side="left", padx=6)

            # 預金者名
            bf_ah = tk.Frame(bank_lf, bg="#f7f6f2")
            bf_ah.pack(fill="x", pady=2)
            tk.Label(bf_ah, text="預金者名（半角カナ）", font=FONT_SMALL, bg="#f7f6f2",
                     width=20, anchor="w").pack(side="left")
            tk.Entry(bf_ah, textvariable=v_acct_holder, font=FONT, width=32).pack(side="left")
            tk.Label(bf_ah, text="空欄のときはふりがなを自動変換",
                     font=FONT_SMALL, bg="#f7f6f2", fg="#888888").pack(side="left", padx=6)

            # 新規コード
            bf_nc = tk.Frame(bank_lf, bg="#f7f6f2")
            bf_nc.pack(fill="x", pady=2)
            tk.Label(bf_nc, text="新規コード", font=FONT_SMALL, bg="#f7f6f2",
                     width=20, anchor="w").pack(side="left")
            for val, lbl in [("0", "0:継続"), ("1", "1:初回"), ("2", "2:変更")]:
                tk.Radiobutton(bf_nc, text=lbl, variable=v_new_code, value=val,
                               font=FONT_SMALL, bg="#f7f6f2").pack(side="left", padx=4)

            self.res_vars[res["id"]] = {
                "room":         v_room,
                "rent":         v_rent,
                "subsidy":      v_subsidy,
                "payment":      v_payment,
                "bank_code":    v_bank_code,
                "bank_name":    v_bank_name,
                "branch_code":  v_branch_code,
                "branch_name":  v_branch_name,
                "acct_type":    v_acct_type,
                "acct_num":     v_acct_num,
                "acct_holder":  v_acct_holder,
                "new_code":     v_new_code,
            }

    def _save_resident_settings(self):
        try:
            for res_id, v in self.res_vars.items():
                pay = v["payment"].get()
                if pay not in PAYMENT_KEYS:
                    pay = "transfer"
                save_resident_billing_info(
                    res_id,
                    v["room"].get().strip(),
                    v["rent"].get(),
                    v["subsidy"].get(),
                    pay,
                    v["bank_code"].get().strip(),
                    v["bank_name"].get().strip(),
                    v["branch_code"].get().strip(),
                    v["branch_name"].get().strip(),
                    v["acct_type"].get().strip() or "1",
                    v["acct_num"].get().strip(),
                    v["acct_holder"].get().strip(),
                    v["new_code"].get().strip() or "0",
                )
            messagebox.showinfo("保存完了", "利用者設定を保存しました。")
            self._load_resident_settings()
        except Exception as e:
            messagebox.showerror("エラー", f"保存に失敗しました。\n{e}")

    # ── タブ4：体験利用請求書 ──────────────────────────────────
    def _build_trial(self, parent):
        """体験利用請求書タブのUIを構築する"""
        body = tk.Frame(parent, bg="#f7f6f2")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        # ── 利用者選択 ──
        res_frame = tk.LabelFrame(body, text="体験利用者", bg="#f7f6f2", font=FONT)
        res_frame.pack(fill="x", pady=(0, 12))
        inner_res = tk.Frame(res_frame, bg="#f7f6f2")
        inner_res.pack(padx=12, pady=10, fill="x")

        tk.Label(inner_res, text="利用者：", font=FONT, bg="#f7f6f2").pack(side="left")
        self.trial_resident_var = tk.StringVar()
        self.trial_resident_cb  = ttk.Combobox(
            inner_res, textvariable=self.trial_resident_var,
            font=FONT, width=20, state="readonly"
        )
        self.trial_resident_cb.pack(side="left", padx=8)
        tk.Button(
            inner_res, text="更新",
            command=self._refresh_trial_residents,
            font=FONT_SMALL, bg="#e0e0e0", relief="flat",
            cursor="hand2", padx=8, pady=2
        ).pack(side="left", padx=4)
        tk.Label(
            inner_res,
            text="※ 入居者マスターで「体験利用中」のステータスの方が表示されます",
            font=FONT_SMALL, bg="#f7f6f2", fg="#888888"
        ).pack(side="left", padx=8)

        self._trial_residents = []
        self._refresh_trial_residents()

        # ── 利用期間 ──
        period_frame = tk.LabelFrame(body, text="体験利用期間", bg="#f7f6f2", font=FONT)
        period_frame.pack(fill="x", pady=(0, 12))
        inner_p = tk.Frame(period_frame, bg="#f7f6f2")
        inner_p.pack(padx=12, pady=10)

        today = date.today()
        self.trial_start_y = tk.IntVar(value=today.year)
        self.trial_start_m = tk.IntVar(value=today.month)
        self.trial_start_d = tk.IntVar(value=today.day)
        self.trial_end_y   = tk.IntVar(value=today.year)
        self.trial_end_m   = tk.IntVar(value=today.month)
        self.trial_end_d   = tk.IntVar(value=today.day)

        for row_i, (label, vy, vm, vd) in enumerate([
            ("開始日：", self.trial_start_y, self.trial_start_m, self.trial_start_d),
            ("終了日：", self.trial_end_y,   self.trial_end_m,   self.trial_end_d),
        ]):
            tk.Label(inner_p, text=label, font=FONT,
                     bg="#f7f6f2").grid(row=row_i, column=0, sticky="w", pady=4)
            tk.Spinbox(inner_p, from_=2020, to=2099,
                       textvariable=vy, width=6, font=FONT).grid(row=row_i, column=1)
            tk.Label(inner_p, text="年", font=FONT,
                     bg="#f7f6f2").grid(row=row_i, column=2, padx=(2, 8))
            tk.Spinbox(inner_p, from_=1, to=12,
                       textvariable=vm, width=4, font=FONT).grid(row=row_i, column=3)
            tk.Label(inner_p, text="月", font=FONT,
                     bg="#f7f6f2").grid(row=row_i, column=4, padx=(2, 8))
            tk.Spinbox(inner_p, from_=1, to=31,
                       textvariable=vd, width=4, font=FONT).grid(row=row_i, column=5)
            tk.Label(inner_p, text="日", font=FONT,
                     bg="#f7f6f2").grid(row=row_i, column=6, padx=2)

        tk.Label(
            inner_p,
            text="※ 退所日当日も日数に含みます（例：5月1日〜5月2日 → 1泊2日 → 2日分請求）",
            font=FONT_SMALL, bg="#f7f6f2", fg="#888888"
        ).grid(row=2, column=0, columnspan=7, sticky="w", pady=(4, 0))

        # ── 食事回数 ──
        meal_frame = tk.LabelFrame(body, text="食事回数", bg="#f7f6f2", font=FONT)
        meal_frame.pack(fill="x", pady=(0, 12))
        inner_m = tk.Frame(meal_frame, bg="#f7f6f2")
        inner_m.pack(padx=12, pady=10)

        self.trial_breakfast = tk.IntVar(value=0)
        self.trial_lunch     = tk.IntVar(value=0)
        self.trial_dinner    = tk.IntVar(value=0)

        for col, (lbl, var) in enumerate([
            ("朝食", self.trial_breakfast),
            ("昼食", self.trial_lunch),
            ("夕食", self.trial_dinner),
        ]):
            tk.Label(inner_m, text=f"{lbl}：", font=FONT,
                     bg="#f7f6f2").grid(row=0, column=col*3,     padx=(0 if col==0 else 20, 4))
            tk.Spinbox(inner_m, from_=0, to=99, textvariable=var,
                       width=5, font=FONT).grid(row=0, column=col*3+1)
            tk.Label(inner_m, text="回", font=FONT,
                     bg="#f7f6f2").grid(row=0, column=col*3+2, padx=(2, 0))

        # ── 家賃補助 ──
        subsidy_frame = tk.LabelFrame(body, text="家賃補助", bg="#f7f6f2", font=FONT)
        subsidy_frame.pack(fill="x", pady=(0, 12))
        inner_s = tk.Frame(subsidy_frame, bg="#f7f6f2")
        inner_s.pack(padx=12, pady=10, fill="x")

        self.trial_housing_subsidy = tk.IntVar(value=10000)
        tk.Label(inner_s, text="家賃補助額：", font=FONT,
                 bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_s, from_=0, to=10000,
                   textvariable=self.trial_housing_subsidy,
                   width=8, font=FONT).pack(side="left", padx=(0, 4))
        tk.Label(inner_s, text="円", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Label(
            inner_s,
            text="　※ 上限：実際の家賃請求額または10,000円の低い方",
            font=FONT_SMALL, bg="#f7f6f2", fg="#888888"
        ).pack(side="left", padx=8)

        # ── 請求書作成日 ──
        trial_iss_frame = tk.LabelFrame(body, text="請求書作成日", bg="#f7f6f2", font=FONT)
        trial_iss_frame.pack(fill="x", pady=(0, 12))
        inner_ti = tk.Frame(trial_iss_frame, bg="#f7f6f2")
        inner_ti.pack(padx=12, pady=8)

        self.trial_issue_y = tk.IntVar(value=today.year)
        self.trial_issue_m = tk.IntVar(value=today.month)
        self.trial_issue_d = tk.IntVar(value=today.day)

        tk.Label(inner_ti, text="年：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_ti, from_=2020, to=2099,
                   textvariable=self.trial_issue_y, width=6, font=FONT).pack(side="left")
        tk.Label(inner_ti, text="　月：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_ti, from_=1, to=12,
                   textvariable=self.trial_issue_m, width=4, font=FONT).pack(side="left")
        tk.Label(inner_ti, text="　日：", font=FONT, bg="#f7f6f2").pack(side="left")
        tk.Spinbox(inner_ti, from_=1, to=31,
                   textvariable=self.trial_issue_d, width=4, font=FONT).pack(side="left")
        tk.Label(inner_ti, text="　※ デフォルトは今日の日付",
                 font=FONT_SMALL, bg="#f7f6f2", fg="#888888").pack(side="left", padx=8)

        # ── 出力先表示 ──
        self.trial_out_label = tk.Label(
            body, text=f"出力先：{OUTPUT_DIR}",
            font=FONT_SMALL, bg="#f7f6f2", fg="#555555", anchor="w")
        self.trial_out_label.pack(fill="x", pady=(0, 8))

        # ── 生成ボタン ──
        tk.Button(
            body, text="体験利用請求書PDFを生成する",
            font=FONT_BOLD, bg="#2a5c45", fg="white",
            relief="flat", padx=20, pady=10, cursor="hand2",
            command=self._generate_trial
        ).pack(pady=8)

        self.trial_status_var = tk.StringVar()
        tk.Label(body, textvariable=self.trial_status_var,
                 font=FONT_SMALL, bg="#f7f6f2", fg="#2a5c45",
                 wraplength=560, justify="left").pack(pady=4)

    def _refresh_trial_residents(self):
        """体験利用中の入居者リストをDBから再取得してコンボボックスを更新する"""
        self._trial_residents = get_residents_for_trial()
        names = [r["name"] for r in self._trial_residents]
        self.trial_resident_cb["values"] = names
        if names:
            self.trial_resident_cb.current(0)

    def _generate_trial(self):
        """体験利用請求書PDFを生成する"""
        # 利用者確認
        name = self.trial_resident_var.get()
        if not name:
            messagebox.showwarning("入力エラー", "利用者を選択してください。")
            return
        resident = next(
            (r for r in self._trial_residents if r["name"] == name), None
        )
        if resident is None:
            messagebox.showwarning(
                "エラー", "利用者情報が見つかりません。\n「更新」ボタンを押して再試行してください。"
            )
            return

        # 日付確認
        try:
            start_date = date(
                self.trial_start_y.get(),
                self.trial_start_m.get(),
                self.trial_start_d.get()
            )
            end_date = date(
                self.trial_end_y.get(),
                self.trial_end_m.get(),
                self.trial_end_d.get()
            )
        except ValueError as e:
            messagebox.showwarning("入力エラー", f"日付が正しくありません。\n{e}")
            return

        nights = (end_date - start_date).days
        days   = nights + 1  # 退所日当日も含めた日数
        if nights <= 0:
            messagebox.showwarning(
                "入力エラー",
                "終了日は開始日より後の日付を指定してください。\n"
                "例）5月1日〜5月2日（1泊2日）→ 2日分請求"
            )
            return

        # 30泊超は念のため確認
        if nights > 30:
            if not messagebox.askyesno(
                "確認",
                f"{nights}泊{days}日の体験利用として請求書を作成します。よろしいですか？\n"
                "（体験利用は通常1回30日まで）"
            ):
                return

        meals = {
            "breakfast": self.trial_breakfast.get(),
            "lunch":     self.trial_lunch.get(),
            "dinner":    self.trial_dinner.get(),
        }

        # ファイル名：体験利用_氏名_開始日_終了日.pdf
        safe_name   = re.sub(r'[\\/:*?"<>|]', '', name)
        output_path = os.path.join(
            OUTPUT_DIR,
            f"体験利用_{safe_name}_{start_date.strftime('%Y%m%d')}"
            f"_{end_date.strftime('%Y%m%d')}.pdf"
        )

        try:
            trial_iss_date = date(
                self.trial_issue_y.get(),
                self.trial_issue_m.get(),
                self.trial_issue_d.get()
            )
        except ValueError:
            messagebox.showwarning("入力エラー", "請求書作成日が正しくありません。")
            return

        self.trial_status_var.set("生成中...")
        self.update()

        try:
            generate_trial_pdf(
                resident, start_date, end_date, meals,
                self.settings, output_path,
                housing_subsidy=self.trial_housing_subsidy.get(),
                issue_date=trial_iss_date,
            )
            self.trial_status_var.set(f"生成完了：{output_path}")
            if messagebox.askyesno("完了", "体験利用請求書を生成しました。\n\nPDFを開きますか？"):
                subprocess.Popen(["start", "", output_path], shell=True)
        except Exception as e:
            self.trial_status_var.set("")
            messagebox.showerror("エラー", str(e))

    # ── タブ4：設定 ────────────────────────────────────────────
    def _build_settings(self, parent):
        body = tk.Frame(parent, bg="#f7f6f2")
        body.pack(fill="both", expand=True, padx=20, pady=20)

        p      = self.settings["prices"]
        issuer = self.settings["issuer"]

        price_frame = tk.LabelFrame(body, text="食事・費用 単価（円）",
                                    bg="#f7f6f2", font=FONT)
        price_frame.pack(fill="x", pady=(0,12))

        self.price_vars = {}
        for key, label in [
            ("breakfast",   "朝食単価"),
            ("lunch",       "昼食単価"),
            ("dinner",      "夕食単価"),
            ("utility",     "光熱水費（宿泊1日あたり）"),
            ("daily",       "日用品費（宿泊1日あたり）"),
            ("trial_daily", "体験利用料（1日あたり）"),
        ]:
            row = tk.Frame(price_frame, bg="#f7f6f2")
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, font=FONT, bg="#f7f6f2",
                     width=24, anchor="w").pack(side="left")
            v = tk.IntVar(value=p.get(key, 0))
            self.price_vars[key] = v
            tk.Spinbox(row, from_=0, to=99999, textvariable=v,
                       width=8, font=FONT).pack(side="left")
            tk.Label(row, text="円", font=FONT, bg="#f7f6f2").pack(
                side="left", padx=4)

        issuer_frame = tk.LabelFrame(body, text="発行者情報",
                                     bg="#f7f6f2", font=FONT)
        issuer_frame.pack(fill="x", pady=(0,12))

        self.issuer_vars = {}
        for key, label in [
            ("name",  "施設名"),
            ("org",   "法人名"),
            ("rep",   "代表者"),
            ("addr",  "住所"),
            ("tel",   "電話番号"),
            ("email", "メール"),
            ("bank",  "振込先口座"),
        ]:
            row = tk.Frame(issuer_frame, bg="#f7f6f2")
            row.pack(fill="x", padx=12, pady=4)
            tk.Label(row, text=label, font=FONT, bg="#f7f6f2",
                     width=12, anchor="w").pack(side="left")
            v = tk.StringVar(value=issuer.get(key, ""))
            self.issuer_vars[key] = v
            tk.Entry(row, textvariable=v, font=FONT, width=40).pack(side="left")

        # 全銀（口座振替）設定
        zengin_data = self.settings.get("zengin", DEFAULT_SETTINGS["zengin"])
        zengin_frame = tk.LabelFrame(body, text="全銀（口座振替）設定",
                                     bg="#f7f6f2", font=FONT, fg="#1a4a7a")
        zengin_frame.pack(fill="x", pady=(0, 12))

        self.zengin_vars = {}
        for key, label, hint in [
            ("contractor_code",      "委託者コード（10桁）",     "リコーから発行される番号"),
            ("contractor_name_kana", "委託者名（半角カナ40文字）", "例）ｼｪｱﾎｰﾑｽﾐｶ"),
            ("bank_code",            "取引銀行番号（4桁）",       "委託者の回収口座"),
            ("bank_name_kana",       "取引銀行名（半角カナ）",    "例）ﾅﾅｻﾄｼﾝｷﾝ"),
            ("branch_code",          "取引支店番号（3桁）",       ""),
            ("branch_name_kana",     "取引支店名（半角カナ）",    ""),
            ("account_type",         "預金種目（1:普通 2:当座）", ""),
            ("account_number",       "口座番号（7桁）",           ""),
        ]:
            row = tk.Frame(zengin_frame, bg="#f7f6f2")
            row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, bg="#f7f6f2",
                     width=24, anchor="w").pack(side="left")
            v = tk.StringVar(value=str(zengin_data.get(key, "")))
            self.zengin_vars[key] = v
            tk.Entry(row, textvariable=v, font=FONT, width=24).pack(side="left")
            if hint:
                tk.Label(row, text=hint, font=FONT_SMALL,
                         bg="#f7f6f2", fg="#888888").pack(side="left", padx=6)

        # 引落日
        row_dd = tk.Frame(zengin_frame, bg="#f7f6f2")
        row_dd.pack(fill="x", padx=12, pady=3)
        tk.Label(row_dd, text="引落日（毎月何日）", font=FONT_SMALL, bg="#f7f6f2",
                 width=24, anchor="w").pack(side="left")
        v_dd = tk.IntVar(value=int(zengin_data.get("debit_day", 20)))
        self.zengin_vars["debit_day"] = v_dd
        tk.Spinbox(row_dd, from_=1, to=31, textvariable=v_dd,
                   width=5, font=FONT).pack(side="left")
        tk.Label(row_dd, text="日（例：20）", font=FONT_SMALL,
                 bg="#f7f6f2", fg="#888888").pack(side="left", padx=4)

        tk.Button(
            body, text="設定を保存",
            font=FONT_BOLD, bg="#2a5c45", fg="white",
            relief="flat", padx=16, pady=8,
            command=self._save_settings
        ).pack(pady=8)

    def _save_settings(self):
        self.settings["prices"] = {k: v.get() for k, v in self.price_vars.items()}
        self.settings["issuer"] = {k: v.get() for k, v in self.issuer_vars.items()}
        self.settings["zengin"] = {
            k: (v.get() if hasattr(v, "get") else v)
            for k, v in self.zengin_vars.items()
        }
        save_settings(self.settings)
        messagebox.showinfo("保存完了", "設定を保存しました。")


# =============================================================================
# コマンドライン
# =============================================================================
def run_cli(year, month):
    settings    = load_settings()
    output_path = os.path.join(OUTPUT_DIR, f"請求書_{year}年{month}月.pdf")
    print(f"生成開始：{year}年{month}月分")
    try:
        generate_pdf(year, month, settings, output_path)
        print(f"完了：{output_path}")
    except Exception as e:
        print(f"エラー：{e}", file=sys.stderr)
        sys.exit(1)


# =============================================================================
# エントリーポイント
# =============================================================================
if __name__ == "__main__":
    if len(sys.argv) == 3:
        try:
            y = int(sys.argv[1])
            m = int(sys.argv[2])
        except ValueError:
            print("使い方：python billing_app.py <年> <月>")
            sys.exit(1)
        run_cli(y, m)
    else:
        app = App()
        app.mainloop()
