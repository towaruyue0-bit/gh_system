#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
募集説明シート生成アプリ
職員のweekly_pattern（定期シフト設定）を読み込み、担当者が未配置の時間帯を「募集中」として
自動反映したHTMLのチラシを生成します。ブラウザから印刷してそのまま配れます。
"""

import tkinter as tk
from tkinter import messagebox
import json
import os
import webbrowser
from datetime import datetime

# ========================
# パス定数
# ========================
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
STAFF_FILE        = os.path.join(BASE_DIR, "staff.json")
SHIFTS_FILE       = os.path.join(BASE_DIR, "shifts.json")
STAFF_MASTER_FILE = os.path.join(r"C:\GH_Data\data", "staff_master.json")  # 職員の氏名・ふりがな
SETTINGS_FILE = os.path.join(BASE_DIR, "flyer_settings.json")
OUTPUT_DIR    = os.path.join(BASE_DIR, "output")
OUTPUT_FILE   = os.path.join(OUTPUT_DIR, "flyer_output.html")

# ========================
# フォント・カラー定数
# ========================
FONT       = ("MS Gothic", 10)
FONT_BOLD  = ("MS Gothic", 10, "bold")
FONT_TITLE = ("MS Gothic", 12, "bold")
FONT_SMALL = ("MS Gothic", 9)

COLOR_BG     = "#F5F7FA"
COLOR_HEADER = "#4A6FA5"

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

# 各時間帯カードの背景色・枠色・絵文字（HTML用）
BAND_COLORS  = ["#DBEAFE", "#D1FAE5", "#EDE9FE", "#FEF3C7"]
BAND_BORDERS = ["#93C5FD", "#6EE7B7", "#C4B5FD", "#FCD34D"]
BAND_EMOJIS  = ["🍳", "🏠", "🛁", "🌙"]

# ========================
# デフォルト設定（初回起動時）
# ========================
DEFAULT_SETTINGS = {
    "corporation_name": "社会福祉法人 ○○",
    "facility_name": "シェアホームすみか",
    "home_names": "①押切　②小江川",
    "capacity": "利用者定員 各4名",
    "contact_tel": "TEL：000-0000-0000",
    "contact_person": "担当：○○",
    "hourly_wage": "",
    "workplace_feature": "シフトの固定／曜日／時間の調整相談可",
    "band_labels": [
        "① 8:00〜14:30",
        "② 14:00〜16:00",
        "③ 16:00〜20:00",
        "④ 20:00〜翌8:00",
    ],
    "band_tasks": [
        "8:00〜 掃除\n10:30〜 昼食準備\n12:00〜 昼食提供\n13:00〜 食器洗い\n〜14:30 その他雑務",
        "掃除\n夕食下ごしらえ\n利用者帰宅受け入れ",
        "入浴促し\n朝食下ごしらえ\n夕食提供",
        "利用者洗濯物\n定時巡視\n朝食提供\n通所送り出し",
    ],
}


# ========================
# シフト分析ロジック
# ========================

def classify_shift(shift):
    """
    シフト情報からどの時間帯グループに属するかを返す。
    名称に含まれるキーワードで判定し、不明なら開始時刻で判定する。

    戻り値:
        0=昼食帯(8時台〜)  1=早番(14時台〜)
        2=夕食帯(16時台〜) 3=夜勤(20時〜翌)
       -1=公休・判定不能
    """
    sid  = shift.get("id", "")
    name = shift.get("name", "")

    if sid == "day_off" or name == "公休":
        return -1
    if "夜勤" in name or "夜" in name or sid == "night":
        return 3
    if "夕食" in name or "夕" in name or sid == "day_b":
        return 2
    if "早番" in name or "早" in name or sid == "day_a":
        return 1
    if "昼食" in name or "昼" in name:
        return 0

    # 名称で判定できなかった場合は開始時刻で分類
    start_str = shift.get("start", "").replace("：", ":").strip()
    if not start_str:
        return -1
    try:
        h, m = map(int, start_str.split(":"))
        sm = h * 60 + m
        if 480 <= sm < 840:
            return 0
        elif 840 <= sm < 960:
            return 1
        elif 960 <= sm < 1200:
            return 2
        elif sm >= 1200 or sm < 300:
            return 3
    except ValueError:
        pass
    return -1


def load_and_analyze():
    """
    staff.json（シフト設定）と shifts.json を読み込み、
    各曜日 × 時間帯（4区分）に誰が担当しているかを返す。
    氏名はGH_Data/staff_master.json から取得してidで結合する。

    戻り値:
        result[day_idx][band_idx] = {
            "manager": [管理者名, ...],
            "staff":   [一般職員名, ...]
        }
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

    result = {
        d: {b: {"manager": [], "staff": []} for b in range(4)}
        for d in range(7)
    }

    for person in staff_list:
        name       = person.get("name", "")
        is_manager = person.get("is_manager", False)
        pattern    = person.get("weekly_pattern", {})

        for day_str, shift_id in pattern.items():
            if not shift_id or shift_id == "day_off":
                continue
            shift_info = shifts_dict.get(shift_id)
            if not shift_info:
                continue
            band = classify_shift(shift_info)
            if band < 0:
                continue
            day_idx = int(day_str)
            key = "manager" if is_manager else "staff"
            result[day_idx][band][key].append(name)

    return result


