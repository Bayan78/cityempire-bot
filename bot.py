import logging
import sqlite3
import asyncio
import random
import os
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import (InlineKeyboardMarkup, InlineKeyboardButton,
                            ReplyKeyboardMarkup, KeyboardButton)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID  = 976860643
GAME_URL  = os.getenv("GAME_URL", "https://bayanchatbot.github.io/cityempire-match/")
# Путь к базе. На Railway ОБЯЗАТЕЛЬНО задай DB_PATH на постоянный Volume,
# например /data/city_empire.db — иначе база стирается при каждом редеплое!
DB = os.getenv("DB_PATH", "city_empire.db")

# ───── Вывод TON на биржу/кошелёк ─────
# Вывод TON ВСЕГДА только для VIP (жёстко зашито).
TON_VIP_ONLY   = True
# Авто-отправка TON on-chain. Включается ТОЛЬКО когда заданы и сид-фраза, и TON_AUTOSEND=1.
# Иначе вывод обрабатывается вручную через админ-панель (безопасный режим по умолчанию).
TON_AUTOSEND   = os.getenv("TON_AUTOSEND", "0") == "1"
TON_MNEMONIC   = os.getenv("TON_WALLET_MNEMONIC", "")   # 24 слова через пробел (горячий кошелёк)
TON_NETWORK    = os.getenv("TON_NETWORK", "mainnet")    # mainnet / testnet
TON_WALLET_VERSION = os.getenv("TON_WALLET_VERSION", "v5r1")  # v5r1 (Tonkeeper W5) или v4r2
TONCENTER_KEY  = os.getenv("TONCENTER_API_KEY", "")
TON_MIN_WD     = float(os.getenv("TON_MIN_WITHDRAW", "0.05"))   # минимум TON к выводу
CITY_MIN_WD    = float(os.getenv("CITY_MIN_WITHDRAW", "100"))   # минимум CITY к выводу
OWNER_TON_REWARD = float(os.getenv("OWNER_TON_DAILY", "10"))    # TON/сутки лично для владельца
# Дневные лимиты ВЫВОДА на одного игрока (защита пула + мотивация играть)
CITY_DAILY_WD_CAP = float(os.getenv("CITY_DAILY_WITHDRAW_CAP", "10000"))  # макс CITY к выводу в сутки
TON_DAILY_WD_CAP  = float(os.getenv("TON_DAILY_WITHDRAW_CAP", "2"))       # макс TON к выводу в сутки

COIN_TO_USDT    = 0.00001
MIN_WITHDRAW    = 50_000
OWNER_START_BAL = 1_000_000_000_000
DEFAULT_COIN_TO_USDT = 0.00001
CITY_TOKEN_ADDRESS   = "EQCzMUbAk5SoKTTc6y3mryqTzrn7Xh7yUn3v12jLzH1TY_TP"

BUILDINGS = {
    "market":     {"name":"🏪 Рынок",          "levels":[0,50,120,250,500,1000],    "income":[0,10,25,55,120,250]},
    "factory":    {"name":"🏭 Завод",           "levels":[0,100,220,450,900,1800],   "income":[0,20,50,110,240,500]},
    "bank":       {"name":"🏦 Банк",            "levels":[0,200,450,900,1800,3600],  "income":[0,40,100,220,480,1000]},
    "powerplant": {"name":"⚡ Электростанция",  "levels":[0,150,330,680,1400,2800],  "income":[0,30,75,165,360,750]},
    "university": {"name":"🎓 Университет",     "levels":[0,300,650,1300,2600,5000], "income":[0,60,140,300,640,1300]},
    "stadium":    {"name":"🏟️ Стадион",        "levels":[0,400,900,1800,3600,7000], "income":[0,80,180,380,800,1600]},
}

ARMY_UNITS = {
    "soldier":  {"name":"⚔️ Солдат",   "attack":10,  "defense":5,   "cost":500},
    "archer":   {"name":"🏹 Лучник",   "attack":20,  "defense":8,   "cost":1000},
    "knight":   {"name":"🛡️ Рыцарь",  "attack":35,  "defense":25,  "cost":2500},
    "tank":     {"name":"🚂 Танк",     "attack":80,  "defense":60,  "cost":8000},
    "general":  {"name":"👑 Генерал",  "attack":200, "defense":150, "cost":25000},
}

MINER_LEVELS = {
    0:{"name":"Нет майнера",  "reward":0,    "cost":500},
    1:{"name":"⛏️ Кирка",    "reward":200,  "cost":1000},
    2:{"name":"🔨 Молот",    "reward":500,  "cost":3000},
    3:{"name":"💎 Дрель",    "reward":1200, "cost":8000},
    4:{"name":"🤖 Авторобот","reward":3000, "cost":20000},
    5:{"name":"🚀 Квантовый","reward":8000, "cost":50000},
}

CRYPTO_MINING = {
    "ton":  {"name":"🔷 TON Майнинг", "symbol":"TON",  "cooldown":24,
             "levels":{1:{"reward":0.05,"cost_city":50000},   2:{"reward":0.1, "cost_city":200000},
                       3:{"reward":0.2, "cost_city":600000},   4:{"reward":0.35,"cost_city":1500000},
                       5:{"reward":0.5, "cost_city":4000000}}},
    "city": {"name":"🟡 CITY Майнинг","symbol":"CITY", "cooldown":12,
             "levels":{1:{"reward":10,"cost_coins":2000},2:{"reward":30,"cost_coins":8000},
                       3:{"reward":80,"cost_coins":25000},4:{"reward":200,"cost_coins":80000},
                       5:{"reward":500,"cost_coins":250000}}},
}

SLOT_SYMBOLS = ["🍋","🍒","🍇","💎","7️⃣","⭐"]
SLOT_PAYOUTS = {
    ("💎","💎","💎"):50000,("7️⃣","7️⃣","7️⃣"):30000,
    ("⭐","⭐","⭐"):20000, ("🍇","🍇","🍇"):5000,
    ("🍒","🍒","🍒"):2000, ("🍋","🍋","🍋"):1000,
}
DAILY_REWARDS = {1:500,2:1000,3:2000,4:3500,5:5000,6:7500,7:10000}
DAILY_MAX     = 15000

SHOP_ITEMS = {
    "vip_30":    {"name":"👑 VIP 30 дней",    "desc":"x2 доход со всего",      "stars":100,"days":30},
    "vip_7":     {"name":"👑 VIP 7 дней",     "desc":"x2 доход со всего",      "stars":30, "days":7},
    "boost_x3":  {"name":"🚀 Буст x3 24ч",   "desc":"x3 доход на 24 часа",    "stars":50, "hours":24},
    "boost_x2":  {"name":"⚡ Буст x2 12ч",   "desc":"x2 доход на 12 часов",   "stars":25, "hours":12},
    "coins_1m":  {"name":"💰 1,000,000 монет","desc":"Мгновенное пополнение",  "stars":75, "coins":1_000_000},
    "coins_500k":{"name":"💰 500,000 монет",  "desc":"Мгновенное пополнение",  "stars":40, "coins":500_000},
    "shield":    {"name":"🛡️ Щит 24ч",       "desc":"Защита от атак",         "stars":20, "shield_hours":24},
    "army_pack": {"name":"⚔️ Армейский пак",  "desc":"100 солдат + 50 рыцарей","stars":60, "army":True},
}

RANK_TITLES = [
    (0,"🪨 Новичок"),(10000,"🪵 Крестьянин"),(50000,"🔩 Ремесленник"),
    (200000,"🏠 Горожанин"),(1000000,"🏛️ Дворянин"),(5000000,"👑 Граф"),
    (20000000,"💎 Герцог"),(100000000,"🌟 Король"),(1000000000,"🚀 Император"),
]

# ─────────────── ЕЖЕДНЕВНЫЕ ЗАДАНИЯ ───────────────
DAILY_QUESTS = {
    "collect": {"name": "💰 Собрать доход",    "target": 1, "reward": 2000},
    "mine":    {"name": "⛏️ Добыть майнером",   "target": 1, "reward": 2500},
    "slot":    {"name": "🎰 Крутить слот",      "target": 1, "reward": 1500},
    "upgrade": {"name": "🏗️ Улучшить здание",   "target": 1, "reward": 3000},
    "attack":  {"name": "⚔️ Атаковать игрока",  "target": 1, "reward": 3500},
}
QUEST_ALL_BONUS = 5000  # бонус за выполнение ВСЕХ заданий дня

def get_rank(bal):
    rank = RANK_TITLES[0][1]
    for t,title in RANK_TITLES:
        if bal>=t: rank=title
    return rank

def get_next_rank(bal):
    for t,title in RANK_TITLES:
        if bal<t: return t,title
    return None,None

def progress_bar(cur,mx,l=10):
    f   = int((cur/mx)*l) if mx>0 else 0
    bar = "█"*f+"░"*(l-f)
    pct = int((cur/mx)*100) if mx>0 else 0
    return f"[{bar}] {pct}%"

def star_level(lvl,mx=5):
    return "⭐"*lvl+"☆"*(mx-lvl)

