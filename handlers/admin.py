from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from config import ADMIN_IDS
from database.models import (
    set_bot_setting, get_bot_settings, get_stats, get_all_plans,
    update_plan_price, update_plan_link, update_plan_instruction, get_user, toggle_ban_user,
    update_user_balance, get_all_users, create_promo, get_all_promos,
    add_user_device, get_user_devices, delete_user_device
)

admin_router = Router()

CANCEL_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel_fsm")]
])


@admin_router.callback_query(F.data == "admin_cancel_fsm", F.from_user.id.in_(ADMIN_IDS))
async def admin_cancel_fsm(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("✅ Действие отменено.")
    await c.answer()


class AdminStates(StatesGroup):
    wait_for_text = State()
    wait_for_gif = State()
    wait_for_sticker = State()
    wait_for_plan_price = State()
    wait_for_plan_link = State()
    wait_for_plan_instruction = State()
    wait_for_balance_amount = State()
    wait_for_payment_setting = State()
    wait_for_promo_name = State()
    wait_for_promo_value = State()
    wait_for_promo_uses = State()
    wait_for_btn_text = State()
    wait_for_btn_emoji = State()
    wait_for_global_emoji = State()
    wait_for_info_url = State()
    wait_for_free_link = State()
    wait_for_paid_link = State()
    wait_for_device_name = State()  # Имя нового устройства для пользователя
    wait_for_dev_emoji = State()  # Эмодзи кнопок устройств
    wait_for_pay_emoji = State()  # Эмодзи кнопок оплаты
    wait_for_kb_emoji = State()   # Эмодзи кнопок главного меню  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
    wait_for_info_vpn_emoji = State()  # Эмодзи кнопок Инфо и VPN
    wait_for_notif_text = State()     # Текст уведомления
    wait_for_notif_btn_text = State() # Текст кнопки уведомления
    wait_for_notif_hours = State()    # Часы для уведомления
    wait_for_notif_btn_emoji = State() # ID кастомного эмодзи кнопки уведомления

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_refresh_stats")],
        [InlineKeyboardButton(text="👤 Пользователи", callback_data="admin_users_page_0"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promos_menu")],
        [InlineKeyboardButton(text="💰 Платёжные системы", callback_data="admin_payments")],
        [InlineKeyboardButton(text="📝 Тарифы и ссылки", callback_data="admin_plans")],
        [InlineKeyboardButton(text="💬 Тексты меню", callback_data="admin_edit_texts_menu")],
        [InlineKeyboardButton(text="🔗 Ссылки раздела «Инфо»", callback_data="admin_info_links")],
        [InlineKeyboardButton(text="✏️ Кнопки и Эмодзи", callback_data="admin_select_btn_to_edit")],
        [InlineKeyboardButton(text="😀 Кастомные эмодзи (глобально)", callback_data="admin_global_emoji")],
        [InlineKeyboardButton(text="⌨️ Эмодзи главного меню", callback_data="admin_kb_emoji")],
        [InlineKeyboardButton(text="🔢 Эмодзи кнопок устройств", callback_data="admin_dev_emoji")],
        [InlineKeyboardButton(text="💳 Эмодзи кнопок оплаты", callback_data="admin_pay_emoji")],
        [InlineKeyboardButton(text="🔔 Эмодзи кнопок Инфо и VPN", callback_data="admin_info_vpn_emoji")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="admin_notifications")],
        [InlineKeyboardButton(text="🖼 Изменить GIF", callback_data="admin_edit_gif"),
         InlineKeyboardButton(text="🎭 Стикер на старте", callback_data="admin_edit_sticker")],
    ])


@admin_router.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
@admin_router.message(F.text.endswith("Администрирование"), F.from_user.id.in_(ADMIN_IDS))
async def admin_panel(message: Message):
    st = get_stats()
    text = (
        f"🛠 <b>Админ-панель AnonchVPN</b>\n\n"
        f"👥 Пользователей всего: <b>{st['total_users']}</b>\n"
        f"🆕 Новых сегодня: <b>{st['today_users']}</b>\n"
        f"🟢 Активных подписок: <b>{st['active_subs']}</b>\n"
        f"💰 Выручка всего: <b>{st['total_revenue']} ₽</b>"
    )
    await message.answer(text, reply_markup=admin_kb())


@admin_router.callback_query(F.data == "admin_home", F.from_user.id.in_(ADMIN_IDS))
async def admin_home_cb(c: CallbackQuery):
    st = get_stats()
    text = (
        f"🛠 <b>Админ-панель AnonchVPN</b>\n\n"
        f"👥 Пользователей: <b>{st['total_users']}</b>\n"
        f"🆕 Сегодня: <b>{st['today_users']}</b>\n"
        f"🟢 Активных: <b>{st['active_subs']}</b>\n"
        f"💰 Выручка: <b>{st['total_revenue']} ₽</b>"
    )
    await c.message.edit_text(text, reply_markup=admin_kb())


@admin_router.callback_query(F.data == "admin_refresh_stats", F.from_user.id.in_(ADMIN_IDS))
async def refresh_stats_adm(c: CallbackQuery):
    await admin_home_cb(c)
    await c.answer("✅ Обновлено")


# ─── ПОЛЬЗОВАТЕЛИ ─────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data.startswith("admin_users_page_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_users_list(c: CallbackQuery):
    page = int(c.data.split("_")[3])
    users = get_all_users()
    start, end = page * 10, (page + 1) * 10
    kb_btns = []
    for u in users[start:end]:
        status = "🔴" if u['is_banned'] else "🟢"
        name = u.get("username") or u.get("full_name") or str(u['user_id'])
        kb_btns.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"adm_uinfo_{u['user_id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_users_page_{page - 1}"))
    if end < len(users):
        nav.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"admin_users_page_{page + 1}"))
    if nav:
        kb_btns.append(nav)
    kb_btns.append([InlineKeyboardButton(text="🔙 В меню", callback_data="admin_home")])
    await c.message.edit_text(f"👤 Пользователи ({len(users)} всего):",
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_btns))


