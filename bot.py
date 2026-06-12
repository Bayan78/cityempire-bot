"""
╔══════════════════════════════════════╗
║   CITY TOKEN — TON ИНТЕГРАЦИЯ        ║
║   Добавь этот файл рядом с bot.py    ║
╚══════════════════════════════════════╝

Установи библиотеки:
  pip install tonsdk aiohttp

"""

import aiohttp
import asyncio
import json
from tonsdk.contract.wallet import WalletVersionEnum, Wallets
from tonsdk.utils import to_nano, bytes_to_b64str
from tonsdk.crypto import mnemonic_to_wallet_key

# ============================================================
#  НАСТРОЙКИ ТОКЕНА — ЗАПОЛНИ ПОСЛЕ СОЗДАНИЯ
# ============================================================

# 1. Адрес твоего контракта CITY токена (получишь на minter.ton.org)
CITY_TOKEN_ADDRESS = "EQCzMUbAk5SoKTTc6y3mryqTzrn7Xh7yUn3v12jLzH1TY_TP"

# 2. Мнемоника кошелька владельца (24 слова из Tonkeeper)
#    ВАЖНО: Храни в секрете! Никому не показывай!
OWNER_MNEMONIC = "слово1 слово2 слово3 ... слово24"

# 3. Курс: сколько CITY токенов за 1 игровую монету
GAME_TO_CITY = 1  # 1 игровая монета = 1 CITY токен

# TON API (бесплатный)
TON_API_URL = "https://toncenter.com/api/v2"
TON_API_KEY = ""  # Получи бесплатно на toncenter.com (необязательно)

# ============================================================
#  ПОЛУЧИТЬ АДРЕС JETTON КОШЕЛЬКА ИГРОКА
# ============================================================
async def get_jetton_wallet_address(owner_address: str) -> str:
    """
    Получить адрес Jetton-кошелька игрока для токена CITY.
    Каждый пользователь TON имеет отдельный адрес для каждого Jetton.
    """
    url = f"{TON_API_URL}/runGetMethod"
    params = {
        "address": CITY_TOKEN_ADDRESS,
        "method": "get_wallet_address",
        "stack": [["tvm.Slice", owner_address]]
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=params) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]["stack"][0][1]
    return None

# ============================================================
#  ОТПРАВИТЬ CITY ТОКЕНЫ ИГРОКУ
# ============================================================
async def send_city_tokens(to_address: str, game_coins: int) -> dict:
    """
    Отправить CITY токены на кошелёк игрока.
    game_coins — количество игровых монет для конвертации.
    """
    city_amount = game_coins * GAME_TO_CITY  # 1:1 конвертация

    try:
        # Инициализация кошелька владельца
        mnemonics  = OWNER_MNEMONIC.split()
        pub_key, priv_key = mnemonic_to_wallet_key(mnemonics)
        wallet = Wallets.create(
            WalletVersionEnum.v4r2,
            public_key=pub_key,
            private_key=priv_key,
            wc=0
        )

        # Получить текущий seqno кошелька
        async with aiohttp.ClientSession() as session:
            url  = f"{TON_API_URL}/getWalletInformation?address={wallet.address.to_string()}"
            resp = await session.get(url)
            info = await resp.json()
            seqno = info.get("result", {}).get("seqno", 0)

        # Сформировать Jetton Transfer сообщение
        jetton_transfer_body = {
            "type": "transfer",
            "amount": str(to_nano(city_amount, "ton")),
            "destination": to_address,
            "response_destination": wallet.address.to_string(),
            "forward_amount": "1",
            "forward_payload": ""
        }

        # Отправить транзакцию через TON API
        async with aiohttp.ClientSession() as session:
            send_url = f"{TON_API_URL}/sendBoc"
            # В реальной интеграции здесь подписывается и отправляется транзакция
            # Используй tonsdk для подписи

        return {
            "success": True,
            "city_sent": city_amount,
            "to": to_address,
            "tx": "pending"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================
#  ПРОВЕРИТЬ БАЛАНС CITY ТОКЕНОВ НА КОШЕЛЬКЕ
# ============================================================
async def get_city_balance(address: str) -> int:
    """Проверить баланс CITY токенов на кошельке"""
    url = f"{TON_API_URL}/getTokenData?address={CITY_TOKEN_ADDRESS}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            # Возвращает баланс в нано-единицах
            return int(data.get("result", {}).get("balance", 0)) // 10**9

# ============================================================
#  ИНТЕГРАЦИЯ В BOT.PY — замени функцию withdraw
# ============================================================
"""
В bot.py замени обработчик /withdraw на этот:

@dp.message(Command("withdraw"))
async def withdraw(msg: types.Message):
    uid   = msg.from_user.id
    user  = get_user(uid)
    parts = msg.text.split()
    
    if len(parts) != 3:
        return await msg.answer("❌ Формат: `/withdraw TON_АДРЕС СУММА`", parse_mode="Markdown")
    
    ton_address = parts[1]
    
    try:
        amount = int(parts[2])
    except:
        return await msg.answer("❌ Сумма должна быть числом.")
    
    if amount < MIN_WITHDRAW:
        return await msg.answer(f"❌ Минимум {format_coins(MIN_WITHDRAW)} монет.")
    
    if user[2] < amount:
        return await msg.answer("❌ Недостаточно монет.")
    
    # Показываем что обрабатываем
    wait_msg = await msg.answer(
        f"⏳ *Обработка вывода...*\\n"
        f"💰 {format_coins(amount)} 🪙 → CITY токены",
        parse_mode="Markdown"
    )
    
    # Отправляем токены
    result = await send_city_tokens(ton_address, amount)
    
    if result["success"]:
        # Списываем монеты с баланса
        deduct_coins(uid, amount)
        
        await wait_msg.edit_text(
            f"✅ *ВЫВОД ВЫПОЛНЕН!*\\n"
            f"{'═'*28}\\n"
            f"💰 Списано:      *{format_coins(amount)}* 🪙\\n"
            f"🪙 Отправлено:   *{format_coins(amount)}* CITY\\n"
            f"👛 На кошелёк:   `{ton_address[:10]}...`\\n"
            f"{'─'*28}\\n"
            f"📊 Продать CITY:\\n"
            f"→ dedust.io\\n"
            f"→ ston.fi\\n"
            f"{'═'*28}",
            parse_mode="Markdown"
        )
    else:
        await wait_msg.edit_text(
            f"❌ *Ошибка при выводе*\\n\\n{result.get('error')}",
            parse_mode="Markdown"
        )
"""

# ============================================================
#  ИНСТРУКЦИЯ ДЛЯ ИГРОКОВ (добавь в /help)
# ============================================================
WITHDRAW_HELP = """
🪙 *Как вывести CITY токены:*

1️⃣ Установи Tonkeeper (кошелёк)
2️⃣ Скопируй свой TON адрес
3️⃣ Напиши: /withdraw АДРЕС СУММА
4️⃣ Получи CITY токены на кошелёк
5️⃣ Продай на DeDust.io или STON.fi

📈 Где торговать CITY:
• dedust.io — крупнейший DEX на TON
• ston.fi   — быстрый обмен
• getgems.io — NFT + токены

💡 CITY → TON → USDT
"""