def format_coins(n):
    n=int(n)
    if n>=1_000_000_000_000: return f"{n/1_000_000_000_000:.2f}T"
    if n>=1_000_000_000:     return f"{n/1_000_000_000:.2f}B"
    if n>=1_000_000:         return f"{n/1_000_000:.2f}M"
    if n>=1_000:             return f"{n/1_000:.1f}K"
    return str(n)

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT,
        balance INTEGER DEFAULT 500,
        last_collect TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        referrer_id INTEGER DEFAULT NULL,
        vip INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        miner_level INTEGER DEFAULT 0,
        last_mine TIMESTAMP DEFAULT NULL,
        last_slot TIMESTAMP DEFAULT NULL,
        last_daily TIMESTAMP DEFAULT NULL,
        daily_streak INTEGER DEFAULT 0,
        last_attack TIMESTAMP DEFAULT NULL,
        shield_until TIMESTAMP DEFAULT NULL,
        clan_id INTEGER DEFAULT NULL
    )""")
    # ── миграция: добавляем колонки для срочного VIP и бустов ──
    for col, ddl in [("vip_until","TIMESTAMP DEFAULT NULL"),
                     ("boost_mult","REAL DEFAULT 1"),
                     ("boost_until","TIMESTAMP DEFAULT NULL")]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass
    c.execute("""CREATE TABLE IF NOT EXISTS buildings (
        user_id INTEGER, building_id TEXT, level INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, building_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS army (
        user_id INTEGER, unit_id TEXT, amount INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, unit_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS clans (
        clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, leader_id INTEGER,
        description TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, amount INTEGER, usdt REAL,
        wallet TEXT, status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS crypto_mining (
        user_id INTEGER, crypto_type TEXT,
        level INTEGER DEFAULT 0, balance REAL DEFAULT 0,
        last_mine TIMESTAMP DEFAULT NULL, total_mined REAL DEFAULT 0,
        PRIMARY KEY (user_id, crypto_type)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS quests (
        user_id INTEGER, quest_id TEXT, quest_date TEXT,
        progress INTEGER DEFAULT 0, claimed INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, quest_id, quest_date)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_progress (
        user_id INTEGER PRIMARY KEY,
        best_level INTEGER DEFAULT 0,
        total_city INTEGER DEFAULT 0,
        last_day TEXT DEFAULT NULL,
        day_earned INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS crypto_withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, crypto_type TEXT, amount REAL,
        address TEXT, memo TEXT DEFAULT '',
        status TEXT DEFAULT 'pending', tx_hash TEXT DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS wd_limits (
        user_id INTEGER, crypto_type TEXT, day TEXT,
        amount REAL DEFAULT 0,
        PRIMARY KEY (user_id, crypto_type, day)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('coin_to_usdt','0.00001')")
    c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('min_withdraw','50000')")
    c.execute("INSERT OR IGNORE INTO settings (key,value) VALUES ('referral_bonus','500')")
    conn.commit(); conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?",(uid,))
    row = c.fetchone(); conn.close(); return row

def create_user(uid, uname, ref_id=None):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    bal = OWNER_START_BAL if uid==OWNER_ID else 500
    c.execute("INSERT OR IGNORE INTO users (user_id,username,balance,referrer_id) VALUES (?,?,?,?)",(uid,uname,bal,ref_id))
    for b in BUILDINGS:
        lvl = 5 if uid==OWNER_ID else 0
        c.execute("INSERT OR IGNORE INTO buildings (user_id,building_id,level) VALUES (?,?,?)",(uid,b,lvl))
    for u in ARMY_UNITS:
        amt = 999999 if uid==OWNER_ID else 0
        c.execute("INSERT OR IGNORE INTO army (user_id,unit_id,amount) VALUES (?,?,?)",(uid,u,amt))
    if uid==OWNER_ID:
        c.execute("UPDATE users SET vip=1,miner_level=5 WHERE user_id=?",(uid,))
    conn.commit(); conn.close()

def get_buildings(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT building_id,level FROM buildings WHERE user_id=?",(uid,))
    rows = {r[0]:r[1] for r in c.fetchall()}; conn.close(); return rows

def get_army(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT unit_id,amount FROM army WHERE user_id=?",(uid,))
    rows = {r[0]:r[1] for r in c.fetchall()}; conn.close(); return rows

def get_army_power(uid,mode="attack"):
    army = get_army(uid)
    return sum(ARMY_UNITS.get(u,{}).get(mode,0)*a for u,a in army.items())

# ─────────────── VIP / БУСТЫ (срочные) ───────────────
def vip_active(uid):
    """True если игрок сейчас VIP (владелец — всегда; остальные — пока не истёк срок)."""
    if uid==OWNER_ID:
        return True
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT vip_until FROM users WHERE user_id=?",(uid,))
    row=c.fetchone(); conn.close()
    if row and row[0]:
        try:
            return datetime.now()<datetime.fromisoformat(row[0])
        except:
            return False
    return False

def get_boost(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT boost_mult,boost_until FROM users WHERE user_id=?",(uid,))
    row=c.fetchone(); conn.close()
    return row if row else (1,None)

def boost_mult_active(uid):
    bm,bu=get_boost(uid)
    if bu:
        try:
            if datetime.now()<datetime.fromisoformat(bu):
                return float(bm or 1)
        except:
            pass
    return 1.0

def income_mult(uid):
    """Множитель для ИГРОВЫХ монет: VIP (x2) * активный буст."""
    m = 2.0 if vip_active(uid) else 1.0
    return m * boost_mult_active(uid)

def crypto_mult(uid):
    """Множитель для крипто-майнинга: только VIP (x2). Бусты на крипту не влияют."""
    return 2.0 if vip_active(uid) else 1.0

def activate_vip(uid, days):
    """Включает/продлевает VIP. Если ещё активен — добавляет дни сверху."""
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT vip_until FROM users WHERE user_id=?",(uid,))
    row=c.fetchone(); base=datetime.now()
    if row and row[0]:
        try:
            cur=datetime.fromisoformat(row[0])
            if cur>base: base=cur
        except:
            pass
    until=(base+timedelta(days=days)).isoformat()
    c.execute("UPDATE users SET vip_until=? WHERE user_id=?",(until,uid))
    conn.commit(); conn.close(); return until

def activate_boost(uid, mult, hours):
    until=(datetime.now()+timedelta(hours=hours)).isoformat()
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE users SET boost_mult=?,boost_until=? WHERE user_id=?",(mult,until,uid))
    conn.commit(); conn.close()

def vip_status_text(uid):
    if uid==OWNER_ID:
        return "✅ (навсегда)"
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT vip_until FROM users WHERE user_id=?",(uid,))
    row=c.fetchone(); conn.close()
    if row and row[0]:
        try:
            until=datetime.fromisoformat(row[0])
            if datetime.now()<until:
                left=until-datetime.now(); d=left.days; h=int(left.seconds//3600)
                return f"✅ {d}д {h}ч" if d>0 else f"✅ {h}ч"
        except:
            pass
    return "❌"

def boost_status_text(uid):
    bm,bu=get_boost(uid)
    if bu:
        try:
            until=datetime.fromisoformat(bu)
            if datetime.now()<until:
                left=until-datetime.now()
                h=int(left.total_seconds()//3600); m=int((left.total_seconds()%3600)//60)
                return f"x{int(bm)} ({h}ч {m}мин)"
        except:
            pass
    return "—"

def is_vip(uid):
    return vip_active(uid)

def get_income_per_hour(uid):
    blds  = get_buildings(uid)
    total = sum(BUILDINGS[b]["income"][l] for b,l in blds.items())
    return int(total * income_mult(uid))

def collect_income(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance,last_collect FROM users WHERE user_id=?",(uid,))
    row = c.fetchone()
    if not row: conn.close(); return 0
    hours  = (datetime.now()-datetime.fromisoformat(row[1])).total_seconds()/3600
    earned = int(hours*get_income_per_hour(uid))
    if earned>0:
        c.execute("UPDATE users SET balance=balance+?,last_collect=? WHERE user_id=?",(earned,datetime.now().isoformat(),uid))
        conn.commit()
    conn.close(); return earned

def upgrade_building(uid,bid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT level FROM buildings WHERE user_id=? AND building_id=?",(uid,bid))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено"
    lvl = row[0]
    if lvl>=5: conn.close(); return False,"Максимальный уровень!"
    cost = BUILDINGS[bid]["levels"][lvl+1]
    c.execute("SELECT balance FROM users WHERE user_id=?",(uid,))
    if c.fetchone()[0]<cost: conn.close(); return False,f"Нужно {cost:,} 🪙"
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(cost,uid))
    c.execute("UPDATE buildings SET level=level+1 WHERE user_id=? AND building_id=?",(uid,bid))
    conn.commit(); conn.close(); return True,lvl+1

def add_coins(uid,amount):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amount,uid))
    conn.commit(); conn.close()

def get_setting(key):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?",(key,))
    row = c.fetchone(); conn.close()
    return row[0] if row else None

def set_setting(key,value):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",(key,str(value)))
    conn.commit(); conn.close()

def get_rate():
    val = get_setting("coin_to_usdt")
    return float(val) if val else DEFAULT_COIN_TO_USDT

def get_min_withdraw():
    val = get_setting("min_withdraw")
    return int(val) if val else 50_000

def get_owner_ton():
    val = get_setting("owner_ton_daily")
    try: return float(val) if val is not None else OWNER_TON_REWARD
    except: return OWNER_TON_REWARD

def do_mine(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT miner_level,last_mine FROM users WHERE user_id=?",(uid,))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено",0
    mlvl,last_mine = row
    if mlvl==0: conn.close(); return False,"no_miner",0
    if last_mine:
        diff = (datetime.now()-datetime.fromisoformat(last_mine)).total_seconds()/3600
        if diff<8:
            left=8-diff; h,m=int(left),int((left%1)*60)
            conn.close(); return False,f"⏳ Через {h}ч {m}мин",0
    reward = int(MINER_LEVELS[mlvl]["reward"] * income_mult(uid))
    c.execute("UPDATE users SET balance=balance+?,last_mine=? WHERE user_id=?",(reward,datetime.now().isoformat(),uid))
    conn.commit(); conn.close(); return True,"",reward

def upgrade_miner(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT miner_level,balance FROM users WHERE user_id=?",(uid,))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено"
    mlvl,bal = row
    if mlvl>=5: conn.close(); return False,"Максимальный уровень!"
    cost = MINER_LEVELS[mlvl]["cost"]
    if bal<cost: conn.close(); return False,f"Нужно {cost:,} 🪙"
    c.execute("UPDATE users SET miner_level=miner_level+1,balance=balance-? WHERE user_id=?",(cost,uid))
    conn.commit(); conn.close(); return True,mlvl+1

def init_crypto_mining(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    for ct in ["ton","city"]:
        c.execute("INSERT OR IGNORE INTO crypto_mining (user_id,crypto_type) VALUES (?,?)",(uid,ct))
    conn.commit(); conn.close()

def get_crypto_mining(uid,ct):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM crypto_mining WHERE user_id=? AND crypto_type=?",(uid,ct))
    row = c.fetchone(); conn.close(); return row

def do_crypto_mine(uid,ct):
    init_crypto_mining(uid)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT level,balance,last_mine FROM crypto_mining WHERE user_id=? AND crypto_type=?",(uid,ct))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено",0
    lvl,bal,last_mine = row
    is_owner_ton = (uid==OWNER_ID and ct=="ton")
    if lvl==0 and not is_owner_ton: conn.close(); return False,"no_miner",0
    cd = CRYPTO_MINING[ct]["cooldown"]
    if last_mine:
        diff=(datetime.now()-datetime.fromisoformat(last_mine)).total_seconds()/3600
        if diff<cd:
            left=cd-diff; h,m=int(left),int((left%1)*60)
            conn.close(); return False,f"⏳ Через {h}ч {m}мин",0
    if is_owner_ton:
        reward = get_owner_ton()
    else:
        reward = CRYPTO_MINING[ct]["levels"][lvl]["reward"] * crypto_mult(uid)
    c.execute("UPDATE crypto_mining SET balance=balance+?,last_mine=?,total_mined=total_mined+? WHERE user_id=? AND crypto_type=?",
              (reward,datetime.now().isoformat(),reward,uid,ct))
    conn.commit(); conn.close(); return True,"",reward

def upgrade_crypto_miner(uid,ct):
    init_crypto_mining(uid)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT level FROM crypto_mining WHERE user_id=? AND crypto_type=?",(uid,ct))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено"
    lvl = row[0]
    if lvl>=5: conn.close(); return False,"Максимальный уровень!"
    nl   = lvl+1
    info = CRYPTO_MINING[ct]
    cost = info["levels"][nl].get("cost_city",info["levels"][nl].get("cost_coins",0))
    c.execute("SELECT balance FROM users WHERE user_id=?",(uid,))
    if c.fetchone()[0]<cost: conn.close(); return False,f"Нужно {format_coins(cost)} 🪙"
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(cost,uid))
    c.execute("UPDATE crypto_mining SET level=? WHERE user_id=? AND crypto_type=?",(nl,uid,ct))
    conn.commit(); conn.close(); return True,nl

def do_slot(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT last_slot FROM users WHERE user_id=?",(uid,))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено",None,0
    last_slot = row[0]
    if last_slot:
        diff=timedelta(hours=24)-(datetime.now()-datetime.fromisoformat(last_slot))
        if diff.total_seconds()>0:
            h=int(diff.total_seconds()//3600); m=int((diff.total_seconds()%3600)//60)
            conn.close(); return False,f"⏳ Через {h}ч {m}мин",None,0
    s1,s2,s3=[random.choice(SLOT_SYMBOLS) for _ in range(3)]
    combo=(s1,s2,s3); reward=SLOT_PAYOUTS.get(combo,0)
    if s1==s2 or s2==s3 or s1==s3: reward=max(reward,100)
    c.execute("UPDATE users SET last_slot=?,balance=balance+? WHERE user_id=?",(datetime.now().isoformat(),reward,uid))
    conn.commit(); conn.close(); return True,"",combo,reward

def do_daily(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT last_daily,daily_streak FROM users WHERE user_id=?",(uid,))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено",0,0
    last_daily,streak = row
    now = datetime.now()
    if last_daily:
        diff=(now-datetime.fromisoformat(last_daily)).total_seconds()/3600
        if diff<24:
            left=24-diff; h,m=int(left),int((left%1)*60)
            conn.close(); return False,f"⏳ Через {h}ч {m}мин",streak,0
        if diff>48: streak=0
    streak=min(streak+1,7)
    reward=DAILY_REWARDS.get(streak,DAILY_MAX)
    if vip_active(uid): reward=int(reward*1.5)
    c.execute("UPDATE users SET last_daily=?,daily_streak=?,balance=balance+? WHERE user_id=?",(now.isoformat(),streak,reward,uid))
    conn.commit(); conn.close(); return True,"",streak,reward

def do_attack(atk_id,def_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT last_attack,balance FROM users WHERE user_id=?",(atk_id,))
    row = c.fetchone()
    if not row: conn.close(); return False,"Не найдено",0
    last_atk,atk_bal = row
    if last_atk:
        diff=(datetime.now()-datetime.fromisoformat(last_atk)).total_seconds()/3600
        if diff<4:
            left=4-diff; h,m=int(left),int((left%1)*60)
            conn.close(); return False,f"⏳ Через {h}ч {m}мин",0
    c.execute("SELECT shield_until,balance FROM users WHERE user_id=?",(def_id,))
    def_row=c.fetchone()
    if not def_row: conn.close(); return False,"Игрок не найден",0
    shield_until,def_bal=def_row
    if shield_until and datetime.now()<datetime.fromisoformat(shield_until):
        conn.close(); return False,"🛡️ У игрока активен щит!",0
    atk_pow=get_army_power(atk_id,"attack")+random.randint(0,50)
    def_pow=get_army_power(def_id,"defense")+random.randint(0,50)
    c.execute("UPDATE users SET last_attack=? WHERE user_id=?",(datetime.now().isoformat(),atk_id))
    if atk_pow>def_pow:
        stolen=min(int(def_bal*random.uniform(0.05,0.10)),def_bal)
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(stolen,def_id))
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(stolen,atk_id))
        conn.commit(); conn.close(); return True,"win",stolen
    else:
        penalty=int(atk_bal*0.02)
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(penalty,atk_id))
        conn.commit(); conn.close(); return True,"loss",penalty

def buy_shield(uid):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?",(uid,))
    if c.fetchone()[0]<2000: conn.close(); return False,"Нужно 2000 🪙"
    c.execute("UPDATE users SET balance=balance-2000 WHERE user_id=?",(uid,))
    until=(datetime.now()+timedelta(hours=12)).isoformat()
    c.execute("UPDATE users SET shield_until=? WHERE user_id=?",(until,uid))
    conn.commit(); conn.close(); return True,""

def activate_shield(uid,hours):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    until=(datetime.now()+timedelta(hours=hours)).isoformat()
    c.execute("UPDATE users SET shield_until=? WHERE user_id=?",(until,uid))
    conn.commit(); conn.close()

def buy_army_unit(uid,unit_id,amount):
    unit=ARMY_UNITS.get(unit_id)
    if not unit: return False,"Юнит не найден"
    cost=unit["cost"]*amount
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?",(uid,))
    if c.fetchone()[0]<cost: conn.close(); return False,f"Нужно {cost:,} 🪙"
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(cost,uid))
    c.execute("UPDATE army SET amount=amount+? WHERE user_id=? AND unit_id=?",(amount,uid,unit_id))
    conn.commit(); conn.close(); return True,cost

def create_clan(uid,name,desc=""):
    conn=sqlite3.connect(DB); c=conn.cursor()
    try:
        c.execute("INSERT INTO clans (name,leader_id,description) VALUES (?,?,?)",(name,uid,desc))
        clan_id=c.lastrowid
        c.execute("UPDATE users SET clan_id=? WHERE user_id=?",(clan_id,uid))
        conn.commit(); conn.close(); return True,clan_id
    except:
        conn.close(); return False,"Клан уже существует!"

def join_clan(uid,clan_id):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT clan_id FROM users WHERE user_id=?",(uid,))
    row=c.fetchone()
    if row and row[0]: conn.close(); return False,"Ты уже в клане!"
    c.execute("SELECT clan_id FROM clans WHERE clan_id=?",(clan_id,))
    if not c.fetchone(): conn.close(); return False,"Клан не найден"
    c.execute("UPDATE users SET clan_id=? WHERE user_id=?",(clan_id,uid))
    conn.commit(); conn.close(); return True,""

def leave_clan(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE users SET clan_id=NULL WHERE user_id=?",(uid,))
    conn.commit(); conn.close(); return True,""

def get_clan_info(clan_id):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT * FROM clans WHERE clan_id=?",(clan_id,))
    clan=c.fetchone()
    if not clan: conn.close(); return None,[]
    c.execute("SELECT user_id,username,balance FROM users WHERE clan_id=? ORDER BY balance DESC",(clan_id,))
    members=c.fetchall(); conn.close(); return clan,members

def get_clan_list():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("""SELECT c.clan_id,c.name,COUNT(u.user_id),SUM(u.balance)
                 FROM clans c LEFT JOIN users u ON u.clan_id=c.clan_id
                 GROUP BY c.clan_id ORDER BY SUM(u.balance) DESC LIMIT 8""")
    rows=c.fetchall(); conn.close(); return rows

def get_referrals(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referrer_id=?",(uid,))
    cnt=c.fetchone()[0]; conn.close(); return cnt

def get_top_users():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id,username,balance FROM users ORDER BY balance DESC LIMIT 10")
    rows=c.fetchall(); conn.close(); return rows

def get_all_users():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT user_id FROM users WHERE banned=0")
    rows=[r[0] for r in c.fetchall()]; conn.close(); return rows

def create_withdrawal(uid,amount,wallet):
    usdt=round(amount*get_rate(),4)
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?",(amount,uid))
    c.execute("INSERT INTO withdrawals (user_id,amount,usdt,wallet) VALUES (?,?,?,?)",(uid,amount,usdt,wallet))
    conn.commit(); conn.close(); return usdt

def get_pending_withdrawals():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id,user_id,amount,usdt,wallet FROM withdrawals WHERE status='pending'")
    rows=c.fetchall(); conn.close(); return rows

def approve_withdrawal(wid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE withdrawals SET status='approved' WHERE id=?",(wid,))
    conn.commit(); conn.close()

def reject_withdrawal(wid,uid,amount):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE withdrawals SET status='rejected' WHERE id=?",(wid,))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(amount,uid))
    conn.commit(); conn.close()

def ban_user(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE users SET banned=1 WHERE user_id=?",(uid,))
    conn.commit(); conn.close()

# ─────────────── КРИПТО-ВЫВОДЫ (TON / CITY) ───────────────
def create_crypto_withdrawal(uid, ct, amount, address, memo=""):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE crypto_mining SET balance=balance-? WHERE user_id=? AND crypto_type=?",(amount,uid,ct))
    c.execute("INSERT INTO crypto_withdrawals (user_id,crypto_type,amount,address,memo) VALUES (?,?,?,?,?)",
              (uid,ct,amount,address,memo))
    wid=c.lastrowid; conn.commit(); conn.close(); return wid

def get_wd_today(uid, ct):
    today=datetime.now().strftime("%Y-%m-%d")
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT amount FROM wd_limits WHERE user_id=? AND crypto_type=? AND day=?",(uid,ct,today))
    row=c.fetchone(); conn.close()
    return row[0] if row else 0.0

def add_wd_today(uid, ct, amt):
    today=datetime.now().strftime("%Y-%m-%d")
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO wd_limits (user_id,crypto_type,day,amount) VALUES (?,?,?,0)",(uid,ct,today))
    c.execute("UPDATE wd_limits SET amount=amount+? WHERE user_id=? AND crypto_type=? AND day=?",(amt,uid,ct,today))
    conn.commit(); conn.close()

def sub_wd_today(uid, ct, amt):
    today=datetime.now().strftime("%Y-%m-%d")
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE wd_limits SET amount=MAX(0,amount-?) WHERE user_id=? AND crypto_type=? AND day=?",(amt,uid,ct,today))
    conn.commit(); conn.close()

def get_crypto_withdrawal(wid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id,user_id,crypto_type,amount,address,memo,status FROM crypto_withdrawals WHERE id=?",(wid,))
    row=c.fetchone(); conn.close(); return row

def get_pending_crypto_withdrawals():
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT id,user_id,crypto_type,amount,address,memo FROM crypto_withdrawals WHERE status='pending'")
    rows=c.fetchall(); conn.close(); return rows

def set_crypto_withdrawal_status(wid, status, tx_hash=None):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE crypto_withdrawals SET status=?,tx_hash=? WHERE id=?",(status,tx_hash,wid))
    conn.commit(); conn.close()

def refund_crypto_withdrawal(wid):
    row=get_crypto_withdrawal(wid)
    if not row: return False
    _,uid,ct,amount,_,_,status=row
    if status!="pending": return False
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("UPDATE crypto_mining SET balance=balance+? WHERE user_id=? AND crypto_type=?",(amount,uid,ct))
    c.execute("UPDATE crypto_withdrawals SET status='rejected' WHERE id=?",(wid,))
    conn.commit(); conn.close()
    sub_wd_today(uid, ct, amount)
    return True

async def send_ton_onchain(address, amount, memo=""):
    """
    Реальная отправка TON с горячего кошелька. Включается только при TON_AUTOSEND=1
    и заданном TON_WALLET_MNEMONIC. Требует: pip install tonutils
    ВАЖНО:
      • сначала протестируй на testnet (TON_NETWORK=testnet);
      • версия кошелька (TON_WALLET_VERSION) должна совпадать с твоим реальным:
        Tonkeeper по умолчанию = v5r1 (W5). Из одной сид-фразы v4r2 и v5r1
        дают РАЗНЫЕ адреса — иначе бот возьмёт пустой адрес.
    Возвращает tx_hash (str) или бросает исключение.
    """
    from tonutils.client import ToncenterV3Client
    from tonutils.wallet import WalletV4R2, WalletV5R1
    is_testnet = (TON_NETWORK.lower() == "testnet")
    client = ToncenterV3Client(
        api_key=(TONCENTER_KEY or None),
        is_testnet=is_testnet,
        rps=1, max_retries=1,
    )
    ver = TON_WALLET_VERSION.lower()
    WalletCls = WalletV5R1 if ver in ("v5", "v5r1", "w5") else WalletV4R2
    wallet, _pub, _priv, _mn = WalletCls.from_mnemonic(client, TON_MNEMONIC.split())
    tx_hash = await wallet.transfer(destination=address, amount=float(amount), body=memo or "")
    return str(tx_hash)

# ─────────────── ЛОГИКА ЗАДАНИЙ ───────────────
def _today():
    return datetime.now().strftime("%Y-%m-%d")

def quest_progress(uid, qid, amount=1):
    if qid not in DAILY_QUESTS: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    today=_today()
    c.execute("INSERT OR IGNORE INTO quests (user_id,quest_id,quest_date,progress,claimed) VALUES (?,?,?,0,0)",(uid,qid,today))
    c.execute("UPDATE quests SET progress=progress+? WHERE user_id=? AND quest_id=? AND quest_date=?",(amount,uid,qid,today))
    conn.commit(); conn.close()

def get_quests(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    today=_today(); result={}
    for qid in DAILY_QUESTS:
        c.execute("SELECT progress,claimed FROM quests WHERE user_id=? AND quest_id=? AND quest_date=?",(uid,qid,today))
        row=c.fetchone()
        result[qid]={"progress":row[0] if row else 0,"claimed":row[1] if row else 0}
    conn.close(); return result

def claim_quest(uid, qid):
    if qid not in DAILY_QUESTS: return False,"Задание не найдено",0
    q=DAILY_QUESTS[qid]
    conn=sqlite3.connect(DB); c=conn.cursor()
    today=_today()
    c.execute("SELECT progress,claimed FROM quests WHERE user_id=? AND quest_id=? AND quest_date=?",(uid,qid,today))
    row=c.fetchone()
    progress=row[0] if row else 0; claimed=row[1] if row else 0
    if claimed: conn.close(); return False,"Уже получено",0
    if progress<q["target"]: conn.close(); return False,"Задание не выполнено",0
    c.execute("INSERT OR IGNORE INTO quests (user_id,quest_id,quest_date,progress,claimed) VALUES (?,?,?,?,0)",(uid,qid,today,progress))
    c.execute("UPDATE quests SET claimed=1 WHERE user_id=? AND quest_id=? AND quest_date=?",(uid,qid,today))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(q["reward"],uid))
    conn.commit(); conn.close(); return True,"",q["reward"]

def claim_all_bonus(uid):
    qs=get_quests(uid)
    if not all(qs[qid]["claimed"] for qid in DAILY_QUESTS):
        return False,"Сначала забери все задания",0
    conn=sqlite3.connect(DB); c=conn.cursor()
    today=_today()
    c.execute("SELECT claimed FROM quests WHERE user_id=? AND quest_id='_allbonus' AND quest_date=?",(uid,today))
    row=c.fetchone()
    if row and row[0]: conn.close(); return False,"Бонус дня уже получен",0
    c.execute("INSERT OR IGNORE INTO quests (user_id,quest_id,quest_date,progress,claimed) VALUES (?,?,?,1,1)",(uid,"_allbonus",today))
    c.execute("UPDATE quests SET claimed=1 WHERE user_id=? AND quest_id='_allbonus' AND quest_date=?",(uid,today))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?",(QUEST_ALL_BONUS,uid))
    conn.commit(); conn.close(); return True,"",QUEST_ALL_BONUS

# ─────────────── НАГРАДЫ ИЗ ИГРЫ (считает СЕРВЕР, анти-чит) ───────────────
GAME_MAX_LEVELS_PER_CLAIM = 12      # за один заход начисляем не больше N новых уровней
GAME_DAILY_CITY_CAP       = 50_000  # дневной лимит CITY из игры

def game_level_reward(L):
    """Сколько CITY даём за ПЕРВОЕ прохождение уровня L. Формулу контролирует бот."""
    return 100 + L*40

def game_get(uid):
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO game_progress (user_id) VALUES (?)",(uid,))
    c.execute("SELECT best_level,total_city,last_day,day_earned FROM game_progress WHERE user_id=?",(uid,))
    row=c.fetchone(); conn.commit(); conn.close()
    return row if row else (0,0,None,0)

def game_claim(uid, claimed_level):
    """Начисляет CITY за новые уровни (выводимый, с дневным лимитом на вывод).
    Сумму считает сервер — клиент лишь сообщает уровень."""
    try: claimed_level=int(claimed_level)
    except: claimed_level=0
    if claimed_level<1: return 0,0,"badlevel"
    init_crypto_mining(uid)
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("INSERT OR IGNORE INTO game_progress (user_id) VALUES (?)",(uid,))
    c.execute("SELECT best_level,last_day,day_earned FROM game_progress WHERE user_id=?",(uid,))
    best,last_day,day_earned=c.fetchone()
    today=datetime.now().strftime("%Y-%m-%d")
    if last_day!=today: day_earned=0
    new_top=min(claimed_level, best+GAME_MAX_LEVELS_PER_CLAIM)
    if new_top<=best:
        conn.close(); return 0,best,"replay"
    reward=sum(game_level_reward(L) for L in range(best+1,new_top+1))
    remaining=max(0,GAME_DAILY_CITY_CAP-day_earned)
    capped=min(reward,remaining)
    status="capped" if capped<reward else "ok"
    c.execute("UPDATE crypto_mining SET balance=balance+?,total_mined=total_mined+? WHERE user_id=? AND crypto_type='city'",
              (capped,capped,uid))
    c.execute("UPDATE game_progress SET best_level=?,total_city=total_city+?,last_day=?,day_earned=? WHERE user_id=?",
              (new_top,capped,today,day_earned+capped,uid))
    conn.commit(); conn.close()
    return capped,new_top,status

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher()
logging.basicConfig(level=logging.INFO)

def game_url_for(uid=None):
    """Ссылка на игру с прогрессом игрока. Бот передаёт сохранённый уровень,
    чтобы при очистке кэша Telegram прогресс восстановился с сервера."""
    if uid is None:
        return GAME_URL
    try:
        prog = game_get(uid); best = prog[0] if prog else 0
    except Exception:
        best = 0
    sep = "&" if "?" in GAME_URL else "?"
    return f"{GAME_URL}{sep}uid={uid}&lvl={best}"

def main_menu(uid=None):
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🏙️ Мой город"),  KeyboardButton(text="🏗️ Здания")],
        [KeyboardButton(text="💰 Собрать"),     KeyboardButton(text="⛏️ Майнинг")],
        [KeyboardButton(text="💎 Крипто"),      KeyboardButton(text="🎰 Слот")],
        [KeyboardButton(text="🎁 Бонус"),       KeyboardButton(text="⚔️ Атака")],
        [KeyboardButton(text="📋 Задания"),     KeyboardButton(text="🏰 Клан")],
        [KeyboardButton(text="🛒 Магазин"),     KeyboardButton(text="💸 Вывод")],
        [KeyboardButton(text="👥 Рефералы"),    KeyboardButton(text="🏆 Рейтинг")],
        [KeyboardButton(text="ℹ️ Помощь")],
        [KeyboardButton(text="🎮 ИГРАТЬ В МАТЧ-3",web_app=types.WebAppInfo(url=game_url_for(uid)))],
    ],resize_keyboard=True)

def buildings_kb(uid):
    blds=get_buildings(uid)
    btns=[[InlineKeyboardButton(text=f"{BUILDINGS[b]['name']} {star_level(blds.get(b,0))}",callback_data=f"bld_{b}")] for b in BUILDINGS]
    return InlineKeyboardMarkup(inline_keyboard=btns)

def miner_kb(uid):
    user=get_user(uid); mlvl=user[8]; btns=[]
    if mlvl<5:
        cost=MINER_LEVELS[mlvl]["cost"]; name=MINER_LEVELS[mlvl+1]["name"]
        btns.append([InlineKeyboardButton(text=f"⬆️ {name} — {cost:,} 🪙",callback_data="mine_upgrade")])
    if mlvl>0:
        btns.append([InlineKeyboardButton(text="⛏️ Добыть монеты!",callback_data="mine_now")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def quests_kb(uid):
    qs=get_quests(uid); btns=[]
    for qid,q in DAILY_QUESTS.items():
        st=qs[qid]; done=st["progress"]>=q["target"]
        if st["claimed"]:
            btns.append([InlineKeyboardButton(text=f"✅ {q['name']} — получено",callback_data="quest_noop")])
        elif done:
            btns.append([InlineKeyboardButton(text=f"🎁 {q['name']} — забрать {format_coins(q['reward'])} 🪙",callback_data=f"qclaim_{qid}")])
        else:
            btns.append([InlineKeyboardButton(text=f"⏳ {q['name']} ({st['progress']}/{q['target']})",callback_data="quest_noop")])
    if all(qs[qid]["claimed"] for qid in DAILY_QUESTS):
        btns.append([InlineKeyboardButton(text=f"🌟 Забрать бонус дня +{format_coins(QUEST_ALL_BONUS)} 🪙",callback_data="qclaim_all")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика",        callback_data="adm_stats")],
        [InlineKeyboardButton(text="💸 Заявки на вывод",   callback_data="adm_withdrawals")],
        [InlineKeyboardButton(text="💎 Крипто-заявки",     callback_data="adm_cwd")],
        [InlineKeyboardButton(text="📢 Рассылка",          callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💱 Управление курсом", callback_data="adm_rates")],
    ])

def rates_kb():
    rate=get_rate(); min_w=get_min_withdraw()
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💱 Курс: 1000🪙={round(rate*1000,4)}$ | Изменить",callback_data="adm_setrate")],
        [InlineKeyboardButton(text=f"📉 Мин.вывод: {format_coins(min_w)}🪙 | Изменить",callback_data="adm_setminw")],
        [InlineKeyboardButton(text="🔙 Назад",callback_data="adm_back")],
    ])

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    uid=msg.from_user.id; uname=msg.from_user.username or msg.from_user.first_name
    ref_id=None; parts=msg.text.split()
    if len(parts)>1:
        try:
            ref_id=int(parts[1])
            if ref_id==uid: ref_id=None
        except: pass
    if not get_user(uid):
        create_user(uid,uname,ref_id)
        if ref_id and get_user(ref_id):
            add_coins(ref_id,500)
            try: await bot.send_message(ref_id,"🎉 Новый игрок по твоей ссылке! *+500* 🪙",parse_mode="Markdown")
            except: pass
    user=get_user(uid); rank=get_rank(user[2])
    vip_b="  👑 VIP" if vip_active(uid) else ""; crown="\n🔱 *ВЛАДЕЛЕЦ ИГРЫ*" if uid==OWNER_ID else ""
    await msg.answer(
        f"🌆✨ *CITY EMPIRE* ✨🌆{crown}\n"
        f"{'─'*28}\n"
        f"👋 Привет, *{uname}*!{vip_b}\n"
        f"{'─'*28}\n"
        f"💰 Баланс: *{format_coins(user[2])}* 🪙\n"
        f"📈 Доход:  *{format_coins(get_income_per_hour(uid))}* 🪙/час\n"
        f"🏅 Ранг:   *{rank}*\n"
        f"{'─'*28}\n"
        f"🏙️ Строй • ⚔️ Воюй • 💎 Майни • 💸 Выводи",
        parse_mode="Markdown",reply_markup=main_menu(uid)
    )

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return await msg.answer("❌ Нет доступа.")
    await msg.answer("👑 *ПАНЕЛЬ ВЛАДЕЛЬЦА*\n"+"─"*28,parse_mode="Markdown",reply_markup=admin_kb())

@dp.message(lambda m: m.text=="🏙️ Мой город")
async def my_city(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    if not user: return
    rank=get_rank(user[2]); nxt_t,nxt_n=get_next_rank(user[2])
    pb=f"\n📊 До *{nxt_n}*: {progress_bar(user[2],nxt_t)}" if nxt_t else ""
    sh="❌"
    if user[14]:
        su=datetime.fromisoformat(user[14])
        if datetime.now()<su: sh=f"✅ {int((su-datetime.now()).total_seconds()//3600)}ч"
    clan_name="—"
    if user[15]:
        clan,_=get_clan_info(user[15])
        if clan: clan_name=clan[1]
    await msg.answer(
        f"🏙️ *МОЙ ГОРОД*\n{'═'*28}\n"
        f"🏅 Ранг: *{rank}*{pb}\n{'─'*28}\n"
        f"💰 Баланс:    *{format_coins(user[2])}* 🪙\n"
        f"📈 Доход/час: *{format_coins(get_income_per_hour(uid))}* 🪙\n"
        f"💵 В USDT:    *{round(user[2]*get_rate(),4)}*\n{'─'*28}\n"
        f"⛏️ Майнер:    *{MINER_LEVELS[user[8]]['name']}*\n"
        f"⚔️ Атака:     *{get_army_power(uid,'attack')}*\n"
        f"🛡️ Защита:    *{get_army_power(uid,'defense')}*  {sh}\n"
        f"🏰 Клан:      *{clan_name}*\n"
        f"👥 Рефералы:  *{get_referrals(uid)}*\n"
        f"👑 VIP:       {vip_status_text(uid)}\n"
        f"🚀 Буст:      {boost_status_text(uid)}\n{'═'*28}",
        parse_mode="Markdown"
    )

@dp.message(lambda m: m.text=="🏗️ Здания")
async def show_buildings(msg: types.Message):
    await msg.answer("🏗️ *ЗДАНИЯ* — нажми чтобы улучшить:",parse_mode="Markdown",reply_markup=buildings_kb(msg.from_user.id))

@dp.message(lambda m: m.text=="💰 Собрать")
async def collect(msg: types.Message):
    uid=msg.from_user.id; earned=collect_income(uid); user=get_user(uid)
    if earned==0:
        await msg.answer(f"⏳ *Монеты копятся...*\n💰 Баланс: *{format_coins(user[2])}* 🪙",parse_mode="Markdown")
    else:
        quest_progress(uid,"collect")
        await msg.answer(
            f"✅ *СОБРАНО!*\n{'═'*28}\n"
            f"🎉 +*{format_coins(earned)}* 🪙\n"
            f"💰 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}",
            parse_mode="Markdown"
        )

@dp.message(lambda m: m.text=="⛏️ Майнинг")
async def mining_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid); mlvl=user[8]
    info=MINER_LEVELS[mlvl]; rwd=int(info['reward']*income_mult(uid))
    text=(f"⛏️ *МАЙНИНГ*\n{'═'*28}\n"
          f"🔧 Майнер: *{info['name']}*\n"
          f"📊 Уровень: {progress_bar(mlvl,5)}\n"
          f"💰 Награда: *{format_coins(rwd)}* 🪙\n⏱️ Кулдаун: *8ч*\n")
    if mlvl<5:
        nxt=MINER_LEVELS[mlvl+1]
        text+=(f"{'─'*28}\n⬆️ Следующий: *{nxt['name']}*\n"
               f"💰 Награда: *{nxt['reward']:,}* 🪙\n💸 Цена: *{info['cost']:,}* 🪙\n")
    text+=f"{'─'*28}\n💼 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}"
    await msg.answer(text,parse_mode="Markdown",reply_markup=miner_kb(uid))

@dp.message(lambda m: m.text=="💎 Крипто")
async def crypto_menu(msg: types.Message):
    uid=msg.from_user.id; init_crypto_mining(uid); user=get_user(uid)
    ton=get_crypto_mining(uid,"ton"); city_m=get_crypto_mining(uid,"city")
    ton_lvl=ton[2] if ton else 0; ton_bal=ton[3] if ton else 0
    city_lvl=city_m[2] if city_m else 0; city_bal=city_m[3] if city_m else 0
    cm=crypto_mult(uid)
    ton_rwd=CRYPTO_MINING["ton"]["levels"][ton_lvl]["reward"]*cm if ton_lvl>0 else 0
    if uid==OWNER_ID: ton_rwd=get_owner_ton()
    city_rwd=CRYPTO_MINING["city"]["levels"][city_lvl]["reward"]*cm if city_lvl>0 else 0
    text=(f"💎 *КРИПТО-МАЙНИНГ*\n{'═'*28}\n"
          f"🔷 *TON Майнер* {star_level(ton_lvl)}\n"
          f"📊 {progress_bar(ton_lvl,5)}\n"
          f"💰 Добыча: *{round(ton_rwd,3)} TON* / 24ч\n"
          f"💼 Баланс: *{round(ton_bal,6)} TON*\n")
    if ton_lvl<5: text+=f"⬆️ Апгрейд: *{format_coins(CRYPTO_MINING['ton']['levels'][ton_lvl+1]['cost_city'])}* 🪙\n"
    text+=(f"{'─'*28}\n🟡 *CITY Майнер* {star_level(city_lvl)}\n"
           f"📊 {progress_bar(city_lvl,5)}\n"
           f"💰 Добыча: *{city_rwd} CITY* / 12ч\n"
           f"💼 Баланс: *{round(city_bal,2)} CITY*\n")
    if city_lvl<5: text+=f"⬆️ Апгрейд: *{format_coins(CRYPTO_MINING['city']['levels'][city_lvl+1]['cost_coins'])}* 🪙\n"
    text+=(f"{'─'*28}\n👑 VIP = x2 добыча!\n"
           f"💸 Лимит вывода: *{int(CITY_DAILY_WD_CAP)} CITY* / *{TON_DAILY_WD_CAP} TON* в сутки\n{'═'*28}")
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔷 Добыть TON",   callback_data="cmine_ton"),
         InlineKeyboardButton(text="🟡 Добыть CITY",  callback_data="cmine_city")],
        [InlineKeyboardButton(text="⬆️ Апгрейд TON",  callback_data="cupgrade_ton"),
         InlineKeyboardButton(text="⬆️ Апгрейд CITY", callback_data="cupgrade_city")],
        [InlineKeyboardButton(text="💸 Вывести TON",  callback_data="cwithdraw_ton"),
         InlineKeyboardButton(text="💸 Вывести CITY", callback_data="cwithdraw_city")],
    ])
    await msg.answer(text,parse_mode="Markdown",reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("cmine_"))
async def crypto_mine_cb(call: types.CallbackQuery):
    uid=call.from_user.id; ct=call.data.split("_",1)[1]
    ok,err,reward=do_crypto_mine(uid,ct); info=CRYPTO_MINING[ct]
    if ok:
        row=get_crypto_mining(uid,ct); bal=row[3] if row else 0
        await call.answer(f"✅ Добыто {round(reward,3)} {info['symbol']}!",show_alert=True)
        await call.message.edit_text(
            f"{'🔷' if ct=='ton' else '🟡'} *ДОБЫЧА УСПЕШНА!*\n{'═'*28}\n"
            f"💰 Добыто: *+{round(reward,3)} {info['symbol']}*\n"
            f"💼 Баланс: *{round(bal,6)} {info['symbol']}*\n"
            f"⏳ Следующая через *{info['cooldown']}ч*\n{'═'*28}",
            parse_mode="Markdown",reply_markup=call.message.reply_markup
        )
    else: await call.answer(err,show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("cupgrade_"))
async def crypto_upgrade_cb(call: types.CallbackQuery):
    uid=call.from_user.id; ct=call.data.split("_",1)[1]
    ok,result=upgrade_crypto_miner(uid,ct); info=CRYPTO_MINING[ct]
    if ok:
        lvl=result; reward=info["levels"][lvl]["reward"]
        await call.answer(f"✅ Майнер улучшен до {lvl} уровня!",show_alert=True)
        await call.message.edit_text(
            f"🎉 *МАЙНЕР УЛУЧШЕН!*\n{'═'*28}\n"
            f"{'🔷' if ct=='ton' else '🟡'} {info['name']}\n"
            f"📊 Уровень: *{lvl}/5* {star_level(lvl)}\n"
            f"💰 Добыча: *{reward} {info['symbol']}*\n{'═'*28}",
            parse_mode="Markdown",reply_markup=call.message.reply_markup
        )
    else: await call.answer(f"❌ {result}",show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("cwithdraw_"))
async def crypto_withdraw_prompt(call: types.CallbackQuery):
    uid=call.from_user.id; ct=call.data.split("_",1)[1]
    info=CRYPTO_MINING[ct]; row=get_crypto_mining(uid,ct); bal=row[3] if row else 0
    min_w=TON_MIN_WD if ct=="ton" else CITY_MIN_WD
    cap=TON_DAILY_WD_CAP if ct=="ton" else CITY_DAILY_WD_CAP
    used=get_wd_today(uid,ct)
    # TON вывод только для VIP (если включено)
    if ct=="ton" and TON_VIP_ONLY and not is_vip(uid):
        await call.answer(
            "❌ Вывод TON только для VIP игроков!\n\nКупи VIP в 🛒 Магазине!",
            show_alert=True
        )
        return
    if ct=="ton":
        extra=(f"{'─'*28}\n"
               f"🏦 Биржи с TON: Binance, OKX, Bybit,\n"
               f"   KuCoin, Bitget, Gate.io, Kraken\n"
               f"📱 Или @wallet прямо в Telegram\n"
               f"🌐 Сеть при выводе: *TON*\n"
               f"⚠️ Для биржи MEMO/комментарий ОБЯЗАТЕЛЕН,\n"
               f"   иначе монеты потеряются!\n"
               f"{'─'*28}\n"
               f"На биржу:\n`/cwithdraw ton АДРЕС МЕМО`\n"
               f"На свой кошелёк (без MEMO):\n`/cwithdraw ton АДРЕС`\n")
    else:
        extra=(f"{'─'*28}\n"
               f"ℹ️ CITY на биржах нет.\n"
               f"Выводи на свой TON-кошелёк, затем\n"
               f"меняй CITY→TON на DeDust.io или STON.fi.\n"
               f"{'─'*28}\n"
               f"Команда:\n`/cwithdraw city АДРЕС`\n")
    await call.message.answer(
        f"💸 *Вывод {info['symbol']}*\n{'═'*28}\n"
        f"💼 Баланс: *{round(bal,6)} {info['symbol']}*\n"
        f"📌 Минимум: *{min_w} {info['symbol']}*\n"
        f"📊 Лимит: *{cap} {info['symbol']}* / сутки (сегодня {round(used,6)})\n"
        f"{extra}{'═'*28}",
        parse_mode="Markdown"
    )
    await call.answer()

@dp.message(Command("cwithdraw"))
async def crypto_withdraw_cmd(msg: types.Message):
    uid=msg.from_user.id; parts=msg.text.split(maxsplit=3)
    if len(parts)<3:
        return await msg.answer(
            "Формат: `/cwithdraw ton АДРЕС МЕМО`\n"
            "Для биржи MEMO обязателен!\n"
            "Для своего кошелька: `/cwithdraw ton АДРЕС`",
            parse_mode="Markdown")
    ct=parts[1].lower(); wallet=parts[2]; memo=parts[3] if len(parts)>3 else ""
    if ct not in ["ton","city"]:
        return await msg.answer("❌ Тип: `ton` или `city`",parse_mode="Markdown")
    # TON вывод только для VIP (если включено)
    if ct=="ton" and TON_VIP_ONLY and not is_vip(uid):
        return await msg.answer(
            f"❌ *Вывод TON только для VIP!*\n{'═'*28}\n"
            f"👑 Купи VIP в 🛒 Магазине\n"
            f"💎 VIP 7 дней — 30 ⭐\n"
            f"💎 VIP 30 дней — 100 ⭐\n{'═'*28}",
            parse_mode="Markdown"
        )
    info=CRYPTO_MINING[ct]; row=get_crypto_mining(uid,ct); bal=row[3] if row else 0
    min_w=TON_MIN_WD if ct=="ton" else CITY_MIN_WD
    cap = TON_DAILY_WD_CAP if ct=="ton" else CITY_DAILY_WD_CAP
    used = get_wd_today(uid, ct)
    remaining = max(0.0, cap - used)
    if remaining <= 0:
        return await msg.answer(
            f"❌ Дневной лимит вывода {info['symbol']} исчерпан: *{cap}* за сутки.\n"
            f"💼 На балансе: {round(bal,6)} {info['symbol']} — выведешь завтра!",
            parse_mode="Markdown")
    amount = min(bal, remaining)
    if amount < min_w:
        return await msg.answer(
            f"❌ Доступно к выводу сейчас: *{round(amount,6)} {info['symbol']}*\n"
            f"Минимум: {min_w}. Дневной лимит: {cap} (исп. сегодня {round(used,6)}).\n"
            f"💼 На балансе: {round(bal,6)} {info['symbol']}",
            parse_mode="Markdown")
    wid=create_crypto_withdrawal(uid,ct,amount,wallet,memo)
    add_wd_today(uid, ct, amount)
    left=round(bal-amount,6)
    memo_line=(f"📝 MEMO: `{memo}`\n" if memo else "⚠️ Без MEMO — для биржи это потеря средств!\n")
    await msg.answer(
        f"✅ *ЗАЯВКА #{wid} НА ВЫВОД {info['symbol']}!*\n{'═'*28}\n"
        f"💰 Сумма: *{round(amount,6)} {info['symbol']}*\n"
        f"👛 Адрес: `{wallet}`\n"
        f"{memo_line}"
        f"{'─'*28}\n"
        f"📊 Дневной лимит: {round(used+amount,6)} / {cap}\n"
        f"💼 Остаток на балансе: {left} {info['symbol']}\n"
        f"⏳ Ожидай обработки\n{'═'*28}",
        parse_mode="Markdown"
    )
    kb=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Отправить", callback_data=f"cwapprove_{wid}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"cwreject_{wid}")
    ]])
    await bot.send_message(OWNER_ID,
        f"🔔 *КРИПТО-ВЫВОД #{wid}* {info['symbol']}\n\n"
        f"👤 ID: `{uid}`\n"
        f"💰 {round(amount,6)} {info['symbol']}\n"
        f"👛 `{wallet}`\n{memo_line}"
        f"{'👑 VIP' if ct=='ton' else '🟡 CITY'}",
        parse_mode="Markdown", reply_markup=kb
    )

@dp.callback_query(lambda c: c.data.startswith("cwapprove_"))
async def cwapprove(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    wid=int(call.data.split("_")[1])
    row=get_crypto_withdrawal(wid)
    if not row: return await call.answer("Заявка не найдена",show_alert=True)
    _,uid,ct,amount,address,memo,status=row
    if status!="pending": return await call.answer("Уже обработано",show_alert=True)
    info=CRYPTO_MINING[ct]
    # авто-отправка TON on-chain (если включена)
    if ct=="ton" and TON_AUTOSEND and TON_MNEMONIC:
        await call.answer("⛓️ Отправляю on-chain...")
        try:
            tx=await send_ton_onchain(address,amount,memo)
            set_crypto_withdrawal_status(wid,"sent",tx)
            await call.message.edit_text(f"✅ #{wid} отправлено on-chain.\n🔗 `{tx}`",parse_mode="Markdown")
            try: await bot.send_message(uid,
                f"✅ *Вывод #{wid} отправлен!*\n💰 {round(amount,6)} {info['symbol']}\n🔗 tx: `{tx}`",
                parse_mode="Markdown")
            except: pass
            return
        except Exception as e:
            await call.message.edit_text(
                f"⚠️ Авто-отправка #{wid} не удалась:\n`{e}`\n\nОтправь вручную, заявка осталась в статусе pending.",
                parse_mode="Markdown")
            return
    # ручной режим
    set_crypto_withdrawal_status(wid,"approved")
    await call.message.edit_text(f"✅ Заявка #{wid} одобрена. Отправь {round(amount,6)} {info['symbol']} вручную.")
    try: await bot.send_message(uid,
        f"✅ *Вывод #{wid} одобрен!*\n💰 {round(amount,6)} {info['symbol']} скоро придёт на "
        f"{'биржу' if memo else 'кошелёк'}.",
        parse_mode="Markdown")
    except: pass

@dp.callback_query(lambda c: c.data.startswith("cwreject_"))
async def cwreject(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    wid=int(call.data.split("_")[1])
    row=get_crypto_withdrawal(wid)
    if refund_crypto_withdrawal(wid):
        uid=row[1]
        await call.message.edit_text(f"❌ Заявка #{wid} отклонена, средства возвращены игроку.")
        try: await bot.send_message(uid,f"❌ Вывод #{wid} отклонён. Монеты возвращены на крипто-баланс.")
        except: pass
    else:
        await call.answer("Уже обработано",show_alert=True)

@dp.message(lambda m: m.text=="🎰 Слот")
async def slot_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎰 КРУТИТЬ!",callback_data="spin_slot")]])
    await msg.answer(
        f"🎰 *СЛОТ-МАШИНА*\n{'═'*28}\n🆓 Бесплатно раз в 24ч!\n{'─'*28}\n"
        f"💎💎💎 → *50,000* 🪙\n7️⃣7️⃣7️⃣ → *30,000* 🪙\n⭐⭐⭐ → *20,000* 🪙\n"
        f"🍇🍇🍇 → *5,000* 🪙\n🍒🍒🍒 → *2,000* 🪙\n🍋🍋🍋 → *1,000* 🪙\n"
        f"{'─'*28}\n💼 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}",
        parse_mode="Markdown",reply_markup=kb
    )

@dp.callback_query(lambda c: c.data=="spin_slot")
async def spin_slot(call: types.CallbackQuery):
    uid=call.from_user.id; ok,err,combo,reward=do_slot(uid)
    if ok:
        quest_progress(uid,"slot")
        user=get_user(uid); s1,s2,s3=combo
        verdict=("🎊 ДЖЕКПОТ!!!" if reward>=20000 else "🎉 Отличный выигрыш!" if reward>=5000
                 else "✅ Неплохо!" if reward>=1000 else "😊 Маленький приз" if reward>=100 else "😔 Не повезло")
        await call.message.edit_text(
            f"🎰 *РЕЗУЛЬТАТ*\n{'═'*28}\n┌─────────────┐\n│ {s1} {s2} {s3} │\n└─────────────┘\n"
            f"{'─'*28}\n{verdict}\n💰 Выигрыш: *+{format_coins(reward)}* 🪙\n"
            f"💼 Баланс: *{format_coins(user[2])}* 🪙\n⏳ Следующее через *24ч*\n{'═'*28}",
            parse_mode="Markdown"
        )
    else: await call.answer(err,show_alert=True)

@dp.message(lambda m: m.text=="🎁 Бонус")
async def daily_bonus(msg: types.Message):
    uid=msg.from_user.id; ok,err,streak,reward=do_daily(uid)
    if ok:
        user=get_user(uid); days_row=""
        for d in range(1,8):
            r=DAILY_REWARDS.get(d,DAILY_MAX); mark="✅" if d<streak else ("🎁" if d==streak else "⬜")
            days_row+=f"{mark} День {d}: {r:,} 🪙\n"
        await msg.answer(
            f"🎁 *ЕЖЕДНЕВНЫЙ БОНУС!*\n{'═'*28}\n"
            f"🔥 Серия: *{streak} день* {'🔥'*min(streak,7)}\n"
            f"💰 Получено: *+{format_coins(reward)}* 🪙\n{'─'*28}\n"
            f"{days_row}{'─'*28}\n💼 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}",
            parse_mode="Markdown"
        )
    else: await msg.answer(f"⏳ *{err}*",parse_mode="Markdown")

@dp.message(lambda m: m.text=="⚔️ Атака")
async def attack_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    army=get_army(uid); army_lines=""
    for u,info in ARMY_UNITS.items():
        amt=army.get(u,0)
        if amt>0: army_lines+=f"  {info['name']}: *{amt}*\n"
    if not army_lines: army_lines="  Армии нет!\n"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚔️ Купить войска",     callback_data="buy_army")],
        [InlineKeyboardButton(text="🛡️ Щит защиты",       callback_data="buy_shield_menu")],
        [InlineKeyboardButton(text="🗺️ Атаковать игрока", callback_data="attack_player")],
    ])
    await msg.answer(
        f"⚔️ *ВОЕННЫЙ ЦЕНТР*\n{'═'*28}\n"
        f"🗡️ Атака: *{get_army_power(uid,'attack')}*\n"
        f"🛡️ Защита: *{get_army_power(uid,'defense')}*\n{'─'*28}\n"
        f"*Армия:*\n{army_lines}{'─'*28}\n"
        f"🛡️ Щит: *2,000* 🪙 / *12ч*\n{'═'*28}",
        parse_mode="Markdown",reply_markup=kb
    )

@dp.callback_query(lambda c: c.data=="buy_army")
async def buy_army_menu(call: types.CallbackQuery):
    uid=call.from_user.id; army=get_army(uid)
    btns=[[InlineKeyboardButton(
        text=f"{info['name']} [{army.get(u,0)}] — {info['cost']:,}🪙",callback_data=f"buyunit_{u}"
    )] for u,info in ARMY_UNITS.items()]
    await call.message.edit_text("⚔️ *КУПИТЬ ВОЙСКА*",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(lambda c: c.data.startswith("buyunit_"))
async def buy_unit(call: types.CallbackQuery):
    uid=call.from_user.id; unit_id=call.data.split("_",1)[1]
    ok,result=buy_army_unit(uid,unit_id,1)
    if ok: await call.answer(f"✅ {ARMY_UNITS[unit_id]['name']} куплен!",show_alert=True)
    else:  await call.answer(f"❌ {result}",show_alert=True)

@dp.callback_query(lambda c: c.data=="buy_shield_menu")
async def buy_shield_cb(call: types.CallbackQuery):
    uid=call.from_user.id; ok,err=buy_shield(uid)
    if ok: await call.answer("✅ Щит активирован на 12ч!",show_alert=True)
    else:  await call.answer(f"❌ {err}",show_alert=True)

@dp.callback_query(lambda c: c.data=="attack_player")
async def attack_player_prompt(call: types.CallbackQuery):
    await call.message.answer("🗺️ Введи ID: `/attack USER_ID`",parse_mode="Markdown")
    await call.answer()

@dp.message(Command("attack"))
async def do_attack_cmd(msg: types.Message):
    uid=msg.from_user.id; parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/attack USER_ID`",parse_mode="Markdown")
    try: def_id=int(parts[1])
    except: return await msg.answer("❌ Неверный ID")
    if def_id==uid: return await msg.answer("❌ Нельзя атаковать себя!")
    if not get_user(def_id): return await msg.answer("❌ Игрок не найден")
    ok,result,amount=do_attack(uid,def_id)
    if not ok: return await msg.answer(result,parse_mode="Markdown")
    quest_progress(uid,"attack")
    if result=="win":
        await msg.answer(
            f"⚔️ *АТАКА УСПЕШНА!*\n{'═'*28}\n🏆 ПОБЕДА!\n"
            f"💰 Украдено: *+{format_coins(amount)}* 🪙\n⏳ Следующая через *4ч*\n{'═'*28}",
            parse_mode="Markdown"
        )
        try: await bot.send_message(def_id,f"😱 *ТВОЙ ГОРОД АТАКОВАН!*\n💸 Украдено: *{format_coins(amount)}* 🪙",parse_mode="Markdown")
        except: pass
    else:
        await msg.answer(
            f"⚔️ *АТАКА ПРОВАЛИЛАСЬ!*\n{'═'*28}\n💀 ПОРАЖЕНИЕ!\n"
            f"💸 Потери: *-{format_coins(amount)}* 🪙\n{'═'*28}",
            parse_mode="Markdown"
        )

# ─────────────── ЗАДАНИЯ (хендлеры) ───────────────
@dp.message(lambda m: m.text=="📋 Задания")
async def quests_menu(msg: types.Message):
    uid=msg.from_user.id; qs=get_quests(uid)
    lines=""; done_cnt=0
    for qid,q in DAILY_QUESTS.items():
        st=qs[qid]
        if st["claimed"]: icon="✅"; done_cnt+=1
        elif st["progress"]>=q["target"]: icon="🎁"
        else: icon="⬜"
        bar=progress_bar(min(st["progress"],q["target"]),q["target"])
        lines+=f"{icon} {q['name']} — *{format_coins(q['reward'])}* 🪙\n     {bar}\n"
    await msg.answer(
        f"📋 *ЕЖЕДНЕВНЫЕ ЗАДАНИЯ*\n{'═'*28}\n"
        f"✅ Выполнено: *{done_cnt}/{len(DAILY_QUESTS)}*\n{'─'*28}\n"
        f"{lines}{'─'*28}\n"
        f"🌟 Все задания = +*{format_coins(QUEST_ALL_BONUS)}* 🪙\n"
        f"♻️ Обновляются каждый день\n{'═'*28}",
        parse_mode="Markdown",reply_markup=quests_kb(uid)
    )

@dp.callback_query(lambda c: c.data=="quest_noop")
async def quest_noop(call: types.CallbackQuery):
    await call.answer("Выполни задание, чтобы забрать награду!")

# ВАЖНО: qclaim_all должен идти ВЫШЕ generic qclaim_ (порядок решает)
@dp.callback_query(lambda c: c.data=="qclaim_all")
async def qclaim_all_cb(call: types.CallbackQuery):
    uid=call.from_user.id; ok,err,reward=claim_all_bonus(uid)
    if ok:
        await call.answer(f"🌟 Бонус дня! +{format_coins(reward)} 🪙",show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=quests_kb(uid))
        except: pass
    else: await call.answer(f"❌ {err}",show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("qclaim_"))
async def qclaim_cb(call: types.CallbackQuery):
    uid=call.from_user.id; qid=call.data.split("_",1)[1]
    ok,err,reward=claim_quest(uid,qid)
    if ok:
        await call.answer(f"🎁 +{format_coins(reward)} 🪙!",show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=quests_kb(uid))
        except: pass
    else: await call.answer(f"❌ {err}",show_alert=True)

@dp.message(lambda m: m.text=="🏰 Клан")
async def clan_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    if user[15]:
        clan,members=get_clan_info(user[15])
        if clan:
            total=sum(m[2] for m in members); m_list=""
            for mid,mname,mbal in members[:8]:
                icon="👑" if mid==clan[2] else "👤"
                m_list+=f"{icon} {mname or mid}: {format_coins(mbal)} 🪙\n"
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚪 Выйти",callback_data="clan_leave")]])
            return await msg.answer(
                f"🏰 *КЛАН: {clan[1]}*\n{'═'*28}\n"
                f"👥 Участников: *{len(members)}*\n"
                f"💰 Общий баланс: *{format_coins(total)}* 🪙\n{'─'*28}\n"
                f"*Участники:*\n{m_list}{'═'*28}",
                parse_mode="Markdown",reply_markup=kb
            )
    clans=get_clan_list(); clan_list=""
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣"]
    for i,(cid,cname,cnt,total) in enumerate(clans):
        clan_list+=f"{medals[i]} *{cname}* [{cnt}чел] — {format_coins(total or 0)} 🪙\n"
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать клан",callback_data="clan_create")],
        *[[InlineKeyboardButton(text=f"🏰 {c[1]}",callback_data=f"clan_join_{c[0]}")] for c in clans]
    ])
    await msg.answer(f"🏰 *КЛАНЫ*\n{'═'*28}\n*🏆 Топ кланов:*\n{clan_list}{'═'*28}",parse_mode="Markdown",reply_markup=kb)

@dp.callback_query(lambda c: c.data=="clan_create")
async def clan_create_prompt(call: types.CallbackQuery):
    await call.message.answer("➕ `/createclan НАЗВАНИЕ ОПИСАНИЕ`",parse_mode="Markdown")
    await call.answer()

@dp.message(Command("createclan"))
async def create_clan_cmd(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    if user[15]: return await msg.answer("❌ Ты уже в клане!")
    parts=msg.text.split(maxsplit=2)
    if len(parts)<2: return await msg.answer("Формат: `/createclan НАЗВАНИЕ`",parse_mode="Markdown")
    ok,result=create_clan(uid,parts[1],parts[2] if len(parts)>2 else "")
    if ok: await msg.answer(f"✅ Клан *{parts[1]}* создан!\n👑 Ты лидер!\nСсылка: `/joinclan {result}`",parse_mode="Markdown")
    else: await msg.answer(f"❌ {result}")

@dp.callback_query(lambda c: c.data.startswith("clan_join_"))
async def clan_join_cb(call: types.CallbackQuery):
    uid=call.from_user.id; clan_id=int(call.data.split("_")[-1])
    ok,err=join_clan(uid,clan_id)
    if ok:
        clan,_=get_clan_info(clan_id)
        await call.answer(f"✅ Добро пожаловать в {clan[1]}!",show_alert=True)
        await call.message.edit_text(f"✅ Ты в клане *{clan[1]}*! 🏰",parse_mode="Markdown")
    else: await call.answer(f"❌ {err}",show_alert=True)

@dp.message(Command("joinclan"))
async def join_clan_cmd(msg: types.Message):
    parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/joinclan CLAN_ID`",parse_mode="Markdown")
    try: clan_id=int(parts[1])
    except: return await msg.answer("❌ Неверный ID")
    ok,err=join_clan(msg.from_user.id,clan_id)
    if ok:
        clan,_=get_clan_info(clan_id)
        await msg.answer(f"✅ Ты в клане *{clan[1]}*! 🏰",parse_mode="Markdown")
    else: await msg.answer(f"❌ {err}")

@dp.callback_query(lambda c: c.data=="clan_leave")
async def clan_leave_cb(call: types.CallbackQuery):
    leave_clan(call.from_user.id)
    await call.message.edit_text("✅ Ты вышел из клана.")

@dp.message(lambda m: m.text=="🛒 Магазин")
async def shop_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid)
    btns=[[InlineKeyboardButton(text=f"{item['name']} — {item['stars']} ⭐",callback_data=f"buy_{iid}")] for iid,item in SHOP_ITEMS.items()]
    await msg.answer(
        f"🛒 *МАГАЗИН* (Telegram Stars ⭐)\n{'═'*28}\n"
        f"💼 Баланс: *{format_coins(user[2])}* 🪙\n"
        f"👑 VIP: {vip_status_text(uid)}\n{'─'*28}\nВыбери товар 👇\n{'═'*28}",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(inline_keyboard=btns)
    )

@dp.callback_query(lambda c: c.data.startswith("buy_") and not c.data.startswith("buyunit_"))
async def buy_item(call: types.CallbackQuery):
    uid=call.from_user.id; item_id=call.data.split("_",1)[1]
    item=SHOP_ITEMS.get(item_id)
    if not item: return await call.answer("❌ Не найдено",show_alert=True)
    await call.message.answer_invoice(
        title=item["name"],description=item["desc"],
        payload=f"{item_id}:{uid}",currency="XTR",
        prices=[types.LabeledPrice(label=item["name"],amount=item["stars"])],
        provider_token=""
    )
    await call.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id,ok=True)

@dp.message(lambda m: m.successful_payment is not None)
async def successful_payment(msg: types.Message):
    uid=msg.from_user.id; item_id=msg.successful_payment.invoice_payload.split(":")[0]
    item=SHOP_ITEMS.get(item_id)
    if not item: return
    if item_id.startswith("vip"):
        days=item.get("days",7); activate_vip(uid,days)
        text=f"✅ *{item['name']} активирован!* 🚀 Доход x2 на {days} дн.!"
    elif item_id.startswith("boost"):
        mult=3 if item_id=="boost_x3" else 2
        hours=item.get("hours",24); activate_boost(uid,mult,hours)
        text=f"✅ *{item['name']} активирован!* ⚡ Доход x{mult} на {hours}ч!"
    elif item_id.startswith("coins"):
        add_coins(uid,item.get("coins",0))
        text=f"✅ *{item['name']} зачислены!* 💰"
    elif item_id=="shield":
        activate_shield(uid,item.get("shield_hours",24))
        text=f"✅ *Щит* на {item.get('shield_hours')}ч! 🛡️"
    elif item_id=="army_pack":
        conn=sqlite3.connect(DB); c=conn.cursor()
        c.execute("UPDATE army SET amount=amount+100 WHERE user_id=? AND unit_id='soldier'",(uid,))
        c.execute("UPDATE army SET amount=amount+50 WHERE user_id=? AND unit_id='knight'",(uid,))
        conn.commit(); conn.close()
        text="✅ *Армейский пак!* +100⚔️ +50🛡️"
    else:
        text="✅ Покупка выполнена!"
    await msg.answer(text,parse_mode="Markdown")
    await bot.send_message(OWNER_ID,f"💳 *ПОКУПКА!*\n👤 `{uid}`\n🛒 {item['name']}\n⭐ {item['stars']} Stars",parse_mode="Markdown")

@dp.message(lambda m: m.text=="💸 Вывод")
async def withdraw_menu(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid); bal=user[2]; min_w=get_min_withdraw()
    await msg.answer(
        f"💸 *ВЫВОД В USDT*\n{'═'*28}\n"
        f"💰 Баланс: *{format_coins(bal)}* 🪙\n"
        f"💵 В USDT: *{round(bal*get_rate(),4)}*\n"
        f"📊 {progress_bar(min(bal,min_w),min_w)}\n{'─'*28}\n"
        f"📌 Минимум: *{format_coins(min_w)}* 🪙\n"
        f"📌 Курс: 1000 🪙 = {round(get_rate()*1000,4)} USDT\n{'─'*28}\n"
        f"Команда:\n`/withdraw КОШЕЛЁК СУММА`\n{'═'*28}",
        parse_mode="Markdown"
    )

@dp.message(Command("withdraw"))
async def withdraw(msg: types.Message):
    uid=msg.from_user.id; user=get_user(uid); parts=msg.text.split()
    if len(parts)!=3: return await msg.answer("❌ Формат: `/withdraw КОШЕЛЁК СУММА`",parse_mode="Markdown")
    wallet=parts[1]
    try: amount=int(parts[2])
    except: return await msg.answer("❌ Сумма должна быть числом.")
    min_w=get_min_withdraw()
    if amount<min_w: return await msg.answer(f"❌ Минимум {format_coins(min_w)} монет.")
    if user[2]<amount: return await msg.answer("❌ Недостаточно монет.")
    usdt=create_withdrawal(uid,amount,wallet)
    await msg.answer(
        f"✅ *ЗАЯВКА СОЗДАНА!*\n{'═'*28}\n"
        f"💸 *{format_coins(amount)}* 🪙 = *{usdt}* USDT\n"
        f"👛 `{wallet}`\n⏳ Ожидай подтверждения\n{'═'*28}",
        parse_mode="Markdown"
    )
    await bot.send_message(OWNER_ID,f"🔔 *ЗАЯВКА!*\n👤 `{uid}`\n💸 {format_coins(amount)} 🪙 = {usdt} USDT\n👛 `{wallet}`",parse_mode="Markdown")

@dp.message(lambda m: m.text=="👥 Рефералы")
async def referrals(msg: types.Message):
    uid=msg.from_user.id; refs=get_referrals(uid)
    link=f"https://t.me/ТВОЙ_БОТ?start={uid}"
    await msg.answer(
        f"👥 *РЕФЕРАЛЫ*\n{'═'*28}\n"
        f"💰 За каждого друга: *+500* 🪙\n{'─'*28}\n"
        f"👤 Рефералов: *{refs}*\n"
        f"📊 {progress_bar(min(refs,10),10)}\n"
        f"💰 Заработано: *{format_coins(refs*500)}* 🪙\n{'─'*28}\n"
        f"🔗 Ссылка:\n`{link}`\n{'═'*28}",
        parse_mode="Markdown"
    )

@dp.message(Command("play"))
@dp.message(lambda m: m.text and "играть" in m.text.lower())
async def play_game(msg: types.Message):
    uid  = msg.from_user.id
    user = get_user(uid)
    if not user:
        create_user(uid, msg.from_user.username or msg.from_user.first_name)
        user = get_user(uid)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Открыть CityEmpire Match",
                            web_app=types.WebAppInfo(url=game_url_for(uid)))],
            [KeyboardButton(text="🔙 Меню")],
        ],
        resize_keyboard=True
    )
    await msg.answer(
        f"🎮 *CITYEMPIRE MATCH*\n"
        f"{'═'*28}\n"
        f"🧙 Волшебник ждёт тебя!\n"
        f"{'─'*28}\n"
        f"⭐ Проходи уровни матч-3\n"
        f"🪙 Зарабатывай CITY монеты\n"
        f"💣 Используй бустеры\n"
        f"🏆 Собирай звёзды\n"
        f"{'─'*28}\n"
        f"💰 Баланс: *{format_coins(user[2])}* 🪙\n"
        f"{'═'*28}\n"
        f"👇 Нажми кнопку, чтобы играть",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.message(lambda m: m.text=="🔙 Меню")
async def back_to_menu(msg: types.Message):
    uid=msg.from_user.id
    await msg.answer("🏙️ Главное меню",reply_markup=main_menu(uid))

@dp.message(lambda m: m.web_app_data is not None)
async def web_app_data_handler(msg: types.Message):
    uid = msg.from_user.id
    try:
        data = json.loads(msg.web_app_data.data)
        action = data.get('action')
        if action in ('claim','level_complete','withdraw'):
            level = data.get('level', data.get('best_level'))
            if level is None:
                # старый клиент слал сумму напрямую — больше не доверяем
                await msg.answer(
                    "🔄 Обнови игру: теперь награды считает сервер.\n"
                    "Открой 🎮 Играть заново — прогресс не потеряется.",
                    reply_markup=main_menu(uid)
                )
                return
            reward, top, status = game_claim(uid, level)
            if reward <= 0:
                await msg.answer(
                    f"🎮 *Прогресс сохранён* — лучший уровень *{top}*.\n"
                    f"Новых наград пока нет: пройди дальше, чтобы заработать ещё CITY!",
                    parse_mode="Markdown", reply_markup=main_menu(uid)
                )
                return
            cm = get_crypto_mining(uid,'city'); bal = cm[3] if cm else 0
            note = "\n⚠️ Достигнут дневной лимит начисления — остальное завтра." if status=="capped" else ""
            await msg.answer(
                f"🎮 *НАГРАДА ИЗ ИГРЫ!*\n{'═'*28}\n"
                f"🏆 Лучший уровень: *{top}*\n"
                f"🪙 Начислено: *+{format_coins(reward)} CITY*\n"
                f"💼 CITY-баланс: *{round(bal,2)} CITY*{note}\n{'─'*28}\n"
                f"📈 Выводи в 💎 Крипто (есть дневной лимит вывода)\n{'═'*28}",
                parse_mode="Markdown", reply_markup=main_menu(uid)
            )
            await bot.send_message(OWNER_ID,
                f"🎮 *Награда из игры*\n👤 `{uid}`\n🏆 ур.{top}\n🪙 +{format_coins(reward)} CITY",
                parse_mode="Markdown"
            )
    except Exception:
        pass

@dp.message(lambda m: m.text=="🏆 Рейтинг")
async def rating(msg: types.Message):
    top=get_top_users(); medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=""
    for i,(uid,uname,bal) in enumerate(top):
        lines+=f"{medals[i]} *{uname or uid}* — {format_coins(bal)} 🪙 {get_rank(bal)}\n"
    await msg.answer(f"🏆 *ТОП-10*\n{'═'*28}\n{lines}{'═'*28}",parse_mode="Markdown")

@dp.message(lambda m: m.text=="ℹ️ Помощь")
async def help_msg(msg: types.Message):
    await msg.answer(
        f"ℹ️ *КАК ИГРАТЬ*\n{'═'*28}\n"
        f"🏗️ Строй здания → доход/час\n💰 Собирай монеты\n"
        f"⛏️ Майни каждые 8ч\n💎 Крипто-майнинг TON/CITY\n"
        f"🎰 Слот раз в день\n🎁 Бонус каждый день\n"
        f"📋 Выполняй задания → награды\n🎮 Играй в матч-3\n"
        f"⚔️ Атакуй игроков\n🏰 Вступи в клан\n"
        f"🛒 VIP и бусты\n💸 Вывод от {format_coins(get_min_withdraw())} 🪙\n{'─'*28}\n"
        f"`/attack ID` — атака\n`/createclan ИМЯ` — клан\n"
        f"`/withdraw КОШЕЛЁК СУММА`\n`/cwithdraw ton/city АДРЕС МЕМО`\n"
        f"(MEMO нужен для биржи!)\n{'═'*28}",
        parse_mode="Markdown"
    )

@dp.callback_query(lambda c: c.data.startswith("bld_"))
async def building_info(call: types.CallbackQuery):
    uid=call.from_user.id; bid=call.data.split("_",1)[1]
    info=BUILDINGS[bid]; blds=get_buildings(uid); lvl=blds.get(bid,0); user=get_user(uid)
    text=(f"{info['name']}\n{'═'*28}\n"
          f"📊 {star_level(lvl)} {progress_bar(lvl,5)}\n"
          f"💰 Доход: *{info['income'][lvl]}* 🪙/час\n")
    if lvl<5:
        text+=(f"{'─'*28}\n⬆️ Следующий: *{info['income'][lvl+1]}* 🪙/час\n"
               f"💸 Цена: *{info['levels'][lvl+1]:,}* 🪙\n💼 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}")
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"⬆️ Улучшить за {info['levels'][lvl+1]:,} 🪙",callback_data=f"upg_{bid}")],
            [InlineKeyboardButton(text="🔙 Назад",callback_data="back_buildings")],
        ])
    else:
        text+=f"✅ *МАКСИМУМ!*\n{'═'*28}"
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад",callback_data="back_buildings")]])
    await call.message.edit_text(text,parse_mode="Markdown",reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("upg_"))
async def upgrade_cb(call: types.CallbackQuery):
    uid=call.from_user.id; bid=call.data.split("_",1)[1]
    ok,result=upgrade_building(uid,bid)
    if ok:
        quest_progress(uid,"upgrade")
        await call.answer(f"✅ Улучшено до уровня {result}!",show_alert=True)
    else:  await call.answer(f"❌ {result}",show_alert=True)
    await call.message.edit_reply_markup(reply_markup=buildings_kb(uid))

@dp.callback_query(lambda c: c.data=="back_buildings")
async def back_buildings(call: types.CallbackQuery):
    await call.message.edit_text("🏗️ *ЗДАНИЯ*",parse_mode="Markdown",reply_markup=buildings_kb(call.from_user.id))

@dp.callback_query(lambda c: c.data=="mine_now")
async def mine_now(call: types.CallbackQuery):
    uid=call.from_user.id; ok,err,reward=do_mine(uid)
    if ok:
        quest_progress(uid,"mine")
        user=get_user(uid)
        await call.answer(f"✅ Добыто {format_coins(reward)}!",show_alert=True)
        await call.message.edit_text(
            f"⛏️ *ДОБЫЧА!*\n{'═'*28}\n💰 +*{format_coins(reward)}* 🪙\n"
            f"💼 Баланс: *{format_coins(user[2])}* 🪙\n⏳ Следующая через *8ч*\n{'═'*28}",
            parse_mode="Markdown",reply_markup=miner_kb(uid)
        )
    else: await call.answer(err,show_alert=True)

@dp.callback_query(lambda c: c.data=="mine_upgrade")
async def mine_upgrade(call: types.CallbackQuery):
    uid=call.from_user.id; ok,result=upgrade_miner(uid)
    if ok:
        user=get_user(uid); info=MINER_LEVELS[user[8]]
        await call.answer(f"✅ Майнер улучшен!",show_alert=True)
        await call.message.edit_text(
            f"🎉 *МАЙНЕР УЛУЧШЕН!*\n{'═'*28}\n🔧 *{info['name']}*\n"
            f"💰 Награда: *{info['reward']:,}* 🪙\n💼 Баланс: *{format_coins(user[2])}* 🪙\n{'═'*28}",
            parse_mode="Markdown",reply_markup=miner_kb(uid)
        )
    else: await call.answer(f"❌ {result}",show_alert=True)

@dp.callback_query(lambda c: c.data=="adm_stats")
async def adm_stats(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    conn=sqlite3.connect(DB); c=conn.cursor()
    c.execute("SELECT COUNT(*) FROM users"); total=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE banned=1"); banned=c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='pending'"); pending=c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users"); total_coins=c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM clans"); clans=c.fetchone()[0]
    conn.close()
    await call.message.edit_text(
        f"📊 *СТАТИСТИКА*\n{'═'*28}\n"
        f"👤 Игроков: *{total}*\n🚫 Забанено: *{banned}*\n"
        f"💸 Заявок: *{pending}*\n🏰 Кланов: *{clans}*\n"
        f"🪙 Монет: *{format_coins(total_coins)}*\n{'═'*28}",
        parse_mode="Markdown",reply_markup=admin_kb()
    )

@dp.callback_query(lambda c: c.data=="adm_withdrawals")
async def adm_withdrawals(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    rows=get_pending_withdrawals()
    if not rows: return await call.answer("Нет заявок!",show_alert=True)
    for row in rows:
        wid,uid,amount,usdt,wallet=row
        kb=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Одобрить",callback_data=f"wapprove_{wid}_{uid}"),
            InlineKeyboardButton(text="❌ Отклонить",callback_data=f"wreject_{wid}_{uid}_{amount}")
        ]])
        await call.message.answer(f"💸 *Заявка #{wid}*\n👤 `{uid}`\n💰 {format_coins(amount)} = {usdt} USDT\n👛 `{wallet}`",parse_mode="Markdown",reply_markup=kb)

