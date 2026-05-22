# =============================================================================
# 通院記録アプリ
# グループホーム 入居者別通院・処方管理システム
# =============================================================================

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
import shutil
import glob
import subprocess
import sys
import calendar
from datetime import datetime, date, timedelta

# =============================================================================
# パス設定
# =============================================================================
BASE_DIR = r"C:\Users\Public\gh_system"
PRIVATE_ROOT = r"C:\GH_Data"
DATA_DIR     = os.path.join(PRIVATE_ROOT, "data")
BACKUP_DIR   = os.path.join(PRIVATE_ROOT, "visit_backups")
RESIDENTS_DB = os.path.join(DATA_DIR, "residents.db")
VISIT_DB     = os.path.join(DATA_DIR, "visits.db")
MEDICINE_DB  = os.path.join(DATA_DIR, "medicine.db")
MAX_BACKUPS  = 10

# 処方対象の時間帯（薬アプリと共通）— 朝・昼・夕・寝る前の順で統一
TIME_SLOTS = ["朝", "昼", "夕", "寝る前"]

# 各時間帯の服薬時刻（薬アプリと共通：この時刻を過ぎたら当日分を消費済みとみなす）
SLOT_TIMES = {"朝": "07:00", "昼": "12:00", "夕": "18:00", "寝る前": "21:00"}

# フォント設定（日本語対応）
FONT       = ("MS Gothic", 11)
FONT_BOLD  = ("MS Gothic", 11, "bold")
FONT_TITLE = ("MS Gothic", 14, "bold")
FONT_SMALL = ("MS Gothic", 10)

# 色設定
COLOR_BG        = "#F5F7FA"
COLOR_HEADER    = "#2E7D6E"       # 医療系のグリーン
COLOR_HEADER_FG = "#FFFFFF"
COLOR_ROW_ODD   = "#FFFFFF"
COLOR_ROW_EVEN  = "#F0F7F5"
COLOR_ACCENT    = "#2E7D6E"
COLOR_BTN       = "#2E7D6E"
COLOR_BTN_FG    = "#FFFFFF"
COLOR_WARN      = "#E74C3C"
COLOR_SUB_BTN   = "#7F8C8D"

# =============================================================================
# 初期セットアップ
# =============================================================================

def setup():
    """アプリ起動時にフォルダとDBを準備する"""
    os.makedirs(DATA_DIR,   exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    _create_db()
    _backup_db()


def _create_db():
    """visits.db のテーブルを作成する（なければ）"""
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()

    # 病院マスター（入居者ごとに複数登録可能）
    c.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id INTEGER NOT NULL,
            name        TEXT    NOT NULL,
            department  TEXT    DEFAULT '',
            memo        TEXT    DEFAULT '',
            is_active   INTEGER DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 通院記録
    c.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            resident_id           INTEGER NOT NULL,
            hospital_id           INTEGER NOT NULL,
            visit_date            TEXT    NOT NULL,
            content               TEXT    DEFAULT '',
            prescription_changed  INTEGER DEFAULT 0,
            next_visit_date       TEXT    DEFAULT NULL,
            memo                  TEXT    DEFAULT '',
            created_at            TEXT    DEFAULT (datetime('now', 'localtime')),
            updated_at            TEXT    DEFAULT (datetime('now', 'localtime'))
        )
    """)

    # 処方記録（通院ごとの時間帯別処方日数）
    # is_temp=0: 定期処方　is_temp=1: 臨時薬
    c.execute("""
        CREATE TABLE IF NOT EXISTS visit_prescriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_id        INTEGER NOT NULL,
            resident_id     INTEGER NOT NULL,
            time_slot       TEXT    NOT NULL,
            days_prescribed INTEGER NOT NULL DEFAULT 0,
            is_temp         INTEGER NOT NULL DEFAULT 0
        )
    """)

    # 後から追加した列の移行処理（列が既にある場合はスキップ）
    for col_def in [
        "ALTER TABLE visits ADD COLUMN appointment_time      TEXT DEFAULT NULL",
        "ALTER TABLE visits ADD COLUMN next_appointment_time TEXT DEFAULT NULL",
        "ALTER TABLE visits ADD COLUMN companion             TEXT DEFAULT NULL",
        # 臨時薬の薬名（時間帯・日数は visit_prescriptions の is_temp=1 行で管理）
        "ALTER TABLE visits ADD COLUMN temp_medicine            TEXT    DEFAULT NULL",
        # 臨時薬の飲み始め日（処方日と異なる場合がある）
        "ALTER TABLE visits ADD COLUMN temp_medicine_start_date TEXT    DEFAULT NULL",
        # 旧列（単一スロット方式の残骸。新コードでは読み書きしない）
        "ALTER TABLE visits ADD COLUMN temp_medicine_slot TEXT    DEFAULT NULL",
        "ALTER TABLE visits ADD COLUMN temp_medicine_days INTEGER DEFAULT 0",
        # visit_prescriptions に is_temp 列を追加（既存DBへの移行）
        "ALTER TABLE visit_prescriptions ADD COLUMN is_temp INTEGER NOT NULL DEFAULT 0",
        # 臨時薬の時間帯ごとの飲み始め日（スロット別に管理するための列）
        "ALTER TABLE visit_prescriptions ADD COLUMN start_date TEXT DEFAULT NULL",
        # 臨時薬の薬名（複数薬対応のため visit_prescriptions 側で管理する）
        "ALTER TABLE visit_prescriptions ADD COLUMN medicine_name TEXT DEFAULT NULL",
    ]:
        try:
            c.execute(col_def)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()


def _backup_db():
    """起動時に visits.db をバックアップする（最大10個保持）"""
    if not os.path.exists(VISIT_DB):
        return
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"backup_{timestamp}.db")
    shutil.copy2(VISIT_DB, backup_path)

    backups = sorted(glob.glob(os.path.join(BACKUP_DIR, "backup_*.db")))
    while len(backups) > MAX_BACKUPS:
        os.remove(backups.pop(0))


# =============================================================================
# DB操作ヘルパー — 入居者
# =============================================================================

def get_residents():
    """residents.db から入居中の入居者一覧を取得する"""
    if not os.path.exists(RESIDENTS_DB):
        messagebox.showerror("エラー", f"入居者マスターDBが見つかりません。\n{RESIDENTS_DB}")
        return []
    try:
        conn = sqlite3.connect(RESIDENTS_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id, name FROM residents WHERE status = '入居中' ORDER BY id")
        rows = c.fetchall()
        conn.close()
        return [(r["id"], r["name"]) for r in rows]
    except Exception as e:
        messagebox.showerror("エラー", f"入居者情報の読み込みに失敗しました。\n{e}")
        return []


# =============================================================================
# DB操作ヘルパー — 病院
# =============================================================================

def get_hospitals(resident_id):
    """指定入居者の病院一覧を取得する（有効なもののみ）"""
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, name, department, memo
        FROM hospitals
        WHERE resident_id = ? AND is_active = 1
        ORDER BY id
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_hospital(resident_id, name, department, memo):
    """病院を追加する"""
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()
    c.execute("""
        INSERT INTO hospitals (resident_id, name, department, memo)
        VALUES (?, ?, ?, ?)
    """, (resident_id, name, department or None, memo or None))
    conn.commit()
    conn.close()


def update_hospital(hospital_id, name, department, memo):
    """病院情報を更新する"""
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()
    c.execute("""
        UPDATE hospitals SET name = ?, department = ?, memo = ?
        WHERE id = ?
    """, (name, department or None, memo or None, hospital_id))
    conn.commit()
    conn.close()


def delete_hospital(hospital_id):
    """病院を論理削除する（過去の記録は残す）"""
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()
    c.execute("UPDATE hospitals SET is_active = 0 WHERE id = ?", (hospital_id,))
    conn.commit()
    conn.close()


# =============================================================================
# DB操作ヘルパー — 通院記録
# =============================================================================

def get_visits(resident_id, hospital_id):
    """指定入居者・病院の通院記録を新しい順で取得する"""
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, visit_date, content, prescription_changed,
               next_visit_date, memo
        FROM visits
        WHERE resident_id = ? AND hospital_id = ?
        ORDER BY visit_date DESC
    """, (resident_id, hospital_id))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_visit(visit_id):
    """通院記録1件を取得する"""
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM visits WHERE id = ?", (visit_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_visit_prescriptions(visit_id):
    """通院記録に紐づく定期処方の日数を取得する（is_temp=0 の行のみ）"""
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT time_slot, days_prescribed
        FROM visit_prescriptions
        WHERE visit_id = ? AND is_temp = 0
    """, (visit_id,))
    rows = c.fetchall()
    conn.close()
    return {r["time_slot"]: r["days_prescribed"] for r in rows}


def get_temp_prescriptions(visit_id):
    """通院記録に紐づく臨時薬の日数を取得する（is_temp=1 の行のみ）"""
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT time_slot, days_prescribed
        FROM visit_prescriptions
        WHERE visit_id = ? AND is_temp = 1
    """, (visit_id,))
    rows = c.fetchall()
    conn.close()
    return {r["time_slot"]: r["days_prescribed"] for r in rows}


