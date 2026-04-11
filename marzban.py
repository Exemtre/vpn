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


async def marzban_create_or_update_user(telegram_user_id: int, days: int) -> str | None:
    """
    Creates or updates a Marzban user for the given Telegram user ID.
    Returns the first subscription link, or None if Marzban is disabled / an error occurs.
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
        if links:
            return links[0]
        return data.get("subscription_url") or f"{url}/sub/{mz_username}"
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
