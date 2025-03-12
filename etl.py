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

# === 2) 建立 ENUM 與五個資料表 (無 address, phone) ===
def create_tables():
    """
    建立:
      1. ENUM day_of_week_enum (含 'Thur')
      2. pharmacies (id, name, cash_balance)
      3. pharmacy_opening_hours (id, pharmacy_id, day_of_week, open_time, close_time)
      4. masks (id, pharmacy_id, name, price)
      5. users (id, name, cash_balance)
      6. purchase_histories (id, user_id, pharmacy_id, mask_id, mask_name, quantity, transaction_amount, transaction_date)
    """
    drop_schema_sql = """
    DROP TABLE IF EXISTS purchase_histories CASCADE;
    DROP TABLE IF EXISTS masks CASCADE;
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

    create_masks = """
    CREATE TABLE IF NOT EXISTS masks (
        id SERIAL PRIMARY KEY,
        pharmacy_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        price DOUBLE PRECISION DEFAULT 0,
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
        mask_id INT,
        mask_name VARCHAR(255),
        quantity INT DEFAULT 1,
        transaction_amount DOUBLE PRECISION DEFAULT 0,
        transaction_date TIMESTAMP,
        CONSTRAINT fk_user
            FOREIGN KEY (user_id) REFERENCES users(id)
            ON DELETE CASCADE,
        CONSTRAINT fk_pharmacy
            FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id)
            ON DELETE CASCADE,
        CONSTRAINT fk_mask
            FOREIGN KEY (mask_id) REFERENCES masks(id)
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

        # 若想保留舊資料，可註解以下:
        cursor.execute(drop_schema_sql)

        # 建立 enum + tables
        cursor.execute(create_enum)
        cursor.execute(create_pharmacies)
        cursor.execute(create_pharmacy_opening_hours)
        cursor.execute(create_masks)
        cursor.execute(create_users)
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

# === 3) 解析 openingHours (支援 "Thur") ===
def parse_opening_hours(opening_str: str):
    """
    範例: "Mon - Fri 08:00 - 17:00 / Sat, Sun 08:00 - 12:00"
         "Mon, Wed, Fri 08:00 - 12:00 / Tue, Thur 14:00 - 18:00"
    拆解成 list[ (day_of_week, open_t, close_t), ...]
    e.g. [("Mon","08:00:00","17:00:00"), ("Tue","14:00:00","18:00:00"), ...]
    """
    segments = [seg.strip() for seg in opening_str.split("/")]
    results = []
    pattern = re.compile(r"([A-Za-z,\s-]+)\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})")

    all_days = ["Mon","Tue","Wed","Thur","Fri","Sat","Sun"]

    def expand_days(day_part: str):
        day_part = day_part.strip()
        if "-" in day_part:
            # e.g. "Mon - Thur" or "Mon - Fri"
            start_day, end_day = [d.strip() for d in day_part.split("-")]
            start_idx = all_days.index(start_day)
            end_idx = all_days.index(end_day)
            return all_days[start_idx : end_idx + 1]
        else:
            # e.g. "Sat, Sun" => ["Sat","Sun"]
            return [x.strip() for x in day_part.split(",")]

    for seg in segments:
        m = pattern.search(seg)
        if m:
            day_range_str = m.group(1)
            open_t = m.group(2) + ":00"
            close_t = m.group(3) + ":00"
            for d in expand_days(day_range_str):
                if d in all_days:
                    results.append((d, open_t, close_t))
                else:
                    print(f"[WARN] Unrecognized day '{d}'. Skipping.")
    return results

