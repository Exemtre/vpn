import asyncio
import logging

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import (
    get_bot_settings,
    get_users_expiring_soon,
    get_users_not_connected,
    check_notification_sent,
    mark_notification_sent,
)

_EXPIRY_DEFAULT_TEXT = (
    "⚠️ Завтра закончится ваша подписка на Anonch VPN\n\n"
    "Автоматического продления нет! Чтобы не остаться без связи, "
    "продлите свою подписку в разделе /profile"
)
_NOCONN_DEFAULT_TEXT = (
    "🤖 Мы заметили, что вы еще не подключились\n\n"
    "Если возникли сложности — напишите в поддержку. Мы всегда готовы помочь!"
)


NOTIFICATION_CHECK_INTERVAL = 3600  # seconds between scheduler runs


def _is_valid_emoji_id(eid):
    """Returns True only when eid is a non-zero numeric string (valid custom emoji ID)."""
    return bool(eid and str(eid).strip().isdigit() and str(eid).strip() != "0")


def _make_notif_btn(text, callback_data, emoji_id):
    """Creates an InlineKeyboardButton for a notification.
    icon_custom_emoji_id is not valid for callback buttons; emoji_id is ignored here.
    """
    return InlineKeyboardButton(text=text, callback_data=callback_data)


async def check_and_send_notifications(bot):
    s = get_bot_settings()

    # ── Уведомление об истечении подписки ─────────────────────────────────────
    if s.get("notif_expiry_enabled", "1") == "1":
        try:
            hours = int(s.get("notif_expiry_hours", "24"))
        except (ValueError, TypeError):
            hours = 24
        text = s.get("notif_expiry_text", _EXPIRY_DEFAULT_TEXT)
        btn_text = s.get("notif_expiry_btn", "📋 Перейти к продлению")
        btn_emoji_id = s.get("notif_expiry_btn_emoji_id", "0")

        users = get_users_expiring_soon(hours)
        for user in users:
            user_id = user["user_id"]
            sub_expires = user.get("sub_expires", "")
            notif_key = f"expiry_{sub_expires[:10]}"
            if check_notification_sent(user_id, notif_key):
                continue
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [_make_notif_btn(btn_text, "manage_vpn", btn_emoji_id)]
                ])
                await bot.send_message(user_id, text, reply_markup=kb)
                mark_notification_sent(user_id, notif_key)
            except Exception as e:
                logging.warning(f"Expiry notification failed for {user_id}: {e}")

    # ── Уведомление «не подключился» ──────────────────────────────────────────
    if s.get("notif_noconn_enabled", "1") == "1":
        try:
            hours = int(s.get("notif_noconn_hours", "2"))
        except (ValueError, TypeError):
            hours = 2
        text = s.get("notif_noconn_text", _NOCONN_DEFAULT_TEXT)
        btn_text = s.get("notif_noconn_btn", "Подключиться")
        btn_emoji_id = s.get("notif_noconn_btn_emoji_id", "0")
        support_url = s.get("info_support_url", "")

        users = get_users_not_connected(hours)
        for user in users:
            user_id = user["user_id"]
            started_at = user.get("started_at", "")
            notif_key = f"noconn_{started_at[:16]}"
            if check_notification_sent(user_id, notif_key):
                continue
            try:
                kb_rows = []
                if support_url:
                    kb_rows.append([InlineKeyboardButton(text="СВЯЗАТЬСЯ", url=support_url)])
                kb_rows.append([_make_notif_btn(btn_text, "manage_vpn", btn_emoji_id)])
                kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
                await bot.send_message(user_id, text, reply_markup=kb)
                mark_notification_sent(user_id, notif_key)
            except Exception as e:
                logging.warning(f"Noconn notification failed for {user_id}: {e}")


async def scheduler_task(bot):
    """Фоновый планировщик уведомлений — запускается раз в час."""
    while True:
        try:
            await check_and_send_notifications(bot)
        except Exception as e:
            logging.error(f"Notification scheduler error: {e}")
        await asyncio.sleep(NOTIFICATION_CHECK_INTERVAL)
