# -*- coding: utf-8 -*-
"""
New Proxy Market - Telegram Digital Goods Shop Bot (Bangladesh / BDT)
Single file: bot.py   |   Install: pip install -r requirements.txt   |   Run: python bot.py

Setup:  BOT_TOKEN aur OWNER_IDS neeche set karo (ya environment variable me do).
"""
import asyncio
import base64
import hashlib
import hmac
import io
import logging
import os
import re
import struct
import time
from datetime import datetime, timedelta, timezone
from html import escape as esc

import aiosqlite
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup)

# ======================================================================
#                              CONFIG
# ======================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
# Owner Telegram numeric ID(s), comma separated. Owner = full access + Admin Management
OWNER_IDS = [int(x) for x in os.getenv("OWNER_IDS", "123456789").split(",") if x.strip()]
SHOP_NAME = "New Proxy Market"
DB_PATH = os.getenv("DB_PATH", "shop.db")
MAX_QTY = 500                       # max pieces per single order
BD = timezone(timedelta(hours=6))   # Bangladesh time (today / yesterday calc)

DEFAULT_SETTINGS = {
    "bkash": "01XXXXXXXXX", "nagad": "01XXXXXXXXX", "rocket": "01XXXXXXXXX",
    "binance": "Binance-Pay-ID", "rate": "120", "min_dep": "20",
    "support_user": "", "tutorial": "",
}
PAY_NAMES = {"bkash": "Bkash", "nagad": "Nagad", "rocket": "Rocket", "binance": "Binance"}

# ======================================================================
#   BUTTON REGISTRY  key: (default unicode emoji, label, color style)
#   style: primary = blue, success = green, danger = red
#   Admin "Premium Emoji Set" se in sab keys par premium emoji lag sakta hai
# ======================================================================
B = {
    # --- user menu (reply keyboard)
    "buy": ("🛒", "Buy Products", "success"),
    "profile": ("👤", "My Profile", "primary"),
    "deposit": ("💰", "Deposit", "primary"),
    "getcode": ("🛡", "Get Code", "primary"),
    "support": ("🎧", "Support", "primary"),
    "tutorial": ("👑", "Tutorial", "success"),
    "admin": ("🛠", "Admin Panel", "primary"),
    # --- admin menu (reply keyboard)
    "a_prod": ("📦", "Product Management", "primary"),
    "a_addstock": ("🔥", "Add Stock", "success"),
    "a_live": ("📊", "Live Stock", "primary"),
    "a_users": ("👥", "User Management", "danger"),
    "a_depreq": ("🚨", "Deposit Requests", "success"),
    "a_dephist": ("🧾", "Deposit History", "primary"),
    "a_bcast": ("📢", "Broadcast", "danger"),
    "a_voucher": ("🎟", "Voucher Management", "success"),
    "a_force": ("🔒", "Force Join Setup", "primary"),
    "a_support": ("🎧", "Support Setup", "danger"),
    "a_admins": ("👮", "Admin Management", "primary"),
    "a_pay": ("💳", "Payment Settings", "success"),
    "a_resell": ("🤝", "Reseller Management", "primary"),
    "a_tutorial": ("📚", "Tutorial Setup", "success"),
    "a_emoji": ("✨", "Premium Emoji Set", "danger"),
    "a_stats": ("📈", "Statistics", "primary"),
    "usermenu": ("✅", "User Menu", "success"),
    # --- inline buttons
    "back": ("❌", "Back", "danger"),
    "bkash": ("💸", "Bkash", "primary"),
    "nagad": ("🟠", "Nagad", "primary"),
    "rocket": ("🚀", "Rocket", "primary"),
    "binance": ("🟡", "Binance", "primary"),
    "paydone": ("✅", "Payment Done", "success"),
    "enterqty": ("✏️", "Enter Quantity", "success"),
    "applyvoucher": ("🎁", "Apply Voucher", "primary"),
    "buyhist": ("🛍", "Buy History", "primary"),
    "rechist": ("💵", "Recharge History", "success"),
    "twofa": ("🔐", "2FA Code", "primary"),
    "contact": ("📞", "Contact Admin", "success"),
    "approve": ("✅", "Approve", "success"),
    "reject": ("❌", "Reject", "danger"),
    "ban": ("⛔", "Ban", "danger"),
    "unban": ("🟢", "Unban", "success"),
    "addbal": ("➕", "Add Balance", "primary"),
    "cutbal": ("➖", "Cut Balance", "danger"),
    "sendmsg": ("✉️", "Send Message", "primary"),
    "reply": ("↩️", "Reply", "success"),
    "addcat": ("📁", "Add Category", "success"),
    "delcat": ("🗑", "Delete Category", "danger"),
    "addprod": ("🆕", "Add Product", "primary"),
    "chprice": ("💲", "Change Price", "primary"),
    "delprod": ("❌", "Delete Product", "danger"),
    "delstock": ("🧹", "Delete Product Stock", "primary"),
    "addadmin": ("👑", "Add Admin", "success"),
    "deladmin": ("❌", "Delete Admin", "danger"),
    "vcreate": ("➕", "Create Voucher", "success"),
    "vdelete": ("🗑", "Delete Voucher", "danger"),
    "vlist": ("📋", "Voucher List", "primary"),
    "fadd": ("➕", "Add Channel", "success"),
    "fremove": ("🗑", "Remove Channel", "danger"),
    "addresell": ("➕", "Add Reseller", "success"),
    "delresell": ("➖", "Remove Reseller", "danger"),
    "yes": ("✅", "Yes, Confirm", "success"),
    "no": ("❌", "Cancel", "danger"),
    "joined": ("✅", "I Joined", "success"),
    "edit_rate": ("💱", "Edit Dollar Rate", "success"),
    "edit_min": ("⬇️", "Edit Minimum Deposit", "primary"),
}
MENU_KEYS = [k for k in B if k in (
    "buy", "profile", "deposit", "getcode", "support", "tutorial", "admin", "usermenu") or k.startswith("a_")]

# ======================================================================
#                         GLOBAL STATE / CACHE
# ======================================================================
DB: aiosqlite.Connection = None
bot: Bot = None
BOT_USERNAME = ""
SET: dict = {}
EMO: dict = {}          # key -> custom emoji id (buttons)
ADMINS: set = set()
SUPMAP: dict = {}       # (admin_chat, msg_id) -> user id (support reply by Telegram reply)
BUY_LOCK = asyncio.Lock()
r = Router()


