import os
import hashlib
import hmac
import time
import logging
import aiohttp

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
                           ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from database.models import (
    get_bot_settings, get_all_plans, get_plan, set_subscription, create_user,
    get_user, update_user_balance, update_user_vpn_key, update_user_sub_url,
    has_used_trial, create_gift, get_gift, claim_gift,
    get_promo, use_promo, get_referral_stats, add_subscription_days,
    get_user_devices, delete_user_device
)
from config import ADMIN_IDS
from datetime import datetime, timedelta, timezone
from marzban import marzban_create_or_update_user, marzban_get_user_status

user_router = Router()


class UserStates(StatesGroup):
    wait_for_promo = State()
    wait_for_yoo_check = State()
    wait_for_crypto_check = State()


def ce(emoji_id, fallback):
    if emoji_id and emoji_id != "0":
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return fallback


def _is_valid_emoji_id(eid):
    """Returns True only when eid is a non-zero numeric string (valid custom emoji ID)."""
    return bool(eid and str(eid).strip().isdigit() and str(eid).strip() != "0")


async def _check_forced_subscription(user_id: int, bot) -> bool:
    """Returns True if forced-channel check passes (not enabled, or user is member)."""
    s = get_bot_settings()
    if s.get("forced_sub_enabled", "0") != "1":
        return True
    channel = s.get("forced_sub_channel", "").strip()
    if not channel:
        return True
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return True  # fail-open so a mis-configured channel doesn't lock everyone out


async def _send_forced_sub_message(user_id: int, bot):
    """Sends the 'please subscribe' gate message."""
    s = get_bot_settings()
    channel = s.get("forced_sub_channel", "").strip()
    text = s.get("forced_sub_text",
                 "🔒 Для использования бота необходимо подписаться на наш канал.")
    channel_url = channel if channel.startswith("http") else f"https://t.me/{channel.lstrip('@')}"
    sub_e = ce(s.get("ge_forced_sub_btn", "0"), "📢")
    check_e = ce(s.get("ge_forced_sub_check_btn", "0"), "✅")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{sub_e} Подписаться", url=channel_url)],
        [InlineKeyboardButton(text=f"{check_e} Я подписался", callback_data="forced_sub_check")],
    ])
    await bot.send_message(user_id, text, reply_markup=kb)


def get_main_reply_kb(user_id: int):
    s = get_bot_settings()
    vpn_e = s.get("kb_vpn_emoji", "⚡️")
    prof_e = s.get("kb_profile_emoji", "👤")
    info_e = s.get("kb_info_emoji", "ℹ️")
    adm_e = s.get("kb_admin_emoji", "🔧")
    kb = [
        [KeyboardButton(text=f"{vpn_e} Подключить VPN")],
        [KeyboardButton(text=f"{prof_e} Профиль"), KeyboardButton(text=f"{info_e} Информация")]
    ]
    if user_id in ADMIN_IDS:
        kb.append([KeyboardButton(text=f"{adm_e} Администрирование")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, is_persistent=True)


def make_btn(text_key, default_text, cb_data, emoji_key, static_emoji=""):
    s = get_bot_settings()
    text = s.get(text_key, default_text)
    eid = s.get(emoji_key, "")
    if _is_valid_emoji_id(eid):
        return InlineKeyboardButton(text=text, callback_data=cb_data, icon_custom_emoji_id=str(eid))
    char = eid if (eid and eid != "0") else static_emoji
    return InlineKeyboardButton(text=f"{char} {text}" if char else text, callback_data=cb_data)


def make_url_btn(text_key, default_text, url, emoji_key, static_emoji=""):
    s = get_bot_settings()
    text = s.get(text_key, default_text)
    eid = s.get(emoji_key, "")
    if _is_valid_emoji_id(eid):
        return InlineKeyboardButton(text=text, url=url, icon_custom_emoji_id=str(eid))
    char = eid if (eid and eid != "0") else static_emoji
    return InlineKeyboardButton(text=f"{char} {text}" if char else text, url=url)


def _build_dual_emoji_btn(s, label, char_key, default_char, id_key, url=None, cb=None):
    """Build an InlineKeyboardButton using separate char and custom-emoji-ID settings.
    When a valid custom emoji ID is present the text contains no char prefix so the
    icon_custom_emoji_id is the only emoji shown.  Otherwise the plain char is prepended.
    """
    eid = s.get(id_key, "0")
    if _is_valid_emoji_id(eid):
        if url:
            return InlineKeyboardButton(text=label, url=url, icon_custom_emoji_id=str(eid))
        return InlineKeyboardButton(text=label, callback_data=cb, icon_custom_emoji_id=str(eid))
    e = s.get(char_key, default_char)
    txt = f"{e} {label}" if e else label
    if url:
        return InlineKeyboardButton(text=txt, url=url)
    return InlineKeyboardButton(text=txt, callback_data=cb)


def main_menu_kb():
    s = get_bot_settings()
    vpn_id = s.get("kb_vpn_emoji_id", "0")
    if _is_valid_emoji_id(vpn_id):
        vpn_btn = InlineKeyboardButton(
            text=s.get("btn_vpn", "Управление VPN"),
            callback_data="manage_vpn",
            icon_custom_emoji_id=str(vpn_id)
        )
    else:
        vpn_btn = make_btn("btn_vpn", "Управление VPN", "manage_vpn", "btn_vpn_emoji", "🌐")
    return InlineKeyboardMarkup(inline_keyboard=[
        [vpn_btn],
        [make_btn("btn_ref", "Пригласить друга", "ref_menu", "btn_ref_emoji", "🤝")],
        [make_btn("btn_gift", "Подарить подписку", "gift_sub", "btn_gift_emoji", "🎁")]
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("btn_prof_buy", "Оформить подписку", "manage_vpn", "btn_prof_buy_emoji", "💳")],
        [make_btn("btn_ref", "Пригласить друга", "ref_menu", "btn_ref_emoji", "🤝")],
        [make_btn("btn_gift", "Подарить подписку", "gift_sub", "btn_gift_emoji", "🎁")]
    ])


