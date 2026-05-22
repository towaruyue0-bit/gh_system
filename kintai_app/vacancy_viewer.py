#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人員不足時間帯ビューア
職員の weekly_pattern（定期シフト設定）を読み込み、
担当者が入っていない・または管理者だけが入っている時間帯を一覧表示します。
パート職員の募集が必要な箇所の把握に使います。
"""

import tkinter as tk
from tkinter import messagebox
import json
import os

# ============================
# ファイルパス
# ============================
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
STAFF_FILE        = os.path.join(BASE_DIR, "staff.json")
SHIFTS_FILE       = os.path.join(BASE_DIR, "shifts.json")
STAFF_MASTER_FILE = os.path.join(r"C:\GH_Data\data", "staff_master.json")  # 職員の氏名・ふりがな

# ============================
# フォント定義
# ============================
FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 9)

# ============================
# 曜日
# ============================
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# ============================
# 時間帯グループの定義（表示ラベル）
# ============================
BAND_LABELS = [
    "① 8:00〜14:30\n  （昼食帯）",
    "② 14:00〜16:00\n  （早番）",
    "③ 16:00〜20:00\n  （夕食帯）",
    "④ 20:00〜翌8:00\n  （夜勤）",
]

# ============================
# 色設定
# ============================
COLOR_BG        = "#F5F7FA"
COLOR_HEADER_BG = "#4A6FA5"
COLOR_HEADER_FG = "white"
COLOR_WEEKEND   = "#E8EDF5"
COLOR_WEEKDAY   = "#EEF2F8"
COLOR_BAND_CELL = "#E5EAF3"
COLOR_VACANT    = "#E55353"   # 誰もいない → 募集中（赤）
COLOR_MANAGER   = "#F0A500"   # 管理者のみ（オレンジ）
COLOR_COVERED   = "#3DAA6F"   # 担当あり（緑）
COLOR_FG_LIGHT  = "white"
COLOR_FG_DARK   = "#222222"


def classify_shift(shift):
    """
    シフト情報から、どの時間帯グループ（band）に属するかを返す。
    シフト名の文字で判断し、判断できない場合は開始時刻で分類する。

    戻り値:
        0 = 昼食帯（8:00〜14:30頃）
        1 = 早番  （14:00〜16:00頃）
        2 = 夕食帯（16:00〜20:00頃）
        3 = 夜勤  （20:00〜翌8:00）
       -1 = 公休・分類不可（集計対象外）
    """
    sid  = shift.get("id", "")
    name = shift.get("name", "")

    # 公休は対象外
    if sid == "day_off" or name == "公休":
        return -1

    # シフト名のキーワードで判定（名称ベースの方が安定している）
    if "夜勤" in name or "夜" in name or sid == "night":
        return 3
    if "夕食" in name or "夕" in name or sid == "day_b":
        return 2
    if "早番" in name or "早" in name or sid == "day_a":
        return 1
    if "昼食" in name or "昼" in name:
        return 0

    # キーワードで判定できない場合は開始時刻で分類（フォールバック）
    start_str = shift.get("start", "").replace("：", ":").strip()
    if not start_str:
        return -1
    try:
        h, m = map(int, start_str.split(":"))
    except ValueError:
        return -1

    start_min = h * 60 + m
    if 480 <= start_min < 840:          # 8:00〜13:59 → 昼食帯
        return 0
    elif 840 <= start_min < 960:        # 14:00〜15:59 → 早番
        return 1
    elif 960 <= start_min < 1200:       # 16:00〜19:59 → 夕食帯
        return 2
    elif start_min >= 1200 or start_min < 300:  # 20:00〜翌4:59 → 夜勤
        return 3
    return -1


def load_data():
    """
    staff.json（シフト設定）と shifts.json を読み込んで返す。
    氏名はGH_Data/staff_master.json から取得してidで結合する。
    戻り値: (職員リスト, シフト辞書{id: シフト情報})
    """
    with open(STAFF_FILE, "r", encoding="utf-8") as f:
        staff_list = json.load(f)
    with open(SHIFTS_FILE, "r", encoding="utf-8") as f:
        shifts_list = json.load(f)

    # 氏名マスターを読み込んで結合する
    try:
        with open(STAFF_MASTER_FILE, "r", encoding="utf-8") as f:
            master_map = {m["id"]: m for m in json.load(f)}
    except Exception:
        master_map = {}
    for s in staff_list:
        personal = master_map.get(s["id"], {})
        s["name"] = personal.get("name", "")
        s["kana"] = personal.get("kana", "")

    shifts_dict = {s["id"]: s for s in shifts_list}
    return staff_list, shifts_dict


def analyze(staff_list, shifts_dict):
    """
    各曜日（0=月〜6=日）× 時間帯（0〜3）について、
    誰が担当しているかを分析する。

    戻り値:
        result[day_idx][band_idx] = {
            "manager": [管理者名, ...],
            "staff":   [一般職員名, ...]
        }
    """
    result = {
        day: {band: {"manager": [], "staff": []} for band in range(4)}
        for day in range(7)
    }

    for person in staff_list:
        name       = person.get("name", "（名前なし）")
        is_manager = person.get("is_manager", False)
        pattern    = person.get("weekly_pattern", {})

        for day_str, shift_id in pattern.items():
            # 空文字・公休は勤務なし扱い
            if not shift_id or shift_id == "day_off":
                continue

            shift_info = shifts_dict.get(shift_id)
            if shift_info is None:
                continue

            band = classify_shift(shift_info)
            if band < 0:
                continue

            day_idx = int(day_str)
            if is_manager:
                result[day_idx][band]["manager"].append(name)
            else:
                result[day_idx][band]["staff"].append(name)

    return result


# ============================
# メインウィンドウ
# ============================
class VacancyViewer(tk.Tk):
    """人員不足時間帯ビューアのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("人員不足時間帯ビューア")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self._load_and_build()
        self._center_window()

    def _load_and_build(self):
        """データ読み込みとUI構築をまとめて行う"""
        try:
            staff_list, shifts_dict = load_data()
        except FileNotFoundError as e:
            messagebox.showerror("ファイルエラー", f"ファイルが見つかりません:\n{e}")
            self.destroy()
            return

        self.data = analyze(staff_list, shifts_dict)
        self._build_ui()

    def _build_ui(self):
        """UIを構築する（再描画のたびに呼ばれる）"""
        # ---- タイトルバー ----
        title_frame = tk.Frame(self, bg=COLOR_HEADER_BG, pady=10)
        title_frame.pack(fill="x")
        tk.Label(
            title_frame, text="人員不足時間帯ビューア",
            font=FONT_TITLE, bg=COLOR_HEADER_BG, fg=COLOR_HEADER_FG
        ).pack()
        tk.Label(
            title_frame, text="定期シフト（weekly_pattern）が未配置の時間帯を表示します",
            font=FONT_SMALL, bg=COLOR_HEADER_BG, fg="#CCDDFF"
        ).pack()

        # ---- 凡例 ----
        legend_frame = tk.Frame(self, bg=COLOR_BG, pady=6)
        legend_frame.pack(fill="x", padx=16)
        tk.Label(legend_frame, text="凡例：", font=FONT, bg=COLOR_BG).pack(side="left")
        self._legend(legend_frame, COLOR_VACANT,  COLOR_FG_LIGHT, "募集中（定期担当なし）")
        self._legend(legend_frame, COLOR_MANAGER, COLOR_FG_DARK,  "管理者のみ")
        self._legend(legend_frame, COLOR_COVERED, COLOR_FG_LIGHT, "担当者あり")

        # ---- グリッド ----
        grid_frame = tk.Frame(self, bg=COLOR_BG)
        grid_frame.pack(fill="both", expand=True, padx=16, pady=(4, 4))

        # ヘッダー（曜日）
        tk.Label(
            grid_frame, text="時間帯", font=FONT_BOLD,
            bg="#D0D8E8", relief="flat", padx=10, pady=8, width=16
        ).grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        for col, day in enumerate(WEEKDAYS):
            bg = "#C8D4E8" if col >= 5 else "#D8E2F0"   # 土日は少し濃く
            tk.Label(
                grid_frame, text=day, font=FONT_BOLD,
                bg=bg, relief="flat", padx=10, pady=8, width=11
            ).grid(row=0, column=col + 1, sticky="nsew", padx=1, pady=1)

        # データ行（時間帯 × 曜日）
        for band_idx, band_label in enumerate(BAND_LABELS):
            # 時間帯ラベル列
            tk.Label(
                grid_frame, text=band_label, font=FONT,
                bg=COLOR_BAND_CELL, relief="flat", padx=10, pady=6,
                justify="left", anchor="w"
            ).grid(row=band_idx + 1, column=0, sticky="nsew", padx=1, pady=1)

            # 各曜日のセル
            for day_idx in range(7):
                cell = self.data[day_idx][band_idx]
                managers = cell["manager"]
                staff    = cell["staff"]

                if staff:
                    # 一般職員が担当している → 緑
                    bg   = COLOR_COVERED
                    fg   = COLOR_FG_LIGHT
                    lines = staff[:]
                    if managers:
                        lines += [f"({m})" for m in managers]
                    text = "\n".join(lines)
                elif managers:
                    # 管理者だけが担当している → オレンジ（要注意）
                    bg   = COLOR_MANAGER
                    fg   = COLOR_FG_DARK
                    text = "\n".join(f"({m})" for m in managers)
                else:
                    # 誰もいない → 赤・募集中
                    bg   = COLOR_VACANT
                    fg   = COLOR_FG_LIGHT
                    text = "募集中"

                tk.Label(
                    grid_frame, text=text, font=FONT,
                    bg=bg, fg=fg, relief="flat", padx=6, pady=6,
                    justify="center"
                ).grid(row=band_idx + 1, column=day_idx + 1, sticky="nsew", padx=1, pady=1)

        # グリッド列の幅を均等にする
        for col in range(8):
            grid_frame.columnconfigure(col, weight=1)
        for row in range(len(BAND_LABELS) + 1):
            grid_frame.rowconfigure(row, weight=1)

        # ---- 要約メッセージ ----
        self._build_summary()

        # ---- 再読み込みボタン ----
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(pady=10)
        tk.Button(
            btn_frame, text="最新データを再読み込み", font=FONT,
            relief="flat", cursor="hand2",
            bg=COLOR_HEADER_BG, fg="white", padx=14, pady=5,
            command=self._refresh
        ).pack()

    def _build_summary(self):
        """募集が必要な箇所を文章でまとめて表示する"""
        vacant_items   = []   # 誰もいない箇所
        manager_items  = []   # 管理者のみの箇所

        for day_idx in range(7):
            for band_idx in range(4):
                cell     = self.data[day_idx][band_idx]
                managers = cell["manager"]
                staff    = cell["staff"]
                day_name = WEEKDAYS[day_idx]
                band_short = ["昼食帯", "早番", "夕食帯", "夜勤"][band_idx]

                if not staff and not managers:
                    vacant_items.append(f"{day_name}・{band_short}")
                elif not staff and managers:
                    manager_items.append(f"{day_name}・{band_short}")

        summary_frame = tk.Frame(self, bg="#FEFAF0", relief="flat", pady=8)
        summary_frame.pack(fill="x", padx=16, pady=(0, 4))

        tk.Label(
            summary_frame, text="▶ 募集優先度の高い箇所", font=FONT_BOLD,
            bg="#FEFAF0", anchor="w"
        ).pack(fill="x", padx=10)

        if vacant_items:
            text = "【定期担当なし】 " + "　".join(vacant_items)
            tk.Label(
                summary_frame, text=text, font=FONT,
                bg="#FEFAF0", fg="#CC2200", anchor="w", wraplength=700, justify="left"
            ).pack(fill="x", padx=20, pady=2)

        if manager_items:
            text = "【管理者のみ担当】 " + "　".join(manager_items)
            tk.Label(
                summary_frame, text=text, font=FONT,
                bg="#FEFAF0", fg="#995500", anchor="w", wraplength=700, justify="left"
            ).pack(fill="x", padx=20, pady=2)

        if not vacant_items and not manager_items:
            tk.Label(
                summary_frame, text="すべての時間帯に定期担当者が配置されています。",
                font=FONT, bg="#FEFAF0", fg="#228833", anchor="w"
            ).pack(fill="x", padx=20, pady=2)

    def _legend(self, parent, bg, fg, label):
        """凡例アイテムを1つ作成する"""
        frame = tk.Frame(parent, bg=COLOR_BG)
        frame.pack(side="left", padx=10)
        tk.Label(frame, text="  ■  ", bg=bg, fg=fg, font=FONT_SMALL).pack(side="left")
        tk.Label(frame, text=label, font=FONT_SMALL, bg=COLOR_BG).pack(side="left")

    def _refresh(self):
        """データを再読み込みして画面を再描画する"""
        for widget in self.winfo_children():
            widget.destroy()
        self._load_and_build()
        self._center_window()

    def _center_window(self):
        """ウィンドウを画面中央に配置する"""
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")


if __name__ == "__main__":
    app = VacancyViewer()
    app.mainloop()
