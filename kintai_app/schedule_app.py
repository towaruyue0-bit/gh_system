#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
勤務表作成アプリ
グループホーム職員の月次勤務表を作成・集計するアプリです。

【機能】
- 職員の登録・管理
- シフトパターンの登録・管理
- 月次勤務表の入力（実際の出退勤時刻・食事・夜勤）
- 出勤日数・総労働時間・深夜時間・残業時間・夜勤回数・食事回数の集計
- 集計結果のCSV出力
"""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import json
import os
import csv
import sqlite3
from datetime import datetime, timedelta
from collections import defaultdict
import calendar

# ========================
# 定数定義
# ========================
APP_TITLE = "勤務表作成アプリ"

# データファイルの保存先（このスクリプトと同じフォルダ）
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
STAFF_FILE    = os.path.join(BASE_DIR, "staff.json")
SHIFTS_FILE   = os.path.join(BASE_DIR, "shifts.json")
RECORDS_FILE  = os.path.join(BASE_DIR, "records.json")
YOTEI_FILE    = os.path.join(BASE_DIR, "yotei.json")          # 月次予定メモ
SETTINGS_FILE = os.path.join(BASE_DIR, "app_settings.json")  # ウィンドウサイズなどの設定

# 個人情報・外部DB（GH_Dataフォルダで一元管理）
_GH_DATA_DIR     = r"C:\GH_Data\data"
VISIT_DB         = os.path.join(_GH_DATA_DIR, "visits.db")
RESIDENTS_DB     = os.path.join(_GH_DATA_DIR, "residents.db")
STAFF_MASTER_FILE = os.path.join(_GH_DATA_DIR, "staff_master.json")  # 職員の氏名・ふりがな

# フォント定義（日本語表示のためMS Gothicを使用）
FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)

# 深夜時間帯の定義（日本の労働基準法：22時〜翌5時）
LATE_NIGHT_START = 22   # 22時
LATE_NIGHT_END   = 5    # 翌5時

# 1日の所定労働時間（残業計算の基準。8時間超えた分が残業）
STANDARD_HOURS = 8.0

# 曜日の略称（0=月曜〜6=日曜）
WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]

# 締め期間の設定（16日始まり・翌月15日締め）
PERIOD_START_DAY = 16   # 期間の起算日

# 予定タブの列定義 (key, ヘッダー文字列, Entryのwidth, 最終列か)
# 最終列だけ expand=True にして残りの幅を埋める
YOTEI_COLS = [
    ("sumika", "すみか休み", 10, False),
    ("col1",   "予定①",     14, False),
    ("col2",   "予定②",     14, False),
    ("col3",   "メモ",       14, True),
]


def get_period_dates(year, month):
    """
    指定した年月を「起算月」とする期間（16日〜翌月15日）の
    全日付を (year, month, day) タプルのリストで返す。

    例: get_period_dates(2026, 4) →
        [(2026,4,16), (2026,4,17), ..., (2026,4,30),
         (2026,5,1),  (2026,5,2),  ..., (2026,5,15)]
    """
    dates = []
    # 前半: 起算月の16日〜月末
    days_in_month = calendar.monthrange(year, month)[1]
    for day in range(PERIOD_START_DAY, days_in_month + 1):
        dates.append((year, month, day))
    # 後半: 翌月1日〜15日
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1
    for day in range(1, PERIOD_START_DAY):
        dates.append((ny, nm, day))
    return dates


def get_period_label(year, month):
    """
    期間のラベル文字列を返す。
    例: get_period_label(2026, 4) → '2026年4月期（4/16〜5/15）'
    """
    if month == 12:
        nm = 1
    else:
        nm = month + 1
    return f"{year}年{month}月期（{month}/16〜{nm}/15）"


def current_period():
    """
    今日の日付から「現在の給与期」の (year, month) を返す。
    16日以降なら今月、15日以前なら先月が起算月になる。
    集計タブの「今月」ボタンで使用する。
    """
    now = datetime.now()
    if now.day >= PERIOD_START_DAY:
        return now.year, now.month
    else:
        if now.month == 1:
            return now.year - 1, 12
        else:
            return now.year, now.month - 1


def get_month_dates(year, month):
    """
    指定した年月のすべての日付を (year, month, day) タプルのリストで返す。
    勤務表タブの入力画面（カレンダー月単位）で使用する。

    例: get_month_dates(2026, 4) →
        [(2026,4,1), (2026,4,2), ..., (2026,4,30)]
    """
    days_in_month = calendar.monthrange(year, month)[1]
    return [(year, month, day) for day in range(1, days_in_month + 1)]


def get_month_label(year, month):
    """
    カレンダー月のラベル文字列を返す。
    例: get_month_label(2026, 4) → '2026年4月'
    """
    return f"{year}年{month}月"


def get_japan_holidays(year):
    """
    指定した年の日本の祝日・振替休日を (month, day) タプルの集合で返す。
    標準ライブラリのみで計算する。

    対応祝日:
      元日・成人の日・建国記念の日・天皇誕生日・春分の日・昭和の日・
      憲法記念日・みどりの日・こどもの日・海の日・山の日・敬老の日・
      秋分の日・スポーツの日・文化の日・勤労感謝の日、振替休日、国民の休日
    """
    from datetime import date

    def nth_monday(month, n):
        """month 月の第 n 月曜日の date を返す"""
        dt = date(year, month, 1)
        diff = (0 - dt.weekday()) % 7   # 最初の月曜までの日数
        return dt + timedelta(days=diff + 7 * (n - 1))

    # ── 固定祝日 ──
    fixed = [
        (1,  1),   # 元日
        (2, 11),   # 建国記念の日
        (2, 23),   # 天皇誕生日（2020年〜）
        (4, 29),   # 昭和の日
        (5,  3),   # 憲法記念日
        (5,  4),   # みどりの日
        (5,  5),   # こどもの日
        (8, 11),   # 山の日（2016年〜）
        (11, 3),   # 文化の日
        (11,23),   # 勤労感謝の日
    ]
    # 春分の日・秋分の日（1980〜2099年有効の近似式）
    syunbun = int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    shubun  = int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))
    fixed.append((3, syunbun))
    fixed.append((9, shubun))

    holidays = {date(year, m, d) for m, d in fixed}

    # ── ハッピーマンデー ──
    holidays.add(nth_monday(1,  2))   # 成人の日：1月第2月曜
    holidays.add(nth_monday(7,  3))   # 海の日：7月第3月曜
    holidays.add(nth_monday(9,  3))   # 敬老の日：9月第3月曜
    holidays.add(nth_monday(10, 2))   # スポーツの日：10月第2月曜

    # ── 振替休日：祝日が日曜なら翌月曜（連鎖あり）──
    for h in sorted(holidays.copy()):
        if h.weekday() == 6:   # 日曜
            furikae = h + timedelta(days=1)
            while furikae in holidays:
                furikae += timedelta(days=1)
            holidays.add(furikae)

    # ── 国民の休日：祝日に挟まれた平日 ──
    sorted_h = sorted(holidays)
    for i in range(len(sorted_h) - 1):
        between = sorted_h[i] + timedelta(days=1)
        if between not in holidays and between == sorted_h[i + 1] - timedelta(days=1):
            if between.weekday() != 6:   # 日曜は対象外
                holidays.add(between)

    # (month, day) のタプル集合にして返す
    return {(h.month, h.day) for h in holidays}


def current_month_view():
    """
    今日の日付から「現在の表示月」の (year, month) を返す。
    給与期間（16日始まり）に関係なく、単純に今月の年月を返す。
    勤務表タブの「今月」ボタンで使用する。
    """
    now = datetime.now()
    return now.year, now.month


# 食事提供時刻（この時刻が勤務時間内に入っていれば自動チェック）
MEAL_TIMES = {
    "meal_b": "06:30",   # 朝食
    "meal_l": "12:00",   # 昼食
    "meal_d": "18:30",   # 夕食
}

# 初回起動時に自動登録されるシフトパターン
DEFAULT_SHIFTS = [
    {
        "id": "day_a",
        "name": "日勤A",
        "abbr": "日A",
        "start": "09:00",
        "end": "18:00",
        "break_min": 60,
        "is_night": False,
        "color": "#DDEEFF"
    },
    {
        "id": "day_b",
        "name": "日勤B",
        "abbr": "日B",
        "start": "10:00",
        "end": "19:00",
        "break_min": 60,
        "is_night": False,
        "color": "#DDEEFF"
    },
    {
        "id": "early",
        "name": "早番",
        "abbr": "早",
        "start": "07:00",
        "end": "16:00",
        "break_min": 60,
        "is_night": False,
        "color": "#FFFACC"
    },
    {
        "id": "late",
        "name": "遅番",
        "abbr": "遅",
        "start": "12:00",
        "end": "21:00",
        "break_min": 60,
        "is_night": False,
        "color": "#CCF0FF"
    },
    {
        "id": "night",
        "name": "夜勤",
        "abbr": "夜",
        "start": "17:00",
        "end": "10:00",       # 翌日10時終了
        "break_min": 120,
        "break_start": "00:00",  # 休憩開始時刻（深夜時間の正確な計算に使用）
        "is_night": True,     # 日またぎフラグ
        "color": "#E8DAFF"
    },
    {
        "id": "day_off",
        "name": "公休",
        "abbr": "休",
        "start": "",
        "end": "",
        "break_min": 0,
        "is_night": False,
        "color": "#EEEEEE"
    },
    {
        "id": "paid_leave",
        "name": "有給",
        "abbr": "有",
        "start": "",
        "end": "",
        "break_min": 0,
        "is_night": False,
        "color": "#CCFFCC"
    },
    {
        "id": "absence",
        "name": "欠勤",
        "abbr": "欠",
        "start": "",
        "end": "",
        "break_min": 0,
        "is_night": False,
        "color": "#FFCCCC"
    },
]


# ========================
# 時間計算ユーティリティ
# ========================

def time_to_minutes(time_str):
    """
    時刻文字列（"HH:MM"形式）を0時からの分数に変換する。
    例: "09:30" → 570

    引数:
        time_str: "HH:MM"形式の時刻文字列。全角コロン（：）・全角数字も自動で正規化する。
    戻り値:
        分数（整数）。変換できない場合はNone
    """
    if not time_str:
        return None
    # 全角コロン・全角数字を半角に正規化する（IMEオンのまま入力された場合の対策）
    time_str = time_str.replace("：", ":").translate(
        str.maketrans("０１２３４５６７８９", "0123456789")
    )
    if ":" not in time_str:
        return None
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except ValueError:
        return None


def minutes_to_hhmm(minutes):
    """
    分数を "H:MM" 形式の文字列に変換する。
    例: 570 → "9:30"、90 → "1:30"

    引数:
        minutes: 分数（整数またはfloat）
    戻り値:
        "H:MM" 形式の文字列
    """
    if minutes is None or minutes < 0:
        return "0:00"
    minutes = int(minutes)
    h = minutes // 60
    m = minutes % 60
    return f"{h}:{m:02d}"


def calc_work_minutes(start_str, end_str, break_min, is_night):
    """
    実際の勤務時間（分）を計算する。
    夜勤など日をまたぐ場合は、終了時刻が翌日のため24時間分を加算して計算する。

    引数:
        start_str: 開始時刻 ("HH:MM")
        end_str:   終了時刻 ("HH:MM")
        break_min: 休憩時間（分）
        is_night:  夜勤（日またぎ）かどうか
    戻り値:
        勤務時間（分）。計算できない場合は0
    """
    if not start_str or not end_str:
        return 0

    start = time_to_minutes(start_str)
    end   = time_to_minutes(end_str)
    if start is None or end is None:
        return 0

    # 夜勤の場合：終了時刻が開始時刻より小さければ翌日分として24時間加算
    # 例: 17:00開始、10:00終了 → 10:00に1440を加えて1580分（翌10:00）として計算
    if is_night and end <= start:
        end += 24 * 60

    work_min = end - start - break_min
    return max(0, work_min)


def calc_late_night_minutes(start_str, end_str, break_min, is_night,
                            break_start_str=None):
    """
    深夜時間帯（22:00〜翌5:00）に該当する勤務時間（分）を計算する。

    休憩開始時刻（break_start_str）が指定されている場合:
        休憩時間帯（break_start〜break_start+break_min）と
        深夜時間帯の重複分を正確に差し引く。
    指定がない場合:
        休憩時間を総勤務時間の割合で按分して差し引く（旧来の方法）。

    引数:
        start_str:       開始時刻 ("HH:MM")
        end_str:         終了時刻 ("HH:MM")
        break_min:       休憩時間（分）
        is_night:        夜勤（日またぎ）かどうか
        break_start_str: 休憩開始時刻 ("HH:MM")。省略可。
    戻り値:
        深夜勤務時間（分）
    """
    if not start_str or not end_str:
        return 0

    start = time_to_minutes(start_str)
    end   = time_to_minutes(end_str)
    if start is None or end is None:
        return 0

    if is_night and end <= start:
        end += 24 * 60

    total_raw = end - start   # 休憩込みの総在籍時間
    if total_raw <= 0:
        return 0

    # 深夜時間帯の範囲（分単位）
    # 前半: 当日22:00〜24:00
    # 後半: 翌日0:00〜5:00（夜勤の場合のみ対象）
    night_ranges = [(LATE_NIGHT_START * 60, 24 * 60)]   # 1320〜1440分
    if is_night:
        # 日またぎ後の0:00〜5:00は、24時間加算した1440〜1740分として計算
        night_ranges.append((24 * 60, (24 + LATE_NIGHT_END) * 60))

    # 各深夜帯との重複時間を合計
    night_raw = 0
    for n_start, n_end in night_ranges:
        overlap = max(0, min(end, n_end) - max(start, n_start))
        night_raw += overlap

    if night_raw <= 0:
        return 0

    # ── 休憩の差し引き ──
    if break_start_str and break_min > 0:
        # 休憩開始時刻が指定されている場合：実際の休憩時間帯と深夜時間帯の重複を正確に計算する
        b_start = time_to_minutes(break_start_str)
        if b_start is not None:
            b_end = b_start + break_min
            # 夜勤で休憩が「日付をまたいだ後（翌日0時以降）」に来る場合は24時間加算する
            # 例: 勤務開始22:00（1320分）、休憩0:00（0分）→ 0 < 1320 なので翌日扱い (0+1440=1440分)
            if is_night and b_start < start:
                b_start += 24 * 60
                b_end   += 24 * 60
            # 各深夜帯と休憩時間帯の重複を合計する
            break_in_night = 0
            for n_start, n_end in night_ranges:
                overlap = max(0, min(b_end, n_end) - max(b_start, n_start))
                break_in_night += overlap
            night_net = max(0, night_raw - break_in_night)
        else:
            # 休憩開始時刻の解析に失敗した場合は按分にフォールバック
            ratio     = night_raw / total_raw
            night_net = max(0, night_raw - break_min * ratio)
    else:
        # 休憩開始時刻が未指定：按分で計算（従来の動作）
        ratio     = night_raw / total_raw
        night_net = max(0, night_raw - break_min * ratio)

    return int(night_net)


def auto_detect_meals(start_str, end_str, is_night):
    """
    勤務時間帯に食事提供時刻が含まれるかどうかを自動判定する。
    朝食06:30・昼食12:00・夕食18:30 の各時刻が start〜end の間に入っていればTrue。

    引数:
        start_str: 開始時刻 ("HH:MM")
        end_str:   終了時刻 ("HH:MM")
        is_night:  夜勤（日またぎ）かどうか
    戻り値:
        {"meal_b": bool, "meal_l": bool, "meal_d": bool} の辞書
    """
    result = {"meal_b": False, "meal_l": False, "meal_d": False}
    if not start_str or not end_str:
        return result

    start = time_to_minutes(start_str)
    end   = time_to_minutes(end_str)
    if start is None or end is None:
        return result

    # 夜勤（日またぎ）の場合は終了時刻を翌日扱いにする
    if is_night and end <= start:
        end += 24 * 60

    for key, meal_time_str in MEAL_TIMES.items():
        meal_min = time_to_minutes(meal_time_str)
        if meal_min is None:
            continue
        # 食事時刻が勤務時間内（開始以上・終了未満）なら支給対象
        if start <= meal_min < end:
            result[key] = True
        # 夜勤の場合：翌日の食事時刻（+24時間）も確認する
        elif is_night and start <= (meal_min + 24 * 60) < end:
            result[key] = True

    return result


def calc_overtime_minutes(work_minutes, standard_minutes=None):
    """
    残業時間（分）を計算する。
    所定労働時間（デフォルト8時間）を超えた分が残業となる。

    引数:
        work_minutes:     実勤務時間（分）
        standard_minutes: 所定労働時間（分）。Noneの場合はSTANDARD_HOURS×60を使用
    戻り値:
        残業時間（分）。残業なしなら0
    """
    if standard_minutes is None:
        standard_minutes = int(STANDARD_HOURS * 60)
    return max(0, work_minutes - standard_minutes)


# ========================
# データ管理クラス
# ========================

class DataManager:
    """
    アプリのデータ（職員・シフト・勤務記録）をJSONファイルで管理するクラス。
    初回起動時にデフォルトデータを自動作成する。
    """

    def __init__(self):
        # 初回起動時にファイルがなければ作成する
        self._ensure_files()

    def _ensure_files(self):
        """必要なファイルが存在しない場合に初期データを作成する"""
        if not os.path.exists(SHIFTS_FILE):
            self.save_shifts(DEFAULT_SHIFTS)
        if not os.path.exists(STAFF_FILE):
            self.save_staff([])
        if not os.path.exists(RECORDS_FILE):
            self.save_records({})
        if not os.path.exists(YOTEI_FILE):
            self.save_yotei({})

    # ── 職員データ ──

    def _load_staff_master(self):
        """
        職員の氏名・ふりがなをGH_Dataから読み込み、{id: {name, kana}} の辞書で返す。
        ファイルが読めない場合は空辞書を返す（アプリが落ちないようにする）。
        """
        try:
            with open(STAFF_MASTER_FILE, "r", encoding="utf-8") as f:
                master = json.load(f)
            return {m["id"]: {"name": m.get("name", ""), "kana": m.get("kana", "")} for m in master}
        except Exception:
            return {}

    def _save_staff_master(self, staff_list):
        """
        職員リストから氏名・ふりがなだけ取り出してGH_Dataに保存する。
        GH_Dataフォルダが存在しない場合も安全に処理する。
        """
        master = [{"id": s["id"], "name": s.get("name", ""), "kana": s.get("kana", "")}
                  for s in staff_list]
        os.makedirs(os.path.dirname(STAFF_MASTER_FILE), exist_ok=True)
        with open(STAFF_MASTER_FILE, "w", encoding="utf-8") as f:
            json.dump(master, f, ensure_ascii=False, indent=2)

    def load_staff(self):
        """
        職員データをファイルから読み込んで返す。
        シフト設定（staff.json）と氏名（GH_Data/staff_master.json）を
        idで突き合わせて結合した1件のオブジェクトとして返す。
        """
        try:
            with open(STAFF_FILE, "r", encoding="utf-8") as f:
                config_list = json.load(f)
        except Exception:
            return []
        # 氏名マスターを取得して設定データに合成する
        master_map = self._load_staff_master()
        for s in config_list:
            personal = master_map.get(s["id"], {"name": "", "kana": ""})
            s["name"] = personal["name"]
            s["kana"] = personal["kana"]
        return config_list

    def save_staff(self, staff_list):
        """
        職員データを保存する。
        氏名・ふりがなはGH_Data/staff_master.jsonへ、
        シフト設定などはkintai_app/staff.jsonへ分けて保存する。
        """
        # 個人情報をGH_Dataに保存
        self._save_staff_master(staff_list)
        # 設定データ（氏名・ふりがなを除いたもの）をkintai_appに保存
        config_list = [{k: v for k, v in s.items() if k not in ("name", "kana")}
                       for s in staff_list]
        with open(STAFF_FILE, "w", encoding="utf-8") as f:
            json.dump(config_list, f, ensure_ascii=False, indent=2)

    def load_active_staff(self, period_start_str=None):
        """
        在職中の職員を返す。
        period_start_str（"YYYY-MM-DD"形式）を渡すと、退職日がその日以降の
        職員も含める（退職した月の途中までのデータを表示するため）。
        period_start_str を省略した場合は退職していない職員のみ返す。
        """
        result = []
        for s in self.load_staff():
            if not s.get("retired", False):
                result.append(s)
            elif period_start_str:
                # 退職日が期間開始日以降なら、この期間はまだ在籍していたとみなす
                rd = s.get("retirement_date", "")
                if rd and rd >= period_start_str:
                    result.append(s)
        return result

    # ── シフトパターンデータ ──

    def load_shifts(self):
        """シフトパターンをファイルから読み込んで返す"""
        try:
            with open(SHIFTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return list(DEFAULT_SHIFTS)

    def save_shifts(self, shifts_list):
        """シフトパターンをファイルに保存する"""
        with open(SHIFTS_FILE, "w", encoding="utf-8") as f:
            json.dump(shifts_list, f, ensure_ascii=False, indent=2)

    def get_shift_by_id(self, shift_id):
        """シフトIDでシフトパターンを検索して返す。見つからなければNone"""
        for s in self.load_shifts():
            if s["id"] == shift_id:
                return s
        return None

    # ── 勤務記録データ ──

    def load_records(self):
        """全勤務記録をファイルから読み込んで返す"""
        try:
            with open(RECORDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_records(self, records_dict):
        """全勤務記録をファイルに保存する"""
        with open(RECORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(records_dict, f, ensure_ascii=False, indent=2)

    # ── 予定メモデータ ──

    def load_yotei(self):
        """
        予定メモをファイルから読み込んで返す。
        形式: {"年_月": {"年_月_日": "メモテキスト", ...}, ...}
        """
        try:
            with open(YOTEI_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_yotei(self, yotei_dict):
        """予定メモをファイルに保存する"""
        with open(YOTEI_FILE, "w", encoding="utf-8") as f:
            json.dump(yotei_dict, f, ensure_ascii=False, indent=2)

    def get_yotei_for_period(self, year, month):
        """
        指定した年月の期間（16日〜翌月15日）の予定メモ辞書を返す（後方互換用）。
        内部的には get_yotei_for_month と同じ実装。
        """
        return self.get_yotei_for_month(year, month)

    def save_yotei_for_period(self, year, month, period_notes):
        """
        指定した年月の予定メモを保存する（後方互換用）。
        内部的には save_yotei_for_month と同じ実装。
        """
        self.save_yotei_for_month(year, month, period_notes)

    def get_yotei_for_month(self, year, month):
        """
        指定した年月（カレンダー月）の予定メモ辞書を返す。
        形式: {"年_月_日": "メモ", ...}
        存在しないキーは空文字。
        """
        all_data  = self.load_yotei()
        month_key = f"{year}_{month:02d}"
        return all_data.get(month_key, {})

    def save_yotei_for_month(self, year, month, month_notes):
        """
        指定した年月（カレンダー月）の予定メモを保存する。
        month_notes: {"年_月_日": "メモ", ...}
        """
        all_data  = self.load_yotei()
        month_key = f"{year}_{month:02d}"
        all_data[month_key] = month_notes
        self.save_yotei(all_data)

    def _make_key(self, staff_id, year, month, day):
        """
        勤務記録の辞書キーを生成する。
        形式: "職員ID_年_月_日"（例: "S001_2026_04_01"）
        """
        return f"{staff_id}_{year}_{month:02d}_{day:02d}"

    def get_record(self, staff_id, year, month, day):
        """
        指定した職員・日付の勤務記録を取得する。
        記録がない場合はNoneを返す。
        """
        records = self.load_records()
        key = self._make_key(staff_id, year, month, day)
        return records.get(key, None)

    def set_record(self, staff_id, year, month, day, data):
        """
        指定した職員・日付の勤務記録を保存する。
        data=Noneを渡すと記録を削除する。
        """
        records = self.load_records()
        key = self._make_key(staff_id, year, month, day)
        if data is None:
            records.pop(key, None)
        else:
            records[key] = data
        self.save_records(records)

    def get_records_for_day(self, staff_id, year, month, day):
        """
        管理者の複数シフト対応：その日の全スロットの記録をリストで返す。
        スロット0は既存キー形式、スロット1・2は末尾に _s1 _s2 を付加したキー。
        """
        records  = self.load_records()
        base_key = self._make_key(staff_id, year, month, day)
        result   = []
        if base_key in records:
            result.append(records[base_key])
        for slot in range(1, 3):
            key = f"{base_key}_s{slot}"
            if key in records:
                result.append(records[key])
        return result

    def set_record_slot(self, staff_id, year, month, day, slot, data):
        """
        スロット番号を指定して記録を保存/削除する（管理者の複数シフト用）。
        slot=0 は既存キー形式（後方互換）、slot=1,2 は _s1 _s2 サフィックス。
        """
        records  = self.load_records()
        base_key = self._make_key(staff_id, year, month, day)
        key      = base_key if slot == 0 else f"{base_key}_s{slot}"
        if data is None:
            records.pop(key, None)
        else:
            records[key] = data
        self.save_records(records)


# ========================
# メインウィンドウ
# ========================

class ScheduleApp(tk.Tk):
    """勤務表作成アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.configure(bg="#F5F6FA")

        # データマネージャーを初期化（ファイルがなければ自動作成）
        self.dm = DataManager()

        # 現在表示している月（初期値は今月。勤務表タブは暦月で表示する）
        py, pm = current_month_view()
        self.current_year  = tk.IntVar(value=py)
        self.current_month = tk.IntVar(value=pm)

        # 前回終了時のウィンドウサイズ・位置を復元する（なければデフォルト値を使用）
        self._restore_geometry()

        # ウィンドウを閉じるときにサイズ・位置を保存する
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()

    def _restore_geometry(self):
        """前回終了時のウィンドウサイズ・位置をファイルから読み込んで適用する"""
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                geom = settings.get("geometry", "")
                if geom:
                    self.geometry(geom)
                    return
        except Exception:
            pass
        # 設定ファイルがない、または読み込み失敗時はデフォルトサイズで起動
        self.geometry("1150x720")

    def _on_close(self):
        """ウィンドウを閉じるときに現在のサイズ・位置を保存する"""
        try:
            settings = {}
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            # geometry() は "幅x高さ+X位置+Y位置" の文字列を返す
            settings["geometry"] = self.geometry()
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.destroy()

    def _build_ui(self):
        """画面全体のUIを構築する"""
        # ── タイトルバー ──
        title_bar = tk.Frame(self, bg="#4A6FA5", pady=8)
        title_bar.pack(fill="x")
        tk.Label(
            title_bar,
            text=f"  {APP_TITLE}",
            font=FONT_TITLE,
            bg="#4A6FA5",
            fg="white"
        ).pack(side="left")

        # ── タブ（ノートブック）──
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=FONT, padding=(10, 4))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # 各タブのクラスをインスタンス化してノートブックに追加
        self.tab_schedule  = ScheduleTab(self.notebook, self)
        self.tab_summary   = SummaryTab(self.notebook, self)
        self.tab_timecard  = TimecardTab(self.notebook, self)
        self.tab_yotei     = YoteiTab(self.notebook, self)
        self.tab_shifts    = ShiftSettingsTab(self.notebook, self)
        self.tab_staff     = StaffSettingsTab(self.notebook, self)

        self.notebook.add(self.tab_schedule,  text="  勤務表  ")
        self.notebook.add(self.tab_summary,   text="  集計  ")
        self.notebook.add(self.tab_timecard,  text="  タイムカード照合  ")
        self.notebook.add(self.tab_yotei,     text="  予定  ")
        self.notebook.add(self.tab_shifts,    text="  シフト設定  ")
        self.notebook.add(self.tab_staff,     text="  職員設定  ")

        # タブを切り替えたときにデータを再読み込みする
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, event):
        """タブ切り替え時に各タブの表示を最新化する"""
        tab_text = self.notebook.tab(self.notebook.select(), "text").strip()
        if "勤務表" in tab_text:
            self.tab_schedule.refresh()
        elif "集計" in tab_text:
            self.tab_summary.refresh()
        elif "タイムカード" in tab_text:
            self.tab_timecard.refresh()
        elif "予定" in tab_text:
            self.tab_yotei.refresh()
        elif "シフト" in tab_text:
            self.tab_shifts.refresh()
        elif "職員" in tab_text:
            self.tab_staff.refresh()


