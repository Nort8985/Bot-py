import telebot
from telebot import types
from gradio_client import Client
import sqlite3
import json
import os
import sys

TOKEN = '7821415435:AAFa5yDOmYiOIwFCfbLyoRTnJIcD0Ulzo5Q'
bot = telebot.TeleBot(TOKEN)
client = Client("yuntian-deng/ChatGPT")

game_states = {}
ADMIN_IDS = [1013039772]
conn = sqlite3.connect('chat_history.db', check_same_thread=False)
cursor = conn.cursor()

def init_db():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chats (
        chat_id INTEGER PRIMARY KEY,
        chat_counter INTEGER DEFAULT 0,
        chatbot TEXT DEFAULT '[]'
    )
    ''')
    conn.commit()

init_db()

def is_admin(user_id):
    return user_id in ADMIN_IDS

def stop_game(message):
    chat_id = message.chat.id
    if chat_id in game_states:
        del game_states[chat_id]
    bot.send_message(chat_id, "🛑 Игра остановлена")

@bot.inline_handler(lambda query: len(query.query) > 0)
def handle_inline_query(inline_query):
    try:
        result = client.predict(
            inline_query.query,
            top_p=1,
            temperature=1,
            chat_counter=0,
            chatbot=[],
            api_name="/predict"
        )
        response_text = result[0][-1][1][:500]
        
        item = types.InlineQueryResultArticle(
            id='1',
            title=f'Ответ на: {inline_query.query[:50]}...',
            description=response_text[:100],
            input_message_content=types.InputTextMessageContent(
                message_text=f"🤖 {response_text}\n\n(Запрос: {inline_query.query})"
            )
        )
        bot.answer_inline_query(inline_query.id, [item], cache_time=1)
        
    except Exception as e:
        error_item = types.InlineQueryResultArticle(
            id='error',
            title='Ошибка',
            description=f'Не удалось получить ответ: {str(e)}',
            input_message_content=types.InputTextMessageContent(
                message_text='⚠️ Произошла ошибка при обработке запроса'
            )
        )
        bot.answer_inline_query(inline_query.id, [error_item])

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
    🤖 Добро пожаловать в ChatGPT бота!
    
    Основные команды:
    /start - показать это сообщение
    /help - список всех команд
    /clear - сбросить историю диалога
    
    Инлайн-режим:
    @ваш_бот [ваш запрос]
    """
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
    🆘 Список доступных команд:
    
    Для всех пользователей:
    /start - начать работу
    /help - показать это сообщение
    /clear - сбросить историю чата
    /game - начать игру
    
    """
    
    if is_admin(message.from_user.id):
        help_text += """
        Команды администратора:
        /restart - перезапустить бота
        """
    
    bot.reply_to(message, help_text)

def get_chat_data(chat_id):
    cursor.execute('SELECT chat_counter, chatbot FROM chats WHERE chat_id = ?', (chat_id,))
    result = cursor.fetchone()
    if result:
        return result[0], json.loads(result[1])
    else:
        cursor.execute('INSERT INTO chats (chat_id) VALUES (?)', (chat_id,))
        conn.commit()
        return 0, []

def update_chat_data(chat_id, chat_counter, chatbot):
    cursor.execute('''
    UPDATE chats 
    SET chat_counter = ?, chatbot = ?
    WHERE chat_id = ?
    ''', (chat_counter, json.dumps(chatbot), chat_id))
    conn.commit()

def reset_user_history(chat_id):
    try:
        cursor.execute('''
        UPDATE chats 
        SET chat_counter = 0, 
            chatbot = '[]' 
        WHERE chat_id = ?
        ''', (chat_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"Reset error: {e}")
        return False

@bot.message_handler(commands=['game'])
def start_game(message):
    chat_id = message.chat.id
    game_states[chat_id] = {"playing": True, "current_item": "камень"}
    bot.send_message(chat_id, 
        "🎮 Игра «Что бьёт?» запущена!\n"
        "Текущий предмет: Камень\n"
        "Введите предмет, который может его победить\n"
        "Пример: ножницы\n"
        "Остановить игру: /stop")

@bot.message_handler(func=lambda m: game_states.get(m.chat.id, {}).get('playing', False))
def game_handler(message):
    chat_id = message.chat.id
    user_item = message.text.strip().lower()
    
    if user_item == '/stop':
        stop_game(message)
        return
        
    current_state = game_states[chat_id]
    current_item = current_state["current_item"]
    
    try:
        prompt = (
            f"Ответь только 'да' или 'нет'. "
            f"В классической логике игр, {user_item} бьёт {current_item}?"
        )
        
        result = client.predict(
            prompt,
            top_p=0.1,
            temperature=0.1,
            chat_counter=0,
            chatbot=[],
            api_name="/predict"
        )
        
        response = result[0][-1][1].lower().strip()
        
        if 'да' in response:
            new_item = user_item
            game_states[chat_id]["current_item"] = new_item
            bot.send_message(chat_id, 
                f"✅ Да! {new_item.capitalize()} побеждает {current_item}\n"
                f"Новый текущий предмет: {new_item.capitalize()}\n"
                "Введите следующий предмет:")
                
        elif 'нет' in response:
            del game_states[chat_id]
            bot.send_message(chat_id, 
                f"❌ Нет! {user_item.capitalize()} не побеждает {current_item}\n"
                "Игра завершена")
                
        else:
            del game_states[chat_id]
            bot.send_message(chat_id, "⚠️ Непонятный ответ. Игра перезагружена")
            
    except Exception as e:
        del game_states[chat_id]
        bot.send_message(chat_id, f"🚫 Ошибка: {str(e)}")

@bot.message_handler(commands=['clear'])
def handle_reset(message):
    success = reset_user_history(message.chat.id)
    if success:
        bot.reply_to(message, "🔄 История сброшена! Начните новый диалог")
    else:
        bot.reply_to(message, "⚠️ История не найдена")

@bot.message_handler(commands=['restart'])
def handle_restart(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ У вас нет прав на эту команду")
        return
        
    bot.reply_to(message, "🔄 Инициирован перезапуск бота...")
    conn.close()
    os.execl(sys.executable, sys.executable, *sys.argv)

@bot.message_handler(content_types=['text'])
def send_text(message):
    if message.text.startswith('/'):
        return
        
    chat_id = message.chat.id
    chat_counter, chatbot = get_chat_data(chat_id)
    
    try:
        result = client.predict(
            message.text,
            top_p=1,
            temperature=1,
            chat_counter=chat_counter,
            chatbot=chatbot,
            api_name="/predict"
        )
        
        update_chat_data(chat_id, result[1], result[0])
        bot.send_message(chat_id, result[0][-1][1])
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")
        print(f"API Error: {e}")

def get_all_chat_ids():
    cursor.execute('SELECT chat_id FROM chats')
    return [row[0] for row in cursor.fetchall()]

def notify_all_users():
    for chat_id in get_all_chat_ids():
        try:
            bot.send_message(chat_id, "🚀 Бот был перезапущен и готов к работе!")
        except Exception as e:
            print(f"Ошибка отправки в {chat_id}: {str(e)}")

if __name__ == '__main__':
    print("Бот запущен...")
    try:
        notify_all_users()
        bot.polling()
    except Exception as e:
        print(f"Critical error: {e}")
        conn.close()