@dp.callback_query(lambda c: c.data=="adm_cwd")
async def adm_cwd(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    rows=get_pending_crypto_withdrawals()
    if not rows: return await call.answer("Нет крипто-заявок!",show_alert=True)
    for wid,uid,ct,amount,address,memo in rows:
        sym=CRYPTO_MINING[ct]['symbol']
        memo_line=f"\n📝 MEMO: `{memo}`" if memo else "\n⚠️ без MEMO"
        kb=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Отправить",callback_data=f"cwapprove_{wid}"),
            InlineKeyboardButton(text="❌ Отклонить",callback_data=f"cwreject_{wid}")
        ]])
        await call.message.answer(
            f"💎 *Заявка #{wid}* — {ct.upper()}\n"
            f"👤 `{uid}`\n💰 {round(amount,6)} {sym}\n👛 `{address}`{memo_line}",
            parse_mode="Markdown",reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("wapprove_"))
async def wapprove(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    _,wid,uid=call.data.split("_"); approve_withdrawal(int(wid))
    await call.message.edit_text(f"✅ Заявка #{wid} одобрена!")
    try: await bot.send_message(int(uid),"✅ Заявка одобрена! Деньги скоро придут. 💸")
    except: pass

@dp.callback_query(lambda c: c.data.startswith("wreject_"))
async def wreject(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    parts=call.data.split("_"); wid,uid,amount=int(parts[1]),int(parts[2]),int(parts[3])
    reject_withdrawal(wid,uid,amount)
    await call.message.edit_text(f"❌ Заявка #{wid} отклонена.")
    try: await bot.send_message(uid,"❌ Заявка отклонена. Монеты возвращены.")
    except: pass

@dp.callback_query(lambda c: c.data=="adm_rates")
async def adm_rates(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    rate=get_rate(); min_w=get_min_withdraw()
    await call.message.edit_text(
        f"💱 *УПРАВЛЕНИЕ КУРСОМ*\n{'═'*28}\n"
        f"📈 1,000 🪙 = *{round(rate*1000,4)}$*\n"
        f"📉 Мин. вывод: *{format_coins(min_w)}* 🪙\n"
        f"🔷 Твой TON-майнинг: *{get_owner_ton()}* TON/сутки\n{'─'*28}\n"
        f"`/setrate 0.00002` — изменить курс\n"
        f"`/setminw 100000` — мин. вывод\n"
        f"`/setownerton 15` — твоя ставка TON\n{'═'*28}",
        parse_mode="Markdown",reply_markup=rates_kb()
    )

@dp.callback_query(lambda c: c.data=="adm_setrate")
async def adm_setrate_p(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    await call.message.answer("💱 Примеры:\n`/setrate 0.00001` → 1000🪙=$0.01\n`/setrate 0.0001` → 1000🪙=$0.10",parse_mode="Markdown")
    await call.answer()

@dp.callback_query(lambda c: c.data=="adm_setminw")
async def adm_setminw_p(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    await call.message.answer("📉 Примеры:\n`/setminw 50000`\n`/setminw 100000`",parse_mode="Markdown")
    await call.answer()

@dp.callback_query(lambda c: c.data=="adm_back")
async def adm_back(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    await call.message.edit_text("👑 *ПАНЕЛЬ ВЛАДЕЛЬЦА*",parse_mode="Markdown",reply_markup=admin_kb())

@dp.callback_query(lambda c: c.data=="adm_broadcast")
async def adm_broadcast_info(call: types.CallbackQuery):
    if call.from_user.id!=OWNER_ID: return
    await call.message.answer("📢 Напиши: `/broadcast ТЕКСТ`",parse_mode="Markdown")

@dp.message(Command("setrate"))
async def set_rate_cmd(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/setrate 0.00002`",parse_mode="Markdown")
    try:
        new_rate=float(parts[1])
        if new_rate<=0: raise ValueError
    except: return await msg.answer("❌ Неверное значение.")
    old_rate=get_rate(); set_setting("coin_to_usdt",new_rate)
    change="⬆️" if new_rate>old_rate else "⬇️"
    await msg.answer(f"✅ *КУРС ОБНОВЛЁН!*\nБыло: {round(old_rate*1000,4)}$\nСтало: {round(new_rate*1000,4)}$ {change}",parse_mode="Markdown")
    for uid in get_all_users():
        try:
            await bot.send_message(uid,f"📢 *ИЗМЕНЕНИЕ КУРСА!*\n1000 🪙 = *{round(new_rate*1000,4)}$* {change}",parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except: pass

@dp.message(Command("setminw"))
async def set_minw_cmd(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/setminw 100000`",parse_mode="Markdown")
    try: new_min=int(parts[1])
    except: return await msg.answer("❌ Неверное значение.")
    old_min=get_min_withdraw(); set_setting("min_withdraw",new_min)
    await msg.answer(f"✅ Мин.вывод: *{format_coins(old_min)}* → *{format_coins(new_min)}* 🪙",parse_mode="Markdown")

@dp.message(Command("setownerton"))
async def set_owner_ton_cmd(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/setownerton 15`",parse_mode="Markdown")
    try:
        val=float(parts[1])
        if val<0: raise ValueError
    except: return await msg.answer("❌ Неверное значение.")
    old=get_owner_ton(); set_setting("owner_ton_daily",val)
    await msg.answer(
        f"✅ *Твоя ставка TON-майнинга обновлена!*\n{'═'*28}\n"
        f"Было: *{old} TON* / сутки\n"
        f"Стало: *{val} TON* / сутки\n{'═'*28}",
        parse_mode="Markdown"
    )

@dp.message(Command("broadcast"))
async def broadcast(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    text=msg.text[len("/broadcast "):].strip()
    if not text: return await msg.answer("❌ Напиши текст.")
    users=get_all_users(); sent=0
    for uid in users:
        try:
            await bot.send_message(uid,f"📢 *ОТ АДМИНИСТРАТОРА:*\n{'─'*20}\n{text}",parse_mode="Markdown")
            sent+=1; await asyncio.sleep(0.05)
        except: pass
    await msg.answer(f"✅ Отправлено *{sent}* игрокам.",parse_mode="Markdown")

@dp.message(Command("give"))
async def give_coins(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=3: return await msg.answer("Формат: `/give USER_ID СУММА`",parse_mode="Markdown")
    try: uid,amount=int(parts[1]),int(parts[2])
    except: return await msg.answer("❌ Неверный формат.")
    add_coins(uid,amount)
    await msg.answer(f"✅ Начислено *{format_coins(amount)}* монет `{uid}`.",parse_mode="Markdown")
    try: await bot.send_message(uid,f"🎁 *+{format_coins(amount)}* 🪙 от администратора!",parse_mode="Markdown")
    except: pass

@dp.message(Command("givevip"))
async def give_vip(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=3: return await msg.answer("Формат: `/givevip USER_ID ДНЕЙ`",parse_mode="Markdown")
    try: uid,days=int(parts[1]),int(parts[2])
    except: return await msg.answer("❌ Неверный формат.")
    activate_vip(uid,days)
    await msg.answer(f"✅ VIP на *{days}* дн. выдан `{uid}`.",parse_mode="Markdown")
    try: await bot.send_message(uid,f"👑 *Тебе выдан VIP на {days} дн.!* Доход x2!",parse_mode="Markdown")
    except: pass

@dp.message(Command("stars"))
async def stars_balance_cmd(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    try:
        bal = await bot.get_my_star_balance()
        amt = getattr(bal, "amount", bal)
        usd = round(int(amt)*0.013, 2)
        await msg.answer(
            f"⭐ *ДОХОД В STARS*\n{'═'*28}\n"
            f"💫 Баланс бота: *{amt}* ⭐\n"
            f"💵 ≈ *${usd}* по курсу выплат\n{'─'*28}\n"
            f"📤 Вывод: Telegram → Настройки → Мои Stars → Вывести\n"
            f"   (через Fragment в TON, потом на биржу)\n"
            f"📌 Условия: от *1000* ⭐ и через *21 день* после получения\n{'═'*28}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await msg.answer(
            f"❌ Не удалось получить баланс Stars.\n"
            f"Нужна свежая версия aiogram (3.13+). Обнови в requirements.txt.\n`{e}`",
            parse_mode="Markdown"
        )

@dp.message(Command("ban"))
async def ban(msg: types.Message):
    if msg.from_user.id!=OWNER_ID: return
    parts=msg.text.split()
    if len(parts)!=2: return await msg.answer("Формат: `/ban USER_ID`",parse_mode="Markdown")
    ban_user(int(parts[1]))
    await msg.answer(f"🚫 Игрок `{parts[1]}` заблокирован.",parse_mode="Markdown")

async def main():
    init_db()
    print("✅ CityEmpire Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