def get_temp_presc_details(visit_id):
    """
    通院記録に紐づく臨時薬の詳細を薬名ごとにグループ化して返す（is_temp=1 の行のみ）。
    戻り値: [{"name": str, "slots": {"朝": {"days": 30, "start_date": "2026-05-14"}, ...}}, ...]
    medicine_name が NULL の旧データは name="" として扱う。
    挿入順（ROWID順）を維持する。
    """
    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT medicine_name, time_slot, days_prescribed, start_date
        FROM visit_prescriptions
        WHERE visit_id = ? AND is_temp = 1
        ORDER BY ROWID
    """, (visit_id,))
    rows = c.fetchall()
    conn.close()

    medicines = {}
    order = []
    for r in rows:
        name = r["medicine_name"] or ""
        if name not in medicines:
            medicines[name] = {}
            order.append(name)
        medicines[name][r["time_slot"]] = {
            "days": r["days_prescribed"],
            "start_date": r["start_date"],
        }
    return [{"name": n, "slots": medicines[n]} for n in order]


def save_visit(resident_id, hospital_id, visit_date, content,
               prescription_changed, next_visit_date, memo,
               prescriptions, visit_id=None,
               next_appointment_time=None, companion=None,
               temp_medicines=None):
    """
    通院記録を保存する。
    prescriptions : {"朝": 28, ...}  定期処方の時間帯別日数。
    temp_medicines: 臨時薬リスト。
        [{"name": "薬名", "slots": {"朝": {"days": 30, "start_date": "2026-05-14"}, ...}}, ...]
    visit_id が None なら新規登録、あれば更新。
    """
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # visits.temp_medicine: 薬名のリスト（後方互換の検索フィルター用）
    all_temp_names = "、".join(
        m["name"] for m in (temp_medicines or []) if m["name"]
    ) or None

    if visit_id is None:
        # 新規登録
        c.execute("""
            INSERT INTO visits
                (resident_id, hospital_id, visit_date, content,
                 prescription_changed, next_visit_date, next_appointment_time,
                 companion, memo, temp_medicine, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (resident_id, hospital_id, visit_date, content or None,
              int(prescription_changed), next_visit_date or None,
              next_appointment_time or None, companion or None,
              memo or None, all_temp_names, now))
        visit_id = c.lastrowid
    else:
        # 更新（既存の処方記録を削除してから再登録）
        c.execute("""
            UPDATE visits SET
                visit_date            = ?,
                content               = ?,
                prescription_changed  = ?,
                next_visit_date       = ?,
                next_appointment_time = ?,
                companion             = ?,
                memo                  = ?,
                temp_medicine         = ?,
                updated_at            = ?
            WHERE id = ?
        """, (visit_date, content or None, int(prescription_changed),
              next_visit_date or None, next_appointment_time or None,
              companion or None, memo or None, all_temp_names, now, visit_id))
        c.execute("DELETE FROM visit_prescriptions WHERE visit_id = ?", (visit_id,))

    # 定期処方を登録（is_temp=0）
    for slot, days in prescriptions.items():
        if days > 0:
            c.execute("""
                INSERT INTO visit_prescriptions
                    (visit_id, resident_id, time_slot, days_prescribed, is_temp)
                VALUES (?, ?, ?, ?, 0)
            """, (visit_id, resident_id, slot, days))

    # 臨時薬を登録（is_temp=1）。薬名・スロット・飲み始め日も保存する
    for med in (temp_medicines or []):
        for slot, sd in med["slots"].items():
            if sd["days"] > 0:
                c.execute("""
                    INSERT INTO visit_prescriptions
                        (visit_id, resident_id, time_slot, days_prescribed,
                         is_temp, start_date, medicine_name)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                """, (visit_id, resident_id, slot, sd["days"],
                      sd.get("start_date"), med["name"] or None))

    conn.commit()
    conn.close()
    return visit_id


def delete_visit(visit_id):
    """通院記録と紐づく処方記録を削除する"""
    conn = sqlite3.connect(VISIT_DB)
    c = conn.cursor()
    c.execute("DELETE FROM visit_prescriptions WHERE visit_id = ?", (visit_id,))
    c.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
    conn.commit()
    conn.close()


# =============================================================================
# 薬在庫管理DB連携
# =============================================================================

def add_stock_from_prescription(resident_id, visit_date, prescriptions):
    """
    処方記録から薬の在庫（日数）を加算する。
    medicine.db の medicine_inventory テーブルを更新する。
    prescriptions = {"朝": 28, "夕": 28, ...}
    """
    if not os.path.exists(MEDICINE_DB):
        return  # 薬アプリ未使用の場合はスキップ

    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slot, days in prescriptions.items():
        if days <= 0:
            continue

        # 現在の在庫を取得（なければ0として扱う）
        c.execute("""
            SELECT stock_days FROM medicine_inventory
            WHERE resident_id = ? AND time_slot = ?
        """, (resident_id, slot))
        row = c.fetchone()
        current = row[0] if row else 0
        new_days = current + days

        # UPSERT（あれば更新、なければ新規）
        # 既存レコードの updated_at は更新しない（薬アプリ側の自動差し引き基準日を壊さないため）
        c.execute("""
            INSERT INTO medicine_inventory
                (resident_id, time_slot, calendar_days, stock_days, updated_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(resident_id, time_slot) DO UPDATE SET
                stock_days = excluded.stock_days
        """, (resident_id, slot, new_days, now))

        # 操作履歴にも記録
        c.execute("""
            INSERT INTO medicine_history
                (resident_id, time_slot, operation_type, quantity, note)
            VALUES (?, ?, '処方', ?, ?)
        """, (resident_id, slot, days,
              f"{visit_date} 処方 {days}日分追加"))

    conn.commit()
    conn.close()


def remove_stock_from_prescription(resident_id, prescriptions):
    """
    通院記録を削除・修正するときに、以前加算した在庫を元に戻す。
    prescriptions = {"朝": 28, "夕": 28, ...}
    """
    if not os.path.exists(MEDICINE_DB):
        return

    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slot, days in prescriptions.items():
        if days <= 0:
            continue
        c.execute("""
            SELECT stock_days FROM medicine_inventory
            WHERE resident_id = ? AND time_slot = ?
        """, (resident_id, slot))
        row = c.fetchone()
        if row:
            new_days = max(0, row[0] - days)
            # updated_at は更新しない（薬アプリ側の自動差し引き基準日を壊さないため）
            c.execute("""
                UPDATE medicine_inventory
                SET stock_days = ?
                WHERE resident_id = ? AND time_slot = ?
            """, (new_days, resident_id, slot))
            c.execute("""
                INSERT INTO medicine_history
                    (resident_id, time_slot, operation_type, quantity, note)
                VALUES (?, ?, '処方取消', ?, ?)
            """, (resident_id, slot, days, f"{days}日分を処方取消"))

    conn.commit()
    conn.close()


def add_temp_stock(resident_id, visit_date, temp_prescriptions, medicine_name):
    """
    臨時薬の在庫（日数）を薬管理DBの残薬ボックスに加算する。
    temp_prescriptions = {"朝": 3, "昼": 3, ...} の形式で受け取る。
    medicine_name: 履歴に残す薬名テキスト。
    """
    if not temp_prescriptions or not os.path.exists(MEDICINE_DB):
        return

    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slot, days in temp_prescriptions.items():
        if days <= 0:
            continue
        c.execute("""
            SELECT stock_days FROM medicine_inventory
            WHERE resident_id = ? AND time_slot = ?
        """, (resident_id, slot))
        row = c.fetchone()
        new_days = (row[0] if row else 0) + days

        c.execute("""
            INSERT INTO medicine_inventory
                (resident_id, time_slot, calendar_days, stock_days, updated_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(resident_id, time_slot) DO UPDATE SET
                stock_days = excluded.stock_days,
                updated_at = excluded.updated_at
        """, (resident_id, slot, new_days, now))

        c.execute("""
            INSERT INTO medicine_history
                (resident_id, time_slot, operation_type, quantity, note)
            VALUES (?, ?, '処方', ?, ?)
        """, (resident_id, slot, days,
              f"{visit_date} 臨時薬「{medicine_name}」{days}日分追加"))

    conn.commit()
    conn.close()


def remove_temp_stock(resident_id, temp_prescriptions, medicine_name=""):
    """
    臨時薬の在庫を薬管理DBの残薬ボックスから差し引く。
    通院記録を削除するときに使う（編集時は update_stock_difference を使うこと）。
    temp_prescriptions = {"朝": 3, "昼": 3, ...} の形式で受け取る。
    """
    if not temp_prescriptions or not os.path.exists(MEDICINE_DB):
        return

    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slot, days in temp_prescriptions.items():
        if days <= 0:
            continue
        c.execute("""
            SELECT stock_days FROM medicine_inventory
            WHERE resident_id = ? AND time_slot = ?
        """, (resident_id, slot))
        row = c.fetchone()
        if row:
            new_days = max(0, row[0] - days)
            c.execute("""
                UPDATE medicine_inventory
                SET stock_days = ?, updated_at = ?
                WHERE resident_id = ? AND time_slot = ?
            """, (new_days, now, resident_id, slot))
            note = (f"臨時薬「{medicine_name}」{days}日分を処方取消"
                    if medicine_name else f"{days}日分を処方取消")
            c.execute("""
                INSERT INTO medicine_history
                    (resident_id, time_slot, operation_type, quantity, note)
                VALUES (?, ?, '処方取消', ?, ?)
            """, (resident_id, slot, days, note))

    conn.commit()
    conn.close()


def update_stock_difference(resident_id, visit_date, old_presc, new_presc,
                             label="処方", medicine_name=""):
    """
    処方日数の「変更差分だけ」在庫を更新する。
    編集時に使い、変化のない時間帯は在庫も履歴も一切変更しない。

    old_presc / new_presc = {"朝": 28, "夕": 28, ...} の形式。
    label: 履歴の「内容」欄に使うラベル（例：「処方」「臨時薬」）。
    """
    if not os.path.exists(MEDICINE_DB):
        return

    all_slots = set(list(old_presc.keys()) + list(new_presc.keys()))
    conn = sqlite3.connect(MEDICINE_DB)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for slot in all_slots:
        old_days = old_presc.get(slot, 0)
        new_days = new_presc.get(slot, 0)
        diff = new_days - old_days

        if diff == 0:
            continue  # 変更なし → 何もしない

        # 在庫を差分だけ増減する
        c.execute("""
            SELECT stock_days FROM medicine_inventory
            WHERE resident_id = ? AND time_slot = ?
        """, (resident_id, slot))
        row = c.fetchone()
        current   = row[0] if row else 0
        new_stock = max(0, current + diff)

        c.execute("""
            INSERT INTO medicine_inventory
                (resident_id, time_slot, calendar_days, stock_days, updated_at)
            VALUES (?, ?, 0, ?, ?)
            ON CONFLICT(resident_id, time_slot) DO UPDATE SET
                stock_days = excluded.stock_days,
                updated_at = excluded.updated_at
        """, (resident_id, slot, new_stock, now))

        # 履歴は「差分」を1行だけ記録する（取消＋追加のペアにしない）
        if diff > 0:
            op   = "処方"
            sign = f"+{diff}"
        else:
            op   = "処方取消"
            sign = str(diff)

        if medicine_name:
            note = f"{visit_date} {label}「{medicine_name}」修正 {sign}日（{slot}）"
        else:
            note = f"{visit_date} {label}修正 {sign}日（{slot}）"

        c.execute("""
            INSERT INTO medicine_history
                (resident_id, time_slot, operation_type, quantity, note)
            VALUES (?, ?, ?, ?, ?)
        """, (resident_id, slot, op, abs(diff), note))

    conn.commit()
    conn.close()