def active_vpn_kb(sub_url: str = ""):
    s = get_bot_settings()
    install_url = sub_url or s.get("info_install_url", "")
    rows = []
    if install_url:
        rows.append([_build_dual_emoji_btn(s, "Установить VPN", "btn_install_vpn_emoji", "📲", "btn_install_vpn_emoji_id", url=install_url)])
    else:
        rows.append([_build_dual_emoji_btn(s, "Установить VPN", "btn_install_vpn_emoji", "📲", "btn_install_vpn_emoji_id", cb="install_vpn_stub")])
    rows.append([_build_dual_emoji_btn(s, "Подключённые устройства", "btn_devices_emoji", "📱", "btn_devices_emoji_id", cb="connected_devices")])
    rows.append([_build_dual_emoji_btn(s, "Продлить подписку", "btn_renew_emoji", "🔄", "btn_renew_emoji_id", cb="renew_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def payment_success_kb(sub_url: str = ""):
    s = get_bot_settings()
    install_url = sub_url or s.get("info_install_url", "")
    support_url = s.get("info_support_url", "")
    rows = []
    if install_url:
        rows.append([_build_dual_emoji_btn(s, "Установить VPN", "btn_install_vpn_emoji", "📲", "btn_install_vpn_emoji_id", url=install_url)])
    else:
        rows.append([_build_dual_emoji_btn(s, "Установить VPN", "btn_install_vpn_emoji", "📲", "btn_install_vpn_emoji_id", cb="install_vpn_stub")])
    if support_url:
        rows.append([_build_dual_emoji_btn(s, "Техническая поддержка", "btn_info_support_emoji", "🛠", "btn_info_support_emoji_id", url=support_url)])
    else:
        rows.append([_build_dual_emoji_btn(s, "Техническая поддержка", "btn_info_support_emoji", "🛠", "btn_info_support_emoji_id", cb="support_stub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_payment_success_text(plan, user_id: int, price: int, method: str = "", user_vpn_link: str = "", user_sub_url: str = "") -> str:
    s = get_bot_settings()
    e_success = ce(s.get("ge_pay_success", "0"), "⭐")
    e_price = ce(s.get("ge_pay_price", "0"), "💰")
    e_expires = ce(s.get("ge_pay_expires", "0"), "📅")
    e_plan = ce(s.get("ge_pay_plan", "0"), "📦")
    e_method = ce(s.get("ge_pay_method", "0"), "💳")
    e_num = ce(s.get("ge_pay_num", "0"), "🔢")
    e_link = ce(s.get("ge_pay_link", "0"), "🔗")
    e_sub_url = ce(s.get("ge_sub_url", "0"), "🌐")
    e_note = ce(s.get("ge_pay_note", "0"), "📝")
    e_sub = ce(s.get("ge_active_sub", "0"), "🔐")
    e_status = ce(s.get("ge_sub_active", "0"), "✅")

    title = s.get("pay_success_title", "Счёт на оплату подписки успешно создан.")
    exp_date = (datetime.utcnow() + timedelta(days=plan['days'])).strftime("%d.%m.%Y")
    method_names = {"stars": "Telegram Stars", "crypto": "Криптовалюта",
                    "yoo": "ЮMoney", "balance": "Баланс", "free": "Бесплатно"}
    method_label = method_names.get(method, method or "—")
    pay_num = str(user_id)[-8:]

    text = f"{e_success} <b>{title}</b>\n\n"
    text += f"{e_price} Стоимость: {price} руб/{plan['label']}\n"
    text += f"{e_expires} Подписка до: <b>{exp_date}</b>\n"
    text += f"{e_plan} План подписки: {plan['label']}\n"
    if method:
        text += f"{e_method} Метод оплаты: {method_label}\n"
    text += f"{e_num} Номер оплаты: {pay_num}\n"

    vpn_link = user_vpn_link or plan.get('vpn_link', '')
    if vpn_link and vpn_link != 'Ссылка не задана':
        text += f"\n{e_sub} <b>Ваша подписка AnonchVPN</b>\n"
        text += f"├ Статус: {e_status} Активна\n"
        text += f"└ Оплачена до: {exp_date}\n\n"
        text += f"{e_link} <b>Ваш ключ:</b> <code>{vpn_link}</code>\n"
        if user_sub_url:
            text += f"\n{e_sub_url} <b>Ссылка подписки:</b> <code>{user_sub_url}</code>\n"
        text += "\n"
    elif user_sub_url:
        text += f"\n{e_sub} <b>Ваша подписка AnonchVPN</b>\n"
        text += f"├ Статус: {e_status} Активна\n"
        text += f"└ Оплачена до: {exp_date}\n\n"
        text += f"{e_sub_url} <b>Ссылка подписки:</b> <code>{user_sub_url}</code>\n\n"

    note = s.get("pay_success_note",
                 "Подписка будет выдана автоматически после оплаты.\nЕсли столкнулись с проблемами – обратитесь в нашу поддержку, вам помогут.")
    text += f"{e_note} {note}"
    return text


def _get_effective_sub_url(user_id: int, stored_sub_url: str, s: dict) -> str:
    """Return the subscription URL for a user.

    Priority:
    1. The value stored in the DB (set at activation time).
    2. If not stored but Marzban is enabled, derive it as <marzban_url>/sub/tg<user_id>.
    3. Otherwise return empty string.
    """
    if stored_sub_url:
        return stored_sub_url
    if s.get("marzban_enabled", "0") == "1":
        marzban_url = s.get("marzban_url", "").rstrip("/")
        if marzban_url:
            return f"{marzban_url}/sub/tg{user_id}"
    return ""


async def notify_admins(bot, text: str):
    """Send a notification message to all configured admin IDs."""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def _activate_and_notify(bot, user_id: int, plan_code: str, days: int, price: int, method: str = ""):
    u = get_user(user_id)
    if u and u.get('referrer_id') and days >= 30:
        referrer_id_val = u['referrer_id']
        add_subscription_days(referrer_id_val, 10)
        # Also extend Marzban subscription for the referrer so their VPN stays active
        referrer = get_user(referrer_id_val)
        if referrer and referrer.get('sub_expires'):
            try:
                ref_exp = datetime.fromisoformat(referrer['sub_expires'])
                ref_remaining = max(1, (ref_exp - datetime.utcnow()).days)
                await marzban_create_or_update_user(int(referrer_id_val), ref_remaining)
            except Exception as ref_mz_err:
                logging.warning(f"[Marzban] Referrer update error for {referrer_id_val}: {ref_mz_err}")
        try:
            await bot.send_message(referrer_id_val, "🎁 Друг купил подписку! Вам начислено +10 дней.")
        except:
            pass
    set_subscription(user_id, plan_code, days, price)

    # Integrate with Marzban: create/update user and get personal VPN links
    user_vpn_link = ""
    user_sub_url = ""
    s = get_bot_settings()
    try:
        result = await marzban_create_or_update_user(user_id, days)
        if result:
            vpn_key, sub_url = result
            if vpn_key:
                update_user_vpn_key(user_id, vpn_key)
                user_vpn_link = vpn_key
            if sub_url:
                update_user_sub_url(user_id, sub_url)
                user_sub_url = sub_url
    except Exception as e:
        logging.warning(f"[Marzban] Activation error for {user_id}: {e}")

    # Fall back to already-stored key if Marzban PUT didn't return links
    if not user_vpn_link:
        stored_u = get_user(user_id)
        user_vpn_link = (stored_u or {}).get('vpn_key', '') or ''

    # Ensure sub_url is available (derive from Marzban URL if not returned)
    user_sub_url = _get_effective_sub_url(user_id, user_sub_url, s)

    # Full invoice sent to admins only
    p = get_plan(plan_code)
    method_names = {"stars": "Telegram Stars", "crypto": "Криптовалюта",
                    "yoo": "ЮMoney", "balance": "Баланс", "free": "Бесплатно"}
    method_label = method_names.get(method, method or "—")
    plan_label = p['label'] if p else plan_code
    exp_date = (datetime.utcnow() + timedelta(days=days)).strftime("%d.%m.%Y")
    pay_num = str(user_id)[-8:]
    if plan_code == 'plan_trial':
        admin_text = (
            f"🆓 <b>Новая пробная подписка</b>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"📦 Тариф: {plan_label}\n"
            f"📅 До: {exp_date}"
        )
    else:
        admin_text = (
            f"💰 <b>Новая покупка!</b>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"📦 Тариф: {plan_label}\n"
            f"💵 Сумма: {price} ₽\n"
            f"💳 Метод: {method_label}\n"
            f"📅 До: {exp_date}\n"
            f"🔢 Номер: {pay_num}"
        )
    await notify_admins(bot, admin_text)

    # User receives the clean active-VPN screen (no invoice details)
    fresh_user = get_user(user_id)
    await _send_active_vpn_screen(user_id, fresh_user, bot=bot)
    # Restore the main reply keyboard so bottom buttons are always visible
    try:
        await bot.send_message(user_id, ".", reply_markup=get_main_reply_kb(user_id))
    except Exception:
        pass


async def _send_active_vpn_screen(chat_id, user, bot=None):
    s = get_bot_settings()
    p = get_plan(user.get('plan', '')) or {}
    try:
        exp_dt = datetime.fromisoformat(user['sub_expires'])
        exp = exp_dt.strftime("%d.%m.%Y")
    except:
        exp = "—"

    e_sub = ce(s.get("ge_active_sub", "0"), "🔐")
    e_status = ce(s.get("ge_sub_active", "0"), "✅")
    e_link = ce(s.get("ge_vpn_link", "0"), "🔗")
    e_sub_url = ce(s.get("ge_sub_url", "0"), "🌐")
    e_hint = ce(s.get("ge_active_hint", "0"), "💡")

    title_tpl = s.get("active_vpn_title",
                      "{e_sub} <b>Ваша подписка AnonchVPN</b>\n├ Статус: {e_status} Активна\n└ Оплачена до: <b>{exp}</b>")
    title = title_tpl.replace("{e_sub}", e_sub).replace("{e_status}", e_status).replace("{exp}", exp)

    vpn_link = user.get('vpn_key') or p.get('vpn_link', '')
    sub_url = _get_effective_sub_url(user.get('user_id', 0), user.get('sub_url', ''), s)
    link_line = ""
    if vpn_link and vpn_link != 'Ссылка не задана':
        link_line = f"\n\n{e_link} <b>Ваш ключ:</b> <code>{vpn_link}</code>"
        if sub_url:
            link_line += f"\n{e_sub_url} <b>Ссылка подписки:</b> <a href=\"{sub_url}\">{sub_url}</a>"
    elif sub_url:
        link_line = f"\n\n{e_sub_url} <b>Ссылка подписки:</b> <a href=\"{sub_url}\">{sub_url}</a>"

    hint_tpl = s.get("active_vpn_hint", "\n\n{e_hint} Для подключения к VPN используйте кнопку снизу.")
    hint = hint_tpl.replace("{e_hint}", e_hint)

    text = title + link_line + hint
    sticker = s.get("sticker_active_vpn", "")
    if sticker and bot:
        try:
            await bot.send_sticker(chat_id, sticker)
        except:
            pass
    await bot.send_message(chat_id, text, reply_markup=active_vpn_kb(sub_url=sub_url),
                           disable_web_page_preview=True)


@user_router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    referrer_id = None

    if len(args) > 1 and args[1].startswith("gift_"):
        token = args[1].replace("gift_", "")
        gift = get_gift(token)
        if gift:
            claim_gift(token, message.from_user.id)
            is_new = create_user(message.from_user.id, message.from_user.full_name, message.from_user.username,
                        str(gift['from_user_id']))
            if is_new:
                await notify_admins(message.bot,
                    f"👤 <b>Новый пользователь (через подарок)</b>\n"
                    f"ID: <code>{message.from_user.id}</code>\n"
                    f"Имя: {message.from_user.full_name}"
                )
            await _activate_and_notify(message.bot, message.from_user.id, gift['plan_code'], gift['days'], 0, "gift")
            if gift['days'] >= 30:
                add_subscription_days(gift['from_user_id'], 10)
                try:
                    await message.bot.send_message(
                        gift['from_user_id'],
                        f"🎉 Ваш подарок активирован! Друг подключился — вам начислено <b>+10 дней</b> к подписке."
                    )
                except:
                    pass
            return await message.answer(
                "🎉 <b>Подарок активирован!</b>\nВаша подписка VPN выдана автоматически. Перейдите в <b>Подключить VPN</b>, чтобы увидеть свой ключ.",
                reply_markup=get_main_reply_kb(message.from_user.id))

    if len(args) > 1 and args[1].isdigit():
        referrer_id = args[1]

    is_new = create_user(message.from_user.id, message.from_user.full_name, message.from_user.username, referrer_id)
    if is_new:
        await notify_admins(message.bot,
            f"👤 <b>Новый пользователь</b>\n"
            f"ID: <code>{message.from_user.id}</code>\n"
            f"Имя: {message.from_user.full_name}"
        )

    if not await _check_forced_subscription(message.from_user.id, message.bot):
        await _send_forced_sub_message(message.from_user.id, message.bot)
        return

    s = get_bot_settings()
    gif = s.get("start_media_id")
    sticker = s.get("start_sticker_id")
    text = s.get("start_text", "<b>🔐 Добро пожаловать в AnonchVPN!</b>\n\nЯ — ваш помощник в мире интернет-свободы!")

    if sticker:
        try:
            await message.answer_sticker(sticker)
        except:
            pass

    if gif:
        gif_sent = False
        try:
            await message.answer_animation(animation=gif, caption=text, reply_markup=main_menu_kb())
            gif_sent = True
        except:
            pass
        if gif_sent:
            await message.answer("\u3164", reply_markup=get_main_reply_kb(message.from_user.id))
            return

    await message.answer(text, reply_markup=get_main_reply_kb(message.from_user.id))
    await message.answer("\u3164", reply_markup=main_menu_kb())


@user_router.message(F.text.endswith("Подключить VPN"))
async def vpn_reply(m: Message):
    u = get_user(m.from_user.id)
    if u and u.get('sub_expires') and u.get('plan'):
        try:
            exp_dt = datetime.fromisoformat(u['sub_expires'])
            if exp_dt > datetime.utcnow():
                await _send_active_vpn_screen(m.chat.id, u, bot=m.bot)
                return
        except:
            pass
    await send_tariff_menu(m.chat.id, bot=m.bot, user_id=m.from_user.id)


@user_router.message(F.text.endswith("Профиль"))
async def profile_reply(m: Message):
    u = get_user(m.from_user.id)
    if not u:
        create_user(m.from_user.id, m.from_user.full_name, m.from_user.username)
        u = get_user(m.from_user.id)

    s = get_bot_settings()
    paid = get_plan(u['plan']) if u and u.get('plan') and u['plan'] not in ('plan_free',) else None

    id_e = ce(s.get("ge_id", "0"), "🆔")
    stat_e = ce(s.get("ge_sub_status", "0"), "📊")
    yes_e = ce(s.get("ge_sub_active", "0"), "✅")
    no_e = ce(s.get("ge_sub_no", "0"), "❌")
    plan_e = ce(s.get("ge_plan_label", "0"), "📦")
    link_e = ce(s.get("ge_vpn_link", "0"), "🔗")
    sub_url_e = ce(s.get("ge_sub_url", "0"), "🌐")

    t = f"{id_e} <b>Ваш айди:</b> <code>{u['user_id']}</code>\n\n"

    now = datetime.utcnow()
    if paid and u.get('sub_expires'):
        try:
            exp_dt = datetime.fromisoformat(u['sub_expires'])
            exp = u['sub_expires'][:10]
            is_active = exp_dt > now
        except:
            exp = "—"
            is_active = False

        t += f"{stat_e} <b>Статус подписки:</b> {yes_e if is_active else no_e} {'Активна' if is_active else 'Истекла'} до <b>{exp}</b>\n"
        t += f"{plan_e} Тариф: <b>{paid['label']}</b>"

        vpn_display = u.get('vpn_key') or paid.get('vpn_link', '')
        sub_url = _get_effective_sub_url(u.get('user_id', 0), u.get('sub_url', ''), s)
        if vpn_display and vpn_display != 'Ссылка не задана':
            t += f"\n\n{link_e} <b>Ваша ссылка для подключения:</b>\n<code>{vpn_display}</code>"
            if sub_url:
                t += f"\n{sub_url_e} <b>Ссылка подписки:</b> <a href=\"{sub_url}\">{sub_url}</a>"
            install_url = s.get("info_install_url", "")
            if install_url:
                t += f"\n\n📋 <a href=\"{install_url}\">Инструкция по подключению</a>"
        elif sub_url:
            t += f"\n\n{sub_url_e} <b>Ссылка подписки:</b> <a href=\"{sub_url}\">{sub_url}</a>"
            install_url = s.get("info_install_url", "")
            if install_url:
                t += f"\n\n📋 <a href=\"{install_url}\">Инструкция по подключению</a>"

        await m.answer(t, reply_markup=active_vpn_kb(sub_url=sub_url), disable_web_page_preview=True)
        return
    else:
        t += f"{stat_e} <b>Статус подписки:</b> {no_e} У вас ещё <b>нет подписки</b> на VPN, но вы её можете оформить кнопкой снизу."

    await m.answer(t, reply_markup=profile_kb())


@user_router.message(F.text.endswith("Информация"))
async def info_reply(m: Message):
    s = get_bot_settings()
    text = s.get("info_text", (
        "🔐 <b>Anonch VPN</b> использует протокол с <b>открытым исходным кодом VLESS</b>.\n\n"
        "🗂 Журнал логов удаляется моментально, <b>мы не храним историю посещений</b>.\n\n"
        "🛡 Используется Telegram и Happ, <b>нас невозможно заблокировать</b>."
    ))

    channel = s.get("info_channel_url", "https://t.me/")
    privacy_url = s.get("info_privacy_url", "")
    agree_url = s.get("info_agree_url", "")
    refund_url = s.get("info_refund_url", "")
    support_url = s.get("info_support_url", "")
    install_url = s.get("info_install_url", "")

    kb_rows = []
    if agree_url:
        kb_rows.append([_build_dual_emoji_btn(s, "Пользовательское соглашение", "btn_info_agree_emoji", "📄", "btn_info_agree_emoji_id", url=agree_url)])
    else:
        kb_rows.append([_build_dual_emoji_btn(s, "Пользовательское соглашение", "btn_info_agree_emoji", "📄", "btn_info_agree_emoji_id", cb="agree_stub")])
    if privacy_url:
        kb_rows.append([_build_dual_emoji_btn(s, "Политика конфиденциальности", "btn_info_privacy_emoji", "🔒", "btn_info_privacy_emoji_id", url=privacy_url)])
    else:
        kb_rows.append([_build_dual_emoji_btn(s, "Политика конфиденциальности", "btn_info_privacy_emoji", "🔒", "btn_info_privacy_emoji_id", cb="info_stub")])
    if refund_url:
        kb_rows.append([_build_dual_emoji_btn(s, "Политика возврата", "btn_info_refund_emoji", "💰", "btn_info_refund_emoji_id", url=refund_url)])
    else:
        kb_rows.append([_build_dual_emoji_btn(s, "Политика возврата", "btn_info_refund_emoji", "💰", "btn_info_refund_emoji_id", cb="info_stub")])
    if support_url:
        kb_rows.append([_build_dual_emoji_btn(s, "Техническая поддержка", "btn_info_support_emoji", "🛠", "btn_info_support_emoji_id", url=support_url)])
    else:
        kb_rows.append([_build_dual_emoji_btn(s, "Техническая поддержка", "btn_info_support_emoji", "🛠", "btn_info_support_emoji_id", cb="support_stub")])
    if install_url:
        kb_rows.append([_build_dual_emoji_btn(s, "Инструкция по установке", "btn_info_install_emoji", "📲", "btn_info_install_emoji_id", url=install_url)])
    kb_rows.append([_build_dual_emoji_btn(s, "Канал", "btn_info_channel_emoji", "📢", "btn_info_channel_emoji_id", url=channel)])
    await m.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@user_router.callback_query(F.data == "info_stub")
async def info_stub_cb(c: CallbackQuery):
    await c.answer("Раздел в разработке", show_alert=False)


@user_router.callback_query(F.data == "active_vpn")
async def active_vpn_cb(c: CallbackQuery):
    u = get_user(c.from_user.id)
    try:
        await c.message.delete()
    except:
        pass
    await _send_active_vpn_screen(c.message.chat.id, u, bot=c.bot)
    await c.answer()


@user_router.callback_query(F.data == "install_vpn_stub")
async def install_stub_cb(c: CallbackQuery):
    await c.answer("Настройте ссылку на инструкцию в Администрировании → Ссылки", show_alert=True)


@user_router.callback_query(F.data == "connected_devices")
async def connected_devices_cb(c: CallbackQuery):
    s = get_bot_settings()
    kb_rows = []

    # Try to get live status from Marzban
    mz = await marzban_get_user_status(c.from_user.id)
    if mz:
        status_labels = {
            "active": "✅ Активен",
            "disabled": "🔴 Отключён",
            "limited": "⚠️ Лимит трафика",
            "expired": "⌛ Истёк",
            "on_hold": "⏸ На паузе",
        }
        status_str = status_labels.get(mz["status"], mz["status"])
        used_gb = round(mz["used_traffic"] / (1024 ** 3), 2) if mz["used_traffic"] else 0
        limit_gb = round(mz["data_limit"] / (1024 ** 3), 2) if mz.get("data_limit") else 0

        online_str = "—"
        if mz.get("online_at"):
            try:
                ot = datetime.fromisoformat(mz["online_at"].replace("Z", "+00:00"))
                diff = datetime.now(timezone.utc) - ot
                mins = int(diff.total_seconds() // 60)
                if mins < 2:
                    online_str = "🟢 Онлайн сейчас"
                elif mins < 60:
                    online_str = f"🕐 {mins} мин. назад"
                elif mins < 1440:
                    online_str = f"🕐 {mins // 60} ч. назад"
                else:
                    online_str = f"🕐 {mins // 1440} дн. назад"
            except Exception:
                online_str = str(mz["online_at"])[:16]

        traffic_line = f"{used_gb} ГБ" + (f" / {limit_gb} ГБ" if limit_gb else " (без лимита)")
        e_hdr = ce(s.get("ge_mz_header", "0"), "📡")
        e_dot = ce(s.get("ge_mz_bullet", "0"), "🔹")
        text = (
            f"{e_hdr} <b>Статус подключения</b>\n\n"
            f"{e_dot} Статус: {status_str}\n"
            f"{e_dot} Последняя активность: {online_str}\n"
            f"{e_dot} Использовано трафика: {traffic_line}\n"
        )
        if mz.get("sub_url"):
            text += f"\n🌐 <b>Ссылка подписки:</b> <a href=\"{mz['sub_url']}\">{mz['sub_url']}</a>"
    else:
        # Fallback: local DB devices
        devices = get_user_devices(c.from_user.id)
        if devices:
            text = "📱 <b>Подключённые устройства</b>\n\n"
            for d in devices:
                dt_str = d['connected_at'][:16].replace('T', ' ') if d['connected_at'] else "—"
                kb_rows.append([
                    InlineKeyboardButton(text=f"📱 {d['device_name']}  ({dt_str})", callback_data="ignore"),
                    InlineKeyboardButton(text="🗑", callback_data=f"del_device_{d['id']}")
                ])
        else:
            text = s.get(
                "devices_text",
                "❌ <b>У вас нет подключённых устройств.</b>\n\nПодключитесь к VPN, чтобы увидеть свои устройства в этом списке."
            )

    kb_rows.append([make_btn("btn_back", "Вернуться", "active_vpn", "btn_back_emoji", "🔙")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
                              disable_web_page_preview=True)
    await c.answer()


@user_router.callback_query(F.data.startswith("del_device_"))
async def del_device_cb(c: CallbackQuery):
    try:
        device_id = int(c.data.split("_")[-1])
        delete_user_device(device_id)
        await c.answer("✅ Устройство удалено")
    except Exception:
        await c.answer("❌ Ошибка при удалении", show_alert=True)
        return
    # Обновляем экран со списком устройств
    s = get_bot_settings()
    devices = get_user_devices(c.from_user.id)
    kb_rows = []
    if devices:
        text = "📱 <b>Подключённые устройства</b>\n\n"
        for d in devices:
            dt_str = d['connected_at'][:16].replace('T', ' ') if d['connected_at'] else "—"
            kb_rows.append([
                InlineKeyboardButton(text=f"📱 {d['device_name']}  ({dt_str})", callback_data="ignore"),
                InlineKeyboardButton(text="🗑", callback_data=f"del_device_{d['id']}")
            ])
    else:
        text = s.get(
            "devices_text",
            "❌ <b>У вас нет подключённых устройств.</b>\n\nПодключитесь к VPN, чтобы увидеть свои устройства в этом списке."
        )
    kb_rows.append([make_btn("btn_back", "Вернуться", "active_vpn", "btn_back_emoji", "🔙")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))


@user_router.callback_query(F.data == "renew_sub")
async def renew_sub_cb(c: CallbackQuery):
    await send_tariff_menu(c.message.chat.id, msg_to_edit=c.message, user_id=c.from_user.id)
    await c.answer()


@user_router.callback_query(F.data == "ref_menu")
async def ref_menu_cb(c: CallbackQuery):
    me = await c.bot.get_me()
    stats = get_referral_stats(c.from_user.id)
    link = f"https://t.me/{me.username}?start={c.from_user.id}"
    s = get_bot_settings()
    e_ref     = ce(s.get("ge_ref",        "0"), "🤝")
    e_card    = ce(s.get("ge_ref_card",   "0"), "💳")
    e_people  = ce(s.get("ge_ref_people", "0"), "👥")
    e_target  = ce(s.get("ge_ref_target", "0"), "🎯")
    text = (
        f"{e_ref} <b>Если Вам понравился наш сервис, рекомендуйте нас друзьям!</b>\n\n"
        f"{e_card} <b>За каждую покупку приглашённых (от 1 месяца) — +10 дней к вашей подписке.</b>\n\n"
        f"{e_people} <b>Всего приглашено:</b> {stats['total']} чел.\n"
        f"┝ С пробной: {stats['trial']} чел.\n"
        f"┕ С премиум: {stats['premium']} чел.\n\n"
        f"{e_target} <b>Ссылка:</b> <code>{link}</code>"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[make_btn("btn_back", "Вернуться", "back_to_main", "btn_back_emoji", "🔙")]])
    if c.message.animation:
        await c.message.delete()
        await c.message.answer(text, reply_markup=kb)
    else:
        await c.message.edit_text(text, reply_markup=kb)
    await c.answer()


@user_router.callback_query(F.data == "gift_sub")
async def gift_sub_menu(c: CallbackQuery):
    t = get_bot_settings().get("gift_text", "🎁 Подарите подписку!")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [make_btn("btn_gift_make", "Сделать подарок", "manage_vpn_gift", "btn_gift_make_emoji", "🎁")],
        [make_btn("btn_back", "Назад", "back_to_main", "btn_back_emoji", "🔙")]
    ])
    if c.message.animation:
        await c.message.delete()
        await c.message.answer(t, reply_markup=kb)
    else:
        await c.message.edit_text(t, reply_markup=kb)
    await c.answer()


@user_router.callback_query(F.data == "manage_vpn_gift")
async def manage_vpn_gift_cb(c: CallbackQuery):
    s = get_bot_settings()
    gift_media1 = s.get("gift_media1_id", "")
    gift_media2 = s.get("gift_media2_id", "")
    try:
        await c.message.delete()
    except:
        pass
    if gift_media1:
        try:
            await c.bot.send_animation(c.from_user.id, gift_media1)
        except:
            try:
                await c.bot.send_photo(c.from_user.id, gift_media1)
            except:
                pass
    if gift_media2:
        try:
            await c.bot.send_animation(c.from_user.id, gift_media2)
        except:
            try:
                await c.bot.send_photo(c.from_user.id, gift_media2)
            except:
                pass
    await send_tariff_menu(c.from_user.id, is_gift=True, bot=c.bot)
    await c.answer()


async def _activate_gift_and_send_link(bot, buyer_id: int, plan_code: str, days: int, price: int, method: str = ""):
    """Создаёт подарочный токен, начисляет рефералу дни и отправляет покупателю ссылку."""
    me = await bot.get_me()
    token = create_gift(buyer_id, plan_code, days, price)
    gift_url = f"https://t.me/{me.username}?start=gift_{token}"

    u = get_user(buyer_id)
    if u and u.get('referrer_id') and days >= 30:
        add_subscription_days(u['referrer_id'], 10)
        try:
            await bot.send_message(u['referrer_id'], "🎁 Друг купил подписку! Вам начислено +10 дней.")
        except:
            pass

    s = get_bot_settings()
    method_names = {"stars": "Telegram Stars", "crypto": "Криптовалюта",
                    "yoo": "ЮMoney", "balance": "Баланс", "free": "Бесплатно"}
    method_label = method_names.get(method, method or "—")
    p = get_plan(plan_code)
    plan_label = p['label'] if p else plan_code

    text = (
        f"🎁 <b>Подарок успешно оплачен!</b>\n\n"
        f"📦 Тариф: <b>{plan_label}</b>\n"
        f"💳 Метод оплаты: {method_label}\n\n"
        f"🔗 <b>Ссылка для активации подарка:</b>\n"
        f"<code>{gift_url}</code>\n\n"
        f"Перешлите эту ссылку другу — при переходе подписка активируется автоматически, "
        f"а он станет вашим рефералом!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Скопировать ссылку", switch_inline_query=gift_url)],
        [make_btn("btn_back", "Главное меню", "back_to_main", "btn_back_emoji", "🔙")]
    ])
    await bot.send_message(buyer_id, text, reply_markup=kb)


async def send_tariff_menu(chat_id: int, msg_to_edit=None, is_gift: bool = False, bot=None, dev: int = 1, user_id: int = None):
    """Отправляет или редактирует меню выбора тарифа."""
    t = get_bot_settings().get("tariff_text", "📦 Выберите тариф:")
    paid_plans = [p for p in get_all_plans() if p['price_rub'] > 0]
    if not paid_plans:
        paid_plans = [p for p in get_all_plans() if p['code'] not in ('plan_trial',)]

    # Show trial plan only for personal subscriptions to users who haven't used it
    all_display_plans = paid_plans
    if not is_gift and user_id and not has_used_trial(user_id):
        trial = get_plan('plan_trial')
        if trial:
            all_display_plans = [trial] + paid_plans

    kb = tariff_kb(all_display_plans, dev, is_gift)
    if msg_to_edit:
        if hasattr(msg_to_edit, 'animation') and msg_to_edit.animation:
            await msg_to_edit.delete()
            await msg_to_edit.bot.send_message(chat_id, t, reply_markup=kb)
        else:
            await msg_to_edit.edit_text(t, reply_markup=kb)
    else:
        await bot.send_message(chat_id, t, reply_markup=kb)


def calculate_price(base, dev):
    if base == 0:
        return 0
    markup = int(get_bot_settings().get("device_markup", 5))
    return int(base * (1 + ((dev - 1) * (markup / 100.0))))


def tariff_kb(plans, dev, is_gift):
    s = get_bot_settings()
    down_id = s.get("kb_dev_down_id", "0")
    up_id = s.get("kb_dev_up_id", "0")
    down_e = s.get("kb_dev_down", "◀")
    up_e = s.get("kb_dev_up", "▶")

    btns = []
    p_c, n_c = max(1, dev - 1), min(15, dev + 1)
    cb_p, dev_p = ("gift_pay", "gift_dev") if is_gift else ("pay_select", "dev_set")

    dev_row = []
    if dev > 1:
        if _is_valid_emoji_id(down_id):
            dev_row.append(InlineKeyboardButton(text=down_e, callback_data=f"{dev_p}_{p_c}", icon_custom_emoji_id=str(down_id)))
        else:
            dev_row.append(InlineKeyboardButton(text=down_e, callback_data=f"{dev_p}_{p_c}"))
    else:
        dev_row.append(InlineKeyboardButton(text=down_e, callback_data="ignore"))

    dev_row.append(InlineKeyboardButton(text=str(dev), callback_data="ignore"))

    if dev < 15:
        if _is_valid_emoji_id(up_id):
            dev_row.append(InlineKeyboardButton(text=up_e, callback_data=f"{dev_p}_{n_c}", icon_custom_emoji_id=str(up_id)))
        else:
            dev_row.append(InlineKeyboardButton(text=up_e, callback_data=f"{dev_p}_{n_c}"))
    else:
        dev_row.append(InlineKeyboardButton(text=up_e, callback_data="ignore"))

    btns.append(dev_row)

    plan_eid = s.get("kb_plan_emoji_id", "0")
    plan_e = s.get("kb_plan_emoji", "🗓")
    for p in plans:
        pr = calculate_price(p['price_rub'], dev)
        lbl = f"{p['label']} — {pr} ₽"
        if _is_valid_emoji_id(plan_eid):
            btns.append([InlineKeyboardButton(
                text=f"{plan_e} {lbl}" if plan_e else lbl,
                callback_data=f"{cb_p}_{p['id']}_{dev}",
                icon_custom_emoji_id=str(plan_eid)
            )])
        else:
            btns.append([InlineKeyboardButton(text=f"{plan_e} {lbl}" if plan_e else lbl, callback_data=f"{cb_p}_{p['id']}_{dev}")])

    btns.append([make_btn("btn_promo", "Промокод", "enter_promo", "btn_promo_emoji", "🎟")])
    btns.append([make_btn("btn_back", "Назад", "back_to_main", "btn_back_emoji", "🔙")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


@user_router.callback_query(F.data == "manage_vpn")
async def manage_vpn_cb(c: CallbackQuery):
    u = get_user(c.from_user.id)
    if u and u.get('sub_expires') and u.get('plan'):
        try:
            exp_dt = datetime.fromisoformat(u['sub_expires'])
            if exp_dt > datetime.utcnow():
                try:
                    await c.message.delete()
                except:
                    pass
                await _send_active_vpn_screen(c.message.chat.id, u, bot=c.bot)
                await c.answer()
                return
        except:
            pass
    await send_tariff_menu(c.message.chat.id, msg_to_edit=c.message, user_id=c.from_user.id)
    await c.answer()


@user_router.callback_query(F.data.startswith("dev_set_"))
@user_router.callback_query(F.data.startswith("gift_dev_"))
async def dev_set_h(c: CallbackQuery):
    is_gift = "gift" in c.data
    dev = int(c.data.split("_")[-1])
    paid_plans = [p for p in get_all_plans() if p['price_rub'] > 0]
    if not paid_plans:
        paid_plans = [p for p in get_all_plans() if p['code'] not in ('plan_trial',)]

    all_display_plans = paid_plans
    if not is_gift and not has_used_trial(c.from_user.id):
        trial = get_plan('plan_trial')
        if trial:
            all_display_plans = [trial] + paid_plans

    t = get_bot_settings().get("tariff_text", "📦 Выберите тариф:")
    kb = tariff_kb(all_display_plans, dev, is_gift)
    await c.message.edit_text(t, reply_markup=kb)
    await c.answer()


@user_router.callback_query(F.data.startswith("pay_select_"))
@user_router.callback_query(F.data.startswith("gift_pay_"))
async def pay_sel_h(c: CallbackQuery):
    is_gift = "gift" in c.data
    parts = c.data.split("_")
    # pay_select_{pid}_{dev} → parts[2]=pid, parts[3]=dev
    # gift_pay_{pid}_{dev}   → parts[2]=pid, parts[3]=dev
    pid = int(parts[2])
    dev = int(parts[-1])
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == pid), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    total = calculate_price(p['price_rub'], dev)
    u = get_user(c.from_user.id)
    prefix = "gpay" if is_gift else "pay"
    s = get_bot_settings()
    inv_e = ce(s.get("ge_invoice", "0"), "💳")
    t = s.get("invoice_text", "{e_invoice} Счёт: {price} ₽").replace("{e_invoice}", inv_e).replace("{price}", str(total))
    kb = []

    if total == 0:
        cb = f"gift_free_{pid}" if is_gift else f"personal_free_{pid}"
        kb.append([make_btn("btn_free", "Получить бесплатно", cb, "btn_free_emoji", "✅")])
    else:
        stars_e = s.get("kb_pay_stars_emoji", "⭐️")
        stars_id = s.get("kb_pay_stars_id", "0")
        crypto_e = s.get("kb_pay_crypto_emoji", "💎")
        crypto_id = s.get("kb_pay_crypto_id", "0")
        yoo_e = s.get("kb_pay_yoo_emoji", "💛")
        yoo_id = s.get("kb_pay_yoo_id", "0")

        def _pay_btn(text, emoji_char, custom_id, cb_data):
            if _is_valid_emoji_id(custom_id):
                return InlineKeyboardButton(text=text, callback_data=cb_data, icon_custom_emoji_id=str(custom_id))
            return InlineKeyboardButton(text=f"{emoji_char} {text}" if emoji_char else text, callback_data=cb_data)

        kb.append([_pay_btn("Telegram Stars", stars_e, stars_id, f"{prefix}_stars_{pid}_{dev}")])
        if s.get("pay_crypto_tok"):
            kb.append([_pay_btn("CryptoBot (USDT/TON)", crypto_e, crypto_id, f"{prefix}_crypto_{pid}_{dev}")])
        if s.get("pay_yoo_num"):
            kb.append([_pay_btn("ЮMoney", yoo_e, yoo_id, f"{prefix}_yoo_{pid}_{dev}")])
        if u and u['balance'] >= total:
            bal_e = ce(s.get("ge_pay_balance", "0"), "💰")
            kb.append(
                [InlineKeyboardButton(text=f"{bal_e} Баланс ({u['balance']} ₽)", callback_data=f"{prefix}_bal_{pid}_{dev}")])

    kb.append([make_btn("btn_back", "Вернуться", "manage_vpn", "btn_back_emoji", "🔙")])
    await c.message.edit_text(t, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()


@user_router.callback_query(F.data.regexp(r"^(pay|gpay)_stars_\d+_\d+$"))
async def stars_pay_h(c: CallbackQuery):
    is_gift = c.data.startswith("gpay")
    parts = c.data.split("_")
    pid, dev = int(parts[2]), int(parts[3])
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == pid), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    total_rub = calculate_price(p['price_rub'], dev)
    stars_amount = max(1, int(total_rub * p['price_stars'] / max(p['price_rub'], 1))) if p['price_rub'] else 1
    prefix = "gift" if is_gift else "sub"
    await c.message.bot.send_invoice(
        c.from_user.id, title=p['label'],
        description=f"VPN подписка — {p['label']}",
        payload=f"{prefix}_{p['code']}_{p['days']}_{total_rub}",
        provider_token="", currency="XTR",
        prices=[LabeledPrice(label="XTR", amount=stars_amount)]
    )
    await c.answer()


@user_router.callback_query(F.data.regexp(r"^(pay|gpay)_crypto_\d+_\d+$"))
async def crypto_pay_h(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    tok = s.get("pay_crypto_tok", "")
    if not tok:
        return await c.answer("❌ CryptoBot не настроен", show_alert=True)
    is_gift = c.data.startswith("gpay")
    parts = c.data.split("_")
    pid, dev = int(parts[2]), int(parts[3])
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == pid), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    total_rub = calculate_price(p['price_rub'], dev)
    usdt = round(total_rub / 90, 2)
    pay_type = "gift" if is_gift else "sub"
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                "https://pay.crypt.bot/api/createInvoice",
                headers={"Crypto-Pay-API-Token": tok},
                json={"asset": "USDT", "amount": str(usdt),
                      "description": f"VPN: {p['label']}",
                      "payload": f"{pay_type}_{p['code']}_{p['days']}_{total_rub}_{c.from_user.id}",
                      "expires_in": 3600}
            )
            data = await resp.json()
        if data.get("ok"):
            invoice = data["result"]
            pay_url = invoice["pay_url"]
            invoice_id = invoice["invoice_id"]
            await state.update_data(crypto_invoice_id=invoice_id, crypto_is_gift=is_gift)
            await state.set_state(UserStates.wait_for_crypto_check)
            paid_cb = f"check_crypto_{invoice_id}_{p['code']}_{p['days']}_{total_rub}_{pay_type}"
            crypto_pay_e = s.get("pay_btn_crypto_pay_emoji", "💎")
            crypto_pay_id = s.get("pay_btn_crypto_pay_id", "0")
            paid_e = s.get("pay_btn_paid_emoji", "✅")
            paid_id = s.get("pay_btn_paid_id", "0")
            if _is_valid_emoji_id(crypto_pay_id):
                pay_btn = InlineKeyboardButton(text="Оплатить через CryptoBot", url=pay_url, icon_custom_emoji_id=str(crypto_pay_id))
            else:
                pay_btn = InlineKeyboardButton(text=f"{crypto_pay_e} Оплатить через CryptoBot" if crypto_pay_e else "Оплатить через CryptoBot", url=pay_url)
            if _is_valid_emoji_id(paid_id):
                paid_btn = InlineKeyboardButton(text="Я оплатил", callback_data=paid_cb, icon_custom_emoji_id=str(paid_id))
            else:
                paid_btn = InlineKeyboardButton(text=f"{paid_e} Я оплатил" if paid_e else "Я оплатил", callback_data=paid_cb)
            kb = InlineKeyboardMarkup(inline_keyboard=[[pay_btn], [paid_btn]])
            await c.message.edit_text(
                f"💎 <b>Оплата через CryptoBot</b>\n\nСумма: <b>{usdt} USDT</b>\nТариф: <b>{p['label']}</b>\n\nНажмите кнопку ниже для оплаты, затем нажмите «Я оплатил»",
                reply_markup=kb)
        else:
            await c.answer("❌ Ошибка создания счёта", show_alert=True)
    except Exception as e:
        await c.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
    await c.answer()


@user_router.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_h(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    tok = s.get("pay_crypto_tok", "")
    raw = c.data[len("check_crypto_"):]
    try:
        parts = raw.rsplit("_", 4)
        invoice_id = parts[0]
        plan_code = parts[1]
        days = int(parts[2])
        price = int(parts[3])
        pay_type = parts[4] if len(parts) > 4 else "sub"
    except Exception as pe:
        return await c.answer(f"❌ Ошибка разбора: {pe}", show_alert=True)
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                "https://pay.crypt.bot/api/getInvoices",
                headers={"Crypto-Pay-API-Token": tok},
                params={"invoice_ids": invoice_id})
            data = await resp.json()
        result = data.get("result") if data.get("ok") else None
        items = (result.get("items") if isinstance(result, dict) else None) or []
        if items and items[0]["status"] == "paid":
            await state.clear()
            if pay_type == "gift":
                await _activate_gift_and_send_link(c.bot, c.from_user.id, plan_code, days, price, "crypto")
            else:
                await _activate_and_notify(c.bot, c.from_user.id, plan_code, days, price, "crypto")
            try:
                await c.message.delete()
            except:
                pass
        else:
            await c.answer("⏳ Оплата ещё не подтверждена. Попробуйте через минуту.", show_alert=True)
    except Exception as e:
        await c.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
    await c.answer()


@user_router.callback_query(F.data.regexp(r"^(pay|gpay)_yoo_\d+_\d+$"))
async def yoo_pay_h(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    wallet = s.get("pay_yoo_num", "")
    if not wallet:
        return await c.answer("❌ ЮMoney не настроен", show_alert=True)
    is_gift = c.data.startswith("gpay")
    parts = c.data.split("_")
    pid, dev = int(parts[2]), int(parts[3])
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == pid), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    total = calculate_price(p['price_rub'], dev)
    pay_type = "gift" if is_gift else "sub"
    label = f"vpn_{c.from_user.id}_{p['code']}_{int(time.time())}"
    await state.update_data(yoo_label=label, yoo_plan_code=p['code'], yoo_days=p['days'], yoo_price=total,
                            yoo_is_gift=is_gift)
    await state.set_state(UserStates.wait_for_yoo_check)
    pay_url = (f"https://yoomoney.ru/quickpay/confirm.xml?receiver={wallet}"
               f"&quickpay-form=button&targets=VPN+{p['label']}&paymentType=AC&sum={total}&label={label}")
    yoo_pay_e = s.get("pay_btn_yoo_pay_emoji", "💛")
    yoo_pay_id = s.get("pay_btn_yoo_pay_id", "0")
    paid_e = s.get("pay_btn_paid_emoji", "✅")
    paid_id = s.get("pay_btn_paid_id", "0")
    paid_cb = f"check_yoo_{label}_{p['code']}_{p['days']}_{total}_{pay_type}"
    if _is_valid_emoji_id(yoo_pay_id):
        yoo_pay_btn = InlineKeyboardButton(text="Оплатить через ЮMoney", url=pay_url, icon_custom_emoji_id=str(yoo_pay_id))
    else:
        yoo_pay_btn = InlineKeyboardButton(text=f"{yoo_pay_e} Оплатить через ЮMoney" if yoo_pay_e else "Оплатить через ЮMoney", url=pay_url)
    if _is_valid_emoji_id(paid_id):
        paid_btn = InlineKeyboardButton(text="Я оплатил", callback_data=paid_cb, icon_custom_emoji_id=str(paid_id))
    else:
        paid_btn = InlineKeyboardButton(text=f"{paid_e} Я оплатил" if paid_e else "Я оплатил", callback_data=paid_cb)
    kb = InlineKeyboardMarkup(inline_keyboard=[[yoo_pay_btn], [paid_btn]])
    await c.message.edit_text(
        f"💛 <b>Оплата через ЮMoney</b>\n\nСумма: <b>{total} ₽</b>\nТариф: <b>{p['label']}</b>\n\nНажмите кнопку ниже, затем «Я оплатил»",
        reply_markup=kb)
    await c.answer()


@user_router.callback_query(F.data.startswith("check_yoo_"))
async def check_yoo_h(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    tok = s.get("pay_yoo_tok", "")
    parts = c.data.split("_")
    label = parts[2];
    plan_code = parts[3];
    days = int(parts[4]);
    price = int(parts[5])
    pay_type = parts[6] if len(parts) > 6 else "sub"
    if not tok:
        return await c.answer("⚠️ Автопроверка недоступна. Свяжитесь с поддержкой.", show_alert=True)
    try:
        async with aiohttp.ClientSession() as session:
            resp = await session.get("https://yoomoney.ru/api/operation-history",
                                     headers={"Authorization": f"Bearer {tok}"},
                                     params={"label": label, "type": "deposition"})
            data = await resp.json()
        paid_op = next((o for o in data.get("operations", []) if o.get("status") == "success"), None)
        if paid_op:
            await state.clear()
            if pay_type == "gift":
                await _activate_gift_and_send_link(c.bot, c.from_user.id, plan_code, days, price, "yoo")
            else:
                await _activate_and_notify(c.bot, c.from_user.id, plan_code, days, price, "yoo")
            try:
                await c.message.delete()
            except:
                pass
        else:
            await c.answer("⏳ Оплата не найдена. Подождите 1-2 минуты.", show_alert=True)
    except Exception as e:
        await c.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)
    await c.answer()


@user_router.callback_query(F.data.regexp(r"^(pay|gpay)_bal_\d+_\d+$"))
async def balance_pay_h(c: CallbackQuery):
    is_gift = c.data.startswith("gpay")
    parts = c.data.split("_")
    pid, dev = int(parts[2]), int(parts[3])
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == pid), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    total = calculate_price(p['price_rub'], dev)
    u = get_user(c.from_user.id)
    if not u or u['balance'] < total:
        return await c.answer("❌ Недостаточно средств!", show_alert=True)
    update_user_balance(u['user_id'], -total)
    if is_gift:
        await _activate_gift_and_send_link(c.bot, c.from_user.id, p['code'], p['days'], total, "balance")
    else:
        await _activate_and_notify(c.bot, c.from_user.id, p['code'], p['days'], total, "balance")
    try:
        await c.message.delete()
    except:
        pass
    await c.answer()


@user_router.pre_checkout_query()
async def pre_checkout_h(q: PreCheckoutQuery):
    await q.bot.answer_pre_checkout_query(q.id, ok=True)


@user_router.message(F.successful_payment)
async def success_pay_h(m: Message):
    parts = m.successful_payment.invoice_payload.split("_")
    prefix = parts[0]
    code, days, pr = parts[1], int(parts[2]), int(parts[3])
    if prefix == "gift":
        await _activate_gift_and_send_link(m.bot, m.from_user.id, code, days, pr, "stars")
    else:
        await _activate_and_notify(m.bot, m.from_user.id, code, days, pr, "stars")


@user_router.callback_query(F.data.startswith("personal_free_"))
async def p_free_cb(c: CallbackQuery):
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == int(c.data.split("_")[-1])), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    await _activate_and_notify(c.bot, c.from_user.id, p['code'], p['days'], 0, "free")
    try:
        await c.message.delete()
    except:
        pass
    await c.answer()