# ========================
# HTML 生成
# ========================

def generate_html(settings, vacancy_data):
    """
    設定辞書と担当状況データを受け取りHTMLチラシの文字列を返す。
    一般職員の定期担当がいないセルを「募集中」として色付けする。
    """
    today = datetime.now().strftime("%Y年%m月%d日")

    # ── 募集表の行を組み立てる ──
    table_rows = ""
    for band_idx in range(4):
        label = settings["band_labels"][band_idx]
        # 改行を<br>に変換してHTMLに埋め込む
        label_html = label.replace("\n", "<br>")
        row = f'<tr><td class="band-cell">{label_html}</td>'
        for day_idx in range(7):
            cell = vacancy_data[day_idx][band_idx]
            # 一般職員（パート含む）が定期で入っていなければ「募集中」
            if not cell["staff"]:
                row += '<td class="cell-vacant">募集中</td>'
            else:
                row += '<td class="cell-ok"></td>'
        row += "</tr>\n"
        table_rows += row

    # ── 業務内容カードを組み立てる ──
    cards_html = ""
    for i in range(4):
        label     = settings["band_labels"][i]
        tasks_raw = settings["band_tasks"][i]
        color     = BAND_COLORS[i]
        border    = BAND_BORDERS[i]
        emoji     = BAND_EMOJIS[i]

        # 空行を除いた箇条書きに変換
        items = [t.strip() for t in tasks_raw.split("\n") if t.strip()]
        items_html = "".join(f"<li>{t}</li>" for t in items)

        cards_html += f"""
        <div class="job-card" style="background:{color};border:2px solid {border};">
          <div class="card-title">{label}</div>
          <div class="card-emoji">{emoji}</div>
          <ul>{items_html}</ul>
        </div>"""

    # ── 時給欄（空欄なら枠だけ表示）──
    wage = settings.get("hourly_wage", "").strip()
    wage_display = wage if wage else "　　　　"

    # ── HTML全体 ──
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>パート職員募集・説明シート</title>
<style>
/* 印刷時はA4サイズ・余白最小に */
@page {{ size: A4; margin: 6mm; }}
@media print {{
  body {{ margin: 0; background: white; }}
  .no-print {{ display: none; }}
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'MS Gothic', 'Yu Gothic', 'Meiryo', sans-serif;
  font-size: 10pt;
  background: #e8ecf0;
  color: #222;
}}

/* 用紙全体の枠 */
.page {{
  width: 190mm;
  min-height: 270mm;
  margin: 10px auto;
  padding: 7mm 8mm;
  background: white;
  border: 3px solid #A0C0E0;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
}}