def get_latest_temp_medicine(resident_id, hospital_id):
    """
    指定入居者・病院の直近通院記録から臨時薬情報を取得する。
    臨時薬が登録されている最新の通院記録を1件返す。
    戻り値: {"visit_date": str,
             "medicines": [{"name": str, "slots": {...}}, ...]} or None
    """
    if not os.path.exists(VISIT_DB):
        return None

    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT id, visit_date
        FROM visits
        WHERE resident_id = ? AND hospital_id = ?
          AND temp_medicine IS NOT NULL AND temp_medicine != ''
        ORDER BY visit_date DESC, id DESC
        LIMIT 1
    """, (resident_id, hospital_id))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    # 薬名ごとにグループ化された臨時薬リストを取得する
    medicines = get_temp_presc_details(row["id"])
    if not medicines or not any(
        any(sd["days"] > 0 for sd in m["slots"].values()) for m in medicines
    ):
        return None

    return {"visit_date": row["visit_date"], "medicines": medicines}


def get_upcoming_visits():
    """
    次回通院予定日が設定されている記録を全入居者分まとめて取得する。
    過去の予定も含めて日付の近い順に返す。
    戻り値: [{"resident_name": ..., "hospital_name": ..., "next_visit_date": ..., "days_left": ...}, ...]
    """
    if not os.path.exists(VISIT_DB) or not os.path.exists(RESIDENTS_DB):
        return []

    conn = sqlite3.connect(VISIT_DB)
    conn.row_factory = sqlite3.Row

    # residents.db をアタッチして入居者名を結合する
    conn.execute(f"ATTACH DATABASE '{RESIDENTS_DB}' AS rdb")

    c = conn.cursor()
    c.execute("""
        SELECT
            r.name                  AS resident_name,
            h.name                  AS hospital_name,
            h.department            AS department,
            v.next_visit_date,
            v.next_appointment_time,
            v.visit_date
        FROM visits v
        JOIN hospitals h ON v.hospital_id = h.id
        JOIN rdb.residents r ON v.resident_id = r.id
        WHERE v.next_visit_date IS NOT NULL AND v.next_visit_date != ''
          AND v.id IN (
              -- 各（入居者×病院）の最新記録だけを対象にする
              SELECT MAX(id) FROM visits GROUP BY resident_id, hospital_id
          )
        ORDER BY v.next_visit_date ASC
    """)
    rows = c.fetchall()
    conn.close()

    today = date.today()
    result = []
    for r in rows:
        try:
            nd = date.fromisoformat(r["next_visit_date"])
            days_left = (nd - today).days
        except ValueError:
            continue
        hospital = r["hospital_name"]
        if r["department"]:
            hospital += f"（{r['department']}）"
        result.append({
            "resident_name":        r["resident_name"],
            "hospital_name":        hospital,
            "next_visit_date":      r["next_visit_date"],
            "next_appointment_time": r["next_appointment_time"] or "",
            "days_left":            days_left,
        })
    return result


def _count_consumed_since(updated_at_str, slot):
    """
    updated_at から現時点までに指定時間帯の服薬時刻を何回通過したかを返す。
    薬アプリと同じロジックでカレンダー日数を自動補正するために使用。
    """
    if not updated_at_str or slot not in SLOT_TIMES:
        return 0
    try:
        updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return 0
    h, m = int(SLOT_TIMES[slot][:2]), int(SLOT_TIMES[slot][3:])
    now = datetime.now()
    consume_dt = updated_at.replace(hour=h, minute=m, second=0, microsecond=0)
    if consume_dt <= updated_at:
        consume_dt += timedelta(days=1)
    if consume_dt > now:
        return 0
    return (now - consume_dt).days + 1


def get_medicine_summary(resident_id):
    """
    薬の在庫サマリーを取得する（在庫管理アプリのDBから）。
    薬アプリと同じ自動補正ロジックを適用して正確な残日数を返す。
    戻り値: {"朝": {"total_days": 18, "until": "6月24日"}, ...}
    """
    if not os.path.exists(MEDICINE_DB):
        return {}

    conn = sqlite3.connect(MEDICINE_DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT ms.time_slot, mi.calendar_days, mi.stock_days, mi.updated_at
        FROM medicine_settings ms
        LEFT JOIN medicine_inventory mi
            ON ms.resident_id = mi.resident_id AND ms.time_slot = mi.time_slot
        WHERE ms.resident_id = ? AND ms.enabled = 1
    """, (resident_id,))
    rows = c.fetchall()
    conn.close()

    # TIME_SLOTS の順（朝・昼・夕・寝る前）で並べる
    slot_order = {s: i for i, s in enumerate(TIME_SLOTS)}
    rows = sorted(rows, key=lambda r: slot_order.get(r["time_slot"], 99))

    result = {}
    now = datetime.now()
    for r in rows:
        cal   = r["calendar_days"] or 0
        stock = r["stock_days"]    or 0

        # 薬アプリと同じ自動補正：更新日時から今まで何回服薬時刻を通過したか引く
        consumed = _count_consumed_since(r["updated_at"], r["time_slot"])
        adj_cal  = max(0, cal - consumed)
        total    = adj_cal + stock

        # 今日の服薬時刻が既に過ぎているかで「いつまで」の計算を調整
        slot_h, slot_m = int(SLOT_TIMES.get(r["time_slot"], "00:00")[:2]), \
                         int(SLOT_TIMES.get(r["time_slot"], "00:00")[3:])
        today_consumed = (now.hour, now.minute) >= (slot_h, slot_m)
        if total <= 0:
            until = "なし"
        else:
            offset = total if today_consumed else total - 1
            until  = (date.today() + timedelta(days=offset)).strftime("%m月%d日")

        result[r["time_slot"]] = {"total_days": total, "until": until}
    return result


# =============================================================================
# 次回通院予定一覧ウィンドウ
# =============================================================================

class ScheduleWindow(tk.Toplevel):
    """全入居者の次回通院予定を一覧表示するウィンドウ"""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("次回通院予定一覧")
        self.geometry("720x480")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)
        self._build_ui()

    def _build_ui(self):
        # ---- タイトル＋更新ボタン ----
        hdr = tk.Frame(self, bg=COLOR_HEADER, pady=8)
        hdr.pack(fill="x")
        tk.Label(hdr, text="次回通院予定一覧",
                 font=FONT_TITLE, bg=COLOR_HEADER, fg="white").pack(side="left", padx=16)
        tk.Button(hdr, text="更新", font=FONT_SMALL,
                  bg="white", fg=COLOR_HEADER, relief="flat", cursor="hand2",
                  padx=8, pady=2,
                  command=self._load).pack(side="right", padx=12)

        # ---- 凡例 ----
        legend = tk.Frame(self, bg=COLOR_BG, pady=4)
        legend.pack(fill="x", padx=12)
        tk.Label(legend, text="■", fg=COLOR_WARN,   bg=COLOR_BG, font=FONT_SMALL).pack(side="left")
        tk.Label(legend, text="期限切れ・当日",      bg=COLOR_BG, font=FONT_SMALL).pack(side="left")
        tk.Label(legend, text="　■", fg="#E67E22",  bg=COLOR_BG, font=FONT_SMALL).pack(side="left")
        tk.Label(legend, text="7日以内",             bg=COLOR_BG, font=FONT_SMALL).pack(side="left")

        # ---- テーブル ----
        frame = tk.Frame(self, bg=COLOR_BG)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        cols = ("resident", "hospital", "next_date", "appt_time", "days_left")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings",
                                 selectmode="browse")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Schedule.Treeview",
                        font=FONT_SMALL, rowheight=28,
                        background=COLOR_ROW_ODD,
                        fieldbackground=COLOR_ROW_ODD)
        style.configure("Schedule.Treeview.Heading",
                        font=FONT_BOLD,
                        background=COLOR_HEADER,
                        foreground=COLOR_HEADER_FG)
        style.map("Schedule.Treeview",
                  background=[("selected", COLOR_ACCENT)])
        self.tree.configure(style="Schedule.Treeview")

        col_defs = [
            ("resident",  "入居者",       120, "w"),
            ("hospital",  "病院・診療科", 220, "w"),
            ("next_date", "次回予定日",   110, "center"),
            ("appt_time", "予約時刻",      80, "center"),
            ("days_left", "残り日数",      90, "center"),
        ]
        for cid, label, width, anchor in col_defs:
            self.tree.heading(cid, text=label)
            self.tree.column(cid, width=width, anchor=anchor,
                             stretch=(cid == "hospital"))

        self.tree.tag_configure("odd",     background=COLOR_ROW_ODD)
        self.tree.tag_configure("even",    background=COLOR_ROW_EVEN)
        self.tree.tag_configure("overdue", foreground=COLOR_WARN)
        self.tree.tag_configure("soon",    foreground="#E67E22")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)

        self._load()

    def _load(self):
        """予定データを読み込んでテーブルを更新する"""
        for row in self.tree.get_children():
            self.tree.delete(row)

        records = get_upcoming_visits()
        if not records:
            self.tree.insert("", "end", values=("予定はありません", "", "", ""))
            return

        for i, r in enumerate(records):
            days = r["days_left"]
            if days <= 0:
                days_str = "期限切れ" if days < 0 else "本日"
                tags = ["overdue"]
            elif days <= 7:
                days_str = f"あと {days} 日"
                tags = ["soon"]
            else:
                days_str = f"あと {days} 日"
                tags = []

            tags.append("odd" if i % 2 == 0 else "even")

            self.tree.insert("", "end", values=(
                r["resident_name"],
                r["hospital_name"],
                r["next_visit_date"],
                r["next_appointment_time"] or "―",
                days_str,
            ), tags=tags)