@user_router.callback_query(F.data.startswith("gift_free_"))
async def gift_free_cb(c: CallbackQuery):
    all_plans = get_all_plans()
    p = next((x for x in all_plans if x['id'] == int(c.data.split("_")[-1])), None)
    if not p:
        return await c.answer("❌ Тариф не найден", show_alert=True)
    await _activate_gift_and_send_link(c.bot, c.from_user.id, p['code'], p['days'], 0, "free")
    try:
        await c.message.delete()
    except:
        pass
    await c.answer()


@user_router.callback_query(F.data == "enter_promo")
async def enter_promo_cb(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎟 Введите промокод:")
    await state.set_state(UserStates.wait_for_promo)
    await c.answer()


@user_router.message(UserStates.wait_for_promo)
async def handle_promo(m: Message, state: FSMContext):
    promo = get_promo(m.text.strip())
    if not promo:
        await m.answer("❌ Промокод не найден или уже использован.")
        await state.clear()
        return
    use_promo(promo['code'])
    update_user_balance(m.from_user.id, promo['value'])
    await m.answer(f"✅ Промокод применён! На баланс зачислено <b>{promo['value']} ₽</b>.")
    await state.clear()


@user_router.callback_query(F.data == "agree_stub")
async def agree_stub(c: CallbackQuery):
    await c.answer("Раздел откроется в ближайшее время", show_alert=False)


@user_router.callback_query(F.data == "support_stub")
async def support_stub(c: CallbackQuery):
    await c.answer("Обратитесь к администратору бота", show_alert=False)


@user_router.callback_query(F.data == "ignore")
async def ignore_cb(c: CallbackQuery):
    await c.answer()


@user_router.callback_query(F.data == "back_to_main")
async def back_h(c: CallbackQuery):
    try:
        await c.message.delete()
    except:
        pass
    s = get_bot_settings()
    gif = s.get("start_media_id")
    text = s.get("start_text", "<b>🔐 Добро пожаловать в AnonchVPN!</b>\n\nЯ — ваш помощник в мире интернет-свободы!")
    kb = get_main_reply_kb(c.from_user.id)
    if gif:
        gif_sent = False
        try:
            await c.message.answer_animation(animation=gif, caption=text, reply_markup=main_menu_kb())
            gif_sent = True
        except:
            pass
        if gif_sent:
            await c.bot.send_message(c.from_user.id, ".", reply_markup=get_main_reply_kb(c.from_user.id))
            await c.answer()
            return
    await c.bot.send_message(c.from_user.id, text, reply_markup=kb)
    await c.bot.send_message(c.from_user.id, ".", reply_markup=main_menu_kb())
    await c.answer()


@user_router.callback_query(F.data == "forced_sub_check")
async def forced_sub_check_cb(c: CallbackQuery):
    if await _check_forced_subscription(c.from_user.id, c.bot):
        try:
            await c.message.delete()
        except:
            pass
        s = get_bot_settings()
        gif = s.get("start_media_id")
        sticker = s.get("start_sticker_id")
        text = s.get("start_text", "<b>🔐 Добро пожаловать в AnonchVPN!</b>\n\nЯ — ваш помощник в мире интернет-свободы!")

        if sticker:
            try:
                await c.bot.send_sticker(c.from_user.id, sticker)
            except:
                pass

        if gif:
            gif_sent = False
            try:
                await c.bot.send_animation(
                    chat_id=c.from_user.id,
                    animation=gif,
                    caption=text,
                    reply_markup=main_menu_kb()
                )
                gif_sent = True
            except:
                pass
            if gif_sent:
                await c.bot.send_message(c.from_user.id, ".", reply_markup=get_main_reply_kb(c.from_user.id))
                await c.answer("✅ Добро пожаловать!")
                return

        await c.bot.send_message(c.from_user.id, text, reply_markup=get_main_reply_kb(c.from_user.id))
        await c.bot.send_message(c.from_user.id, ".", reply_markup=main_menu_kb())
        await c.answer("✅ Добро пожаловать!")
    else:
        await c.answer("❌ Вы ещё не подписались на канал!", show_alert=True)