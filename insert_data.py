import psycopg2
import json

def connect_db():
    return psycopg2.connect(
        dbname="your_database",
        user="your_user",
        password="your_password",
        host="localhost",
        port="5432"
    )

def create_tables():
    conn = connect_db()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pharmacies (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        cash_balance DECIMAL NOT NULL,
        opening_hours TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS masks (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        price DECIMAL NOT NULL,
        pharmacy_id INT REFERENCES pharmacies(id) ON DELETE CASCADE
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) UNIQUE NOT NULL,
        cash_balance DECIMAL NOT NULL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchase_histories (
        id SERIAL PRIMARY KEY,
        user_id INT REFERENCES users(id) ON DELETE CASCADE,
        pharmacy_id INT REFERENCES pharmacies(id) ON DELETE CASCADE,
        mask_id INT REFERENCES masks(id) ON DELETE CASCADE,
        transaction_amount DECIMAL NOT NULL,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

def insert_data():
    conn = connect_db()
    cursor = conn.cursor()
    
    with open("pharmacies.json", "r", encoding="utf-8") as file:
        pharmacies_data = json.load(file)
    
    for pharmacy in pharmacies_data:
        cursor.execute("""
            INSERT INTO pharmacies (name, cash_balance, opening_hours)
            VALUES (%s, %s, %s) ON CONFLICT (name) DO NOTHING
        """, (pharmacy["name"], pharmacy["cash_balance"], pharmacy["opening_hours"]))
        
        cursor.execute("SELECT id FROM pharmacies WHERE name = %s", (pharmacy["name"],))
        pharmacy_id = cursor.fetchone()[0]
        
        for mask in pharmacy["masks"]:
            cursor.execute("""
                INSERT INTO masks (name, price, pharmacy_id)
                VALUES (%s, %s, %s)
            """, (mask["name"], mask["price"], pharmacy_id))
    
    with open("users.json", "r", encoding="utf-8") as file:
        users_data = json.load(file)
    
    for user in users_data:
        cursor.execute("""
            INSERT INTO users (name, cash_balance)
            VALUES (%s, %s) ON CONFLICT (name) DO NOTHING
        """, (user["name"], user["cash_balance"]))
    
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    create_tables()
    insert_data()
    print("資料已成功匯入 PostgreSQL")