# ========================
# 勤務表タブ
# ========================

class ScheduleTab(tk.Frame):
    """月次勤務表を表示・編集するタブ"""

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F5F6FA")
        self.app = app
        self.dm  = app.dm
        self._build()
        self.refresh()

    def _build(self):
        """ウィジェットを構築する"""

        # ── 上部コントロールバー（月移動） ──
        ctrl = tk.Frame(self, bg="#F5F6FA", pady=6)
        ctrl.pack(fill="x", padx=10)

        tk.Button(
            ctrl, text="◀ 前月", font=FONT,
            command=self._prev_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        self.lbl_yearmonth = tk.Label(
            ctrl, text="", font=FONT_BOLD, bg="#F5F6FA", width=14
        )
        self.lbl_yearmonth.pack(side="left", padx=8)

        tk.Button(
            ctrl, text="翌月 ▶", font=FONT,
            command=self._next_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        tk.Button(
            ctrl, text="今月", font=FONT,
            command=self._goto_today,
            relief="flat", cursor="hand2", padx=10, pady=3
        ).pack(side="left", padx=12)

        tk.Button(
            ctrl, text="パターン一括入力", font=FONT,
            command=self._apply_pattern_all,
            relief="flat", cursor="hand2",
            bg="#3A9A50", fg="white", padx=10, pady=3
        ).pack(side="left", padx=(12, 2))

        tk.Button(
            ctrl, text="印刷", font=FONT,
            command=self._print_schedule,
            relief="flat", cursor="hand2",
            bg="#555555", fg="white", padx=10, pady=3
        ).pack(side="left", padx=2)

        tk.Button(
            ctrl, text="穴埋め自動入力", font=FONT,
            command=self._fill_manager_gaps,
            relief="flat", cursor="hand2",
            bg="#E8A020", fg="white", padx=10, pady=3
        ).pack(side="left", padx=2)

        tk.Label(
            ctrl,
            text="※ セルをクリックしてシフトを入力します",
            font=FONT_SMALL, bg="#F5F6FA", fg="#666666"
        ).pack(side="left")

        # ── グリッドエリア（スクロール対応） ──
        grid_outer = tk.Frame(self, bg="#F5F6FA")
        grid_outer.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        v_scroll = ttk.Scrollbar(grid_outer, orient="vertical")
        h_scroll = ttk.Scrollbar(grid_outer, orient="horizontal")
        v_scroll.pack(side="right",  fill="y")
        h_scroll.pack(side="bottom", fill="x")

        # Canvasの中にグリッドを配置することでスクロールを実現する
        self.canvas = tk.Canvas(
            grid_outer, bg="white",
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        v_scroll.config(command=self.canvas.yview)
        h_scroll.config(command=self.canvas.xview)

        # グリッドを格納するフレーム
        self.grid_frame = tk.Frame(self.canvas, bg="white")
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        # フレームサイズが変わったらスクロール範囲を更新する
        self.grid_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        # マウスホイールで縦スクロールできるようにする
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        """マウスホイールで縦スクロールする"""
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def _prev_month(self):
        """前の月を表示する"""
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 1:
            self.app.current_year.set(y - 1)
            self.app.current_month.set(12)
        else:
            self.app.current_month.set(m - 1)
        self.refresh()

    def _next_month(self):
        """次の月を表示する"""
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 12:
            self.app.current_year.set(y + 1)
            self.app.current_month.set(1)
        else:
            self.app.current_month.set(m + 1)
        self.refresh()

    def _goto_today(self):
        """今月（今日が属するカレンダー月）を表示する"""
        py, pm = current_month_view()
        self.app.current_year.set(py)
        self.app.current_month.set(pm)
        self.refresh()

    def refresh(self):
        """勤務表グリッドを最新データで再描画する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()

        # 月ラベルを更新する（例: 2026年4月）
        self.lbl_yearmonth.config(text=get_month_label(year, month))

        # グリッドを一旦すべて削除
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        # カレンダー月の1日を期間開始とする（退職日が1日以降なら表示対象）
        period_start = f"{year}-{month:02d}-01"
        staff_list   = self.dm.load_active_staff(period_start)
        shifts       = self.dm.load_shifts()
        shift_map    = {s["id"]: s for s in shifts}
        period_dates = get_month_dates(year, month)   # [(y,m,d), ...] 暦月の日付一覧
        holidays     = get_japan_holidays(year)        # {(month, day), ...}

        today        = datetime.now()
        today_tuple  = (today.year, today.month, today.day)

        # ── ヘッダー行：職員名列 + 各日付列 ──
        tk.Label(
            self.grid_frame,
            text="職員名",
            font=FONT_SMALL, bg="#4A6FA5", fg="white",
            width=10, relief="groove", pady=5
        ).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        for col_idx, (y, m, d) in enumerate(period_dates, start=1):
            weekday    = datetime(y, m, d).weekday()
            is_holiday = (m, d) in holidays
            wname      = WEEKDAY_JP[weekday]
            day_text   = f"{d}\n{wname}"

            # 色の決定（今日 > 土 > 日・祝 > 通常）
            if (y, m, d) == today_tuple:
                hdr_bg, hdr_fg = "#FF8C00", "white"
            elif weekday == 5:
                hdr_bg, hdr_fg = "#4477BB", "white"
            elif weekday == 6 or is_holiday:
                hdr_bg, hdr_fg = "#BB4444", "white"
            else:
                hdr_bg, hdr_fg = "#4A6FA5", "white"

            tk.Label(
                self.grid_frame,
                text=day_text,
                font=FONT_SMALL, bg=hdr_bg, fg=hdr_fg,
                width=4, relief="groove", pady=1
            ).grid(row=0, column=col_idx, sticky="nsew", padx=1, pady=1)

        # 職員が登録されていない場合のメッセージ
        if not staff_list:
            tk.Label(
                self.grid_frame,
                text="まだ職員が登録されていません。\n「職員設定」タブから職員を追加してください。",
                font=FONT, bg="white", justify="center"
            ).grid(row=1, column=0, columnspan=len(period_dates) + 2, pady=30)
            return

        # ── 職員ごとの行 ──
        # 管理者は3行（スロットごと）、一般職員は1行。current_row でグリッド行番号を管理する
        current_row = 1
        non_mgr_idx = 0   # 一般職員の交互背景色用カウンター

        # 管理者スロット行の名前列背景色（3スロット分を少しずつ変化させる）
        MGR_NAME_BG  = ["#C8DAFA", "#D4E4FF", "#DFF0FF"]
        # 管理者スロット行に表示する番号ラベル
        MGR_SLOT_LBL = ["①", "②", "③"]

        for staff in staff_list:
            if staff.get("is_manager"):
                # ── 管理者：スロットごとに3行に分けて表示する ──
                for slot_idx in range(3):
                    # 1行目はフルネーム＋★、2・3行目はスロット番号のみ
                    if slot_idx == 0:
                        name_text = f"★{staff['name']}"
                    else:
                        name_text = f"　{MGR_SLOT_LBL[slot_idx]}"
                    name_bg = MGR_NAME_BG[slot_idx]

                    name_lbl = tk.Label(
                        self.grid_frame,
                        text=name_text,
                        font=FONT_SMALL, bg=name_bg,
                        width=12, relief="groove", anchor="w", padx=4
                    )
                    name_lbl.grid(row=current_row, column=0, sticky="nsew", padx=1, pady=1, ipady=5)
                    # 右クリックで記録クリアメニューを表示（1行目のみ）
                    if slot_idx == 0:
                        name_lbl.bind(
                            "<Button-3>",
                            lambda e, s=staff: self._show_clear_menu(e, s)
                        )

                    # 日付ごとのセル
                    for col_idx, (y, m, d) in enumerate(period_dates, start=1):
                        weekday    = datetime(y, m, d).weekday()
                        is_holiday = (m, d) in holidays
                        row_bg     = name_bg   # スロット行の背景色に合わせる

                        # このスロットの記録を取得する
                        day_records = self.dm.get_records_for_day(staff["id"], y, m, d)
                        if slot_idx < len(day_records):
                            record = day_records[slot_idx]
                            shift  = shift_map.get(record.get("shift_id", ""))
                            if shift:
                                cell_text = shift.get("abbr", "?")
                                cell_bg   = shift.get("color", row_bg)
                            else:
                                cell_text = "?"
                                cell_bg   = row_bg
                        else:
                            cell_text = ""
                            cell_bg   = row_bg

                        if not cell_text:
                            if weekday == 5:
                                cell_bg = "#EEF3FF"
                            elif weekday == 6 or is_holiday:
                                cell_bg = "#FFEEEE"
                            else:
                                cell_bg = row_bg

                        if (y, m, d) == today_tuple and not cell_text:
                            cell_bg = "#FFF5E0"

                        btn = tk.Button(
                            self.grid_frame,
                            text=cell_text,
                            font=FONT_SMALL, bg=cell_bg,
                            relief="groove", width=4,
                            cursor="hand2",
                            command=lambda s=staff, dt=(y, m, d): self._on_cell_click(s, dt)
                        )
                        btn.grid(row=current_row, column=col_idx, sticky="nsew", padx=1, pady=1)

                    current_row += 1

            else:
                # ── 一般職員：1行で表示する ──
                non_mgr_idx += 1
                row_bg = "#FFFFFF" if non_mgr_idx % 2 == 0 else "#F0F4FA"

                name_lbl = tk.Label(
                    self.grid_frame,
                    text=staff["name"],
                    font=FONT_SMALL, bg="#E8EEF8",
                    width=12, relief="groove", anchor="w", padx=4
                )
                name_lbl.grid(row=current_row, column=0, sticky="nsew", padx=1, pady=1, ipady=5)
                # 右クリックで記録クリアメニューを表示
                name_lbl.bind(
                    "<Button-3>",
                    lambda e, s=staff: self._show_clear_menu(e, s)
                )

                for col_idx, (y, m, d) in enumerate(period_dates, start=1):
                    weekday    = datetime(y, m, d).weekday()
                    is_holiday = (m, d) in holidays

                    record = self.dm.get_record(staff["id"], y, m, d)
                    if record and record.get("shift_id"):
                        shift = shift_map.get(record["shift_id"])
                        if shift:
                            cell_text = shift["abbr"]
                            cell_bg   = shift.get("color", row_bg)
                        else:
                            cell_text = "?"
                            cell_bg   = row_bg
                    else:
                        cell_text = ""

                    if not cell_text:
                        if weekday == 5:
                            cell_bg = "#EEF3FF"
                        elif weekday == 6 or is_holiday:
                            cell_bg = "#FFEEEE"
                        else:
                            cell_bg = row_bg

                    # 今日のセルを目立たせる
                    if (y, m, d) == today_tuple and not cell_text:
                        cell_bg = "#FFF5E0"

                    btn = tk.Button(
                        self.grid_frame,
                        text=cell_text,
                        font=FONT_SMALL, bg=cell_bg,
                        relief="groove", width=4,
                        cursor="hand2",
                        command=lambda s=staff, dt=(y, m, d): self._on_cell_click(s, dt)
                    )
                    btn.grid(row=current_row, column=col_idx, sticky="nsew", padx=1, pady=1)

                current_row += 1

        # ── 予定行：グリッド最下部に1行追加 ──
        yotei_notes = self.dm.get_yotei_for_month(year, month)

        tk.Label(
            self.grid_frame,
            text="予　定",
            font=FONT_SMALL, bg="#D0E8D0",
            width=12, relief="groove", anchor="w", padx=4
        ).grid(row=current_row, column=0, sticky="nsew", padx=1, pady=1, ipady=5)

        for col_idx, (y, m, d) in enumerate(period_dates, start=1):
            weekday = datetime(y, m, d).weekday()
            key     = f"{y}_{m:02d}_{d:02d}"
            raw     = yotei_notes.get(key, "")
            # 4列dict形式：空でない列を結合して1つの文字列にする
            if isinstance(raw, dict):
                note = " / ".join(v for v in raw.values() if v)
            else:
                note = raw

            # セルの背景色
            if note:
                cell_bg = "#D8F0D8"   # メモありは薄緑
            elif weekday == 5:
                cell_bg = "#EEF3FF"
            elif weekday == 6:
                cell_bg = "#FFEEEE"
            else:
                cell_bg = "#F5FBF5"

            # 表示テキスト（長い場合は省略）
            disp = note[:4] if len(note) > 4 else note

            btn = tk.Button(
                self.grid_frame,
                text=disp,
                font=FONT_SMALL, bg=cell_bg,
                relief="groove", width=4,
                cursor="hand2",
                command=lambda cy=y, cm=m, cd=d: self._on_yotei_click(cy, cm, cd)
            )
            btn.grid(row=current_row, column=col_idx, sticky="nsew", padx=1, pady=1)

    def _on_yotei_click(self, y, m, d):
        """
        予定セルをクリックしたときに呼ばれる。
        ダイアログを開いてメモを編集できるようにする。
        """
        year_period  = self.app.current_year.get()
        month_period = self.app.current_month.get()
        yotei_notes  = self.dm.get_yotei_for_month(year_period, month_period)
        key          = f"{y}_{m:02d}_{d:02d}"
        raw          = yotei_notes.get(key, {})
        # 旧形式（文字列）は dict に変換する
        if isinstance(raw, str):
            raw = {"sumika": raw} if raw == "すみか休み" else {"col1": raw}

        wd_jp    = WEEKDAY_JP[datetime(y, m, d).weekday()]
        date_str = f"{m}/{d}（{wd_jp}）"

        # ダイアログを作成する（4列分の入力欄を表示）
        dlg = tk.Toplevel(self)
        dlg.title(f"予定メモ — {date_str}")
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text=f"  {date_str} の予定・メモ", font=FONT_BOLD,
                 bg="#D0E8D0", pady=6).pack(fill="x")

        # 4列分の入力欄（YOTEI_COLS に従う）
        col_entries = {}
        for col_id, col_label, col_width, _ in YOTEI_COLS:
            frm = tk.Frame(dlg)
            frm.pack(fill="x", padx=12, pady=2)
            bg_lbl = "#C05000" if col_id == "sumika" else "#4A6FA5"
            tk.Label(frm, text=col_label, font=FONT_SMALL,
                     bg=bg_lbl, fg="white", width=10, anchor="center").pack(side="left", padx=(0, 4))
            ent = tk.Entry(frm, font=FONT, relief="solid", bd=1)
            ent.pack(side="left", fill="x", expand=True, ipady=2)
            ent.insert(0, raw.get(col_id, ""))
            col_entries[col_id] = ent

        col_entries[list(col_entries.keys())[0]].focus_set()

        def _save():
            new_data = {}
            for col_id, ent in col_entries.items():
                text = ent.get().strip()
                if text:
                    new_data[col_id] = text
            if new_data:
                yotei_notes[key] = new_data
            elif key in yotei_notes:
                del yotei_notes[key]
            self.dm.save_yotei_for_month(year_period, month_period, yotei_notes)
            dlg.destroy()
            self.refresh()   # グリッドを再描画して反映させる

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text="保存", font=FONT,
                  bg="#3A9A50", fg="white", relief="flat", cursor="hand2",
                  padx=16, command=_save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2", padx=10,
                  command=dlg.destroy).pack(side="left", padx=6)

        dlg.bind("<Escape>", lambda e: dlg.destroy())

    def _print_schedule(self):
        """
        勤務表をHTMLファイルに書き出してブラウザで開く。
        ブラウザの印刷機能（Ctrl+P）でA4横向きに印刷できる。
        外部ライブラリ不要（標準ライブラリのみ使用）。
        """
        import webbrowser
        import tempfile
        import html as html_lib

        year         = self.app.current_year.get()
        month        = self.app.current_month.get()
        staff_list   = self.dm.load_active_staff(f"{year}-{month:02d}-01")
        shifts       = self.dm.load_shifts()
        shift_map    = {s["id"]: s for s in shifts}
        period_dates = get_month_dates(year, month)
        holidays     = get_japan_holidays(year)

        # ── ヘッダー行を生成 ──
        header_cells = '<th class="name-col">職員名</th>'
        for y, m, d in period_dates:
            wd         = datetime(y, m, d).weekday()
            is_holiday = (m, d) in holidays
            if wd == 5:
                cls = ' class="sat"'
            elif wd == 6 or is_holiday:
                cls = ' class="sun"'
            else:
                cls = ""
            header_cells += f'<th{cls}>{d}<br>{WEEKDAY_JP[wd]}</th>'

        # ── データ行を生成 ──
        MGR_SLOT_LBL = ["①", "②", "③"]
        body_rows    = ""

        for staff in staff_list:
            if staff.get("is_manager"):
                for slot_idx in range(3):
                    if slot_idx == 0:
                        name_text = f"★{staff['name']}"
                        name_cls  = "name-col mgr mgr1"
                    else:
                        name_text = f"　{MGR_SLOT_LBL[slot_idx]}"
                        name_cls  = "name-col mgr"
                    row = f'<td class="{name_cls}">{html_lib.escape(name_text)}</td>'

                    for y, m, d in period_dates:
                        wd         = datetime(y, m, d).weekday()
                        is_holiday = (m, d) in holidays
                        day_records = self.dm.get_records_for_day(staff["id"], y, m, d)
                        if slot_idx < len(day_records):
                            rec   = day_records[slot_idx]
                            shift = shift_map.get(rec.get("shift_id", ""))
                            if shift:
                                abbr  = html_lib.escape(shift.get("abbr", "?"))
                                color = shift.get("color", "#FFFFFF")
                                row  += f'<td style="background:{color}">{abbr}</td>'
                            else:
                                row  += "<td>?</td>"
                        else:
                            if wd == 5:
                                extra = ' class="sat"'
                            elif wd == 6 or is_holiday:
                                extra = ' class="sun"'
                            else:
                                extra = ""
                            row  += f"<td{extra}></td>"

                    body_rows += f'<tr class="mgr-row">{row}</tr>\n'
            else:
                row = f'<td class="name-col">{html_lib.escape(staff["name"])}</td>'
                for y, m, d in period_dates:
                    wd         = datetime(y, m, d).weekday()
                    is_holiday = (m, d) in holidays
                    record = self.dm.get_record(staff["id"], y, m, d)
                    if record and record.get("shift_id"):
                        shift = shift_map.get(record["shift_id"])
                        if shift:
                            abbr  = html_lib.escape(shift.get("abbr", "?"))
                            color = shift.get("color", "#FFFFFF")
                            row  += f'<td style="background:{color}">{abbr}</td>'
                        else:
                            row  += "<td>?</td>"
                    else:
                        if wd == 5:
                            extra = ' class="sat"'
                        elif wd == 6 or is_holiday:
                            extra = ' class="sun"'
                        else:
                            extra = ""
                        row  += f"<td{extra}></td>"
                body_rows += f"<tr>{row}</tr>\n"

        # ── 予定行（縦書き）を最下行に追加 ──
        yotei_notes = self.dm.get_yotei_for_month(year, month)
        yotei_row = '<td class="name-col yotei-label-cell">予　定</td>'
        for y, m, d in period_dates:
            key = f"{y}_{m:02d}_{d:02d}"
            raw = yotei_notes.get(key, "")
            # 4列dict形式：空でない列を改行でつなげて表示する
            if isinstance(raw, dict):
                parts = [v for v in raw.values() if v]
                text  = html_lib.escape(" / ".join(parts))
            else:
                text  = html_lib.escape(raw)
            yotei_row += f'<td class="yotei-text">{text}</td>'
        body_rows += f'<tr class="yotei-row">{yotei_row}</tr>\n'

        period_label = get_month_label(year, month)

        html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>勤務表 {html_lib.escape(period_label)}</title>
<style>
  @page {{ size: A4 landscape; margin: 6mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "MS Gothic", "Meiryo UI", monospace;
    font-size: 7pt;
    color: #111;
  }}
  h1 {{
    font-size: 10pt;
    text-align: center;
    margin-bottom: 3mm;
    font-weight: bold;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  th, td {{
    border: 1px solid #888;
    text-align: center;
    vertical-align: middle;
    padding: 1px 0;
    overflow: hidden;
    white-space: nowrap;
    font-size: 6.5pt;
    height: 14pt;
  }}
  tbody td {{
    height: 25pt;
  }}
  /* 職員名列は少し広めに固定 */
  th.name-col, td.name-col {{
    width: 22mm;
    text-align: left;
    padding-left: 2px;
    font-size: 6.5pt;
  }}
  thead th {{
    background: #4A6FA5;
    color: white;
    font-size: 6pt;
    height: 18pt;
  }}
  thead th.name-col {{
    background: #4A6FA5;
  }}
  /* 土曜・日曜（ヘッダー） */
  .sat {{ background: #dde8ff !important; color: #224; }}
  .sun {{ background: #ffdede !important; color: #422; }}
  /* 管理者行：空きセルは公休と同系のグレーにして、入力済みセルを目立たせる */
  tr.mgr-row td {{ background: #e8e8e8; }}
  td.mgr {{ background: #c8daff !important; font-weight: bold; }}
  td.mgr1 {{ border-top: 2px solid #4A6FA5; }}
  /* 印刷時にカラーを保持する */
  @media print {{
    body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
  /* 予定行（縦書き） */
  tr.yotei-row td {{
    height: 40mm;
    vertical-align: top;
    background: #f8f8f8;
    white-space: normal;
    word-break: break-all;
    font-size: 6pt;
    padding: 2px;
  }}
  tr.yotei-row td.yotei-label-cell {{
    background: #e8eef8;
    font-weight: bold;
    font-size: 7pt;
    text-align: center;
    vertical-align: middle;
    white-space: nowrap;
  }}
  tr.yotei-row td.yotei-text {{
    writing-mode: vertical-rl;
    text-orientation: mixed;
    overflow: hidden;
  }}
  /* 画面表示用のヒント */
  .hint {{
    font-size: 8pt;
    color: #666;
    text-align: right;
    margin-top: 2mm;
  }}
</style>
</head>
<body>
<h1>勤務表　{html_lib.escape(period_label)}</h1>
<table>
  <thead><tr>{header_cells}</tr></thead>
  <tbody>
{body_rows}
  </tbody>
</table>
<p class="hint">印刷するには Ctrl+P → 用紙サイズ: A4 / 向き: 横 を選択してください</p>
</body>
</html>"""

        # 一時ファイルに書き出してブラウザで開く
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False,
            encoding="utf-8", prefix="kintai_"
        ) as f:
            f.write(html_content)
            tmp_path = f.name

        webbrowser.open(f"file:///{tmp_path.replace(os.sep, '/')}")

    def _apply_pattern_staff(self, staff, show_result=False):
        """
        1人分の通常勤務パターンを現在の期間に適用する。
        すでに記録が入っている日はスキップする（上書きしない）。

        引数:
            staff:       職員辞書
            show_result: True のときは結果をメッセージボックスで表示する
        戻り値:
            入力した件数（int）
        """
        pattern = staff.get("weekly_pattern", {})
        # パターンが一切設定されていない場合
        if not any(v for v in pattern.values()):
            if show_result:
                messagebox.showinfo(
                    "パターン未設定",
                    f"「{staff['name']}」には通常勤務パターンが設定されていません。\n"
                    "「職員設定」タブで曜日ごとのシフトを設定してください。"
                )
            return 0

        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        count = 0

        for y, m, d in get_month_dates(year, month):
            weekday  = datetime(y, m, d).weekday()   # 0=月〜6=日
            shift_id = pattern.get(str(weekday), "")
            if not shift_id:
                continue   # この曜日はパターンなし

            # 既に記録がある日はスキップ（上書きしない）
            existing = self.dm.get_record(staff["id"], y, m, d)
            if existing:
                continue

            shift = self.dm.get_shift_by_id(shift_id)
            if not shift:
                continue

            meals = auto_detect_meals(
                shift.get("start", ""), shift.get("end", ""),
                shift.get("is_night", False)
            )
            data = {
                "shift_id":     shift_id,
                "actual_start": shift.get("start", ""),
                "actual_end":   shift.get("end",   ""),
                "actual_break": shift.get("break_min", 0),
                "break_start":  shift.get("break_start", ""),
                "is_night":     shift.get("is_night", False),
                "meal_b":       meals["meal_b"],
                "meal_l":       meals["meal_l"],
                "meal_d":       meals["meal_d"],
                "memo":         "パターン自動入力",
            }
            # スロット0に書き込む（管理者も非管理者も同じ）
            self.dm.set_record_slot(staff["id"], y, m, d, 0, data)
            count += 1

        if show_result:
            if count > 0:
                messagebox.showinfo(
                    "パターン入力完了",
                    f"「{staff['name']}」に {count} 件入力しました。\n"
                    "（入力済みの日はスキップしました）"
                )
                self.refresh()
            else:
                messagebox.showinfo(
                    "パターン入力完了",
                    f"「{staff['name']}」は入力できる日がありませんでした。\n"
                    "（すでに全日入力済み、またはパターン対象曜日がない）"
                )
        return count

    def _apply_pattern_all(self):
        """全職員の通常勤務パターンを現在の期間に一括適用する"""
        year     = self.app.current_year.get()
        month    = self.app.current_month.get()
        all_staff    = self.dm.load_active_staff(f"{year}-{month:02d}-01")
        total_count  = 0
        applied_list = []

        for staff in all_staff:
            cnt = self._apply_pattern_staff(staff, show_result=False)
            if cnt > 0:
                total_count += cnt
                applied_list.append(f"{staff['name']}（{cnt}件）")

        if total_count > 0:
            detail = "\n".join(applied_list)
            messagebox.showinfo(
                "パターン一括入力完了",
                f"合計 {total_count} 件を入力しました。\n\n{detail}\n\n"
                "※ 入力済みの日はスキップしました。"
            )
            self.refresh()
        else:
            messagebox.showinfo(
                "パターン一括入力完了",
                "入力できるデータがありませんでした。\n"
                "（すべて入力済み、またはパターン未設定）"
            )

    def _show_clear_menu(self, event, staff):
        """職員名を右クリックしたときにコンテキストメニューを表示する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        menu  = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=f"「{staff['name']}」パターンで一括入力",
            command=lambda: self._apply_pattern_staff(staff, show_result=True)
        )
        menu.add_separator()
        menu.add_command(
            label=f"「{staff['name']}」この期間の記録をすべてクリア",
            command=lambda: self._clear_staff_records(staff, year, month)
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _clear_staff_records(self, staff, year, month):
        """
        指定した職員の、現在の期間（16日〜翌月15日）の勤務記録をすべて削除する。
        管理者の複数スロット（_s1, _s2）も含めてすべて削除する。
        """
        if not messagebox.askyesno(
            "記録の削除確認",
            f"「{staff['name']}」のこの期間の勤務記録を\n"
            "すべて削除してよいですか？\n\n"
            "※ この操作は元に戻せません。",
            parent=self
        ):
            return

        records    = self.dm.load_records()
        staff_id   = staff["id"]
        delete_cnt = 0

        # 月内の全日付に対してキーを生成し、存在すれば削除する
        for y, m, d in get_month_dates(year, month):
            base_key = self.dm._make_key(staff_id, y, m, d)
            # スロット0（基本キー）
            if base_key in records:
                del records[base_key]
                delete_cnt += 1
            # スロット1・2（管理者用）
            for slot in range(1, 3):
                slot_key = f"{base_key}_s{slot}"
                if slot_key in records:
                    del records[slot_key]
                    delete_cnt += 1

        self.dm.save_records(records)
        messagebox.showinfo(
            "削除完了",
            f"「{staff['name']}」の記録を {delete_cnt} 件削除しました。"
        )
        self.refresh()

    def _fill_manager_gaps(self):
        """
        管理者の穴埋め自動入力。
        現在の期間で「早番（14:00カバー）」「夕食帯（18:30カバー）」「夜勤」のいずれかが
        他の職員にカバーされていない日を探し、管理者のスロットに自動入力する。
        昼食帯（8:00〜14:30）は自動入力の対象外。
        """
        year       = self.app.current_year.get()
        month      = self.app.current_month.get()
        all_staff  = self.dm.load_active_staff(f"{year}-{month:02d}-01")
        managers   = [s for s in all_staff if s.get("is_manager")]
        non_mgr    = [s for s in all_staff if not s.get("is_manager")]
        all_shifts = self.dm.load_shifts()

        if not managers:
            messagebox.showwarning(
                "管理者なし",
                "管理者として登録された職員がいません。\n"
                "「職員設定」タブで「管理者」チェックを入れてください。"
            )
            return

        # 穴埋めに使うシフトを種別ごとに探す
        def find_shift(kind):
            """
            kind: 'hayaban'(早番) / 'dinner'(夕食帯) / 'night'(夜勤)
            早番は10:00以降に開始し14:00をカバーするシフト（昼食帯は除外）。
            昼食帯は8:00開始のため10:00未満という条件で自動的に除外される。
            """
            for s in all_shifts:
                if kind == "night" and s.get("is_night"):
                    return s
                s_min = time_to_minutes(s.get("start", ""))
                e_min = time_to_minutes(s.get("end",   ""))
                if s_min is None or s.get("is_night"):
                    continue
                if kind == "hayaban":
                    # 10:00以降に開始し、14:00をカバーするシフトを早番とみなす
                    # （8:00開始の昼食帯は10:00未満のため自動除外）
                    hayaban_check = time_to_minutes("14:00")
                    if s_min >= time_to_minutes("10:00") and s_min <= hayaban_check < (e_min or 0):
                        return s
                if kind == "dinner":
                    dinner = time_to_minutes("18:30")
                    if e_min is not None and s_min <= dinner < e_min:
                        return s
            return None

        hayaban_shift = find_shift("hayaban")
        dinner_shift  = find_shift("dinner")
        night_shift   = find_shift("night")
        filled_count  = 0

        for y, m, d in get_month_dates(year, month):
            # 一般職員のカバー状況を確認する
            has_hayaban = has_dinner = has_night = False
            for staff in non_mgr:
                rec = self.dm.get_record(staff["id"], y, m, d)
                if not rec:
                    continue
                s_str = rec.get("actual_start", "")
                e_str = rec.get("actual_end",   "")
                is_n  = rec.get("is_night",     False)
                if not s_str or not e_str:
                    continue
                s_min = time_to_minutes(s_str)
                e_min = time_to_minutes(e_str)
                if s_min is None or e_min is None:
                    continue
                if is_n and e_min <= s_min:
                    e_min += 24 * 60
                # 15:00をカバーしているか（夕食帯C15:00開始や早番・昼食帯も対象）
                # 15:00基準にすることで、15:00開始の夕食帯がいれば早番不要と判断できる
                if s_min <= time_to_minutes("15:00") < e_min:
                    has_hayaban = True
                if s_min <= time_to_minutes("18:30") < e_min:
                    has_dinner = True
                if is_n:
                    has_night = True

            # 管理者に未カバーのシフトを追加する
            for manager in managers:
                existing           = self.dm.get_records_for_day(manager["id"], y, m, d)
                slot_idx           = len(existing)
                existing_shift_ids = {r.get("shift_id") for r in existing}

                for needed, shift in [
                    (not has_hayaban and hayaban_shift is not None, hayaban_shift),
                    (not has_dinner  and dinner_shift  is not None, dinner_shift),
                    (not has_night   and night_shift   is not None, night_shift),
                ]:
                    if not needed or shift is None:
                        continue
                    if slot_idx >= 3:
                        break
                    if shift["id"] in existing_shift_ids:
                        continue
                    meals = auto_detect_meals(
                        shift.get("start", ""), shift.get("end", ""),
                        shift.get("is_night", False)
                    )
                    data = {
                        "shift_id":     shift["id"],
                        "actual_start": shift.get("start", ""),
                        "actual_end":   shift.get("end",   ""),
                        "actual_break": shift.get("break_min", 0),
                        "break_start":  shift.get("break_start", ""),
                        "is_night":     shift.get("is_night", False),
                        "meal_b":       meals["meal_b"],
                        "meal_l":       meals["meal_l"],
                        "meal_d":       meals["meal_d"],
                        "memo":         "穴埋め自動入力",
                    }
                    self.dm.set_record_slot(manager["id"], y, m, d, slot_idx, data)
                    existing_shift_ids.add(shift["id"])
                    slot_idx     += 1
                    filled_count += 1

        if filled_count > 0:
            messagebox.showinfo(
                "穴埋め完了",
                f"{filled_count} 件のシフトを管理者に自動入力しました。"
            )
        else:
            messagebox.showinfo(
                "穴埋め完了",
                "穴埋めが必要なシフトはありませんでした。\n"
                "（すべての日で早番・夕食帯・夜勤がカバーされています）"
            )
        self.refresh()

    def _on_cell_click(self, staff, date_tuple):
        """セルをクリックしたときにシフト入力ダイアログを開く。管理者は専用ダイアログを使用する"""
        year         = self.app.current_year.get()
        month        = self.app.current_month.get()
        period_dates = get_month_dates(year, month)

        # 最新のスタッフ情報を再読み込みする（設定変更直後でも正しく反映されるように）
        staff_id      = staff["id"]
        fresh_staff   = next(
            (s for s in self.dm.load_staff() if s["id"] == staff_id),
            staff  # 見つからない場合は元のデータを使う
        )

        # 管理者フラグがある職員はマルチスロットダイアログを開く
        if fresh_staff.get("is_manager"):
            dlg = ManagerShiftEditDialog(self, self.app, fresh_staff, date_tuple, period_dates)
        else:
            dlg = ShiftEditDialog(self, self.app, fresh_staff, date_tuple, period_dates)
        self.wait_window(dlg)
        self.refresh()


# ========================
# 管理者用マルチスロット勤務入力ダイアログ
# ========================

class ManagerShiftEditDialog(tk.Toplevel):
    """
    管理者専用の勤務入力ダイアログ。
    1日に最大3つのシフトをタブ形式で入力できる。
    """

    MAX_SLOTS = 3

    def __init__(self, parent, app, staff, date_tuple, period_dates):
        super().__init__(parent)
        self.app          = app
        self.dm           = app.dm
        self.staff        = staff
        self.period_dates = period_dates
        self._date_idx    = period_dates.index(date_tuple)
        # 各スロットのウィジェット参照リスト（各要素は辞書）
        self.slots = []

        self.resizable(True, True)
        self.grab_set()
        self._build()
        self._load_by_idx(self._date_idx)

        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.winfo_width())  // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ── UI構築 ──────────────────────────────────────────

    def _build(self):
        """ダイアログ全体のUIを構築する"""
        main = tk.Frame(self, padx=10, pady=8)
        main.pack(fill="both", expand=True)

        # タイトル
        self.lbl_title = tk.Label(main, text="", font=FONT_BOLD,
                                   bg="#E8EEF8", anchor="w", padx=8, pady=4)
        self.lbl_title.pack(fill="x", pady=(0, 6))

        # 操作ボタン行
        btn_frm = tk.Frame(main)
        btn_frm.pack(fill="x", pady=(0, 6))

        self.btn_prev = tk.Button(
            btn_frm, text="◀ 前日\n(Ctrl+←)", font=FONT,
            command=self._nav_prev, relief="flat", cursor="hand2", padx=10, pady=5)
        self.btn_prev.pack(side="left", padx=3)

        tk.Button(btn_frm, text="  保 存  ", font=FONT_BOLD,
                  command=self._save, bg="#4A6FA5", fg="white",
                  relief="flat", cursor="hand2", padx=12, pady=5).pack(side="left", padx=3)

        self.btn_next = tk.Button(
            btn_frm, text="翌日 ▶\n(Enter)", font=FONT,
            command=self._nav_next, relief="flat", cursor="hand2", padx=10, pady=5)
        self.btn_next.pack(side="left", padx=3)

        tk.Button(btn_frm, text="削除", font=FONT, command=self._delete_all,
                  bg="#CC4444", fg="white", relief="flat",
                  cursor="hand2", padx=8, pady=5).pack(side="left", padx=(14, 3))

        tk.Button(btn_frm, text="閉じる", font=FONT, command=self.destroy,
                  relief="flat", cursor="hand2", padx=8, pady=5).pack(side="left", padx=3)

        # スロットタブ
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)
        for i in range(self.MAX_SLOTS):
            self._build_slot_tab(i)

        # キーバインド
        self.bind("<Return>",        lambda e: self._shortcut_next())
        self.bind("<Control-Right>", lambda e: self._shortcut_next())
        self.bind("<Control-Left>",  lambda e: self._shortcut_prev())
        self.bind("<Control-s>",     lambda e: self._save())
        self.bind("<Escape>",        lambda e: self.destroy())

    def _build_slot_tab(self, slot_idx):
        """スロット番号 slot_idx のタブを構築してノートブックに追加する"""
        tab_frame = tk.Frame(self.notebook, padx=8, pady=6)
        self.notebook.add(tab_frame, text=f"  勤務{slot_idx + 1}  ")

        slot = {
            "selected_shift":  None,
            "shift_buttons":   {},
            "shift_frame":     None,
            "ent_start":       None,
            "ent_end":         None,
            "ent_break":       None,
            "ent_break_start": None,
            "var_is_night":    tk.BooleanVar(),
            "var_meal_b":      tk.BooleanVar(),
            "var_meal_l":      tk.BooleanVar(),
            "var_meal_d":      tk.BooleanVar(),
        }
        self.slots.append(slot)

        # シフトボタン
        frm_shift = tk.LabelFrame(tab_frame, text="シフト選択", font=FONT, padx=8, pady=6)
        frm_shift.pack(fill="x", pady=(0, 6))
        slot["shift_frame"] = frm_shift
        self._rebuild_shift_buttons(slot_idx)

        # 時刻入力
        frm_time = tk.LabelFrame(tab_frame, text="勤務時刻", font=FONT, padx=8, pady=4)
        frm_time.pack(fill="x", pady=(0, 6))

        for i, (lbl, fkey) in enumerate([
            ("開始時刻（例: 09:00）",     "ent_start"),
            ("終了時刻（例: 18:00）",     "ent_end"),
            ("休憩時間（分）",             "ent_break"),
            ("休憩開始時刻（例: 00:00）", "ent_break_start"),
        ]):
            tk.Label(frm_time, text=lbl, font=FONT).grid(
                row=i, column=0, sticky="w", pady=2, padx=(0, 6))
            ent = tk.Entry(frm_time, font=FONT, width=10)
            ent.grid(row=i, column=1, sticky="w", pady=2)
            ent.bind("<FocusOut>", lambda e, si=slot_idx: self._auto_fill_meals(si))
            slot[fkey] = ent

        tk.Checkbutton(
            frm_time, text="夜勤（日またぎ）",
            variable=slot["var_is_night"], font=FONT_SMALL,
            command=lambda si=slot_idx: self._auto_fill_meals(si)
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # 食事
        frm_meal = tk.LabelFrame(tab_frame, text="食事（自動判定・手動変更可）",
                                  font=FONT, padx=8, pady=4)
        frm_meal.pack(fill="x")
        tk.Checkbutton(frm_meal, text="朝食（06:30）",
                       variable=slot["var_meal_b"], font=FONT).pack(side="left", padx=6)
        tk.Checkbutton(frm_meal, text="昼食（12:00）",
                       variable=slot["var_meal_l"], font=FONT).pack(side="left", padx=6)
        tk.Checkbutton(frm_meal, text="夕食（18:30）",
                       variable=slot["var_meal_d"], font=FONT).pack(side="left", padx=6)

    def _rebuild_shift_buttons(self, slot_idx):
        """指定スロットのシフトボタンを再構築する"""
        slot = self.slots[slot_idx]
        frm  = slot["shift_frame"]
        for w in frm.winfo_children():
            w.destroy()
        slot["shift_buttons"]  = {}
        slot["selected_shift"] = None

        all_shifts   = self.dm.load_shifts()
        assigned_ids = self.staff.get("assigned_shifts", [])
        if assigned_ids:
            display = [s for s in all_shifts if s["id"] in assigned_ids]
            order   = {sid: i for i, sid in enumerate(assigned_ids)}
            display.sort(key=lambda s: order.get(s["id"], 999))
            shown = {s["id"] for s in display}
            for s in all_shifts:
                if not s.get("start") and s["id"] not in shown:
                    display.append(s)
        else:
            display = all_shifts

        COLS = 4
        for idx, shift in enumerate(display):
            btn = tk.Button(
                frm,
                text=f"  {shift['name']}  ",
                font=FONT,
                bg=shift.get("color", "#FFFFFF"),
                relief="raised", bd=2, cursor="hand2", padx=4, pady=3,
                command=lambda s=shift, si=slot_idx: self._on_shift_btn(si, s)
            )
            btn.grid(row=idx // COLS, column=idx % COLS, padx=2, pady=2, sticky="w")
            slot["shift_buttons"][shift["id"]] = btn

    # ── シフト選択 ──────────────────────────────────────

    def _on_shift_btn(self, slot_idx, shift):
        """シフトボタン押下：選択状態を更新してデフォルト時刻を入力する"""
        slot = self.slots[slot_idx]
        for sid, btn in slot["shift_buttons"].items():
            s = self.dm.get_shift_by_id(sid)
            bg = s.get("color", "#FFFFFF") if s else "#FFFFFF"
            btn.configure(relief="raised", bd=2, bg=bg)
        if shift and shift["id"] in slot["shift_buttons"]:
            slot["shift_buttons"][shift["id"]].configure(relief="solid", bd=3)
        slot["selected_shift"] = shift

        slot["ent_start"].delete(0, tk.END)
        slot["ent_end"].delete(0, tk.END)
        slot["ent_break"].delete(0, tk.END)
        slot["ent_break_start"].delete(0, tk.END)
        slot["ent_start"].insert(0, shift.get("start", ""))
        slot["ent_end"].insert(0,   shift.get("end",   ""))
        slot["ent_break"].insert(0, str(shift.get("break_min", 0)))
        slot["ent_break_start"].insert(0, shift.get("break_start", ""))
        slot["var_is_night"].set(shift.get("is_night", False))
        self._auto_fill_meals(slot_idx)

    def _auto_fill_meals(self, slot_idx):
        """指定スロットの時刻から食事チェックを自動設定する"""
        slot = self.slots[slot_idx]
        meals = auto_detect_meals(
            slot["ent_start"].get().strip(),
            slot["ent_end"].get().strip(),
            slot["var_is_night"].get()
        )
        slot["var_meal_b"].set(meals["meal_b"])
        slot["var_meal_l"].set(meals["meal_l"])
        slot["var_meal_d"].set(meals["meal_d"])

    # ── ナビゲーション ────────────────────────────────────

    def _nav_prev(self):
        self._save(silent=True)
        self._load_by_idx(self._date_idx - 1)

    def _nav_next(self):
        self._save(silent=True)
        self._load_by_idx(self._date_idx + 1)

    def _shortcut_prev(self):
        if self.btn_prev["state"] != "disabled":
            self._nav_prev()

    def _shortcut_next(self):
        if self.btn_next["state"] != "disabled":
            self._nav_next()
        else:
            self._save()

    # ── 読み込み ──────────────────────────────────────────

    def _load_by_idx(self, idx):
        """period_dates[idx] の日付データを全スロットに読み込む"""
        self._date_idx = idx
        y, m, d = self.period_dates[idx]
        weekday = datetime(y, m, d).weekday()

        self.title(
            f"勤務入力（管理者）：{self.staff['name']}  "
            f"{y}/{m:02d}/{d:02d}（{WEEKDAY_JP[weekday]}）"
        )
        self.lbl_title.config(
            text=f"{y}年{m}月{d}日（{WEEKDAY_JP[weekday]}）　"
                 f"{self.staff['name']}　【管理者・複数シフト】"
        )
        self.btn_prev.config(state="normal" if idx > 0                        else "disabled")
        self.btn_next.config(state="normal" if idx < len(self.period_dates)-1 else "disabled")

        # 全スロットをクリア
        for slot in self.slots:
            for sid, btn in slot["shift_buttons"].items():
                s = self.dm.get_shift_by_id(sid)
                bg = s.get("color", "#FFFFFF") if s else "#FFFFFF"
                btn.configure(relief="raised", bd=2, bg=bg)
            slot["selected_shift"] = None
            for fkey in ("ent_start", "ent_end", "ent_break", "ent_break_start"):
                slot[fkey].delete(0, tk.END)
            slot["var_is_night"].set(False)
            slot["var_meal_b"].set(False)
            slot["var_meal_l"].set(False)
            slot["var_meal_d"].set(False)

        # 既存記録を各スロットに復元
        records = self.dm.get_records_for_day(self.staff["id"], y, m, d)
        for slot_idx, record in enumerate(records[:self.MAX_SLOTS]):
            slot  = self.slots[slot_idx]
            shift = self.dm.get_shift_by_id(record.get("shift_id", ""))
            if shift and shift["id"] in slot["shift_buttons"]:
                slot["shift_buttons"][shift["id"]].configure(relief="solid", bd=3)
                slot["selected_shift"] = shift
            slot["ent_start"].insert(0, record.get("actual_start", ""))
            slot["ent_end"].insert(0,   record.get("actual_end",   ""))
            slot["ent_break"].insert(0, str(record.get("actual_break", "")))
            slot["ent_break_start"].insert(0, record.get("break_start", ""))
            slot["var_is_night"].set(record.get("is_night",  False))
            slot["var_meal_b"].set(  record.get("meal_b",    False))
            slot["var_meal_l"].set(  record.get("meal_l",    False))
            slot["var_meal_d"].set(  record.get("meal_d",    False))

    # ── 保存・削除 ────────────────────────────────────────

    def _normalize_time(self, time_str):
        """全角コロン・全角数字を半角に正規化して返す"""
        if not time_str:
            return time_str
        return time_str.replace("：", ":").translate(
            str.maketrans("０１２３４５６７８９", "0123456789"))

    def _save(self, silent=False):
        """全スロットの内容を保存する"""
        y, m, d = self.period_dates[self._date_idx]
        for slot_idx, slot in enumerate(self.slots):
            shift = slot["selected_shift"]
            if not shift:
                self.dm.set_record_slot(self.staff["id"], y, m, d, slot_idx, None)
                continue
            try:
                break_min = int(slot["ent_break"].get().strip() or "0")
            except ValueError:
                break_min = 0
            data = {
                "shift_id":     shift["id"],
                "actual_start": self._normalize_time(slot["ent_start"].get().strip()),
                "actual_end":   self._normalize_time(slot["ent_end"].get().strip()),
                "actual_break": break_min,
                "break_start":  self._normalize_time(slot["ent_break_start"].get().strip()),
                "is_night":     slot["var_is_night"].get(),
                "meal_b":       slot["var_meal_b"].get(),
                "meal_l":       slot["var_meal_l"].get(),
                "meal_d":       slot["var_meal_d"].get(),
                "memo":         "",
            }
            self.dm.set_record_slot(self.staff["id"], y, m, d, slot_idx, data)
        if not silent:
            self.destroy()

    def _delete_all(self):
        """この日の全スロットを削除する"""
        if messagebox.askyesno("削除の確認",
                               "この日の勤務記録をすべて削除してよいですか？", parent=self):
            y, m, d = self.period_dates[self._date_idx]
            for slot_idx in range(self.MAX_SLOTS):
                self.dm.set_record_slot(self.staff["id"], y, m, d, slot_idx, None)
            self._load_by_idx(self._date_idx)


# ========================
# シフト入力ダイアログ
# ========================

class ShiftEditDialog(tk.Toplevel):
    """
    1日分のシフト情報を入力・編集するダイアログウィンドウ。

    【特徴】
    - シフト選択はボタン式（職員に割り当てられたシフトのみ表示）
    - 勤務時刻を入力すると食事（朝・昼・夕）を自動判定してチェック
    - 「◀ 前日」「翌日 ▶」ボタンで日をまたいで連続入力できる
    """

    def __init__(self, parent, app, staff, date_tuple, period_dates):
        """
        引数:
            date_tuple:   最初に表示する日付 (year, month, day)
            period_dates: 期間内の全日付リスト [(y,m,d), ...]
        """
        super().__init__(parent)
        self.app          = app
        self.dm           = app.dm
        self.staff        = staff
        self.period_dates = period_dates   # 期間内の全日付
        self._date_idx    = period_dates.index(date_tuple)  # 現在の位置
        self._selected_shift = None
        self._shift_buttons  = {}

        self.resizable(False, False)
        self.grab_set()

        self._build()
        self._load_by_idx(self._date_idx)

        self.update_idletasks()
        x = (self.winfo_screenwidth()  - self.winfo_width())  // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    # ── UI構築 ──────────────────────────────────────────

    def _build(self):
        """ダイアログ全体のウィジェットを構築する"""
        main = tk.Frame(self, padx=15, pady=10)
        main.pack(fill="both", expand=True)

        # タイトルラベル（日付・職員名を表示。日移動のたびに更新）
        self.lbl_title = tk.Label(main, text="", font=FONT_BOLD, anchor="w", fg="#2244AA")
        self.lbl_title.pack(fill="x", pady=(0, 8))

        # ── シフト選択ボタン ＋ 操作ボタンをまとめた枠 ──
        # シフト選択とナビゲーションを1つのLabelFrameにまとめ、
        # ボタン選択後すぐ保存・前日・翌日を押せるようにする
        frm_shift = tk.LabelFrame(
            main,
            text="シフト選択（職員設定で割り当てたシフトのみ表示）",
            font=FONT, padx=8, pady=6
        )
        frm_shift.pack(fill="x", pady=(0, 10))

        # シフトボタン行
        self.shift_btn_frame = tk.Frame(frm_shift)
        self.shift_btn_frame.pack(fill="x")
        self._build_shift_buttons()

        # 区切り線
        ttk.Separator(frm_shift, orient="horizontal").pack(fill="x", pady=(8, 6))

        # 操作ボタン行（シフトボタンのすぐ下）
        btn_frm = tk.Frame(frm_shift)
        btn_frm.pack()

        self.btn_prev = tk.Button(
            btn_frm, text="◀ 前日", font=FONT,
            command=self._nav_prev,
            relief="flat", cursor="hand2", padx=10, pady=5
        )
        self.btn_prev.pack(side="left", padx=3)

        tk.Button(
            btn_frm, text="  保 存  ", font=FONT_BOLD,
            command=self._save,
            bg="#4A6FA5", fg="white", relief="flat", cursor="hand2",
            padx=12, pady=5
        ).pack(side="left", padx=3)

        self.btn_next = tk.Button(
            btn_frm, text="翌日 ▶", font=FONT,
            command=self._nav_next,
            relief="flat", cursor="hand2", padx=10, pady=5
        )
        self.btn_next.pack(side="left", padx=3)

        tk.Button(
            btn_frm, text="削除", font=FONT,
            command=self._delete,
            bg="#CC4444", fg="white", relief="flat", cursor="hand2",
            padx=8, pady=5
        ).pack(side="left", padx=(14, 3))

        tk.Button(
            btn_frm, text="閉じる", font=FONT,
            command=self.destroy,
            relief="flat", cursor="hand2", padx=8, pady=5
        ).pack(side="left", padx=3)

        # ── 実際の勤務時刻 ──
        frm_time = tk.LabelFrame(main, text="実際の勤務時刻", font=FONT, padx=10, pady=6)
        frm_time.pack(fill="x", pady=(0, 8))

        for i, (label_text, attr_name) in enumerate([
            ("開始時刻（例: 09:00）",       "ent_start"),
            ("終了時刻（例: 18:00）",       "ent_end"),
            ("休憩時間（分）",              "ent_break"),
            ("休憩開始時刻（例: 00:00）",   "ent_break_start"),
        ]):
            tk.Label(frm_time, text=label_text, font=FONT).grid(
                row=i, column=0, sticky="w", pady=3, padx=(0, 8)
            )
            ent = tk.Entry(frm_time, font=FONT, width=10)
            ent.grid(row=i, column=1, sticky="w", pady=3)
            setattr(self, attr_name, ent)
            # フォーカスが外れたタイミングで食事を自動判定する
            ent.bind("<FocusOut>", lambda e: self._auto_fill_meals())

        # 休憩開始時刻の補足説明
        tk.Label(
            frm_time,
            text="  ※夜勤の場合に入力。深夜時間の正確な計算に使用します。",
            font=FONT_SMALL, fg="#666666"
        ).grid(row=3, column=2, sticky="w", padx=(4, 0))

        self.var_is_night = tk.BooleanVar()
        tk.Checkbutton(
            frm_time,
            text="夜勤（日またぎ）  ※チェックすると翌日終了として計算されます",
            variable=self.var_is_night,
            font=FONT_SMALL,
            command=self._auto_fill_meals
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # 穴埋め計算ボタン（他の職員がカバーしていない時間帯を自動入力する）
        tk.Button(
            frm_time,
            text="穴埋め計算",
            font=FONT_SMALL,
            command=self._calc_gap_times,
            relief="flat", cursor="hand2",
            bg="#7A5C9E", fg="white", padx=8, pady=2
        ).grid(row=4, column=2, sticky="e", pady=(6, 0), padx=(4, 0))

        # ── 食事（自動判定 + 手動修正可） ──
        frm_meal = tk.LabelFrame(
            main,
            text="食事（勤務時間から自動判定・手動で変更可）",
            font=FONT, padx=10, pady=6
        )
        frm_meal.pack(fill="x", pady=(0, 8))

        self.var_meal_b = tk.BooleanVar()
        self.var_meal_l = tk.BooleanVar()
        self.var_meal_d = tk.BooleanVar()

        tk.Checkbutton(frm_meal, text="朝食（06:30）", variable=self.var_meal_b, font=FONT).pack(side="left", padx=10)
        tk.Checkbutton(frm_meal, text="昼食（12:00）", variable=self.var_meal_l, font=FONT).pack(side="left", padx=10)
        tk.Checkbutton(frm_meal, text="夕食（18:30）", variable=self.var_meal_d, font=FONT).pack(side="left", padx=10)

        # ── メモ ──
        frm_memo = tk.LabelFrame(main, text="メモ（任意）", font=FONT, padx=10, pady=6)
        frm_memo.pack(fill="x", pady=(0, 4))
        self.ent_memo = tk.Entry(frm_memo, font=FONT, width=36)
        self.ent_memo.pack(fill="x")

        # ── ショートカットキーの登録 ──
        # Enter       → 翌日へ（保存して次の日に移動）
        # Ctrl+右矢印 → 翌日へ（同上）
        # Ctrl+左矢印 → 前日へ（保存して前の日に移動）
        # Ctrl+S      → 保存のみ（ダイアログを閉じる）
        # Escape      → 閉じる
        self.bind("<Return>",          lambda e: self._shortcut_next())
        self.bind("<Control-Right>",   lambda e: self._shortcut_next())
        self.bind("<Control-Left>",    lambda e: self._shortcut_prev())
        self.bind("<Control-s>",       lambda e: self._save())
        self.bind("<Escape>",          lambda e: self.destroy())

        # ショートカットのヒントをボタンに表示する
        self.btn_prev.config(text="◀ 前日\n(Ctrl+←)")
        self.btn_next.config(text="翌日 ▶\n(Enter)")

    def _build_shift_buttons(self):
        """
        シフト選択ボタンを生成する。
        職員の「担当シフト（assigned_shifts）」に登録されたシフトのみ表示する。
        割り当てがない場合は全シフトを表示する。
        """
        # 既存ボタンをすべて削除
        for w in self.shift_btn_frame.winfo_children():
            w.destroy()
        self._shift_buttons  = {}
        self._selected_shift = None

        # 表示するシフトを決定する
        all_shifts   = self.dm.load_shifts()
        assigned_ids = self.staff.get("assigned_shifts", [])
        if assigned_ids:
            display_shifts = [s for s in all_shifts if s["id"] in assigned_ids]
            # 割り当て順を保持する（assigned_idsの順番通りに並べる）
            id_order       = {sid: i for i, sid in enumerate(assigned_ids)}
            display_shifts.sort(key=lambda s: id_order.get(s["id"], 999))
            # 公休・有給・欠勤など（開始時刻が空のシフト）は割り当て未登録でも常に末尾に表示する
            shown_ids = {s["id"] for s in display_shifts}
            for s in all_shifts:
                if not s.get("start") and s["id"] not in shown_ids:
                    display_shifts.append(s)
        else:
            display_shifts = all_shifts

        COLS = 4  # 1行に並べるボタン数

        if not display_shifts:
            tk.Label(
                self.shift_btn_frame,
                text="表示するシフトがありません。「シフト設定」タブで追加してください。",
                font=FONT_SMALL, fg="#888888"
            ).pack()
            return

        for idx, shift in enumerate(display_shifts):
            row = idx // COLS
            col = idx % COLS

            btn = tk.Button(
                self.shift_btn_frame,
                text=f"  {shift['name']}  ",
                font=FONT,
                bg=shift.get("color", "#FFFFFF"),
                relief="raised",
                bd=2,
                cursor="hand2",
                padx=4, pady=4,
                command=lambda s=shift: self._on_shift_btn(s)
            )
            btn.grid(row=row, column=col, padx=3, pady=3, sticky="w")
            self._shift_buttons[shift["id"]] = btn

    # ── シフト選択 ──────────────────────────────────────

    def _on_shift_btn(self, shift):
        """シフトボタンがクリックされたとき：選択状態を更新し時刻を自動入力する"""
        self._set_selected(shift)

        # そのシフトのデフォルト時刻をセットする
        self.ent_start.delete(0, tk.END)
        self.ent_end.delete(0, tk.END)
        self.ent_break.delete(0, tk.END)
        self.ent_break_start.delete(0, tk.END)
        self.ent_start.insert(0, shift.get("start", ""))
        self.ent_end.insert(0,   shift.get("end",   ""))
        self.ent_break.insert(0, str(shift.get("break_min", 0)))
        self.ent_break_start.insert(0, shift.get("break_start", ""))
        self.var_is_night.set(shift.get("is_night", False))

        # 食事を自動判定する
        self._auto_fill_meals()

    def _set_selected(self, shift):
        """
        指定したシフトを選択状態（枠付き）にする。
        他のボタンは通常スタイルに戻す。
        """
        # 全ボタンを非選択スタイルに戻す
        for sid, btn in self._shift_buttons.items():
            s = self.dm.get_shift_by_id(sid)
            bg = s.get("color", "#FFFFFF") if s else "#FFFFFF"
            btn.configure(relief="raised", bd=2, bg=bg)

        # 選択ボタンを強調表示する（太枠 + 少し暗い背景）
        if shift and shift["id"] in self._shift_buttons:
            btn = self._shift_buttons[shift["id"]]
            btn.configure(relief="solid", bd=3)

        self._selected_shift = shift

    # ── 食事自動判定 ─────────────────────────────────────

    def _auto_fill_meals(self):
        """
        現在の開始・終了時刻から食事チェックを自動設定する。
        既存の記録を読み込んだときは上書きしない（手動変更を尊重する）。
        """
        start_str = self.ent_start.get().strip()
        end_str   = self.ent_end.get().strip()
        is_night  = self.var_is_night.get()

        meals = auto_detect_meals(start_str, end_str, is_night)
        self.var_meal_b.set(meals["meal_b"])
        self.var_meal_l.set(meals["meal_l"])
        self.var_meal_d.set(meals["meal_d"])

    # ── 穴埋め計算 ───────────────────────────────────────

    def _calc_gap_times(self):
        """
        この日に他の職員がカバーしていない時間帯を計算し、開始・終了時刻に自動入力する。
        「管理者がシフトの穴を埋める」ときに使う機能。

        処理の流れ:
          1. 今日の他の職員の勤務時間をすべて収集する
          2. 重複を統合して「カバー済み時間帯」のリストを作る
          3. カバー済みの間にある「穴（ギャップ）」を探す
          4. 穴が1つなら自動入力。複数ならリスト表示して最初の穴を入力するか確認する
        """
        y, m, d = self.period_dates[self._date_idx]
        all_staff = self.dm.load_active_staff(f"{y}-{m:02d}-{d:02d}")

        # ── 他の職員の勤務時間を収集 ──
        covered = []
        for staff in all_staff:
            if staff["id"] == self.staff["id"]:
                continue   # 自分自身はスキップ
            record = self.dm.get_record(staff["id"], y, m, d)
            if not record:
                continue
            s_str = record.get("actual_start", "")
            e_str = record.get("actual_end",   "")
            is_n  = record.get("is_night",     False)
            if not s_str or not e_str:
                continue
            s_min = time_to_minutes(s_str)
            e_min = time_to_minutes(e_str)
            if s_min is None or e_min is None:
                continue
            # 夜勤（日またぎ）は終了時刻に24時間加算して連続した時間として扱う
            if is_n and e_min <= s_min:
                e_min += 24 * 60
            covered.append((s_min, e_min))

        if not covered:
            messagebox.showinfo(
                "穴埋め計算",
                "他の職員の勤務記録がこの日には見つかりませんでした。\n"
                "先に他の職員の入力を行ってから使用してください。",
                parent=self
            )
            return

        # ── 重複する時間帯をマージして「カバー済み区間」リストを作る ──
        covered.sort()
        merged = [list(covered[0])]
        for s, e in covered[1:]:
            if s <= merged[-1][1]:
                # 前の区間と重なる（または連続する）→ 終了時刻を延ばして統合
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])

        # ── カバー済み区間の「間」にあるギャップを探す ──
        gaps = []
        for i in range(len(merged) - 1):
            gap_s = merged[i][1]     # 前の区間の終わり
            gap_e = merged[i + 1][0] # 次の区間の始まり
            if gap_e > gap_s:
                gaps.append((gap_s, gap_e))

        if not gaps:
            # カバー済み範囲を読みやすい文字列に変換して表示する
            cover_str = "、".join(
                f"{s // 60 % 24:02d}:{s % 60:02d}〜{e // 60 % 24:02d}:{e % 60:02d}"
                for s, e in merged
            )
            messagebox.showinfo(
                "穴埋め計算",
                f"この日は穴がありません。\n\nカバー済み時間帯:\n  {cover_str}",
                parent=self
            )
            return

        # ── 分単位 → "HH:MM" 文字列に変換するローカル関数 ──
        def mins_to_str(mins):
            """1440分（24:00）を超える場合も正しく表示する（25:00 など翌日時刻）"""
            h = mins // 60
            m = mins % 60
            return f"{h:02d}:{m:02d}"

        def mins_to_display(mins):
            """表示用：25:00 → 翌01:00 のように括弧付きで示す"""
            if mins >= 24 * 60:
                return f"{mins // 60 % 24:02d}:{mins % 60:02d}（翌日）"
            return f"{mins // 60:02d}:{mins % 60:02d}"

        # ── 穴が1つなら自動入力、複数なら確認ダイアログを出す ──
        if len(gaps) == 1:
            gs, ge = gaps[0]
            self._set_gap(mins_to_str(gs), mins_to_str(ge), ge >= 24 * 60)
            messagebox.showinfo(
                "穴埋め計算",
                f"穴埋め時間を設定しました。\n\n"
                f"  {mins_to_display(gs)} 〜 {mins_to_display(ge)}",
                parent=self
            )
        else:
            # 複数の穴をリスト表示して最初の穴を入力するか確認
            gap_list = "\n".join(
                f"  {i + 1}. {mins_to_display(gs)} 〜 {mins_to_display(ge)}"
                for i, (gs, ge) in enumerate(gaps)
            )
            ans = messagebox.askyesno(
                "穴埋め計算",
                f"この日には {len(gaps)} か所の穴があります。\n\n"
                f"{gap_list}\n\n"
                f"最初の穴（1番）の時間を入力しますか？",
                parent=self
            )
            if ans:
                gs, ge = gaps[0]
                self._set_gap(mins_to_str(gs), mins_to_str(ge), ge >= 24 * 60)

    def _set_gap(self, start_str, end_str, is_night):
        """
        計算した穴埋め時間を開始・終了時刻フィールドにセットする。

        引数:
            start_str: 開始時刻文字列（例: "21:00"）
            end_str:   終了時刻文字列（例: "25:00" のように24超もありえる）
            is_night:  日またぎかどうか
        """
        # 終了時刻が24時間を超える場合は mod 24 して is_night フラグを立てる
        if is_night:
            h = int(end_str.split(":")[0]) % 24
            m_str = end_str.split(":")[1]
            end_str = f"{h:02d}:{m_str}"

        self.ent_start.delete(0, tk.END)
        self.ent_start.insert(0, start_str)
        self.ent_end.delete(0, tk.END)
        self.ent_end.insert(0, end_str)
        self.var_is_night.set(is_night)
        self._auto_fill_meals()

    # ── 日付ナビゲーション ────────────────────────────────

    def _nav_prev(self):
        """前日へ移動する。移動前に現在の入力を保存する"""
        self._save(silent=True)
        self._load_by_idx(self._date_idx - 1)

    def _nav_next(self):
        """翌日へ移動する。移動前に現在の入力を保存する"""
        self._save(silent=True)
        self._load_by_idx(self._date_idx + 1)

    def _shortcut_prev(self):
        """Ctrl+← ショートカット：前日ボタンが有効なときだけ移動する"""
        if self.btn_prev["state"] != "disabled":
            self._nav_prev()

    def _shortcut_next(self):
        """
        Enter / Ctrl+→ ショートカット：翌日へ進む。期末なら保存して閉じる。
        シフトが未選択の場合は「公休」を自動入力してから進む。
        """
        # シフトが未選択なら公休を自動セットする
        if self._selected_shift is None:
            self._auto_select_dayoff()

        if self.btn_next["state"] != "disabled":
            self._nav_next()
        else:
            self._save()

    def _auto_select_dayoff(self):
        """
        シフトが未選択のとき、「公休」（start が空のシフト）を自動選択する。
        公休が見つからない場合は何もしない。
        """
        for shift in self.dm.load_shifts():
            if shift.get("id") == "day_off" or (
                not shift.get("start") and shift.get("name") in ("公休", "公欠")
            ):
                self._on_shift_btn(shift)
                return
        # day_off が見つからなければ start が空の最初のシフトを使う
        for shift in self.dm.load_shifts():
            if not shift.get("start"):
                self._on_shift_btn(shift)
                return

    def _load_by_idx(self, idx):
        """
        period_dates[idx] の日付データをフォームに読み込む。
        前日/翌日ナビゲーション時にも使用する。
        """
        self._date_idx = idx
        y, m, d = self.period_dates[idx]
        weekday = datetime(y, m, d).weekday()

        # タイトルを更新する
        self.title(
            f"勤務入力：{self.staff['name']}  {y}/{m:02d}/{d:02d}（{WEEKDAY_JP[weekday]}）"
        )
        self.lbl_title.config(
            text=f"{y}年{m}月{d}日（{WEEKDAY_JP[weekday]}）　{self.staff['name']}"
        )

        # 前日・翌日ボタンの有効/無効（期間の端では無効化）
        self.btn_prev.config(state="normal" if idx > 0                        else "disabled")
        self.btn_next.config(state="normal" if idx < len(self.period_dates)-1 else "disabled")

        # フォームをクリア
        self._set_selected(None)
        self.ent_start.delete(0, tk.END)
        self.ent_end.delete(0, tk.END)
        self.ent_break.delete(0, tk.END)
        self.ent_break_start.delete(0, tk.END)
        self.ent_memo.delete(0, tk.END)
        self.var_is_night.set(False)
        self.var_meal_b.set(False)
        self.var_meal_l.set(False)
        self.var_meal_d.set(False)

        # 既存の記録があれば復元する
        record = self.dm.get_record(self.staff["id"], y, m, d) or {}
        if record:
            shift = self.dm.get_shift_by_id(record.get("shift_id", ""))
            if shift:
                self._set_selected(shift)
            self.ent_start.insert(0, record.get("actual_start", ""))
            self.ent_end.insert(0,   record.get("actual_end",   ""))
            self.ent_break.insert(0, str(record.get("actual_break", "")))
            self.ent_break_start.insert(0, record.get("break_start", ""))
            self.var_is_night.set(record.get("is_night",  False))
            self.var_meal_b.set(  record.get("meal_b",    False))
            self.var_meal_l.set(  record.get("meal_l",    False))
            self.var_meal_d.set(  record.get("meal_d",    False))
            self.ent_memo.insert(0, record.get("memo", ""))
        else:
            # 新規：担当シフトが1つだけなら自動選択する
            assigned_ids = self.staff.get("assigned_shifts", [])
            all_shifts   = self.dm.load_shifts()
            candidates   = [s for s in all_shifts if s["id"] in assigned_ids] if assigned_ids else all_shifts
            if len(candidates) == 1:
                self._on_shift_btn(candidates[0])

    # ── 検証・保存・削除 ──────────────────────────────────

    def _normalize_time(self, time_str):
        """
        時刻文字列を半角に正規化して返す。
        全角コロン「：」→半角「:」、全角数字「０〜９」→半角「0〜9」に変換する。
        IMEがオンのまま入力されても正しく処理できるようにするための処置。
        """
        if not time_str:
            return time_str
        # 全角コロンを半角コロンに変換
        result = time_str.replace("：", ":")
        # 全角数字を半角数字に変換（０→0, １→1, ... ９→9）
        result = result.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        return result

    def _validate_time(self, time_str):
        """時刻文字列が "HH:MM" 形式かチェックする。空文字はOK"""
        if not time_str:
            return True
        try:
            parts = time_str.split(":")
            if len(parts) != 2:
                return False
            h, m = int(parts[0]), int(parts[1])
            return 0 <= h <= 23 and 0 <= m <= 59
        except ValueError:
            return False

    def _save(self, silent=False):
        """
        現在の入力内容を保存する。
        silent=True のとき：前日/翌日ナビ用。エラーダイアログを出さずに保存し、
        ダイアログも閉じない。シフト未選択なら何もしない。
        """
        y, m, d = self.period_dates[self._date_idx]   # 現在の日付を取得

        if not self._selected_shift:
            self.dm.set_record(self.staff["id"], y, m, d, None)
            if not silent:
                self.destroy()
            return

        shift            = self._selected_shift
        # 全角文字（全角コロン・全角数字など）を半角に統一して保存ミスを防ぐ
        start_str        = self._normalize_time(self.ent_start.get().strip())
        end_str          = self._normalize_time(self.ent_end.get().strip())
        break_str        = self.ent_break.get().strip()
        break_start_str  = self._normalize_time(self.ent_break_start.get().strip())

        if not silent:
            if not self._validate_time(start_str):
                messagebox.showerror("入力エラー", "開始時刻の形式が正しくありません。\n「09:00」のように入力してください。", parent=self)
                return
            if not self._validate_time(end_str):
                messagebox.showerror("入力エラー", "終了時刻の形式が正しくありません。\n「18:00」のように入力してください。", parent=self)
                return
            if break_start_str and not self._validate_time(break_start_str):
                messagebox.showerror("入力エラー", "休憩開始時刻の形式が正しくありません。\n「00:00」のように入力してください。", parent=self)
                return

        try:
            break_min = int(break_str) if break_str else 0
        except ValueError:
            break_min = 0

        data = {
            "shift_id":     shift["id"],
            "actual_start": start_str,
            "actual_end":   end_str,
            "actual_break": break_min,
            "break_start":  break_start_str,   # 休憩開始時刻（深夜時間の正確な計算に使用）
            "is_night":     self.var_is_night.get(),
            "meal_b":       self.var_meal_b.get(),
            "meal_l":       self.var_meal_l.get(),
            "meal_d":       self.var_meal_d.get(),
            "memo":         self.ent_memo.get().strip()
        }

        self.dm.set_record(self.staff["id"], y, m, d, data)

        if not silent:
            self.destroy()

    def _delete(self):
        """この日の勤務記録を削除してフォームをリセットする"""
        if messagebox.askyesno("削除の確認", "この日の勤務記録を削除してよいですか？", parent=self):
            y, m, d = self.period_dates[self._date_idx]
            self.dm.set_record(self.staff["id"], y, m, d, None)
            self._load_by_idx(self._date_idx)


# ========================
# 集計タブ
# ========================

class SummaryTab(tk.Frame):
    """月次の勤務集計を表示するタブ"""

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F5F6FA")
        self.app = app
        self.dm  = app.dm
        self._build()
        self.refresh()

    def _build(self):
        """ウィジェットを構築する"""

        # ── 上部コントロールバー ──
        ctrl = tk.Frame(self, bg="#F5F6FA", pady=6)
        ctrl.pack(fill="x", padx=10)

        tk.Button(
            ctrl, text="◀ 前月", font=FONT,
            command=self._prev_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        self.lbl_yearmonth = tk.Label(
            ctrl, text="", font=FONT_BOLD, bg="#F5F6FA", width=26
        )
        self.lbl_yearmonth.pack(side="left", padx=8)

        tk.Button(
            ctrl, text="翌月 ▶", font=FONT,
            command=self._next_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        tk.Button(
            ctrl, text="今月", font=FONT,
            command=self._goto_today,
            relief="flat", cursor="hand2", padx=10, pady=3
        ).pack(side="left", padx=12)

        tk.Button(
            ctrl, text="印刷", font=FONT,
            command=self._print_summary,
            relief="flat", cursor="hand2",
            bg="#555555", fg="white", padx=10, pady=3
        ).pack(side="right", padx=(0, 6))

        tk.Button(
            ctrl, text="CSV出力", font=FONT,
            command=self._export_csv,
            relief="flat", cursor="hand2",
            bg="#2E7D32", fg="white", padx=12, pady=3
        ).pack(side="right")

        tk.Button(
            ctrl, text="管理者 穴埋め自動入力", font=FONT,
            command=self._fill_manager_gaps,
            relief="flat", cursor="hand2",
            bg="#7A5C9E", fg="white", padx=10, pady=3
        ).pack(side="right", padx=(0, 6))

        # ── 集計テーブル ──
        # 列の定義：（列ID、ヘッダー、幅）
        columns_def = [
            ("name",         "職員名",           110),
            ("work_days",    "出勤\n日数",         60),
            ("work_hours",   "総労働\n時間",        80),
            ("regular",      "普通就業\n時間",      80),
            ("late_night",   "深夜\n時間",          80),
            ("overtime",     "残業\n時間",          80),
            ("night_shifts", "通勤回数\n(交通費)",   90),
            ("meal_b",       "朝食\n回数",          55),
            ("meal_l",       "昼食\n回数",          55),
            ("meal_d",       "夕食\n回数",          55),
        ]
        col_ids = [c[0] for c in columns_def]

        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(
            tree_frame, columns=col_ids, show="headings",
            height=16
        )
        for col_id, header, width in columns_def:
            self.tree.heading(col_id, text=header)
            self.tree.column(col_id, width=width, anchor="center", minwidth=40)
        self.tree.column("name", anchor="w")

        v_sb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        h_sb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_sb.set, xscrollcommand=h_sb.set)

        v_sb.pack(side="right",  fill="y")
        h_sb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        # 偶数行・奇数行の色設定
        self.tree.tag_configure("even", background="#FFFFFF")
        self.tree.tag_configure("odd",  background="#F0F4FA")

        # ── 合計表示ラベル ──
        self.lbl_total = tk.Label(
            self, text="", font=FONT_SMALL, bg="#E8EEF8",
            anchor="w", padx=10, pady=4
        )
        self.lbl_total.pack(fill="x", padx=10, pady=(0, 5))

        # ── 凡例 ──
        legend = tk.Label(
            self,
            text="【集計の説明】 総労働時間：実労働時間合計　普通就業時間：総労働−深夜−残業　"
                 "深夜時間：22時〜翌5時　残業時間：1日8時間超　通勤回数＝交通費支給回数（日勤は出勤日ごと1回・夜勤は1回ずつ）",
            font=FONT_SMALL, bg="#F5F6FA", fg="#555555", anchor="w"
        )
        legend.pack(fill="x", padx=10, pady=(0, 5))

    def _prev_month(self):
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 1:
            self.app.current_year.set(y - 1)
            self.app.current_month.set(12)
        else:
            self.app.current_month.set(m - 1)
        self.refresh()

    def _next_month(self):
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 12:
            self.app.current_year.set(y + 1)
            self.app.current_month.set(1)
        else:
            self.app.current_month.set(m + 1)
        self.refresh()

    def _goto_today(self):
        py, pm = current_period()
        self.app.current_year.set(py)
        self.app.current_month.set(pm)
        self.refresh()

    def refresh(self):
        """集計データを再計算してテーブルに表示する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        # 集計タブは給与期間（16日〜翌月15日）で集計するため、期間ラベルを表示する
        self.lbl_yearmonth.config(text=f"【給与集計】{get_period_label(year, month)}")

        # テーブルをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")
        if not staff_list:
            self.lbl_total.config(text="職員が登録されていません。")
            return

        # 全職員の合計を集計するための変数
        total_days    = 0
        total_work    = 0
        total_regular = 0
        total_night   = 0
        total_ot      = 0
        total_nshift  = 0
        total_mb      = 0
        total_ml      = 0
        total_md      = 0

        for i, staff in enumerate(staff_list):
            s = self._calc_summary(staff["id"], year, month)
            tag = "even" if i % 2 == 0 else "odd"

            self.tree.insert("", "end", tag=tag, values=(
                staff["name"],
                f'{s["work_days"]}日',
                minutes_to_hhmm(s["work_min"]),
                minutes_to_hhmm(s["regular_min"]),
                minutes_to_hhmm(s["late_night_min"]),
                minutes_to_hhmm(s["overtime_min"]),
                f'{s["night_shifts"]}回',
                f'{s["meal_b"]}回',
                f'{s["meal_l"]}回',
                f'{s["meal_d"]}回',
            ))

            total_days    += s["work_days"]
            total_work    += s["work_min"]
            total_regular += s["regular_min"]
            total_night   += s["late_night_min"]
            total_ot      += s["overtime_min"]
            total_nshift  += s["night_shifts"]
            total_mb      += s["meal_b"]
            total_ml      += s["meal_l"]
            total_md      += s["meal_d"]

        self.lbl_total.config(
            text=(
                f"【全員合計】  出勤: {total_days}日  "
                f"総労働: {minutes_to_hhmm(total_work)}  "
                f"普通: {minutes_to_hhmm(total_regular)}  "
                f"深夜: {minutes_to_hhmm(total_night)}  "
                f"残業: {minutes_to_hhmm(total_ot)}  "
                f"通勤(交通費): {total_nshift}回  "
                f"朝食: {total_mb}回  昼食: {total_ml}回  夕食: {total_md}回"
            )
        )

    def _get_day_records(self, staff_id, y, m, d, is_manager):
        """
        指定した職員・日付のレコードリストを返す。
        管理者は複数スロット対応、一般職員は最大1件。
        """
        if is_manager:
            return self.dm.get_records_for_day(staff_id, y, m, d)
        r = self.dm.get_record(staff_id, y, m, d)
        return [r] if r else []

    def _has_night_record(self, staff_id, y, m, d, is_manager):
        """指定日に夜勤（is_night=True）の記録があるか返す"""
        return any(
            r and r.get("is_night", False)
            for r in self._get_day_records(staff_id, y, m, d, is_manager)
        )

    def _accumulate_records(self, records, result):
        """
        レコードリストを集計結果辞書に加算する。
        day_worked（出勤フラグ）と night_shifts（通勤回数）も返す。
        """
        day_worked    = False
        has_day_shift = False
        night_count   = 0

        for record in records:
            shift_id = record.get("shift_id")
            if not shift_id:
                continue

            shift = self.dm.get_shift_by_id(shift_id)
            if shift and not shift.get("start"):
                # 公休・有給・欠勤など勤務時間なし
                continue

            start_str       = record.get("actual_start", "")
            end_str         = record.get("actual_end",   "")
            break_min       = record.get("actual_break",  60)
            is_night        = record.get("is_night",      False)
            break_start_str = record.get("break_start",   "")

            if not start_str or not end_str:
                continue

            work_min = calc_work_minutes(start_str, end_str, break_min, is_night)
            if work_min <= 0:
                continue

            late_night_min = calc_late_night_minutes(
                start_str, end_str, break_min, is_night,
                break_start_str=break_start_str or None
            )
            overtime_min = calc_overtime_minutes(work_min)

            day_worked = True
            result["work_min"]       += work_min
            result["late_night_min"] += late_night_min
            result["overtime_min"]   += overtime_min
            result["regular_min"]    += max(0, work_min - late_night_min - overtime_min)

            if is_night:
                night_count += 1
            else:
                has_day_shift = True

            if record.get("meal_b"): result["meal_b"] += 1
            if record.get("meal_l"): result["meal_l"] += 1
            if record.get("meal_d"): result["meal_d"] += 1

        return day_worked, has_day_shift, night_count

    def _calc_summary(self, staff_id, year, month):
        """
        指定した職員の期間集計（16日〜翌月15日）を計算して返す。

        【夜勤またぎの扱い】
        ・期間末日（翌月15日）に夜勤がある場合、翌日（翌月16日 = 次期初日）の
          明け分（is_night=False の記録）を今期に含める。
        ・期間初日（16日）の前日（15日）に夜勤がある場合、初日の明け分
          （is_night=False の記録）はスキップする（前期で集計済みのため）。

        引数:
            staff_id: 職員ID
            year, month: 期間の起算年月（この月の16日から翌月15日が対象）
        戻り値:
            集計結果の辞書
        """
        result = {
            "work_days":      0,
            "work_min":       0,
            "regular_min":    0,
            "late_night_min": 0,
            "overtime_min":   0,
            "night_shifts":   0,
            "meal_b":         0,
            "meal_l":         0,
            "meal_d":         0,
        }

        staff_obj  = next((s for s in self.dm.load_staff() if s["id"] == staff_id), {})
        is_manager = staff_obj.get("is_manager", False)

        period_dates = get_period_dates(year, month)
        first_y, first_m, first_d = period_dates[0]   # この月の16日
        last_y,  last_m,  last_d  = period_dates[-1]   # 翌月15日

        # 期間初日（16日）の前日（15日）に夜勤があるか確認
        # → ある場合、初日の明け分（is_night=False）は前期計上済みなのでスキップ
        prev_dt = datetime(first_y, first_m, first_d) - timedelta(days=1)
        night_before_start = self._has_night_record(
            staff_id, prev_dt.year, prev_dt.month, prev_dt.day, is_manager
        )

        # 期間末日（翌月15日）に夜勤があるか確認
        # → ある場合、翌日（翌月16日）の明け分（is_night=False）を今期に追加
        night_on_last = self._has_night_record(
            staff_id, last_y, last_m, last_d, is_manager
        )

        for y, m, d in period_dates:
            day_records = self._get_day_records(staff_id, y, m, d, is_manager)

            # 期間初日で前日夜勤がある場合：
            # is_night=False の記録（明け分）は前期で計上済みなのでスキップ
            if (y, m, d) == (first_y, first_m, first_d) and night_before_start:
                day_records = [r for r in day_records if r and r.get("is_night", False)]

            if not day_records:
                continue

            day_worked, has_day_shift, night_count = self._accumulate_records(
                day_records, result
            )

            if day_worked:
                result["work_days"]   += 1
            result["night_shifts"] += (1 if has_day_shift else 0) + night_count

        # 期間末日に夜勤がある場合：翌日（次期初日）の明け分も今期に追加する
        if night_on_last:
            next_dt = datetime(last_y, last_m, last_d) + timedelta(days=1)
            ny, nm, nd = next_dt.year, next_dt.month, next_dt.day
            ake_records = self._get_day_records(staff_id, ny, nm, nd, is_manager)
            # 明け分 = is_night=False の記録のみ（is_night=True は翌日以降の新たな入り）
            ake_records = [r for r in ake_records if r and not r.get("is_night", False)]

            if ake_records:
                day_worked, has_day_shift, night_count = self._accumulate_records(
                    ake_records, result
                )
                # 明けは夜勤入りと同じ日の出勤としてカウント（出勤日数は加算しない）
                result["night_shifts"] += (1 if has_day_shift else 0) + night_count

        # みなし勤務時間（固定加算分）を総労働・普通就業時間に加える
        # deemed_minutes（分単位）を優先し、古い deemed_hours（時間単位）があればフォールバックする
        if "deemed_minutes" in staff_obj:
            deemed_min = int(staff_obj.get("deemed_minutes", 0))
        else:
            deemed_min = int(staff_obj.get("deemed_hours", 0) * 60)
        if deemed_min > 0:
            result["work_min"]    += deemed_min
            result["regular_min"] += deemed_min

        return result

    def _print_summary(self):
        """
        勤務集計表をHTMLファイルに書き出してブラウザで開く。
        ブラウザの印刷機能（Ctrl+P）でA4縦に印刷できる。
        """
        import webbrowser
        import tempfile
        import html as html_lib

        year       = self.app.current_year.get()
        month      = self.app.current_month.get()
        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")

        # 集計データを取得する
        rows_data     = []
        total_days    = total_work = total_regular = 0
        total_night   = total_ot  = total_nshift   = 0
        total_mb      = total_ml  = total_md        = 0

        for staff in staff_list:
            s = self._calc_summary(staff["id"], year, month)
            rows_data.append((staff["name"], s))
            total_days    += s["work_days"]
            total_work    += s["work_min"]
            total_regular += s["regular_min"]
            total_night   += s["late_night_min"]
            total_ot      += s["overtime_min"]
            total_nshift  += s["night_shifts"]
            total_mb      += s["meal_b"]
            total_ml      += s["meal_l"]
            total_md      += s["meal_d"]

        # テーブル行を生成する
        table_rows = ""
        for i, (name, s) in enumerate(rows_data):
            bg  = "#FFFFFF" if i % 2 == 0 else "#F0F4FA"
            row = (
                f'<tr style="background:{bg}">'
                f'<td class="name">{html_lib.escape(name)}</td>'
                f'<td>{s["work_days"]}日</td>'
                f'<td>{minutes_to_hhmm(s["work_min"])}</td>'
                f'<td>{minutes_to_hhmm(s["regular_min"])}</td>'
                f'<td>{minutes_to_hhmm(s["late_night_min"])}</td>'
                f'<td>{minutes_to_hhmm(s["overtime_min"])}</td>'
                f'<td>{s["night_shifts"]}回</td>'
                f'<td>{s["meal_b"]}回</td>'
                f'<td>{s["meal_l"]}回</td>'
                f'<td>{s["meal_d"]}回</td>'
                f'</tr>\n'
            )
            table_rows += row

        # 合計行
        table_rows += (
            f'<tr class="total">'
            f'<td class="name">【全員合計】</td>'
            f'<td>{total_days}日</td>'
            f'<td>{minutes_to_hhmm(total_work)}</td>'
            f'<td>{minutes_to_hhmm(total_regular)}</td>'
            f'<td>{minutes_to_hhmm(total_night)}</td>'
            f'<td>{minutes_to_hhmm(total_ot)}</td>'
            f'<td>{total_nshift}回</td>'
            f'<td>{total_mb}回</td>'
            f'<td>{total_ml}回</td>'
            f'<td>{total_md}回</td>'
            f'</tr>\n'
        )

        period_label = get_period_label(year, month)

        html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>給与集計 {html_lib.escape(period_label)}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "MS Gothic", "Meiryo UI", monospace; font-size: 11pt; color: #111; }}
  h1 {{ font-size: 15pt; text-align: center; margin-bottom: 5mm; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  th, td {{
    border: 1px solid #888; text-align: center; vertical-align: middle;
    padding: 5px 3px; font-size: 11pt; height: 22pt;
  }}
  th {{ background: #4A6FA5; color: white; font-size: 10pt; white-space: pre-line; height: 36pt; }}
  td.name, th.name {{ text-align: left; padding-left: 6px; width: 36mm; }}
  tr.total {{ background: #E8EEF8 !important; font-weight: bold; border-top: 2px solid #4A6FA5; }}
  .legend {{ margin-top: 5mm; font-size: 9pt; color: #555; line-height: 1.8; }}
  .hint {{ font-size: 10pt; color: #444; text-align: center; margin-top: 5mm;
           border: 1px solid #ccc; padding: 6px; background: #f9f9f9; border-radius: 4px; }}
  @media print {{ body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }} }}
</style>
</head>
<body>
<h1>給与集計表　{html_lib.escape(period_label)}</h1>
<table>
  <thead>
    <tr>
      <th class="name">職員名</th>
      <th>出勤\n日数</th>
      <th>総労働\n時間</th>
      <th>普通就業\n時間</th>
      <th>深夜\n時間</th>
      <th>残業\n時間</th>
      <th>通勤回数\n(交通費)</th>
      <th>朝食\n回数</th>
      <th>昼食\n回数</th>
      <th>夕食\n回数</th>
    </tr>
  </thead>
  <tbody>
{table_rows}
  </tbody>
</table>
<div class="legend">
  【説明】　総労働時間：実労働時間の合計　／　普通就業時間：総労働 − 深夜 − 残業　／　深夜時間：22時〜翌5時　／　残業時間：1日8時間超　／　通勤回数＝交通費支給回数（日勤：出勤日ごと1回・夜勤：1回ずつ）
</div>
<p class="hint">
  📄 PDFとして保存する方法：<strong>Ctrl+P</strong> を押す →「送信先」を <strong>「PDFに保存」</strong> に変更 → 保存ボタンをクリック<br>
  　 印刷する場合：用紙サイズ <strong>A4</strong> ／ 向き <strong>横</strong> を選択してください
</p>
</body>
</html>"""

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False,
            encoding="utf-8", prefix="kintai_summary_"
        ) as f:
            f.write(html_content)
            tmp_path = f.name

        webbrowser.open(f"file:///{tmp_path.replace(os.sep, '/')}")

    def _fill_manager_gaps(self):
        """
        管理者の穴埋め自動入力。
        現在の期間で「早番（朝食帯）」「夕食帯」「夜勤」のいずれかが
        他の職員にカバーされていない日を探し、管理者のスロットに自動入力する。

        カバー判定:
          早番あり  → 他の職員の勤務が 06:30（朝食時刻）を含んでいる
          夕食帯あり → 他の職員の勤務が 18:30（夕食時刻）を含んでいる
          夜勤あり  → 他の職員が is_night=True の記録を持っている
        """
        year      = self.app.current_year.get()
        month     = self.app.current_month.get()
        all_staff = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")
        managers  = [s for s in all_staff if s.get("is_manager")]
        non_mgr   = [s for s in all_staff if not s.get("is_manager")]
        all_shifts = self.dm.load_shifts()

        if not managers:
            messagebox.showwarning(
                "管理者なし",
                "管理者として登録された職員がいません。\n"
                "「職員設定」タブで「管理者」チェックを入れてください。"
            )
            return

        # 穴埋めに使うシフトを種別ごとに探す
        def find_shift(kind):
            """
            kind: 'hayaban'(早番) / 'dinner'(夕食帯) / 'night'(夜勤)
            早番は10:00以降に開始し14:00をカバーするシフト（昼食帯は除外）。
            """
            for s in all_shifts:
                if kind == "night" and s.get("is_night"):
                    return s
                s_min = time_to_minutes(s.get("start", ""))
                e_min = time_to_minutes(s.get("end",   ""))
                if s_min is None or s.get("is_night"):
                    continue
                if kind == "hayaban":
                    # 10:00以降に開始し14:00をカバー（8:00開始の昼食帯は除外）
                    hayaban_check = time_to_minutes("14:00")
                    if s_min >= time_to_minutes("10:00") and s_min <= hayaban_check < (e_min or 0):
                        return s
                if kind == "dinner":
                    dinner = time_to_minutes("18:30")
                    if e_min is not None and s_min <= dinner < e_min:
                        return s
            return None

        hayaban_shift = find_shift("hayaban")
        dinner_shift  = find_shift("dinner")
        night_shift   = find_shift("night")
        filled_count  = 0

        for y, m, d in get_period_dates(year, month):
            # 一般職員のカバー状況を確認する
            has_hayaban = has_dinner = has_night = False
            for staff in non_mgr:
                rec = self.dm.get_record(staff["id"], y, m, d)
                if not rec:
                    continue
                s_str = rec.get("actual_start", "")
                e_str = rec.get("actual_end",   "")
                is_n  = rec.get("is_night",     False)
                if not s_str or not e_str:
                    continue
                s_min = time_to_minutes(s_str)
                e_min = time_to_minutes(e_str)
                if s_min is None or e_min is None:
                    continue
                if is_n and e_min <= s_min:
                    e_min += 24 * 60
                # 15:00をカバーしているか（夕食帯C15:00開始や早番・昼食帯も対象）
                # 15:00基準にすることで、15:00開始の夕食帯がいれば早番不要と判断できる
                if s_min <= time_to_minutes("15:00") < e_min:
                    has_hayaban = True
                if s_min <= time_to_minutes("18:30") < e_min:
                    has_dinner = True
                if is_n:
                    has_night = True

            # 管理者に未カバーのシフトを追加する
            for manager in managers:
                existing   = self.dm.get_records_for_day(manager["id"], y, m, d)
                slot_idx   = len(existing)   # 次の空きスロット番号
                existing_shift_ids = {r.get("shift_id") for r in existing}

                for needed, shift in [
                    (not has_hayaban and hayaban_shift is not None, hayaban_shift),
                    (not has_dinner  and dinner_shift  is not None, dinner_shift),
                    (not has_night   and night_shift   is not None, night_shift),
                ]:
                    if not needed or shift is None:
                        continue
                    if slot_idx >= 3:
                        break
                    # 同じシフトが既に登録されていればスキップ
                    if shift["id"] in existing_shift_ids:
                        continue
                    meals = auto_detect_meals(
                        shift.get("start", ""), shift.get("end", ""),
                        shift.get("is_night", False)
                    )
                    data = {
                        "shift_id":     shift["id"],
                        "actual_start": shift.get("start", ""),
                        "actual_end":   shift.get("end",   ""),
                        "actual_break": shift.get("break_min", 0),
                        "break_start":  shift.get("break_start", ""),
                        "is_night":     shift.get("is_night", False),
                        "meal_b":       meals["meal_b"],
                        "meal_l":       meals["meal_l"],
                        "meal_d":       meals["meal_d"],
                        "memo":         "穴埋め自動入力",
                    }
                    self.dm.set_record_slot(manager["id"], y, m, d, slot_idx, data)
                    existing_shift_ids.add(shift["id"])
                    slot_idx    += 1
                    filled_count += 1

        if filled_count > 0:
            messagebox.showinfo(
                "穴埋め完了",
                f"{filled_count} 件のシフトを管理者に自動入力しました。\n"
                "勤務表タブで内容を確認・修正してください。"
            )
            self.refresh()
        else:
            messagebox.showinfo(
                "穴埋え完了",
                "穴埋めが必要なシフトはありませんでした。\n"
                "（すべての日で早番・夕食帯・夜勤がカバーされています）"
            )

    def _export_csv(self):
        """集計結果をCSVファイルに書き出す"""
        from tkinter import filedialog

        year  = self.app.current_year.get()
        month = self.app.current_month.get()

        filepath = filedialog.asksaveasfilename(
            title="CSV保存先を選択",
            defaultextension=".csv",
            filetypes=[("CSVファイル", "*.csv"), ("すべてのファイル", "*.*")],
            initialfile=f"給与集計_{year}{month:02d}期.csv"
        )
        if not filepath:
            return

        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")

        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "職員名", "出勤日数", "総労働時間", "普通就業時間", "深夜時間",
                    "残業時間", "夜勤回数(交通費)", "朝食回数", "昼食回数", "夕食回数"
                ])
                for staff in staff_list:
                    s = self._calc_summary(staff["id"], year, month)
                    writer.writerow([
                        staff["name"],
                        s["work_days"],
                        minutes_to_hhmm(s["work_min"]),
                        minutes_to_hhmm(s["regular_min"]),
                        minutes_to_hhmm(s["late_night_min"]),
                        minutes_to_hhmm(s["overtime_min"]),
                        s["night_shifts"],
                        s["meal_b"],
                        s["meal_l"],
                        s["meal_d"],
                    ])
            messagebox.showinfo("出力完了", f"CSVを保存しました。\n{filepath}")
        except Exception as e:
            messagebox.showerror("エラー", f"CSVの保存に失敗しました。\n{e}")


# ========================
# シフト設定タブ
# ========================

class ShiftSettingsTab(tk.Frame):
    """シフトパターンの登録・編集・削除を行うタブ"""

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F5F6FA")
        self.app = app
        self.dm  = app.dm
        self._editing_id = None  # 現在編集中のシフトID
        self._build()
        self.refresh()

    def _build(self):
        """ウィジェットを構築する"""

        # ── 左側：シフト一覧 ──
        left = tk.Frame(self, bg="#F5F6FA")
        left.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        tk.Label(left, text="登録済みシフト一覧", font=FONT_BOLD, bg="#F5F6FA").pack(anchor="w")

        cols = [("name", "シフト名", 100), ("abbr", "略称", 55),
                ("start", "開始", 65), ("end", "終了", 65),
                ("break", "休憩(分)", 65), ("is_night", "夜勤", 50)]
        col_ids = [c[0] for c in cols]

        self.tree = ttk.Treeview(left, columns=col_ids, show="headings", height=16)
        for col_id, header, width in cols:
            self.tree.heading(col_id, text=header)
            self.tree.column(col_id, width=width, anchor="center")
        self.tree.column("name", anchor="w")

        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        btn_row = tk.Frame(left, bg="#F5F6FA")
        btn_row.pack(fill="x", pady=5)
        for text, cmd, bg in [
            ("新規追加", self._new,       "#4A6FA5"),
            ("↑ 上へ",  self._move_up,   None),
            ("↓ 下へ",  self._move_down, None),
            ("削除",     self._delete,    "#CC4444"),
        ]:
            kwargs = {"text": text, "font": FONT, "command": cmd,
                      "relief": "flat", "cursor": "hand2", "padx": 8, "pady": 4}
            if bg:
                kwargs["bg"] = bg
                kwargs["fg"] = "white"
            tk.Button(btn_row, **kwargs).pack(side="left", padx=3)

        # ── 右側：編集フォーム ──
        right = tk.LabelFrame(self, text="シフト編集", font=FONT, padx=12, pady=8)
        right.pack(side="right", fill="y", padx=(5, 10), pady=10)

        # テキスト入力フィールド（色はカラーピッカーで別途設定）
        form_fields = [
            ("name",        "シフト名（例: 日勤A）"),
            ("abbr",        "略称・2〜3文字（例: 日A）"),
            ("start",       "開始時刻（例: 09:00）"),
            ("end",         "終了時刻（例: 18:00）"),
            ("break",       "休憩時間（分）（例: 60）"),
            ("break_start", "休憩開始時刻（例: 00:00）"),
        ]
        self.entries = {}
        for i, (key, label) in enumerate(form_fields):
            tk.Label(right, text=label, font=FONT).grid(row=i, column=0, sticky="w", pady=3)
            ent = tk.Entry(right, font=FONT, width=22)
            ent.grid(row=i, column=1, sticky="w", padx=6, pady=3)
            self.entries[key] = ent

        r = len(form_fields)

        # 夜勤チェックボックス
        self.var_night = tk.BooleanVar()
        tk.Checkbutton(
            right, text="夜勤（日またぎ）",
            variable=self.var_night, font=FONT
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))

        # ── カラーピッカー ──
        # ボタン自体の背景色が選択中の色を示す
        r += 1
        tk.Label(right, text="表示色", font=FONT).grid(row=r, column=0, sticky="w", pady=3)
        self._color = "#FFFFFF"   # 現在選択中の色（内部保持）

        color_row = tk.Frame(right)
        color_row.grid(row=r, column=1, sticky="w", padx=6, pady=3)

        # 色見本ラベル（選択した色を四角で表示）
        self.lbl_color_preview = tk.Label(
            color_row, text="　　　　", bg=self._color,
            relief="solid", bd=1, width=6
        )
        self.lbl_color_preview.pack(side="left", padx=(0, 6))

        tk.Button(
            color_row, text="色を選ぶ…", font=FONT,
            command=self._pick_color,
            relief="flat", cursor="hand2", padx=8, pady=2
        ).pack(side="left")

        r += 1
        tk.Button(
            right, text="  保存  ", font=FONT_BOLD,
            command=self._save,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=16, pady=6
        ).grid(row=r, column=0, columnspan=2, pady=12)

    def refresh(self):
        """シフト一覧を最新データで再描画する"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for s in self.dm.load_shifts():
            self.tree.insert("", "end", iid=s["id"], values=(
                s.get("name",      ""),
                s.get("abbr",      ""),
                s.get("start",     ""),
                s.get("end",       ""),
                s.get("break_min", 0),
                "○" if s.get("is_night") else ""
            ))

    def _set_color(self, color_code):
        """内部の色変数とプレビューラベルを同時に更新する"""
        self._color = color_code or "#FFFFFF"
        self.lbl_color_preview.config(bg=self._color)

    def _pick_color(self):
        """カラーピッカーダイアログを開いて色を選択する"""
        # askcolor の戻り値: ((R,G,B), "#RRGGBB") または (None, None)
        result = colorchooser.askcolor(
            color=self._color,
            title="シフトの表示色を選択",
            parent=self
        )
        if result and result[1]:
            self._set_color(result[1])

    def _on_select(self, event):
        """一覧でシフトを選択したとき編集フォームに値を反映する"""
        sel = self.tree.selection()
        if not sel:
            return
        shift = self.dm.get_shift_by_id(sel[0])
        if not shift:
            return

        self._editing_id = shift["id"]
        for key in ("name", "abbr", "start", "end"):
            self.entries[key].delete(0, tk.END)
            self.entries[key].insert(0, shift.get(key, ""))
        self.entries["break"].delete(0, tk.END)
        self.entries["break"].insert(0, str(shift.get("break_min", 0)))
        self.entries["break_start"].delete(0, tk.END)
        self.entries["break_start"].insert(0, shift.get("break_start", ""))
        self.var_night.set(shift.get("is_night", False))
        self._set_color(shift.get("color", "#FFFFFF"))

    def _new(self):
        """新規追加用にフォームをクリアする"""
        self._editing_id = None
        for ent in self.entries.values():
            ent.delete(0, tk.END)
        self._set_color("#FFFFFF")
        self.var_night.set(False)
        self.tree.selection_remove(self.tree.selection())

    def _save(self):
        """フォームの内容でシフトを保存する"""
        name = self.entries["name"].get().strip()
        abbr = self.entries["abbr"].get().strip()
        if not name:
            messagebox.showerror("エラー", "シフト名を入力してください。")
            return
        if not abbr:
            messagebox.showerror("エラー", "略称を入力してください。")
            return

        try:
            break_min = int(self.entries["break"].get().strip() or "0")
        except ValueError:
            messagebox.showerror("エラー", "休憩時間は数字で入力してください。")
            return

        shifts = self.dm.load_shifts()

        if self._editing_id:
            for s in shifts:
                if s["id"] == self._editing_id:
                    s.update({
                        "name":        name,
                        "abbr":        abbr,
                        "start":       self.entries["start"].get().strip(),
                        "end":         self.entries["end"].get().strip(),
                        "break_min":   break_min,
                        "break_start": self.entries["break_start"].get().strip(),
                        "is_night":    self.var_night.get(),
                        "color":       self._color,
                    })
                    break
        else:
            new_id = f"shift_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shifts.append({
                "id":          new_id,
                "name":        name,
                "abbr":        abbr,
                "start":       self.entries["start"].get().strip(),
                "end":         self.entries["end"].get().strip(),
                "break_min":   break_min,
                "break_start": self.entries["break_start"].get().strip(),
                "is_night":    self.var_night.get(),
                "color":       self._color,
            })
            self._editing_id = new_id

        self.dm.save_shifts(shifts)
        self.refresh()
        messagebox.showinfo("保存完了", f"シフト「{name}」を保存しました。")

    def _delete(self):
        """選択中のシフトを削除する"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "削除するシフトを一覧から選択してください。")
            return

        shift = self.dm.get_shift_by_id(sel[0])
        if not shift:
            return

        if messagebox.askyesno(
            "削除の確認",
            f"シフト「{shift['name']}」を削除してよいですか？\n"
            "※ すでにこのシフトで入力済みの記録には影響が出る場合があります。"
        ):
            new_shifts = [s for s in self.dm.load_shifts() if s["id"] != shift["id"]]
            self.dm.save_shifts(new_shifts)
            self._editing_id = None
            self.refresh()

    def _move_up(self):
        """選択したシフトを一つ上に移動する"""
        self._move(-1)

    def _move_down(self):
        """選択したシフトを一つ下に移動する"""
        self._move(1)

    def _move(self, direction):
        """
        シフトの表示順を入れ替える。
        direction: -1=上に移動、1=下に移動
        """
        sel = self.tree.selection()
        if not sel:
            return

        shift_id = sel[0]
        shifts   = self.dm.load_shifts()
        idx      = next((i for i, s in enumerate(shifts) if s["id"] == shift_id), None)
        if idx is None:
            return

        new_idx = idx + direction
        if 0 <= new_idx < len(shifts):
            shifts[idx], shifts[new_idx] = shifts[new_idx], shifts[idx]
            self.dm.save_shifts(shifts)
            self.refresh()
            # 移動後も同じシフトを選択状態に保つ
            self.tree.selection_set(shift_id)
            self.tree.see(shift_id)


# ========================
# 職員設定タブ
# ========================

class StaffSettingsTab(tk.Frame):
    """職員の登録・編集・退職処理・並び順変更を行うタブ"""

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F5F6FA")
        self.app = app
        self.dm  = app.dm
        self._editing_id = None  # 現在編集中の職員ID
        self._build()
        self.refresh()

    def _build(self):
        """ウィジェットを構築する"""

        # ── 左側：職員一覧 ──
        left = tk.Frame(self, bg="#F5F6FA")
        left.pack(side="left", fill="both", expand=True, padx=(10, 5), pady=10)

        tk.Label(left, text="職員一覧", font=FONT_BOLD, bg="#F5F6FA").pack(anchor="w")

        cols = [
            ("no",     "No.",     35),
            ("name",   "氏名",    110),
            ("kana",   "よみがな", 120),
            ("type",   "雇用形態", 80),
            ("weekly", "週所定(h)", 70),
            ("mgr",    "管理者",   50),
            ("status", "状態",    110),
        ]
        col_ids = [c[0] for c in cols]

        self.tree = ttk.Treeview(left, columns=col_ids, show="headings", height=16)
        for col_id, header, width in cols:
            self.tree.heading(col_id, text=header)
            self.tree.column(col_id, width=width, anchor="center")
        self.tree.column("name", anchor="w")
        self.tree.column("kana", anchor="w")

        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        btn_row = tk.Frame(left, bg="#F5F6FA")
        btn_row.pack(fill="x", pady=5)

        for text, cmd, bg in [
            ("新規追加", self._new,        "#4A6FA5"),
            ("↑ 上へ",  self._move_up,    None),
            ("↓ 下へ",  self._move_down,  None),
            ("退職",     self._retire,     "#CC4444"),
            ("復職",     self._unretire,   "#3A9A50"),
        ]:
            kwargs = {"text": text, "font": FONT, "command": cmd,
                      "relief": "flat", "cursor": "hand2",
                      "padx": 8, "pady": 4}
            if bg:
                kwargs["bg"] = bg
                kwargs["fg"] = "white"
            tk.Button(btn_row, **kwargs).pack(side="left", padx=3)

        # ── 右側：編集フォーム ──
        right = tk.LabelFrame(self, text="職員編集", font=FONT, padx=12, pady=8)
        right.pack(side="right", fill="y", padx=(5, 10), pady=10)

        form_fields = [
            ("name", "氏名（例: 田中太郎）"),
            ("kana", "よみがな（例: たなかたろう）"),
        ]
        self.entries = {}
        for i, (key, label) in enumerate(form_fields):
            tk.Label(right, text=label, font=FONT).grid(row=i, column=0, sticky="w", pady=3)
            ent = tk.Entry(right, font=FONT, width=22)
            ent.grid(row=i, column=1, sticky="w", padx=6, pady=3)
            self.entries[key] = ent

        # 雇用形態（ドロップダウン）
        r = len(form_fields)
        tk.Label(right, text="雇用形態", font=FONT).grid(row=r, column=0, sticky="w", pady=3)
        self.cmb_emp = ttk.Combobox(
            right,
            values=["正社員", "パート", "アルバイト"],
            font=FONT, state="readonly", width=12
        )
        self.cmb_emp.current(0)
        self.cmb_emp.grid(row=r, column=1, sticky="w", padx=6, pady=3)

        # 週所定労働時間
        r += 1
        tk.Label(right, text="週所定労働時間（時間）", font=FONT).grid(row=r, column=0, sticky="w", pady=3)
        self.ent_weekly = tk.Entry(right, font=FONT, width=8)
        self.ent_weekly.insert(0, "40")
        self.ent_weekly.grid(row=r, column=1, sticky="w", padx=6, pady=3)

        tk.Label(
            right,
            text="※週所定時間は残業計算の基準になります\n　（正社員40h、パートは契約時間）",
            font=FONT_SMALL, fg="#666666"
        ).grid(row=r+1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # みなし勤務時間
        r += 2
        tk.Label(right, text="みなし勤務時間（分）", font=FONT).grid(row=r, column=0, sticky="w", pady=3)
        self.ent_deemed = tk.Entry(right, font=FONT, width=8)
        self.ent_deemed.insert(0, "0")
        self.ent_deemed.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        tk.Label(
            right,
            text="※集計時に総労働・普通就業時間へ加算されます\n　（みなし残業など固定加算がある場合に設定。例: 30分なら 30）",
            font=FONT_SMALL, fg="#666666"
        ).grid(row=r+1, column=0, columnspan=2, sticky="w", pady=(0, 2))

        # ── 管理者フラグ ──
        r += 2
        self.var_is_manager = tk.BooleanVar()
        tk.Checkbutton(
            right,
            text="管理者（1日3シフト入力可・穴埋め自動入力の対象）",
            variable=self.var_is_manager,
            font=FONT
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 2))

        # ── 担当シフト（勤務入力ボタンに表示するシフトを選択） ──
        r += 1
        frm_shifts = tk.LabelFrame(
            right,
            text="担当シフト（勤務入力画面でボタン表示するシフト）",
            font=FONT_SMALL, padx=6, pady=5
        )
        frm_shifts.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        tk.Label(
            frm_shifts,
            text="☑ チェックしたシフトだけがボタン表示されます\n"
                 "（チェックなし＝全シフト表示）",
            font=FONT_SMALL, fg="#555555", justify="left"
        ).pack(anchor="w")

        # シフトチェックボックスを収めるフレーム
        self.shift_cb_frame = tk.Frame(frm_shifts)
        self.shift_cb_frame.pack(fill="x", pady=(4, 0))
        self.shift_vars = {}   # shift_id -> BooleanVar
        self._rebuild_shift_checkboxes()

        # ── 通常勤務パターン ──
        r += 1
        frm_pattern = tk.LabelFrame(
            right,
            text="通常勤務パターン（毎週同じ曜日に勤務がある場合に設定）",
            font=FONT_SMALL, padx=6, pady=5
        )
        frm_pattern.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        tk.Label(
            frm_pattern,
            text="曜日ごとにデフォルトシフトを設定しておくと、\n"
                 "勤務表タブの「パターン一括入力」で一気に反映できます。",
            font=FONT_SMALL, fg="#555555", justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

        tk.Button(
            frm_pattern,
            text="全曜日を公休に設定",
            font=FONT_SMALL,
            command=self._set_all_pattern_dayoff,
            relief="flat", cursor="hand2",
            bg="#888888", fg="white", padx=8, pady=2
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 4))

        self.pattern_cmb_frame = tk.Frame(frm_pattern)
        self.pattern_cmb_frame.grid(row=2, column=0, columnspan=2, sticky="w")
        self.pattern_cmbs   = {}   # weekday(0-6) -> Combobox
        self._pattern_shifts = []  # 現在のシフトリスト（name→ID変換用）
        self._rebuild_pattern_dropdowns()

        tk.Button(
            right, text="  保存  ", font=FONT_BOLD,
            command=self._save,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=16, pady=6
        ).grid(row=r+1, column=0, columnspan=2, pady=14)

    def _rebuild_shift_checkboxes(self):
        """
        担当シフトのチェックボックスを再構築する。
        シフト設定が変わった場合に備え、refresh時にも呼べるようにしている。
        """
        for w in self.shift_cb_frame.winfo_children():
            w.destroy()
        self.shift_vars = {}

        shifts = self.dm.load_shifts()
        COLS   = 3  # 1行に並べる数

        for i, shift in enumerate(shifts):
            var = tk.BooleanVar()
            tk.Checkbutton(
                self.shift_cb_frame,
                text=shift["name"],
                variable=var,
                font=FONT_SMALL,
                bg=shift.get("color", "#F0F0F0")
            ).grid(row=i // COLS, column=i % COLS, sticky="w", padx=4, pady=1)
            self.shift_vars[shift["id"]] = var

    def _set_all_pattern_dayoff(self):
        """全曜日のパターンを公休に一括設定する"""
        dayoff_name = next(
            (s["name"] for s in self._pattern_shifts if not s.get("start")),
            None
        )
        if not dayoff_name:
            messagebox.showwarning("公休なし", "公休シフトが見つかりません。")
            return
        for cmb in self.pattern_cmbs.values():
            if dayoff_name in cmb["values"]:
                cmb.set(dayoff_name)

    def _rebuild_pattern_dropdowns(self):
        """
        曜日パターン用のドロップダウンを再構築する。
        シフト設定が変わったときや画面リフレッシュ時に呼び出す。
        """
        for w in self.pattern_cmb_frame.winfo_children():
            w.destroy()
        self.pattern_cmbs    = {}
        self._pattern_shifts = self.dm.load_shifts()
        shift_names          = ["なし"] + [s["name"] for s in self._pattern_shifts]

        for weekday_idx in range(7):
            day_label = WEEKDAY_JP[weekday_idx] + "曜"
            tk.Label(
                self.pattern_cmb_frame,
                text=day_label, font=FONT_SMALL, width=4, anchor="e"
            ).grid(row=weekday_idx, column=0, sticky="e", padx=(0, 4), pady=1)

            cmb = ttk.Combobox(
                self.pattern_cmb_frame,
                values=shift_names,
                font=FONT_SMALL,
                state="readonly",
                width=14
            )
            cmb.current(0)   # デフォルトは「なし」
            cmb.grid(row=weekday_idx, column=1, sticky="w", pady=1)
            self.pattern_cmbs[weekday_idx] = cmb

    def refresh(self):
        """職員一覧を最新データで再描画する"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 退職者行をグレーで表示するタグを設定する
        self.tree.tag_configure("retired", foreground="#999999", background="#F0F0F0")

        for i, s in enumerate(self.dm.load_staff(), 1):
            is_retired = s.get("retired", False)
            tag = ("retired",) if is_retired else ()

            # 退職日があれば「退職 YYYY/MM/DD」と表示する
            if is_retired:
                rd = s.get("retirement_date", "")
                if rd:
                    try:
                        rd_disp = datetime.strptime(rd, "%Y-%m-%d").strftime("%Y/%m/%d")
                    except ValueError:
                        rd_disp = rd
                    status_text = f"退職 {rd_disp}"
                else:
                    status_text = "退職"
            else:
                status_text = "在職"

            self.tree.insert("", "end", iid=s["id"], values=(
                i,
                s.get("name", ""),
                s.get("kana", ""),
                s.get("employment_type", "正社員"),
                s.get("weekly_hours", 40),
                "★" if s.get("is_manager") else "",
                status_text,
            ), tags=tag)

        # シフト設定が変わっている可能性があるので両方再構築する
        self._rebuild_shift_checkboxes()
        self._rebuild_pattern_dropdowns()

    def _on_select(self, event):
        """一覧で職員を選択したとき編集フォームに値を反映する"""
        sel = self.tree.selection()
        if not sel:
            return
        staff_id   = sel[0]
        staff_list = self.dm.load_staff()
        staff      = next((s for s in staff_list if s["id"] == staff_id), None)
        if not staff:
            return

        self._editing_id = staff_id

        self.entries["name"].delete(0, tk.END)
        self.entries["name"].insert(0, staff.get("name", ""))
        self.entries["kana"].delete(0, tk.END)
        self.entries["kana"].insert(0, staff.get("kana", ""))

        emp_types = ["正社員", "パート", "アルバイト"]
        emp       = staff.get("employment_type", "正社員")
        self.cmb_emp.current(emp_types.index(emp) if emp in emp_types else 0)

        self.ent_weekly.delete(0, tk.END)
        self.ent_weekly.insert(0, str(staff.get("weekly_hours", 40)))
        self.ent_deemed.delete(0, tk.END)
        # deemed_minutes（分）優先、古い deemed_hours（時間）は分に変換して表示する
        if "deemed_minutes" in staff:
            self.ent_deemed.insert(0, str(staff.get("deemed_minutes", 0)))
        else:
            old_hours = staff.get("deemed_hours", 0)
            self.ent_deemed.insert(0, str(int(old_hours * 60)))
        self.var_is_manager.set(staff.get("is_manager", False))

        # 担当シフトのチェック状態を復元する
        assigned = staff.get("assigned_shifts", [])
        for sid, var in self.shift_vars.items():
            var.set(sid in assigned)

        # 曜日パターンを復元する
        pattern = staff.get("weekly_pattern", {})
        shift_name_map = {s["id"]: s["name"] for s in self._pattern_shifts}
        for weekday_idx, cmb in self.pattern_cmbs.items():
            shift_id = pattern.get(str(weekday_idx), "")
            shift_name = shift_name_map.get(shift_id, "")
            if shift_name and shift_name in cmb["values"]:
                cmb.set(shift_name)
            else:
                cmb.current(0)  # なし

    def _new(self):
        """新規追加用にフォームをクリアする"""
        self._editing_id = None
        for ent in self.entries.values():
            ent.delete(0, tk.END)
        self.cmb_emp.current(0)
        self.ent_weekly.delete(0, tk.END)
        self.ent_weekly.insert(0, "40")
        self.ent_deemed.delete(0, tk.END)
        self.ent_deemed.insert(0, "0")  # 分単位でリセット
        # 担当シフトをすべて未チェックにする
        for var in self.shift_vars.values():
            var.set(False)
        self.var_is_manager.set(False)
        # 曜日パターンをすべてなしにする
        for cmb in self.pattern_cmbs.values():
            cmb.current(0)
        self.tree.selection_remove(self.tree.selection())

    def _save(self):
        """フォームの内容で職員情報を保存する"""
        name = self.entries["name"].get().strip()
        if not name:
            messagebox.showerror("エラー", "氏名を入力してください。")
            return

        try:
            weekly_hours = float(self.ent_weekly.get().strip() or "40")
        except ValueError:
            messagebox.showerror("エラー", "週所定労働時間は数字で入力してください（例: 40）。")
            return

        try:
            deemed_minutes = int(self.ent_deemed.get().strip() or "0")
            if deemed_minutes < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("エラー", "みなし勤務時間は0以上の整数（分）で入力してください（例: 30）。")
            return

        # チェックされた担当シフトIDのリストを取得する
        assigned_shifts = [sid for sid, var in self.shift_vars.items() if var.get()]

        # 曜日パターンを収集する（シフト名 → シフトIDに変換）
        shift_id_map   = {s["name"]: s["id"] for s in self._pattern_shifts}
        weekly_pattern = {}
        for weekday_idx, cmb in self.pattern_cmbs.items():
            selected = cmb.get()
            weekly_pattern[str(weekday_idx)] = shift_id_map.get(selected, "")

        staff_list = self.dm.load_staff()

        if self._editing_id:
            # 既存職員の情報を更新する
            for s in staff_list:
                if s["id"] == self._editing_id:
                    s.update({
                        "name":            name,
                        "kana":            self.entries["kana"].get().strip(),
                        "employment_type": self.cmb_emp.get(),
                        "weekly_hours":    weekly_hours,
                        "deemed_minutes":  deemed_minutes,
                        "assigned_shifts": assigned_shifts,
                        "is_manager":      self.var_is_manager.get(),
                        "weekly_pattern":  weekly_pattern,
                    })
                    break
        else:
            # 新規職員を追加する（IDは現在時刻から自動生成）
            new_id = f"S{datetime.now().strftime('%Y%m%d%H%M%S')}"
            staff_list.append({
                "id":              new_id,
                "name":            name,
                "kana":            self.entries["kana"].get().strip(),
                "employment_type": self.cmb_emp.get(),
                "weekly_hours":    weekly_hours,
                "deemed_minutes":  deemed_minutes,
                "assigned_shifts": assigned_shifts,
                "is_manager":      self.var_is_manager.get(),
                "weekly_pattern":  weekly_pattern,
            })
            self._editing_id = new_id

        self.dm.save_staff(staff_list)
        self.refresh()
        messagebox.showinfo("保存完了", f"職員「{name}」を保存しました。")

    def _retire(self):
        """選択中の職員を退職扱いにする。退職日を入力させてから保存する。"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "退職にする職員を一覧から選択してください。")
            return

        staff_id   = sel[0]
        staff_list = self.dm.load_staff()
        staff      = next((s for s in staff_list if s["id"] == staff_id), None)
        if not staff:
            return

        if staff.get("retired", False):
            messagebox.showinfo("確認", f"「{staff['name']}」はすでに退職扱いです。")
            return

        # 退職日を入力させるダイアログを表示する
        retirement_date = self._ask_retirement_date(staff["name"])
        if retirement_date is None:
            return  # キャンセル

        for s in staff_list:
            if s["id"] == staff_id:
                s["retired"]         = True
                s["retirement_date"] = retirement_date
                break
        self.dm.save_staff(staff_list)
        self.refresh()
        messagebox.showinfo(
            "退職処理完了",
            f"「{staff['name']}」を退職扱いにしました。\n退職日：{retirement_date}"
        )

    def _ask_retirement_date(self, staff_name):
        """
        退職日を入力するダイアログを表示して、入力された日付文字列を返す。
        キャンセルされた場合は None を返す。
        戻り値: "YYYY-MM-DD" 形式の文字列、またはNone
        """
        dlg = tk.Toplevel(self)
        dlg.title("退職日の入力")
        dlg.resizable(False, False)
        dlg.grab_set()

        # ダイアログを画面中央に配置する
        dlg.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width()  // 2 - 160
        y = self.winfo_rooty() + self.winfo_height() // 2 - 80
        dlg.geometry(f"320x160+{x}+{y}")

        tk.Label(dlg, text=f"「{staff_name}」の退職日を入力してください",
                 font=FONT, wraplength=290, justify="left").pack(padx=16, pady=(14, 4))
        tk.Label(dlg, text="形式：YYYY/MM/DD（例：2026/04/30）",
                 font=FONT_SMALL, fg="#666666").pack(padx=16, anchor="w")

        ent = tk.Entry(dlg, font=FONT, width=16)
        # 今日の日付を初期値として入れる
        ent.insert(0, datetime.now().strftime("%Y/%m/%d"))
        ent.pack(padx=16, pady=8)
        ent.select_range(0, tk.END)
        ent.focus_set()

        result = [None]  # クロージャ経由で結果を受け取る

        def on_ok():
            raw = ent.get().strip().replace("／", "/")
            # YYYY/MM/DD → YYYY-MM-DD に変換して検証する
            try:
                dt = datetime.strptime(raw, "%Y/%m/%d")
                result[0] = dt.strftime("%Y-%m-%d")
                dlg.destroy()
            except ValueError:
                messagebox.showerror(
                    "入力エラー", "日付の形式が正しくありません。\n例：2026/04/30",
                    parent=dlg
                )

        def on_cancel():
            dlg.destroy()

        btn_frm = tk.Frame(dlg)
        btn_frm.pack(pady=4)
        tk.Button(btn_frm, text="OK",      font=FONT, bg="#4A6FA5", fg="white",
                  relief="flat", cursor="hand2", padx=16,
                  command=on_ok).pack(side="left", padx=6)
        tk.Button(btn_frm, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2", padx=10,
                  command=on_cancel).pack(side="left", padx=6)

        ent.bind("<Return>", lambda e: on_ok())
        dlg.wait_window()
        return result[0]

    def _unretire(self):
        """選択中の退職職員を在職に戻す（復職）"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "復職させる職員を一覧から選択してください。")
            return

        staff_id   = sel[0]
        staff_list = self.dm.load_staff()
        staff      = next((s for s in staff_list if s["id"] == staff_id), None)
        if not staff:
            return

        if not staff.get("retired", False):
            messagebox.showinfo("確認", f"「{staff['name']}」はすでに在職中です。")
            return

        if messagebox.askyesno(
            "復職の確認",
            f"職員「{staff['name']}」を在職に戻してよいですか？"
        ):
            for s in staff_list:
                if s["id"] == staff_id:
                    s["retired"]         = False
                    s["retirement_date"] = ""  # 退職日もクリアする
                    break
            self.dm.save_staff(staff_list)
            self.refresh()

    def _move_up(self):
        """選択した職員を一つ上（先）に移動する"""
        self._move(-1)

    def _move_down(self):
        """選択した職員を一つ下（後）に移動する"""
        self._move(1)

    def _move(self, direction):
        """
        職員の表示順を入れ替える。
        direction: -1=上に移動、1=下に移動
        """
        sel = self.tree.selection()
        if not sel:
            return

        staff_id   = sel[0]
        staff_list = self.dm.load_staff()
        idx        = next((i for i, s in enumerate(staff_list) if s["id"] == staff_id), None)
        if idx is None:
            return

        new_idx = idx + direction
        if 0 <= new_idx < len(staff_list):
            # 入れ替えて保存する
            staff_list[idx], staff_list[new_idx] = staff_list[new_idx], staff_list[idx]
            self.dm.save_staff(staff_list)
            self.refresh()
            # 移動した職員を選択状態に戻す
            self.tree.selection_set(staff_id)
            self.tree.see(staff_id)


# ========================
# 予定タブ
# ========================

class YoteiTab(tk.Frame):
    """
    月次の予定メモを入力・管理するタブ。
    カレンダー月（1日〜月末）の各日付に対して自由記載のメモを入力できる。
    データは yotei.json に保存される。
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F7F9FC")
        self.app = app
        self.dm  = app.dm

        # 各日付の入力欄を保持する辞書 {"年_月_日": Text widget}
        self._entries = {}
        # 最後に保存した内容（変更検知用）
        self._last_saved = {}

        self._build()

    def _build(self):
        """タブのUIを構築する"""
        # タイトルバー
        top = tk.Frame(self, bg="#4A6FA5")
        top.pack(fill="x")
        tk.Label(
            top, text="月次予定メモ",
            font=FONT_BOLD, bg="#4A6FA5", fg="white",
            padx=10, pady=6
        ).pack(side="left")

        # 保存ボタン
        tk.Button(
            top, text="保存", font=FONT_SMALL,
            bg="#2ecc71", fg="white",
            relief="flat", cursor="hand2", padx=10,
            command=self._save_all
        ).pack(side="right", padx=8, pady=4)

        # 休み自動入力ボタン（水・木曜日に「すみか休み」を一括入力）
        tk.Button(
            top, text="休み自動入力", font=FONT_SMALL,
            bg="#E08030", fg="white",
            relief="flat", cursor="hand2", padx=10,
            command=self._fill_yasumi
        ).pack(side="right", padx=4, pady=4)

        # 通院予定読み込みボタン（visits.db から next_visit_date を取得して入力）
        tk.Button(
            top, text="通院予定を読み込む", font=FONT_SMALL,
            bg="#2E7D6E", fg="white",
            relief="flat", cursor="hand2", padx=10,
            command=self._load_visits
        ).pack(side="right", padx=4, pady=4)

        # ── 月移動コントロールバー ──
        ctrl = tk.Frame(self, bg="#F7F9FC", pady=4)
        ctrl.pack(fill="x", padx=10)

        tk.Button(
            ctrl, text="◀ 前月", font=FONT,
            command=self._prev_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        self.lbl_yearmonth = tk.Label(
            ctrl, text="", font=FONT_BOLD, bg="#F7F9FC", width=14
        )
        self.lbl_yearmonth.pack(side="left", padx=8)

        tk.Button(
            ctrl, text="翌月 ▶", font=FONT,
            command=self._next_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        tk.Button(
            ctrl, text="今月", font=FONT,
            command=self._goto_today,
            relief="flat", cursor="hand2", padx=10, pady=3
        ).pack(side="left", padx=12)

        # スクロール可能なメインエリア
        container = tk.Frame(self, bg="#F7F9FC")
        container.pack(fill="both", expand=True, padx=10, pady=8)

        canvas = tk.Canvas(container, bg="#F7F9FC", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self._scroll_frame = tk.Frame(canvas, bg="#F7F9FC")

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # マウスホイールでスクロールできるようにする
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>",
            lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units")))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        self._canvas = canvas
        self._build_date_rows()

    def _build_date_rows(self):
        """現在の月（カレンダー月）の日付ごとに入力行を作成する"""
        # 既存の行を削除
        for w in self._scroll_frame.winfo_children():
            w.destroy()
        self._entries.clear()

        year     = self.app.current_year.get()
        month    = self.app.current_month.get()
        period   = get_month_dates(year, month)
        notes    = self.dm.get_yotei_for_month(year, month)
        holidays = get_japan_holidays(year)

        # ヘッダー行
        hdr = tk.Frame(self._scroll_frame, bg="#4A6FA5")
        hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hdr, text="日付", width=10, anchor="center",
                 font=FONT_BOLD, bg="#4A6FA5", fg="white").pack(side="left", padx=(4, 6), pady=3)
        for col_id, col_label, col_width, is_last in YOTEI_COLS:
            # すみか休み列はオレンジ系で他と区別する
            bg = "#C05000" if col_id == "sumika" else "#4A6FA5"
            lbl = tk.Label(hdr, text=col_label, width=col_width, anchor="center",
                           font=FONT_BOLD, bg=bg, fg="white")
            if is_last:
                lbl.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=3)
            else:
                lbl.pack(side="left", padx=(0, 2), pady=3)

        for i, (y, m, d) in enumerate(period):
            row_bg     = "#FFFFFF" if i % 2 == 0 else "#F0F4FA"
            weekday    = datetime(y, m, d).weekday()
            is_holiday = (m, d) in holidays

            if weekday == 6 or is_holiday:
                date_label_bg = "#FFE0E0"
            elif weekday == 5:
                date_label_bg = "#E0E8FF"
            else:
                date_label_bg = row_bg

            row = tk.Frame(self._scroll_frame, bg=row_bg, pady=2)
            row.pack(fill="x", pady=1)

            # 日付ラベル
            wd_jp    = WEEKDAY_JP[weekday]
            date_str = f"{m}/{d}（{wd_jp}）"
            tk.Label(
                row, text=date_str, width=10, anchor="center",
                font=FONT_SMALL, bg=date_label_bg, relief="groove"
            ).pack(side="left", padx=(0, 6), ipady=3)

            # 保存済みデータを読み込む（旧形式の文字列も自動変換）
            key      = f"{y}_{m:02d}_{d:02d}"
            raw      = notes.get(key, {})
            if isinstance(raw, str):
                # 旧形式：文字列をすみか列 or col1 列に振り分ける
                saved = {"sumika": raw} if raw == "すみか休み" else {"col1": raw}
            else:
                saved = raw

            col_entries = {}
            for col_id, col_label, col_width, is_last in YOTEI_COLS:
                bg = "#FFF5EE" if col_id == "sumika" else "white"
                ent = tk.Entry(row, font=FONT_SMALL, bg=bg,
                               relief="solid", bd=1, width=col_width)
                ent.insert(0, saved.get(col_id, ""))
                ent.bind("<FocusOut>", lambda e: self._save_all())
                if is_last:
                    ent.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 4))
                else:
                    ent.pack(side="left", ipady=3, padx=(0, 2))
                col_entries[col_id] = ent

            self._entries[key] = col_entries

    def _prev_month(self):
        """前の月を表示する"""
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 1:
            self.app.current_year.set(y - 1)
            self.app.current_month.set(12)
        else:
            self.app.current_month.set(m - 1)
        self.refresh()

    def _next_month(self):
        """次の月を表示する"""
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 12:
            self.app.current_year.set(y + 1)
            self.app.current_month.set(1)
        else:
            self.app.current_month.set(m + 1)
        self.refresh()

    def _goto_today(self):
        """今月（今日が属するカレンダー月）を表示する"""
        py, pm = current_month_view()
        self.app.current_year.set(py)
        self.app.current_month.set(pm)
        self.refresh()

    def _fill_yasumi(self):
        """
        水曜日・木曜日の「すみか休み」専用列に「すみか休み」を一括入力して保存する。
        すでに文字が入力されている場合は上書きする。
        """
        year   = self.app.current_year.get()
        month  = self.app.current_month.get()
        period = get_month_dates(year, month)

        for (y, m, d) in period:
            weekday = datetime(y, m, d).weekday()
            # 水曜=2、木曜=3 のみ対象
            if weekday in (2, 3):
                key         = f"{y}_{m:02d}_{d:02d}"
                col_entries = self._entries.get(key)
                if col_entries:
                    ent = col_entries.get("sumika")
                    if ent is not None:
                        ent.delete(0, "end")
                        ent.insert(0, "すみか休み")

        # 入力後すぐ保存する
        self._save_all()

    def _load_visits(self):
        """
        visits.db から表示中の月の next_visit_date を読み込み、
        各日付の予定①・予定②列に「入居者名 病院名（時間）」形式で入力する。
        予定①が埋まっていれば予定②に、両方埋まっていればスキップする。
        """
        if not os.path.exists(VISIT_DB):
            messagebox.showwarning(
                "通院記録DB未検出",
                f"通院記録DBが見つかりません。\n{VISIT_DB}"
            )
            return
        if not os.path.exists(RESIDENTS_DB):
            messagebox.showwarning(
                "入居者DB未検出",
                f"入居者DBが見つかりません。\n{RESIDENTS_DB}"
            )
            return

        year     = self.app.current_year.get()
        month    = self.app.current_month.get()
        last_day = calendar.monthrange(year, month)[1]
        from_date = f"{year}-{month:02d}-01"
        to_date   = f"{year}-{month:02d}-{last_day:02d}"

        try:
            # 入居者名マスター（id → 氏名）
            conn_r = sqlite3.connect(RESIDENTS_DB)
            conn_r.row_factory = sqlite3.Row
            resident_names = {}
            for row in conn_r.execute("SELECT id, name FROM residents"):
                resident_names[row["id"]] = row["name"]
            conn_r.close()

            # 対象月の通院予定を取得
            conn_v = sqlite3.connect(VISIT_DB)
            conn_v.row_factory = sqlite3.Row
            cur = conn_v.cursor()
            cur.execute("""
                SELECT v.resident_id,
                       v.next_visit_date,
                       v.next_appointment_time,
                       h.name       AS hospital_name,
                       h.department AS department
                FROM   visits v
                JOIN   hospitals h ON v.hospital_id = h.id
                WHERE  v.next_visit_date BETWEEN ? AND ?
                ORDER  BY v.next_visit_date, v.resident_id
            """, (from_date, to_date))
            rows = cur.fetchall()
            conn_v.close()

        except Exception as e:
            messagebox.showerror("DB読み込みエラー", str(e))
            return

        if not rows:
            messagebox.showinfo(
                "通院予定なし",
                f"{year}年{month}月の通院予定データが見つかりませんでした。"
            )
            return

        # 日付ごとに表示テキストをまとめる
        day_visits = defaultdict(list)
        for row in rows:
            d = int(row["next_visit_date"][8:10])
            name     = resident_names.get(row["resident_id"], "不明")
            hospital = row["hospital_name"] or ""
            dept     = row["department"]    or ""
            time_str = row["next_appointment_time"] or ""

            # 「田中花子 △△病院内科（13:30）」の形式で組み立てる
            label = name
            if hospital:
                label += f" {hospital}"
                if dept:
                    label += dept
            if time_str:
                label += f"（{time_str}）"

            day_visits[d].append(label)

        # 各日付の入力欄（予定①→予定②の順）に書き込む
        filled  = 0
        skipped = 0
        for d, labels in day_visits.items():
            key         = f"{year}_{month:02d}_{d:02d}"
            col_entries = self._entries.get(key)
            if col_entries is None:
                continue
            for label in labels:
                wrote = False
                for col_id in ("col1", "col2"):
                    ent = col_entries.get(col_id)
                    if ent is not None and not ent.get().strip():
                        ent.delete(0, "end")
                        ent.insert(0, label)
                        filled  += 1
                        wrote    = True
                        break
                if not wrote:
                    skipped += 1

        self._save_all()

        msg = f"{filled} 件の通院予定を読み込みました。"
        if skipped:
            msg += f"\n（{skipped} 件は予定①②がすでに入力済みのためスキップしました）"
        messagebox.showinfo("読み込み完了", msg)

    def _save_all(self):
        """全日付のメモを一括保存する（4列分をdict形式で保存）"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()

        period_notes = {}
        for key, col_entries in self._entries.items():
            col_data = {}
            for col_id, ent in col_entries.items():
                text = ent.get().strip()
                if text:
                    col_data[col_id] = text
            if col_data:
                period_notes[key] = col_data

        self.dm.save_yotei_for_month(year, month, period_notes)

    def refresh(self):
        """タブが選択されたときに表示を更新する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        self.lbl_yearmonth.config(text=f"{year}年 {month}月")
        self._build_date_rows()


# ========================
# タイムカード照合タブ
# ========================

class TimecardTab(tk.Frame):
    """
    タイムカード照合タブ。
    職員を選択すると、その月の日別出退勤時刻・実労働時間を一覧表示する。
    """

    def __init__(self, parent, app):
        super().__init__(parent, bg="#F5F6FA")
        self.app = app
        self.dm  = app.dm
        self._build()
        self.refresh()

    def _build(self):
        """ウィジェットを構築する"""

        # ── 上部コントロールバー ──
        ctrl = tk.Frame(self, bg="#F5F6FA", pady=6)
        ctrl.pack(fill="x", padx=10)

        tk.Button(
            ctrl, text="◀ 前期", font=FONT,
            command=self._prev_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        self.lbl_yearmonth = tk.Label(
            ctrl, text="", font=FONT_BOLD, bg="#F5F6FA", width=22
        )
        self.lbl_yearmonth.pack(side="left", padx=8)

        tk.Button(
            ctrl, text="翌期 ▶", font=FONT,
            command=self._next_month,
            relief="flat", cursor="hand2",
            bg="#4A6FA5", fg="white", padx=10, pady=3
        ).pack(side="left")

        tk.Button(
            ctrl, text="今期", font=FONT,
            command=self._goto_today,
            relief="flat", cursor="hand2", padx=10, pady=3
        ).pack(side="left", padx=12)

        # 職員選択コンボボックス＋前後ボタン
        tk.Label(
            ctrl, text="職員：", font=FONT, bg="#F5F6FA"
        ).pack(side="left", padx=(20, 4))

        tk.Button(
            ctrl, text="◀", font=FONT,
            command=self._prev_staff,
            relief="flat", cursor="hand2",
            bg="#7A9CC8", fg="white", padx=6, pady=3
        ).pack(side="left")

        self.staff_var   = tk.StringVar()
        self.staff_combo = ttk.Combobox(
            ctrl, textvariable=self.staff_var,
            font=FONT, state="readonly", width=16
        )
        self.staff_combo.pack(side="left", padx=2)
        self.staff_combo.bind("<<ComboboxSelected>>", lambda e: self._show_timecard())

        tk.Button(
            ctrl, text="▶", font=FONT,
            command=self._next_staff,
            relief="flat", cursor="hand2",
            bg="#7A9CC8", fg="white", padx=6, pady=3
        ).pack(side="left")

        tk.Button(
            ctrl, text="編集", font=FONT,
            command=self._edit_selected_row,
            relief="flat", cursor="hand2",
            bg="#5A8A5A", fg="white", padx=10, pady=3
        ).pack(side="left", padx=(16, 0))

        tk.Label(
            ctrl, text="（行をダブルクリックでも編集できます）",
            font=FONT_SMALL, fg="#666666", bg="#F5F6FA"
        ).pack(side="left", padx=(8, 0))

        # ── 一覧テーブル ──
        # 列定義：（列ID、ヘッダー、幅）
        columns_def = [
            ("date",    "日付",       70),
            ("weekday", "曜日",       40),
            ("shift",   "シフト名", 90),
            ("start",   "出勤",       70),
            ("end",     "退勤",       70),
            ("work",    "実労働時間", 90),
            ("memo",    "備考",      160),
        ]
        col_ids = [c[0] for c in columns_def]

        tree_frame = tk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(
            tree_frame, columns=col_ids, show="headings", height=24
        )
        for col_id, header, width in columns_def:
            self.tree.heading(col_id, text=header)
            self.tree.column(col_id, width=width, anchor="center", minwidth=40)
        # 左揃えにする列
        self.tree.column("shift", anchor="w")
        self.tree.column("memo",  anchor="w")

        v_sb = ttk.Scrollbar(tree_frame, orient="vertical",   command=self.tree.yview)
        h_sb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_sb.set, xscrollcommand=h_sb.set)

        v_sb.pack(side="right",  fill="y")
        h_sb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        # ダブルクリックで編集ダイアログを開く
        self.tree.bind("<Double-1>", lambda e: self._edit_selected_row())

        # 行の色設定
        self.tree.tag_configure("even",    background="#FFFFFF")
        self.tree.tag_configure("odd",     background="#F0F4FA")
        self.tree.tag_configure("holiday", background="#FFE0E0")  # 日曜
        self.tree.tag_configure("sat",     background="#E0E8FF")  # 土曜

        # ── 合計ラベル ──
        self.lbl_total = tk.Label(
            self, text="", font=FONT_SMALL,
            bg="#E8EEF8", anchor="w", padx=10, pady=4
        )
        self.lbl_total.pack(fill="x", padx=10, pady=(0, 5))

    # ── 月移動 ──────────────────────────────────────────

    def _prev_month(self):
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 1:
            self.app.current_year.set(y - 1)
            self.app.current_month.set(12)
        else:
            self.app.current_month.set(m - 1)
        self.refresh()

    def _next_month(self):
        y, m = self.app.current_year.get(), self.app.current_month.get()
        if m == 12:
            self.app.current_year.set(y + 1)
            self.app.current_month.set(1)
        else:
            self.app.current_month.set(m + 1)
        self.refresh()

    def _goto_today(self):
        py, pm = current_period()
        self.app.current_year.set(py)
        self.app.current_month.set(pm)
        self.refresh()

    def _prev_staff(self):
        """コンボボックスの一つ前の職員に切り替える"""
        names = list(self.staff_combo["values"])
        if not names:
            return
        current = self.staff_var.get()
        idx = names.index(current) if current in names else 0
        # 先頭の場合は末尾に循環する
        new_idx = (idx - 1) % len(names)
        self.staff_var.set(names[new_idx])
        self._show_timecard()

    def _next_staff(self):
        """コンボボックスの一つ後の職員に切り替える"""
        names = list(self.staff_combo["values"])
        if not names:
            return
        current = self.staff_var.get()
        idx = names.index(current) if current in names else 0
        # 末尾の場合は先頭に循環する
        new_idx = (idx + 1) % len(names)
        self.staff_var.set(names[new_idx])
        self._show_timecard()

    def _edit_selected_row(self):
        """選択中の行の日付でシフト編集ダイアログを開く"""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("編集", "編集したい行をクリックして選択してください。")
            return

        date_tuple = self._row_date_map.get(sel[0])
        if not date_tuple:
            return

        self._open_edit_dialog(date_tuple)

    def _open_edit_dialog(self, date_tuple):
        """指定日のシフト編集ダイアログを開く。管理者は専用ダイアログを使用する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        sel_name = self.staff_var.get()

        # 職員オブジェクトを取得する
        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")
        staff = next((s for s in staff_list if s["name"] == sel_name), None)
        if not staff:
            return

        # 最新のスタッフ情報を再読み込みする（設定変更直後でも正しく反映されるように）
        fresh_staff = next(
            (s for s in self.dm.load_staff() if s["id"] == staff["id"]),
            staff
        )

        period_dates = get_period_dates(year, month)

        # 管理者フラグがある職員はマルチスロットダイアログを開く
        if fresh_staff.get("is_manager"):
            dlg = ManagerShiftEditDialog(self, self.app, fresh_staff, date_tuple, period_dates)
        else:
            dlg = ShiftEditDialog(self, self.app, fresh_staff, date_tuple, period_dates)
        self.wait_window(dlg)
        self.refresh()

    # ── 表示更新 ─────────────────────────────────────────

    def refresh(self):
        """タブが選択されたときに表示を更新する"""
        year  = self.app.current_year.get()
        month = self.app.current_month.get()
        self.lbl_yearmonth.config(text=get_period_label(year, month))

        # 職員一覧をコンボボックスに反映する（退職者は除外）
        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")
        names = [s["name"] for s in staff_list]
        self.staff_combo["values"] = names

        # 現在選択中の職員が削除されていたら先頭の職員を選択する
        if self.staff_var.get() not in names:
            self.staff_var.set(names[0] if names else "")

        self._show_timecard()

    def _show_timecard(self):
        """
        選択された職員の給与期間（16日〜翌月15日）の日別出退勤時刻を一覧表示する。
        管理者は複数スロットに対応し、1日で複数行になる場合がある。
        """
        # テーブルをクリアする
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.lbl_total.config(text="")

        # 行ID → 日付タプル のマッピング（編集ダイアログ起動に使用）
        self._row_date_map = {}

        year       = self.app.current_year.get()
        month      = self.app.current_month.get()
        staff_list = self.dm.load_active_staff(f"{year}-{month:02d}-{PERIOD_START_DAY:02d}")
        sel_name   = self.staff_var.get()
        staff      = next((s for s in staff_list if s["name"] == sel_name), None)

        if not staff:
            return

        is_manager     = staff.get("is_manager", False)
        total_work_min = 0
        work_days      = 0

        for i, (y, m, d) in enumerate(get_period_dates(year, month)):
            # その日の記録を取得する
            if is_manager:
                day_records = self.dm.get_records_for_day(staff["id"], y, m, d)
            else:
                r = self.dm.get_record(staff["id"], y, m, d)
                day_records = [r] if r else []

            wd     = datetime(y, m, d).weekday()   # 0=月曜 … 6=日曜
            wd_str = WEEKDAY_JP[wd]

            # 日付表示文字列（2行目以降は空にして見やすくする）
            date_str = f"{m}/{d}"

            # 曜日による行の色タグを決定する
            if wd == 6:
                row_tag = "holiday"
            elif wd == 5:
                row_tag = "sat"
            elif i % 2 == 0:
                row_tag = "even"
            else:
                row_tag = "odd"

            if not day_records:
                # 記録がない日も空行で表示して日付の抜けがわかるようにする
                iid = self.tree.insert("", "end", tag=row_tag, values=(
                    date_str, wd_str, "", "", "", "", ""
                ))
                self._row_date_map[iid] = (y, m, d)
                continue

            day_worked = False

            for record in day_records:
                shift_id   = record.get("shift_id", "")
                shift      = self.dm.get_shift_by_id(shift_id)
                shift_name = shift["name"] if shift else shift_id
                start_str  = record.get("actual_start", "")
                end_str    = record.get("actual_end",   "")
                break_min  = record.get("actual_break",  0)
                is_night   = record.get("is_night",      False)
                memo       = record.get("memo",          "")

                # 公休・有給・欠勤など（開始時刻が設定されていないシフト）
                if shift and not shift.get("start"):
                    iid = self.tree.insert("", "end", tag=row_tag, values=(
                        date_str, wd_str, shift_name, "", "", "", memo
                    ))
                    self._row_date_map[iid] = (y, m, d)
                    date_str = ""
                    wd_str   = ""
                    continue

                # 出退勤時刻が入力されている場合のみ実労働時間を計算する
                if start_str and end_str:
                    work_min = calc_work_minutes(start_str, end_str, break_min, is_night)
                    work_str = minutes_to_hhmm(work_min)
                    total_work_min += work_min
                    day_worked      = True
                else:
                    work_min = 0
                    work_str = ""

                iid = self.tree.insert("", "end", tag=row_tag, values=(
                    date_str, wd_str, shift_name,
                    start_str, end_str, work_str, memo
                ))
                self._row_date_map[iid] = (y, m, d)
                # 同じ日の2行目以降は日付・曜日を空にする
                date_str = ""
                wd_str   = ""

            if day_worked:
                work_days += 1

        self.lbl_total.config(
            text=(
                f"【{sel_name}】  "
                f"出勤日数: {work_days}日  "
                f"実労働時間合計: {minutes_to_hhmm(total_work_min)}"
            )
        )


# ========================
# エントリーポイント
# ========================

if __name__ == "__main__":
    app = ScheduleApp()
    app.mainloop()
