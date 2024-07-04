import sqlite3
from datetime import datetime

conn = sqlite3.connect('shop.db')
cursor = conn.cursor()

# Проверка существования столбца image_file_id
cursor.execute("PRAGMA table_info(products)")
columns = [column[1] for column in cursor.fetchall()]

# Добавляем новый столбец image_file_id в таблицу products, если его нет
if 'image_file_id' not in columns:
    cursor.execute('ALTER TABLE products ADD COLUMN image_file_id TEXT')

# Проверка существования столбца date
cursor.execute("PRAGMA table_info(sales)")
columns = [column[1] for column in cursor.fetchall()]

# Добавляем новый столбец date в таблицу sales, если его нет
if 'date' not in columns:
    cursor.execute('ALTER TABLE sales ADD COLUMN date TIMESTAMP')
    conn.commit()
    # Обновляем все существующие записи с текущей датой
    cursor.execute('UPDATE sales SET date = ?', (datetime.now(),))
    conn.commit()

conn.close()
