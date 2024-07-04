import telebot
from telebot import types
import sqlite3
from datetime import datetime, timedelta
import os

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect('shop.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, role TEXT, password TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, quantity INTEGER, image_file_id TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY, product_id INTEGER, quantity INTEGER, total_price REAL, date TIMESTAMP, FOREIGN KEY(product_id) REFERENCES products(id))''')
conn.commit()

# пароль: admin123
cursor.execute('INSERT OR IGNORE INTO users (id, role, password) VALUES (1, "admin", "admin123")')
conn.commit()

# пароль: cashier123
cursor.execute('INSERT OR IGNORE INTO users (id, role, password) VALUES (2, "cashier", "cashier123")')
conn.commit()

user_role = {}
product_index = {}
new_product_data = {}

def check_password(password):
    cursor.execute('SELECT id, role FROM users WHERE password=?', (password,))
    result = cursor.fetchone()
    if result:
        return result
    return None

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Введите пароль:")

@bot.message_handler(func=lambda message: message.chat.id not in user_role)
def login(message):
    result = check_password(message.text)
    if result:
        user_id, role = result
        user_role[message.chat.id] = role
        if role == "admin":
            admin_menu(message)
        elif role == "cashier":
            cashier_menu(message)
    else:
        bot.send_message(message.chat.id, "Неверный пароль. Попробуйте еще раз.")