@admin_router.callback_query(F.data.startswith("adm_uinfo_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_user_card(c: CallbackQuery):
    uid = c.data.split("_")[2]
    u = get_user(uid)
    if not u:
        return await c.answer("Не найден")
    status = "🔴 Забанен" if u['is_banned'] else "🟢 Активен"
    text = (
        f"👤 <b>{u['full_name']}</b>\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"👤 Username: @{u.get('username') or '—'}\n"
        f"💰 Баланс: <b>{u['balance']} ₽</b>\n"
        f"🛡 Статус: {status}\n"
        f"📦 Тариф: {u.get('plan') or 'Нет'}\n"
        f"📅 Подписка до: {u['sub_expires'][:10] if u['sub_expires'] else 'Нет'}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data=f"adm_editbal_{uid}")],
        [InlineKeyboardButton(text="🚫 Бан / Разбан", callback_data=f"adm_toggleban_{uid}")],
        [InlineKeyboardButton(text="📱 Устройства VPN", callback_data=f"adm_devices_{uid}")],
        [InlineKeyboardButton(text="🔙 К списку", callback_data="admin_users_page_0")]
    ])
    await c.message.edit_text(text, reply_markup=kb)


@admin_router.callback_query(F.data.startswith("adm_editbal_"), F.from_user.id.in_(ADMIN_IDS))
async def req_bal(c: CallbackQuery, state: FSMContext):
    await state.update_data(target_uid=c.data.split("_")[2])
    await c.message.answer("Введите сумму (например 500 или -500):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_balance_amount)


@admin_router.message(AdminStates.wait_for_balance_amount)
async def save_bal(m: Message, state: FSMContext):
    d = await state.get_data()
    try:
        val = int(m.text)
        update_user_balance(d['target_uid'], val)
        await m.answer(f"✅ Баланс изменён на {val:+d} ₽")
        await state.clear()
    except:
        await m.answer("❌ Введите число!")


@admin_router.callback_query(F.data.startswith("adm_toggleban_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_ban(c: CallbackQuery):
    uid = c.data.split("_")[2]
    toggle_ban_user(uid)
    await admin_user_card(c)


# ─── УПРАВЛЕНИЕ УСТРОЙСТВАМИ (АДМИН) ──────────────────────────────────────────

def _admin_devices_kb(uid, devices):
    kb = []
    for d in devices:
        dt_str = d['connected_at'][:16].replace('T', ' ')
        kb.append([
            InlineKeyboardButton(text=f"📱 {d['device_name']}  ({dt_str})", callback_data="ignore"),
            InlineKeyboardButton(text="🗑", callback_data=f"adm_deldev_{uid}_{d['id']}")
        ])
    kb.append([InlineKeyboardButton(text="➕ Добавить устройство", callback_data=f"adm_adddev_{uid}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"adm_uinfo_{uid}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@admin_router.callback_query(F.data.startswith("adm_devices_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_devices_list(c: CallbackQuery):
    uid = c.data.split("_")[2]
    devices = get_user_devices(uid)
    u = get_user(uid)
    name = u['full_name'] if u else uid
    if devices:
        text = f"📱 <b>Устройства пользователя {name}</b>\n\nВсего: {len(devices)}"
    else:
        text = f"📱 <b>Устройства пользователя {name}</b>\n\nУстройств нет."
    await c.message.edit_text(text, reply_markup=_admin_devices_kb(uid, devices))
    await c.answer()


@admin_router.callback_query(F.data.startswith("adm_adddev_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_add_device_ask(c: CallbackQuery, state: FSMContext):
    uid = c.data.split("_")[2]
    await state.update_data(target_uid=uid, devices_msg_id=c.message.message_id)
    await c.message.answer("Введите название устройства (например: iPhone 15, Windows PC, MacBook):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_device_name)
    await c.answer()


@admin_router.message(AdminStates.wait_for_device_name, F.from_user.id.in_(ADMIN_IDS))
async def adm_add_device_save(m: Message, state: FSMContext):
    d = await state.get_data()
    uid = d['target_uid']
    name = m.text.strip()
    if not name:
        await m.answer("❌ Введите непустое название!")
        return
    add_user_device(uid, name)
    await state.clear()
    devices = get_user_devices(uid)
    u = get_user(uid)
    uname = u['full_name'] if u else uid
    text = f"📱 <b>Устройства пользователя {uname}</b>\n\nВсего: {len(devices)}"
    await m.answer(f"✅ Устройство «{name}» добавлено!")
    await m.answer(text, reply_markup=_admin_devices_kb(uid, devices))


@admin_router.callback_query(F.data.startswith("adm_deldev_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_delete_device(c: CallbackQuery):
    parts = c.data.split("_")
    uid = parts[2]
    device_id = int(parts[3])
    delete_user_device(device_id)
    await c.answer("✅ Устройство удалено")
    devices = get_user_devices(uid)
    u = get_user(uid)
    name = u['full_name'] if u else uid
    if devices:
        text = f"📱 <b>Устройства пользователя {name}</b>\n\nВсего: {len(devices)}"
    else:
        text = f"📱 <b>Устройства пользователя {name}</b>\n\nУстройств нет."
    await c.message.edit_text(text, reply_markup=_admin_devices_kb(uid, devices))


# ─── ТАРИФЫ И ССЫЛКИ ──────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_plans", F.from_user.id.in_(ADMIN_IDS))
async def admin_plans(c: CallbackQuery):
    plans = get_all_plans()
    kb = []
    for p in plans:
        kb.append([InlineKeyboardButton(
            text=f"{'🆓' if p['price_rub']==0 else '💳'} {p['label']} — {p['price_rub']} ₽",
            callback_data=f"adm_p_{p['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text("📝 <b>Тарифы:</b>\nВыберите тариф для редактирования:",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@admin_router.callback_query(F.data.startswith("adm_p_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_plan_det(c: CallbackQuery, state: FSMContext):
    pid = int(c.data.split("_")[2])
    p = next(x for x in get_all_plans() if x['id'] == pid)
    await state.update_data(editing_plan=pid)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить цену (₽)", callback_data="set_p_pr")],
        [InlineKeyboardButton(text="🔗 Изменить VPN-ссылку", callback_data="set_p_li")],
        [InlineKeyboardButton(text="📋 Изменить инструкцию", callback_data="set_p_ins")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_plans")]
    ])
    vpn_link = p['vpn_link'] or "Не задана"
    instruction = p.get('plan_instruction') or "—"
    instr_preview = (instruction[:60] + "...") if len(instruction) > 60 else instruction
    await c.message.edit_text(
        f"📝 <b>{p['label']}</b>\n"
        f"💰 Цена: <b>{p['price_rub']} ₽</b>\n"
        f"⭐️ Stars: <b>{p['price_stars']}</b>\n"
        f"🔗 Ссылка:\n<code>{vpn_link}</code>\n\n"
        f"📋 Инструкция:\n{instr_preview}",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "set_p_pr")
async def r_p_pr(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новую цену в рублях:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_plan_price)


@admin_router.callback_query(F.data == "set_p_li")
async def r_p_li(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новую VPN-ссылку для этого тарифа:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_plan_link)


@admin_router.message(AdminStates.wait_for_plan_price)
async def s_p_pr(m: Message, state: FSMContext):
    d = await state.get_data()
    try:
        update_plan_price(d['editing_plan'], int(m.text))
        await m.answer("✅ Цена обновлена!")
        await state.clear()
    except:
        await m.answer("❌ Введите число!")


@admin_router.message(AdminStates.wait_for_plan_link)
async def s_p_li(m: Message, state: FSMContext):
    d = await state.get_data()
    update_plan_link(d['editing_plan'], m.text.strip())
    await m.answer("✅ Ссылка обновлена!")
    await state.clear()


@admin_router.callback_query(F.data == "set_p_ins")
async def r_p_ins(c: CallbackQuery, state: FSMContext):
    await c.message.answer(
        "📋 <b>Введите инструкцию для тарифа</b>\n\n"
        "Этот текст будет показан пользователю после успешной оплаты вместе со ссылкой.\n"
        "Поддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>.\n\n"
        "Отправьте «0» чтобы очистить инструкцию.",
        reply_markup=CANCEL_KB
    )
    await state.set_state(AdminStates.wait_for_plan_instruction)


@admin_router.message(AdminStates.wait_for_plan_instruction)
async def s_p_ins(m: Message, state: FSMContext):
    d = await state.get_data()
    text = "" if m.text.strip() == "0" else m.html_text.strip()
    update_plan_instruction(d['editing_plan'], text)
    await m.answer("✅ Инструкция обновлена!")
    await state.clear()


# ─── ССЫЛКИ В РАЗДЕЛЕ ИНФО ────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_info_links", F.from_user.id.in_(ADMIN_IDS))
async def admin_info_links(c: CallbackQuery):
    s = get_bot_settings()

    def sv(k):
        v = s.get(k, "")
        if not v:
            return "—"
        return (v[:28] + "...") if len(v) > 28 else v

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📄 Соглашение: {sv('info_agree_url')}", callback_data="set_info_info_agree_url")],
        [InlineKeyboardButton(text=f"🔒 Конфиденциальность: {sv('info_privacy_url')}", callback_data="set_info_info_privacy_url")],
        [InlineKeyboardButton(text=f"💰 Возврат: {sv('info_refund_url')}", callback_data="set_info_info_refund_url")],
        [InlineKeyboardButton(text=f"🛠 Поддержка: {sv('info_support_url')}", callback_data="set_info_info_support_url")],
        [InlineKeyboardButton(text=f"📢 Канал: {sv('info_channel_url')}", callback_data="set_info_info_channel_url")],
        [InlineKeyboardButton(text=f"📲 Инструкция: {sv('info_install_url')}", callback_data="set_info_info_install_url")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")]
    ])
    await c.message.edit_text("🔗 <b>Ссылки в разделе «Информация»:</b>", reply_markup=kb)


@admin_router.callback_query(F.data.startswith("set_info_"), F.from_user.id.in_(ADMIN_IDS))
async def set_info_url(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("set_info_", "")
    await state.update_data(info_url_key=key)
    await c.message.answer("Введите URL (или «0» чтобы очистить):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_info_url)


@admin_router.message(AdminStates.wait_for_info_url)
async def save_info_url(m: Message, state: FSMContext):
    d = await state.get_data()
    val = "" if m.text.strip() == "0" else m.text.strip()
    set_bot_setting(d['info_url_key'], val)
    await m.answer("✅ Ссылка сохранена!")
    await state.clear()


# ─── РЕДАКТОР КНОПОК ──────────────────────────────────────────────────────────

BTN_MAPPING = {
    "vpn":       ("btn_vpn",       "btn_vpn_emoji"),
    "ref":       ("btn_ref",       "btn_ref_emoji"),
    "gift":      ("btn_gift",      "btn_gift_emoji"),
    "gift_make": ("btn_gift_make", "btn_gift_make_emoji"),
    "prof_buy":  ("btn_prof_buy",  "btn_prof_buy_emoji"),
    "agree":     ("btn_agree",     "btn_agree_emoji"),
    "supp":      ("btn_supp",      "btn_supp_emoji"),
    "free":      ("btn_free",      "btn_free_emoji"),
    "promo":     ("btn_promo",     "btn_promo_emoji"),
    "back":      ("btn_back",      "btn_back_emoji"),
}

BTN_LABELS = {
    "vpn":       "🌐 Управление VPN",
    "ref":       "🤝 Пригласить",
    "gift":      "🎁 Подарить (меню)",
    "gift_make": "🎁 Сделать подарок",
    "prof_buy":  "💳 Оформить (Профиль)",
    "agree":     "📄 Соглашение",
    "supp":      "🛠 Поддержка",
    "free":      "✅ Бесплатно",
    "promo":     "🎟 Промокод",
    "back":      "🔙 Вернуться/Назад",
}


@admin_router.callback_query(F.data == "admin_select_btn_to_edit", F.from_user.id.in_(ADMIN_IDS))
async def admin_select_btn(c: CallbackQuery):
    kb = []
    keys = list(BTN_MAPPING.keys())
    for i in range(0, len(keys), 2):
        row = [InlineKeyboardButton(text=BTN_LABELS[keys[i]], callback_data=f"bc_{keys[i]}")]
        if i + 1 < len(keys):
            row.append(InlineKeyboardButton(text=BTN_LABELS[keys[i + 1]], callback_data=f"bc_{keys[i + 1]}"))
        kb.append(row)
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text("✏️ <b>Выберите кнопку для редактирования:</b>",
                              reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@admin_router.callback_query(F.data.startswith("bc_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_btn_sub(c: CallbackQuery, state: FSMContext):
    btn = c.data.replace("bc_", "")
    await state.update_data(editing_btn=btn)
    s = get_bot_settings()
    tk, ek = BTN_MAPPING.get(btn, (f"btn_{btn}", f"btn_{btn}_emoji"))
    cur_text = s.get(tk, "—")
    cur_emoji = s.get(ek, "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Изменить текст", callback_data="be_text")],
        [InlineKeyboardButton(text="🎭 Изменить кастомный эмодзи (ID)", callback_data="be_emoji")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_select_btn_to_edit")]
    ])
    await c.message.edit_text(
        f"✏️ <b>Настройка кнопки: {BTN_LABELS.get(btn, btn)}</b>\n\n"
        f"Текущий текст: <b>{cur_text}</b>\n"
        f"Текущий Emoji ID: <code>{cur_emoji}</code>\n\n"
        "💡 Для кастомного эмодзи — скопируйте ID эмодзи из любого сета в Telegram.",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "be_text")
async def be_t_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("✏️ Введите новый текст кнопки:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_btn_text)


@admin_router.callback_query(F.data == "be_emoji")
async def be_e_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("🎭 Введите ID кастомного эмодзи (число) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_btn_emoji)


@admin_router.message(AdminStates.wait_for_btn_text)
async def bs_t(m: Message, state: FSMContext):
    d = await state.get_data()
    tk, _ = BTN_MAPPING.get(d['editing_btn'], (f"btn_{d['editing_btn']}", ""))
    set_bot_setting(tk, m.text.strip())
    await m.answer("✅ Текст кнопки обновлён!")
    await state.clear()


@admin_router.message(AdminStates.wait_for_btn_emoji)
async def bs_e(m: Message, state: FSMContext):
    d = await state.get_data()
    _, ek = BTN_MAPPING.get(d['editing_btn'], ("", f"btn_{d['editing_btn']}_emoji"))
    val = m.text.strip()
    if val == "0":
        set_bot_setting(ek, "0")
        await m.answer("✅ Эмодзи сброшен.")
    elif val.isdigit():
        set_bot_setting(ek, val)
        await m.answer("✅ Эмодзи обновлён!")
    else:
        await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
        return
    await state.clear()


# ─── ГЛОБАЛЬНЫЕ КАСТОМНЫЕ ЭМОДЗИ В ТЕКСТАХ ────────────────────────────────────

GLOBAL_EMOJI_KEYS = {
    "ge_start":       "Эмодзи старта (замена 🔐)",
    "ge_profile":     "Эмодзи профиля в инлайн-меню (замена 👤)",
    "ge_info":        "Эмодзи информации (замена ℹ️)",
    "ge_ref":         "Эмодзи рефералки (замена 🤝)",
    "ge_payment":     "Эмодзи оплаты (замена 💳)",
    "ge_success":     "Эмодзи успешной оплаты (замена 🎉)",
    # Профиль пользователя
    "ge_id":          "Эмодзи ID в профиле (замена 🆔)",
    "ge_sub_status":  "Эмодзи статуса подписки (замена 📊)",
    "ge_sub_active":  "Эмодзи активной подписки (замена ✅)",
    "ge_sub_no":      "Эмодзи отсутствия подписки (замена ❌)",
    "ge_free_server": "Эмодзи бесплатного сервера (замена 🆓)",
}


@admin_router.callback_query(F.data == "admin_global_emoji", F.from_user.id.in_(ADMIN_IDS))
async def admin_global_emoji(c: CallbackQuery):
    s = get_bot_settings()
    kb = []
    for key, label in GLOBAL_EMOJI_KEYS.items():
        cur = s.get(key, "0")
        cur_str = f"✅ ID:{cur}" if cur and cur != "0" else "❌ Не задан"
        kb.append([InlineKeyboardButton(text=f"{label}: {cur_str}", callback_data=f"setge_{key}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text(
        "😀 <b>Кастомные эмодзи в текстах бота</b>\n\n"
        "Здесь задаются ID кастомных эмодзи из Telegram Premium-сетов. "
        "Они будут отображаться в текстах сообщений бота вместо стандартных.\n\n"
        "💡 Чтобы получить ID: найдите нужный эмодзи в пакете, нажмите на него — "
        "скопируйте числовой ID из @Combot или @getidbot.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@admin_router.callback_query(F.data.startswith("setge_"), F.from_user.id.in_(ADMIN_IDS))
async def set_global_emoji(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setge_", "")
    await state.update_data(ge_key=key)
    label = GLOBAL_EMOJI_KEYS.get(key, key)
    await c.message.answer(f"Введите ID кастомного эмодзи для:\n<b>{label}</b>\n\n(«0» для сброса)", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_global_emoji)


@admin_router.message(AdminStates.wait_for_global_emoji)
async def save_global_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    val = m.text.strip()
    if val == "0":
        set_bot_setting(d['ge_key'], "0")
        await m.answer("✅ Эмодзи сброшен.")
    elif val.isdigit():
        set_bot_setting(d['ge_key'], val)
        await m.answer("✅ Эмодзи сохранён!")
    else:
        await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
        return
    await state.clear()


# ─── ЭМОДЗИ ГЛАВНЫХ КНОПОК МЕНЮ ──────────────────────────────────────────────

KB_EMOJI_MAP = {
    "kb_vpn_emoji":     ("⚡️", "⚡️ Подключить VPN",      "kb_vpn_emoji_id"),
    "kb_profile_emoji": ("👤", "👤 Профиль",              "kb_profile_emoji_id"),
    "kb_info_emoji":    ("ℹ️", "ℹ️ Информация",          "kb_info_emoji_id"),
    "kb_admin_emoji":   ("🔧", "🔧 Администрирование",   "kb_admin_emoji_id"),
}


@admin_router.callback_query(F.data == "admin_kb_emoji", F.from_user.id.in_(ADMIN_IDS))
async def admin_kb_emoji_menu(c: CallbackQuery):
    s = get_bot_settings()
    kb = []
    for key, (default, label, id_key) in KB_EMOJI_MAP.items():
        cur_char = s.get(key, default)
        cur_id   = s.get(id_key, "0")
        id_str   = f"✅ кастом. ID:{cur_id}" if cur_id and cur_id != "0" else "стандарт"
        kb.append([InlineKeyboardButton(
            text=f"{label}  →  {cur_char} ({id_str})",
            callback_data=f"setkbe_{key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text(
        "⌨️ <b>Эмодзи кнопок главного меню</b>\n\n"
        "Для каждой кнопки можно задать:\n"
        "• <b>Эмодзи-символ</b> — отображается в reply-клавиатуре (снизу экрана)\n"
        "• <b>ID кастомного эмодзи</b> (Premium) — отображается в inline-кнопках меню\n\n"
        "⚠️ Telegram не поддерживает кастомные эмодзи в reply-клавиатуре.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@admin_router.callback_query(F.data.startswith("setkbe_"), F.from_user.id.in_(ADMIN_IDS))
async def set_kb_emoji_req(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setkbe_", "")
    default, label, id_key = KB_EMOJI_MAP.get(key, ("", key, ""))
    await state.update_data(kb_emoji_key=key, kb_emoji_id_key=id_key, kb_emoji_default=default)
    s = get_bot_settings()
    cur_char = s.get(key, default)
    cur_id   = s.get(id_key, "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😀 Изменить эмодзи (символ)", callback_data="kbemoji_char")],
        [InlineKeyboardButton(text="🎭 Изменить кастомный ID (Premium)", callback_data="kbemoji_id")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_kb_emoji")],
    ])
    await c.message.edit_text(
        f"🔧 <b>Кнопка: {label}</b>\n\n"
        f"Текущий символ: {cur_char}\n"
        f"Кастомный ID: <code>{cur_id}</code>",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "kbemoji_char", F.from_user.id.in_(ADMIN_IDS))
async def kbemoji_char_req(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    default = d.get("kb_emoji_default", "")
    await c.message.answer(
        f"Введите новый эмодзи-символ (например ⚡️) или «0» для сброса к стандартному ({default}):",
        reply_markup=CANCEL_KB
    )
    await state.update_data(kb_save_mode="char")
    await state.set_state(AdminStates.wait_for_kb_emoji)
    await c.answer()


@admin_router.callback_query(F.data == "kbemoji_id", F.from_user.id.in_(ADMIN_IDS))
async def kbemoji_id_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ID кастомного эмодзи (число) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.update_data(kb_save_mode="id")
    await state.set_state(AdminStates.wait_for_kb_emoji)
    await c.answer()


@admin_router.message(AdminStates.wait_for_kb_emoji)
async def save_kb_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    mode    = d.get("kb_save_mode", "char")
    key     = d.get("kb_emoji_key", "")
    id_key  = d.get("kb_emoji_id_key", "")
    default = d.get("kb_emoji_default", "")

    if mode == "char":
        val = default if m.text.strip() == "0" else m.text.strip()
        set_bot_setting(key, val)
        await m.answer(f"✅ Эмодзи-символ обновлён: {val}")
    else:
        val = m.text.strip()
        if val == "0":
            set_bot_setting(id_key, "0")
            await m.answer("✅ Кастомный ID сброшен.")
        elif val.isdigit():
            set_bot_setting(id_key, val)
            await m.answer("✅ Кастомный ID сохранён!")
        else:
            await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
            return
    await state.clear()



# ─── ЭМОДЗИ КНОПОК ОПЛАТЫ ─────────────────────────────────────────────────────

PAY_EMOJI_MAP = {
    "kb_plan_emoji":           ("🗓", "🗓 Тариф (кнопки выбора тарифа)",  "kb_plan_emoji_id"),
    "kb_pay_stars_emoji":      ("⭐️", "⭐️ Telegram Stars (выбор тарифа)", "kb_pay_stars_id"),
    "kb_pay_yoo_emoji":        ("💛", "💛 ЮMoney (выбор тарифа)",          "kb_pay_yoo_id"),
    "kb_pay_crypto_emoji":     ("💎", "💎 CryptoBot (выбор тарифа)",       "kb_pay_crypto_id"),
    "pay_btn_crypto_pay_emoji":("💎", "💎 Оплатить через CryptoBot",       "pay_btn_crypto_pay_id"),
    "pay_btn_yoo_pay_emoji":   ("💛", "💛 Оплатить через ЮMoney",          "pay_btn_yoo_pay_id"),
    "pay_btn_paid_emoji":      ("✅", "✅ Я оплатил",                      "pay_btn_paid_id"),
}


@admin_router.callback_query(F.data == "admin_pay_emoji", F.from_user.id.in_(ADMIN_IDS))
async def admin_pay_emoji_menu(c: CallbackQuery):
    s = get_bot_settings()
    kb = []
    for key, (default, label, id_key) in PAY_EMOJI_MAP.items():
        cur_emoji = s.get(key, default)
        cur_id    = s.get(id_key, "0")
        id_str    = f"✅ кастом. ID:{cur_id}" if cur_id and cur_id != "0" else "стандарт"
        kb.append([InlineKeyboardButton(
            text=f"{label}  →  {cur_emoji} ({id_str})",
            callback_data=f"setpaye_{key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text(
        "💳 <b>Эмодзи кнопок оплаты</b>\n\n"
        "Для каждого способа оплаты можно задать:\n"
        "• <b>Эмодзи</b> — любой юникод символ\n"
        "• <b>ID кастомного эмодзи</b> (Premium) — для анимированного\n\n"
        "💡 Кнопки отображаются в меню выбора оплаты.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@admin_router.callback_query(F.data.startswith("setpaye_"), F.from_user.id.in_(ADMIN_IDS))
async def set_pay_emoji_req(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setpaye_", "")
    default, label, id_key = PAY_EMOJI_MAP.get(key, ("", key, ""))
    await state.update_data(pay_emoji_key=key, pay_emoji_id_key=id_key, pay_emoji_default=default)
    s = get_bot_settings()
    cur_e  = s.get(key, default)
    cur_id = s.get(id_key, "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😀 Изменить эмодзи (символ)", callback_data="payemoji_char")],
        [InlineKeyboardButton(text="🎭 Изменить кастомный ID (Premium)", callback_data="payemoji_id")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_pay_emoji")],
    ])
    await c.message.edit_text(
        f"🔧 <b>Кнопка: {label}</b>\n\n"
        f"Текущий эмодзи: {cur_e}\n"
        f"Кастомный ID: <code>{cur_id}</code>",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "payemoji_char", F.from_user.id.in_(ADMIN_IDS))
async def payemoji_char_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новый эмодзи-символ (например 💰) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_pay_emoji)
    await state.update_data(pay_save_mode="char")
    await c.answer()


@admin_router.callback_query(F.data == "payemoji_id", F.from_user.id.in_(ADMIN_IDS))
async def payemoji_id_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ID кастомного эмодзи (число) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_pay_emoji)
    await state.update_data(pay_save_mode="id")
    await c.answer()


@admin_router.message(AdminStates.wait_for_pay_emoji)
async def save_pay_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    mode    = d.get("pay_save_mode", "char")
    key     = d.get("pay_emoji_key", "")
    id_key  = d.get("pay_emoji_id_key", "")
    default = d.get("pay_emoji_default", "")

    if mode == "char":
        val = default if m.text.strip() == "0" else m.text.strip()
        set_bot_setting(key, val)
        await m.answer(f"✅ Эмодзи обновлён: {val}")
    else:
        val = m.text.strip()
        if val == "0":
            set_bot_setting(id_key, "0")
            await m.answer("✅ Кастомный ID сброшен.")
        elif val.isdigit():
            set_bot_setting(id_key, val)
            await m.answer("✅ Кастомный ID сохранён!")
        else:
            await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
            return
    await state.clear()


# ─── ЭМОДЗИ КНОПОК УСТРОЙСТВ ──────────────────────────────────────────────────

DEV_EMOJI_MAP = {
    "kb_dev_down":       ("🔽", "🔽 Уменьшить", "kb_dev_down_id"),
    "kb_dev_counter":    ("💻", "💻 Счётчик", "kb_dev_counter_id"),
    "kb_dev_up":         ("🔼", "🔼 Увеличить", "kb_dev_up_id"),
}


@admin_router.callback_query(F.data == "admin_dev_emoji", F.from_user.id.in_(ADMIN_IDS))
async def admin_dev_emoji_menu(c: CallbackQuery):
    s = get_bot_settings()
    kb = []
    for key, (default, label, id_key) in DEV_EMOJI_MAP.items():
        cur_emoji = s.get(key, default)
        cur_id = s.get(id_key, "0")
        id_str = f"✅ кастом. ID:{cur_id}" if cur_id and cur_id != "0" else "стандарт"
        kb.append([InlineKeyboardButton(
            text=f"{label}  →  {cur_emoji} ({id_str})",
            callback_data=f"setdev_{key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text(
        "🔢 <b>Эмодзи кнопок выбора устройств</b>\n\n"
        "Для каждой кнопки можно задать:\n"
        "• <b>Эмодзи</b> — любой юникод символ\n"
        "• <b>ID кастомного эмодзи</b> (Premium) — для отображения анимированного\n\n"
        "💡 Кнопки: 🔽 (уменьшить), 💻 (счётчик), 🔼 (увеличить)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@admin_router.callback_query(F.data.startswith("setdev_"), F.from_user.id.in_(ADMIN_IDS))
async def set_dev_emoji_req(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setdev_", "")
    default, label, id_key = DEV_EMOJI_MAP.get(key, ("", key, ""))
    await state.update_data(dev_emoji_key=key, dev_emoji_id_key=id_key, dev_emoji_default=default)
    s = get_bot_settings()
    cur_e = s.get(key, default)
    cur_id = s.get(id_key, "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😀 Изменить эмодзи (символ)", callback_data="devemoji_char")],
        [InlineKeyboardButton(text="🎭 Изменить кастомный ID (Premium)", callback_data="devemoji_id")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_dev_emoji")],
    ])
    await c.message.edit_text(
        f"🔧 <b>Кнопка: {label}</b>\n\n"
        f"Текущий эмодзи: {cur_e}\n"
        f"Кастомный ID: <code>{cur_id}</code>",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "devemoji_char", F.from_user.id.in_(ADMIN_IDS))
async def devemoji_char_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новый эмодзи-символ (например 🔻) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_dev_emoji)
    await state.update_data(dev_save_mode="char")
    await c.answer()


@admin_router.callback_query(F.data == "devemoji_id", F.from_user.id.in_(ADMIN_IDS))
async def devemoji_id_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ID кастомного эмодзи (число) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_dev_emoji)
    await state.update_data(dev_save_mode="id")
    await c.answer()


@admin_router.message(AdminStates.wait_for_dev_emoji)
async def save_dev_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    mode    = d.get("dev_save_mode", "char")
    key     = d.get("dev_emoji_key", "")
    id_key  = d.get("dev_emoji_id_key", "")
    default = d.get("dev_emoji_default", "")

    if mode == "char":
        val = default if m.text.strip() == "0" else m.text.strip()
        set_bot_setting(key, val)
        await m.answer(f"✅ Эмодзи обновлён: {val}")
    else:
        val = m.text.strip()
        if val == "0":
            set_bot_setting(id_key, "0")
            await m.answer("✅ Кастомный ID сброшен.")
        elif val.isdigit():
            set_bot_setting(id_key, val)
            await m.answer("✅ Кастомный ID сохранён!")
        else:
            await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
            return
    await state.clear()


# ─── ЭМОДЗИ КНОПОК ИНФО И АКТИВНОГО VPN ──────────────────────────────────────

INFO_VPN_EMOJI_MAP = {
    "btn_info_agree_emoji":   ("📄", "📄 Соглашение (Инфо)",             "btn_info_agree_emoji_id"),
    "btn_info_privacy_emoji": ("🔒", "🔒 Конфиденциальность (Инфо)",     "btn_info_privacy_emoji_id"),
    "btn_info_refund_emoji":  ("💰", "💰 Возврат (Инфо)",                "btn_info_refund_emoji_id"),
    "btn_info_support_emoji": ("🛠", "🛠 Поддержка (Инфо)",              "btn_info_support_emoji_id"),
    "btn_info_channel_emoji": ("📢", "📢 Канал (Инфо)",                   "btn_info_channel_emoji_id"),
    "btn_info_install_emoji": ("📲", "📲 Инструкция (Инфо)",             "btn_info_install_emoji_id"),
    "btn_install_vpn_emoji":  ("📲", "📲 Установить VPN (Активный VPN)", "btn_install_vpn_emoji_id"),
    "btn_devices_emoji":      ("📱", "📱 Устройства (Активный VPN)",     "btn_devices_emoji_id"),
    "btn_renew_emoji":        ("🔄", "🔄 Продлить (Активный VPN)",       "btn_renew_emoji_id"),
}


@admin_router.callback_query(F.data == "admin_info_vpn_emoji", F.from_user.id.in_(ADMIN_IDS))
async def admin_info_vpn_emoji_menu(c: CallbackQuery):
    s = get_bot_settings()
    kb = []
    for key, (default, label, id_key) in INFO_VPN_EMOJI_MAP.items():
        cur_emoji = s.get(key, default)
        cur_id = s.get(id_key, "0")
        id_str = f"✅ кастом. ID:{cur_id}" if cur_id and cur_id != "0" else "стандарт"
        kb.append([InlineKeyboardButton(
            text=f"{label}  →  {cur_emoji} ({id_str})",
            callback_data=f"setivpe_{key}"
        )])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    await c.message.edit_text(
        "🔔 <b>Эмодзи кнопок Инфо и Активного VPN</b>\n\n"
        "Для каждой кнопки можно задать:\n"
        "• <b>Эмодзи</b> — любой юникод символ (отображается в тексте кнопки)\n"
        "• <b>ID кастомного эмодзи</b> (Premium) — для анимированного\n\n"
        "💡 Кнопки Инфо отображаются в разделе «Информация».\n"
        "Кнопки Активный VPN — в экране с активной подпиской.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@admin_router.callback_query(F.data.startswith("setivpe_"), F.from_user.id.in_(ADMIN_IDS))
async def set_info_vpn_emoji_req(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setivpe_", "")
    default, label, id_key = INFO_VPN_EMOJI_MAP.get(key, ("", key, ""))
    await state.update_data(ivp_emoji_key=key, ivp_emoji_id_key=id_key, ivp_emoji_default=default)
    s = get_bot_settings()
    cur_e = s.get(key, default)
    cur_id = s.get(id_key, "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😀 Изменить эмодзи (символ)", callback_data="ivpemoji_char")],
        [InlineKeyboardButton(text="🎭 Изменить кастомный ID (Premium)", callback_data="ivpemoji_id")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_info_vpn_emoji")],
    ])
    await c.message.edit_text(
        f"🔧 <b>Кнопка: {label}</b>\n\n"
        f"Текущий эмодзи: {cur_e}\n"
        f"Кастомный ID: <code>{cur_id}</code>",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "ivpemoji_char", F.from_user.id.in_(ADMIN_IDS))
async def ivpemoji_char_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите новый эмодзи-символ (например 📲) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_info_vpn_emoji)
    await state.update_data(ivp_save_mode="char")
    await c.answer()


@admin_router.callback_query(F.data == "ivpemoji_id", F.from_user.id.in_(ADMIN_IDS))
async def ivpemoji_id_req(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите ID кастомного эмодзи (число) или «0» для сброса:", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_info_vpn_emoji)
    await state.update_data(ivp_save_mode="id")
    await c.answer()


@admin_router.message(AdminStates.wait_for_info_vpn_emoji)
async def save_info_vpn_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    mode    = d.get("ivp_save_mode", "char")
    key     = d.get("ivp_emoji_key", "")
    id_key  = d.get("ivp_emoji_id_key", "")
    default = d.get("ivp_emoji_default", "")

    if mode == "char":
        val = default if m.text.strip() == "0" else m.text.strip()
        set_bot_setting(key, val)
        await m.answer(f"✅ Эмодзи обновлён: {val}")
    else:
        val = m.text.strip()
        if val == "0":
            set_bot_setting(id_key, "0")
            await m.answer("✅ Кастомный ID сброшен.")
        elif val.isdigit():
            set_bot_setting(id_key, val)
            await m.answer("✅ Кастомный ID сохранён!")
        else:
            await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
            return
    await state.clear()


# ─── УВЕДОМЛЕНИЯ ──────────────────────────────────────────────────────────────

_NOTIF_DEFAULTS = {
    "expiry": {
        "enabled_key": "notif_expiry_enabled",
        "text_key":    "notif_expiry_text",
        "btn_key":     "notif_expiry_btn",
        "hours_key":   "notif_expiry_hours",
        "btn_emoji_key": "notif_expiry_btn_emoji_id",
        "label":       "⚠️ Подписка истекает",
        "default_text": (
            "⚠️ Завтра закончится ваша подписка на Anonch VPN\n\n"
            "Автоматического продления нет! Чтобы не остаться без связи, "
            "продлите свою подписку в разделе /profile"
        ),
        "default_btn":   "📋 Перейти к продлению",
        "default_hours": "24",
    },
    "noconn": {
        "enabled_key": "notif_noconn_enabled",
        "text_key":    "notif_noconn_text",
        "btn_key":     "notif_noconn_btn",
        "hours_key":   "notif_noconn_hours",
        "btn_emoji_key": "notif_noconn_btn_emoji_id",
        "label":       "🤖 Не подключился",
        "default_text": (
            "🤖 Мы заметили, что вы еще не подключились\n\n"
            "Если возникли сложности — напишите в поддержку. Мы всегда готовы помочь!"
        ),
        "default_btn":   "Подключиться",
        "default_hours": "2",
    },
}


def _notif_kb(s):
    """Строит клавиатуру для панели уведомлений."""
    kb = []
    for ntype, cfg in _NOTIF_DEFAULTS.items():
        enabled = s.get(cfg["enabled_key"], "1") == "1"
        status = "✅ Вкл" if enabled else "❌ Выкл"
        hours = s.get(cfg["hours_key"], cfg["default_hours"])
        hours_label = f"за {hours}ч" if ntype == "expiry" else f"через {hours}ч"
        emoji_id = s.get(cfg["btn_emoji_key"], "0")
        emoji_str = f"✅ ID:{emoji_id}" if emoji_id and emoji_id != "0" else "❌ Не задан"
        kb.append([InlineKeyboardButton(
            text=f"{cfg['label']} ({hours_label}) — {status}",
            callback_data=f"notif_toggle_{ntype}"
        )])
        kb.append([
            InlineKeyboardButton(text="✏️ Текст", callback_data=f"notif_edit_{ntype}_text"),
            InlineKeyboardButton(text="📋 Кнопка", callback_data=f"notif_edit_{ntype}_btn"),
            InlineKeyboardButton(text="⏰ Часы", callback_data=f"notif_edit_{ntype}_hours"),
        ])
        kb.append([
            InlineKeyboardButton(
                text=f"🎭 Эмодзи кнопки: {emoji_str}",
                callback_data=f"notif_edit_{ntype}_btn_emoji"
            ),
        ])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@admin_router.callback_query(F.data == "admin_notifications", F.from_user.id.in_(ADMIN_IDS))
async def admin_notifications_menu(c: CallbackQuery):
    s = get_bot_settings()
    lines = ["🔔 <b>Управление уведомлениями</b>\n"]
    for ntype, cfg in _NOTIF_DEFAULTS.items():
        enabled = s.get(cfg["enabled_key"], "1") == "1"
        hours = s.get(cfg["hours_key"], cfg["default_hours"])
        hours_label = f"за {hours}ч до истечения" if ntype == "expiry" else f"через {hours}ч после активации"
        text_preview = s.get(cfg["text_key"], cfg["default_text"])[:60] + "..."
        lines.append(
            f"<b>{cfg['label']}</b>\n"
            f"Статус: {'✅ Включено' if enabled else '❌ Выключено'} | Отправка: {hours_label}\n"
            f"Текст: {text_preview}\n"
        )
    await c.message.edit_text("\n".join(lines), reply_markup=_notif_kb(s))


@admin_router.callback_query(F.data.startswith("notif_toggle_"), F.from_user.id.in_(ADMIN_IDS))
async def notif_toggle(c: CallbackQuery):
    ntype = c.data.replace("notif_toggle_", "")
    cfg = _NOTIF_DEFAULTS.get(ntype)
    if not cfg:
        return await c.answer("Неизвестный тип")
    s = get_bot_settings()
    current = s.get(cfg["enabled_key"], "1")
    new_val = "0" if current == "1" else "1"
    set_bot_setting(cfg["enabled_key"], new_val)
    await c.answer("✅ Включено" if new_val == "1" else "❌ Выключено")
    s = get_bot_settings()
    await c.message.edit_reply_markup(reply_markup=_notif_kb(s))


@admin_router.callback_query(F.data.startswith("notif_edit_"), F.from_user.id.in_(ADMIN_IDS))
async def notif_edit_req(c: CallbackQuery, state: FSMContext):
    parts = c.data.split("_")  # notif_edit_<type>_<field>
    ntype = parts[2]
    field = parts[3]
    cfg = _NOTIF_DEFAULTS.get(ntype)
    if not cfg:
        return await c.answer("Неизвестный тип")
    await state.update_data(notif_type=ntype, notif_field=field)
    s = get_bot_settings()
    if field == "text":
        cur = s.get(cfg["text_key"], cfg["default_text"])
        await c.message.answer(
            f"✏️ <b>Текст уведомления «{cfg['label']}»</b>\n\n"
            f"Текущий текст:\n{cur}\n\n"
            "Введите новый текст (HTML поддерживается):",
            reply_markup=CANCEL_KB
        )
        await state.set_state(AdminStates.wait_for_notif_text)
    elif field == "btn":
        cur = s.get(cfg["btn_key"], cfg["default_btn"])
        await c.message.answer(
            f"📋 <b>Текст кнопки уведомления «{cfg['label']}»</b>\n\n"
            f"Текущий текст кнопки: <b>{cur}</b>\n\n"
            "Введите новый текст кнопки:",
            reply_markup=CANCEL_KB
        )
        await state.set_state(AdminStates.wait_for_notif_btn_text)
    elif field == "hours":
        cur = s.get(cfg["hours_key"], cfg["default_hours"])
        hint = "до истечения подписки" if ntype == "expiry" else "после активации подписки"
        await c.message.answer(
            f"⏰ <b>Часы отправки уведомления «{cfg['label']}»</b>\n\n"
            f"Текущее значение: <b>{cur}ч</b> ({hint})\n\n"
            "Введите новое количество часов (целое число):",
            reply_markup=CANCEL_KB
        )
        await state.set_state(AdminStates.wait_for_notif_hours)
    elif field == "btn_emoji":
        cur = s.get(cfg["btn_emoji_key"], "0")
        cur_str = f"<code>{cur}</code>" if cur and cur != "0" else "❌ Не задан"
        await c.message.answer(
            f"🎭 <b>Кастомный эмодзи кнопки «{cfg['label']}»</b>\n\n"
            f"Текущий ID: {cur_str}\n\n"
            "Введите ID кастомного эмодзи (число) или «0» для сброса:",
            reply_markup=CANCEL_KB
        )
        await state.set_state(AdminStates.wait_for_notif_btn_emoji)
    await c.answer()


@admin_router.message(AdminStates.wait_for_notif_text)
async def save_notif_text(m: Message, state: FSMContext):
    d = await state.get_data()
    ntype = d.get("notif_type", "")
    cfg = _NOTIF_DEFAULTS.get(ntype, {})
    set_bot_setting(cfg.get("text_key", ""), m.html_text.strip())
    await m.answer("✅ Текст уведомления обновлён!")
    await state.clear()


@admin_router.message(AdminStates.wait_for_notif_btn_text)
async def save_notif_btn_text(m: Message, state: FSMContext):
    d = await state.get_data()
    ntype = d.get("notif_type", "")
    cfg = _NOTIF_DEFAULTS.get(ntype, {})
    set_bot_setting(cfg.get("btn_key", ""), m.text.strip())
    await m.answer("✅ Текст кнопки уведомления обновлён!")
    await state.clear()


@admin_router.message(AdminStates.wait_for_notif_btn_emoji)
async def save_notif_btn_emoji(m: Message, state: FSMContext):
    d = await state.get_data()
    ntype = d.get("notif_type", "")
    cfg = _NOTIF_DEFAULTS.get(ntype, {})
    val = m.text.strip()
    if val == "0":
        set_bot_setting(cfg.get("btn_emoji_key", ""), "0")
        await m.answer("✅ Эмодзи кнопки сброшен.")
    elif val.isdigit():
        set_bot_setting(cfg.get("btn_emoji_key", ""), val)
        await m.answer("✅ Эмодзи кнопки уведомления обновлён!")
    else:
        await m.answer("❌ Введите числовой ID кастомного эмодзи или «0» для сброса!")
        return
    await state.clear()


@admin_router.message(AdminStates.wait_for_notif_hours)
async def save_notif_hours(m: Message, state: FSMContext):
    d = await state.get_data()
    ntype = d.get("notif_type", "")
    cfg = _NOTIF_DEFAULTS.get(ntype, {})
    try:
        val = int(m.text.strip())
        if val < 1:
            raise ValueError
        set_bot_setting(cfg.get("hours_key", ""), str(val))
        await m.answer(f"✅ Часы обновлены: {val}ч")
        await state.clear()
    except (ValueError, TypeError):
        await m.answer("❌ Введите целое положительное число!")


@admin_router.callback_query(F.data == "admin_payments", F.from_user.id.in_(ADMIN_IDS))
async def admin_payments_menu(c: CallbackQuery):
    s = get_bot_settings()

    def st(k): return "✅" if s.get(k) else "❌"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Telegram Stars — всегда активен", callback_data="info_stars")],
        [InlineKeyboardButton(text=f"[{st('pay_yoo_num')}] 💛 ЮMoney", callback_data="cfg_yoo")],
        [InlineKeyboardButton(text=f"[{st('pay_crypto_tok')}] 💎 CryptoBot", callback_data="cfg_crypto")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")]
    ])
    await c.message.edit_text(
        "💰 <b>Управление платёжными системами</b>\n\n"
        "Stars работает автоматически.\n"
        "Для ЮMoney укажите номер кошелька (и токен для автопроверки).\n"
        "Для CryptoBot укажите API-токен от @CryptoBot.",
        reply_markup=kb
    )


@admin_router.callback_query(F.data == "info_stars", F.from_user.id.in_(ADMIN_IDS))
async def info_stars(c: CallbackQuery):
    await c.answer("Telegram Stars работает автоматически, настройка не нужна ✅", show_alert=True)


@admin_router.callback_query(F.data.startswith("cfg_"), F.from_user.id.in_(ADMIN_IDS))
async def cfg_payment_sys(c: CallbackQuery):
    sys = c.data.split("_")[1]
    s = get_bot_settings()
    kb = []
    if sys == "yoo":
        num = s.get("pay_yoo_num", "—")
        tok = "✅ Задан" if s.get("pay_yoo_tok") else "❌ Не задан"
        txt = (f"💛 <b>ЮMoney</b>\n\nНомер кошелька: <code>{num}</code>\nAPI-токен: {tok}\n\n"
               "Без токена оплата фиксируется вручную.")
        kb.append([InlineKeyboardButton(text="📱 Номер кошелька", callback_data="setp_pay_yoo_num")])
        kb.append([InlineKeyboardButton(text="🔑 API-токен (автопроверка)", callback_data="setp_pay_yoo_tok")])
    elif sys == "crypto":
        tok = "✅ Задан" if s.get("pay_crypto_tok") else "❌ Не задан"
        txt = f"💎 <b>CryptoBot</b>\n\nAPI-токен: {tok}\n\nПолучите токен у @CryptoBot → My Apps → Create App"
        kb.append([InlineKeyboardButton(text="🔑 API-токен", callback_data="setp_pay_crypto_tok")])
    else:
        txt = "Неизвестная система"
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_payments")])
    await c.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@admin_router.callback_query(F.data.startswith("setp_"), F.from_user.id.in_(ADMIN_IDS))
async def set_pay_key(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("setp_", "")
    await state.update_data(epk=key)
    await c.message.answer("Введите значение (или «0» для очистки):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_payment_setting)


@admin_router.message(AdminStates.wait_for_payment_setting)
async def save_pay_setting(m: Message, state: FSMContext):
    d = await state.get_data()
    set_bot_setting(d['epk'], "" if m.text.strip() == "0" else m.text.strip())
    await m.answer("✅ Сохранено!")
    await state.clear()


# ─── ПРОМОКОДЫ ────────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_promos_menu", F.from_user.id.in_(ADMIN_IDS))
async def adm_promos_menu(c: CallbackQuery):
    promos = get_all_promos()
    text = "🎟 <b>Активные промокоды:</b>\n\n"
    if promos:
        for p in promos[:15]:
            text += f"• <code>{p['code']}</code> — {p['value']} ₽, осталось: {p['uses_left']}\n"
    else:
        text += "Промокодов нет."
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")]
    ])
    await c.message.edit_text(text, reply_markup=kb)


@admin_router.callback_query(F.data == "admin_create_promo", F.from_user.id.in_(ADMIN_IDS))
async def adm_create_promo(c: CallbackQuery, state: FSMContext):
    await c.message.answer("Введите название промокода (буквы/цифры, будет в верхнем регистре):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_promo_name)


@admin_router.message(AdminStates.wait_for_promo_name)
async def adm_pr_n(m: Message, state: FSMContext):
    await state.update_data(pn=m.text.strip().upper())
    await m.answer("Введите сумму пополнения баланса (рублей):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_promo_value)


@admin_router.message(AdminStates.wait_for_promo_value)
async def adm_pr_v(m: Message, state: FSMContext):
    try:
        await state.update_data(pv=int(m.text))
        await m.answer("Введите количество активаций:", reply_markup=CANCEL_KB)
        await state.set_state(AdminStates.wait_for_promo_uses)
    except:
        await m.answer("❌ Введите число!")


@admin_router.message(AdminStates.wait_for_promo_uses)
async def adm_pr_u(m: Message, state: FSMContext):
    try:
        d = await state.get_data()
        create_promo(d['pn'], d['pv'], int(m.text))
        await m.answer(f"✅ Промокод <b>{d['pn']}</b> создан!\nСумма: {d['pv']} ₽, активаций: {m.text}")
        await state.clear()
    except:
        await m.answer("❌ Ошибка!")


# ─── ТЕКСТЫ ───────────────────────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_edit_texts_menu", F.from_user.id.in_(ADMIN_IDS))
async def adm_txt_m(c: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Текст старта", callback_data="et_start_text"),
         InlineKeyboardButton(text="👤 Текст профиля", callback_data="et_profile_text")],
        [InlineKeyboardButton(text="ℹ️ Текст Инфо", callback_data="et_info_text"),
         InlineKeyboardButton(text="🎁 Текст подарка", callback_data="et_gift_text")],
        [InlineKeyboardButton(text="📦 Текст тарифов", callback_data="et_tariff_text"),
         InlineKeyboardButton(text="💳 Текст счёта", callback_data="et_invoice_text")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_home")]
    ])
    await c.message.edit_text(
        "💬 <b>Редактирование текстов</b>\n\nПоддерживается HTML: <b>жирный</b>, <i>курсив</i>, <code>код</code>.",
        reply_markup=kb
    )


@admin_router.callback_query(F.data.startswith("et_"), F.from_user.id.in_(ADMIN_IDS))
async def adm_et_req(c: CallbackQuery, state: FSMContext):
    key = c.data.replace("et_", "")
    await state.update_data(ek=key)
    s = get_bot_settings()
    cur = s.get(key, "—")
    await c.message.answer(f"Текущий текст:\n{cur}\n\n✏️ Введите новый текст (HTML поддерживается):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_text)


@admin_router.message(AdminStates.wait_for_text)
async def adm_et_sv(m: Message, state: FSMContext):
    d = await state.get_data()
    set_bot_setting(d['ek'], m.html_text)
    await m.answer("✅ Текст обновлён!")
    await state.clear()


# ─── GIF И СТИКЕР НА СТАРТЕ ───────────────────────────────────────────────────

@admin_router.callback_query(F.data == "admin_edit_gif", F.from_user.id.in_(ADMIN_IDS))
async def adm_gif_req(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    cur = s.get("start_media_id", "—")
    await c.message.answer(f"Текущий GIF ID: <code>{cur}</code>\n\n🖼 Отправьте новый GIF (анимацию):", reply_markup=CANCEL_KB)
    await state.set_state(AdminStates.wait_for_gif)


@admin_router.message(AdminStates.wait_for_gif, F.animation)
async def adm_gif_sv(m: Message, state: FSMContext):
    set_bot_setting("start_media_id", m.animation.file_id)
    await m.answer(f"✅ GIF обновлён!\nID: <code>{m.animation.file_id}</code>")
    await state.clear()


@admin_router.message(AdminStates.wait_for_gif)
async def adm_gif_wrong(m: Message, state: FSMContext):
    await m.answer("❌ Это не GIF! Отправьте анимацию.")


@admin_router.callback_query(F.data == "admin_edit_sticker", F.from_user.id.in_(ADMIN_IDS))
async def adm_sticker_req(c: CallbackQuery, state: FSMContext):
    s = get_bot_settings()
    cur = s.get("start_sticker_id", "—")
    await c.message.answer(
        f"Текущий стикер ID: <code>{cur}</code>\n\n"
        "🎭 Отправьте стикер, который будет показываться при команде /start\n"
        "(или напишите «0» для отключения стикера):",
        reply_markup=CANCEL_KB
    )
    await state.set_state(AdminStates.wait_for_sticker)


@admin_router.message(AdminStates.wait_for_sticker, F.sticker)
async def adm_sticker_sv(m: Message, state: FSMContext):
    set_bot_setting("start_sticker_id", m.sticker.file_id)
    await m.answer(f"✅ Стикер обновлён!\nID: <code>{m.sticker.file_id}</code>")
    await state.clear()


@admin_router.message(AdminStates.wait_for_sticker, F.text == "0")
async def adm_sticker_clear(m: Message, state: FSMContext):
    set_bot_setting("start_sticker_id", "")
    await m.answer("✅ Стикер отключён!")
    await state.clear()


@admin_router.message(AdminStates.wait_for_sticker)
async def adm_sticker_wrong(m: Message, state: FSMContext):
    await m.answer("❌ Отправьте стикер или напишите «0» для отключения.")
