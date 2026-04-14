import asyncio
import logging
from config import bot, dp
from database.models import init_db

# Импортируем роутеры из хендлеров
from handlers.admin import admin_router
from handlers.user import user_router
from handlers.notifications import scheduler_task


async def main():
    # Настраиваем логирование
    logging.basicConfig(level=logging.INFO)

    # 1. Инициализируем БД
    init_db()

    # 2. Регистрируем роутеры (админский первым, чтобы он перехватывал свои команды)
    dp.include_router(admin_router)
    dp.include_router(user_router)

    # 3. Fallback (Эхо-хендлер для неизвестных сообщений)
    # В aiogram 3 он делается внутри роутера или просто добавляется последним

    # 4. Запускаем планировщик уведомлений
    asyncio.create_task(scheduler_task(bot))

    # 5. Запуск поллинга
    print("Бот запущен на aiogram 3...")
    # Пропускаем старые апдейты, чтобы бот не спамил при включении
    for attempt in range(5):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            break
        except Exception as e:
            if attempt < 4:
                logging.warning(f"delete_webhook failed (attempt {attempt + 1}/5): {e}. Retrying in 3s...")
                await asyncio.sleep(3)
            else:
                logging.warning(f"delete_webhook failed after 5 attempts, continuing anyway: {e}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())