# =============================================================================
# カレンダーダイアログ
# =============================================================================

class CalendarDialog(tk.Toplevel):
    """日付をカレンダーから選択するダイアログ"""

    def __init__(self, parent, current_date_str, on_select):
        super().__init__(parent)
        self.title("日付を選択")
        self.resizable(False, False)
        self.grab_set()
        self.on_select = on_select

        try:
            d = date.fromisoformat(current_date_str)
        except ValueError:
            d = date.today()
        self.year  = d.year
        self.month = d.month

        self._build_ui()
        self._center(parent)

    def _build_ui(self):
        self.configure(bg=COLOR_BG, padx=10, pady=10)

        # ナビゲーションバー（前月・年月表示・翌月）
        nav = tk.Frame(self, bg=COLOR_BG)
        nav.pack(fill="x", pady=(0, 6))
        tk.Button(nav, text="◀", font=FONT_BOLD, relief="flat", cursor="hand2",
                  bg=COLOR_BG, command=self._prev_month).pack(side="left")
        self.month_label = tk.Label(nav, font=FONT_BOLD, bg=COLOR_BG, width=16)
        self.month_label.pack(side="left", expand=True)
        tk.Button(nav, text="▶", font=FONT_BOLD, relief="flat", cursor="hand2",
                  bg=COLOR_BG, command=self._next_month).pack(side="right")

        self.cal_frame = tk.Frame(self, bg=COLOR_BG)
        self.cal_frame.pack()
        self._draw()

    def _draw(self):
        """カレンダーグリッドを描画する"""
        for w in self.cal_frame.winfo_children():
            w.destroy()

        self.month_label.config(text=f"{self.year}年 {self.month}月")

        # 曜日ヘッダー（土=青、日=赤）
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        colors   = ["#333"] * 5 + ["#2255CC", COLOR_WARN]
        for col, (wd, fg) in enumerate(zip(weekdays, colors)):
            tk.Label(self.cal_frame, text=wd, font=FONT_BOLD,
                     bg=COLOR_BG, fg=fg, width=4).grid(row=0, column=col, pady=2)

        today = date.today()
        for row_idx, week in enumerate(calendar.monthcalendar(self.year, self.month)):
            for col_idx, day in enumerate(week):
                if day == 0:
                    tk.Label(self.cal_frame, text="", bg=COLOR_BG,
                             width=4).grid(row=row_idx + 1, column=col_idx)
                    continue

                d      = date(self.year, self.month, day)
                is_today = (d == today)
                bg = COLOR_ACCENT if is_today else COLOR_BG
                fg = ("white" if is_today
                      else COLOR_WARN if col_idx == 6
                      else "#2255CC" if col_idx == 5
                      else "#333333")
                tk.Button(
                    self.cal_frame,
                    text=str(day), font=FONT_SMALL,
                    width=3, bg=bg, fg=fg,
                    relief="flat", cursor="hand2",
                    command=lambda d=d: self._select(d),
                ).grid(row=row_idx + 1, column=col_idx, padx=1, pady=1)

    def _prev_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        self._draw()

    def _next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        self._draw()

    def _select(self, d):
        self.on_select(d.strftime("%Y-%m-%d"))
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 病院追加・編集ダイアログ
# =============================================================================

class HospitalDialog(tk.Toplevel):
    """病院の追加・編集を行うダイアログ"""

    def __init__(self, parent, resident_id, on_done, hospital=None):
        super().__init__(parent)
        self.title("病院を編集" if hospital else "病院を追加")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id = resident_id
        self.hospital    = hospital  # 編集時は既存データ、新規時は None
        self.on_done     = on_done

        self.name_var  = tk.StringVar(value=hospital["name"]       if hospital else "")
        self.dept_var  = tk.StringVar(value=hospital["department"] if hospital else "")
        self.memo_var  = tk.StringVar(value=hospital["memo"]       if hospital else "")

        self._build_ui()
        self._center(parent)

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}

        title = "病院情報の編集" if self.hospital else "病院の追加"
        tk.Label(self, text=title, font=FONT_BOLD).grid(
            row=0, column=0, columnspan=2, **pad, sticky="w")

        fields = [
            ("病院名 *",   self.name_var,  True),
            ("診療科",     self.dept_var,  False),
            ("メモ",       self.memo_var,  False),
        ]
        for i, (label, var, required) in enumerate(fields):
            tk.Label(self, text=label, font=FONT).grid(
                row=i+1, column=0, padx=(14, 4), pady=6, sticky="e")
            tk.Entry(self, textvariable=var, width=24, font=FONT).grid(
                row=i+1, column=1, padx=(4, 14), pady=6, sticky="w")

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=len(fields)+1, column=0, columnspan=2, pady=12)
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=20, pady=6, command=self._save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=6, command=self.destroy).pack(side="left", padx=6)

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("入力エラー", "病院名は必須です。", parent=self)
            return

        if self.hospital:
            update_hospital(self.hospital["id"], name,
                            self.dept_var.get().strip(),
                            self.memo_var.get().strip())
        else:
            add_hospital(self.resident_id, name,
                         self.dept_var.get().strip(),
                         self.memo_var.get().strip())

        self.on_done()
        self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# 通院記録 入力・編集ダイアログ
# =============================================================================

