import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Получаем ID админов из .env и превращаем их в список чисел
admin_ids_str = os.getenv("ADMIN_IDS", "123456789")
ADMIN_IDS = [int(i.strip()) for i in admin_ids_str.split(",") if i.strip()]

# Инициализируем бота с дефолтным HTML парсингом
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()