/* ヘッダー */
.header {{
  background: linear-gradient(135deg, #E8F3FF, #C4DEFF);
  border: 1.5px solid #A0C0E0;
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 9px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}}
.header-animals {{
  font-size: 26pt;
  line-height: 1.1;
  color: #5080B0;
  flex-shrink: 0;
}}
.header-center {{ text-align: center; flex: 1; }}
.header h1 {{
  font-size: 14.5pt;
  font-weight: bold;
  color: #1a3a5c;
  margin-bottom: 5px;
  letter-spacing: 0.02em;
}}
.header .facility-info {{
  font-size: 10.5pt;
  color: #2a4a6c;
  line-height: 1.7;
}}

/* セクション見出し */
.section-title {{
  font-size: 10.5pt;
  font-weight: bold;
  color: #1a3a5c;
  border-left: 5px solid #4A6FA5;
  padding: 2px 7px;
  margin: 9px 0 5px;
  background: #EEF4FB;
}}

/* 募集表 */
table.schedule {{
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 7px;
  font-size: 9.5pt;
}}
table.schedule th {{
  background: #D0E2F5;
  border: 1px solid #A0C0E0;
  padding: 5px 2px;
  text-align: center;
  font-weight: bold;
  color: #1a3a5c;
}}
table.schedule th.weekend {{ background: #B8D0EC; }}
table.schedule td {{
  border: 1px solid #C0CED8;
  padding: 7px 4px;
  text-align: center;
  vertical-align: middle;
  height: 36px;
}}
.band-cell {{
  background: #EEF2F8 !important;
  font-weight: bold;
  text-align: left !important;
  padding-left: 9px !important;
  color: #1a3a5c;
  white-space: nowrap;
  width: 82px;
}}
/* 「募集中」セル：画像に合わせた水色 */
.cell-vacant {{
  background: #BFDBFE;
  color: #1e40af;
  font-weight: bold;
  font-size: 10pt;
}}
.cell-ok {{ background: #F8FAFC; }}

/* 待遇セクション */
.benefits {{
  display: flex;
  align-items: center;
  gap: 12px;
  background: #F5F8FC;
  border: 1.5px solid #C8D8EC;
  border-radius: 8px;
  padding: 8px 14px;
  margin: 5px 0;
  flex-wrap: wrap;
}}
.benefits-label {{
  font-weight: bold;
  color: #1a3a5c;
  margin-right: 4px;
}}
.benefit-item {{
  display: flex;
  align-items: center;
  gap: 5px;
  background: white;
  border: 1px solid #C8D8EC;
  border-radius: 20px;
  padding: 3px 11px;
  font-size: 10pt;
  white-space: nowrap;
}}
.wage-box {{
  display: inline-block;
  min-width: 64px;
  border: 1.5px solid #999;
  padding: 1px 6px;
  text-align: center;
  border-radius: 3px;
}}

/* 業務内容カード */
.job-cards {{
  display: flex;
  gap: 6px;
  margin: 5px 0;
}}
.job-card {{
  flex: 1;
  border-radius: 9px;
  padding: 8px 7px;
  font-size: 9pt;
}}
.card-title {{
  font-weight: bold;
  font-size: 9.5pt;
  color: #1a3a5c;
  margin-bottom: 2px;
  border-bottom: 1px solid rgba(0,0,0,0.15);
  padding-bottom: 3px;
}}
.card-emoji {{
  font-size: 20pt;
  text-align: center;
  margin: 4px 0 5px;
}}
.job-card ul {{
  padding-left: 14px;
  line-height: 1.75;
  color: #333;
}}

/* 職場の特徴 */
.feature-box {{
  text-align: center;
  font-size: 17pt;
  font-weight: bold;
  color: #1a3a5c;
  padding: 8px 6px;
  letter-spacing: 0.04em;
}}

/* 連絡先 */
.contact-box {{
  border: 1.5px solid #A0C0E0;
  border-radius: 8px;
  padding: 8px 16px;
  background: #EEF4FB;
  margin-top: 8px;
  font-size: 10pt;
  line-height: 1.9;
}}
.contact-box .corp {{ font-size: 11pt; font-weight: bold; color: #1a3a5c; }}

/* 発行日 */
.date-line {{
  text-align: right;
  font-size: 8pt;
  color: #999;
  margin-top: 5px;
}}

/* ブラウザ表示時の印刷ボタン */
.print-area {{
  text-align: center;
  padding: 16px 0 24px;
}}
.print-btn {{
  padding: 11px 36px;
  background: #4A6FA5;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 12pt;
  cursor: pointer;
  font-family: 'MS Gothic', sans-serif;
  box-shadow: 0 2px 6px rgba(0,0,0,0.18);
}}
.print-btn:hover {{ background: #3a5f95; }}
.print-hint {{
  margin-top: 6px;
  font-size: 9pt;
  color: #888;
  font-family: 'MS Gothic', sans-serif;
}}
</style>
</head>
<body>

<div class="page">

  <!-- ヘッダー：施設情報 -->
  <div class="header">
    <div class="header-animals">🐐<br>🐐</div>
    <div class="header-center">
      <h1>グループホーム　パート職員募集・説明シート</h1>
      <div class="facility-info">
        施設名称：{settings['facility_name']}<br>
        {settings['home_names']}　{settings['capacity']}
      </div>
    </div>
    <div class="header-animals">🐐<br>🐐</div>
  </div>

  <!-- 募集している時間帯 -->
  <div class="section-title">募集している時間帯</div>
  <table class="schedule">
    <tr>
      <th style="width:82px"></th>
      <th>月</th><th>火</th><th>水</th><th>木</th><th>金</th>
      <th class="weekend">土</th>
      <th class="weekend">日</th>
    </tr>
    {table_rows}
  </table>

  <!-- 待遇 -->
  <div class="section-title">待遇</div>
  <div class="benefits">
    <span class="benefits-label">待遇</span>
    <span class="benefit-item">
      💴 時給&nbsp;<span class="wage-box">{wage_display}</span>&nbsp;円
    </span>
    <span class="benefit-item">🚗 交通費支給</span>
    <span class="benefit-item">🍽️ 食事代助成</span>
  </div>

  <!-- 時間帯別の仕事内容 -->
  <div class="section-title">時間帯別の仕事内容</div>
  <div class="job-cards">{cards_html}
  </div>

  <!-- 職場の特徴 -->
  <div class="section-title">職場の特徴</div>
  <div class="feature-box">{settings['workplace_feature']}</div>

  <!-- 連絡先 -->
  <div class="contact-box">
    <div class="corp">{settings['corporation_name']}</div>
    {settings['contact_tel']}　{settings['contact_person']}
  </div>

  <div class="date-line">作成日：{today}</div>

</div>

<!-- 印刷ボタン（印刷時は非表示） -->
<div class="no-print print-area">
  <button class="print-btn" onclick="window.print()">🖨️ 印刷する</button>
  <div class="print-hint">
    ブラウザの印刷設定で「余白：最小」「用紙サイズ：A4」を選択してください
  </div>
</div>

</body>
</html>"""


# ========================
# GUI
# ========================

class ScrollableFrame(tk.Frame):
    """
    縦スクロールができるフレーム。
    設定項目が多いので入力フォームをここに配置する。
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        canvas    = tk.Canvas(self, bg=COLOR_BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=COLOR_BG)

        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # マウスホイールでスクロール（Windows用）
        def _on_wheel(e):
            canvas.yview_scroll(-1 * (e.delta // 120), "units")
        canvas.bind("<MouseWheel>", _on_wheel)
        self.inner.bind("<MouseWheel>", _on_wheel)

        self.canvas = canvas


class FlyerApp(tk.Tk):
    """募集説明シート生成アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("募集説明シート 生成アプリ")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self.settings = self._load_settings()
        self.vars = {}          # 通常の入力欄 → StringVar
        self.text_widgets = {}  # 業務内容テキストエリア → Text ウィジェット（key=band番号0〜3）

        self._build_ui()
        self._center_window(680, 660)

    # ── 設定の読み書き ──────────────────────────────────

    def _load_settings(self):
        """設定ファイルがあれば読み込み、なければデフォルト設定を使う。"""
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 新しいキーがデフォルトにあっても消えないようにマージ
                merged = DEFAULT_SETTINGS.copy()
                merged.update(saved)
                return merged
            except Exception:
                pass
        return DEFAULT_SETTINGS.copy()

    def _collect_from_ui(self):
        """UIの入力内容を辞書にまとめて返す（ファイル保存は行わない）。"""
        settings = {key: var.get() for key, var in self.vars.items()
                    if not key.startswith("band_label_")}

        # band_label_0〜3 をリストに変換
        settings["band_labels"] = [
            self.vars.get(f"band_label_{i}", tk.StringVar()).get()
            for i in range(4)
        ]
        # テキストエリアの内容をリストに変換
        settings["band_tasks"] = [
            self.text_widgets[i].get("1.0", tk.END).strip()
            for i in range(4)
        ]
        return settings

    def _save_settings_to_file(self, settings):
        """設定辞書をファイルに保存する。"""
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

    # ── UI 構築 ─────────────────────────────────────────

    def _build_ui(self):
        """ウィンドウ全体のUIを組み立てる。"""

        # タイトルバー
        title_frame = tk.Frame(self, bg=COLOR_HEADER, pady=9)
        title_frame.pack(fill="x")
        tk.Label(
            title_frame, text="募集説明シート 生成アプリ",
            font=FONT_TITLE, bg=COLOR_HEADER, fg="white"
        ).pack()
        tk.Label(
            title_frame, text="設定を入力 → 「HTML生成・ブラウザで開く」で印刷用チラシが作られます",
            font=FONT_SMALL, bg=COLOR_HEADER, fg="#CCDDFF"
        ).pack()

        # スクロール可能な入力フォーム
        scroll_area = ScrollableFrame(self, bg=COLOR_BG)
        scroll_area.pack(fill="both", expand=True, padx=10, pady=(8, 0))
        form = scroll_area.inner

        r = 0  # グリッドの行番号

        # 施設情報
        r = self._section_label(form, "🏠 施設情報", r)
        r = self._entry_row(form, "法人名",   "corporation_name", r)
        r = self._entry_row(form, "施設名",   "facility_name",    r)
        r = self._entry_row(form, "ホーム名", "home_names",       r)
        r = self._entry_row(form, "定員",     "capacity",         r)

        # 連絡先
        r = self._section_label(form, "📞 連絡先（外部配布用）", r)
        r = self._entry_row(form, "電話番号", "contact_tel",    r)
        r = self._entry_row(form, "担当者名", "contact_person", r)

        # 待遇
        r = self._section_label(form, "💴 待遇", r)
        r = self._entry_row(form, "時給（空欄でもOK）", "hourly_wage", r)

        # 職場の特徴
        r = self._section_label(form, "✨ 職場の特徴", r)
        r = self._entry_row(form, "特徴文言", "workplace_feature", r)

        # 時間帯別業務内容
        r = self._section_label(form, "📋 時間帯別の業務内容（1行に1項目）", r)

        band_labels_saved = self.settings.get("band_labels", DEFAULT_SETTINGS["band_labels"])
        band_tasks_saved  = self.settings.get("band_tasks",  DEFAULT_SETTINGS["band_tasks"])

        for i in range(4):
            default_label = band_labels_saved[i] if i < len(band_labels_saved) else ""
            default_tasks = band_tasks_saved[i]  if i < len(band_tasks_saved)  else ""

            # 時間帯ラベル
            r = self._entry_row(form, f"時間帯ラベル ④"[i + 1], f"band_label_{i}", r,
                                default=default_label)

            # 業務内容テキストエリア
            tk.Label(
                form, text="  業務内容（1行に1項目ずつ）",
                font=FONT_SMALL, bg=COLOR_BG, fg="#555", anchor="w"
            ).grid(row=r, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 1))
            r += 1

            txt = tk.Text(form, height=5, width=52, font=FONT,
                          relief="solid", bd=1, padx=4, pady=3)
            txt.insert("1.0", default_tasks)
            txt.grid(row=r, column=0, columnspan=2, sticky="ew",
                     padx=20, pady=(0, 6))
            self.text_widgets[i] = txt
            r += 1

            # テキストエリアにもスクロールを伝播させる
            def _wheel(e, t=txt):
                t.event_generate("<MouseWheel>", delta=e.delta)
            txt.bind("<MouseWheel>", lambda e: None)  # ここは内部スクロールに任せる

        form.columnconfigure(1, weight=1)

        # ── ボタン行 ──
        btn_frame = tk.Frame(self, bg=COLOR_BG, pady=10)
        btn_frame.pack(fill="x", padx=10)

        tk.Button(
            btn_frame, text="💾 設定を保存",
            font=FONT, relief="flat", cursor="hand2",
            bg="#6B8CBF", fg="white", padx=12, pady=5,
            command=self._on_save
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="🖨️  HTML生成・ブラウザで開く",
            font=FONT_BOLD, relief="flat", cursor="hand2",
            bg=COLOR_HEADER, fg="white", padx=18, pady=5,
            command=self._on_generate
        ).pack(side="right", padx=4)

    def _section_label(self, parent, text, row):
        """セクション見出しを配置して次の行番号を返す。"""
        frame = tk.Frame(parent, bg="#C8D8EC")
        frame.grid(row=row, column=0, columnspan=2, sticky="ew",
                   padx=4, pady=(10, 2))
        tk.Label(
            frame, text=text, font=FONT_BOLD,
            bg="#C8D8EC", padx=8, pady=4
        ).pack(anchor="w")
        return row + 1

    def _entry_row(self, parent, label_text, var_key, row, default=None):
        """
        ラベルとテキスト入力欄を1行配置する。
        self.vars[var_key] に StringVar を登録して次の行番号を返す。
        """
        var = tk.StringVar()
        if default is not None:
            var.set(default)
        elif var_key in self.settings:
            var.set(str(self.settings[var_key]))
        self.vars[var_key] = var

        tk.Label(
            parent, text=f"  {label_text}",
            font=FONT, bg=COLOR_BG, anchor="w", width=20
        ).grid(row=row, column=0, sticky="w", padx=8, pady=3)

        tk.Entry(
            parent, textvariable=var, font=FONT, relief="solid", bd=1
        ).grid(row=row, column=1, sticky="ew", padx=8, pady=3)

        return row + 1

    # ── ボタン処理 ──────────────────────────────────────

    def _on_save(self):
        """入力内容を設定ファイルに保存する。"""
        try:
            settings = self._collect_from_ui()
            self._save_settings_to_file(settings)
            messagebox.showinfo("保存完了", "設定を保存しました。")
        except Exception as e:
            messagebox.showerror("保存エラー", f"保存に失敗しました：\n{e}")

    def _on_generate(self):
        """入力内容を保存してHTMLチラシを生成し、ブラウザで開く。"""
        # UIから設定を取り出して保存
        settings = self._collect_from_ui()
        try:
            self._save_settings_to_file(settings)
        except Exception as e:
            messagebox.showerror("保存エラー", f"設定の保存に失敗しました：\n{e}")
            return

        # シフトデータを読み込んで担当状況を分析
        try:
            vacancy_data = load_and_analyze()
        except FileNotFoundError as e:
            messagebox.showerror(
                "ファイルエラー",
                f"データファイルが見つかりません：\n{e}\n\n"
                f"kintai_app フォルダに staff.json と shifts.json があるか確認してください。"
            )
            return
        except Exception as e:
            messagebox.showerror("読み込みエラー", f"データの読み込みに失敗しました：\n{e}")
            return

        # HTMLを生成してファイルに書き出す
        html = generate_html(settings, vacancy_data)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception as e:
            messagebox.showerror("書き出しエラー", f"HTMLファイルの保存に失敗しました：\n{e}")
            return

        # ブラウザで開く（パスをURLに変換）
        url = "file:///" + OUTPUT_FILE.replace("\\", "/")
        webbrowser.open(url)

        messagebox.showinfo(
            "生成完了",
            f"HTMLチラシをブラウザで開きました。\n\n"
            f"【印刷方法】\n"
            f"ブラウザの「印刷」ボタン（または Ctrl+P）を押し、\n"
            f"「余白：最小」「用紙：A4」に設定して印刷してください。\n\n"
            f"保存先：\n{OUTPUT_FILE}"
        )

    def _center_window(self, w, h):
        """ウィンドウを画面中央に配置する。"""
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")


# ========================
# エントリーポイント
# ========================
if __name__ == "__main__":
    app = FlyerApp()
    app.mainloop()