class VisitDialog(tk.Toplevel):
    """通院記録の新規登録・編集を行うダイアログ"""

    def __init__(self, parent, resident_id, hospital_id, hospital_name,
                 resident_name, on_done, visit_id=None):
        super().__init__(parent)
        self.title(f"通院記録 — {resident_name}（{hospital_name}）")
        self.resizable(False, False)
        self.grab_set()

        self.resident_id   = resident_id
        self.hospital_id   = hospital_id
        self.hospital_name = hospital_name
        self.resident_name = resident_name
        self.on_done       = on_done
        self.visit_id      = visit_id  # None なら新規

        # 既存データの読み込み
        existing      = get_visit(visit_id)             if visit_id else None
        existing_presc = get_visit_prescriptions(visit_id) if visit_id else {}

        # ウィジェット変数の初期化
        today = date.today().strftime("%Y-%m-%d")
        self.date_var      = tk.StringVar(value=existing["visit_date"]              if existing else today)
        self.content_var   = tk.StringVar(value=existing["content"]                 if existing else "")
        self.companion_var = tk.StringVar(value=existing["companion"]               if existing and existing["companion"] else "")
        self.changed_var   = tk.BooleanVar(value=bool(existing["prescription_changed"]) if existing else False)
        self.next_var      = tk.StringVar(value=existing["next_visit_date"]         if existing and existing["next_visit_date"] else "")
        self.next_time_var = tk.StringVar(value=existing["next_appointment_time"]   if existing and existing["next_appointment_time"] else "")
        self.memo_var      = tk.StringVar(value=existing["memo"]                    if existing and existing["memo"] else "")

        # 時間帯ごとの処方日数
        self.presc_vars = {}
        for slot in TIME_SLOTS:
            val = existing_presc.get(slot, 0)
            self.presc_vars[slot] = tk.StringVar(value=str(val))

        # 臨時薬：複数薬エントリを管理するリスト（_build_ui 内で初期化される）
        self._temp_init_data = get_temp_presc_details(visit_id) if visit_id else []
        # 在庫差分計算用：旧データのスロット別合計日数
        self.original_temp_presc = {}
        for med in self._temp_init_data:
            for slot, sd in med["slots"].items():
                self.original_temp_presc[slot] = (
                    self.original_temp_presc.get(slot, 0) + sd["days"])
        self.temp_entries = []  # _build_ui 内で作成される

        # 編集時の元の定期処方記録（在庫の差し戻し用）
        self.original_presc = existing_presc if visit_id else {}

        self._build_ui()
        self._center(parent)

    def _build_ui(self):
        """ダイアログのUIを組み立てる"""
        main = tk.Frame(self, padx=16, pady=12)
        main.pack(fill="both", expand=True)

        row = 0

        # ---- 通院日 ----
        tk.Label(main, text="通院日 *", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        date_frame = tk.Frame(main)
        date_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=5)
        tk.Entry(date_frame, textvariable=self.date_var, width=13, font=FONT).pack(side="left")
        tk.Label(date_frame, text="（例：2026-05-07）", font=FONT_SMALL,
                 fg="#888888").pack(side="left", padx=6)
        row += 1

        # ---- 受診内容 ----
        tk.Label(main, text="受診内容", font=FONT).grid(
            row=row, column=0, sticky="ne", padx=(0, 8), pady=5)
        self.content_text = tk.Text(main, width=36, height=4, font=FONT,
                                    wrap="word", relief="solid", bd=1)
        self.content_text.grid(row=row, column=1, columnspan=2,
                                sticky="w", pady=5)
        if self.content_var.get():
            self.content_text.insert("1.0", self.content_var.get())
        row += 1

        # ---- 同行者 ----
        tk.Label(main, text="同行者", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        comp_frame = tk.Frame(main)
        comp_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=5)
        tk.Entry(comp_frame, textvariable=self.companion_var, width=24, font=FONT).pack(side="left")
        tk.Label(comp_frame, text="（職員名・家族名など、空欄OK）",
                 font=FONT_SMALL, fg="#888888").pack(side="left", padx=6)
        row += 1

        # ---- 処方変更 ----
        tk.Label(main, text="処方変更", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        tk.Checkbutton(main, text="あり", variable=self.changed_var,
                       font=FONT).grid(row=row, column=1, sticky="w", pady=5)
        row += 1

        # ---- 処方日数（時間帯別）----
        tk.Label(main, text="処方日数", font=FONT_BOLD).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=(10, 2))
        tk.Label(main, text="（処方なしの時間帯は 0 のまま）",
                 font=FONT_SMALL, fg="#888888").grid(
            row=row, column=1, columnspan=2, sticky="w", pady=(10, 2))
        row += 1

        presc_frame = tk.Frame(main, bd=1, relief="solid", padx=8, pady=6)
        presc_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)

        for i, slot in enumerate(TIME_SLOTS):
            tk.Label(presc_frame, text=f"{slot}：", font=FONT, width=6,
                     anchor="e").grid(row=0, column=i*2, padx=(8, 2))
            tk.Spinbox(presc_frame, from_=0, to=365,
                       textvariable=self.presc_vars[slot],
                       width=5, font=FONT).grid(row=0, column=i*2+1, padx=(0, 8))
        row += 1

        # ---- 臨時薬 ----
        tk.Label(main, text="臨時薬", font=FONT_BOLD).grid(
            row=row, column=0, sticky="ne", padx=(0, 8), pady=(10, 2))
        tk.Label(main, text="（複数の臨時薬を登録できます。処方のない場合はそのまま）",
                 font=FONT_SMALL, fg="#888888").grid(
            row=row, column=1, columnspan=2, sticky="w", pady=(10, 2))
        row += 1

        # スクロール可能なエントリコンテナ
        scroll_outer = tk.Frame(main, bd=1, relief="solid")
        scroll_outer.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        self.temp_canvas = tk.Canvas(scroll_outer, bg="#FEF9EC", height=240,
                                     bd=0, highlightthickness=0)
        temp_vbar = ttk.Scrollbar(scroll_outer, orient="vertical",
                                  command=self.temp_canvas.yview)
        self.temp_canvas.configure(yscrollcommand=temp_vbar.set)
        temp_vbar.pack(side="right", fill="y")
        self.temp_canvas.pack(side="left", fill="both", expand=True)
        self.temp_inner = tk.Frame(self.temp_canvas, bg="#FEF9EC")
        self.temp_canvas_win = self.temp_canvas.create_window(
            (0, 0), window=self.temp_inner, anchor="nw")
        self.temp_inner.bind(
            "<Configure>",
            lambda e: self.temp_canvas.configure(
                scrollregion=self.temp_canvas.bbox("all")))
        self.temp_canvas.bind(
            "<Configure>",
            lambda e: self.temp_canvas.itemconfig(
                self.temp_canvas_win, width=e.width))
        row += 1

        # 「＋臨時薬を追加」ボタン
        add_row = tk.Frame(main)
        add_row.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 6))
        tk.Button(add_row, text="＋ 臨時薬を追加", font=FONT_SMALL,
                  bg="#27AE60", fg="white", relief="flat", cursor="hand2",
                  padx=10, pady=3,
                  command=lambda: self._add_temp_entry("", {})).pack(side="left")
        row += 1

        # 既存データからエントリを作成する（なければ空エントリを1件）
        for med_data in self._temp_init_data:
            self._add_temp_entry(med_data["name"], med_data["slots"])
        if not self.temp_entries:
            self._add_temp_entry("", {})

        # 通院日が変わったら全エントリの終了日を再計算する
        self.date_var.trace_add(
            "write", lambda *_: self.after(50, self._update_all_temp_end_dates))

        # ---- 次回通院予定日 ----
        tk.Label(main, text="次回予定日", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        next_frame = tk.Frame(main)
        next_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=5)
        tk.Entry(next_frame, textvariable=self.next_var, width=13, font=FONT).pack(side="left")
        tk.Button(next_frame, text="📅", font=FONT_SMALL,
                  bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                  padx=6, pady=2,
                  command=self._open_next_calendar).pack(side="left", padx=(4, 0))
        tk.Label(next_frame, text="（空欄OK）", font=FONT_SMALL,
                 fg="#888888").pack(side="left", padx=6)
        row += 1

        # ---- 次回予約時間 ----
        tk.Label(main, text="予約時間", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        ntime_frame = tk.Frame(main)
        ntime_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=5)
        self.next_hour_var = tk.StringVar()
        self.next_min_var  = tk.StringVar()
        # 既存データがあれば時・分に分割してセットする
        t = self.next_time_var.get()
        if t and ":" in t:
            h, m = t.split(":", 1)
            self.next_hour_var.set(h.zfill(2))
            self.next_min_var.set(m.zfill(2))
        tk.Spinbox(ntime_frame, from_=0, to=23, textvariable=self.next_hour_var,
                   width=4, font=FONT, format="%02.0f").pack(side="left")
        tk.Label(ntime_frame, text=" ：", font=FONT).pack(side="left")
        tk.Spinbox(ntime_frame, from_=0, to=59, textvariable=self.next_min_var,
                   width=4, font=FONT, format="%02.0f", increment=5).pack(side="left")
        tk.Label(ntime_frame, text="  （予約なしの場合は空欄のまま）",
                 font=FONT_SMALL, fg="#888888").pack(side="left", padx=6)
        row += 1

        # ---- メモ ----
        tk.Label(main, text="メモ", font=FONT).grid(
            row=row, column=0, sticky="e", padx=(0, 8), pady=5)
        tk.Entry(main, textvariable=self.memo_var, width=30, font=FONT).grid(
            row=row, column=1, columnspan=2, sticky="w", pady=5)
        row += 1

        # ---- ボタン ----
        btn_frame = tk.Frame(main)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(12, 0))
        tk.Button(btn_frame, text="保存", font=FONT_BOLD,
                  bg=COLOR_BTN, fg=COLOR_BTN_FG, relief="flat", cursor="hand2",
                  padx=24, pady=7, command=self._save).pack(side="left", padx=6)
        tk.Button(btn_frame, text="キャンセル", font=FONT,
                  relief="flat", cursor="hand2",
                  padx=12, pady=7, command=self.destroy).pack(side="left", padx=6)

        # ダイアログを開いた時点で時間帯ごとの終了日を表示する（編集時に既存データを反映）
        self.after(100, self._update_all_temp_end_dates)


    def _save(self):
        """入力内容を検証して保存する"""
        # 通院日の検証
        visit_date = self.date_var.get().strip()
        try:
            date.fromisoformat(visit_date)
        except ValueError:
            messagebox.showerror("入力エラー",
                                 "通院日の形式が正しくありません。\n例：2026-05-07",
                                 parent=self)
            return

        # 次回予定日の検証（入力がある場合のみ）
        next_date = self.next_var.get().strip() or None
        if next_date:
            try:
                date.fromisoformat(next_date)
            except ValueError:
                messagebox.showerror("入力エラー",
                                     "次回予定日の形式が正しくありません。\n例：2026-06-04",
                                     parent=self)
                return

        # 処方日数の取得
        prescriptions = {}
        for slot in TIME_SLOTS:
            try:
                days = int(self.presc_vars[slot].get())
                if days < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("入力エラー",
                                     f"「{slot}」の処方日数は0以上の整数で入力してください。",
                                     parent=self)
                return
            prescriptions[slot] = days

        content = self.content_text.get("1.0", "end").strip()

        # 次回予約時間の取得（時・分が両方入力されている場合のみ "HH:MM" 形式にする）
        h = self.next_hour_var.get().strip()
        m = self.next_min_var.get().strip()
        if h and m:
            try:
                next_appointment_time = f"{int(h):02d}:{int(m):02d}"
            except ValueError:
                messagebox.showerror("入力エラー", "予約時間の値が正しくありません。", parent=self)
                return
        else:
            next_appointment_time = None

        # 臨時薬の収集（複数薬対応）
        temp_medicines = []
        new_temp_totals = {}  # スロット別合計日数（在庫差分用）
        for entry in self.temp_entries:
            name = entry["name_var"].get().strip()
            slots = {}
            for slot in TIME_SLOTS:
                try:
                    days = int(entry["presc_vars"][slot].get() or 0)
                    if days < 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror(
                        "入力エラー",
                        f"臨時薬の「{slot}」の日数は0以上の整数で入力してください。",
                        parent=self)
                    return
                if days > 0:
                    start = entry["start_vars"][slot].get().strip() or None
                    slots[slot] = {"days": days, "start_date": start}
                    new_temp_totals[slot] = new_temp_totals.get(slot, 0) + days
            if name or slots:
                temp_medicines.append({"name": name, "slots": slots})

        # 薬名があるのに日数が全部0の薬は警告する
        for med in temp_medicines:
            if med["name"] and not med["slots"]:
                if not messagebox.askyesno(
                    "確認",
                    f"臨時薬「{med['name']}」は日数がすべて0です。このまま保存しますか？",
                    parent=self
                ):
                    return

        # 通院記録を保存（在庫更新より先にDBに書き込む）
        save_visit(
            resident_id           = self.resident_id,
            hospital_id           = self.hospital_id,
            visit_date            = visit_date,
            content               = content,
            companion             = self.companion_var.get().strip(),
            prescription_changed  = self.changed_var.get(),
            next_visit_date       = next_date,
            next_appointment_time = next_appointment_time,
            memo                  = self.memo_var.get().strip(),
            prescriptions         = prescriptions,
            visit_id              = self.visit_id,
            temp_medicines        = temp_medicines,
        )

        # ── 在庫を更新する ──────────────────────────────────────
        # 新規登録：処方分をまるごと追加する
        # 編集    ：変化した分だけ差分更新する（履歴が「取消+追加」のペアにならない）
        # ─────────────────────────────────────────────────────────
        has_presc  = any(d > 0 for d in prescriptions.values())
        stock_msgs = []

        if self.visit_id:
            # 編集時：差分のみ更新
            update_stock_difference(
                self.resident_id, visit_date,
                self.original_presc, prescriptions,
                label="処方")
            # 臨時薬は在庫ボックスに反映しない（終了日は処方記録から算出）
            messagebox.showinfo("保存完了", "通院記録を更新しました。",
                                parent=self)
        else:
            # 新規登録
            if has_presc:
                add_stock_from_prescription(self.resident_id, visit_date, prescriptions)
                stock_msgs.append("処方分：" + "　".join(
                    f"{s}:{d}日" for s, d in prescriptions.items() if d > 0))

            # 臨時薬は在庫ボックスに足し込まない。
            # 終了日は visit_prescriptions の start_date + days から別パネルで表示する。
            if temp_medicines:
                med_names = "・".join(
                    m["name"] for m in temp_medicines if m["name"]) or "臨時薬"
                stock_msgs.append(f"臨時薬「{med_names}」を記録しました（在庫は別管理）")

            if stock_msgs:
                messagebox.showinfo(
                    "保存完了",
                    "通院記録を保存しました。\n\n"
                    + "\n".join(stock_msgs)
                    + "\nを薬の在庫に追加しました。",
                    parent=self
                )
            else:
                messagebox.showinfo("保存完了", "通院記録を保存しました。", parent=self)

        self.on_done()
        self.destroy()

    def _add_temp_entry(self, name="", slots=None):
        """臨時薬エントリを1件追加してUIを構築する"""
        if slots is None:
            slots = {}
        entry = {
            "name_var":   tk.StringVar(value=name),
            "presc_vars": {},
            "start_vars": {},
            "end_vars":   {},
            "bulk_var":   tk.StringVar(value=""),
            "frame":      None,
        }
        for slot in TIME_SLOTS:
            sd = slots.get(slot, {})
            entry["presc_vars"][slot] = tk.StringVar(value=str(sd.get("days", 0)))
            entry["start_vars"][slot] = tk.StringVar(value=sd.get("start_date") or "")
            entry["end_vars"][slot]   = tk.StringVar(value="")
        self.temp_entries.append(entry)
        self._build_entry_frame(entry)
        self.update_idletasks()
        self.temp_canvas.yview_moveto(1.0)
        self.after(50, lambda: self._update_end_dates_for_entry(entry))

    def _build_entry_frame(self, entry):
        """1件の臨時薬エントリのUIフレームを組み立てる"""
        bg = "#FEF9EC"
        outer = tk.Frame(self.temp_inner, bg=bg, bd=1, relief="groove", padx=6, pady=4)
        outer.pack(fill="x", padx=4, pady=(4, 0))
        entry["frame"] = outer

        # ヘッダー行：薬名 + 削除ボタン
        hdr = tk.Frame(outer, bg=bg)
        hdr.pack(fill="x", pady=(0, 3))
        tk.Label(hdr, text="薬　名：", font=FONT, bg=bg).pack(side="left")
        tk.Entry(hdr, textvariable=entry["name_var"],
                 width=22, font=FONT).pack(side="left", padx=(4, 0))
        tk.Button(hdr, text="この薬を削除", font=FONT_SMALL,
                  fg=COLOR_WARN, bg=bg, relief="flat", cursor="hand2",
                  padx=6, pady=1,
                  command=lambda e=entry: self._remove_temp_entry(e)
                  ).pack(side="right")

        # 一括飲み始め日行
        bulk = tk.Frame(outer, bg=bg)
        bulk.pack(fill="x", pady=(0, 3))
        tk.Label(bulk, text="一括飲み始め：", font=FONT_SMALL, bg=bg).pack(side="left")
        tk.Entry(bulk, textvariable=entry["bulk_var"],
                 width=12, font=FONT).pack(side="left", padx=(4, 0))
        tk.Button(bulk, text="📅", font=FONT_SMALL,
                  bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                  padx=4, pady=1,
                  command=lambda e=entry: CalendarDialog(
                      self,
                      e["bulk_var"].get() or self.date_var.get()
                      or date.today().strftime("%Y-%m-%d"),
                      e["bulk_var"].set
                  )).pack(side="left", padx=(2, 0))
        tk.Button(bulk, text="全スロットに適用", font=FONT_SMALL,
                  bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                  padx=6, pady=1,
                  command=lambda e=entry: self._apply_bulk_start(e)
                  ).pack(side="left", padx=(6, 0))
        tk.Button(bulk, text="◀1日", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=6, pady=1,
                  command=lambda e=entry: self._shift_start_dates(e, -1)
                  ).pack(side="left", padx=(6, 0))
        tk.Button(bulk, text="1日▶", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=6, pady=1,
                  command=lambda e=entry: self._shift_start_dates(e, 1)
                  ).pack(side="left", padx=(2, 0))
        tk.Label(bulk, text="← 日数が入っているスロットに一括設定。◀▶は設定済みをずらす",
                 font=FONT_SMALL, fg="#888888", bg=bg).pack(side="left", padx=8)

        # テーブル：時間帯 / 日数 / 飲み始め / 飲み終わり
        grid = tk.Frame(outer, bg=bg)
        grid.pack(fill="x", pady=(0, 2))
        for col, (lbl, w) in enumerate([("時間帯", 6), ("日　数", 6),
                                         ("飲み始め（空欄=処方日）", 18), ("飲み終わり", 12)]):
            tk.Label(grid, text=lbl, font=FONT_SMALL,
                     bg="#D4E8D4", width=w, anchor="center",
                     relief="flat", pady=3).grid(
                row=0, column=col, padx=1, pady=(0, 1), sticky="ew")

        for i, slot in enumerate(TIME_SLOTS):
            row_bg = "#FFFFFF" if i % 2 == 0 else "#F0F8F0"
            tk.Label(grid, text=slot, font=FONT, bg=row_bg,
                     width=6, anchor="center", relief="flat", pady=4).grid(
                row=i + 1, column=0, padx=1, pady=1, sticky="ew")
            tk.Spinbox(grid, from_=0, to=365,
                       textvariable=entry["presc_vars"][slot],
                       width=5, font=FONT).grid(
                row=i + 1, column=1, padx=6, pady=1)
            start_cell = tk.Frame(grid, bg=row_bg)
            start_cell.grid(row=i + 1, column=2, padx=1, pady=1, sticky="ew")
            tk.Entry(start_cell, textvariable=entry["start_vars"][slot],
                     width=11, font=FONT).pack(side="left", padx=(2, 1))
            tk.Button(start_cell, text="📅", font=FONT_SMALL,
                      bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                      padx=4, pady=1,
                      command=lambda s=slot, e=entry: CalendarDialog(
                          self,
                          e["start_vars"][s].get() or self.date_var.get()
                          or date.today().strftime("%Y-%m-%d"),
                          e["start_vars"][s].set
                      )).pack(side="left")
            tk.Label(grid, textvariable=entry["end_vars"][slot],
                     font=FONT, bg=row_bg, width=12, anchor="center",
                     relief="flat", pady=4).grid(
                row=i + 1, column=3, padx=1, pady=1, sticky="ew")
            entry["presc_vars"][slot].trace_add(
                "write", lambda *_, e=entry: self.after(
                    50, lambda: self._update_end_dates_for_entry(e)))
            entry["start_vars"][slot].trace_add(
                "write", lambda *_, e=entry: self.after(
                    50, lambda: self._update_end_dates_for_entry(e)))

    def _remove_temp_entry(self, entry):
        """臨時薬エントリを削除する（最後の1件は削除せずクリアする）"""
        if len(self.temp_entries) <= 1:
            entry["name_var"].set("")
            for slot in TIME_SLOTS:
                entry["presc_vars"][slot].set("0")
                entry["start_vars"][slot].set("")
            return
        entry["frame"].destroy()
        self.temp_entries.remove(entry)

    def _apply_bulk_start(self, entry):
        """一括飲み始め日を、日数が入力されているスロットすべてに適用する"""
        bulk = entry["bulk_var"].get().strip()
        if not bulk:
            messagebox.showwarning("入力なし", "一括設定する日付を入力してください。", parent=self)
            return
        try:
            date.fromisoformat(bulk)
        except ValueError:
            messagebox.showerror("入力エラー", "日付の形式が正しくありません。\n例：2026-05-14", parent=self)
            return
        for slot in TIME_SLOTS:
            try:
                if int(entry["presc_vars"][slot].get() or 0) > 0:
                    entry["start_vars"][slot].set(bulk)
            except ValueError:
                pass

    def _shift_start_dates(self, entry, delta):
        """飲み始め日が設定されているスロットをすべて delta 日ずらす"""
        for slot in TIME_SLOTS:
            s = entry["start_vars"][slot].get().strip()
            if not s:
                continue
            try:
                d = date.fromisoformat(s)
                entry["start_vars"][slot].set(
                    (d + timedelta(days=delta)).strftime("%Y-%m-%d"))
            except ValueError:
                pass

    def _update_end_dates_for_entry(self, entry):
        """1件の臨時薬エントリの終了日ラベルを更新する"""
        visit_date_str = self.date_var.get().strip()
        for slot in TIME_SLOTS:
            try:
                days = int(entry["presc_vars"][slot].get() or 0)
            except ValueError:
                entry["end_vars"][slot].set("")
                continue
            if days <= 0:
                entry["end_vars"][slot].set("―")
                continue
            start_str = entry["start_vars"][slot].get().strip() or visit_date_str
            try:
                start = date.fromisoformat(start_str)
            except ValueError:
                entry["end_vars"][slot].set("")
                continue
            end_date = start + timedelta(days=days - 1)
            entry["end_vars"][slot].set(f"{end_date.strftime('%m月%d日')}まで")

    def _update_all_temp_end_dates(self):
        """全臨時薬エントリの終了日ラベルを更新する（通院日変更時などに呼ぶ）"""
        for entry in self.temp_entries:
            self._update_end_dates_for_entry(entry)

    def _open_next_calendar(self):
        """カレンダーダイアログを開き、選択した日付を次回予定日欄にセットする"""
        CalendarDialog(self, self.next_var.get() or date.today().strftime("%Y-%m-%d"),
                       self.next_var.set)

    def _center(self, parent):
        self.update_idletasks()
        pw = parent.winfo_rootx() + parent.winfo_width()  // 2
        ph = parent.winfo_rooty() + parent.winfo_height() // 2
        self.geometry(f"+{pw - self.winfo_width()//2}+{ph - self.winfo_height()//2}")