# === 4) 匯入 pharmacies.json → pharmacies, pharmacy_opening_hours, masks ===
def import_pharmacies(pharmacies_json_path: str):
    """
    期待 JSON 結構:
    [
      {
        "name": "DFW Wellness",
        "cashBalance": 328.41,
        "openingHours": "Mon, Wed, Fri 08:00 - 12:00 / Tue, Thur 14:00 - 18:00",
        "masks": [
          {"name": "MaskT (green) (10 per pack)", "price": 41.86},
          ...
        ]
      },
      ...
    ]
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

        with open(pharmacies_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        inserted_count = 0

        for item in data:
            name = item["name"]
            cash_balance = float(item.get("cashBalance", 0))
            opening_str = item.get("openingHours", "")

            # INSERT pharmacies
            sql_pharmacy = """
                INSERT INTO pharmacies (name, cash_balance)
                VALUES (%s, %s)
                RETURNING id
            """
            cursor.execute(sql_pharmacy, (name, cash_balance))
            pharmacy_id = cursor.fetchone()[0]

            # 插入營業時間
            oh_list = parse_opening_hours(opening_str)
            for (dow, open_t, close_t) in oh_list:
                sql_oh = """
                    INSERT INTO pharmacy_opening_hours
                    (pharmacy_id, day_of_week, open_time, close_time)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(sql_oh, (pharmacy_id, dow, open_t, close_t))

            # 插入口罩
            for m in item.get("masks", []):
                mask_name = m["name"]
                mask_price = float(m["price"])
                sql_mask = """
                    INSERT INTO masks (pharmacy_id, name, price)
                    VALUES (%s, %s, %s)
                """
                cursor.execute(sql_mask, (pharmacy_id, mask_name, mask_price))

            inserted_count += 1

        conn.commit()
        cursor.close()
        print(f"[INFO] Inserted {inserted_count} pharmacies (opening_hours, masks).")
    except Exception as e:
        print("[ERROR] Failed to import pharmacies:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# === 5) 匯入 users.json → users, purchase_histories ===
def import_users(users_json_path: str):
    """
    期待 JSON 結構:
    [
      {
        "name": "Yvonne Guerrero",
        "cashBalance": 191.83,
        "purchaseHistories": [
          {
            "pharmacyName": "DFW Wellness",
            "maskName": "Second Smile (black) (3 per pack)",
            "transactionAmount": 5.28,
            "transactionDate": "2021-01-02 10:58:40"
          },
          ...
        ]
      },
      ...
    ]
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

        with open(users_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        user_count = 0
        purchase_count = 0

        for u in data:
            user_name = u["name"]
            user_balance = float(u.get("cashBalance", 0))
            purchase_list = u.get("purchaseHistories", [])

            # 新增 user
            sql_user = """
                INSERT INTO users (name, cash_balance)
                VALUES (%s, %s)
                RETURNING id
            """
            cursor.execute(sql_user, (user_name, user_balance))
            user_id = cursor.fetchone()[0]
            user_count += 1

            # 新增 purchase_histories
            for ph in purchase_list:
                pharmacy_name = ph["pharmacyName"]
                mask_name = ph.get("maskName", "")
                amt = float(ph.get("transactionAmount", 0))
                dt_str = ph.get("transactionDate", "2021-01-01 00:00:00")
                dt_obj = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

                # 查找 pharmacy_id
                sql_find_pharmacy = "SELECT id FROM pharmacies WHERE name=%s"
                cursor.execute(sql_find_pharmacy, (pharmacy_name,))
                row_p = cursor.fetchone()
                if not row_p:
                    print(f"[WARN] Pharmacy '{pharmacy_name}' not found. Skipping.")
                    continue
                pharmacy_id = row_p[0]

                # 查找 mask_id
                sql_find_mask = """
                    SELECT id FROM masks
                    WHERE pharmacy_id=%s AND name=%s
                """
                cursor.execute(sql_find_mask, (pharmacy_id, mask_name))
                row_m = cursor.fetchone()
                if not row_m:
                    print(f"[WARN] Mask '{mask_name}' not found under pharmacy '{pharmacy_name}'. Skipping mask_id.")
                    mask_id = None
                else:
                    mask_id = row_m[0]

                # 預設 quantity=1
                sql_insert_ph = """
                    INSERT INTO purchase_histories
                    (user_id, pharmacy_id, mask_id, mask_name, quantity, transaction_amount, transaction_date)
                    VALUES (%s, %s, %s, %s, 1, %s, %s)
                """
                cursor.execute(sql_insert_ph, (user_id, pharmacy_id, mask_id, mask_name, amt, dt_obj))
                purchase_count += 1

        conn.commit()
        cursor.close()
        print(f"[INFO] Inserted {user_count} users, {purchase_count} purchase records.")
    except Exception as e:
        print("[ERROR] Failed to import users:", e)
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# === 6) 主程式：建表 & 從JSON匯入 ===
def main():
    # (1) 建表
    create_tables()

    # (2) 匯入 pharmacies.json
    import_pharmacies("pharmacies.json")

    # (3) 匯入 users.json
    import_users("users.json")


if __name__ == "__main__":
    main()
