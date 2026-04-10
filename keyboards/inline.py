from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("⚡️ Подключить VPN", callback_data="connect_vpn"),
        InlineKeyboardButton("👤 Профиль", callback_data="my_profile"),
        InlineKeyboardButton("💳 Тарифы", callback_data="show_plans")
    )
    return kb

def profile_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("💰 Пополнить баланс / Купить", callback_data="buy_sub"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")
    )
    return kb