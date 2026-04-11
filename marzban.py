import aiohttp
from database.models import get_bot_settings


async def _get_marzban_token(url: str, username: str, password: str) -> str:
    """Authenticate with Marzban and return access token."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{url}/api/admin/token",
            data={"username": username, "password": password, "grant_type": "password"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


async def marzban_create_or_update_user(telegram_user_id: int, days: int) -> tuple[str, str] | None:
    """
    Creates or updates a Marzban user for the given Telegram user ID.
    Returns (vpn_key, sub_url) tuple, or None if Marzban is disabled / an error occurs.
    vpn_key is the first individual protocol link (e.g. vless://...).
    sub_url is the subscription URL (e.g. http://host/sub/username).
    """
    s = get_bot_settings()
    if s.get("marzban_enabled", "0") != "1":
        return None

    url = s.get("marzban_url", "").rstrip("/")
    adm_user = s.get("marzban_admin_user", "")
    adm_pass = s.get("marzban_admin_pass", "")
    inbound = s.get("marzban_inbound", "")

    if not (url and adm_user and adm_pass):
        return None

    import time
    expire_ts = int(time.time()) + days * 86400
    mz_username = f"tg{telegram_user_id}"

    try:
        token = await _get_marzban_token(url, adm_user, adm_pass)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        proxies = {"vless": {"flow": ""}}
        inbounds = {"vless": [inbound]} if inbound else {}

        payload = {
            "username": mz_username,
            "proxies": proxies,
            "inbounds": inbounds,
            "expire": expire_ts,
            "data_limit": 0,
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/api/user/{mz_username}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                user_exists = resp.status == 200

            if user_exists:
                async with session.put(
                    f"{url}/api/user/{mz_username}",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            else:
                async with session.post(
                    f"{url}/api/user",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

        links = data.get("links", [])
        vpn_key = links[0] if links else ""
        # subscription_url may be relative (e.g. "/sub/tgXXX") in some Marzban versions
        sub_url_raw = data.get("subscription_url", "")
        if sub_url_raw:
            sub_url = sub_url_raw if sub_url_raw.startswith("http") else f"{url}{sub_url_raw}"
        else:
            sub_url = f"{url}/sub/{mz_username}"
        return vpn_key, sub_url
    except Exception as e:
        print(f"[Marzban] Error for user {telegram_user_id}: {e}")
        return None


async def marzban_test_connection() -> tuple[bool, str]:
    """Test Marzban API connectivity. Returns (success, message)."""
    s = get_bot_settings()
    url = s.get("marzban_url", "").rstrip("/")
    adm_user = s.get("marzban_admin_user", "")
    adm_pass = s.get("marzban_admin_pass", "")

    if not url:
        return False, "URL Marzban не задан"
    if not adm_user:
        return False, "Имя администратора Marzban не задано"
    if not adm_pass:
        return False, "Пароль Marzban не задан"

    try:
        token = await _get_marzban_token(url, adm_user, adm_pass)
        if token:
            return True, "✅ Подключение к Marzban успешно!"
        return False, "❌ Токен не получен"
    except aiohttp.ClientConnectorError:
        return False, f"❌ Не удалось подключиться к {url}"
    except aiohttp.ClientResponseError as e:
        return False, f"❌ HTTP {e.status}: {e.message}"
    except Exception as e:
        return False, f"❌ Ошибка: {str(e)[:200]}"


async def marzban_get_user_status(telegram_user_id: int) -> dict | None:
    """
    Fetches the current Marzban user record for a given Telegram user ID.
    Returns a dict with keys: status, online_at, used_traffic, data_limit, links, sub_url.
    Returns None if Marzban is disabled, user not found, or an error occurs.
    """
    s = get_bot_settings()
    if s.get("marzban_enabled", "0") != "1":
        return None

    url = s.get("marzban_url", "").rstrip("/")
    adm_user = s.get("marzban_admin_user", "")
    adm_pass = s.get("marzban_admin_pass", "")
    if not (url and adm_user and adm_pass):
        return None

    mz_username = f"tg{telegram_user_id}"
    try:
        token = await _get_marzban_token(url, adm_user, adm_pass)
        headers = {"Authorization": f"Bearer {token}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{url}/api/user/{mz_username}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        sub_url_raw = data.get("subscription_url", "")
        sub_url = (sub_url_raw if sub_url_raw.startswith("http") else f"{url}{sub_url_raw}") if sub_url_raw else f"{url}/sub/{mz_username}"
        return {
            "status": data.get("status", "unknown"),
            "online_at": data.get("online_at"),
            "used_traffic": data.get("used_traffic", 0),
            "data_limit": data.get("data_limit", 0),
            "links": data.get("links", []),
            "sub_url": sub_url,
            "expire": data.get("expire"),
        }
    except Exception as e:
        print(f"[Marzban] get_user_status error for {telegram_user_id}: {e}")
        return None
