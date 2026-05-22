# =============================================================================
# GAS 更新ツール（統合版）
# projects.json に登録したGASプロジェクトをまとめて管理できます。
# 新しいプロジェクトが増えたら projects.json に追記するだけでOKです。
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import webbrowser
import threading
import json
import os

# =============================================================================
# 設定
# =============================================================================
# このファイルと同じフォルダにある projects.json を読み込む
PROJECTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.json")

# フォント定数
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 13, "bold")
FONT_SMALL = ("MS Gothic", 10)

# ウィンドウの高さ（Netlifyステップあり／なし）
HEIGHT_BASE    = 580   # GASのみ
HEIGHT_NETLIFY = 720   # Netlifyステップを含む場合


# =============================================================================
# プロジェクト読み込み
# =============================================================================

def load_projects():
    """projects.json を読み込んでプロジェクト一覧を返す。

    Returns:
        list[dict]: プロジェクト情報のリスト。
                    各要素は {"name": str, "folder": str, "deploy_url": str,
                               "netlify_dir": str}  ※ netlify_dir は省略可
    """
    if not os.path.exists(PROJECTS_FILE):
        messagebox.showerror(
            "エラー",
            f"projects.json が見つかりません。\n{PROJECTS_FILE}"
        )
        return []

    with open(PROJECTS_FILE, encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# メインアプリ
# =============================================================================

class GasPushApp(tk.Tk):
    """GAS更新ツール（統合版）"""

    def __init__(self):
        super().__init__()
        self.title("GAS 更新ツール")
        self.geometry(f"620x{HEIGHT_BASE}")
        self.resizable(False, False)
        self.configure(bg="#F0F4FA")

        # プロジェクト一覧を読み込む
        self.projects = load_projects()
        if not self.projects:
            self.destroy()
            return

        self._build_ui()
        # 初期選択プロジェクトに応じてNetlifyステップの表示を更新する
        self._on_project_changed()

    def _build_ui(self):
        """画面全体を組み立てる"""

        # ---- タイトルバー ----
        tk.Label(
            self,
            text="GAS 更新ツール",
            font=FONT_TITLE, bg="#4A6FA5", fg="white",
            padx=10, pady=12
        ).pack(fill="x")

        # ---- プロジェクト選択 ----
        sel_frame = tk.Frame(self, bg="#F0F4FA")
        sel_frame.pack(fill="x", padx=20, pady=(16, 4))

        tk.Label(
            sel_frame,
            text="更新するプロジェクトを選んでください：",
            font=FONT_BOLD, bg="#F0F4FA"
        ).pack(anchor="w")

        # コンボボックス（プルダウン選択）でプロジェクトを選ぶ
        self.project_var = tk.StringVar()
        names = [p["name"] for p in self.projects]
        self.combo = ttk.Combobox(
            sel_frame,
            textvariable=self.project_var,
            values=names,
            state="readonly",
            font=FONT,
            width=40
        )
        self.combo.pack(anchor="w", pady=(6, 0))
        self.combo.current(0)
        # プロジェクトを切り替えたときにNetlifyステップの表示を更新する
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._on_project_changed())

        # ---- Step1：Push ----
        frame1 = tk.LabelFrame(
            self,
            text="  Step 1：Pushする（修正をGoogleに送る）  ",
            font=FONT_BOLD, bg="#F0F4FA", fg="#2c5282",
            padx=16, pady=12
        )
        frame1.pack(fill="x", padx=20, pady=(14, 0))

        tk.Label(
            frame1,
            text="ボタンを押すと、修正したコードをGoogleに送ります。",
            font=FONT, bg="#F0F4FA", justify="left"
        ).pack(anchor="w", pady=(0, 8))

        self.push_btn = tk.Button(
            frame1,
            text="① Pushする",
            font=FONT_BOLD, bg="#4A6FA5", fg="white",
            relief="flat", cursor="hand2",
            padx=20, pady=10,
            command=self._on_push
        )
        self.push_btn.pack(anchor="w")

        # Push結果メッセージ
        self.result_label = tk.Label(
            frame1,
            text="",
            font=FONT, bg="#F0F4FA",
            justify="left", wraplength=500
        )
        self.result_label.pack(anchor="w", pady=(8, 0))

        # ---- Step2：GASデプロイ ----
        frame2 = tk.LabelFrame(
            self,
            text="  Step 2：GASデプロイする（スクリプトに反映する）  ",
            font=FONT_BOLD, bg="#F0F4FA", fg="#276749",
            padx=16, pady=12
        )
        frame2.pack(fill="x", padx=20, pady=(12, 0))

        tk.Label(
            frame2,
            text=(
                "ボタンを押すとブラウザが開きます。\n"
                "開いたら：\n"
                "  「デプロイ」→「デプロイを管理」→ 鉛筆マーク\n"
                "  → バージョン「新しいバージョン」→「デプロイ」"
            ),
            font=FONT, bg="#F0F4FA", justify="left"
        ).pack(anchor="w", pady=(0, 8))

        self.deploy_btn = tk.Button(
            frame2,
            text="② GASデプロイ画面を開く",
            font=FONT_BOLD, bg="#48bb78", fg="white",
            relief="flat", cursor="hand2",
            padx=20, pady=10,
            command=self._on_deploy
        )
        self.deploy_btn.pack(anchor="w")

        # ---- Step3：Netlifyデプロイ（netlify_dir があるプロジェクトのみ表示）----
        self.frame3 = tk.LabelFrame(
            self,
            text="  Step 3：Netlifyに送る（スマホに反映する）  ",
            font=FONT_BOLD, bg="#F0F4FA", fg="#6B46C1",
            padx=16, pady=12
        )
        # ※ pack はここではしない。_on_project_changed() で表示・非表示を切り替える

        tk.Label(
            self.frame3,
            text="ボタンを押すと、修正したHTMLファイルをスマホ向けに公開します。",
            font=FONT, bg="#F0F4FA", justify="left"
        ).pack(anchor="w", pady=(0, 8))

        self.netlify_btn = tk.Button(
            self.frame3,
            text="③ Netlifyに送る",
            font=FONT_BOLD, bg="#805AD5", fg="white",
            relief="flat", cursor="hand2",
            padx=20, pady=10,
            command=self._on_netlify_deploy
        )
        self.netlify_btn.pack(anchor="w")

        # Netlifyデプロイ結果メッセージ
        self.netlify_result_label = tk.Label(
            self.frame3,
            text="",
            font=FONT, bg="#F0F4FA",
            justify="left", wraplength=500
        )
        self.netlify_result_label.pack(anchor="w", pady=(8, 0))

        # ---- 注意書き ----
        self.note_label = tk.Label(
            self,
            text="※ Step1が完了してからStep2を押してください。",
            font=FONT_SMALL, bg="#F0F4FA", fg="#718096"
        )
        self.note_label.pack(pady=(12, 0))

        # ---- projects.json 編集ボタン ----
        tk.Button(
            self,
            text="projects.json を開く（プロジェクト追加・編集）",
            font=FONT_SMALL, bg="#EDF2F7", fg="#4A5568",
            relief="flat", cursor="hand2",
            padx=10, pady=6,
            command=self._open_projects_json
        ).pack(pady=(12, 0))

    def _on_project_changed(self):
        """プロジェクト選択が変わったときの処理。
        Netlifyステップの表示・非表示とウィンドウサイズを切り替える。
        """
        project = self._get_selected_project()
        has_netlify = bool(project and project.get("netlify_dir"))

        if has_netlify:
            # Step3を表示する（まだ表示されていない場合のみ pack する）
            if not self.frame3.winfo_ismapped():
                self.frame3.pack(fill="x", padx=20, pady=(12, 0))
                self.note_label.pack_forget()
                self.note_label.pack(pady=(12, 0))
            self.geometry(f"620x{HEIGHT_NETLIFY}")
        else:
            # Step3を非表示にする
            self.frame3.pack_forget()
            self.geometry(f"620x{HEIGHT_BASE}")

    def _get_selected_project(self):
        """現在選択中のプロジェクト情報を返す。

        Returns:
            dict: {"name": str, "folder": str, "deploy_url": str,
                   "netlify_dir": str（省略可）}
        """
        name = self.project_var.get()
        for p in self.projects:
            if p["name"] == name:
                return p
        return None

    def _on_push(self):
        """①Pushボタンが押されたときの処理"""
        project = self._get_selected_project()
        if not project:
            messagebox.showerror("エラー", "プロジェクトが選択されていません。")
            return

        self.push_btn.config(state="disabled", text="送信中...")
        self.result_label.config(text="Googleに送信しています...", fg="#4A6FA5")
        self.update()

        # 画面が固まらないよう別スレッドで実行する
        thread = threading.Thread(target=self._run_push, args=(project,))
        thread.daemon = True
        thread.start()

    def _run_push(self, project):
        """clasp push --force を実行する（バックグラウンド処理）。

        Args:
            project (dict): 対象プロジェクトの情報
        """
        try:
            result = subprocess.run(
                ["clasp", "push", "--force"],
                cwd=project["folder"],
                capture_output=True,
                timeout=60,
                shell=True  # Windowsで clasp コマンドを認識させるために必要
            )
            stdout = result.stdout.decode("utf-8", errors="ignore")
            stderr = result.stderr.decode("utf-8", errors="ignore")

            if result.returncode == 0:
                self.after(0, self._push_success)
            else:
                self.after(0, self._push_error, stderr or stdout)

        except subprocess.TimeoutExpired:
            self.after(0, self._push_error, "タイムアウトしました。ネットワークを確認してください。")
        except Exception as e:
            self.after(0, self._push_error, str(e))

    def _push_success(self):
        """Push成功時の画面更新"""
        self.push_btn.config(state="normal", text="① Pushする")
        self.result_label.config(
            text="✓ 送信成功！次はStep2のボタンを押してください。",
            fg="#276749"
        )

    def _push_error(self, error_msg):
        """Push失敗時の画面更新"""
        self.push_btn.config(state="normal", text="① Pushする")
        self.result_label.config(
            text=f"✗ エラーが発生しました:\n{error_msg}",
            fg="#c53030"
        )

    def _on_deploy(self):
        """②GASデプロイ画面を開くボタンが押されたときの処理"""
        project = self._get_selected_project()
        if not project:
            messagebox.showerror("エラー", "プロジェクトが選択されていません。")
            return
        webbrowser.open(project["deploy_url"])

    def _on_netlify_deploy(self):
        """③Netlifyに送るボタンが押されたときの処理"""
        project = self._get_selected_project()
        if not project or not project.get("netlify_dir"):
            messagebox.showerror("エラー", "Netlifyの設定がありません。")
            return

        self.netlify_btn.config(state="disabled", text="送信中...")
        self.netlify_result_label.config(text="Netlifyに送信しています...", fg="#6B46C1")
        self.update()

        # 画面が固まらないよう別スレッドで実行する
        thread = threading.Thread(target=self._run_netlify_deploy, args=(project,))
        thread.daemon = True
        thread.start()

    def _get_netlify_token(self):
        """Netlify設定ファイルから認証トークンを読み込んで返す。

        Returns:
            str | None: トークン文字列。見つからない場合は None
        """
        config_path = os.path.join(
            os.environ.get("APPDATA", ""),
            "netlify", "Config", "config.json"
        )
        if not os.path.exists(config_path):
            return None
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            # users の中から最初のユーザーのトークンを取得する
            for user in data.get("users", {}).values():
                token = user.get("auth", {}).get("token")
                if token:
                    return token
        except Exception:
            pass
        return None

    def _run_netlify_deploy(self, project):
        """netlify deploy --prod を実行する（バックグラウンド処理）。

        Args:
            project (dict): 対象プロジェクトの情報
        """
        try:
            # 環境変数を現在のプロセスから引き継ぎ、トークンを追加する
            env = os.environ.copy()
            token = self._get_netlify_token()
            if token:
                env["NETLIFY_AUTH_TOKEN"] = token

            result = subprocess.run(
                ["netlify", "deploy", "--prod", "--dir=."],
                cwd=project["netlify_dir"],
                capture_output=True,
                timeout=120,
                shell=True,  # Windowsで netlify コマンドを認識させるために必要
                env=env
            )
            stdout = result.stdout.decode("utf-8", errors="ignore")
            stderr = result.stderr.decode("utf-8", errors="ignore")

            if result.returncode == 0:
                self.after(0, self._netlify_success)
            else:
                self.after(0, self._netlify_error, stderr or stdout)

        except subprocess.TimeoutExpired:
            self.after(0, self._netlify_error, "タイムアウトしました。ネットワークを確認してください。")
        except Exception as e:
            self.after(0, self._netlify_error, str(e))

    def _netlify_success(self):
        """Netlifyデプロイ成功時の画面更新"""
        self.netlify_btn.config(state="normal", text="③ Netlifyに送る")
        self.netlify_result_label.config(
            text="✓ スマホへの反映が完了しました！",
            fg="#276749"
        )

    def _netlify_error(self, error_msg):
        """Netlifyデプロイ失敗時の画面更新"""
        self.netlify_btn.config(state="normal", text="③ Netlifyに送る")
        self.netlify_result_label.config(
            text=f"✗ エラーが発生しました:\n{error_msg}",
            fg="#c53030"
        )

    def _open_projects_json(self):
        """projects.json をメモ帳で開く（プロジェクトの追加・編集用）"""
        os.startfile(PROJECTS_FILE)


# =============================================================================
# 起動
# =============================================================================
if __name__ == "__main__":
    app = GasPushApp()
    app.mainloop()