# ======================================================================
#                               DATABASE
# ======================================================================
async def init_db():
    global DB
    DB = await aiosqlite.connect(DB_PATH)
    DB.row_factory = aiosqlite.Row
    await DB.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, username TEXT,
        balance REAL DEFAULT 0, banned INTEGER DEFAULT 0, reseller INTEGER DEFAULT 0,
        referrer INTEGER, joined INTEGER);
    CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, emoji_id TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER, name TEXT,
        price REAL, rprice REAL, emoji_id TEXT);
    CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, data TEXT,
        sold INTEGER DEFAULT 0, buyer INTEGER, sold_at INTEGER);
    CREATE INDEX IF NOT EXISTS ix_stock ON stock(product_id, sold);
    CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER,
        product_name TEXT, qty INTEGER, total REAL, created INTEGER, items TEXT);
    CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, method TEXT,
        amount REAL, trx TEXT, photo TEXT, status TEXT DEFAULT 'pending', created INTEGER, decided INTEGER);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS emojis(key TEXT PRIMARY KEY, emoji_id TEXT);
    CREATE TABLE IF NOT EXISTS vouchers(code TEXT PRIMARY KEY, amount REAL, max_uses INTEGER, used INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS voucher_uses(code TEXT, user_id INTEGER);
    CREATE TABLE IF NOT EXISTS force_channels(id INTEGER PRIMARY KEY AUTOINCREMENT, chat TEXT, title TEXT, link TEXT);
    """)
    for k, v in DEFAULT_SETTINGS.items():
        await DB.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    await DB.commit()
    await load_cache()


async def load_cache():
    SET.clear(); EMO.clear(); ADMINS.clear()
    for x in await fetchall("SELECT * FROM settings"):
        SET[x["key"]] = x["value"]
    for x in await fetchall("SELECT * FROM emojis"):
        EMO[x["key"]] = x["emoji_id"]
    for x in await fetchall("SELECT id FROM admins"):
        ADMINS.add(x["id"])


async def fetchone(sql, args=()):
    async with DB.execute(sql, args) as c:
        return await c.fetchone()


async def fetchall(sql, args=()):
    async with DB.execute(sql, args) as c:
        return await c.fetchall()


async def run(sql, args=()):
    cur = await DB.execute(sql, args)
    await DB.commit()
    return cur


async def set_setting(k, v):
    SET[k] = str(v)
    await run("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v)))


# ======================================================================
#                               HELPERS
# ======================================================================
def admin_ids():
    return set(OWNER_IDS) | ADMINS


def is_admin(uid):
    return uid in OWNER_IDS or uid in ADMINS


def rate():
    try:
        return float(SET.get("rate") or 120)
    except ValueError:
        return 120.0


def money(x):
    return f"{x:.2f} BDT ({x / rate():.2f} USD)"


def fp(x):
    return f"{x:.1f}"


def now():
    return int(time.time())


def day_bounds():
    t0 = datetime.now(BD).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(t0.timestamp()), int((t0 - timedelta(days=1)).timestamp())


def fdate(ts):
    return datetime.fromtimestamp(ts, BD).strftime("%d-%b %I:%M %p")


def em(key):
    """premium emoji (if set) else normal emoji - for message text (HTML)"""
    fb = B[key][0] if key in B else "•"
    cid = EMO.get(key)
    return f'<tg-emoji emoji-id="{cid}">{fb}</tg-emoji>' if cid else fb


def cem(cid, fb):
    return f'<tg-emoji emoji-id="{cid}">{fb}</tg-emoji>' if cid else fb


def IM(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ib(key, text=None, **kw):
    emo, label, style = B[key]
    cid = EMO.get(key)
    t = text or label
    d = dict(text=t if cid else f"{emo} {t}", style=style, **kw)
    if cid:
        d["icon_custom_emoji_id"] = cid
    return InlineKeyboardButton(**d)


def dib(text, cb, cid=None, default="📁", style="primary"):
    d = dict(text=text if cid else f"{default} {text}", callback_data=cb, style=style)
    if cid:
        d["icon_custom_emoji_id"] = cid
    return InlineKeyboardButton(**d)


def rb(key):
    """Reply-keyboard fallback. ReplyKeyboardButton does not support custom emoji icons."""
    emo, label, style = B[key]
    return KeyboardButton(text=f"{emo} {label}")


def mb(key, **kw):
    """Menu button using InlineKeyboardButton, which supports custom emoji icons."""
    emo, label, style = B[key]
    cid = EMO.get(key)
    d = dict(text=label if cid else f"{emo} {label}", style=style, callback_data=f"menu:{key}", **kw)
    if cid:
        d["icon_custom_emoji_id"] = cid
    return InlineKeyboardButton(**d)


def RK(rows):
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def main_kb(uid):
    rows = [[mb("buy")], [mb("profile"), mb("deposit")], [mb("getcode"), mb("support")], [mb("tutorial")]]
    if is_admin(uid):
        rows.append([mb("admin")])
    return IM(rows)


def admin_kb():
    k = ["a_prod", "a_addstock", "a_live", "a_users", "a_depreq", "a_dephist", "a_bcast", "a_voucher",
         "a_force", "a_support", "a_admins", "a_pay", "a_resell", "a_tutorial", "a_emoji", "a_stats"]
    rows = [[mb(k[i]), mb(k[i + 1])] for i in range(0, len(k), 2)]
    rows.append([mb("usermenu")])
    return IM(rows)


async def show(ev, text, kb=None):
    """edit if callback else answer"""
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.edit_text(text, reply_markup=kb)
            return
        except TelegramBadRequest:
            await ev.message.answer(text, reply_markup=kb)
            return
    await ev.answer(text, reply_markup=kb)


async def notify_admins(text, **kw):
    for a in admin_ids():
        try:
            await bot.send_message(a, text, **kw)
        except Exception:
            pass


async def ensure_user(u, ref=None):
    row = await fetchone("SELECT id FROM users WHERE id=?", (u.id,))
    if not row:
        await DB.execute("INSERT INTO users(id,name,username,joined,referrer) VALUES(?,?,?,?,?)",
                         (u.id, u.full_name, u.username or "", now(), ref))
    else:
        await DB.execute("UPDATE users SET name=?, username=? WHERE id=?", (u.full_name, u.username or "", u.id))
    await DB.commit()


async def get_user(uid):
    return await fetchone("SELECT * FROM users WHERE id=?", (uid,))


async def find_user(txt):
    txt = txt.strip().lstrip("@")
    if txt.isdigit():
        return await fetchone("SELECT * FROM users WHERE id=?", (int(txt),))
    return await fetchone("SELECT * FROM users WHERE lower(username)=lower(?)", (txt,))


async def stock_count(pid):
    x = await fetchone("SELECT COUNT(*) c FROM stock WHERE product_id=? AND sold=0", (pid,))
    return x["c"]


def totp(secret):
    s = re.sub(r"\s+", "", secret).upper()
    s += "=" * (-len(s) % 8)
    key = base64.b32decode(s, casefold=True)
    h = hmac.new(key, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest()
    o = h[-1] & 15
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000
    return f"{code:06d}", 30 - int(time.time()) % 30


def parse_txt(b):
    return [l.strip() for l in b.decode("utf-8", "ignore").splitlines() if l.strip()]


def parse_xlsx(b):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(b), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() for c in row if c is not None and str(c).strip() != ""]
            if cells:
                out.append(":".join(cells))
    return out


def parse_emoji_id(m: Message):
    """digits ya premium emoji message se custom_emoji_id nikalta hai. '0' = remove"""
    for e in (m.entities or []):
        if e.type == "custom_emoji":
            return e.custom_emoji_id
    t = (m.text or "").strip()
    return t if t.isdigit() else None


# ======================================================================
#                                STATES
# ======================================================================
class S(StatesGroup):
    dep_amount = State(); dep_trx = State(); dep_shot = State()
    qty = State(); support = State(); voucher = State(); twofa = State()
    a_reply = State()
    a_cat_name = State(); a_prod_name = State(); a_prod_price = State(); a_prod_rprice = State()
    a_price = State(); a_rprice = State(); a_stock = State()
    a_user = State(); a_bal = State(); a_msg = State(); a_bcast = State()
    a_vcode = State(); a_vamt = State(); a_vuses = State()
    a_force = State(); a_admin = State(); a_resell = State(); a_setval = State(); a_emoji = State()


# ======================================================================
#                      FILTERS + MIDDLEWARE (ban / force join)
# ======================================================================
class AdminF(BaseFilter):
    async def __call__(self, ev):
        return is_admin(ev.from_user.id)


A = AdminF()


class MenuF(BaseFilter):
    async def __call__(self, m: Message):
        t = (m.text or "").strip()
        if not t:
            return False
        for k in MENU_KEYS:
            label = B[k][1]
            if t.endswith(label):
                prefix = t[:-len(label)].strip()
                if not prefix or (len(prefix) <= 8 and not any(ch.isalnum() for ch in prefix)):
                    return {"mkey": k}
        return False


class SupReplyF(BaseFilter):
    async def __call__(self, m: Message):
        if not m.reply_to_message or not is_admin(m.from_user.id):
            return False
        uid = SUPMAP.get((m.chat.id, m.reply_to_message.message_id))
        return {"sup_uid": uid} if uid else False


async def missing_channels(uid):
    miss = []
    for c in await fetchall("SELECT * FROM force_channels"):
        try:
            chat = int(c["chat"]) if c["chat"].lstrip("-").isdigit() else c["chat"]
            mem = await bot.get_chat_member(chat, uid)
            if mem.status in ("left", "kicked"):
                miss.append(c)
        except Exception:
            pass
    return miss


class Guard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user or user.is_bot:
            return await handler(event, data)
        ref = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start "):
            arg = event.text.split(maxsplit=1)[1].strip()
            if arg.isdigit() and int(arg) != user.id:
                ref = int(arg)
        await ensure_user(user, ref)
        if is_admin(user.id):
            return await handler(event, data)
        u = await get_user(user.id)
        if u["banned"]:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 আপনাকে ব্যান করা হয়েছে।", show_alert=True)
            else:
                await event.answer("🚫 <b>আপনাকে ব্যান করা হয়েছে।</b>")
            return
        if not (isinstance(event, CallbackQuery) and event.data == "chk"):
            miss = await missing_channels(user.id)
            if miss:
                rows = [[InlineKeyboardButton(text=f"📢 Join {c['title'] or c['chat']}", url=c["link"], style="primary")]
                        for c in miss if c["link"]]
                rows.append([ib("joined", callback_data="chk")])
                tgt = event.message if isinstance(event, CallbackQuery) else event
                await tgt.answer("🔒 <b>বট ব্যবহার করতে আগে নিচের চ্যানেলগুলোতে জয়েন করুন:</b>", reply_markup=IM(rows))
                if isinstance(event, CallbackQuery):
                    await event.answer()
                return
        return await handler(event, data)


# ======================================================================
#   MENU DISPATCH (reply keyboard) - sabse pehle register, taaki kisi bhi
#   state me menu button dabane par state clear ho jaye
# ======================================================================
MENU_H = {}   # neeche fill hota hai


@r.message(MenuF())
async def on_menu(m: Message, state: FSMContext, mkey: str):
    await state.clear()
    if (mkey.startswith("a_") or mkey in ("admin", "usermenu")) and not is_admin(m.from_user.id):
        return
    await MENU_H[mkey](m, state)


@r.callback_query(F.data.startswith("menu:"))
async def cb_menu(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":", 1)[1]
    if key not in MENU_KEYS:
        await c.answer("Unknown menu", show_alert=True)
        return
    if (key.startswith("a_") or key in ("admin", "usermenu")) and not is_admin(c.from_user.id):
        await c.answer("Not allowed", show_alert=True)
        return
    await c.answer()
    await state.clear()
    await MENU_H[key](c.message, state)


# ======================================================================
#                          START / MAIN MENU
# ======================================================================
def welcome_text(name):
    return (f"{em('tutorial')} <b>Welcome to {esc(SHOP_NAME)}</b>\n\n"
            f"👋 <b>{esc(name)}</b>, নিচের মেনু থেকে অপশন সিলেক্ট করুন।")


@r.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(welcome_text(m.from_user.full_name), reply_markup=main_kb(m.from_user.id))


@r.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("✅ <b>Cancelled</b>", reply_markup=main_kb(m.from_user.id))


@r.callback_query(F.data == "chk")
async def cb_chk(c: CallbackQuery):
    if await missing_channels(c.from_user.id):
        await c.answer("❌ আগে সব চ্যানেলে জয়েন করুন।", show_alert=True)
        return
    await c.answer()
    await c.message.answer(welcome_text(c.from_user.full_name), reply_markup=main_kb(c.from_user.id))


@r.callback_query(F.data == "noop")
async def cb_noop(c: CallbackQuery):
    await c.answer()


# ======================================================================
#                        USER MENU HANDLERS
# ======================================================================
async def cats_view():
    cats = await fetchall("SELECT * FROM categories ORDER BY id")
    if not cats:
        return "❌ <b>এখনো কোনো ক্যাটাগরি নেই।</b>", None
    rows = []
    for i in range(0, len(cats), 2):
        rows.append([dib(c["name"], f"cat:{c['id']}", c["emoji_id"]) for c in cats[i:i + 2]])
    return f"{em('buy')} <b>প্যাকেজ সিলেক্ট করুন</b>", IM(rows)


async def h_buy(m, state):
    t, kb = await cats_view()
    await m.answer(t, reply_markup=kb)


async def prods_view(cid, uid):
    cat = await fetchone("SELECT * FROM categories WHERE id=?", (cid,))
    if not cat:
        return "❌ ক্যাটাগরি পাওয়া যায়নি।", None
    u = await get_user(uid)
    prods = await fetchall("SELECT * FROM products WHERE cat_id=? ORDER BY id", (cid,))
    rows = []
    for p in prods:
        price = p["rprice"] if u["reseller"] else p["price"]
        s = await stock_count(p["id"])
        rows.append([dib(f"{p['name']} | {fp(price)}৳ | Stock: {s}", f"prod:{p['id']}", p["emoji_id"], "🌐")])
    rows.append([ib("back", callback_data="buy_back")])
    return f"{cem(cat['emoji_id'], '🌐')} <b>{esc(cat['name'])} প্রোডাক্টস:</b>", IM(rows)


@r.callback_query(F.data == "buy_back")
async def cb_buy_back(c: CallbackQuery):
    await c.answer()
    t, kb = await cats_view()
    await show(c, t, kb)


@r.callback_query(F.data.startswith("cat:"))
async def cb_cat(c: CallbackQuery):
    await c.answer()
    t, kb = await prods_view(int(c.data.split(":")[1]), c.from_user.id)
    await show(c, t, kb)


@r.callback_query(F.data.startswith("prod:"))
async def cb_prod(c: CallbackQuery):
    await c.answer()
    pid = int(c.data.split(":")[1])
    p = await fetchone("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return
    u = await get_user(c.from_user.id)
    price = p["rprice"] if u["reseller"] else p["price"]
    s = await stock_count(pid)
    txt = (f"{em('tutorial')} <b>কয়টি নিতে চান</b>\n━━━━━━━━━━━━━━\n"
           f"📌 Product: <b>{esc(p['name'])}</b>\n💲 Price: <b>{price:g} BDT / pcs</b>\n🔥 Stock: <b>{s} pcs</b>")
    kb = IM([
        [dib("1 pcs", f"q:{pid}:1", default="👑"), dib("3 pcs", f"q:{pid}:3", default="👑")],
        [dib("5 pcs", f"q:{pid}:5", default="👑"), dib("10 pcs", f"q:{pid}:10", default="👑", style="danger")],
        [ib("enterqty", callback_data=f"qe:{pid}")],
        [ib("back", callback_data=f"cat:{p['cat_id']}")],
    ])
    await show(c, txt, kb)


async def purchase(uid, pid, n):
    async with BUY_LOCK:
        u = await get_user(uid)
        p = await fetchone("SELECT * FROM products WHERE id=?", (pid,))
        if not p:
            return "err", "❌ প্রোডাক্ট পাওয়া যায়নি।"
        if n < 1 or n > MAX_QTY:
            return "err", f"❌ সর্বনিম্ন 1 এবং সর্বোচ্চ {MAX_QTY} পিস নেওয়া যাবে।"
        rows = await fetchall("SELECT id,data FROM stock WHERE product_id=? AND sold=0 ORDER BY id LIMIT ?", (pid, n))
        if len(rows) < n:
            return "err", f"❌ পর্যাপ্ত স্টক নেই। Available: {len(rows)} pcs"
        price = p["rprice"] if u["reseller"] else p["price"]
        total = round(price * n, 2)
        if u["balance"] + 1e-9 < total:
            return "nobal", total
        ids = [x["id"] for x in rows]
        items = [x["data"] for x in rows]
        try:
            ph = ",".join("?" * len(ids))
            await DB.execute(f"UPDATE stock SET sold=1, buyer=?, sold_at=? WHERE id IN ({ph})", [uid, now(), *ids])
            await DB.execute("UPDATE users SET balance=balance-? WHERE id=?", (total, uid))
            cur = await DB.execute(
                "INSERT INTO orders(user_id,product_id,product_name,qty,total,created,items) VALUES(?,?,?,?,?,?,?)",
                (uid, pid, p["name"], n, total, now(), "\n".join(items)))
            await DB.commit()
        except Exception:
            await DB.rollback()
            raise
        left = await stock_count(pid)
        u2 = await get_user(uid)
        return "ok", dict(oid=cur.lastrowid, items=items, total=total, name=p["name"], left=left, bal=u2["balance"])


async def do_buy(target: Message, uid, pid, n):
    st, res = await purchase(uid, pid, n)
    if st == "err":
        await target.answer(res)
        return
    if st == "nobal":
        await target.answer(f"❌ <b>আপনার ব্যালেন্স যথেষ্ট নয়!</b>\nপ্রয়োজন: <b>{money(res)}</b>\nআগে Deposit করুন।")
        return
    head = (f"{em('paydone')} <b>Purchase Successful!</b>\n━━━━━━━━━━━━━━\n📌 Product: <b>{esc(res['name'])}</b>\n"
            f"🔢 Quantity: <b>{n} pcs</b>\n💰 Cost: <b>{money(res['total'])}</b>\n"
            f"💳 Balance: <b>{money(res['bal'])}</b>\n🧾 Order ID: <b>#{res['oid']}</b>")
    body = "\n".join(f"<code>{esc(x)}</code>" for x in res["items"])
    if n <= 20 and len(body) < 3300:
        await target.answer(f"{head}\n\n{body}")
    else:
        await target.answer(head)
        await target.answer_document(BufferedInputFile("\n".join(res["items"]).encode(), f"order_{res['oid']}.txt"))
    u = await get_user(uid)
    await notify_admins(
        f"{em('buy')} <b>New Purchase!</b>\n━━━━━━━━━━━━━━\n👤 {esc(u['name'])} (@{esc(u['username'] or '-')})\n"
        f"🆔 <code>{uid}</code>\n📌 {esc(res['name'])}\n🔢 Qty: <b>{n}</b>\n💰 Total: <b>{money(res['total'])}</b>\n"
        f"📦 Stock left: <b>{res['left']}</b>")


@r.callback_query(F.data.startswith("q:"))
async def cb_qty(c: CallbackQuery):
    await c.answer()
    _, pid, n = c.data.split(":")
    await do_buy(c.message, c.from_user.id, int(pid), int(n))


@r.callback_query(F.data.startswith("qe:"))
async def cb_qty_enter(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.qty)
    await state.update_data(pid=int(c.data.split(":")[1]))
    await c.message.answer("✏️ <b>কয়টি নিতে চান সংখ্যা লিখুন:</b>")


@r.message(S.qty, F.text)
async def st_qty(m: Message, state: FSMContext):
    if not m.text.strip().isdigit():
        await m.answer("❌ শুধু সংখ্যা লিখুন।")
        return
    d = await state.get_data()
    await state.clear()
    await do_buy(m, m.from_user.id, d["pid"], int(m.text.strip()))


# ---------------- profile / voucher ----------------
async def h_profile(m, state):
    u = await get_user(m.from_user.id)
    o = await fetchone("SELECT COALESCE(SUM(qty),0) q FROM orders WHERE user_id=?", (u["id"],))
    rf = await fetchone("SELECT COUNT(*) c FROM users WHERE referrer=?", (u["id"],))
    reseller_line = "🤝 Account: <b>Reseller</b>\n" if u["reseller"] else ""
    txt = (f"{em('profile')} <b>My Profile</b>\n━━━━━━━━━━━━━━\n"
           f"👑 Name: <b>{esc(u['name'])}</b>\n⚙️ User ID: <code>{u['id']}</code>\n"
           f"🌐 Username: @{esc(u['username'] or '-')}\n💰 Balance: <b>{money(u['balance'])}</b>\n"
           f"🧾 Total Orders: <b>{o['q']}</b>\n👥 Referrals: <b>{rf['c']}</b>\n"
           f"{reseller_line}━━━━━━━━━━━━━━\n"
           f"🔗 Referral Link:\n<code>https://t.me/{BOT_USERNAME}?start={u['id']}</code>")
    await m.answer(txt, reply_markup=IM([[ib("applyvoucher", callback_data="vch")]]))


@r.callback_query(F.data == "vch")
async def cb_vch(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.voucher)
    await c.message.answer("🎁 <b>আপনার Voucher Code লিখুন:</b>")


@r.message(S.voucher, F.text)
async def st_voucher(m: Message, state: FSMContext):
    await state.clear()
    code = m.text.strip().upper()
    v = await fetchone("SELECT * FROM vouchers WHERE code=?", (code,))
    if not v:
        await m.answer("❌ <b>Invalid Voucher Code।</b>")
        return
    if v["used"] >= v["max_uses"]:
        await m.answer("❌ <b>এই Voucher এর লিমিট শেষ।</b>")
        return
    if await fetchone("SELECT 1 FROM voucher_uses WHERE code=? AND user_id=?", (code, m.from_user.id)):
        await m.answer("❌ <b>আপনি আগেই এই Voucher ব্যবহার করেছেন।</b>")
        return
    await DB.execute("UPDATE vouchers SET used=used+1 WHERE code=?", (code,))
    await DB.execute("INSERT INTO voucher_uses(code,user_id) VALUES(?,?)", (code, m.from_user.id))
    await DB.execute("UPDATE users SET balance=balance+? WHERE id=?", (v["amount"], m.from_user.id))
    await DB.commit()
    await m.answer(f"✅ <b>Voucher Applied!</b>\n+{money(v['amount'])} যোগ হয়েছে।")


# ---------------- deposit ----------------
async def h_deposit(m, state):
    rows = [[ib("bkash", callback_data="dm:bkash"), ib("nagad", callback_data="dm:nagad")],
            [ib("rocket", callback_data="dm:rocket"), ib("binance", callback_data="dm:binance")]]
    await m.answer(f"{em('deposit')} <b>Deposit Method সিলেক্ট করুন:</b>", reply_markup=IM(rows))


@r.callback_query(F.data.startswith("dm:"))
async def cb_dm(c: CallbackQuery, state: FSMContext):
    await c.answer()
    meth = c.data.split(":")[1]
    await state.set_state(S.dep_amount)
    await state.update_data(method=meth)
    await c.message.answer(f"{em(meth)} <b>{PAY_NAMES[meth].upper()}</b>\nকত টাকা ডিপোজিট করবেন লিখুন:")


@r.message(S.dep_amount, F.text)
async def st_dep_amount(m: Message, state: FSMContext):
    try:
        amt = float(m.text.strip())
    except ValueError:
        await m.answer("❌ শুধু সংখ্যা লিখুন।")
        return
    mn = float(SET.get("min_dep") or 20)
    if amt < mn:
        await m.answer(f"❌ <b>সর্বনিম্ন {mn:g} টাকা লিখতে হবে।</b>")
        return
    d = await state.get_data()
    meth = d["method"]
    await state.update_data(amount=amt)
    label = "Binance Pay ID" if meth == "binance" else "নাম্বার"
    await m.answer(
        f"{em(meth)} <b>Deposit Request</b>\n\nMethod: <b>{PAY_NAMES[meth]}</b>\nAmount: <b>{money(amt)}</b>\n\n"
        f"এই {label}-এ টাকা পাঠান: <code>{esc(SET.get(meth, ''))}</code>\n\nপেমেন্ট সম্পন্ন হলে নিচের বাটনে ক্লিক করুন:",
        reply_markup=IM([[ib("paydone", callback_data="pd")]]))


@r.callback_query(F.data == "pd")
async def cb_pd(c: CallbackQuery, state: FSMContext):
    await c.answer()
    d = await state.get_data()
    if not d.get("amount"):
        await c.message.answer("❌ Session শেষ। আবার Deposit চাপুন।")
        return
    await state.set_state(S.dep_trx)
    await c.message.answer("⚙️ <b>Transaction ID (TrxID) দিন:</b>")


@r.message(S.dep_trx, F.text)
async def st_dep_trx(m: Message, state: FSMContext):
    trx = m.text.strip()
    if await fetchone("SELECT 1 FROM deposits WHERE lower(trx)=lower(?) AND status!='rejected'", (trx,)):
        await m.answer("❌ <b>এই TrxID আগেই ব্যবহার করা হয়েছে।</b>")
        return
    await state.update_data(trx=trx)
    await state.set_state(S.dep_shot)
    await m.answer("📸 <b>পেমেন্টের Screenshot পাঠান:</b>")


def dep_caption(u, method, amount, trx, did, status=None):
    s = f"\n\n<b>Status: {status}</b>" if status else ""
    return (f"🚨 <b>Deposit Request #{did}</b>\n━━━━━━━━━━━━━━\n👤 {esc(u['name'])} (@{esc(u['username'] or '-')})\n"
            f"🆔 <code>{u['id']}</code>\nMethod: <b>{PAY_NAMES.get(method, method)}</b>\n"
            f"Amount: <b>{money(amount)}</b>\nTrxID: <code>{esc(trx)}</code>{s}")


def dep_kb(did):
    return IM([[ib("approve", callback_data=f"da:{did}"), ib("reject", callback_data=f"dr:{did}")]])


@r.message(S.dep_shot, F.photo)
async def st_dep_shot(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    fid = m.photo[-1].file_id
    cur = await run("INSERT INTO deposits(user_id,method,amount,trx,photo,created) VALUES(?,?,?,?,?,?)",
                    (m.from_user.id, d["method"], d["amount"], d["trx"], fid, now()))
    did = cur.lastrowid
    await m.answer(
        f"🚨 <b>Deposit Request Submitted</b>\n\nAmount: <b>{d['amount']:g} BDT</b>\nMethod: <b>{PAY_NAMES[d['method']]}</b>\n"
        f"TrxID: <code>{esc(d['trx'])}</code>\n\nআপনার payment এখন Admin verification-এর জন্য pending আছে। "
        f"Verify হওয়ার পর balance যোগ হবে।\nকোনো সমস্যা থাকলে সাপোর্টে যোগাযোগ করুন।")
    u = await get_user(m.from_user.id)
    for a in admin_ids():
        try:
            await bot.send_photo(a, fid, caption=dep_caption(u, d["method"], d["amount"], d["trx"], did),
                                 reply_markup=dep_kb(did))
        except Exception:
            pass


@r.message(S.dep_shot)
async def st_dep_shot_bad(m: Message):
    await m.answer("❌ <b>Screenshot (ছবি) পাঠান।</b>")


@r.callback_query(A, F.data.regexp(r"^d[ar]:\d+$"))
async def cb_dep_decide(c: CallbackQuery):
    act, did = c.data.split(":")
    did = int(did)
    d = await fetchone("SELECT * FROM deposits WHERE id=?", (did,))
    if not d:
        await c.answer("Not found", show_alert=True)
        return
    ok = act == "da"
    cur = await run("UPDATE deposits SET status=?, decided=? WHERE id=? AND status='pending'",
                    ("approved" if ok else "rejected", now(), did))
    if cur.rowcount == 0:
        await c.answer("⚠️ আগেই প্রসেস করা হয়েছে।", show_alert=True)
        return
    u = await get_user(d["user_id"])
    if ok:
        await run("UPDATE users SET balance=balance+? WHERE id=?", (d["amount"], d["user_id"]))
    await c.answer("Done")
    cap = dep_caption(u, d["method"], d["amount"], d["trx"], did, "✅ APPROVED" if ok else "❌ REJECTED")
    try:
        await c.message.edit_caption(caption=cap)
    except TelegramBadRequest:
        try:
            await c.message.edit_text(cap)
        except TelegramBadRequest:
            pass
    try:
        if ok:
            await bot.send_message(d["user_id"], f"✅ <b>Approved: {money(d['amount'])}</b>\nআপনার ব্যালেন্সে যোগ হয়েছে।")
        else:
            await bot.send_message(d["user_id"], f"❌ <b>Rejected: {money(d['amount'])}</b>\nTrxID: <code>{esc(d['trx'])}</code>\n"
                                                 f"সমস্যা থাকলে Support-এ যোগাযোগ করুন।")
    except Exception:
        pass


# ---------------- get code (history + 2FA) ----------------
async def h_getcode(m, state):
    # Get Code is now History-only: 2FA option removed.
    kb = IM([[ib("buyhist", callback_data="bh")], [ib("rechist", callback_data="rh")]])
    await m.answer(f"{em('getcode')} <b>History</b>\nনিচের History অপশন সিলেক্ট করুন:", reply_markup=kb)


@r.callback_query(F.data == "bh")
async def cb_bh(c: CallbackQuery):
    await c.answer()
    uid = c.from_user.id
    t0, t1 = day_bounds()
    q = "SELECT COALESCE(SUM(qty),0) q, COALESCE(SUM(total),0) s FROM orders WHERE user_id=?"
    tot = await fetchone(q, (uid,))
    td = await fetchone(q + " AND created>=?", (uid, t0))
    yd = await fetchone(q + " AND created>=? AND created<?", (uid, t1, t0))
    last = await fetchall("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    lines = "\n".join(f"• #{o['id']} {esc(o['product_name'])} ×{o['qty']} — {o['total']:g}৳ ({fdate(o['created'])})" for o in last) or "—"
    await c.message.answer(
        f"{em('buyhist')} <b>Buy History</b>\n━━━━━━━━━━━━━━\n"
        f"📅 Today: <b>{td['q']} pcs</b> | {td['s']:g}৳\n📅 Yesterday: <b>{yd['q']} pcs</b> | {yd['s']:g}৳\n"
        f"📦 Total Bought: <b>{tot['q']} pcs</b> | {tot['s']:g}৳\n━━━━━━━━━━━━━━\n<b>Last 10 Orders:</b>\n{lines}")


@r.callback_query(F.data == "rh")
async def cb_rh(c: CallbackQuery):
    await c.answer()
    uid = c.from_user.id
    t0, t1 = day_bounds()
    q = "SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE user_id=? AND status='approved'"
    tot = await fetchone(q, (uid,))
    td = await fetchone(q + " AND created>=?", (uid, t0))
    yd = await fetchone(q + " AND created>=? AND created<?", (uid, t1, t0))
    last = await fetchall("SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    ic = {"approved": "✅", "pending": "⏳", "rejected": "❌"}
    lines = "\n".join(f"• {ic[d['status']]} {d['amount']:g}৳ {PAY_NAMES.get(d['method'])} ({fdate(d['created'])})" for d in last) or "—"
    await c.message.answer(
        f"{em('rechist')} <b>Recharge History</b>\n━━━━━━━━━━━━━━\n"
        f"📅 Today Recharge: <b>{td['s']:g}৳</b>\n📅 Yesterday Recharge: <b>{yd['s']:g}৳</b>\n"
        f"💰 Total Recharge: <b>{tot['s']:g}৳</b>\n━━━━━━━━━━━━━━\n<b>Last 10 Deposits:</b>\n{lines}")


@r.callback_query(F.data == "tf")
async def cb_tf(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.twofa)
    await c.message.answer("🔐 <b>আপনার 2FA Secret Key পাঠান:</b>\n(মেনু বাটন চাপলে বের হয়ে যাবেন)")


@r.message(S.twofa, F.text)
async def st_twofa(m: Message):
    try:
        code, left = totp(m.text)
        await m.answer(f"🔐 <b>2FA Code:</b> <code>{code}</code>\n⏳ {left} সেকেন্ড বৈধ")
    except Exception:
        await m.answer("❌ <b>Invalid Secret Key।</b>")


# ---------------- support (live chat) ----------------
async def h_support(m, state):
    await state.set_state(S.support)
    su = (SET.get("support_user") or "").strip().lstrip("@")
    kb = IM([[ib("contact", url=f"https://t.me/{su}")]]) if su else None
    await m.answer(f"{em('support')} <b>Support Center</b>\n━━━━━━━━━━━━━━\n"
                   f"আপনার সমস্যা বা প্রশ্ন বিস্তারিত লিখে মেসেজ করুন। অ্যাডমিনরা শীঘ্রই বটের মাধ্যমে আপনাকে রিপ্লে দেবেন।"
                   + (f"\n\nসরাসরি যোগাযোগ: @{esc(su)}" if su else ""), reply_markup=kb)


@r.message(S.support)
async def st_support(m: Message):
    u = m.from_user
    head = (f"📩 <b>Support Message</b>\n👤 {esc(u.full_name)} (@{esc(u.username or '-')})\n🆔 ID: <code>{u.id}</code>")
    kb = IM([[ib("reply", callback_data=f"sr:{u.id}")]])
    for a in admin_ids():
        try:
            h = await bot.send_message(a, head, reply_markup=kb)
            cp = await bot.copy_message(a, m.chat.id, m.message_id)
            SUPMAP[(a, h.message_id)] = u.id
            SUPMAP[(a, cp.message_id)] = u.id
        except Exception:
            pass
    if len(SUPMAP) > 5000:
        SUPMAP.clear()
    await m.answer("✅ <b>আপনার মেসেজটি অ্যাডমিনদের কাছে পাঠানো হয়েছে।</b> অপেক্ষা করুন, খুব শীঘ্রই রিপ্লে পাবেন।")


async def send_admin_reply(m: Message, uid):
    head = f"{em('a_admins')} <b>Reply from Admin ({esc(m.from_user.full_name)})</b>"
    try:
        if m.text:
            await bot.send_message(uid, f"{head}\n━━━━━━━━━━━━━━\n{esc(m.text)}")
        else:
            await bot.send_message(uid, head)
            await bot.copy_message(uid, m.chat.id, m.message_id)
        await m.answer("✅ Reply পাঠানো হয়েছে।")
    except Exception:
        await m.answer("❌ ইউজারকে মেসেজ পাঠানো যায়নি (বট ব্লক করেছে?)")


@r.callback_query(A, F.data.startswith("sr:"))
async def cb_sr(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.a_reply)
    await state.update_data(uid=int(c.data.split(":")[1]))
    await c.message.answer("↩️ <b>ইউজারের জন্য রিপ্লে লিখুন:</b>")


async def h_tutorial(m, state):
    t = SET.get("tutorial", "").strip()
    await m.answer(f"{em('tutorial')} <b>Tutorial</b>\n━━━━━━━━━━━━━━\n{esc(t) if t else 'Tutorial এখনো সেট করা হয়নি।'}")


# ======================================================================
#                        ADMIN PANEL – MENUS
# ======================================================================
async def h_admin(m, state):
    await m.answer(f"{em('admin')} <b>Welcome Admin</b>", reply_markup=admin_kb())


async def h_usermenu(m, state):
    await m.answer("✅ <b>মূল মেনু:</b>", reply_markup=main_kb(m.from_user.id))


async def h_a_prod(m, state):
    kb = IM([[ib("addcat", callback_data="pcm:addcat"), ib("addprod", callback_data="pcat:ap")],
             [ib("chprice", callback_data="pcat:cp")],
             [ib("delcat", callback_data="pcat:dc")],
             [ib("delprod", callback_data="pcat:dp")],
             [ib("delstock", callback_data="pcat:ds")]])
    await m.answer(f"{em('a_prod')} <b>Product Management:</b>", reply_markup=kb)


async def pick_cat_kb(action):
    cats = await fetchall("SELECT * FROM categories ORDER BY id")
    rows = []
    for i in range(0, len(cats), 2):
        rows.append([dib(c["name"], f"pc:{action}:{c['id']}", c["emoji_id"]) for c in cats[i:i + 2]])
    if not rows:
        rows = [[dib("কোনো ক্যাটাগরি নেই", "noop", default="❌", style="danger")]]
    return IM(rows)


async def h_a_addstock(m, state):
    await m.answer(f"{em('a_addstock')} <b>কোন ক্যাটাগরিতে স্টক অ্যাড করবেন?</b>", reply_markup=await pick_cat_kb("as"))


@r.callback_query(A, F.data.startswith("pcat:"))
async def cb_pcat(c: CallbackQuery):
    await c.answer()
    await show(c, "📁 <b>ক্যাটাগরি সিলেক্ট করুন:</b>", await pick_cat_kb(c.data.split(":")[1]))


@r.callback_query(A, F.data == "pcm:addcat")
async def cb_addcat(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.a_cat_name)
    await c.message.answer("📁 <b>নতুন ক্যাটাগরির নাম লিখুন:</b>")


@r.message(A, S.a_cat_name, F.text)
async def st_cat_name(m: Message, state: FSMContext):
    await state.clear()
    await run("INSERT INTO categories(name) VALUES(?)", (m.text.strip(),))
    await m.answer(f"✅ <b>Category Added:</b> {esc(m.text.strip())}")


@r.callback_query(A, F.data.startswith("pc:"))
async def cb_pc(c: CallbackQuery, state: FSMContext):
    await c.answer()
    _, act, cid = c.data.split(":")
    cid = int(cid)
    cat = await fetchone("SELECT * FROM categories WHERE id=?", (cid,))
    if not cat:
        return
    if act == "ap":
        await state.set_state(S.a_prod_name)
        await state.update_data(cid=cid)
        await c.message.answer(f"📦 <b>{esc(cat['name'])}</b> — প্রোডাক্টের নাম লিখুন:")
    elif act == "dc":
        await show(c, f"⚠️ <b>{esc(cat['name'])}</b> ক্যাটাগরি, এর সব প্রোডাক্ট ও স্টক মুছে যাবে। নিশ্চিত?",
                   IM([[ib("yes", callback_data=f"cf:dc:{cid}"), ib("no", callback_data="cf:no:0")]]))
    elif act == "emc":
        await state.set_state(S.a_emoji)
        await state.update_data(t="c", k=cid)
        await c.message.answer(f"✨ <b>{esc(cat['name'])}</b> — Premium Emoji ID পাঠান (বা premium emoji পাঠান)। '0' = remove")
    else:  # product pickers: as / cp / dp / ds / emp
        prods = await fetchall("SELECT * FROM products WHERE cat_id=? ORDER BY id", (cid,))
        rows = []
        for p in prods:
            n = await stock_count(p["id"])
            rows.append([dib(f"{p['name']} | {fp(p['price'])}৳ | Stock: {n}", f"pp:{act}:{p['id']}", p["emoji_id"], "🌐")])
        if not rows:
            rows = [[dib("কোনো প্রোডাক্ট নেই", "noop", default="❌", style="danger")]]
        await show(c, "🌐 <b>প্রোডাক্ট সিলেক্ট করুন:</b>", IM(rows))


@r.message(A, S.a_prod_name, F.text)
async def st_prod_name(m: Message, state: FSMContext):
    await state.update_data(name=m.text.strip())
    await state.set_state(S.a_prod_price)
    await m.answer(f"✅ প্রোডাক্টের নাম: <b>{esc(m.text.strip())}</b>\nএবার Normal Price (BDT) লিখুন:")


@r.message(A, S.a_prod_price, F.text)
async def st_prod_price(m: Message, state: FSMContext):
    try:
        p = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    await state.update_data(price=p)
    await state.set_state(S.a_prod_rprice)
    await m.answer(f"✅ Normal Price: <b>{p:g} BDT</b>\nএবার Reseller Price লিখুন:")


@r.message(A, S.a_prod_rprice, F.text)
async def st_prod_rprice(m: Message, state: FSMContext):
    try:
        rp = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    d = await state.get_data()
    await state.clear()
    await run("INSERT INTO products(cat_id,name,price,rprice) VALUES(?,?,?,?)", (d["cid"], d["name"], d["price"], rp))
    await m.answer(f"✅ <b>Product Added!</b>\nName: {esc(d['name'])}\nPrice: {d['price']:g} BDT\nReseller Price: {rp:g} BDT")


@r.callback_query(A, F.data.startswith("pp:"))
async def cb_pp(c: CallbackQuery, state: FSMContext):
    await c.answer()
    _, act, pid = c.data.split(":")
    pid = int(pid)
    p = await fetchone("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return
    await state.update_data(pid=pid)
    if act == "as":
        await state.set_state(S.a_stock)
        await c.message.answer(
            f"📦 <b>{esc(p['name'])}</b> এর জন্য Excel (.xlsx) অথবা Text (.txt) ফাইল পাঠান — অথবা সরাসরি মেসেজে লিখুন:\n\n"
            f"📌 <b>ফরম্যাট:</b> প্রতি লাইনে ১টি আইটেম।\nযেমন: <code>Host:Port:Username:Password</code> বা <code>email:password</code>\n\n"
            f"📗 <b>Excel হলে:</b> প্রতি Row = ১টি আইটেম (কলামগুলো <code>:</code> দিয়ে জোড়া লাগবে)")
    elif act == "cp":
        await state.set_state(S.a_price)
        await c.message.answer(f"💲 <b>{esc(p['name'])}</b>\nবর্তমান: {p['price']:g} BDT | Reseller: {p['rprice']:g} BDT\nনতুন Normal Price লিখুন:")
    elif act == "dp":
        await show(c, f"⚠️ <b>{esc(p['name'])}</b> ও এর সব স্টক মুছে যাবে। নিশ্চিত?",
                   IM([[ib("yes", callback_data=f"cf:dp:{pid}"), ib("no", callback_data="cf:no:0")]]))
    elif act == "ds":
        n = await stock_count(pid)
        await show(c, f"⚠️ <b>{esc(p['name'])}</b> এর <b>{n}</b>টি unsold স্টক মুছে যাবে। নিশ্চিত?",
                   IM([[ib("yes", callback_data=f"cf:ds:{pid}"), ib("no", callback_data="cf:no:0")]]))
    elif act == "emp":
        await state.set_state(S.a_emoji)
        await state.update_data(t="p", k=pid)
        await c.message.answer(f"✨ <b>{esc(p['name'])}</b> — Premium Emoji ID পাঠান (বা premium emoji পাঠান)। '0' = remove")


@r.callback_query(A, F.data.startswith("cf:"))
async def cb_confirm(c: CallbackQuery):
    await c.answer()
    _, act, i = c.data.split(":")
    if act == "no":
        await show(c, "❌ Cancelled")
        return
    i = int(i)
    if act == "dc":
        await DB.execute("DELETE FROM stock WHERE product_id IN (SELECT id FROM products WHERE cat_id=?)", (i,))
        await DB.execute("DELETE FROM products WHERE cat_id=?", (i,))
        await DB.execute("DELETE FROM categories WHERE id=?", (i,))
        msg = "✅ Category Deleted"
    elif act == "dp":
        await DB.execute("DELETE FROM stock WHERE product_id=?", (i,))
        await DB.execute("DELETE FROM products WHERE id=?", (i,))
        msg = "✅ Product Deleted"
    else:
        await DB.execute("DELETE FROM stock WHERE product_id=? AND sold=0", (i,))
        msg = "✅ Stock Deleted"
    await DB.commit()
    await show(c, msg)


@r.message(A, S.a_price, F.text)
async def st_price(m: Message, state: FSMContext):
    try:
        p = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    await state.update_data(price=p)
    await state.set_state(S.a_rprice)
    await m.answer(f"✅ Normal Price: <b>{p:g}</b>\nএবার নতুন Reseller Price লিখুন:")


@r.message(A, S.a_rprice, F.text)
async def st_rprice(m: Message, state: FSMContext):
    try:
        rp = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    d = await state.get_data()
    await state.clear()
    await run("UPDATE products SET price=?, rprice=? WHERE id=?", (d["price"], rp, d["pid"]))
    await m.answer(f"✅ <b>Price Updated!</b>\nNormal: {d['price']:g} BDT\nReseller: {rp:g} BDT")


@r.message(A, S.a_stock)
async def st_stock(m: Message, state: FSMContext):
    d = await state.get_data()
    items = []
    try:
        if m.document:
            name = (m.document.file_name or "").lower()
            buf = io.BytesIO()
            await bot.download(m.document, destination=buf)
            data = buf.getvalue()
            items = await asyncio.to_thread(parse_xlsx if name.endswith((".xlsx", ".xlsm")) else parse_txt, data)
        elif m.text:
            items = parse_txt(m.text.encode())
    except Exception as e:
        await m.answer(f"❌ ফাইল পড়া যায়নি: {esc(str(e))}")
        return
    if not items:
        await m.answer("❌ কোনো আইটেম পাওয়া যায়নি। .txt/.xlsx ফাইল বা টেক্সট পাঠান।")
        return
    await state.clear()
    await DB.executemany("INSERT INTO stock(product_id,data) VALUES(?,?)", [(d["pid"], x) for x in items])
    await DB.commit()
    p = await fetchone("SELECT name FROM products WHERE id=?", (d["pid"],))
    await m.answer(f"✅ <b>Stock Added!</b>\n📦 {esc(p['name'])}\n➕ Added: <b>{len(items)}</b>\n🔥 Total Stock: <b>{await stock_count(d['pid'])}</b>")


async def h_a_live(m, state):
    cats = await fetchall("SELECT * FROM categories ORDER BY id")
    if not cats:
        await m.answer("❌ কোনো ক্যাটাগরি নেই।")
        return
    out = f"{em('a_live')} <b>Live Stock</b>\n"
    for cat in cats:
        out += f"\n📁 <b>{esc(cat['name'])}</b>\n"
        prods = await fetchall("SELECT * FROM products WHERE cat_id=?", (cat["id"],))
        for p in prods:
            n = await stock_count(p["id"])
            out += f"  🌐 <b>{esc(p['name'])}</b> | Price: {fp(p['price'])}৳ (Reseller: {fp(p['rprice'])}৳) | Stock: <b>{n}</b>\n"
        if not prods:
            out += "  —\n"
    for i in range(0, len(out), 3800):
        await m.answer(out[i:i + 3800])


# ---------------- user management ----------------
async def h_a_users(m, state):
    await state.set_state(S.a_user)
    await m.answer("👥 <b>ইউজারের টেলিগ্রাম ID বা Username দিন:</b>")


async def user_card_view(uid):
    u = await get_user(uid)
    o = await fetchone("SELECT COALESCE(SUM(qty),0) q FROM orders WHERE user_id=?", (uid,))
    txt = (f"👥 <b>USER PROFILE</b>\n━━━━━━━━━━━━━━\n👑 Name: <b>{esc(u['name'])}</b>\n⚙️ ID: <code>{u['id']}</code>\n"
           f"🌐 Username: @{esc(u['username'] or '-')}\n💰 Balance: <b>{money(u['balance'])}</b>\n"
           f"🧾 Orders: <b>{o['q']}</b>\n🤝 Reseller: <b>{'Yes' if u['reseller'] else 'No'}</b>\n"
           f"Status: <b>{'🚫 Banned' if u['banned'] else '✅ Active'}</b>\n━━━━━━━━━━━━━━")
    kb = IM([[ib("unban", callback_data=f"um:unban:{uid}") if u["banned"] else ib("ban", callback_data=f"um:ban:{uid}")],
             [ib("addbal", callback_data=f"um:add:{uid}"), ib("cutbal", callback_data=f"um:cut:{uid}")],
             [ib("sendmsg", callback_data=f"um:msg:{uid}")]])
    return txt, kb


@r.message(A, S.a_user, F.text)
async def st_a_user(m: Message, state: FSMContext):
    u = await find_user(m.text)
    if not u:
        await m.answer("❌ ইউজার পাওয়া যায়নি (ইউজারকে অবশ্যই একবার বট চালু করতে হবে)।")
        return
    await state.clear()
    t, kb = await user_card_view(u["id"])
    await m.answer(t, reply_markup=kb)


@r.callback_query(A, F.data.startswith("um:"))
async def cb_um(c: CallbackQuery, state: FSMContext):
    await c.answer()
    _, act, uid = c.data.split(":")
    uid = int(uid)
    if act in ("ban", "unban"):
        await run("UPDATE users SET banned=? WHERE id=?", (1 if act == "ban" else 0, uid))
        t, kb = await user_card_view(uid)
        await show(c, t, kb)
    elif act in ("add", "cut"):
        await state.set_state(S.a_bal)
        await state.update_data(uid=uid, mode=act)
        await c.message.answer(f"💰 কত টাকা {'Add' if act == 'add' else 'Cut'} করবেন লিখুন:")
    elif act == "msg":
        await state.set_state(S.a_msg)
        await state.update_data(uid=uid)
        await c.message.answer("✉️ ইউজারকে যে মেসেজ পাঠাতে চান সেটা পাঠান:")


@r.message(A, S.a_bal, F.text)
async def st_a_bal(m: Message, state: FSMContext):
    try:
        amt = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    d = await state.get_data()
    await state.clear()
    sign = 1 if d["mode"] == "add" else -1
    await run("UPDATE users SET balance=balance+? WHERE id=?", (sign * amt, d["uid"]))
    await m.answer(f"✅ <b>{money(amt)}</b> {'যোগ করা' if sign > 0 else 'কেটে নেওয়া'} হয়েছে।")
    try:
        await bot.send_message(d["uid"], f"{'✅ +' if sign > 0 else '➖ -'}<b>{money(amt)}</b> আপনার ব্যালেন্সে {'যোগ' if sign > 0 else 'কাটা'} হয়েছে।")
    except Exception:
        pass


@r.message(A, S.a_msg)
async def st_a_msg(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    try:
        await bot.copy_message(d["uid"], m.chat.id, m.message_id)
        await m.answer("✅ মেসেজ পাঠানো হয়েছে।")
    except Exception:
        await m.answer("❌ পাঠানো যায়নি।")


@r.message(A, S.a_reply)
async def st_a_reply(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    await send_admin_reply(m, d["uid"])


@r.message(A, SupReplyF())
async def sup_reply_by_reply(m: Message, sup_uid: int):
    await send_admin_reply(m, sup_uid)


# ---------------- deposits (admin) ----------------
async def h_a_depreq(m, state):
    rows = await fetchall("SELECT * FROM deposits WHERE status='pending' ORDER BY id LIMIT 15")
    if not rows:
        await m.answer("❌ <b>কোনো পেন্ডিং ডিপোজিট নেই।</b>")
        return
    for d in rows:
        u = await get_user(d["user_id"])
        await m.answer_photo(d["photo"], caption=dep_caption(u, d["method"], d["amount"], d["trx"], d["id"]),
                             reply_markup=dep_kb(d["id"]))


async def h_a_dephist(m, state):
    t0, _ = day_bounds()
    q = "SELECT COALESCE(SUM(amount),0) s, COUNT(*) c FROM deposits WHERE status='approved'"
    tot = await fetchone(q)
    td = await fetchone(q + " AND created>=?", (t0,))
    pend = await fetchone("SELECT COUNT(*) c FROM deposits WHERE status='pending'")
    last = await fetchall("SELECT * FROM deposits ORDER BY id DESC LIMIT 20")
    ic = {"approved": "✅", "pending": "⏳", "rejected": "❌"}
    lines = "\n".join(f"{ic[d['status']]} #{d['id']} <code>{d['user_id']}</code> {d['amount']:g}৳ {PAY_NAMES.get(d['method'])} ({fdate(d['created'])})" for d in last) or "—"
    await m.answer(f"{em('a_dephist')} <b>Deposit History</b>\n━━━━━━━━━━━━━━\n📅 Today: <b>{td['s']:g}৳</b> ({td['c']})\n"
                   f"💰 Total Approved: <b>{tot['s']:g}৳</b> ({tot['c']})\n⏳ Pending: <b>{pend['c']}</b>\n━━━━━━━━━━━━━━\n{lines}")


# ---------------- broadcast ----------------
async def h_a_bcast(m, state):
    await state.set_state(S.a_bcast)
    await m.answer("📢 <b>Broadcast মেসেজ পাঠান</b> (টেক্সট/ছবি/ভিডিও যা খুশি)।\nবাতিল করতে /cancel")


@r.message(A, S.a_bcast)
async def st_bcast(m: Message, state: FSMContext):
    await state.clear()
    users = await fetchall("SELECT id FROM users WHERE banned=0")
    st = await m.answer(f"⏳ Sending to {len(users)} users...")
    ok = fail = 0
    for u in users:
        try:
            await bot.copy_message(u["id"], m.chat.id, m.message_id)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.04)
    await st.edit_text(f"📢 <b>Broadcast Done</b>\n✅ Success: <b>{ok}</b>\n❌ Failed: <b>{fail}</b>")


# ---------------- vouchers ----------------
async def h_a_voucher(m, state):
    kb = IM([[ib("vcreate", callback_data="v:new")], [ib("vlist", callback_data="v:list")], [ib("vdelete", callback_data="v:del")]])
    await m.answer(f"{em('a_voucher')} <b>Voucher Management:</b>", reply_markup=kb)


@r.callback_query(A, F.data.startswith("v:"))
async def cb_v(c: CallbackQuery, state: FSMContext):
    await c.answer()
    act = c.data.split(":")[1]
    if act == "new":
        await state.set_state(S.a_vcode)
        await c.message.answer("🎟 <b>Voucher Code লিখুন</b> (যেমন: WELCOME20):")
    elif act == "list":
        vs = await fetchall("SELECT * FROM vouchers")
        t = "\n".join(f"🎟 <code>{esc(v['code'])}</code> | {v['amount']:g}৳ | Used {v['used']}/{v['max_uses']}" for v in vs) or "কোনো Voucher নেই।"
        await c.message.answer(f"📋 <b>Vouchers</b>\n{t}")
    elif act == "del":
        vs = await fetchall("SELECT * FROM vouchers")
        rows = [[dib(f"{v['code']} ({v['amount']:g}৳)", f"vdel:{v['code']}", default="🗑", style="danger")] for v in vs]
        if rows:
            await c.message.answer("🗑 <b>কোনটি ডিলিট করবেন?</b>", reply_markup=IM(rows))
        else:
            await c.message.answer("কোনো Voucher নেই।")


@r.callback_query(A, F.data.startswith("vdel:"))
async def cb_vdel(c: CallbackQuery):
    await c.answer("Deleted")
    await run("DELETE FROM vouchers WHERE code=?", (c.data.split(":", 1)[1],))
    await show(c, "✅ Voucher Deleted")


@r.message(A, S.a_vcode, F.text)
async def st_vcode(m: Message, state: FSMContext):
    code = m.text.strip().upper()[:20]
    if not re.fullmatch(r"[A-Z0-9_\-]+", code):
        await m.answer("❌ শুধু English অক্ষর/সংখ্যা ব্যবহার করুন।")
        return
    await state.update_data(code=code)
    await state.set_state(S.a_vamt)
    await m.answer("💰 কত টাকার Voucher (BDT)?")


@r.message(A, S.a_vamt, F.text)
async def st_vamt(m: Message, state: FSMContext):
    try:
        amt = float(m.text.strip())
    except ValueError:
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    await state.update_data(amt=amt)
    await state.set_state(S.a_vuses)
    await m.answer("👥 সর্বোচ্চ কতজন ব্যবহার করতে পারবে?")


@r.message(A, S.a_vuses, F.text)
async def st_vuses(m: Message, state: FSMContext):
    if not m.text.strip().isdigit():
        await m.answer("❌ সংখ্যা লিখুন।")
        return
    d = await state.get_data()
    await state.clear()
    await run("INSERT OR REPLACE INTO vouchers(code,amount,max_uses,used) VALUES(?,?,?,0)", (d["code"], d["amt"], int(m.text.strip())))
    await m.answer(f"✅ <b>Voucher Created</b>\nCode: <code>{d['code']}</code>\nAmount: {d['amt']:g}৳\nLimit: {m.text.strip()}")


# ---------------- force join ----------------
async def h_a_force(m, state):
    chs = await fetchall("SELECT * FROM force_channels")
    t = "\n".join(f"• {esc(c['title'] or c['chat'])} (<code>{esc(c['chat'])}</code>)" for c in chs) or "কোনো চ্যানেল সেট করা নেই।"
    kb = IM([[ib("fadd", callback_data="f:add")], [ib("fremove", callback_data="f:rm")]])
    await m.answer(f"{em('a_force')} <b>Force Join Setup</b>\n━━━━━━━━━━━━━━\n{t}\n\n⚠️ বটকে চ্যানেল/গ্রুপে Admin বানাতে হবে।", reply_markup=kb)


@r.callback_query(A, F.data.startswith("f:"))
async def cb_f(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.data == "f:add":
        await state.set_state(S.a_force)
        await c.message.answer("🔒 চ্যানেলের @username বা ID (-100...) পাঠান:")
    else:
        chs = await fetchall("SELECT * FROM force_channels")
        rows = [[dib(x["title"] or x["chat"], f"frm:{x['id']}", default="🗑", style="danger")] for x in chs]
        if rows:
            await c.message.answer("🗑 <b>কোনটি রিমুভ করবেন?</b>", reply_markup=IM(rows))
        else:
            await c.message.answer("কিছু নেই।")


@r.callback_query(A, F.data.startswith("frm:"))
async def cb_frm(c: CallbackQuery):
    await c.answer("Removed")
    await run("DELETE FROM force_channels WHERE id=?", (int(c.data.split(":")[1]),))
    await show(c, "✅ Channel Removed")


@r.message(A, S.a_force, F.text)
async def st_force(m: Message, state: FSMContext):
    x = m.text.strip()
    chat = int(x) if x.lstrip("-").isdigit() else x
    try:
        ch = await bot.get_chat(chat)
    except Exception:
        await m.answer("❌ চ্যানেল পাওয়া যায়নি। বট অ্যাডমিন কিনা চেক করুন।")
        return
    await state.clear()
    link = f"https://t.me/{ch.username}" if ch.username else (ch.invite_link or "")
    await run("INSERT INTO force_channels(chat,title,link) VALUES(?,?,?)", (str(ch.id), ch.title or x, link))
    await m.answer(f"✅ <b>Added:</b> {esc(ch.title or x)}")


# ---------------- support setup / tutorial / payments ----------------
async def ask_set(m, state, key, prompt):
    await state.set_state(S.a_setval)
    await state.update_data(key=key)
    await m.answer(prompt)


async def h_a_support(m, state):
    await ask_set(m, state, "support_user", f"🎧 <b>Support Setup</b>\nবর্তমান: @{esc(SET.get('support_user') or '-')}\nনতুন Support Username লিখুন (@ ছাড়া/সহ):")


async def h_a_tutorial(m, state):
    await ask_set(m, state, "tutorial", "📚 <b>Tutorial Setup</b>\nTutorial এর টেক্সট/লিংক লিখুন (পুরো মেসেজ হিসেবে):")


async def h_a_pay(m, state):
    kb = IM([[ib("bkash", "Edit Bkash Number", callback_data="ps:bkash")],
             [ib("nagad", "Edit Nagad Number", callback_data="ps:nagad")],
             [ib("rocket", "Edit Rocket Number", callback_data="ps:rocket")],
             [ib("binance", "Edit Binance Number", callback_data="ps:binance")],
             [ib("edit_rate", f"Edit Dollar Rate (Current: {rate():g} BDT)", callback_data="ps:rate")],
             [ib("edit_min", f"Edit Minimum Deposit (Current: {SET.get('min_dep')} BDT)", callback_data="ps:min_dep")]])
    await m.answer(f"{em('a_pay')} <b>কোন পেমেন্ট মেথডের নাম্বার পরিবর্তন করবেন?</b>", reply_markup=kb)


@r.callback_query(A, F.data.startswith("ps:"))
async def cb_ps(c: CallbackQuery, state: FSMContext):
    await c.answer()
    key = c.data.split(":")[1]
    names = {"rate": "Dollar Rate (1 USD = ? BDT)", "min_dep": "Minimum Deposit (BDT)"}
    await ask_set(c.message, state, key, f"✏️ নতুন <b>{names.get(key, PAY_NAMES.get(key, key) + ' Number')}</b> লিখুন:")


@r.message(A, S.a_setval, F.text)
async def st_setval(m: Message, state: FSMContext):
    d = await state.get_data()
    key, val = d["key"], m.text.strip()
    if key in ("rate", "min_dep"):
        try:
            if float(val) <= 0:
                raise ValueError
        except ValueError:
            await m.answer("❌ সঠিক সংখ্যা লিখুন।")
            return
    if key == "support_user":
        val = val.lstrip("@")
    await state.clear()
    await set_setting(key, val)
    await m.answer("✅ <b>Updated!</b>")


# ---------------- admin mgmt (owner) / reseller ----------------
async def h_a_admins(m, state):
    if m.from_user.id not in OWNER_IDS:
        await m.answer("❌ শুধু Owner এই অপশন ব্যবহার করতে পারবে।")
        return
    t = "\n".join(f"• <code>{a}</code>" for a in sorted(ADMINS)) or "কোনো এক্সট্রা অ্যাডমিন নেই।"
    kb = IM([[ib("addadmin", callback_data="adm:add")], [ib("deladmin", callback_data="adm:del")]])
    await m.answer(f"{em('a_admins')} <b>Admin Management System:</b>\n{t}", reply_markup=kb)


@r.callback_query(A, F.data.startswith("adm:"))
async def cb_adm(c: CallbackQuery, state: FSMContext):
    await c.answer()
    if c.from_user.id not in OWNER_IDS:
        return
    if c.data == "adm:add":
        await state.set_state(S.a_admin)
        await c.message.answer("👑 নতুন Admin এর Telegram ID লিখুন:")
    else:
        rows = [[dib(str(a), f"admd:{a}", default="❌", style="danger")] for a in sorted(ADMINS)]
        if rows:
            await c.message.answer("কাকে রিমুভ করবেন?", reply_markup=IM(rows))
        else:
            await c.message.answer("কোনো এক্সট্রা অ্যাডমিন নেই।")


@r.callback_query(A, F.data.startswith("admd:"))
async def cb_admd(c: CallbackQuery):
    if c.from_user.id not in OWNER_IDS:
        await c.answer()
        return
    await c.answer("Removed")
    await run("DELETE FROM admins WHERE id=?", (int(c.data.split(":")[1]),))
    await load_cache()
    await show(c, "✅ Admin Removed")


@r.message(A, S.a_admin, F.text)
async def st_admin(m: Message, state: FSMContext):
    if m.from_user.id not in OWNER_IDS or not m.text.strip().isdigit():
        await m.answer("❌ সঠিক numeric ID দিন।")
        return
    await state.clear()
    await run("INSERT OR IGNORE INTO admins(id) VALUES(?)", (int(m.text.strip()),))
    await load_cache()
    await m.answer("✅ <b>Admin Added!</b>")


async def h_a_resell(m, state):
    rs = await fetchall("SELECT id,name FROM users WHERE reseller=1")
    t = "\n".join(f"• {esc(x['name'])} <code>{x['id']}</code>" for x in rs) or "কোনো Reseller নেই।"
    kb = IM([[ib("addresell", callback_data="rs:add"), ib("delresell", callback_data="rs:del")]])
    await m.answer(f"{em('a_resell')} <b>Reseller Management</b>\n{t}", reply_markup=kb)


@r.callback_query(A, F.data.startswith("rs:"))
async def cb_rs(c: CallbackQuery, state: FSMContext):
    await c.answer()
    await state.set_state(S.a_resell)
    await state.update_data(mode=c.data.split(":")[1])
    await c.message.answer("🤝 ইউজারের Telegram ID বা Username দিন:")


@r.message(A, S.a_resell, F.text)
async def st_resell(m: Message, state: FSMContext):
    u = await find_user(m.text)
    if not u:
        await m.answer("❌ ইউজার পাওয়া যায়নি।")
        return
    d = await state.get_data()
    await state.clear()
    on = 1 if d["mode"] == "add" else 0
    await run("UPDATE users SET reseller=? WHERE id=?", (on, u["id"]))
    await m.answer(f"✅ {esc(u['name'])} এখন {'Reseller' if on else 'Normal User'}।")
    try:
        await bot.send_message(u["id"], "🤝 <b>আপনি এখন Reseller!</b> আপনি রিসেলার প্রাইসে কিনতে পারবেন।" if on else "ℹ️ আপনার Reseller স্ট্যাটাস সরানো হয়েছে।")
    except Exception:
        pass


# ---------------- premium emoji set ----------------
EMO_KEYS = list(B.keys())


def emoji_page_kb(page):
    per = 14
    chunk = EMO_KEYS[page * per:(page + 1) * per]
    rows = []
    for i in range(0, len(chunk), 2):
        rows.append([InlineKeyboardButton(text=("✅ " if k in EMO else "") + B[k][1], callback_data=f"es:{k}", style="primary")
                     for k in chunk[i:i + 2]])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"ek:{page - 1}"))
    if (page + 1) * per < len(EMO_KEYS):
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"ek:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="📁 Category Emoji", callback_data="pcat:emc", style="success"),
                 InlineKeyboardButton(text="🌐 Product Emoji", callback_data="pcat:emp", style="success")])
    return IM(rows)


async def h_a_emoji(m, state):
    await m.answer(f"{em('a_emoji')} <b>Premium Emoji Set</b>\nযে বাটনে Premium Emoji লাগাতে চান সেটা সিলেক্ট করুন "
                   f"(✅ = emoji সেট আছে):", reply_markup=emoji_page_kb(0))


@r.callback_query(A, F.data.startswith("ek:"))
async def cb_ek(c: CallbackQuery):
    await c.answer()
    await show(c, f"{em('a_emoji')} <b>Premium Emoji Set</b>\nযে বাটনে Premium Emoji লাগাতে চান সেটা সিলেক্ট করুন:",
               emoji_page_kb(int(c.data.split(":")[1])))


@r.callback_query(A, F.data.startswith("es:"))
async def cb_es(c: CallbackQuery, state: FSMContext):
    await c.answer()
    key = c.data.split(":", 1)[1]
    if key not in B:
        return
    await state.set_state(S.a_emoji)
    await state.update_data(t="b", k=key)
    await c.message.answer(f"✨ <b>{B[key][1]}</b> বাটনের জন্য Premium Emoji ID পাঠান\n(অথবা সরাসরি একটি premium emoji পাঠান)। '0' পাঠালে remove হবে।")


@r.message(A, S.a_emoji, F.text)
async def st_emoji(m: Message, state: FSMContext):
    eid = parse_emoji_id(m)
    if eid is None:
        await m.answer("❌ শুধু Emoji ID (সংখ্যা) বা premium emoji পাঠান।")
        return
    d = await state.get_data()
    await state.clear()
    remove = eid == "0"
    if d["t"] == "b":
        if remove:
            await run("DELETE FROM emojis WHERE key=?", (d["k"],))
        else:
            await run("INSERT OR REPLACE INTO emojis(key,emoji_id) VALUES(?,?)", (d["k"], eid))
        await load_cache()
    else:
        table = "categories" if d["t"] == "c" else "products"
        await run(f"UPDATE {table} SET emoji_id=? WHERE id=?", (None if remove else eid, d["k"]))
    await m.answer(f"✅ <b>{'Removed' if remove else 'Set!'}</b> {'' if remove else cem(eid, '⭐')}", reply_markup=admin_kb())


# ---------------- statistics ----------------
async def h_a_stats(m, state):
    u = await fetchone("SELECT COUNT(*) c, COALESCE(SUM(balance),0) b FROM users")
    o = await fetchone("SELECT COALESCE(SUM(qty),0) q, COALESCE(SUM(total),0) s FROM orders")
    d = await fetchone("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE status='approved'")
    st = await fetchone("SELECT COUNT(*) c FROM stock WHERE sold=0")
    t0, _ = day_bounds()
    to = await fetchone("SELECT COALESCE(SUM(qty),0) q, COALESCE(SUM(total),0) s FROM orders WHERE created>=?", (t0,))
    nu = await fetchone("SELECT COUNT(*) c FROM users WHERE joined>=?", (t0,))
    await m.answer(f"{em('a_stats')} <b>Statistics</b>\n━━━━━━━━━━━━━━\n👥 Users: <b>{u['c']}</b> (আজ নতুন: {nu['c']})\n"
                   f"💰 User Balances: <b>{u['b']:.2f}৳</b>\n🛍 Total Sold: <b>{o['q']} pcs</b> | {o['s']:.2f}৳\n"
                   f"📅 আজকের Sale: <b>{to['q']} pcs</b> | {to['s']:.2f}৳\n💵 Total Deposit: <b>{d['s']:.2f}৳</b>\n📦 Total Stock: <b>{st['c']}</b>")


MENU_H.update({
    "buy": h_buy, "profile": h_profile, "deposit": h_deposit, "getcode": h_getcode, "support": h_support,
    "tutorial": h_tutorial, "admin": h_admin, "usermenu": h_usermenu,
    "a_prod": h_a_prod, "a_addstock": h_a_addstock, "a_live": h_a_live, "a_users": h_a_users,
    "a_depreq": h_a_depreq, "a_dephist": h_a_dephist, "a_bcast": h_a_bcast, "a_voucher": h_a_voucher,
    "a_force": h_a_force, "a_support": h_a_support, "a_admins": h_a_admins, "a_pay": h_a_pay,
    "a_resell": h_a_resell, "a_tutorial": h_a_tutorial, "a_emoji": h_a_emoji, "a_stats": h_a_stats,
})


# ======================================================================
#                                 MAIN
# ======================================================================
async def main():
    global bot, BOT_USERNAME
    logging.basicConfig(level=logging.INFO)
    await init_db()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    BOT_USERNAME = (await bot.get_me()).username
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(Guard())
    dp.callback_query.outer_middleware(Guard())
    dp.include_router(r)
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot started as @%s", BOT_USERNAME)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
