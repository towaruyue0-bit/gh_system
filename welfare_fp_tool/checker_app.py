# =============================================================================
# 障害者向けFP補助ツール - 制度チェッカー（フェーズ1）
# グループホーム入居希望者アセスメント支援ツール
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import date

# =============================================================================
# パス設定
# =============================================================================
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
DB_PATH      = os.path.join(DATA_DIR, "residents.db")

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 色設定
COLOR_BG      = "#F5F7FA"
COLOR_PRIMARY = "#2E7D9C"   # 青系メイン
COLOR_GREEN   = "#4A9B6F"   # グリーン系
COLOR_HEADER  = "#1A5C73"

# =============================================================================
# 制度判定ロジック
# =============================================================================

def check_eligibility(data):
    """
    入力データをもとに申請可能な制度を判定して返す。

    Args:
        data (dict): フォームから収集した入力情報
            - techo       : 障害者手帳の種類・等級（例："精神1級", "療育A"）
            - shogai_types: 障害種別のリスト（例：["精神障害"]）
            - kyufu       : 現在受給中の制度リスト
            - gh_yotei    : GH入居予定（"はい" or "いいえ"）
            - shuro       : 就労状況（"あり" or "なし"）
    Returns:
        list[dict]: 対象制度のリスト
    """
    results = []

    techo        = data.get("techo", "なし")
    shogai_types = data.get("shogai_types", [])
    kyufu        = data.get("kyufu", [])
    gh_yotei     = data.get("gh_yotei", "いいえ")
    shuro        = data.get("shuro", "なし")

    # -----------------------------------------------------------------------
    # 1. 障害基礎年金
    # -----------------------------------------------------------------------
    # 1級対象：精神手帳1級・療育A・身体1〜2級
    nenkin1_ok = techo in ["精神1級", "療育A", "身体1級", "身体2級"]
    # 2級対象：精神手帳2〜3級・療育B・身体3〜4級
    nenkin2_ok = techo in ["精神2級", "精神3級", "療育B", "身体3級", "身体4級"]

    already_nenkin = ("障害基礎年金1級" in kyufu or "障害基礎年金2級" in kyufu)

    if nenkin1_ok and not already_nenkin:
        results.append({
            "category": "申請推奨",
            "name":     "障害基礎年金 1級",
            "amount":   "月額 約81,620円（2024年度）",
            "summary":  "国民年金加入中に一定の障害状態になった方に支給される年金です。"
                        "20歳前傷病の場合は20歳から受給できます。",
            "window":   "市区町村役場（国民年金担当窓口）または年金事務所",
            "notes":    [],
        })
    elif nenkin2_ok and not already_nenkin:
        results.append({
            "category": "申請推奨",
            "name":     "障害基礎年金 2級",
            "amount":   "月額 約66,250円（2024年度）",
            "summary":  "国民年金加入中に一定の障害状態になった方に支給される年金です。"
                        "20歳前傷病の場合は20歳から受給できます。",
            "window":   "市区町村役場（国民年金担当窓口）または年金事務所",
            "notes":    [],
        })

    # -----------------------------------------------------------------------
    # 2. 特別障害者手当
    # ※ グループホーム入居中は施設入所扱いとなり原則対象外。
    #   入居前に申請済みのケースは継続の可否を別途確認が必要。
    # -----------------------------------------------------------------------
    tokubetsu_ok = techo in ["精神1級", "療育A", "身体1級", "身体2級"]
    if tokubetsu_ok and "特別障害者手当" not in kyufu:
        notes = []
        if gh_yotei == "はい":
            notes.append(
                "⚠️ グループホーム入居後は原則として対象外となります。"
                "入居前に申請を検討してください。"
            )
        results.append({
            "category": "申請推奨",
            "name":     "特別障害者手当",
            "amount":   "月額 約27,980円（2024年度）",
            "summary":  "在宅で重度の障害があり、日常生活において常時特別の介護を必要とする"
                        "20歳以上の方に支給される手当です。所得制限があります。",
            "window":   "市区町村役場（障害福祉担当窓口）",
            "notes":    notes,
        })

    # -----------------------------------------------------------------------
    # 3. 自立支援医療（精神通院）
    # -----------------------------------------------------------------------
    if "精神障害" in shogai_types and "自立支援医療（精神通院）" not in kyufu:
        results.append({
            "category": "申請推奨",
            "name":     "自立支援医療（精神通院）",
            "amount":   "医療費の自己負担が原則1割に軽減",
            "summary":  "精神疾患で継続的な通院治療が必要な方を対象に、"
                        "指定医療機関での医療費（診察・薬代等）を軽減する制度です。",
            "window":   "市区町村役場（障害福祉担当窓口）",
            "notes":    [],
        })

    # -----------------------------------------------------------------------
    # 4. 重度心身障害者医療費助成
    # ※ 自治体によって対象要件・助成内容が大きく異なる。
    #   対象と思われる場合でも、必ず担当窓口で確認するよう案内する。
    # -----------------------------------------------------------------------
    juudo_ok = techo in ["精神1級", "療育A", "身体1級", "身体2級", "身体3級"]
    if juudo_ok and "重度心身障害者医療費助成" not in kyufu:
        results.append({
            "category": "要確認",
            "name":     "重度心身障害者医療費助成",
            "amount":   "医療費の自己負担分が助成（自治体により異なる）",
            "summary":  "重度の障害がある方の医療費を助成する制度です。"
                        "内容・対象要件は各自治体で異なります。",
            "window":   "市区町村役場（障害福祉担当窓口）",
            "notes":    [
                "⚠️ 自治体によって対象要件・助成内容が大きく異なります。"
                "必ず担当窓口にご確認ください。"
            ],
        })

    # -----------------------------------------------------------------------
    # 5. 生活保護
    # 簡易判定：年金未受給かつ就労なし の場合に案内する
    # 実際の要否は収支シミュレーター（フェーズ2）で詳細判定予定
    # -----------------------------------------------------------------------
    if not already_nenkin and shuro == "なし":
        results.append({
            "category": "参考情報",
            "name":     "生活保護",
            "amount":   "最低生活費との差額を支給（収入・資産による審査あり）",
            "summary":  "収入・資産が最低生活費を下回る場合に利用できる制度です。"
                        "他の制度を最大限活用してもなお生活が成り立たない場合の"
                        "最後のセーフティネットです。",
            "window":   "お住まいの市区町村の福祉事務所",
            "notes":    [
                "収支の詳細な判定は「収支シミュレーター（フェーズ2）」で確認できます（準備中）。"
            ],
        })

    return results


