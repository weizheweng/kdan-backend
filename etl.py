#!/usr/bin/env python3
# etl.py

import psycopg2
import json
import re
from datetime import datetime

# ===【1) 資料庫連線設定】===
DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "KDAN"
DB_USER = "postgres"
DB_PASSWORD = 8510

# ===【2) 建立 ENUM 與四個資料表】===
def create_tables():
    """
    依需求建立:
      1. ENUM: day_of_week_enum
      2. pharmacies
      3. pharmacy_opening_hours
      4. users
      5. purchase_histories
    """
    # 如果你確定要清空舊表、舊 enum，可在此先做 DROP:
    # (請酌情決定是否要在正式環境中執行)
    drop_schema_sql = """
    DROP TABLE IF EXISTS purchase_histories CASCADE;
    DROP TABLE IF EXISTS pharmacy_opening_hours CASCADE;
    DROP TABLE IF EXISTS pharmacies CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    DROP TYPE IF EXISTS day_of_week_enum CASCADE;
    """
    create_enum = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'day_of_week_enum') THEN
            CREATE TYPE day_of_week_enum AS ENUM ('Mon','Tue','Wed','Thur','Fri','Sat','Sun');
        END IF;
    END$$;
    """

    create_pharmacies = """
    CREATE TABLE IF NOT EXISTS pharmacies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        address VARCHAR(255),
        phone VARCHAR(50),
        cash_balance DOUBLE PRECISION DEFAULT 0
    );
    """

    create_pharmacy_opening_hours = """
    CREATE TABLE IF NOT EXISTS pharmacy_opening_hours (
        id SERIAL PRIMARY KEY,
        pharmacy_id INT NOT NULL,
        day_of_week day_of_week_enum NOT NULL,
        open_time TIME NOT NULL,
        close_time TIME NOT NULL,
        CONSTRAINT fk_pharmacy
            FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id)
            ON DELETE CASCADE
    );
    """

    create_users = """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        cash_balance DOUBLE PRECISION DEFAULT 0
    );
    """

    create_purchase_histories = """
    CREATE TABLE IF NOT EXISTS purchase_histories (
        id SERIAL PRIMARY KEY,
        user_id INT NOT NULL,
        pharmacy_id INT NOT NULL,
        mask_name VARCHAR(255),
        transaction_amount DOUBLE PRECISION DEFAULT 0,
        transaction_date TIMESTAMP,
        CONSTRAINT fk_user
            FOREIGN KEY (user_id) REFERENCES users(id)
            ON DELETE CASCADE,
        CONSTRAINT fk_pharmacy
            FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id)
            ON DELETE CASCADE
    );
    """

    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()

        # (可選) 先清空舊的 schema，請自行決定是否要執行
        cursor.execute(drop_schema_sql)

        # 建立 ENUM
        cursor.execute(create_enum)
        # 建立 pharmacies
        cursor.execute(create_pharmacies)
        # 建立 pharmacy_opening_hours
        cursor.execute(create_pharmacy_opening_hours)
        # 建立 users
        cursor.execute(create_users)
        # 建立 purchase_histories
        cursor.execute(create_purchase_histories)

        conn.commit()
        cursor.close()
        print("[INFO] Tables created (or already exist).")
    except Exception as e:
        print("[ERROR] Failed to create tables:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ===【3) 解析 openingHours，支援 "Thur"】===
def parse_opening_hours(opening_str: str):
    """
    將像 "Mon - Fri 08:00 - 17:00 / Sat, Sun 08:00 - 12:00" 或
    "Mon, Wed, Fri 08:00 - 12:00 / Tue, Thur 14:00 - 18:00" 的字串
    拆解成 list，每一筆包含 (day_of_week, open_time, close_time)。
    e.g. [
      ("Mon", "08:00:00", "17:00:00"),
      ("Tue", "08:00:00", "17:00:00"),
      ...
      ("Thur", "14:00:00", "18:00:00"),
    ]
    """
    segments = [seg.strip() for seg in opening_str.split("/")]
    results = []
    # e.g. "Mon - Fri 08:00 - 17:00" or "Mon,Wed,Fri 08:00 - 12:00"
    pattern = re.compile(r"([A-Za-z,\s-]+)\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")

    # 注意，我們這裡使用 'Thur' 作為星期四
    all_days = ["Mon","Tue","Wed","Thur","Fri","Sat","Sun"]

    def expand_days(day_part: str):
        """
        e.g. "Mon - Fri" => ["Mon","Tue","Wed","Thur","Fri"] (如果要連續到 Thur 也要加進來)
             "Mon, Wed, Fri" => ["Mon","Wed","Fri"]
             "Tue, Thur" => ["Tue","Thur"]
        """
        day_part = day_part.strip()
        if "-" in day_part:
            # 如 "Mon - Thur" 或 "Mon - Fri"
            start_day, end_day = [d.strip() for d in day_part.split("-")]
            start_index = all_days.index(start_day)
            end_index = all_days.index(end_day)
            return all_days[start_index : end_index + 1]
        else:
            # 如 "Sat, Sun" => ["Sat","Sun"]
            # "Mon" => ["Mon"]
            items = [d.strip() for d in day_part.split(",")]
            return items

    for seg in segments:
        m = pattern.search(seg)
        if m:
            day_range_str = m.group(1)    # e.g. "Mon - Fri" / "Sat, Sun"
            open_t = m.group(2) + ":00"   # "08:00" => "08:00:00"
            close_t = m.group(3) + ":00"  # "17:00" => "17:00:00"
            for d in expand_days(day_range_str):
                # 如果 d 不在 all_days 裡，會導致 ENUM insert 失敗
                # 可再做個檢查
                if d not in all_days:
                    print(f"[WARN] day_of_week '{d}' is not in the enum list. Skipped.")
                    continue
                results.append((d, open_t, close_t))

    return results

# ===【4) 匯入 pharmacies.json → pharmacies & pharmacy_opening_hours】===
def import_pharmacies(pharmacies_json_path: str):
    """
    解析 pharmacies.json, 將資料寫進:
      - pharmacies (id, name, address, phone, cash_balance)
      - pharmacy_opening_hours (多筆營業時間)
    """
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()

        with open("pharmacies.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        inserted_count = 0
        for item in data:
            name = item["name"]
            cash_balance = float(item.get("cashBalance", 0))
            address = item.get("address", "")     # 若json沒有就空字串
            phone = item.get("phone", "")         # 同上
            opening_str = item.get("openingHours", "")

            # 1) 插入 pharmacies
            insert_pharmacy_sql = """
                INSERT INTO pharmacies (name, address, phone, cash_balance)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """
            cursor.execute(insert_pharmacy_sql, (name, address, phone, cash_balance))
            pharmacy_id = cursor.fetchone()[0]

            # 2) 解析開放時間, 插入 pharmacy_opening_hours
            oh_list = parse_opening_hours(opening_str)
            for (day_of_week, open_time, close_time) in oh_list:
                insert_oh_sql = """
                    INSERT INTO pharmacy_opening_hours
                    (pharmacy_id, day_of_week, open_time, close_time)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(insert_oh_sql, (pharmacy_id, day_of_week, open_time, close_time))

            inserted_count += 1

        conn.commit()
        cursor.close()
        print(f"[INFO] Inserted {inserted_count} pharmacies and their opening hours.")
    except Exception as e:
        print("[ERROR] Failed to import pharmacies:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ===【5) 匯入 users.json → users & purchase_histories】===
def import_users(users_json_path: str):
    """
    解析 users.json, 將資料寫進:
      - users (id, name, cash_balance)
      - purchase_histories (一對多)
    其中 purchaseHistories 裡會有 pharmacyName => 需根據 pharmacies.name 找到 pharmacy_id
    """
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        cursor = conn.cursor()

        with open("users.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        user_count = 0
        purchase_count = 0

        for user_item in data:
            user_name = user_item["name"]
            user_balance = float(user_item.get("cashBalance", 0))
            purchase_histories = user_item.get("purchaseHistories", [])

            # 1) INSERT INTO users
            insert_user_sql = """
                INSERT INTO users (name, cash_balance)
                VALUES (%s, %s)
                RETURNING id
            """
            cursor.execute(insert_user_sql, (user_name, user_balance))
            user_id = cursor.fetchone()[0]
            user_count += 1

            # 2) 逐筆插入 purchase_histories
            for ph in purchase_histories:
                pharmacy_name = ph["pharmacyName"]
                mask_name = ph.get("maskName", "")
                transaction_amount = float(ph.get("transactionAmount", 0))
                transaction_date_str = ph.get("transactionDate", "")
                # 轉成 datetime
                transaction_date = datetime.strptime(transaction_date_str, "%Y-%m-%d %H:%M:%S")

                # 先查詢 pharmacy_id
                select_pharmacy_sql = """
                    SELECT id FROM pharmacies WHERE name = %s
                """
                cursor.execute(select_pharmacy_sql, (pharmacy_name,))
                result = cursor.fetchone()
                if not result:
                    print(f"[WARN] Pharmacy '{pharmacy_name}' not found. Skipping this purchase.")
                    continue

                pharmacy_id = result[0]

                insert_purchase_sql = """
                    INSERT INTO purchase_histories
                    (user_id, pharmacy_id, mask_name, transaction_amount, transaction_date)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(insert_purchase_sql, (user_id, pharmacy_id, mask_name, transaction_amount, transaction_date))
                purchase_count += 1

        conn.commit()
        cursor.close()
        print(f"[INFO] Inserted {user_count} users and {purchase_count} purchase records.")
    except Exception as e:
        print("[ERROR] Failed to import users:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# ===【6) 主程式：建立表 + 從兩個 JSON 檔匯入資料】===
def main():
    # 1) 先建表
    create_tables()

    # 2) 匯入 pharmacies.json (裡面要使用 Thur 而非 Thu)
    import_pharmacies("data/pharmacies.json")

    # 3) 匯入 users.json
    import_users("data/users.json")


if __name__ == "__main__":
    main()