def admin_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Посмотреть список товаров", callback_data="view_products_admin"))
    markup.add(types.InlineKeyboardButton("Добавить товар", callback_data="add_product"))
    markup.add(types.InlineKeyboardButton("Посмотреть отчет", callback_data="view_report"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

def cashier_menu(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Посмотреть список товаров", callback_data="view_products_cashier"))
    markup.add(types.InlineKeyboardButton("Продать товар", callback_data="sell_product"))
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    bot.answer_callback_query(call.id)
    if call.data == "view_products_admin":
        view_products(call.message, "admin")
    elif call.data == "view_products_cashier":
        view_products(call.message, "cashier")
    elif call.data == "add_product":
        msg = bot.send_message(call.message.chat.id, "Введите название товара:")
        bot.register_next_step_handler(msg, add_product_name)
    elif call.data == "view_report":
        show_report_options(call.message)
    elif call.data == "sell_product":
        view_products(call.message, "cashier", action="sell")
    elif call.data.startswith("navigate_"):
        direction, role, action = call.data.split('_')[1:]
        navigate_products(call.message, role, action, direction)
    elif call.data.startswith("action_"):
        action, role, product_id = call.data.split('_')[1:]
        if action == "delete":
            delete_product(call.message, product_id, role)
        elif action == "edit":
            edit_product(call.message, product_id, role)
        elif action == "sell":
            sell_product_step(call.message, product_id)
    elif call.data.startswith("report_"):
        period = call.data.split('_')[1]
        view_report(call.message, period)
    elif call.data.startswith("back_"):
        role = call.data.split('_')[1]
        if role == "admin":
            admin_menu(call.message)
        elif role == "cashier":
            cashier_menu(call.message)

def show_report_options(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("День", callback_data="report_day"))
    markup.add(types.InlineKeyboardButton("Неделя", callback_data="report_week"))
    markup.add(types.InlineKeyboardButton("Месяц", callback_data="report_month"))
    markup.add(types.InlineKeyboardButton("Год", callback_data="report_year"))
    markup.add(types.InlineKeyboardButton("Все время", callback_data="report_all"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data=f"back_admin"))
    bot.edit_message_text("Выберите период для отчета:", chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)

def view_products(message, role, action=None):
    cursor.execute('SELECT id, name, price, quantity, image_file_id FROM products')
    products = cursor.fetchall()
    if not products:
        bot.send_message(message.chat.id, "Товары отсутствуют.")
        if role == "admin":
            admin_menu(message)
        else:
            cashier_menu(message)
        return

    if message.chat.id not in product_index:
        product_index[message.chat.id] = 0

    index = product_index[message.chat.id]
    if index >= len(products):
        index = 0
        product_index[message.chat.id] = 0
    product = products[index]
    response = f"{product[1]}\nЦена: {product[2]} руб.\nКоличество: {product[3]} шт."

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Предыдущий", callback_data=f"navigate_prev_{role}_{action or 'none'}"),
               types.InlineKeyboardButton("Следующий", callback_data=f"navigate_next_{role}_{action or 'none'}"))
    if role == "admin":
        markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"action_delete_{role}_{product[0]}"))
        markup.add(types.InlineKeyboardButton("Изменить", callback_data=f"action_edit_{role}_{product[0]}"))
    if action == "sell":
        markup.add(types.InlineKeyboardButton("Продать", callback_data=f"action_sell_{role}_{product[0]}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data=f"back_{role}"))

    if product[4]:
        media = types.InputMediaPhoto(product[4], caption=response)
        try:
            bot.edit_message_media(media, chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
        except:
            bot.send_photo(message.chat.id, product[4], caption=response, reply_markup=markup)
    else:
        try:
            bot.edit_message_text(text=response, chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id=message.chat.id, text=response, reply_markup=markup)

def navigate_products(message, role, action, direction):
    cursor.execute('SELECT COUNT(*) FROM products')
    count = cursor.fetchone()[0]
    index = product_index[message.chat.id]
    if direction == "next":
        index = (index + 1) % count
    elif direction == "prev":
        index = (index - 1) % count
    product_index[message.chat.id] = index

    cursor.execute('SELECT id, name, price, quantity, image_file_id FROM products')
    products = cursor.fetchall()
    if index >= len(products):
        index = 0
        product_index[message.chat.id] = 0
    product = products[index]
    response = f"{product[1]}\nЦена: {product[2]} руб.\nКоличество: {product[3]} шт."

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Предыдущий", callback_data=f"navigate_prev_{role}_{action or 'none'}"),
               types.InlineKeyboardButton("Следующий", callback_data=f"navigate_next_{role}_{action or 'none'}"))
    if role == "admin":
        markup.add(types.InlineKeyboardButton("Удалить", callback_data=f"action_delete_{role}_{product[0]}"))
        markup.add(types.InlineKeyboardButton("Изменить", callback_data=f"action_edit_{role}_{product[0]}"))
    if action == "sell":
        markup.add(types.InlineKeyboardButton("Продать", callback_data=f"action_sell_{role}_{product[0]}"))
    markup.add(types.InlineKeyboardButton("Назад", callback_data=f"back_{role}"))

    if product[4]:
        media = types.InputMediaPhoto(product[4], caption=response)
        try:
            bot.edit_message_media(media, chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
        except:
            bot.send_photo(message.chat.id, product[4], caption=response, reply_markup=markup)
    else:
        try:
            bot.edit_message_text(text=response, chat_id=message.chat.id, message_id=message.message_id, reply_markup=markup)
        except:
            bot.send_message(chat_id=message.chat.id, text=response, reply_markup=markup)

def add_product_name(message):
    name = message.text
    new_product_data[message.chat.id] = {'name': name}
    msg = bot.send_message(message.chat.id, "Введите цену товара:")
    bot.register_next_step_handler(msg, add_product_price)

def add_product_price(message):
    try:
        price = float(message.text)
        new_product_data[message.chat.id]['price'] = price
        msg = bot.send_message(message.chat.id, "Введите количество товара:")
        bot.register_next_step_handler(msg, add_product_quantity)
    except ValueError:
        bot.send_message(message.chat.id, "Цена должна быть числом. Попробуйте снова.")
        msg = bot.send_message(message.chat.id, "Введите цену товара:")
        bot.register_next_step_handler(msg, add_product_price)

def add_product_quantity(message):
    try:
        quantity = int(message.text)
        new_product_data[message.chat.id]['quantity'] = quantity
        msg = bot.send_message(message.chat.id, "Отправьте фото товара:")
        bot.register_next_step_handler(msg, add_product_image)
    except ValueError:
        bot.send_message(message.chat.id, "Количество должно быть целым числом. Попробуйте снова.")
        msg = bot.send_message(message.chat.id, "Введите количество товара:")
        bot.register_next_step_handler(msg, add_product_quantity)

@bot.message_handler(content_types=['photo'])
def add_product_image(message):
    if message.chat.id in new_product_data:
        file_id = message.photo[-1].file_id
        product_data = new_product_data.pop(message.chat.id)
        cursor.execute('INSERT INTO products (name, price, quantity, image_file_id) VALUES (?, ?, ?, ?)',
                       (product_data['name'], product_data['price'], product_data['quantity'], file_id))
        conn.commit()
        bot.send_message(message.chat.id, "Товар добавлен.")
        admin_menu(message)

def delete_product(message, product_id, role):
    cursor.execute('DELETE FROM products WHERE id=?', (product_id,))
    conn.commit()
    bot.send_message(message.chat.id, "Товар удален!")
    cursor.execute('SELECT id, name, price, quantity, image_file_id FROM products')
    products = cursor.fetchall()
    if not products:
        if role == "admin":
            admin_menu(message)
        else:
            cashier_menu(message)
        return
    product_index[message.chat.id] = 0
    view_products(message, role)

def edit_product(message, product_id, role):
    cursor.execute('SELECT name, price, quantity, image_file_id FROM products WHERE id=?', (product_id,))
    product = cursor.fetchone()
    if product:
        msg = bot.send_message(message.chat.id, f"Текущие данные:\nНазвание: {product[0]}\nЦена: {product[1]}\nКоличество: {product[2]}\n\nВведите новое название (или оставьте пустым для сохранения текущего):")
        bot.register_next_step_handler(msg, update_product_name, product_id, role)
    else:
        bot.send_message(message.chat.id, "Товар не найден.")
        if role == "admin":
            admin_menu(message)
        else:
            cashier_menu(message)

def update_product_name(message, product_id, role):
    new_name = message.text or None
    msg = bot.send_message(message.chat.id, "Введите новую цену (или оставьте пустым для сохранения текущей):")
    bot.register_next_step_handler(msg, update_product_price, product_id, role, new_name)

def update_product_price(message, product_id, role, new_name):
    try:
        new_price = float(message.text) if message.text else None
        msg = bot.send_message(message.chat.id, "Введите новое количество (или оставьте пустым для сохранения текущего):")
        bot.register_next_step_handler(msg, update_product_quantity, product_id, role, new_name, new_price)
    except ValueError:
        bot.send_message(message.chat.id, "Цена должна быть числом. Попробуйте снова.")
        msg = bot.send_message(message.chat.id, "Введите новую цену (или оставьте пустым для сохранения текущей):")
        bot.register_next_step_handler(msg, update_product_price, product_id, role, new_name)

def update_product_quantity(message, product_id, role, new_name, new_price):
    try:
        new_quantity = int(message.text) if message.text else None
        cursor.execute('SELECT name, price, quantity FROM products WHERE id=?', (product_id,))
        current_product = cursor.fetchone()
        name = new_name or current_product[0]
        price = new_price or current_product[1]
        quantity = new_quantity or current_product[2]
        cursor.execute('UPDATE products SET name=?, price=?, quantity=? WHERE id=?', (name, price, quantity, product_id))
        conn.commit()
        bot.send_message(message.chat.id, "Товар обновлен.")
        view_products(message, role)
    except ValueError:
        bot.send_message(message.chat.id, "Количество должно быть целым числом. Попробуйте снова.")
        msg = bot.send_message(message.chat.id, "Введите новое количество (или оставьте пустым для сохранения текущего):")
        bot.register_next_step_handler(msg, update_product_quantity, product_id, role, new_name, new_price)

def view_report(message, period):
    now = datetime.now()
    if period == 'day':
        start_date = now - timedelta(days=1)
    elif period == 'week':
        start_date = now - timedelta(weeks=1)
    elif period == 'month':
        start_date = now - timedelta(days=30)
    elif period == 'year':
        start_date = now - timedelta(days=365)
    elif period == 'all':
        start_date = datetime.min
    else:
        bot.send_message(message.chat.id, "Неизвестный период.")
        return

    print(f"Start date: {start_date}")
    cursor.execute('SELECT p.name, s.quantity, s.total_price, s.date FROM sales s JOIN products p ON s.product_id = p.id WHERE s.date >= ?', (start_date,))
    sales = cursor.fetchall()
    print(f"Sales fetched: {sales}")
    if not sales:
        bot.send_message(message.chat.id, "Продажи отсутствуют за выбранный период.")
        return

    response = f"Отчет о продажах за {period}:\n"
    for sale in sales:
        response += f"{sale[0]} - {sale[1]} шт. - {sale[2]} сом. ({sale[3]})\n"
    bot.send_message(message.chat.id, response)

def sell_product_step(message, product_id):
    msg = bot.send_message(message.chat.id, "Введите количество:")
    bot.register_next_step_handler(msg, sell_product_quantity, product_id)


def sell_product_quantity(message, product_id):
    try:
        quantity = int(message.text)
        cursor.execute('SELECT price, quantity FROM products WHERE id=?', (product_id,))
        product = cursor.fetchone()
        if product and product[1] >= quantity:
            total_price = product[0] * quantity
            new_quantity = product[1] - quantity
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"Selling {quantity} of product {product_id} for total price {total_price} at {current_time}")

            if new_quantity == 0:
                cursor.execute('DELETE FROM products WHERE id=?', (product_id,))
                conn.commit()
                print(f"Product {product_id} deleted from products table.")
            else:
                cursor.execute('UPDATE products SET quantity=? WHERE id=?', (new_quantity, product_id))
                conn.commit()
                print(f"Product {product_id} updated in products table with new quantity {new_quantity}.")

            # вставка данных о продаже
            cursor.execute('INSERT INTO sales (product_id, quantity, total_price, date) VALUES (?, ?, ?, ?)', (product_id, quantity, total_price, current_time))
            print(f"Inserted sale record for product {product_id}, quantity {quantity}, total_price {total_price}, date {current_time}.")

            # проверка данных в таблице sales до commit
            cursor.execute('SELECT * FROM sales WHERE product_id=? AND date=?', (product_id, current_time))
            sales_check_before_commit = cursor.fetchall()
            print(f"Sales table before commit: {sales_check_before_commit}")

            if not sales_check_before_commit:
                print("Data not inserted into sales table before commit.")
            
            conn.commit()
            print("Sale committed to database.")

            # проверка данных в таблице sales после commit
            cursor.execute('SELECT * FROM sales WHERE product_id=? AND date=?', (product_id, current_time))
            sales_check_after_commit = cursor.fetchall()
            print(f"Sales table after commit: {sales_check_after_commit}")

            if sales_check_after_commit:
                bot.send_message(message.chat.id, "Продажа завершена.")
            else:
                bot.send_message(message.chat.id, "Ошибка записи в базу данных.")
        else:
            bot.send_message(message.chat.id, "Недостаточно товара на складе.")
        cashier_menu(message)
    except ValueError:
        bot.send_message(message.chat.id, "Количество должно быть целым числом. Попробуйте снова.")
        msg = bot.send_message(message.chat.id, "Введите количество:")
        bot.register_next_step_handler(msg, sell_product_quantity, product_id)
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        bot.send_message(message.chat.id, "Ошибка базы данных. Попробуйте еще раз.")


bot.infinity_polling()