# =============================================================================
# メインアプリケーション
# =============================================================================

class CheckerApp(tk.Tk):
    """制度チェッカーのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("障害者向けFP補助ツール - 制度チェッカー")
        self.geometry("820x700")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        # フォームデータを保持する変数群（フレーム間で共有）
        self._init_vars()

        # ヘッダー
        self._build_header()

        # コンテンツエリア
        self.content = tk.Frame(self, bg=COLOR_BG)
        self.content.pack(fill="both", expand=True, padx=20, pady=10)

        # フッター（免責事項）
        self._build_footer()

        # 最初のフレームを表示
        self._show_frame_step1()

    def _init_vars(self):
        """フォームで使う変数を初期化する"""
        # Step1：入居者選択
        self.var_input_mode  = tk.StringVar(value="db")
        self.var_resident_id = tk.IntVar(value=0)
        self.var_name        = tk.StringVar()
        self.var_age         = tk.StringVar()
        self.var_shien_ku    = tk.StringVar(value="区分なし")

        # Step2：詳細情報
        self.var_shogai_seishin     = tk.BooleanVar()
        self.var_shogai_chiteki     = tk.BooleanVar()
        self.var_shogai_shintai     = tk.BooleanVar()
        self.var_techo              = tk.StringVar(value="なし")
        self.var_kyufu_nenkin1      = tk.BooleanVar()
        self.var_kyufu_nenkin2      = tk.BooleanVar()
        self.var_kyufu_tokubetsu    = tk.BooleanVar()
        self.var_kyufu_jiritsushien = tk.BooleanVar()
        self.var_kyufu_juudo        = tk.BooleanVar()
        self.var_kyufu_seiho        = tk.BooleanVar()
        self.var_gh_yotei           = tk.StringVar(value="いいえ")
        self.var_shuro              = tk.StringVar(value="なし")

    # -----------------------------------------------------------------------
    # ヘッダー・フッター
    # -----------------------------------------------------------------------

    def _build_header(self):
        """ヘッダーを作成する"""
        header = tk.Frame(self, bg=COLOR_HEADER, height=58)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="障害者向けFP補助ツール　制度チェッカー",
            font=FONT_TITLE, bg=COLOR_HEADER, fg="white"
        ).pack(side="left", padx=20, pady=14)

        tk.Label(
            header,
            text="ver 1.0　フェーズ1",
            font=FONT_SMALL, bg=COLOR_HEADER, fg="#A8CCE0"
        ).pack(side="right", padx=20)

    def _build_footer(self):
        """フッター（免責事項）を作成する"""
        footer = tk.Frame(self, bg="#DDE3EA")
        footer.pack(fill="x", side="bottom")
        tk.Label(
            footer,
            text="※ 本ツールは支援者の補助ツールです。個別の制度適用については必ず専門機関"
                 "（市区町村・社会福祉士・年金事務所等）にご確認ください。",
            font=FONT_SMALL, bg="#DDE3EA", fg="#555555",
            wraplength=780, justify="left"
        ).pack(padx=15, pady=6)

    def _clear_content(self):
        """コンテンツエリアをクリアする"""
        for widget in self.content.winfo_children():
            widget.destroy()

    # -----------------------------------------------------------------------
    # ステップインジケーター
    # -----------------------------------------------------------------------

    def _build_step_indicator(self, current: int):
        """現在のステップを示すインジケーターを表示する"""
        steps = [(1, "対象者選択"), (2, "詳細情報入力"), (3, "チェック結果")]

        frame = tk.Frame(self.content, bg=COLOR_BG)
        frame.pack(anchor="w", pady=(4, 0))

        for i, (num, label) in enumerate(steps):
            is_current = (num == current)
            is_done    = (num < current)

            if is_current:
                bg, fg, text = COLOR_PRIMARY, "white", f" {num} "
            elif is_done:
                bg, fg, text = COLOR_GREEN, "white", " ✓ "
            else:
                bg, fg, text = "#CCC", "#888", f" {num} "

            tk.Label(frame, text=text, font=FONT_BOLD, bg=bg, fg=fg).pack(side="left")
            tk.Label(
                frame, text=f" {label} ",
                font=FONT_SMALL, bg=COLOR_BG,
                fg=COLOR_HEADER if is_current else ("#555" if is_done else "#AAA")
            ).pack(side="left")

            if i < len(steps) - 1:
                tk.Label(frame, text=" ▶ ", font=FONT_SMALL, bg=COLOR_BG, fg="#BBB").pack(side="left")

    # -----------------------------------------------------------------------
    # ステップ1：対象者選択
    # -----------------------------------------------------------------------

    def _show_frame_step1(self):
        """ステップ1（対象者選択）を表示する"""
        self._clear_content()
        self._build_step_indicator(current=1)

        tk.Label(
            self.content, text="対象者の選択",
            font=FONT_TITLE, bg=COLOR_BG, fg=COLOR_HEADER
        ).pack(anchor="w", pady=(10, 4))

        tk.Label(
            self.content,
            text="入居者マスターから選ぶか、情報を直接入力してください。",
            font=FONT, bg=COLOR_BG, fg="#555"
        ).pack(anchor="w", pady=(0, 10))

        # 入力モード選択（ラジオボタン）
        mode_frame = tk.Frame(self.content, bg=COLOR_BG)
        mode_frame.pack(anchor="w", pady=(0, 8))
        tk.Radiobutton(
            mode_frame, text="入居者マスターから選択",
            variable=self.var_input_mode, value="db",
            font=FONT, bg=COLOR_BG, activebackground=COLOR_BG,
            command=self._on_mode_change
        ).pack(side="left", padx=(0, 20))
        tk.Radiobutton(
            mode_frame, text="直接入力",
            variable=self.var_input_mode, value="manual",
            font=FONT, bg=COLOR_BG, activebackground=COLOR_BG,
            command=self._on_mode_change
        ).pack(side="left")

        # DBモード UI
        self.frame_db_mode = tk.Frame(self.content, bg=COLOR_BG)
        self.frame_db_mode.pack(fill="x", pady=(0, 8))
        self._build_db_mode_ui()

        # 手動モード UI
        self.frame_manual_mode = tk.Frame(self.content, bg=COLOR_BG)
        self.frame_manual_mode.pack(fill="x", pady=(0, 8))
        self._build_manual_mode_ui()

        self._on_mode_change()

        tk.Button(
            self.content, text="次へ　▶",
            font=FONT_BOLD, bg=COLOR_PRIMARY, fg="white",
            relief="flat", cursor="hand2", padx=30, pady=8,
            command=self._go_to_step2
        ).pack(anchor="e", pady=15)

    def _build_db_mode_ui(self):
        """DBから入居者を選択するUIを作成する"""
        residents = self._load_residents()

        if not residents:
            tk.Label(
                self.frame_db_mode,
                text="入居者マスターが見つかりません（DB未接続またはデータなし）\n直接入力をご利用ください。",
                font=FONT, bg="#FFF3CD", fg="#856404",
                relief="flat", padx=12, pady=8, justify="left"
            ).pack(anchor="w")
            return

        row = tk.Frame(self.frame_db_mode, bg=COLOR_BG)
        row.pack(anchor="w")

        tk.Label(row, text="入居者：", font=FONT, bg=COLOR_BG).pack(side="left")

        self._residents_data = residents
        labels = [
            f"{r['name']}（{r['age']}歳・区分{r['disability_grade'] or 'なし'}）"
            for r in residents
        ]
        self.combo_residents = ttk.Combobox(
            row, values=labels, state="readonly", width=40, font=FONT
        )
        self.combo_residents.pack(side="left", padx=8)
        self.combo_residents.bind("<<ComboboxSelected>>", self._on_resident_select)

        self.lbl_resident_info = tk.Label(
            self.frame_db_mode, text="",
            font=FONT_SMALL, bg=COLOR_BG, fg="#555"
        )
        self.lbl_resident_info.pack(anchor="w", pady=(4, 0))

    def _build_manual_mode_ui(self):
        """直接入力フィールドを作成する"""
        # 氏名
        row1 = tk.Frame(self.frame_manual_mode, bg=COLOR_BG)
        row1.pack(anchor="w", pady=3)
        tk.Label(row1, text="氏名：", font=FONT, bg=COLOR_BG, width=14, anchor="w").pack(side="left")
        tk.Entry(row1, textvariable=self.var_name, font=FONT, width=25).pack(side="left")

        # 年齢
        row2 = tk.Frame(self.frame_manual_mode, bg=COLOR_BG)
        row2.pack(anchor="w", pady=3)
        tk.Label(row2, text="年齢：", font=FONT, bg=COLOR_BG, width=14, anchor="w").pack(side="left")
        tk.Entry(row2, textvariable=self.var_age, font=FONT, width=8).pack(side="left")
        tk.Label(row2, text="歳", font=FONT, bg=COLOR_BG).pack(side="left", padx=4)

        # 障害支援区分
        row3 = tk.Frame(self.frame_manual_mode, bg=COLOR_BG)
        row3.pack(anchor="w", pady=3)
        tk.Label(row3, text="障害支援区分：", font=FONT, bg=COLOR_BG, width=14, anchor="w").pack(side="left")
        ku_values = ["区分なし", "区分1", "区分2", "区分3", "区分4", "区分5", "区分6"]
        ttk.Combobox(
            row3, textvariable=self.var_shien_ku,
            values=ku_values, state="readonly", width=12, font=FONT
        ).pack(side="left")

    def _on_mode_change(self):
        """入力モード切り替え時にUIを切り替える"""
        if self.var_input_mode.get() == "db":
            self.frame_db_mode.pack(fill="x", pady=(0, 8))
            self.frame_manual_mode.pack_forget()
        else:
            self.frame_db_mode.pack_forget()
            self.frame_manual_mode.pack(fill="x", pady=(0, 8))

    def _on_resident_select(self, event):
        """入居者ドロップダウンで選択したときに基本情報を反映する"""
        idx = self.combo_residents.current()
        if idx < 0:
            return
        r = self._residents_data[idx]
        self.var_name.set(r["name"])
        self.var_age.set(str(r["age"]))
        ku = r["disability_grade"]
        self.var_shien_ku.set(f"区分{ku}" if ku else "区分なし")
        self.var_resident_id.set(r["id"])
        self.lbl_resident_info.config(
            text=f"　生年月日：{r['birthdate']}　部屋番号：{r['room_number'] or '—'}"
        )

    def _go_to_step2(self):
        """バリデーション後にステップ2へ進む"""
        if self.var_input_mode.get() == "manual":
            if not self.var_name.get().strip():
                messagebox.showwarning("入力不足", "氏名を入力してください。")
                return
            if not self.var_age.get().strip():
                messagebox.showwarning("入力不足", "年齢を入力してください。")
                return
        else:
            if not self.var_name.get():
                messagebox.showwarning("選択なし", "入居者を選択してください。")
                return
        self._show_frame_step2()

    # -----------------------------------------------------------------------
    # ステップ2：詳細情報入力
    # -----------------------------------------------------------------------

    def _show_frame_step2(self):
        """ステップ2（詳細情報入力）を表示する"""
        self._clear_content()
        self._build_step_indicator(current=2)

        tk.Label(
            self.content,
            text=f"詳細情報の入力　―　{self.var_name.get()} さん",
            font=FONT_TITLE, bg=COLOR_BG, fg=COLOR_HEADER
        ).pack(anchor="w", pady=(10, 10))

        # スクロール可能なエリアを作成
        canvas    = tk.Canvas(self.content, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
        sf        = tk.Frame(canvas, bg=COLOR_BG)  # scroll_frame
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # ① 障害種別
        self._section_label(sf, "① 障害種別（複数選択可）")
        cb_frame = tk.Frame(sf, bg=COLOR_BG)
        cb_frame.pack(anchor="w", padx=20, pady=(0, 12))
        for text, var in [
            ("精神障害", self.var_shogai_seishin),
            ("知的障害", self.var_shogai_chiteki),
            ("身体障害", self.var_shogai_shintai),
        ]:
            tk.Checkbutton(
                cb_frame, text=text, variable=var,
                font=FONT, bg=COLOR_BG, activebackground=COLOR_BG
            ).pack(side="left", padx=10)

        # ② 障害者手帳
        self._section_label(sf, "② 障害者手帳の種類・等級")
        techo_frame = tk.Frame(sf, bg=COLOR_BG)
        techo_frame.pack(anchor="w", padx=20, pady=(0, 12))
        techo_values = [
            "なし",
            "精神1級", "精神2級", "精神3級",
            "療育A（最重度・重度）", "療育B（中度・軽度）",
            "身体1級", "身体2級", "身体3級", "身体4級", "身体5級", "身体6級",
        ]
        ttk.Combobox(
            techo_frame, textvariable=self.var_techo,
            values=techo_values, state="readonly", width=28, font=FONT
        ).pack(side="left")
        tk.Label(
            techo_frame,
            text="　※複数の手帳がある場合は最も重い等級を選択",
            font=FONT_SMALL, bg=COLOR_BG, fg="#777"
        ).pack(side="left")

        # ③ 受給状況
        self._section_label(sf, "③ 現在受給中の制度（当てはまるものをすべて選択）")
        kyufu_frame = tk.Frame(sf, bg=COLOR_BG)
        kyufu_frame.pack(anchor="w", padx=20, pady=(0, 12))
        kyufu_items = [
            ("障害基礎年金1級",          self.var_kyufu_nenkin1),
            ("障害基礎年金2級",          self.var_kyufu_nenkin2),
            ("特別障害者手当",            self.var_kyufu_tokubetsu),
            ("自立支援医療（精神通院）",  self.var_kyufu_jiritsushien),
            ("重度心身障害者医療費助成",  self.var_kyufu_juudo),
            ("生活保護",                  self.var_kyufu_seiho),
        ]
        for i, (text, var) in enumerate(kyufu_items):
            tk.Checkbutton(
                kyufu_frame, text=text, variable=var,
                font=FONT, bg=COLOR_BG, activebackground=COLOR_BG
            ).grid(row=i // 2, column=i % 2, sticky="w", padx=10, pady=2)

        # ④ GH入居予定
        self._section_label(sf, "④ グループホームへの入居予定")
        gh_frame = tk.Frame(sf, bg=COLOR_BG)
        gh_frame.pack(anchor="w", padx=20, pady=(0, 12))
        for label, val in [("はい（入居予定あり）", "はい"), ("いいえ（未定・検討中）", "いいえ")]:
            tk.Radiobutton(
                gh_frame, text=label, variable=self.var_gh_yotei, value=val,
                font=FONT, bg=COLOR_BG, activebackground=COLOR_BG
            ).pack(side="left", padx=10)

        # ⑤ 就労状況
        self._section_label(sf, "⑤ 就労状況")
        shuro_frame = tk.Frame(sf, bg=COLOR_BG)
        shuro_frame.pack(anchor="w", padx=20, pady=(0, 12))
        for label, val in [("就労あり（一般・福祉的就労を含む）", "あり"), ("就労なし", "なし")]:
            tk.Radiobutton(
                shuro_frame, text=label, variable=self.var_shuro, value=val,
                font=FONT, bg=COLOR_BG, activebackground=COLOR_BG
            ).pack(side="left", padx=10)

        tk.Frame(sf, bg=COLOR_BG, height=16).pack()

        # ボタン行（スクロールエリアの外に配置）
        btn_frame = tk.Frame(self.content, bg=COLOR_BG)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(
            btn_frame, text="◀　戻る",
            font=FONT, bg="#888", fg="white",
            relief="flat", cursor="hand2", padx=20, pady=8,
            command=self._show_frame_step1
        ).pack(side="left")
        tk.Button(
            btn_frame, text="制度チェックを実行　▶",
            font=FONT_BOLD, bg=COLOR_GREEN, fg="white",
            relief="flat", cursor="hand2", padx=30, pady=8,
            command=self._run_check
        ).pack(side="right")

    def _section_label(self, parent, text):
        """セクション見出しと区切り線を作成する"""
        tk.Label(
            parent, text=text,
            font=FONT_BOLD, bg=COLOR_BG, fg=COLOR_HEADER
        ).pack(anchor="w", pady=(10, 2))
        tk.Frame(parent, bg=COLOR_PRIMARY, height=1).pack(fill="x", pady=(0, 4))

    def _run_check(self):
        """入力を収集して制度判定を実行し、結果画面へ進む"""
        # 療育A/Bの表示ラベルから内部キーに変換
        techo_raw = self.var_techo.get()
        techo = techo_raw.replace("（最重度・重度）", "").replace("（中度・軽度）", "").strip()

        shogai_types = []
        if self.var_shogai_seishin.get():  shogai_types.append("精神障害")
        if self.var_shogai_chiteki.get():  shogai_types.append("知的障害")
        if self.var_shogai_shintai.get():  shogai_types.append("身体障害")

        kyufu = []
        if self.var_kyufu_nenkin1.get():      kyufu.append("障害基礎年金1級")
        if self.var_kyufu_nenkin2.get():      kyufu.append("障害基礎年金2級")
        if self.var_kyufu_tokubetsu.get():    kyufu.append("特別障害者手当")
        if self.var_kyufu_jiritsushien.get(): kyufu.append("自立支援医療（精神通院）")
        if self.var_kyufu_juudo.get():        kyufu.append("重度心身障害者医療費助成")
        if self.var_kyufu_seiho.get():        kyufu.append("生活保護")

        data = {
            "name":         self.var_name.get(),
            "age":          self.var_age.get(),
            "shien_ku":     self.var_shien_ku.get(),
            "shogai_types": shogai_types,
            "techo":        techo,
            "kyufu":        kyufu,
            "gh_yotei":     self.var_gh_yotei.get(),
            "shuro":        self.var_shuro.get(),
        }

        results = check_eligibility(data)
        self._show_frame_results(data, results)

    # -----------------------------------------------------------------------
    # ステップ3：結果表示
    # -----------------------------------------------------------------------

    def _show_frame_results(self, data, results):
        """チェック結果を表示するフレームを表示する"""
        self._clear_content()
        self._build_step_indicator(current=3)

        tk.Label(
            self.content,
            text=f"チェック結果　―　{data['name']} さん（{data['age']}歳・{data['shien_ku']}）",
            font=FONT_TITLE, bg=COLOR_BG, fg=COLOR_HEADER
        ).pack(anchor="w", pady=(10, 2))

        techo_disp = data["techo"] if data["techo"] != "なし" else "手帳なし"
        types_disp = "・".join(data["shogai_types"]) if data["shogai_types"] else "未選択"
        tk.Label(
            self.content,
            text=f"障害種別：{types_disp}　／　手帳：{techo_disp}　／　GH入居予定：{data['gh_yotei']}",
            font=FONT_SMALL, bg=COLOR_BG, fg="#555"
        ).pack(anchor="w", pady=(0, 8))

        # スクロールエリア
        canvas    = tk.Canvas(self.content, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
        sf        = tk.Frame(canvas, bg=COLOR_BG)
        sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=sf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        if not results:
            tk.Label(
                sf,
                text="✅  現在の情報では、未申請で申請可能な制度は見つかりませんでした。",
                font=FONT_BOLD, bg="#E8F5E9", fg="#2E7D32",
                relief="flat", padx=16, pady=14
            ).pack(fill="x", pady=10, padx=4)
        else:
            tk.Label(
                sf,
                text=f"申請を検討できる制度が {len(results)} 件見つかりました。",
                font=FONT_BOLD, bg=COLOR_BG, fg=COLOR_PRIMARY
            ).pack(anchor="w", pady=(0, 6))
            for item in results:
                self._build_result_card(sf, item)

        # 免責注意
        tk.Label(
            sf,
            text="※ 上記はあくまで参考情報です。実際の申請可否・受給額は"
                 "各担当窓口にご確認ください。",
            font=FONT_SMALL, bg="#FFF8E1", fg="#795548",
            relief="flat", padx=12, pady=8,
            justify="left", wraplength=720
        ).pack(fill="x", pady=(10, 4), padx=4)
        tk.Frame(sf, bg=COLOR_BG, height=12).pack()

        # ボタン行
        btn_frame = tk.Frame(self.content, bg=COLOR_BG)
        btn_frame.pack(fill="x", pady=10)
        tk.Button(
            btn_frame, text="◀　入力に戻る",
            font=FONT, bg="#888", fg="white",
            relief="flat", cursor="hand2", padx=20, pady=8,
            command=self._show_frame_step2
        ).pack(side="left")
        tk.Button(
            btn_frame, text="最初からやり直す",
            font=FONT, bg="#999", fg="white",
            relief="flat", cursor="hand2", padx=20, pady=8,
            command=self._reset
        ).pack(side="left", padx=10)

    def _build_result_card(self, parent, item):
        """制度情報のカードを1枚作成する"""
        # カテゴリ別スタイル
        styles = {
            "申請推奨": {"bg": "#E3F2FD", "accent": "#1565C0", "badge_bg": "#1565C0"},
            "要確認":   {"bg": "#FFF3E0", "accent": "#E65100", "badge_bg": "#E65100"},
            "参考情報": {"bg": "#F3E5F5", "accent": "#6A1B9A", "badge_bg": "#6A1B9A"},
        }
        s = styles.get(item["category"], styles["参考情報"])

        card  = tk.Frame(parent, bg=s["bg"], relief="flat", bd=1)
        card.pack(fill="x", padx=4, pady=5)
        inner = tk.Frame(card, bg=s["bg"])
        inner.pack(fill="x", padx=14, pady=10)

        # バッジ + 制度名
        hrow = tk.Frame(inner, bg=s["bg"])
        hrow.pack(fill="x", pady=(0, 4))
        tk.Label(
            hrow, text=f"  {item['category']}  ",
            font=("MS Gothic", 9, "bold"),
            bg=s["badge_bg"], fg="white", padx=2, pady=2
        ).pack(side="left", padx=(0, 10))
        tk.Label(
            hrow, text=item["name"],
            font=FONT_BOLD, bg=s["bg"], fg=s["accent"]
        ).pack(side="left")

        # 金額
        tk.Label(
            inner, text=f"▸ {item['amount']}",
            font=FONT_BOLD, bg=s["bg"], fg=s["accent"]
        ).pack(anchor="w", pady=(0, 3))

        # 概要
        tk.Label(
            inner, text=item["summary"],
            font=FONT, bg=s["bg"], fg="#333",
            wraplength=700, justify="left"
        ).pack(anchor="w", pady=(0, 3))

        # 申請窓口
        wrow = tk.Frame(inner, bg=s["bg"])
        wrow.pack(anchor="w")
        tk.Label(wrow, text="申請窓口：", font=FONT_BOLD, bg=s["bg"], fg="#555").pack(side="left")
        tk.Label(wrow, text=item["window"],  font=FONT,      bg=s["bg"], fg="#555").pack(side="left")

        # 注意事項
        for note in item.get("notes", []):
            nf = tk.Frame(inner, bg="#FFFDE7")
            nf.pack(fill="x", pady=(5, 0))
            tk.Label(
                nf, text=note,
                font=FONT_SMALL, bg="#FFFDE7", fg="#5D4037",
                wraplength=700, justify="left", padx=8, pady=4
            ).pack(anchor="w")

    def _reset(self):
        """すべての入力をリセットしてステップ1に戻る"""
        self._init_vars()
        self._show_frame_step1()

    # -----------------------------------------------------------------------
    # DB操作
    # -----------------------------------------------------------------------

    def _load_residents(self):
        """
        入居者マスターDBから入居中の入居者一覧を読み込む。
        DBが存在しない・接続できない場合は空リストを返す。
        """
        if not os.path.exists(DB_PATH):
            return []
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cur  = conn.cursor()
            cur.execute("""
                SELECT id, name, birthdate, room_number, disability_grade, status
                FROM residents
                WHERE status = '入居中'
                ORDER BY room_number
            """)
            rows = cur.fetchall()
            conn.close()

            result = []
            for r in rows:
                age = self._calc_age(r["birthdate"])
                result.append({
                    "id":               r["id"],
                    "name":             r["name"],
                    "birthdate":        r["birthdate"] or "",
                    "room_number":      r["room_number"] or "",
                    "disability_grade": r["disability_grade"],
                    "status":           r["status"],
                    "age":              age if age != "" else "不明",
                })
            return result
        except Exception:
            return []

    def _calc_age(self, birthdate_str):
        """生年月日（YYYY-MM-DD）から現在の年齢を計算して返す"""
        if not birthdate_str:
            return ""
        try:
            bd    = date.fromisoformat(birthdate_str)
            today = date.today()
            return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
        except Exception:
            return ""


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    app = CheckerApp()
    app.mainloop()