# =============================================================================
# メインアプリ
# =============================================================================

class VisitApp(tk.Tk):
    """通院記録アプリのメインウィンドウ"""

    def __init__(self):
        super().__init__()
        self.title("通院記録")
        self.geometry("1100x660")
        self.configure(bg=COLOR_BG)
        self.resizable(True, True)

        self.residents     = []
        self.selected_rid  = None   # 選択中の入居者ID
        self.selected_name = ""
        self.hospitals     = []
        self.selected_hid  = None   # 選択中の病院ID
        self.selected_hname = ""
        self.visits        = []

        self._build_ui()
        self._load_residents()

    def _build_ui(self):
        """メインウィンドウのUIを組み立てる"""

        # ---- タイトルバー ----
        title_frame = tk.Frame(self, bg=COLOR_HEADER, pady=10)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text="通院記録",
                 font=FONT_TITLE, bg=COLOR_HEADER, fg="white").pack(side="left", padx=16)
        tk.Button(title_frame, text="📅 次回通院予定一覧", font=FONT_BOLD,
                  bg="white", fg=COLOR_HEADER, relief="flat", cursor="hand2",
                  padx=12, pady=4,
                  command=self._open_schedule_window).pack(side="right", padx=16)

        # ---- メインエリア（3カラム構成）----
        main = tk.Frame(self, bg=COLOR_BG)
        main.pack(fill="both", expand=True, padx=12, pady=10)

        # ---- 左パネル：入居者一覧 ----
        left = tk.Frame(main, bg=COLOR_BG, width=170)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        tk.Label(left, text="入居者", font=FONT_BOLD, bg=COLOR_BG).pack(
            anchor="w", pady=(0, 4))

        lf = tk.Frame(left)
        lf.pack(fill="both", expand=True)
        sb1 = tk.Scrollbar(lf)
        self.res_lb = tk.Listbox(lf, font=FONT, yscrollcommand=sb1.set,
                                  selectbackground=COLOR_ACCENT,
                                  selectforeground="white",
                                  relief="flat", bd=1,
                                  highlightthickness=1, activestyle="dotbox")
        sb1.config(command=self.res_lb.yview)
        sb1.pack(side="right", fill="y")
        self.res_lb.pack(fill="both", expand=True)
        self.res_lb.bind("<<ListboxSelect>>", self._on_select_resident)

        # ---- 中パネル：病院一覧 ----
        mid = tk.Frame(main, bg=COLOR_BG, width=210)
        mid.pack(side="left", fill="y", padx=(0, 8))
        mid.pack_propagate(False)

        hosp_hdr = tk.Frame(mid, bg=COLOR_BG)
        hosp_hdr.pack(fill="x", pady=(0, 4))
        tk.Label(hosp_hdr, text="病院", font=FONT_BOLD, bg=COLOR_BG).pack(side="left")
        tk.Button(hosp_hdr, text="＋追加", font=FONT_SMALL,
                  bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                  padx=6, pady=2,
                  command=self._add_hospital).pack(side="right")

        hf = tk.Frame(mid)
        hf.pack(fill="both", expand=True)
        sb2 = tk.Scrollbar(hf)
        self.hosp_lb = tk.Listbox(hf, font=FONT, yscrollcommand=sb2.set,
                                   selectbackground=COLOR_ACCENT,
                                   selectforeground="white",
                                   relief="flat", bd=1,
                                   highlightthickness=1, activestyle="dotbox")
        sb2.config(command=self.hosp_lb.yview)
        sb2.pack(side="right", fill="y")
        self.hosp_lb.pack(fill="both", expand=True)
        self.hosp_lb.bind("<<ListboxSelect>>", self._on_select_hospital)

        # 病院編集・削除ボタン
        hosp_btn = tk.Frame(mid, bg=COLOR_BG)
        hosp_btn.pack(fill="x", pady=4)
        tk.Button(hosp_btn, text="編集", font=FONT_SMALL,
                  relief="flat", cursor="hand2", padx=8, pady=3,
                  command=self._edit_hospital).pack(side="left", padx=2)
        tk.Button(hosp_btn, text="削除", font=FONT_SMALL,
                  fg=COLOR_WARN, relief="flat", cursor="hand2", padx=8, pady=3,
                  command=self._delete_hospital).pack(side="left", padx=2)

        # ---- 右パネル：通院記録一覧＋薬サマリー ----
        self.right = tk.Frame(main, bg=COLOR_BG)
        self.right.pack(side="left", fill="both", expand=True)
        self._build_right_placeholder()

    def _build_right_placeholder(self):
        """病院未選択時のプレースホルダー"""
        for w in self.right.winfo_children():
            w.destroy()
        tk.Label(self.right,
                 text="← 入居者・病院を選択してください",
                 font=FONT, fg="#AAAAAA", bg=COLOR_BG).pack(expand=True)

    def _build_right_panel(self):
        """選択した入居者・病院の通院記録パネルを構築する"""
        for w in self.right.winfo_children():
            w.destroy()

        # ---- ヘッダー ----
        hdr = tk.Frame(self.right, bg=COLOR_BG)
        hdr.pack(fill="x", pady=(0, 6))
        tk.Label(hdr,
                 text=f"　{self.selected_name}  ／  {self.selected_hname}",
                 font=FONT_TITLE, bg=COLOR_BG).pack(side="left")
        tk.Button(hdr, text="＋ 新規記録", font=FONT_BOLD,
                  bg=COLOR_BTN, fg="white", relief="flat", cursor="hand2",
                  padx=14, pady=5,
                  command=self._add_visit).pack(side="right")

        # ---- 薬の残日数サマリー ----
        self._build_medicine_summary()

        # ---- 通院記録テーブル ----
        self._build_visit_table()

    def _build_medicine_summary(self):
        """薬の在庫管理アプリから残日数サマリーを取得して表示する"""
        summary  = get_medicine_summary(self.selected_rid)
        temp_info = get_latest_temp_medicine(self.selected_rid, self.selected_hid)

        if not summary and not temp_info:
            return

        frame = tk.Frame(self.right, bg="#EAF4F2",
                         bd=1, relief="solid", padx=10, pady=6)
        frame.pack(fill="x", pady=(0, 6))

        # ---- 1行目：定期処方の残日数 ----
        row1 = tk.Frame(frame, bg="#EAF4F2")
        row1.pack(fill="x")

        tk.Label(row1, text="現在の薬残日数：", font=FONT_BOLD,
                 bg="#EAF4F2").pack(side="left")

        # 血圧測定アプリを開くボタン
        tk.Button(row1, text="🩺 血圧測定を開く", font=FONT_SMALL,
                  bg=COLOR_SUB_BTN, fg="white", relief="flat", cursor="hand2",
                  padx=8, pady=2,
                  command=self._open_bp_app).pack(side="right", padx=(0, 4))

        # 薬管理アプリを開くボタン
        tk.Button(row1, text="💊 薬管理を開く", font=FONT_SMALL,
                  bg=COLOR_ACCENT, fg="white", relief="flat", cursor="hand2",
                  padx=8, pady=2,
                  command=self._open_medicine_app).pack(side="right", padx=(0, 4))

        for slot, info in (summary or {}).items():
            total = info["total_days"]
            until = info["until"]
            fg    = COLOR_WARN if 0 < total <= 7 else "#333333"
            tk.Label(row1,
                     text=f"　{slot}：{total}日分（{until}まで）",
                     font=FONT, fg=fg, bg="#EAF4F2").pack(side="left")

        # ---- 2行目以降：臨時薬の時間帯ごとの服薬終了予定（複数薬対応）----
        if temp_info:
            any_displayed = False
            for med in temp_info["medicines"]:
                slot_parts = []
                for slot in TIME_SLOTS:
                    detail = med["slots"].get(slot, {})
                    days = detail.get("days", 0)
                    if days <= 0:
                        continue
                    start_str = detail.get("start_date") or temp_info["visit_date"]
                    try:
                        start = date.fromisoformat(start_str)
                    except ValueError:
                        continue
                    end_date  = start + timedelta(days=days - 1)
                    remaining = (end_date - date.today()).days
                    if remaining < 0:
                        remain_str = "終了済"
                    elif remaining == 0:
                        remain_str = "本日まで"
                    else:
                        remain_str = f"あと{remaining}日"
                    slot_parts.append((slot, days, end_date, remaining))

                if not slot_parts:
                    continue
                row2 = tk.Frame(frame, bg="#EAF4F2")
                row2.pack(fill="x", pady=(4, 0))
                med_label = f"臨時薬「{med['name']}」" if med["name"] else "臨時薬"
                tk.Label(row2, text=med_label, font=FONT_BOLD, bg="#EAF4F2").pack(side="left")
                for slot, days, end_date, remaining in slot_parts:
                    if remaining < 0:
                        fg = "#999999"
                        label_text = f"　{slot}：終了済（{end_date.strftime('%m月%d日')}まで）"
                    elif remaining == 0:
                        fg = COLOR_WARN
                        label_text = f"　{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"
                    elif remaining <= 3:
                        fg = "#E67E22"
                        label_text = f"　{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"
                    else:
                        fg = COLOR_ACCENT
                        label_text = f"　{slot}：{days}日分（{end_date.strftime('%m月%d日')}まで）"
                    tk.Label(row2,
                             text=label_text,
                             font=FONT_SMALL, fg=fg, bg="#EAF4F2").pack(side="left")
                any_displayed = True

    def _build_visit_table(self):
        """通院記録の一覧を Treeview で表示する"""
        self.visits = get_visits(self.selected_rid, self.selected_hid)

        # ---- Treeview ----
        tree_frame = tk.Frame(self.right, bg=COLOR_BG)
        tree_frame.pack(fill="both", expand=True)

        cols = ("visit_date", "prescription_changed", "presc_days",
                "next_visit", "content")
        self.visit_tree = ttk.Treeview(
            tree_frame,
            columns=cols,
            show="headings",
            height=12,
            selectmode="browse",
        )

        # スタイル設定（clam テーマを使わないと Windows で見出し色が上書きされて白抜けする）
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        font=FONT_SMALL, rowheight=26,
                        background=COLOR_ROW_ODD,
                        fieldbackground=COLOR_ROW_ODD)
        style.configure("Treeview.Heading",
                        font=FONT_BOLD,
                        background=COLOR_HEADER,
                        foreground=COLOR_HEADER_FG)
        style.map("Treeview", background=[("selected", COLOR_ACCENT)])

        # カラム定義
        col_defs = [
            ("visit_date",            "通院日",    90, "center"),
            ("prescription_changed",  "処方変更",  70, "center"),
            ("presc_days",            "処方日数", 190, "w"),
            ("next_visit",            "次回予定", 120, "center"),
            ("content",               "受診内容", 190, "w"),
        ]
        for cid, label, width, anchor in col_defs:
            self.visit_tree.heading(cid, text=label)
            self.visit_tree.column(cid, width=width, anchor=anchor,
                                   stretch=(cid == "content"))

        # 行データの挿入
        self.visit_tree.tag_configure("odd",  background=COLOR_ROW_ODD)
        self.visit_tree.tag_configure("even", background=COLOR_ROW_EVEN)
        self.visit_tree.tag_configure("past_next", foreground=COLOR_WARN)

        for i, v in enumerate(self.visits):
            presc     = get_visit_prescriptions(v["id"])
            presc_str = "  ".join(
                f"{s}:{d}日" for s, d in presc.items() if d > 0
            )
            # 臨時薬がある場合は「＋臨時:薬名N日」として末尾に追加する
            temp_name = v.get("temp_medicine") or ""
            temp_slot = v.get("temp_medicine_slot") or ""
            temp_days = v.get("temp_medicine_days") or 0
            if temp_name and temp_days > 0:
                presc_str += ("  " if presc_str else "") + f"【臨時:{temp_name} {temp_slot}{temp_days}日】"
            if not presc_str:
                presc_str = "処方なし"

            next_d = v["next_visit_date"] or ""
            tags   = ["odd" if i % 2 == 0 else "even"]
            if next_d:
                try:
                    nd = date.fromisoformat(next_d)
                    if nd < date.today():
                        tags.append("past_next")
                    next_d = nd.strftime("%m/%d")
                except ValueError:
                    pass

            content_short = (v["content"] or "")
            if len(content_short) > 30:
                content_short = content_short[:30] + "…"

            # 次回予定日に予約時間があれば "05/20 10:30" の形で表示する
            if next_d and v.get("next_appointment_time"):
                next_d += f" {v['next_appointment_time']}"

            self.visit_tree.insert(
                "", "end",
                iid=str(v["id"]),
                values=(
                    v["visit_date"],
                    "あり" if v["prescription_changed"] else "なし",
                    presc_str,
                    next_d,
                    content_short,
                ),
                tags=tags,
            )

        # スクロールバー
        sb_v = ttk.Scrollbar(tree_frame, orient="vertical",
                             command=self.visit_tree.yview)
        self.visit_tree.configure(yscrollcommand=sb_v.set)
        sb_v.pack(side="right", fill="y")
        self.visit_tree.pack(fill="both", expand=True)

        # ダブルクリックでも編集できる
        self.visit_tree.bind("<Double-1>", lambda e: self._edit_selected())

        # ---- 操作ボタン（行選択後に使う）----
        btn_bar = tk.Frame(self.right, bg=COLOR_BG)
        btn_bar.pack(fill="x", pady=(4, 0))

        tk.Button(btn_bar, text="編 集", font=FONT_BOLD,
                  bg=COLOR_BTN, fg="white", relief="flat", cursor="hand2",
                  padx=18, pady=6,
                  command=self._edit_selected).pack(side="left", padx=4)
        tk.Button(btn_bar, text="削 除", font=FONT_BOLD,
                  bg=COLOR_WARN, fg="white", relief="flat", cursor="hand2",
                  padx=18, pady=6,
                  command=self._delete_selected).pack(side="left", padx=4)
        tk.Label(btn_bar,
                 text="※ 行を選択してから「編集」「削除」を押してください　ダブルクリックでも編集できます",
                 font=FONT_SMALL, fg="#888888", bg=COLOR_BG).pack(
            side="left", padx=10)

    # =========================================================================
    # イベントハンドラ
    # =========================================================================

    def _open_schedule_window(self):
        """次回通院予定一覧ウィンドウを開く"""
        ScheduleWindow(self)

    def _open_bp_app(self):
        """血圧測定アプリを別プロセスで起動する"""
        bp_path = os.path.join(BASE_DIR, "bp_app", "bp_app.py")
        if not os.path.exists(bp_path):
            messagebox.showerror("エラー", f"血圧測定アプリが見つかりません。\n{bp_path}")
            return
        subprocess.Popen([sys.executable, bp_path])

    def _open_medicine_app(self):
        """薬管理アプリを別プロセスで起動する"""
        medicine_path = os.path.join(BASE_DIR, "medicine_app", "medicine_app.py")
        if not os.path.exists(medicine_path):
            messagebox.showerror("エラー", f"薬管理アプリが見つかりません。\n{medicine_path}")
            return
        subprocess.Popen([sys.executable, medicine_path])

    def _load_residents(self):
        """入居者一覧を読み込んでリストボックスに表示する"""
        self.residents = get_residents()
        self.res_lb.delete(0, "end")
        for _, name in self.residents:
            self.res_lb.insert("end", f"  {name}")

    def _on_select_resident(self, event):
        """入居者を選択したときに病院一覧を更新する"""
        sel = self.res_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self.selected_rid  = self.residents[idx][0]
        self.selected_name = self.residents[idx][1]
        self.selected_hid  = None
        self.selected_hname = ""
        self._reload_hospitals()
        self._build_right_placeholder()

    def _reload_hospitals(self):
        """病院一覧を再読み込みする"""
        self.hospitals = get_hospitals(self.selected_rid) if self.selected_rid else []
        self.hosp_lb.delete(0, "end")
        for h in self.hospitals:
            label = h["name"]
            if h["department"]:
                label += f"（{h['department']}）"
            self.hosp_lb.insert("end", f"  {label}")

    def _on_select_hospital(self, event):
        """病院を選択したときに通院記録パネルを更新する"""
        sel = self.hosp_lb.curselection()
        if not sel:
            return
        idx = sel[0]
        self.selected_hid   = self.hospitals[idx]["id"]
        self.selected_hname = self.hospitals[idx]["name"]
        if self.hospitals[idx]["department"]:
            self.selected_hname += f"（{self.hospitals[idx]['department']}）"
        self._build_right_panel()

    def _add_hospital(self):
        """病院追加ダイアログを開く"""
        if not self.selected_rid:
            messagebox.showwarning("未選択", "先に入居者を選択してください。")
            return
        HospitalDialog(self, self.selected_rid, self._reload_hospitals)

    def _edit_hospital(self):
        """病院編集ダイアログを開く"""
        sel = self.hosp_lb.curselection()
        if not sel:
            messagebox.showwarning("未選択", "編集する病院を選択してください。")
            return
        hospital = self.hospitals[sel[0]]
        HospitalDialog(self, self.selected_rid, self._reload_hospitals,
                       hospital=hospital)

    def _delete_hospital(self):
        """病院を削除する（通院記録は残す）"""
        sel = self.hosp_lb.curselection()
        if not sel:
            messagebox.showwarning("未選択", "削除する病院を選択してください。")
            return
        hospital = self.hospitals[sel[0]]
        if not messagebox.askyesno(
            "削除確認",
            f"「{hospital['name']}」を削除しますか？\n"
            f"（過去の通院記録は残ります）"
        ):
            return
        delete_hospital(hospital["id"])
        self.selected_hid   = None
        self.selected_hname = ""
        self._reload_hospitals()
        self._build_right_placeholder()

    def _add_visit(self):
        """通院記録の新規登録ダイアログを開く"""
        VisitDialog(self, self.selected_rid, self.selected_hid,
                    self.selected_hname, self.selected_name,
                    self._build_right_panel)

    def _get_selected_visit_id(self):
        """Treeview で選択中の通院記録IDを返す。未選択なら None。"""
        sel = self.visit_tree.selection()
        if not sel:
            messagebox.showwarning("未選択", "操作する記録を選択してください。")
            return None
        return int(sel[0])

    def _edit_selected(self):
        """選択中の通院記録を編集する"""
        visit_id = self._get_selected_visit_id()
        if visit_id is None:
            return
        VisitDialog(self, self.selected_rid, self.selected_hid,
                    self.selected_hname, self.selected_name,
                    self._build_right_panel, visit_id=visit_id)

    def _delete_selected(self):
        """選択中の通院記録を削除する（在庫から処方分を差し引く）"""
        visit_id = self._get_selected_visit_id()
        if visit_id is None:
            return

        v     = get_visit(visit_id)
        presc = get_visit_prescriptions(visit_id)

        msg = f"通院日：{v['visit_date']} の記録を削除しますか？"
        if any(d > 0 for d in presc.values()):
            presc_str = "、".join(f"{s}:{d}日" for s, d in presc.items() if d > 0)
            msg += f"\n\n処方分（{presc_str}）が薬の在庫から差し引かれます。"

        if not messagebox.askyesno("削除確認", msg):
            return

        if presc:
            remove_stock_from_prescription(self.selected_rid, presc)

        # 臨時薬は在庫ボックスに記録していないので差し引き不要

        delete_visit(visit_id)
        self._build_right_panel()


# =============================================================================
# エントリーポイント
# =============================================================================

if __name__ == "__main__":
    setup()
    app = VisitApp()
    app.mainloop()
