# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  LEGION ORGANIZATOR  —  @LegionOrganizatorBot                 ║
║  Mafia guruhlar ittifoqi uchun professional boshqaruv boti    ║
╚══════════════════════════════════════════════════════════════╝

O'RNATISH:
    pip install "aiogram>=3.13"

ENV O'ZGARUVCHILARI (Railway / .env):
    BOT_TOKEN     = BotFather tokeni                     (majburiy)
    OWNER_IDS     = 123456789,987654321  (egalar ID)      (majburiy)
    DB_PATH       = legion.db                             (ixtiyoriy)

BIRINCHI SOZLASH:
    1) Botni ishga tushiring, /start -> «👑 Boshqaruv paneli».
    2) Ittifoq guruhingizga botni TO'LIQ ADMIN qiling va guruhda /bind yozing.
    3) Panel -> Mezonlar bo'limida qabul mezonlarini sozlang.
"""
import asyncio
import difflib
import html
import json
import logging
import os
import random
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import BaseFilter, Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand, CallbackQuery, ChatJoinRequest, ChatMemberUpdated,
    InlineKeyboardButton, InlineKeyboardMarkup, Message,
)

# ════════════════════════════════════════════════════════════════
#  SOZLAMALAR
# ════════════════════════════════════════════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_IDS = {int(x) for x in re.findall(r"\d+", os.getenv("OWNER_IDS", ""))}
DB_PATH = os.getenv("DB_PATH", "legion.db")
TZ = timezone(timedelta(hours=5))  # Toshkent vaqti
ADMIN_RIGHTS = "change_info+delete_messages+restrict_members+invite_users+pin_messages"
BOT_USERNAME = ""
log = logging.getLogger("legion")

# Mezon va sozlamalar: kalit -> (nomi, turi, standart qiymat, bo'lim)
SETTINGS = {
    "owner_only": ("Faqat guruh EGASI ariza bera oladi", "bool", "1", "crit"),
    "min_members": ("Minimal a'zolar soni", "int", "30", "crit"),
    "max_members": ("Maksimal a'zolar (0 = cheklovsiz)", "int", "0", "crit"),
    "min_title_len": ("Guruh nomi minimal uzunligi", "int", "3", "crit"),
    "require_full_admin": ("Bot TO'LIQ admin bo'lishi shart", "bool", "1", "crit"),
    "require_public": ("Guruh ochiq (@username) bo'lishi shart", "bool", "0", "crit"),
    "require_comment": ("Arizada izoh majburiy", "bool", "0", "crit"),
    "max_groups_per_owner": ("Bir egadan maksimal guruh", "int", "3", "crit"),
    "cooldown_hours": ("Rad etilgach qayta ariza (soat)", "int", "24", "crit"),
    "strict": ("Mezonga mos kelmasa ariza qabul qilinmasin", "bool", "1", "crit"),
    "auto_mode": ("Avto-qabul (mezon o'tsa o'zi qabul qiladi)", "bool", "0", "auto"),
    "guard": ("Ittifoq guruhi qo'riqchisi (ruxsatsizni chiqaradi)", "bool", "1", "auto"),
    "pin_broadcast": ("E'lonni guruhlarda pin qilish", "bool", "0", "auto"),
    "ad_cooldown_hours": ("Reklama oralig'i (soat)", "int", "24", "auto"),
    "auto_report": ("Avto-hisobot (0 o'chiq, 1 kunlik, 7 haftalik)", "int", "0", "auto"),
    "ai_enabled": ("AI yoqilgan", "bool", "1", "ai"),
    "ai_autonomy": ("AI owner buyruqlarini tasdiqsiz bajaradi", "bool", "0", "ai"),
    "ai_user_limit": ("AI: foydalanuvchiga kunlik limit", "int", "30", "ai"),
}
SET_GROUPS = {"crit": "📋 Qabul mezonlari", "auto": "⚙️ Avtomatlashtirish", "ai": "🤖 AI sozlamalari"}

DEFAULT_TEXTS = {
    "welcome_text": (
        "👑 <b>LEGION · QIROLLAR ITTIFOQI</b> 👑\n"
        "━━━━━━━━━━━━━━\n"
        "Xush kelibsiz, <b>{name}</b>.\n\n"
        "Bu yerda kuch baqirishda emas — <b>tartibda, so'zda va sadoqatda</b>. "
        "Legion — o'z guruhining hukmdori bo'lgan egalarning yopiq kengashi.\n\n"
        "⚔️ Kuch — birlikda.\n🛡 Hurmat — sadoqatda.\n🏰 Shon — LEGION bilan.\n\n"
        "Taxt zali ochiq. Yo'lingizni tanlang 👇"
    ),
    "about_text": (
        "🏰 <b>LEGION · QIROLLAR ITTIFOQI</b>\n\n"
        "Legion — mafia olamining eng kuchli guruh egalarini birlashtirgan ittifoq. "
        "Har bir a'zo o'z guruhida to'liq hukmdor bo'lib qoladi, ammo ittifoq saflarida hech qachon yolg'iz emas.\n\n"
        "👑 <b>Nima beramiz</b>\n"
        "🛡 Himoya — guruhingizga tahdid bo'lsa, butun ittifoq yelkadosh\n"
        "⚔️ Turnirlar — haqiqiy raqobat va shon-sharaf\n"
        "📯 Reklama almashinuvi — o'sish uchun kuchli minbar\n"
        "🤝 Hamkorlik — faqat saralanganlar davrasi\n\n"
        "📜 <b>Qasamyodimiz</b>\nSo'zga sodiqlik. Ittifoqqa hurmat. Dushmanga ayovsizlik — o'yin ichida, adolat bilan."
    ),
    "accept_text": (
        "👑 <b>Qabul qilindingiz!</b>\n\n"
        "«{title}» guruhi LEGION saflariga qo'shildi. Endi siz — Kengash a'zosisiz.\n\n"
        "Quyidagi tugma orqali Kengash zaliga kiring. Havola faqat sizga tegishli — uni hech kimga bermang. ⚜️"
    ),
    "reject_text": (
        "🕯 «{title}» guruhi bo'yicha arizangiz Kengash tomonidan ma'qullanmadi.\n\n"
        "📝 Sabab: {reason}\n\nKamchiliklarni to'g'rilab, belgilangan muddatdan so'ng qayta murojaat qilishingiz mumkin."
    ),
    "family_links": "",
}
TEXT_LABELS = {
    "welcome_text": "Salomlashuv matni ({name} — ism)",
    "about_text": "«Ittifoq haqida» matni",
    "accept_text": "Qabul xabari ({title})",
    "reject_text": "Rad xabari ({title}, {reason})",
    "family_links": "Legion Family havolalari (har qatorda: Nom | https://...)",
}
REJECT_REASONS = [
    "Mezonlarga mos emas", "A'zolar soni yetarli emas", "Guruh faol emas",
    "Qoidalarga zid", "Boshqa (o'zim yozaman)", "Sababsiz",
]


# ════════════════════════════════════════════════════════════════
#  MA'LUMOTLAR BAZASI
# ════════════════════════════════════════════════════════════════
SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, name TEXT, username TEXT, created_at INTEGER, last_seen INTEGER);
CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at INTEGER);
CREATE TABLE IF NOT EXISTS bot_adds(user_id INTEGER, chat_id INTEGER, title TEXT, ts INTEGER, PRIMARY KEY(user_id, chat_id));
CREATE TABLE IF NOT EXISTS applications(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, user_name TEXT, username TEXT,
    chat_id INTEGER, chat_title TEXT, chat_username TEXT, invite_link TEXT, members INTEGER,
    bot_ok INTEGER, comment TEXT, status TEXT DEFAULT 'pending', reason TEXT, checks TEXT,
    created_at INTEGER, decided_at INTEGER, decided_by INTEGER, auto INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS app_msgs(app_id INTEGER, admin_id INTEGER, message_id INTEGER);
CREATE TABLE IF NOT EXISTS groups(
    chat_id INTEGER PRIMARY KEY, title TEXT, username TEXT, owner_id INTEGER, owner_name TEXT,
    app_id INTEGER, members INTEGER DEFAULT 0, status TEXT DEFAULT 'active', joined_at INTEGER,
    last_check INTEGER, note TEXT);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, members INTEGER, ts INTEGER);
CREATE INDEX IF NOT EXISTS ix_snap ON snapshots(chat_id, ts);
CREATE TABLE IF NOT EXISTS blacklist(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, target INTEGER, note TEXT, added_at INTEGER, UNIQUE(kind, target));
CREATE TABLE IF NOT EXISTS tournaments(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, descr TEXT, starts TEXT, status TEXT DEFAULT 'open', created_at INTEGER);
CREATE TABLE IF NOT EXISTS tregs(tid INTEGER, chat_id INTEGER, user_id INTEGER, ts INTEGER, PRIMARY KEY(tid, chat_id));
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, text TEXT, status TEXT DEFAULT 'open', answer TEXT, created_at INTEGER, answered_at INTEGER);
CREATE TABLE IF NOT EXISTS ads(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, src_chat INTEGER, src_msg INTEGER, status TEXT DEFAULT 'pending', created_at INTEGER);
CREATE TABLE IF NOT EXISTS kb(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT);
CREATE TABLE IF NOT EXISTS ai_history(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, role TEXT, content TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS ai_facts(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, fact TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS pending_actions(token TEXT PRIMARY KEY, actor INTEGER, action TEXT, payload TEXT, ts INTEGER);
CREATE TABLE IF NOT EXISTS log(id INTEGER PRIMARY KEY AUTOINCREMENT, actor INTEGER, action TEXT, detail TEXT, ts INTEGER);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.Lock()

    def _run(self, sql, args, mode):
        with self.lock:
            cur = self.conn.execute(sql, args)
            if mode == "all":
                res = [dict(x) for x in cur.fetchall()]
            elif mode == "one":
                x = cur.fetchone()
                res = dict(x) if x else None
            elif mode == "id":
                res = cur.lastrowid
            else:
                res = cur.rowcount
            self.conn.commit()
            return res

    async def all(self, sql, *a):
        return await asyncio.to_thread(self._run, sql, a, "all")

    async def one(self, sql, *a):
        return await asyncio.to_thread(self._run, sql, a, "one")

    async def exec(self, sql, *a):
        return await asyncio.to_thread(self._run, sql, a, "exec")

    async def ins(self, sql, *a):
        return await asyncio.to_thread(self._run, sql, a, "id")

    async def cnt(self, sql, *a):
        r = await self.one(sql, *a)
        return list(r.values())[0] if r else 0


db = DB(DB_PATH)


class Cfg:
    def __init__(self):
        self.cache = {}

    async def load(self):
        rows = await db.all("SELECT k, v FROM settings")
        self.cache = {r["k"]: r["v"] for r in rows}

    def get(self, k):
        if k in self.cache:
            return self.cache[k]
        if k in SETTINGS:
            return SETTINGS[k][2]
        return DEFAULT_TEXTS.get(k, "")

    def i(self, k):
        try:
            return int(self.get(k))
        except (TypeError, ValueError):
            return 0

    def b(self, k):
        return self.get(k) == "1"

    async def set(self, k, v):
        await db.exec(
            "INSERT INTO settings(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", k, str(v))
        self.cache[k] = str(v)

    async def reset(self, k):
        await db.exec("DELETE FROM settings WHERE k=?", k)
        self.cache.pop(k, None)


cfg = Cfg()
ADMINS = set()


def is_super(uid):
    return uid in OWNER_IDS


def is_admin(uid):
    return uid in OWNER_IDS or uid in ADMINS


def all_admin_ids():
    return list(OWNER_IDS | ADMINS)


async def load_admins():
    ADMINS.clear()
    for r in await db.all("SELECT user_id FROM admins"):
        ADMINS.add(r["user_id"])


# ════════════════════════════════════════════════════════════════
#  YORDAMCHI FUNKSIYALAR
# ════════════════════════════════════════════════════════════════
def esc(s):
    return html.escape(str(s if s is not None else ""), quote=False)


def now():
    return int(time.time())


def fmt(ts):
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M") if ts else "—"


def today_start():
    d = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp())


def short(s, n=24):
    s = str(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def mention(uid, name):
    return f'<a href="tg://user?id={uid}">{esc(name or uid)}</a>'


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s or "")


def md_to_html(text):
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=re.S)
    t = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", t)
    t = re.sub(r"^#{1,4}\s*(.+)$", r"<b>\1</b>", t, flags=re.M)
    return t


def B(text, data=None, url=None):
    if url:
        return InlineKeyboardButton(text=text, url=url)
    return InlineKeyboardButton(text=text, callback_data=data or "x")


def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pager(prefix, page, total, per=8):
    pages = max(1, (total + per - 1) // per)
    nav = []
    if page > 0:
        nav.append(B("◀️", f"{prefix}:{page - 1}"))
    nav.append(B(f"{page + 1}/{pages}", "x"))
    if (page + 1) * per < total:
        nav.append(B("▶️", f"{prefix}:{page + 1}"))
    return nav


async def ui(ev, text, markup=None):
    """Callback bo'lsa xabarni tahrirlaydi, aks holda yangi xabar yuboradi."""
    text = text[:4000]
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await ev.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            await ev.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        try:
            await ev.answer()
        except Exception:
            pass
    else:
        await ev.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def log_action(actor, action, detail=""):
    await db.exec("INSERT INTO log(actor, action, detail, ts) VALUES(?,?,?,?)", actor, action, str(detail)[:500], now())


async def touch_user(u):
    await db.exec(
        "INSERT INTO users(user_id,name,username,created_at,last_seen) VALUES(?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET name=excluded.name, username=excluded.username, last_seen=excluded.last_seen",
        u.id, u.full_name, u.username or "", now(), now())


async def is_blacklisted(kind, target):
    return bool(await db.one("SELECT 1 AS x FROM blacklist WHERE kind=? AND target=?", kind, target))


async def notify_admins(bot, text, markup=None):
    for aid in all_admin_ids():
        try:
            await bot.send_message(aid, text, reply_markup=markup, disable_web_page_preview=True)
        except Exception:
            pass


class Touch(BaseMiddleware):
    async def __call__(self, handler, event, data):
        u = data.get("event_from_user")
        if u and not u.is_bot:
            try:
                await touch_user(u)
            except Exception:
                log.exception("touch_user")
        return await handler(event, data)


class AdminOnly(BaseFilter):
    async def __call__(self, ev) -> bool:
        u = getattr(ev, "from_user", None)
        return bool(u and is_admin(u.id))


class UF(StatesGroup):
    comment = State()
    ad = State()
    ticket = State()
    ai = State()


class AF(StatesGroup):
    reject_reason = State()
    set_value = State()
    text_value = State()
    bc_msg = State()
    t_title = State()
    t_desc = State()
    t_start = State()
    bl_add = State()
    adm_add = State()
    kb_title = State()
    kb_content = State()
    tix_reply = State()
    chan_fwd = State()
    ai = State()


# ════════════════════════════════════════════════════════════════
#  MEZONLARNI TEKSHIRISH
# ════════════════════════════════════════════════════════════════
FULL_PERMS = [
    ("can_invite_users", "Havola yaratish"),
    ("can_delete_messages", "Xabarlarni o'chirish"),
    ("can_restrict_members", "A'zolarni cheklash"),
    ("can_pin_messages", "Xabarni pin qilish"),
    ("can_change_info", "Guruh ma'lumotini o'zgartirish"),
]


def criteria_text():
    L = []
    L.append("• Ariza beruvchi: guruh EGASI" if cfg.b("owner_only") else "• Ariza beruvchi: guruh egasi yoki admini")
    mx = cfg.i("max_members")
    L.append(f"• A'zolar soni: kamida {cfg.i('min_members')}" + (f", ko'pi bilan {mx}" if mx else ""))
    L.append("• Bot guruhda TO'LIQ admin" if cfg.b("require_full_admin") else "• Bot guruhda admin")
    if cfg.b("require_public"):
        L.append("• Guruh ochiq (@username) bo'lishi shart")
    if cfg.b("require_comment"):
        L.append("• Arizada izoh majburiy")
    L.append(f"• Guruh nomi kamida {cfg.i('min_title_len')} belgi")
    return "\n".join(L)


async def eval_group(bot, chat_id, user_id):
    res = {"ok": True, "checks": [], "info": {}}

    def chk(passed, text):
        res["checks"].append((bool(passed), text))
        if not passed:
            res["ok"] = False

    try:
        chat = await bot.get_chat(chat_id)
    except Exception:
        chk(False, "Guruh topilmadi yoki bot guruhda emas")
        return res
    info = res["info"]
    info.update(chat_id=chat_id, title=chat.title or "", username=chat.username or "", type=str(chat.type))
    chk(str(getattr(chat.type, "value", chat.type)) in ("group", "supergroup"), "Oddiy yoki super guruh bo'lishi kerak")
    title = (chat.title or "").strip()
    chk(len(title) >= cfg.i("min_title_len") and re.search(r"\w", title), f"Guruh nomi mazmunli va kamida {cfg.i('min_title_len')} belgi")
    try:
        members = await bot.get_chat_member_count(chat_id)
    except Exception:
        members = 0
    owner_id, owner_name, owner_un, bots = None, "", "", 0
    try:
        for a in await bot.get_chat_administrators(chat_id):
            if a.status == "creator":
                owner_id, owner_name, owner_un = a.user.id, a.user.full_name, a.user.username or ""
            if a.user.is_bot:
                bots += 1
    except Exception:
        pass
    eff = max(members - bots, 0)
    info.update(members=eff, raw_members=members, owner_id=owner_id, owner_name=owner_name, owner_un=owner_un)
    # bot huquqlari
    bot_admin, missing = False, []
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
        bot_admin = me.status == "administrator"
        if bot_admin and cfg.b("require_full_admin"):
            missing = [lbl for attr, lbl in FULL_PERMS if not getattr(me, attr, False)]
    except Exception:
        pass
    info["bot_admin"] = bot_admin
    if not bot_admin:
        chk(False, "Bot guruhda admin emas")
    elif missing:
        chk(False, "Botga yetishmayotgan huquqlar: " + ", ".join(missing))
    else:
        chk(True, "Bot guruhda admin")
    # foydalanuvchi huquqi
    try:
        um = await bot.get_chat_member(chat_id, user_id)
        st = um.status
    except Exception:
        st = "left"
    if cfg.b("owner_only"):
        chk(st == "creator", "Siz guruh EGASI bo'lishingiz shart")
    else:
        chk(st in ("creator", "administrator"), "Siz guruh egasi yoki admini bo'lishingiz shart")
    mn, mx = cfg.i("min_members"), cfg.i("max_members")
    chk(eff >= mn, f"A'zolar soni kamida {mn} (hozir {eff})")
    if mx:
        chk(eff <= mx, f"A'zolar soni ko'pi bilan {mx} (hozir {eff})")
    if cfg.b("require_public"):
        chk(bool(chat.username), "Guruh ochiq (@username) bo'lishi shart")
    chk(not await is_blacklisted("group", chat_id), "Guruh qora ro'yxatda emas")
    chk(not await is_blacklisted("user", user_id), "Foydalanuvchi qora ro'yxatda emas")
    dup = await db.one("SELECT 1 AS x FROM groups WHERE chat_id=? AND status='active'", chat_id)
    pend = await db.one("SELECT 1 AS x FROM applications WHERE chat_id=? AND status='pending'", chat_id)
    chk(not dup and not pend, "Guruh ittifoqda yoki arizada emas")
    mg = cfg.i("max_groups_per_owner")
    if mg:
        have = await db.cnt("SELECT COUNT(*) FROM groups WHERE owner_id=? AND status='active'", user_id)
        chk(have < mg, f"Bir egadan ko'pi bilan {mg} ta guruh")
    return res


def checks_text(res):
    return "\n".join(("✅ " if p else "❌ ") + t for p, t in res["checks"])


# ════════════════════════════════════════════════════════════════
#  ARIZA MANTIQI
# ════════════════════════════════════════════════════════════════
ST_LABEL = {
    "pending": "⏳ Ko'rib chiqilmoqda", "approved": "✅ Qabul qilingan",
    "rejected": "❌ Rad etilgan", "cancelled": "🚫 Bekor qilingan",
}


def app_card(a, admin=True):
    own = mention(a["user_id"], a["user_name"]) + (f" @{esc(a['username'])}" if a.get("username") else "")
    t = (
        f"📋 <b>Ariza #{a['id']}</b>\n{ST_LABEL.get(a['status'], a['status'])}\n\n"
        f"🏷 Guruh: <b>{esc(a['chat_title'])}</b>\n"
        f"🔗 Havola: {esc(a['invite_link'] or '—')}\n"
        f"👑 Ega: {own}\n"
        f"👥 A'zolar: {a['members']}\n"
        f"💬 Izoh: {esc(a['comment'] or '—')}\n"
        f"🕒 {fmt(a['created_at'])}"
    )
    if a["status"] == "rejected" and a.get("reason"):
        t += f"\n📝 Sabab: {esc(a['reason'])}"
    if a.get("auto"):
        t += "\n🤖 Avto-qabul"
    if admin and a.get("checks"):
        t += "\n\n<b>Mezonlar:</b>\n" + esc(a["checks"])
    return t


def app_admin_kb(a):
    rows = []
    if a["status"] == "pending":
        rows.append([B("✅ Qabul qilish", f"a:ok:{a['id']}"), B("❌ Rad etish", f"a:no:{a['id']}")])
        rows.append([B("🤖 AI tahlil", f"a:ai:{a['id']}")])
    rows.append([B("⬅️ Arizalar", "a:apps:pending:0")])
    return kb(rows)


async def submit_application(bot, user, chat_id, comment):
    if cfg.b("require_comment") and not comment:
        return None, "Izoh majburiy."
    res = await eval_group(bot, chat_id, user.id)
    if not res["ok"] and cfg.b("strict"):
        return None, "Mezonlarga mos kelmadi:\n" + checks_text(res)
    if not res["info"].get("bot_admin"):
        return None, "Bot guruhda admin emas."
    info = res["info"]
    link = f"https://t.me/{info['username']}" if info.get("username") else ""
    if not link:
        try:
            link = (await bot.create_chat_invite_link(chat_id, name="Legion ariza")).invite_link
        except Exception:
            link = ""
    aid = await db.ins(
        "INSERT INTO applications(user_id,user_name,username,chat_id,chat_title,chat_username,invite_link,members,"
        "bot_ok,comment,status,checks,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
        user.id, user.full_name, user.username or "", chat_id, info["title"], info.get("username", ""), link,
        info["members"], 1, comment, checks_text(res), now())
    await log_action(user.id, "apply", f"app#{aid}")
    if cfg.b("auto_mode") and res["ok"]:
        await approve_application(bot, aid, 0, auto=True)
        return aid, "auto"
    a = await db.one("SELECT * FROM applications WHERE id=?", aid)
    for adm in all_admin_ids():
        try:
            m = await bot.send_message(adm, "🔔 <b>Yangi ariza!</b>\n\n" + app_card(a), reply_markup=app_admin_kb(a),
                                       disable_web_page_preview=True)
            await db.exec("INSERT INTO app_msgs VALUES(?,?,?)", aid, adm, m.message_id)
        except Exception:
            pass
    if not cfg.get("alliance_chat_id"):
        await notify_admins(bot, "⚠️ Ittifoq guruhi ulanmagan! Ittifoq guruhida botni admin qilib /bind yozing.")
    return aid, "ok"


async def refresh_notifs(bot, app_id):
    a = await db.one("SELECT * FROM applications WHERE id=?", app_id)
    if not a:
        return
    for r in await db.all("SELECT * FROM app_msgs WHERE app_id=?", app_id):
        try:
            await bot.edit_message_text(app_card(a), chat_id=r["admin_id"], message_id=r["message_id"],
                                        reply_markup=app_admin_kb(a), disable_web_page_preview=True)
        except Exception:
            pass


async def make_join_link(bot, label):
    alliance = cfg.get("alliance_chat_id")
    if not alliance:
        return None
    try:
        lk = await bot.create_chat_invite_link(int(alliance), name=str(label)[:32], creates_join_request=True)
        return lk.invite_link
    except Exception as e:
        log.warning("join link: %s", e)
        return None


async def approve_application(bot, app_id, actor, auto=False):
    a = await db.one("SELECT * FROM applications WHERE id=?", app_id)
    if not a:
        return False, "Ariza topilmadi"
    if a["status"] != "pending":
        return False, "Ariza allaqachon ko'rib chiqilgan"
    try:
        await bot.get_chat(a["chat_id"])
    except Exception:
        return False, "Bot guruhda yo'q yoki guruh o'chirilgan"
    await db.exec("UPDATE applications SET status='approved', decided_at=?, decided_by=?, auto=? WHERE id=?",
                  now(), actor, int(auto), app_id)
    await db.exec(
        "INSERT INTO groups(chat_id,title,username,owner_id,owner_name,app_id,members,status,joined_at,last_check) "
        "VALUES(?,?,?,?,?,?,?,'active',?,?) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title, "
        "owner_id=excluded.owner_id, owner_name=excluded.owner_name, app_id=excluded.app_id, members=excluded.members, "
        "status='active', joined_at=excluded.joined_at",
        a["chat_id"], a["chat_title"], a["chat_username"], a["user_id"], a["user_name"], app_id, a["members"], now(), now())
    await db.exec("INSERT INTO snapshots(chat_id,members,ts) VALUES(?,?,?)", a["chat_id"], a["members"], now())
    text = cfg.get("accept_text").replace("{title}", esc(a["chat_title"]))
    link = await make_join_link(bot, f"Ariza #{app_id}")
    markup = kb([[B("⚜️ Ittifoq guruhiga qo'shilish", url=link)]]) if link else None
    if not link:
        text += "\n\n⏳ Ittifoq guruhi havolasi tez orada yuboriladi."
        await notify_admins(bot, f"⚠️ Ariza #{app_id} qabul qilindi, lekin ittifoq guruhi havolasi yaratilmadi. "
                                 f"Ittifoq guruhi ulanganini va bot adminligini tekshiring (Panel → Ulanishlar).")
    try:
        await bot.send_message(a["user_id"], text, reply_markup=markup)
    except Exception:
        pass
    await refresh_notifs(bot, app_id)
    await log_action(actor, "approve", f"app#{app_id}")
    return True, "Qabul qilindi"


async def reject_application(bot, app_id, actor, reason=""):
    a = await db.one("SELECT * FROM applications WHERE id=?", app_id)
    if not a:
        return False, "Ariza topilmadi"
    if a["status"] != "pending":
        return False, "Ariza allaqachon ko'rib chiqilgan"
    await db.exec("UPDATE applications SET status='rejected', reason=?, decided_at=?, decided_by=? WHERE id=?",
                  reason, now(), actor, app_id)
    text = cfg.get("reject_text").replace("{title}", esc(a["chat_title"])).replace("{reason}", esc(reason or "ko'rsatilmagan"))
    try:
        await bot.send_message(a["user_id"], text)
    except Exception:
        pass
    await refresh_notifs(bot, app_id)
    await log_action(actor, "reject", f"app#{app_id} {reason}")
    return True, "Rad etildi"


async def kick_from_alliance(bot, uid):
    alliance = cfg.get("alliance_chat_id")
    if not alliance or is_admin(uid):
        return
    try:
        await bot.ban_chat_member(int(alliance), uid)
        await bot.unban_chat_member(int(alliance), uid, only_if_banned=True)
    except Exception:
        pass


async def remove_group(bot, chat_id, reason="", actor=0):
    g = await db.one("SELECT * FROM groups WHERE chat_id=?", chat_id)
    if not g:
        return False, "Guruh topilmadi"
    await db.exec("UPDATE groups SET status='removed', note=? WHERE chat_id=?", reason, chat_id)
    try:
        await bot.send_message(g["owner_id"], f"⚠️ «{esc(g['title'])}» guruhingiz LEGION ITTIFOQIDAN chiqarildi.\n📝 Sabab: {esc(reason or 'ko‘rsatilmagan')}")
    except Exception:
        pass
    left = await db.cnt("SELECT COUNT(*) FROM groups WHERE owner_id=? AND status='active'", g["owner_id"])
    if not left:
        await kick_from_alliance(bot, g["owner_id"])
    await log_action(actor, "remove_group", f"{chat_id} {reason}")
    return True, "Guruh ittifoqdan chiqarildi"


# ════════════════════════════════════════════════════════════════
#  STATISTIKA VA O'SISH
# ════════════════════════════════════════════════════════════════
async def stats_data():
    d7 = now() - 7 * 86400
    return {
        "users": await db.cnt("SELECT COUNT(*) FROM users"),
        "users_today": await db.cnt("SELECT COUNT(*) FROM users WHERE created_at>=?", today_start()),
        "users_7d": await db.cnt("SELECT COUNT(*) FROM users WHERE created_at>=?", d7),
        "pending": await db.cnt("SELECT COUNT(*) FROM applications WHERE status='pending'"),
        "approved": await db.cnt("SELECT COUNT(*) FROM applications WHERE status='approved'"),
        "rejected": await db.cnt("SELECT COUNT(*) FROM applications WHERE status='rejected'"),
        "removed": await db.cnt("SELECT COUNT(*) FROM groups WHERE status IN ('removed','lost')"),
        "groups": await db.cnt("SELECT COUNT(*) FROM groups WHERE status='active'"),
        "members": await db.cnt("SELECT COALESCE(SUM(members),0) FROM groups WHERE status='active'"),
    }


async def stats_text():
    s = await stats_data()
    return (
        "📊 <b>«Legion» statistikasi</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>\n"
        f"   ├ Bugun: +{s['users_today']}\n   └ 7 kunda: +{s['users_7d']}\n\n"
        "📮 <b>Arizalar:</b>\n"
        f"   ⏳ Kutilmoqda: {s['pending']}\n   ✅ Qabul qilingan: {s['approved']}\n"
        f"   ❌ Rad etilgan: {s['rejected']}\n   🚫 Chiqarilgan/yo'qotilgan: {s['removed']}\n\n"
        f"🏰 Ittifoq guruhlari: <b>{s['groups']}</b>\n"
        f"👥 Guruhlardagi jami a'zolar: <b>{s['members']}</b>"
    )


async def growth_rows(days):
    since = now() - days * 86400
    out = []
    for g in await db.all("SELECT * FROM groups WHERE status='active' ORDER BY members DESC"):
        base = await db.one("SELECT members FROM snapshots WHERE chat_id=? AND ts<=? ORDER BY ts DESC LIMIT 1", g["chat_id"], since)
        if not base:
            base = await db.one("SELECT members FROM snapshots WHERE chat_id=? ORDER BY ts ASC LIMIT 1", g["chat_id"])
        d = (g["members"] - base["members"]) if base else 0
        out.append((g, d))
    return out


async def growth_text(days=7):
    rows = await growth_rows(days)
    if not rows:
        return "📈 Hali ittifoq guruhlari yo'q."
    L = [f"📈 <b>«Legion» a'zolar o'sishi (oxirgi {days} kun)</b>\n"]
    total, dsum = 0, 0
    for g, d in rows:
        mark = f"▲ +{d}" if d > 0 else (f"▼ {d}" if d < 0 else "•")
        L.append(f"• {esc(g['title'])}: <b>{g['members']}</b> ({mark})")
        total += g["members"]
        dsum += d
    L.append(f"\n👥 Jami: <b>{total}</b> ({days} kunda {dsum:+d})\nℹ️ O'lchov har 6 soatda avtomatik olinadi.")
    return "\n".join(L)


async def rating_text():
    rows = await growth_rows(7)
    if not rows:
        return "🏆 Reyting hali shakllanmagan."
    L = ["🏆 <b>LEGION reytingi</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, (g, d) in enumerate(rows[:15]):
        mk = medals[i] if i < 3 else f"{i + 1}."
        mark = f" ▲{d}" if d > 0 else (f" ▼{abs(d)}" if d < 0 else "")
        L.append(f"{mk} {esc(g['title'])} — <b>{g['members']}</b>{mark}")
    return "\n".join(L)


async def snapshot_job(bot):
    for g in await db.all("SELECT * FROM groups WHERE status='active'"):
        cid = g["chat_id"]
        try:
            members = await bot.get_chat_member_count(cid)
            me = await bot.get_chat_member(cid, bot.id)
            if me.status in ("left", "kicked"):
                await db.exec("UPDATE groups SET status='lost', note='bot yo\'q' WHERE chat_id=?", cid)
                await notify_admins(bot, f"🚨 «{esc(g['title'])}» guruhida bot yo'q. Guruh «yo'qotilgan» deb belgilandi.")
                continue
            await db.exec("UPDATE groups SET members=?, last_check=? WHERE chat_id=?", members, now(), cid)
            await db.exec("INSERT INTO snapshots(chat_id,members,ts) VALUES(?,?,?)", cid, members, now())
            try:
                for a in await bot.get_chat_administrators(cid):
                    if a.status == "creator" and a.user.id != g["owner_id"]:
                        await db.exec("UPDATE groups SET owner_id=?, owner_name=? WHERE chat_id=?", a.user.id, a.user.full_name, cid)
                        await notify_admins(bot, f"⚠️ «{esc(g['title'])}» guruhi egasi o'zgardi: {mention(a.user.id, a.user.full_name)}")
            except Exception:
                pass
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            await db.exec("UPDATE groups SET status='lost', note=? WHERE chat_id=?", str(e)[:200], cid)
            await notify_admins(bot, f"🚨 «{esc(g['title'])}» guruhida bot yo'q yoki guruh o'chirilgan. Guruh «yo'qotilgan» deb belgilandi.")
        except Exception:
            log.exception("snapshot")
        await asyncio.sleep(0.4)


async def post_report(bot):
    text = await stats_text() + "\n\n" + await growth_text(7)
    ch = cfg.get("stats_channel_id")
    if ch:
        try:
            await bot.send_message(int(ch), text)
            return
        except Exception:
            log.warning("kanalga hisobot yuborilmadi")
    await notify_admins(bot, text)


async def scheduler(bot):
    await asyncio.sleep(15)
    while True:
        try:
            if now() - int(cfg.get("last_snapshot") or 0) >= 6 * 3600:
                await snapshot_job(bot)
                await cfg.set("last_snapshot", now())
            mode = cfg.i("auto_report")
            if mode:
                dt = datetime.now(TZ)
                last = cfg.get("last_report")
                last_dt = datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=TZ) if last else None
                if dt.hour >= 9 and (not last_dt or (dt - last_dt).days >= mode):
                    await post_report(bot)
                    await cfg.set("last_report", dt.strftime("%Y-%m-%d"))
            await db.exec("DELETE FROM pending_actions WHERE ts<?", now() - 86400)
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(600)


# ════════════════════════════════════════════════════════════════
#  E'LON, TURNIR, BAN
# ════════════════════════════════════════════════════════════════
async def broadcast(bot, src=None, text=None, pin=False, exclude=()):
    sent, failed = 0, []
    for g in await db.all("SELECT * FROM groups WHERE status='active'"):
        if g["chat_id"] in exclude:
            continue
        for attempt in range(2):
            try:
                if src:
                    m = await bot.copy_message(g["chat_id"], src[0], src[1])
                else:
                    m = await bot.send_message(g["chat_id"], text, disable_web_page_preview=True)
                sent += 1
                if pin:
                    try:
                        await bot.pin_chat_message(g["chat_id"], m.message_id, disable_notification=True)
                    except Exception:
                        pass
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                failed.append(g["title"])
                break
        await asyncio.sleep(0.07)
    return sent, failed


def tour_text(t, regs=0):
    return (f"🏟 <b>Turnir #{t['id']}: {esc(t['title'])}</b>\n\n{esc(t['descr'])}\n\n"
            f"🕒 Boshlanishi: <b>{esc(t['starts'])}</b>\n👥 Ro'yxatdan o'tgan guruhlar: {regs}\n"
            f"📌 Holat: {'🟢 ochiq' if t['status'] == 'open' else '🔒 yopiq'}")


async def announce_tournament(bot, tid):
    t = await db.one("SELECT * FROM tournaments WHERE id=?", tid)
    if not t:
        return 0, []
    regs = await db.cnt("SELECT COUNT(*) FROM tregs WHERE tid=?", tid)
    text = tour_text(t, regs) + "\n\n👇 Ro'yxatdan o'tish uchun guruh egasi botga kiradi:"
    # tugmali xabar
    sent, failed = 0, []
    markup = kb([[B("✅ Ro'yxatdan o'tish", url=f"https://t.me/{BOT_USERNAME}?start=tour")]])
    for g in await db.all("SELECT * FROM groups WHERE status='active'"):
        try:
            await bot.send_message(g["chat_id"], text, reply_markup=markup)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except Exception:
            failed.append(g["title"])
        await asyncio.sleep(0.07)
    return sent, failed


async def global_ban(bot, uid, reason=""):
    ok, bad = 0, 0
    await db.exec("INSERT OR IGNORE INTO blacklist(kind,target,note,added_at) VALUES('user',?,?,?)", uid, reason, now())
    chats = [g["chat_id"] for g in await db.all("SELECT chat_id FROM groups WHERE status='active'")]
    alliance = cfg.get("alliance_chat_id")
    if alliance:
        chats.append(int(alliance))
    for cid in chats:
        try:
            await bot.ban_chat_member(cid, uid)
            ok += 1
        except Exception:
            bad += 1
        await asyncio.sleep(0.1)
    return ok, bad


# ════════════════════════════════════════════════════════════════
#  LEGION AI — ichki (tashqi modelsiz) aqlli yordamchi
# ════════════════════════════════════════════════════════════════
_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
}


def norm(t):
    """Matnni soddalashtiradi: kichik harf, kirill->lotin, apostrofsiz."""
    t = (t or "").lower()
    t = "".join(_CYR.get(ch, ch) for ch in t)
    t = re.sub(r"['’ʻʼ‘`´]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def toks(t):
    return re.findall(r"[a-z0-9#]+", norm(t))


def tm(tok, stem):
    """So'z o'zagiga mosligi (imlo xatosiga chidamli)."""
    if len(stem) <= 3:
        return tok == stem
    if tok.startswith(stem):
        return True
    if len(tok) >= 5 and len(stem) >= 5:
        return difflib.SequenceMatcher(None, tok[: len(stem) + 1], stem).ratio() >= 0.86
    return False


def has(tk, *stems):
    return any(tm(t, s) for t in tk for s in stems)


def cnt_has(tk, stems):
    return sum(1 for s in stems if any(tm(t, s) for t in tk))


USER_INTENTS = [
    ("greet", ["salom", "assalom", "hayrli", "hello", "hi", "qalay", "qalesiz", "tinchmi"], 3),
    ("thanks", ["rahmat", "raxmat", "tashakkur", "thanks", "sagbol"], 3),
    ("bye", ["xayr", "bye", "korishguncha"], 3),
    ("join", ["qoshil", "ariza", "kirmoq", "kirish", "qoshilmoqchi", "azo"], 2),
    ("criteria", ["talab", "mezon", "shart", "minimal", "kamida", "nechta", "qancha", "limit", "azolar"], 2),
    ("status", ["holat", "xolat", "natija", "javob", "korib", "boldimi", "arizam", "qilindimi"], 3),
    ("about", ["haqida", "imkoniyat", "foyda", "nimaga", "ittifoq", "legion", "nima", "nega"], 1),
    ("rating", ["reyting", "top", "kuchli", "daraja", "royxat"], 2),
    ("tour", ["turnir", "musobaqa", "chempionat"], 3),
    ("ad", ["reklama", "reklam", "pr", "promo"], 3),
    ("problem", ["muammo", "shikoyat", "hujum", "spam", "raid", "tahdid", "buzg", "yordam", "kimdir"], 2),
    ("link", ["havola", "link", "kira"], 2),
    ("reapply", ["qayta", "rad", "kutish", "yana"], 3),
    ("trouble", ["huquq", "tekshir", "topilmadi", "bot", "admin"], 1),
    ("contact", ["murojaat", "bogla", "egasi", "aloqa"], 2),
]


def detect_intent(tk):
    best, bs = None, 0
    for name, stems, w in USER_INTENTS:
        sc = w * cnt_has(tk, stems)
        if sc > bs:
            best, bs = name, sc
    return best, bs


async def kb_best(tk):
    q = {t[:5] for t in tk if len(t) >= 4}
    if not q:
        return None
    best, bs = None, 0
    for r in await db.all("SELECT title, content FROM kb"):
        tt = {t[:5] for t in toks(r["title"]) if len(t) >= 4}
        ct = {t[:5] for t in toks(r["content"]) if len(t) >= 4}
        sc = 2 * len(q & tt) + len(q & ct)
        if sc > bs:
            best, bs = r, sc
    return best if best and bs >= min(3, 2 * len(q)) else None


def sr(res):
    if res.get("status") == "done":
        return "✅ " + esc(res["result"])
    return "🔔 Tasdiqlash tugmasi yuborildi — o'sha xabardagi ✅ ni bosing."


# ---------- foydalanuvchi miyasi ----------
async def user_brain(bot, user, text):
    uid = user.id
    tk, n = toks(text), norm(text)
    m = re.search(r"\bismim\s+([a-z]{2,20})", n)
    if m:
        nm = m.group(1).capitalize()
        await db.exec("INSERT INTO ai_facts(user_id,fact,ts) VALUES(?,?,?)", uid, f"ism:{nm}", now())
        return f"Tanishganimdan xursandman, <b>{esc(nm)}</b>! 👑 Ittifoq bo'yicha qanday yordam kerak?"
    fr = await db.one("SELECT fact FROM ai_facts WHERE user_id=? AND fact LIKE 'ism:%' ORDER BY id DESC LIMIT 1", uid)
    name = fr["fact"][4:] if fr else user.first_name
    hit = await kb_best(tk)
    if hit:
        return f"📚 <b>{esc(hit['title'])}</b>\n\n{md_to_html(hit['content'])}"
    intent, sc = detect_intent(tk)
    if not intent or sc < 2:
        return (f"Savolingizni to'liq tushunmadim, {esc(name)}. 🤔 Quyidagilarni so'rab ko'ring:\n\n"
                "• «Ittifoqqa qanday qo'shilaman?»\n• «Talablar qanday?»\n• «Arizam holati?»\n"
                "• «Turnirlar bormi?»\n• «Reyting»\n• «Reklama qanday beriladi?»\n\n"
                "Yoki muammoingizni batafsil yozing — adminlarga murojaat sifatida yuboraman.")
    if intent == "greet":
        return (f"Assalomu alaykum, <b>{esc(name)}</b>! 👑\nMen — <b>Legion Organizator</b>, ittifoq yordamchisiman. "
                "Ariza, talablar, turnirlar, reyting va boshqa savollaringizga javob beraman.")
    if intent == "thanks":
        return random.choice(["Marhamat! ⚜️ Yana savol bo'lsa, shu yerdaman.", "Doim tayyorman, Legion bilan qoling! 👑"])
    if intent == "bye":
        return "Omad yor bo'lsin! ⚔️ Legion doim eshigi ochiq."
    if intent == "join":
        return ("👑 <b>Ittifoqqa qo'shilish yo'li</b>\n\n"
                "1️⃣ Menyuda «👑 Ittifoqqa qo'shilish» ni bosing.\n"
                "2️⃣ «➕ Botni guruhga qo'shish» tugmasi orqali botni guruhingizga qo'shing — u to'liq admin bo'ladi.\n"
                "3️⃣ «✅ Tekshirish» ni bosing, izoh yozing va arizani yuboring.\n"
                "4️⃣ Kengash ko'rib chiqadi, natija shu yerda keladi.\n\n"
                f"📌 <b>Talablar:</b>\n{criteria_text()}")
    if intent == "criteria":
        s = await stats_data()
        return f"📌 <b>Qabul talablari</b>\n\n{criteria_text()}\n\n🏰 Hozir ittifoqda {s['groups']} ta guruh, {s['members']} a'zo bor."
    if intent in ("status", "reapply"):
        apps = await db.all("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 3", uid)
        if not apps:
            return "Siz hali ariza bermagansiz. «Ittifoqqa qanday qo'shilaman?» deb so'rang — yo'lini ko'rsataman. 👑"
        a = apps[0]
        if a["status"] == "pending":
            pos = await db.cnt("SELECT COUNT(*) FROM applications WHERE status='pending' AND id<?", a["id"]) + 1
            return f"⏳ Arizangiz <b>#{a['id']}</b> («{esc(a['chat_title'])}») ko'rib chiqilmoqda. Navbatdagi o'rningiz: <b>{pos}</b>."
        if a["status"] == "approved":
            return f"✅ Arizangiz #{a['id']} <b>qabul qilingan</b>! Ittifoq guruhi havolasi kerak bo'lsa: 📜 Mening arizam → 🔗 havola."
        if a["status"] == "rejected":
            cd = cfg.i("cooldown_hours") * 3600
            left = max(0, cd - (now() - (a["decided_at"] or 0)))
            wait = (f"Qayta ariza berishga <b>{left // 3600} soat {left % 3600 // 60} daqiqa</b> qoldi."
                    if left else "Endi qayta ariza berishingiz mumkin.")
            return (f"😔 Arizangiz #{a['id']} rad etilgan.\n📝 Sabab: {esc(a['reason'] or 'ko‘rsatilmagan')}\n\n{wait}\n"
                    "Kamchiliklarni to'g'rilab qayta urinib ko'ring.")
        return f"Oxirgi arizangiz #{a['id']} — {ST_LABEL.get(a['status'])}."
    if intent == "about":
        s = await stats_data()
        return strip_tags(cfg.get("about_text"))[:1200] + f"\n\n🏰 Guruhlar: {s['groups']} · 👥 A'zolar: {s['members']}"
    if intent == "rating":
        return await rating_text()
    if intent == "tour":
        ts = await db.all("SELECT * FROM tournaments WHERE status='open' ORDER BY id DESC LIMIT 3")
        if not ts:
            return "🛡 Hozircha ochiq turnir yo'q. E'lon qilinishi bilan ittifoq guruhlarida xabar beramiz!"
        return "\n\n".join(tour_text(t, await db.cnt("SELECT COUNT(*) FROM tregs WHERE tid=?", t["id"])) for t in ts) + \
               "\n\nRo'yxatdan o'tish: 🛡 Turnirlar menyusi."
    if intent == "ad":
        mem = await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", uid)
        return ("📯 <b>Reklama almashinuvi</b> — ittifoq a'zolari uchun: reklamangiz admin tasdig'idan so'ng barcha ittifoq guruhlariga "
                f"yuboriladi. Oralig'i: {cfg.i('ad_cooldown_hours')} soat.\n\n"
                + ("Menyudan «📯 Reklama» ni bosing." if mem else "Buning uchun avval ittifoqqa a'zo bo'lishingiz kerak."))
    if intent == "problem":
        if len(tk) >= 5:
            tid = await db.ins("INSERT INTO tickets(user_id,text,created_at) VALUES(?,?,?)", uid, text[:1500], now())
            await notify_admins(bot, f"🎫 <b>Yangi murojaat #{tid}</b> (AI aniqladi)\n👤 {mention(uid, user.full_name)}\n\n{esc(text[:1500])}",
                                kb([[B("↩️ Javob berish", f"a:tk:{tid}")]]))
            return f"🛡 Muammoingiz jiddiy qabul qilindi. Murojaat <b>#{tid}</b> adminlarga yuborildi — tez orada javob beramiz."
        return "🛡 Yordam beraman. Muammoni batafsil bitta xabarda yozing (nima, qayerda, kim) — adminlarga darhol yuboraman."
    if intent == "link":
        own = await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", uid)
        if own:
            return "🔗 Ittifoq guruhi havolasi: 📜 Mening arizam → «🔗 Ittifoq guruhi havolasi». Havola faqat sizga tegishli."
        return "Havola faqat qabul qilingan guruh egalariga beriladi. Avval ariza bering: «Ittifoqqa qanday qo'shilaman?»"
    if intent == "trouble":
        return ("🔧 <b>Tekshiruv ro'yxati</b>\n\n1️⃣ Botni «➕ Botni guruhga qo'shish» tugmasi orqali o'zingiz qo'shdingizmi?\n"
                "2️⃣ Bot to'liq admin (havola, o'chirish, cheklash, pin, ma'lumot) huquqlariga egami?\n"
                f"3️⃣ Siz guruhning {'EGASI' if cfg.b('owner_only') else 'egasi/admini'}misiz? (anonim admin bo'lmasin)\n"
                f"4️⃣ A'zolar soni kamida {cfg.i('min_members')} ta va guruh nomi mazmunlimi?\n\nHammasi to'g'ri bo'lsa «✅ Tekshirish»ni qayta bosing.")
    if intent == "contact":
        return "🕯 Adminlar bilan bog'lanish: menyuda «🕯 Murojaat» ni bosing va xabaringizni yozing."
    return "Tushundim. Menyudan kerakli bo'limni tanlang. 👑"


# ---------- ariza bahosi ----------
async def assess_score(a):
    notes = []
    ck = a.get("checks") or ""
    ok_n, bad_n = ck.count("✅"), ck.count("❌")
    tot = ok_n + bad_n
    sc = 50 * ok_n / tot if tot else 25
    mn = max(cfg.i("min_members"), 1)
    ratio = a["members"] / mn
    sc += min(25, 10 * ratio)
    if ratio >= 3:
        notes.append("a'zolar soni mezondan 3 barobar ko'p — kuchli guruh")
    elif ratio < 1.2:
        notes.append("a'zolar soni chegaraga juda yaqin")
    comment = (a.get("comment") or "").strip()
    if len(comment) >= 20:
        sc += 8
        notes.append("izoh mazmunli")
    elif not comment:
        notes.append("izoh yo'q")
    if re.search(r"https?://|t\.me/|sotaman|narx|reklama|obuna", comment.lower()):
        sc -= 15
        notes.append("⚠️ izohda reklama/havola belgilari")
    prev_rej = await db.cnt("SELECT COUNT(*) FROM applications WHERE user_id=? AND status='rejected' AND id<?", a["user_id"], a["id"])
    if prev_rej:
        sc -= min(20, 8 * prev_rej)
        notes.append(f"⚠️ oldin {prev_rej} marta rad etilgan")
    have = await db.cnt("SELECT COUNT(*) FROM groups WHERE owner_id=? AND status='active'", a["user_id"])
    if have:
        sc += 5
        notes.append(f"ittifoqda allaqachon {have} ta guruhi bor")
    if await is_blacklisted("user", a["user_id"]) or await is_blacklisted("group", a["chat_id"]):
        sc = 0
        notes.append("🚫 qora ro'yxatda")
    if bad_n:
        notes.append(f"{bad_n} ta mezon bajarilmagan")
    sc = max(0, min(100, int(sc)))
    rec = "✅ Qabul" if sc >= 75 and not bad_n else ("❌ Rad" if sc < 45 else "❓ Qo'shimcha tekshiruv")
    return sc, rec, notes


async def ai_assess(a):
    sc, rec, notes = await assess_score(a)
    L = [f"📊 Ball: <b>{sc}/100</b>", f"💡 Tavsiya: <b>{rec}</b>"]
    L += [f"• {esc(x)}" for x in notes]
    if rec.startswith("❓"):
        L.append("🔎 Tekshiring: guruhga kirib faolligini ko'ring, egasidan izoh so'rang.")
    return "\n".join(L)


# ---------- tahlil, reja, e'lon yozish ----------
async def insights():
    s = await stats_data()
    L = ["🧠 <b>Legion tahlili</b>\n"]
    tips = []
    old = await db.one("SELECT created_at FROM applications WHERE status='pending' ORDER BY id LIMIT 1")
    if s["pending"]:
        hrs = (now() - old["created_at"]) // 3600
        L.append(f"📥 {s['pending']} ta ariza kutmoqda (eng eskisi {hrs} soat oldin).")
        if hrs >= 24:
            tips.append("Arizalarni 24 soatdan oshirmay ko'ring — kechikkan ariza beruvchi qiziqishini yo'qotadi.")
    rows = await growth_rows(7)
    if rows:
        tot_d = sum(d for _, d in rows)
        L.append(f"👥 {s['groups']} guruh, {s['members']} a'zo; 7 kunlik o'zgarish: <b>{tot_d:+d}</b>.")
        grow = sorted(rows, key=lambda x: -x[1])[:3]
        shrink = [x for x in sorted(rows, key=lambda x: x[1]) if x[1] < 0][:3]
        if grow and grow[0][1] > 0:
            L.append("🚀 Eng tez o'sganlar: " + ", ".join(f"{esc(g['title'])} ({d:+d})" for g, d in grow if d > 0))
            tips.append(f"«{grow[0][0]['title']}» tajribasini boshqalarga ulashing va ittifoq nomidan rag'batlantiring.")
        if shrink:
            L.append("📉 Kamayayotganlar: " + ", ".join(f"{esc(g['title'])} ({d:+d})" for g, d in shrink))
            tips.append("Kamayayotgan guruh egalari bilan gaplashing: turnir yoki reklama almashinuvi ularga a'zo olib kelishi mumkin.")
    else:
        L.append("🏰 Hali ittifoq guruhlari yo'q — birinchi arizalarni jalb qilish vaqti.")
    lost = await db.cnt("SELECT COUNT(*) FROM groups WHERE status='lost'")
    if lost:
        L.append(f"🚨 {lost} ta guruhda bot yo'qotilgan.")
        tips.append("Yo'qotilgan guruh egalari bilan bog'lanib, botni qayta admin qildiring.")
    appr, rej = s["approved"], s["rejected"]
    if appr + rej >= 3:
        L.append(f"📮 Qabul ulushi: {appr * 100 // (appr + rej)}% ({appr} qabul / {rej} rad).")
    low = await db.cnt("SELECT COUNT(*) FROM applications WHERE status='rejected' AND checks LIKE '%❌ A''zolar soni%'")
    if low >= 2:
        tips.append(f"{low} ta ariza a'zolar soni kamligi sabab rad bo'lgan. Minimal chegarani ({cfg.i('min_members')}) biroz tushirishni o'ylab ko'ring: «min a'zolarni {max(10, cfg.i('min_members') - 10)} qil».")
    if s["users"] >= 10 and (appr + rej + s["pending"]) * 100 // max(s["users"], 1) < 15:
        tips.append("Bot foydalanuvchilarining kam qismi ariza beryapti — talablar qat'iy bo'lishi mumkin yoki jarayon tushunarsiz. «Ittifoq haqida» matnini kuchaytiring.")
    if not await db.cnt("SELECT COUNT(*) FROM tournaments WHERE status='open'"):
        tips.append("Ochiq turnir yo'q. Turnir — a'zolar faolligini oshirishning eng tez yo'li: «turnir yarat: nom | tavsif | vaqt».")
    if not await db.cnt("SELECT COUNT(*) FROM ads WHERE created_at>?", now() - 7 * 86400):
        tips.append("Oxirgi 7 kunda reklama almashinuvi bo'lmagan. a'zolarga e'lon qilib, bu imkoniyatni eslating.")
    if not cfg.get("alliance_chat_id"):
        tips.append("⚠️ Ittifoq guruhi ulanmagan: guruhda botni admin qilib /bind yozing.")
    if not cfg.get("stats_channel_id"):
        tips.append("Statistika kanalini ulang (Panel → Ulanishlar) — ochiq hisobot ittifoq obro'sini oshiradi.")
    if not cfg.i("auto_report"):
        tips.append("Avto-hisobotni yoqing: «avto hisobot haftalik».")
    if not await db.cnt("SELECT COUNT(*) FROM kb"):
        tips.append("Bilim bazasi bo'sh. «bilim qo'sh: sarlavha | matn» bilan qoidalar va FAQ ni kiriting — AI shular asosida javob beradi.")
    if tips:
        L.append("\n💡 <b>Tavsiyalar:</b>")
        L += [f"{i}. {esc(t)}" for i, t in enumerate(tips[:7], 1)]
    return "\n".join(L)


async def plan_text():
    rows = await growth_rows(7)
    top = max(rows, key=lambda x: x[1])[0]["title"] if rows else None
    shr = [g["title"] for g, d in rows if d < 0][:2]
    pend = await db.cnt("SELECT COUNT(*) FROM applications WHERE status='pending'")
    has_tour = await db.cnt("SELECT COUNT(*) FROM tournaments WHERE status='open'")
    steps = [
        f"<b>1-kun:</b> {'kutilayotgan ' + str(pend) + ' ta arizani ko‘rib chiqing' if pend else 'ittifoq guruhi va kanal ulanganini tekshiring'}.",
        f"<b>2-kun:</b> {'«' + '», «'.join(esc(x) for x in shr) + '» egalari bilan gaplashing' if shr else 'a‘zolardan fikr so‘rang: nimani yaxshilash kerak?'}.",
        f"<b>3-kun:</b> {'turnir juftliklarini tuzing' if has_tour else 'yangi turnir yarating va e‘lon qiling'}.",
        "<b>4-kun:</b> reklama almashinuvini e'lon qilib, a'zolarni ishtirokka chorlang.",
        f"<b>5-kun:</b> {'«' + esc(top) + '» ni haftaning eng faol guruhi deb e‘lon qiling' if top else 'ittifoq qoidalarini e‘lon qiling'}.",
        "<b>6-kun:</b> rad etilgan arizalar sabablarini ko'rib, mezonlarni sozlang.",
        "<b>7-kun:</b> haftalik hisobotni kanalga yuboring va keyingi haftaga reja tuzing.",
    ]
    return "🚀 <b>7 kunlik o'sish rejasi</b>\n\n" + "\n".join(steps)


async def draft_announcement(n):
    s = await stats_data()
    g, m = s["groups"], s["members"]
    if "turnir" in n:
        v = [
            "🛡 <b>LEGION TURNIRI E'LON QILINDI!</b>\n\nKuchlilar maydonga chorlanadi. Ro'yxatdan o'tish — guruh egasi orqali botda.\n"
            "Shon, sovrin va ittifoq obro'si — g'oliblarga. ⚔️\n\n👑 Legion · Qirollar ittifoqi",
            "⚔️ <b>Taxt uchun jang boshlanadi!</b>\n\nLegion turniri uchun ro'yxat ochiq. Guruhingizni olib keling — o'z kuchingizni isbotlang.\n\n"
            "📜 Ro'yxat: bot → 🛡 Turnirlar",
        ]
    elif "qoida" in n:
        v = [
            "📜 <b>LEGION QOIDALARI</b>\n\n1️⃣ Ittifoq a'zosiga hurmat — shart.\n2️⃣ Spam va o'zaro hujum — taqiqlanadi.\n"
            "3️⃣ Muammo bo'lsa — botdagi 🕯 Murojaat orqali yozing.\n\nQoidaga rioya — kuchimiz asosi. 👑",
        ]
    elif has(n.split(), "yangi", "xush", "qabul"):
        v = [f"👑 <b>Legion saflari kengaydi!</b>\n\nIttifoqqa yangi a'zolar qo'shildi. Hozir <b>{g}</b> guruh va <b>{m}</b> a'zo birlikda!\n\n"
             "Xush kelibsiz, Kengash a'zolari! ⚜️"]
    else:
        v = [f"⚜️ <b>LEGION · QIROLLAR ITTIFOQI</b>\n\n<b>{g}</b> guruh · <b>{m}</b> a'zo — hammasi bir saf, bir maqsad.\n"
             "Kuch — birlikda. Hurmat — sadoqatda. Shon — LEGION bilan. 👑",
             "🏰 <b>Legion yo'lida davom etamiz!</b>\n\nHimoya, turnirlar va hamkorlik — barchasi ittifoq ichida.\n"
             "Savol yoki taklif bo'lsa, botdagi 🕯 Murojaat sizga ochiq."]
    out = ["✍️ <b>E'lon variantlari</b> (yuborish uchun: <code>e'lon: matn</code>)\n"]
    for i, t in enumerate(v, 1):
        out.append(f"<b>— {i}-variant —</b>\n{t}\n")
    return "\n".join(out)


# ---------- egalar miyasi ----------
SET_RX = [
    ("ad_cooldown_hours", r"reklama\s+(oraligi|muddat\w*|cooldown)"),
    ("min_members", r"(min\w*|kamida)\s+azo"),
    ("max_members", r"(maks\w*|max\w*|kopi\s*bilan)\s+azo"),
    ("min_title_len", r"nom\w*\s+(uzunlig\w*|belgi)"),
    ("max_groups_per_owner", r"(bir\s+egadan|ega\s+boshiga|maks\w*\s+guruh)"),
    ("cooldown_hours", r"(cooldown|kutish\s+muddat\w*|qayta\s+ariza)"),
    ("ai_user_limit", r"ai\s+limit|kunlik\s+limit"),
    ("owner_only", r"faqat\s+ega|ega\s+shart|egasi\s+shart"),
    ("require_full_admin", r"tolaq?\s+admin|toliq\s+admin"),
    ("require_public", r"ochiq\s+guruh|username\s+shart|ommaviy"),
    ("require_comment", r"izoh\s+(majbur\w*|shart)"),
    ("strict", r"\bqatiy\b|\bstrict\b"),
    ("auto_mode", r"avto\w*\s*qabul|avtomatik\s+qabul"),
    ("guard", r"qoriqchi|\bguard\b"),
    ("pin_broadcast", r"\bpin\b"),
    ("ai_autonomy", r"tasdiqsiz|avtonom\w*"),
    ("auto_report", r"avto\s*hisobot|hisobot\s+(kunlik|haftalik)"),
]


async def apply_setting(uid, key, n):
    lbl, typ, _d, _g = SETTINGS[key]
    cur = cfg.get(key)
    if typ == "bool":
        off = re.search(r"\b(ochir\w*|toxtat\w*|bekor\w*|yoqma\w*)\b", n)
        on = re.search(r"\b(yoq\w*|faollashtir\w*|ha|on)\b", n)
        if not off and not on:
            return f"⚙️ {lbl}: <b>{'yoqilgan' if cur == '1' else 'o‘chiq'}</b>.\nO'zgartirish: «{lbl.split('(')[0].strip().lower()} yoq» yoki «... o'chir»."
        val = "0" if off else "1"
    else:
        nums = re.findall(r"\d+", n)
        if key == "auto_report":
            if "haftalik" in n:
                nums = ["7"]
            elif "kunlik" in n:
                nums = ["1"]
            elif re.search(r"\bochir\w*", n):
                nums = ["0"]
        if not nums:
            return f"⚙️ {lbl}: <b>{esc(cur)}</b>.\nO'zgartirish uchun raqam ayting, masalan: «{lbl.split('(')[0].strip().lower()} 50 qil»."
        val = str(int(nums[0]))
    await cfg.set(key, val)
    await log_action(uid, "ai_set", f"{key}={val}")
    shown = ("yoqildi ✅" if val == "1" else "o‘chirildi ❌") if typ == "bool" else f"<b>{val}</b> qilindi ✅"
    return f"⚙️ {esc(lbl)}: {shown}"


OWNER_HELP = (
    "🤖 <b>Men nima qila olaman</b>\n\n"
    "📥 «kutilayotgan arizalar» — ball va tavsiya bilan\n"
    "✅ «12 qabul qil» · ❌ «12 rad et sabab: a'zolar kam»\n"
    "🤖 «mezonga mos hammasini qabul qil»\n"
    "⚙️ «min a'zolarni 50 qil», «avto qabulni yoq», «qayta ariza 12 soat», «mezonlar»\n"
    "📊 «statistika», «o'sish 30 kun», «guruhlar»\n"
    "🧠 «tahlil», «7 kunlik reja»\n"
    "📣 «e'lon yoz turnir» · «e'lon: matn»\n"
    "🏟 «turnir yarat: nom | tavsif | vaqt»\n"
    "🚫 «ban 123456789», «qora ro'yxat»\n"
    "🎫 «murojaatlar» · «javob #5: matn»\n"
    "🧠 «bilim qo'sh: sarlavha | matn», «bilim ro'yxati»\n"
    "Xavfli amallar sizning tasdig'ingizdan keyin bajariladi."
)


async def owner_brain(bot, user, text):
    uid = user.id
    raw = re.sub(r"yo['’ʻ‘`]q", "ochir", text, flags=re.I)
    n, tk = norm(raw), toks(raw)
    ctx = {"bot": bot, "actor": uid, "owner": True}
    if re.match(r"^elon\s+(yoz|tayyorla|tuz|ber)", n):
        return await draft_announcement(n)
    m = re.match(r"^\s*e['’ʻ‘`]?lon\b[^:\n]{0,25}:\s*(.+)$", text.strip(), re.S | re.I)
    if m:
        body = m.group(1).strip()
        return sr(await stage(ctx, "broadcast", {"text": body}, f"📣 <b>E'lon barcha guruhlarga:</b>\n\n{md_to_html(body)}"))
    if re.match(r"^turnir (yarat|qosh|och|elon)", n):
        parts = [x.strip() for x in raw.split(":", 1)[1].split("|")] if ":" in raw else []
        if len(parts) < 3 or not all(parts[:3]):
            return "🏟 Format: <code>turnir yarat: nomi | tavsifi | vaqti</code>"
        p = {"title": parts[0][:100], "description": parts[1][:1500], "starts_at": parts[2][:100]}
        return sr(await stage(ctx, "tournament", p, f"🏟 Turnir: <b>{esc(p['title'])}</b>\n{esc(p['description'])}\n🕒 {esc(p['starts_at'])}"))
    if re.match(r"^bilim (qosh|yoz|saqla)", n):
        if ":" not in raw or "|" not in raw:
            return "🧠 Format: <code>bilim qo'sh: sarlavha | matn</code>"
        t, c = [x.strip() for x in raw.split(":", 1)[1].split("|", 1)]
        await db.exec("INSERT INTO kb(title,content) VALUES(?,?)", t[:100], c[:1500])
        return f"✅ Bilim bazasiga qo'shildi: <b>{esc(t)}</b>"
    m = re.search(r"javob\s*#?(\d+)\s*[:\-]\s*(.+)", raw, re.S | re.I)
    if m:
        return sr(await stage(ctx, "reply_ticket", {"id": int(m.group(1)), "text": m.group(2).strip()},
                              f"↩️ Murojaat #{m.group(1)} ga javob:\n\n{esc(m.group(2).strip())}"))
    if has(tk, "hamma", "barcha", "hammasini") and has(tk, "qabul", "tasdiq", "maqul"):
        return sr(await stage(ctx, "approve_ok", {}, "✅ Barcha mezonga to'liq mos kutilayotgan arizalarni qabul qilish"))
    for key, rx in SET_RX:
        if re.search(rx, n):
            return await apply_setting(uid, key, n)
    mnum = re.search(r"#?\b(\d{1,5})\b", n)
    approve, reject = has(tk, "qabul", "tasdiq", "maqul", "ok"), has(tk, "rad", "qaytar")
    if mnum and (approve or reject) and (has(tk, "ariza", "arizani", "arizasini") or "#" in raw or re.match(r"^\s*#?\d+", raw)):
        aid = int(mnum.group(1))
        a = await db.one("SELECT * FROM applications WHERE id=?", aid)
        if not a:
            return f"❗ Ariza #{aid} topilmadi."
        if a["status"] != "pending":
            return f"ℹ️ Ariza #{aid} allaqachon ko'rib chiqilgan ({ST_LABEL.get(a['status'])})."
        dec = "reject" if reject else "approve"
        rs = re.search(r"sabab\w*\s*[:\-]?\s*(.+)$", raw, re.I | re.S)
        reason = rs.group(1).strip() if rs else ""
        return sr(await stage(ctx, "decide", {"id": aid, "decision": dec, "reason": reason},
                              f"Ariza #{aid} «{esc(a['chat_title'])}»: <b>{'✅ QABUL' if dec == 'approve' else '❌ RAD'}</b>\n{esc(reason)}"))
    ids = [int(x) for x in re.findall(r"-?\d{6,}", n)]
    if ph(n, "qora royxat"):
        if ids and has(tk, "qosh", "kirit", "yoz"):
            for i in ids:
                await db.exec("INSERT OR IGNORE INTO blacklist(kind,target,note,added_at) VALUES(?,?,?,?)", "group" if i < 0 else "user", i, "AI", now())
            return f"🚫 Qora ro'yxatga qo'shildi: {', '.join(map(str, ids))}"
        if ids and has(tk, "ochir", "chiqar", "olib"):
            for i in ids:
                await db.exec("DELETE FROM blacklist WHERE target=?", i)
            return "✅ Qora ro'yxatdan olib tashlandi."
        rows = await db.all("SELECT kind,target,note FROM blacklist ORDER BY id DESC LIMIT 20")
        return "🚫 <b>Qora ro'yxat</b>\n" + ("\n".join(f"• {r['kind']} <code>{r['target']}</code> {esc(r['note'])}" for r in rows) or "bo'sh")
    if ids and has(tk, "ban", "banla", "chetlat"):
        uid_t = [i for i in ids if i > 0]
        if uid_t:
            return sr(await stage(ctx, "gban", {"user_id": uid_t[0], "reason": "Admin qarori"}, f"🔨 {uid_t[0]} ni barcha guruhlardan ban qilish"))
    cg = re.search(r"-\d{9,}", n)
    if cg and has(tk, "guruh", "guruhni") and has(tk, "chiqar", "ochir"):
        rs = re.search(r"sabab\w*\s*[:\-]?\s*(.+)$", raw, re.I | re.S)
        g = await db.one("SELECT title FROM groups WHERE chat_id=?", int(cg.group()))
        return sr(await stage(ctx, "remove_group", {"chat_id": int(cg.group()), "reason": rs.group(1).strip() if rs else "Admin qarori"},
                              f"🚫 Guruhni chiqarish: <b>{esc(g['title'] if g else cg.group())}</b>"))
    if has(tk, "murojaat", "murojaatlar", "ticket", "tiket"):
        rows = await db.all("SELECT id,text FROM tickets WHERE status='open' ORDER BY id LIMIT 15")
        return ("🎫 <b>Ochiq murojaatlar</b>\n" + "\n".join(f"#{r['id']}: {esc(short(r['text'], 80))}" for r in rows) +
                "\n\nJavob: <code>javob #5: matn</code>") if rows else "🎫 Ochiq murojaat yo'q."
    if has(tk, "reja", "plan"):
        return await plan_text()
    if has(tk, "tahlil", "maslahat", "strategiya", "tavsiya"):
        return await insights()
    if has(tk, "ariza", "arizalar", "navbat", "kutilayotgan"):
        rows = await db.all("SELECT * FROM applications WHERE status='pending' ORDER BY id LIMIT 10")
        if not rows:
            return "📥 Kutilayotgan ariza yo'q. ✅"
        L = ["📥 <b>Kutilayotgan arizalar</b>\n"]
        for a in rows:
            sc, rec, notes = await assess_score(a)
            L.append(f"<b>#{a['id']}</b> · {esc(short(a['chat_title'], 24))} · {a['members']}👥\n   {sc}/100 → {rec}" + (f" ({esc(notes[0])})" if notes else ""))
        L.append("\n«12 qabul qil» · «12 rad et sabab: ...» · «mezonga mos hammasini qabul qil»")
        return "\n".join(L)
    if has(tk, "osish", "osdi", "dinamika"):
        d = re.search(r"(\d{1,3})\s*kun", n)
        return await growth_text(int(d.group(1)) if d else 7)
    if has(tk, "guruhlar", "reyting", "top"):
        return await rating_text()
    if has(tk, "statistika", "hisobot", "raqamlar", "holat"):
        return await stats_text()
    if has(tk, "bilim"):
        rows = await db.all("SELECT id,title FROM kb ORDER BY id")
        return "🧠 <b>Bilim bazasi</b>\n" + ("\n".join(f"{r['id']}. {esc(r['title'])}" for r in rows) or "bo'sh — «bilim qo'sh: sarlavha | matn»")
    if has(tk, "mezon", "mezonlar", "sozlama", "sozlamalar"):
        auto = "\n".join(f"• {SETTINGS[k][0]}: {'✅' if cfg.b(k) else '❌'}" for k in ("auto_mode", "guard", "strict", "ai_autonomy"))
        return f"⚙️ <b>Joriy mezonlar</b>\n\n{criteria_text()}\n\n{auto}\n\nO'zgartirish: «min a'zolarni 50 qil»"
    if has(tk, "yordam", "buyruqlar", "help") or re.search(r"nima\s+qila", n):
        return OWNER_HELP
    base = await user_brain(bot, user, text)
    if base.startswith("Savolingizni to'liq tushunmadim"):
        return "🤔 Buyruqni tushunmadim.\n\n" + OWNER_HELP
    return base


def ph(n, *phrases):
    return any(p in n for p in phrases)


async def ai_agent(bot, user, text, owner_mode):
    if not cfg.b("ai_enabled"):
        return "🤖 AI hozircha o'chirilgan."
    uid = user.id
    if not is_admin(uid):
        used = await db.cnt("SELECT COUNT(*) FROM ai_history WHERE user_id=? AND role='user' AND ts>=?", uid, today_start())
        if used >= cfg.i("ai_user_limit"):
            return "⏳ Bugungi AI limitingiz tugadi. Ertaga qayta urinib ko'ring yoki 🕯 Murojaat yuboring."
    try:
        ans = await (owner_brain if owner_mode else user_brain)(bot, user, text)
    except Exception:
        log.exception("ai")
        return "⚠️ Kutilmagan xatolik. Birozdan keyin urinib ko'ring."
    await db.exec("INSERT INTO ai_history(user_id,role,content,ts) VALUES(?,?,?,?)", uid, "user", text[:200], now())
    await db.exec("DELETE FROM ai_history WHERE ts<?", now() - 3 * 86400)
    return ans[:3900]


async def stage(ctx, action, payload, preview):
    if cfg.b("ai_autonomy"):
        res = await execute_action(ctx["bot"], ctx["actor"], action, payload)
        return {"status": "done", "result": res}
    token = secrets.token_hex(4)
    await db.exec("INSERT INTO pending_actions VALUES(?,?,?,?,?)", token, ctx["actor"], action,
                  json.dumps(payload, ensure_ascii=False), now())
    await ctx["bot"].send_message(
        ctx["actor"], f"🤖 <b>AI tasdiq so'rayapti</b>\n\n{preview}",
        reply_markup=kb([[B("✅ Tasdiqlash", f"pa:ok:{token}"), B("❌ Bekor", f"pa:no:{token}")]]))
    return {"status": "awaiting_owner_confirmation", "note": "Tasdiqlash tugmasi egasiga yuborildi."}


async def execute_action(bot, actor, action, p):
    if action == "decide":
        if p.get("decision") == "approve":
            ok, msg = await approve_application(bot, int(p["id"]), actor)
        else:
            ok, msg = await reject_application(bot, int(p["id"]), actor, p.get("reason", ""))
        return msg
    if action == "broadcast":
        s, f = await broadcast(bot, text=md_to_html(p["text"]), pin=cfg.b("pin_broadcast"))
        return f"E'lon yuborildi: {s} ta guruh, xato: {len(f)}"
    if action == "remove_group":
        return (await remove_group(bot, int(p["chat_id"]), p.get("reason", ""), actor))[1]
    if action == "gban":
        ok, bad = await global_ban(bot, int(p["user_id"]), p.get("reason", ""))
        return f"Ban qilindi: {ok} ta chatda, xato: {bad}"
    if action == "tournament":
        tid = await db.ins("INSERT INTO tournaments(title,descr,starts,created_at) VALUES(?,?,?,?)",
                           p["title"], p["description"], p["starts_at"], now())
        s, f = await announce_tournament(bot, tid)
        return f"Turnir #{tid} yaratildi va {s} ta guruhga e'lon qilindi"
    if action == "reply_ticket":
        t = await db.one("SELECT * FROM tickets WHERE id=?", int(p["id"]))
        if not t:
            return "Murojaat topilmadi"
        await db.exec("UPDATE tickets SET status='closed', answer=?, answered_at=? WHERE id=?", p["text"], now(), t["id"])
        try:
            await bot.send_message(t["user_id"], f"📩 <b>Legion ma'muriyatidan javob (#{t['id']}):</b>\n\n{md_to_html(p['text'])}")
        except Exception:
            return "Javob saqlandi, lekin foydalanuvchiga yuborib bo'lmadi"
        return "Javob yuborildi"
    if action == "approve_ok":
        n_ok = 0
        for a in await db.all("SELECT * FROM applications WHERE status='pending' ORDER BY id"):
            if "❌" not in (a["checks"] or ""):
                ok, _m = await approve_application(bot, a["id"], actor)
                n_ok += 1 if ok else 0
        return f"{n_ok} ta ariza qabul qilindi"
    return "Noma'lum amal"


# ════════════════════════════════════════════════════════════════
#  FOYDALANUVCHI HANDLERLARI
# ════════════════════════════════════════════════════════════════
user_router = Router()
admin_router = Router()
admin_router.message.filter(AdminOnly())
admin_router.callback_query.filter(AdminOnly())


def main_menu(uid):
    rows = [
        [B("👑 Ittifoqqa qo'shilish", "m:join"), B("📜 Mening arizam", "m:my")],
        [B("🏰 Ittifoq haqida", "m:about"), B("⚔️ Reyting", "m:rating")],
        [B("🛡 Turnirlar", "m:tour"), B("📯 Reklama", "m:ad")],
        [B("🕯 Murojaat", "m:tix"), B("🤖 Legion AI", "m:ai")],
        [B("🌐 Legion Family", "m:family")],
    ]
    if is_admin(uid):
        rows.append([B("🔱 Qirollik paneli", "a:home")])
    return kb(rows)


async def show_home(ev):
    u = ev.from_user
    text = cfg.get("welcome_text").replace("{name}", esc(u.first_name))
    await ui(ev, text, main_menu(u.id))


@user_router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(m: Message, state: FSMContext, command: CommandObject):
    await state.clear()
    if command.args == "tour":
        return await show_tournaments_user(m)
    await show_home(m)


@user_router.message(Command("help"), F.chat.type == "private")
async def cmd_help(m: Message):
    await m.answer("ℹ️ /start — asosiy menyu\n/panel — boshqaruv paneli (adminlar)\n/id — ID ni ko'rish")


@user_router.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"🆔 Sizning ID: <code>{m.from_user.id}</code>\n💬 Chat ID: <code>{m.chat.id}</code>")


@user_router.callback_query(F.data == "x")
async def cb_noop(c: CallbackQuery):
    await c.answer()


@user_router.callback_query(F.data == "m:home")
async def cb_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_home(c)


# ---- Ittifoqqa qo'shilish ----
@user_router.callback_query(F.data == "m:join")
async def cb_join(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    if await is_blacklisted("user", uid):
        return await c.answer("Siz ittifoqqa ariza bera olmaysiz.", show_alert=True)
    pend = await db.one("SELECT id FROM applications WHERE user_id=? AND status='pending'", uid)
    if pend:
        return await c.answer(f"Sizda ko'rib chiqilayotgan ariza bor (#{pend['id']}).", show_alert=True)
    last = await db.one("SELECT decided_at FROM applications WHERE user_id=? AND status='rejected' ORDER BY id DESC LIMIT 1", uid)
    cd = cfg.i("cooldown_hours") * 3600
    if last and cd and last["decided_at"] and now() - last["decided_at"] < cd:
        rem = cd - (now() - last["decided_at"])
        return await c.answer(f"Qayta ariza berish uchun {rem // 3600} soat {rem % 3600 // 60} daqiqa kuting.", show_alert=True)
    await state.clear()
    link = f"https://t.me/{BOT_USERNAME}?startgroup=legion&admin={ADMIN_RIGHTS}"
    text = (
        "📝 <b>LEGION ITTIFOQIGA qo'shilish arizasi</b>\n\n"
        "🤖 <b>1/2.</b> Botni guruhingizga qo'shib, unga <b>to'liq adminlik</b> bering (anonimlikdan tashqari barcha huquqlar).\n\n"
        "➕ Quyidagi tugma orqali qo'shsangiz, kerakli huquqlar avtomatik taklif qilinadi.\n"
        "❗ Botni guruhga o'zingiz qo'shishingiz kerak va siz o'sha guruhning "
        f"{'egasi' if cfg.b('owner_only') else 'egasi yoki admini'} bo'lishingiz shart.\n\n"
        f"📌 <b>Talablar:</b>\n{criteria_text()}\n\n"
        "Tayyor bo'lgach, «✅ Tekshirish» tugmasini bosing."
    )
    await ui(c, text, kb([[B("➕ Botni guruhga qo'shish", url=link)], [B("✅ Tekshirish", "m:chk")], [B("❌ Bekor qilish", "m:home")]]))


@user_router.callback_query(F.data == "m:chk")
async def cb_chk(c: CallbackQuery, state: FSMContext, bot: Bot):
    uid = c.from_user.id
    await c.answer("Tekshirilmoqda…")
    rows = await db.all("SELECT chat_id, title FROM bot_adds WHERE user_id=? AND ts>? ORDER BY ts DESC LIMIT 6", uid, now() - 7 * 86400)
    back = kb([[B("🔄 Qayta tekshirish", "m:chk")], [B("⬅️ Orqaga", "m:join")]])
    if not rows:
        return await ui(c, "❌ Siz qo'shgan guruh topilmadi.\n\nBotni «➕ Botni guruhga qo'shish» tugmasi orqali o'zingiz guruhga qo'shing va admin qiling.", back)
    good, bad = [], []
    for r in rows:
        res = await eval_group(bot, r["chat_id"], uid)
        allowed = res["ok"] or (not cfg.b("strict") and res["info"].get("bot_admin"))
        (good if allowed else bad).append((r, res))
    if not good:
        L = ["❌ <b>Mezonlarga mos guruh topilmadi:</b>"]
        for r, res in bad[:3]:
            L.append(f"\n🏷 <b>{esc(r['title'])}</b>\n{esc(checks_text(res))}")
        return await ui(c, "\n".join(L), back)
    if len(good) == 1:
        return await ask_comment(c, state, good[0][0]["chat_id"])
    btns = [[B(f"🏷 {short(r['title'], 30)} · {res['info']['members']}👥", f"m:pick:{r['chat_id']}")] for r, res in good]
    btns.append([B("⬅️ Orqaga", "m:join")])
    await ui(c, "✅ Bir nechta mos guruh topildi. Qaysi biri bilan ariza berasiz?", kb(btns))


@user_router.callback_query(F.data.startswith("m:pick:"))
async def cb_pick(c: CallbackQuery, state: FSMContext):
    cid = int(c.data.split(":")[2])
    if not await db.one("SELECT 1 AS x FROM bot_adds WHERE user_id=? AND chat_id=?", c.from_user.id, cid):
        return await c.answer("Guruh topilmadi", show_alert=True)
    await ask_comment(c, state, cid)


async def ask_comment(ev, state, chat_id):
    await state.set_state(UF.comment)
    await state.update_data(chat_id=chat_id)
    rows = []
    if not cfg.b("require_comment"):
        rows.append([B("⏭ O'tkazib yuborish", "m:skip")])
    rows.append([B("❌ Bekor qilish", "m:home")])
    await ui(ev, "✅ Guruhda bot adminligi va sizning huquqingiz tasdiqlandi!\n\n💬 <b>2/2.</b> Qo'shimcha izoh yozing"
                 + ("" if cfg.b("require_comment") else " yoki o'tkazib yuboring") + ":", kb(rows))


async def show_confirm(ev, state, bot, comment):
    d = await state.get_data()
    await state.update_data(comment=comment)
    res = await eval_group(bot, d["chat_id"], ev.from_user.id)
    i = res["info"]
    own = f"@{i['owner_un']}" if i.get("owner_un") else esc(i.get("owner_name") or "—")
    text = (
        "📋 <b>Arizangizni tekshiring</b> (ma'lumotlar guruhdan avtomatik olindi):\n\n"
        f"🏷 Guruh: <b>{esc(i.get('title'))}</b>\n"
        f"🔗 Havola: {('https://t.me/' + i['username']) if i.get('username') else 'yopiq guruh (bot havola yaratadi)'}\n"
        f"👑 Guruh egasi: {own}\n👥 A'zolar soni: {i.get('members')}\n"
        f"🤖 Bot guruhda admin: {'✅' if i.get('bot_admin') else '❌'}\n"
        f"💬 Izoh: {esc(comment) or '—'}\n\nHammasi to'g'rimi?"
    )
    await ui(ev, text, kb([[B("✅ Yuborish", "m:send"), B("❌ Bekor qilish", "m:home")]]))


@user_router.message(UF.comment, F.text)
async def msg_comment(m: Message, state: FSMContext, bot: Bot):
    await show_confirm(m, state, bot, m.text.strip()[:500])


@user_router.callback_query(F.data == "m:skip")
async def cb_skip(c: CallbackQuery, state: FSMContext, bot: Bot):
    await show_confirm(c, state, bot, "")


@user_router.callback_query(F.data == "m:send")
async def cb_send(c: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    if not d.get("chat_id"):
        return await ui(c, "Sessiya tugadi. Qaytadan boshlang.", kb([[B("⬅️ Menyu", "m:home")]]))
    aid, status = await submit_application(bot, c.from_user, d["chat_id"], d.get("comment", ""))
    await state.clear()
    if not aid:
        return await ui(c, f"❌ {esc(status)}", kb([[B("🔄 Qayta tekshirish", "m:chk")], [B("⬅️ Menyu", "m:home")]]))
    if status == "auto":
        return await ui(c, f"🎉 Arizangiz #{aid} avtomatik qabul qilindi! Ittifoq guruhi havolasi yuqorida yuborildi.", kb([[B("⬅️ Orqaga", "m:home")]]))
    await ui(c, f"✅ Arizangiz <b>#{aid}</b> raqami bilan qabul qilindi!\n\nKo'rib chiqilgach, natijani shu yerda xabar qilamiz. ⚜️",
             kb([[B("⬅️ Orqaga", "m:home")]]))


@user_router.callback_query(F.data == "m:my")
async def cb_my(c: CallbackQuery):
    uid = c.from_user.id
    apps = await db.all("SELECT * FROM applications WHERE user_id=? ORDER BY id DESC LIMIT 5", uid)
    groups = await db.all("SELECT * FROM groups WHERE owner_id=? AND status='active'", uid)
    L = ["📋 <b>Mening arizalarim</b>\n"]
    if not apps:
        L.append("Hali ariza bermagansiz.")
    for a in apps:
        L.append(f"#{a['id']} · {esc(a['chat_title'])} · {ST_LABEL.get(a['status'])}\n🕒 {fmt(a['created_at'])}"
                 + (f"\n📝 Sabab: {esc(a['reason'])}" if a["status"] == "rejected" and a["reason"] else "") + "\n")
    if groups:
        L.append("⚜️ <b>Ittifoqdagi guruhlaringiz:</b>\n" + "\n".join(f"• {esc(g['title'])} — {g['members']}👥" for g in groups))
    rows = []
    pend = next((a for a in apps if a["status"] == "pending"), None)
    if pend:
        rows.append([B("🚫 Arizani bekor qilish", f"m:cancel:{pend['id']}")])
    if groups:
        rows.append([B("🔗 Ittifoq guruhi havolasi", "m:relink")])
    rows.append([B("⬅️ Orqaga", "m:home")])
    await ui(c, "\n".join(L), kb(rows))


@user_router.callback_query(F.data.startswith("m:cancel:"))
async def cb_cancel(c: CallbackQuery, bot: Bot):
    aid = int(c.data.split(":")[2])
    n = await db.exec("UPDATE applications SET status='cancelled', decided_at=? WHERE id=? AND user_id=? AND status='pending'", now(), aid, c.from_user.id)
    if n:
        await refresh_notifs(bot, aid)
    await c.answer("Ariza bekor qilindi" if n else "Bekor qilib bo'lmadi", show_alert=True)
    await cb_my(c)


@user_router.callback_query(F.data == "m:relink")
async def cb_relink(c: CallbackQuery, bot: Bot):
    if not await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", c.from_user.id):
        return await c.answer("Sizda ittifoqdagi guruh yo'q", show_alert=True)
    link = await make_join_link(bot, f"Ega {c.from_user.id}")
    if not link:
        return await c.answer("Havola hozircha yaratilmadi, adminlarga murojaat qiling.", show_alert=True)
    await c.message.answer("⚜️ Ittifoq guruhi havolasi (faqat sizga tegishli):", reply_markup=kb([[B("⚜️ Qo'shilish", url=link)]]))
    await c.answer()


@user_router.callback_query(F.data == "m:about")
async def cb_about(c: CallbackQuery):
    s = await stats_data()
    t = cfg.get("about_text") + f"\n\n🏰 Ittifoq guruhlari: <b>{s['groups']}</b>  ·  👥 Jami a'zolar: <b>{s['members']}</b>"
    await ui(c, t, kb([[B("🤝 Qo'shilish", "m:join")], [B("⬅️ Orqaga", "m:home")]]))


@user_router.callback_query(F.data == "m:rating")
async def cb_rating(c: CallbackQuery):
    await ui(c, await rating_text(), kb([[B("⬅️ Orqaga", "m:home")]]))


@user_router.callback_query(F.data == "m:family")
async def cb_family(c: CallbackQuery):
    rows = []
    for line in cfg.get("family_links").splitlines():
        if "|" in line:
            name, url = [x.strip() for x in line.split("|", 1)]
            if url.startswith("http") or url.startswith("tg://"):
                rows.append([B(name, url=url)])
    rows.append([B("⬅️ Orqaga", "m:home")])
    await ui(c, "🌐 <b>Legion Family</b>" if len(rows) > 1 else "🌐 Havolalar hali qo'shilmagan.", kb(rows))


# ---- Turnirlar (foydalanuvchi) ----
async def show_tournaments_user(ev):
    uid = ev.from_user.id
    ts = await db.all("SELECT * FROM tournaments WHERE status='open' ORDER BY id DESC LIMIT 5")
    groups = await db.all("SELECT * FROM groups WHERE owner_id=? AND status='active'", uid)
    if not ts:
        return await ui(ev, "🏟 Hozircha ochiq turnirlar yo'q.", kb([[B("⬅️ Orqaga", "m:home")]]))
    L, rows = ["🏟 <b>Ochiq turnirlar</b>\n"], []
    for t in ts:
        regs = await db.cnt("SELECT COUNT(*) FROM tregs WHERE tid=?", t["id"])
        L.append(tour_text(t, regs) + "\n")
        for g in groups:
            done = await db.one("SELECT 1 AS x FROM tregs WHERE tid=? AND chat_id=?", t["id"], g["chat_id"])
            if not done:
                rows.append([B(f"➕ #{t['id']} ga: {short(g['title'], 24)}", f"mt:{t['id']}:{g['chat_id']}")])
            else:
                L.append(f"✅ «{esc(g['title'])}» ro'yxatdan o'tgan\n")
    if not groups:
        L.append("ℹ️ Ro'yxatdan o'tish uchun ittifoqda guruhingiz bo'lishi kerak.")
    rows.append([B("⬅️ Orqaga", "m:home")])
    await ui(ev, "\n".join(L), kb(rows))


@user_router.callback_query(F.data == "m:tour")
async def cb_tour(c: CallbackQuery):
    await show_tournaments_user(c)


@user_router.callback_query(F.data.startswith("mt:"))
async def cb_treg(c: CallbackQuery):
    _, tid, cid = c.data.split(":")
    g = await db.one("SELECT * FROM groups WHERE chat_id=? AND owner_id=? AND status='active'", int(cid), c.from_user.id)
    t = await db.one("SELECT * FROM tournaments WHERE id=? AND status='open'", int(tid))
    if not g or not t:
        return await c.answer("Ro'yxatdan o'tib bo'lmadi", show_alert=True)
    await db.exec("INSERT OR IGNORE INTO tregs VALUES(?,?,?,?)", int(tid), int(cid), c.from_user.id, now())
    await c.answer("✅ Ro'yxatdan o'tdingiz!", show_alert=True)
    await show_tournaments_user(c)


# ---- Reklama ----
@user_router.callback_query(F.data == "m:ad")
async def cb_ad(c: CallbackQuery, state: FSMContext):
    uid = c.from_user.id
    if not await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", uid):
        return await c.answer("Reklama faqat ittifoq a'zolari uchun.", show_alert=True)
    cd = cfg.i("ad_cooldown_hours") * 3600
    last = await db.one("SELECT created_at FROM ads WHERE user_id=? AND status!='rejected' ORDER BY id DESC LIMIT 1", uid)
    if last and cd and now() - last["created_at"] < cd:
        rem = cd - (now() - last["created_at"])
        return await c.answer(f"Keyingi reklama uchun {rem // 3600} soat {rem % 3600 // 60} daqiqa kuting.", show_alert=True)
    await state.set_state(UF.ad)
    await ui(c, "📣 <b>Reklama almashinuvi</b>\n\nReklama xabaringizni yuboring (matn, rasm yoki video). "
                "Admin tasdiqlagach, u barcha ittifoq guruhlariga yuboriladi.", kb([[B("❌ Bekor qilish", "m:home")]]))


@user_router.message(UF.ad)
async def msg_ad(m: Message, state: FSMContext, bot: Bot):
    aid = await db.ins("INSERT INTO ads(user_id,src_chat,src_msg,created_at) VALUES(?,?,?,?)", m.from_user.id, m.chat.id, m.message_id, now())
    await state.clear()
    for adm in all_admin_ids():
        try:
            await bot.send_message(adm, f"📣 <b>Reklama so'rovi #{aid}</b> — {mention(m.from_user.id, m.from_user.full_name)}")
            await bot.copy_message(adm, m.chat.id, m.message_id, reply_markup=kb([[B("✅ Yuborish", f"ap:ok:{aid}"), B("❌ Rad", f"ap:no:{aid}")]]))
        except Exception:
            pass
    await m.answer("✅ Reklamangiz adminlarga yuborildi. Natijani shu yerda xabar qilamiz.", reply_markup=kb([[B("⬅️ Menyu", "m:home")]]))


# ---- Murojaat ----
@user_router.callback_query(F.data == "m:tix")
async def cb_tix(c: CallbackQuery, state: FSMContext):
    await state.set_state(UF.ticket)
    await ui(c, "🎫 <b>Murojaat</b>\n\nMuammo yoki savolingizni yozing — adminlar javob beradi.", kb([[B("❌ Bekor qilish", "m:home")]]))


@user_router.message(UF.ticket, F.text)
async def msg_ticket(m: Message, state: FSMContext, bot: Bot):
    tid = await db.ins("INSERT INTO tickets(user_id,text,created_at) VALUES(?,?,?)", m.from_user.id, m.text[:2000], now())
    await state.clear()
    await notify_admins(bot, f"🎫 <b>Yangi murojaat #{tid}</b>\n👤 {mention(m.from_user.id, m.from_user.full_name)}\n\n{esc(m.text[:2000])}",
                        kb([[B("↩️ Javob berish", f"a:tk:{tid}")]]))
    await m.answer(f"✅ Murojaatingiz #{tid} qabul qilindi. Tez orada javob beramiz.", reply_markup=kb([[B("⬅️ Menyu", "m:home")]]))


# ---- AI (foydalanuvchi) ----
@user_router.callback_query(F.data == "m:ai")
async def cb_ai(c: CallbackQuery, state: FSMContext):
    await state.set_state(UF.ai)
    await ui(c, "🤖 <b>Legion Organizator AI</b>\n\nIttifoq, ariza, talablar yoki boshqa savolingizni yozing. Chiqish uchun tugmani bosing.",
             kb([[B("⬅️ Chiqish", "m:home")]]))


async def ai_reply(m: Message, bot: Bot, owner_mode, exit_cb):
    try:
        await bot.send_chat_action(m.chat.id, "typing")
    except Exception:
        pass
    ans = await ai_agent(bot, m.from_user, m.text, owner_mode)
    await m.answer(ans, reply_markup=kb([[B("⬅️ Chiqish", exit_cb)]]))


@user_router.message(UF.ai, F.text)
async def msg_ai(m: Message, bot: Bot):
    await ai_reply(m, bot, is_admin(m.from_user.id), "m:home")


# ---- Guruh hodisalari ----
@user_router.my_chat_member()
async def on_my_chat_member(ev: ChatMemberUpdated, bot: Bot):
    ctype = str(getattr(ev.chat.type, "value", ev.chat.type))
    if ctype not in ("group", "supergroup"):
        return
    new = ev.new_chat_member.status
    if new in ("member", "administrator"):
        if ev.from_user and not ev.from_user.is_bot:
            await db.exec(
                "INSERT INTO bot_adds(user_id,chat_id,title,ts) VALUES(?,?,?,?) ON CONFLICT(user_id,chat_id) DO UPDATE SET title=excluded.title, ts=excluded.ts",
                ev.from_user.id, ev.chat.id, ev.chat.title or "", now())
    elif new in ("left", "kicked"):
        await db.exec("DELETE FROM bot_adds WHERE chat_id=?", ev.chat.id)
        g = await db.one("SELECT * FROM groups WHERE chat_id=? AND status='active'", ev.chat.id)
        if g:
            await db.exec("UPDATE groups SET status='lost', note='bot chiqarib yuborildi' WHERE chat_id=?", ev.chat.id)
            await notify_admins(bot, f"🚨 «{esc(g['title'])}» guruhida bot chiqarib yuborildi! Ega: {mention(g['owner_id'], g['owner_name'])}")


@user_router.chat_join_request()
async def on_join_request(req: ChatJoinRequest):
    alliance = cfg.get("alliance_chat_id")
    if not alliance or str(req.chat.id) != alliance:
        return
    uid = req.from_user.id
    allowed = is_admin(uid) or await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", uid)
    if allowed and not await is_blacklisted("user", uid):
        await req.approve()
    else:
        await req.decline()


@user_router.chat_member()
async def on_chat_member(ev: ChatMemberUpdated, bot: Bot):
    alliance = cfg.get("alliance_chat_id")
    if not alliance or str(ev.chat.id) != alliance or not cfg.b("guard"):
        return
    if ev.new_chat_member.status not in ("member", "restricted"):
        return
    u = ev.new_chat_member.user
    if u.is_bot or is_admin(u.id):
        return
    if ev.from_user and ev.from_user.id != u.id and is_admin(ev.from_user.id):
        return  # admin o'zi qo'shgan
    ok = await db.one("SELECT 1 AS x FROM groups WHERE owner_id=? AND status='active'", u.id)
    if ok and not await is_blacklisted("user", u.id):
        return
    try:
        await bot.ban_chat_member(ev.chat.id, u.id)
        await bot.unban_chat_member(ev.chat.id, u.id, only_if_banned=True)
        await log_action(0, "guard_kick", u.id)
    except Exception:
        pass


# ════════════════════════════════════════════════════════════════
#  ADMIN PANELI
# ════════════════════════════════════════════════════════════════
async def admin_home(ev):
    pend = await db.cnt("SELECT COUNT(*) FROM applications WHERE status='pending'")
    tix = await db.cnt("SELECT COUNT(*) FROM tickets WHERE status='open'")
    s = await stats_data()
    alliance = "✅ ulangan" if cfg.get("alliance_chat_id") else "❌ ulanmagan"
    text = (
        "👑 <b>LEGION — Boshqaruv paneli</b>\n\n"
        f"🏰 Guruhlar: <b>{s['groups']}</b> · 👥 A'zolar: <b>{s['members']}</b>\n"
        f"📥 Kutilayotgan arizalar: <b>{pend}</b> · 🎫 Murojaatlar: <b>{tix}</b>\n"
        f"🔗 Ittifoq guruhi: {alliance}\n"
        f"🚦 Rejim: {'🤖 avto-qabul' if cfg.b('auto_mode') else '👤 qo‘lda ko‘rib chiqish'}"
    )
    rows = [
        [B(f"📥 Arizalar ({pend})", "a:apps:pending:0"), B("🏰 Guruhlar", "a:grp:0")],
        [B("📊 Statistika", "a:stat"), B("📈 O'sish", "a:grow")],
        [B("⚙️ Mezonlar", "a:set"), B("📣 E'lon", "a:bc")],
        [B("🏟 Turnirlar", "a:tour"), B(f"🎫 Murojaatlar ({tix})", "a:tix")],
        [B("🚫 Qora ro'yxat", "a:bl"), B("🧠 Bilim bazasi", "a:kb")],
        [B("🤖 AI yordamchi", "a:ai"), B("🔗 Ulanishlar", "a:bind")],
        [B("✏️ Matnlar", "a:txts")],
    ]
    if is_super(ev.from_user.id):
        rows[-1].append(B("👥 Adminlar", "a:adm"))
    rows.append([B("⬅️ Asosiy menyu", "m:home")])
    await ui(ev, text, kb(rows))


@admin_router.message(Command("panel"), F.chat.type == "private")
async def cmd_panel(m: Message, state: FSMContext):
    await state.clear()
    await admin_home(m)


@admin_router.message(Command("stats"), F.chat.type == "private")
async def cmd_stats(m: Message):
    await m.answer(await stats_text())


@admin_router.message(Command("bind"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_bind(m: Message, bot: Bot):
    if m.from_user.id == 1087968824:
        return await m.reply("Anonim admin sifatida yozib bo'lmaydi. Anonimlikni o'chirib, qayta yozing.")
    try:
        me = await bot.get_chat_member(m.chat.id, bot.id)
    except Exception:
        return
    if me.status != "administrator" or not getattr(me, "can_invite_users", False) or not getattr(me, "can_restrict_members", False):
        return await m.reply("❗ Avval botni admin qiling (havola yaratish va a'zolarni cheklash huquqlari bilan).")
    await cfg.set("alliance_chat_id", m.chat.id)
    await log_action(m.from_user.id, "bind", m.chat.id)
    await m.reply("✅ Bu guruh <b>Ittifoq guruhi</b> sifatida ulandi. Qabul qilingan egalar shu yerga havola orqali qo'shiladi.")


@admin_router.callback_query(F.data == "a:home")
async def cb_a_home(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await admin_home(c)


# ---- Arizalar ----
@admin_router.callback_query(F.data.startswith("a:apps:"))
async def cb_a_apps(c: CallbackQuery):
    _, _, st, p = c.data.split(":")
    p = int(p)
    total = await db.cnt("SELECT COUNT(*) FROM applications WHERE status=?", st)
    rows = await db.all("SELECT * FROM applications WHERE status=? ORDER BY id DESC LIMIT 8 OFFSET ?", st, p * 8)
    tabs = [B(("• " if s == st else "") + lbl, f"a:apps:{s}:0") for s, lbl in (("pending", "⏳"), ("approved", "✅"), ("rejected", "❌"))]
    btns = [tabs] + [[B(f"#{a['id']} · {short(a['chat_title'], 20)} · {a['members']}👥", f"a:app:{a['id']}")] for a in rows]
    btns.append(pager(f"a:apps:{st}", p, total))
    btns.append([B("⬅️ Panel", "a:home")])
    await ui(c, f"📥 <b>Arizalar</b> — {ST_LABEL.get(st)} ({total})", kb(btns))


@admin_router.callback_query(F.data.startswith("a:app:"))
async def cb_a_app(c: CallbackQuery):
    a = await db.one("SELECT * FROM applications WHERE id=?", int(c.data.split(":")[2]))
    if not a:
        return await c.answer("Topilmadi", show_alert=True)
    await ui(c, app_card(a), app_admin_kb(a))


@admin_router.callback_query(F.data.startswith("a:ok:"))
async def cb_a_ok(c: CallbackQuery, bot: Bot):
    aid = int(c.data.split(":")[2])
    ok, msg = await approve_application(bot, aid, c.from_user.id)
    await c.answer(("✅ " if ok else "⚠️ ") + msg, show_alert=not ok)
    a = await db.one("SELECT * FROM applications WHERE id=?", aid)
    if a:
        await ui(c, app_card(a), app_admin_kb(a))


@admin_router.callback_query(F.data.startswith("a:no:"))
async def cb_a_no(c: CallbackQuery):
    aid = int(c.data.split(":")[2])
    rows = [[B(r, f"a:rj:{aid}:{i}")] for i, r in enumerate(REJECT_REASONS)]
    rows.append([B("⬅️ Orqaga", f"a:app:{aid}")])
    await ui(c, f"❌ <b>Ariza #{aid}</b> — rad etish sababini tanlang:", kb(rows))


@admin_router.callback_query(F.data.startswith("a:rj:"))
async def cb_a_rj(c: CallbackQuery, state: FSMContext, bot: Bot):
    _, _, aid, i = c.data.split(":")
    aid, i = int(aid), int(i)
    if i == 4:
        await state.set_state(AF.reject_reason)
        await state.update_data(aid=aid)
        return await ui(c, "✍️ Rad etish sababini yozing:", kb([[B("⬅️ Bekor", f"a:app:{aid}")]]))
    reason = "" if i == 5 else REJECT_REASONS[i]
    ok, msg = await reject_application(bot, aid, c.from_user.id, reason)
    await c.answer(msg, show_alert=not ok)
    a = await db.one("SELECT * FROM applications WHERE id=?", aid)
    if a:
        await ui(c, app_card(a), app_admin_kb(a))


@admin_router.message(AF.reject_reason, F.text)
async def msg_reject_reason(m: Message, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.clear()
    ok, msg = await reject_application(bot, d["aid"], m.from_user.id, m.text.strip()[:300])
    await m.answer(("✅ " if ok else "⚠️ ") + msg, reply_markup=kb([[B("📥 Arizalar", "a:apps:pending:0")]]))


@admin_router.callback_query(F.data.startswith("a:ai:"))
async def cb_a_ai(c: CallbackQuery, bot: Bot):
    a = await db.one("SELECT * FROM applications WHERE id=?", int(c.data.split(":")[2]))
    if not a:
        return await c.answer("Topilmadi", show_alert=True)
    await c.answer("🤖 Tahlil qilinmoqda…")
    txt = await ai_assess(a)
    await c.message.answer(f"🤖 <b>AI tahlil — ariza #{a['id']}</b>\n\n{txt}")


# ---- Guruhlar ----
@admin_router.callback_query(F.data.startswith("a:grp:"))
async def cb_a_grp(c: CallbackQuery):
    p = int(c.data.split(":")[2])
    total = await db.cnt("SELECT COUNT(*) FROM groups WHERE status='active'")
    rows = await db.all("SELECT * FROM groups WHERE status='active' ORDER BY members DESC LIMIT 8 OFFSET ?", p * 8)
    btns = [[B(f"{short(g['title'], 24)} · {g['members']}👥", f"a:g:{g['chat_id']}")] for g in rows]
    btns.append(pager("a:grp", p, total))
    btns.append([B("⬅️ Panel", "a:home")])
    await ui(c, f"🏰 <b>Ittifoq guruhlari</b> ({total})", kb(btns))


@admin_router.callback_query(F.data.startswith("a:g:"))
async def cb_a_g(c: CallbackQuery):
    cid = int(c.data.split(":")[2])
    g = await db.one("SELECT * FROM groups WHERE chat_id=?", cid)
    if not g:
        return await c.answer("Topilmadi", show_alert=True)
    d = next((d for gg, d in await growth_rows(7) if gg["chat_id"] == cid), 0)
    t = (f"🏰 <b>{esc(g['title'])}</b>\n\n👑 Ega: {mention(g['owner_id'], g['owner_name'])}\n👥 A'zolar: <b>{g['members']}</b> (7 kunda {d:+d})\n"
         f"🆔 <code>{cid}</code>\n📅 Qo'shilgan: {fmt(g['joined_at'])}\n🔎 Oxirgi tekshiruv: {fmt(g['last_check'])}\n📌 Holat: {g['status']}")
    rows = [[B("🔗 Havolani qayta yuborish", f"a:gl:{cid}")], [B("🚫 Ittifoqdan chiqarish", f"a:grm:{cid}")], [B("⬅️ Guruhlar", "a:grp:0")]]
    await ui(c, t, kb(rows))


@admin_router.callback_query(F.data.startswith("a:gl:"))
async def cb_a_gl(c: CallbackQuery, bot: Bot):
    g = await db.one("SELECT * FROM groups WHERE chat_id=?", int(c.data.split(":")[2]))
    link = await make_join_link(bot, f"Ega {g['owner_id']}") if g else None
    if not link:
        return await c.answer("Havola yaratilmadi (ittifoq guruhi ulanganini tekshiring)", show_alert=True)
    try:
        await bot.send_message(g["owner_id"], "⚜️ Ittifoq guruhi havolasi (faqat sizga tegishli):", reply_markup=kb([[B("⚜️ Qo'shilish", url=link)]]))
        await c.answer("✅ Egaga yuborildi", show_alert=True)
    except Exception:
        await c.answer("Egaga yuborib bo'lmadi", show_alert=True)


@admin_router.callback_query(F.data.startswith("a:grm:"))
async def cb_a_grm(c: CallbackQuery):
    cid = c.data.split(":")[2]
    await ui(c, "⚠️ Guruhni ittifoqdan chiqarishni tasdiqlaysizmi?", kb([[B("✅ Ha, chiqarish", f"a:grmy:{cid}"), B("❌ Yo'q", f"a:g:{cid}")]]))


@admin_router.callback_query(F.data.startswith("a:grmy:"))
async def cb_a_grmy(c: CallbackQuery, bot: Bot):
    ok, msg = await remove_group(bot, int(c.data.split(":")[2]), "Admin qarori", c.from_user.id)
    await c.answer(msg, show_alert=True)
    await ui(c, "✅ " + esc(msg), kb([[B("🏰 Guruhlar", "a:grp:0")]]))


# ---- Statistika / o'sish ----
@admin_router.callback_query(F.data == "a:stat")
async def cb_a_stat(c: CallbackQuery):
    await ui(c, await stats_text(), kb([[B("📤 Kanalga yuborish", "a:rep")], [B("⬅️ Panel", "a:home")]]))


@admin_router.callback_query(F.data == "a:grow")
async def cb_a_grow(c: CallbackQuery):
    await ui(c, await growth_text(7), kb([[B("7 kun", "a:grow"), B("30 kun", "a:grow30")], [B("⬅️ Panel", "a:home")]]))


@admin_router.callback_query(F.data == "a:grow30")
async def cb_a_grow30(c: CallbackQuery):
    await ui(c, await growth_text(30), kb([[B("7 kun", "a:grow"), B("30 kun", "a:grow30")], [B("⬅️ Panel", "a:home")]]))


@admin_router.callback_query(F.data == "a:rep")
async def cb_a_rep(c: CallbackQuery, bot: Bot):
    await post_report(bot)
    await c.answer("✅ Hisobot yuborildi", show_alert=True)


# ---- Sozlamalar ----
@admin_router.callback_query(F.data == "a:set")
async def cb_a_set(c: CallbackQuery):
    rows = [[B(lbl, f"a:sg:{k}")] for k, lbl in SET_GROUPS.items()]
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "⚙️ <b>Sozlamalar</b>\n\nQabul mezonlari, avtomatlashtirish va AI sozlamalarini shu yerda o'zgartirasiz.", kb(rows))


async def show_set_group(ev, grp):
    rows = []
    for k, (lbl, typ, _d, g) in SETTINGS.items():
        if g != grp:
            continue
        v = cfg.get(k)
        rows.append([B((("✅ " if v == "1" else "❌ ") + lbl) if typ == "bool" else f"{lbl}: {v}", f"a:st:{k}")])
    rows.append([B("⬅️ Sozlamalar", "a:set")])
    await ui(ev, f"<b>{SET_GROUPS[grp]}</b>\n\nTugmani bosib o'zgartiring:", kb(rows))


@admin_router.callback_query(F.data.startswith("a:sg:"))
async def cb_a_sg(c: CallbackQuery):
    await show_set_group(c, c.data.split(":")[2])


@admin_router.callback_query(F.data.startswith("a:st:"))
async def cb_a_st(c: CallbackQuery, state: FSMContext):
    k = c.data.split(":")[2]
    if k not in SETTINGS:
        return await c.answer()
    lbl, typ, _d, grp = SETTINGS[k]
    if typ == "bool":
        await cfg.set(k, "0" if cfg.b(k) else "1")
        await log_action(c.from_user.id, "set", f"{k}={cfg.get(k)}")
        return await show_set_group(c, grp)
    await state.set_state(AF.set_value)
    await state.update_data(key=k)
    await ui(c, f"✏️ <b>{lbl}</b>\nJoriy qiymat: <b>{cfg.get(k)}</b>\n\nYangi raqamni yuboring:", kb([[B("⬅️ Bekor", f"a:sg:{grp}")]]))


@admin_router.message(AF.set_value, F.text)
async def msg_set_value(m: Message, state: FSMContext):
    d = await state.get_data()
    if not re.fullmatch(r"\d{1,9}", m.text.strip()):
        return await m.answer("❗ Faqat raqam yuboring.")
    await cfg.set(d["key"], m.text.strip())
    await log_action(m.from_user.id, "set", f"{d['key']}={m.text.strip()}")
    await state.clear()
    await m.answer("✅ Saqlandi.", reply_markup=kb([[B("⚙️ Sozlamalar", f"a:sg:{SETTINGS[d['key']][3]}")]]))


# ---- Matnlar ----
@admin_router.callback_query(F.data == "a:txts")
async def cb_a_txts(c: CallbackQuery):
    rows = [[B(lbl, f"a:te:{k}")] for k, lbl in TEXT_LABELS.items()]
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "✏️ <b>Matnlar</b> — tahrirlash uchun tanlang:", kb(rows))


@admin_router.callback_query(F.data.startswith("a:te:"))
async def cb_a_te(c: CallbackQuery, state: FSMContext):
    k = c.data.split(":")[2]
    await state.set_state(AF.text_value)
    await state.update_data(key=k)
    cur = cfg.get(k) or "(bo'sh)"
    await ui(c, f"✏️ <b>{TEXT_LABELS[k]}</b>\n\nJoriy matn:\n{cur}\n\nYangi matnni yuboring (Telegram formatlash qo'llanadi):",
             kb([[B("♻️ Standartga qaytarish", f"a:tr:{k}")], [B("⬅️ Bekor", "a:txts")]]))


@admin_router.callback_query(F.data.startswith("a:tr:"))
async def cb_a_tr(c: CallbackQuery, state: FSMContext):
    await cfg.reset(c.data.split(":")[2])
    await state.clear()
    await c.answer("♻️ Standartga qaytarildi", show_alert=True)
    await cb_a_txts(c)


@admin_router.message(AF.text_value, F.text)
async def msg_text_value(m: Message, state: FSMContext):
    d = await state.get_data()
    await cfg.set(d["key"], m.html_text)
    await state.clear()
    await m.answer("✅ Matn saqlandi.", reply_markup=kb([[B("✏️ Matnlar", "a:txts")]]))


# ---- E'lon ----
@admin_router.callback_query(F.data == "a:bc")
async def cb_a_bc(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.bc_msg)
    await ui(c, "📣 <b>E'lon</b>\n\nBarcha ittifoq guruhlariga yuboriladigan xabarni yuboring (matn, rasm, video — istalgan).",
             kb([[B("⬅️ Bekor", "a:home")]]))


@admin_router.message(AF.bc_msg)
async def msg_bc(m: Message, state: FSMContext, bot: Bot):
    await state.update_data(src_chat=m.chat.id, src_msg=m.message_id, pin=cfg.b("pin_broadcast"))
    n = await db.cnt("SELECT COUNT(*) FROM groups WHERE status='active'")
    await m.answer(f"👆 Shu xabar <b>{n} ta guruhga</b> yuboriladi.", reply_markup=bc_kb(cfg.b("pin_broadcast")))


def bc_kb(pin):
    return kb([[B(f"📌 Pin: {'✅' if pin else '❌'}", "a:bcpin")], [B("🚀 Yuborish", "a:bcgo")], [B("❌ Bekor", "a:home")]])


@admin_router.callback_query(F.data == "a:bcpin")
async def cb_a_bcpin(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    pin = not d.get("pin")
    await state.update_data(pin=pin)
    await c.message.edit_reply_markup(reply_markup=bc_kb(pin))
    await c.answer()


@admin_router.callback_query(F.data == "a:bcgo")
async def cb_a_bcgo(c: CallbackQuery, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.clear()
    if not d.get("src_msg"):
        return await c.answer("Sessiya tugadi", show_alert=True)
    await c.answer("🚀 Yuborilmoqda…")
    await c.message.edit_text("🚀 E'lon yuborilmoqda, natija shu yerda chiqadi…")

    async def job():
        s, f = await broadcast(bot, src=(d["src_chat"], d["src_msg"]), pin=d.get("pin", False))
        txt = f"✅ E'lon yuborildi: <b>{s}</b> ta guruh."
        if f:
            txt += f"\n⚠️ Xato ({len(f)}): " + esc(", ".join(f[:10]))
        await bot.send_message(c.from_user.id, txt, reply_markup=kb([[B("⬅️ Panel", "a:home")]]))
        await log_action(c.from_user.id, "broadcast", f"{s} ok / {len(f)} xato")

    asyncio.create_task(job())


# ---- Turnirlar ----
@admin_router.callback_query(F.data == "a:tour")
async def cb_a_tour(c: CallbackQuery):
    ts = await db.all("SELECT * FROM tournaments ORDER BY id DESC LIMIT 10")
    rows = [[B(f"#{t['id']} {short(t['title'], 22)} · {'🟢' if t['status'] == 'open' else '🔒'}", f"a:t:{t['id']}")] for t in ts]
    rows.append([B("➕ Yangi turnir", "a:tn")])
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "🏟 <b>Turnirlar</b>", kb(rows))


@admin_router.callback_query(F.data == "a:tn")
async def cb_a_tn(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.t_title)
    await ui(c, "🏟 Turnir <b>nomini</b> yozing:", kb([[B("⬅️ Bekor", "a:tour")]]))


@admin_router.message(AF.t_title, F.text)
async def msg_t_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:100])
    await state.set_state(AF.t_desc)
    await m.answer("📝 Turnir <b>tavsifi</b> (qoidalar, sovrinlar):")


@admin_router.message(AF.t_desc, F.text)
async def msg_t_desc(m: Message, state: FSMContext):
    await state.update_data(descr=m.text.strip()[:1500])
    await state.set_state(AF.t_start)
    await m.answer("🕒 Boshlanish <b>vaqti</b> (masalan: 15-noyabr, 21:00):")


@admin_router.message(AF.t_start, F.text)
async def msg_t_start(m: Message, state: FSMContext):
    d = await state.get_data()
    tid = await db.ins("INSERT INTO tournaments(title,descr,starts,created_at) VALUES(?,?,?,?)", d["title"], d["descr"], m.text.strip()[:100], now())
    await state.clear()
    await m.answer(f"✅ Turnir #{tid} yaratildi.", reply_markup=kb([[B("📣 Guruhlarga e'lon qilish", f"a:tann:{tid}")], [B("🏟 Turnirlar", "a:tour")]]))


@admin_router.callback_query(F.data.startswith("a:t:"))
async def cb_a_t(c: CallbackQuery):
    tid = int(c.data.split(":")[2])
    t = await db.one("SELECT * FROM tournaments WHERE id=?", tid)
    if not t:
        return await c.answer("Topilmadi", show_alert=True)
    regs = await db.all("SELECT g.title FROM tregs r JOIN groups g ON g.chat_id=r.chat_id WHERE r.tid=?", tid)
    txt = tour_text(t, len(regs)) + ("\n\n" + "\n".join(f"• {esc(r['title'])}" for r in regs) if regs else "")
    rows = [[B("📣 E'lon qilish", f"a:tann:{tid}")], [B("🎲 Juftliklar", f"a:tpair:{tid}")]]
    if t["status"] == "open":
        rows.append([B("🔒 Ro'yxatni yopish", f"a:tclose:{tid}")])
    rows.append([B("⬅️ Turnirlar", "a:tour")])
    await ui(c, txt, kb(rows))


@admin_router.callback_query(F.data.startswith("a:tann:"))
async def cb_a_tann(c: CallbackQuery, bot: Bot):
    tid = int(c.data.split(":")[2])
    await c.answer("📣 Yuborilmoqda…")
    s, f = await announce_tournament(bot, tid)
    await c.message.answer(f"✅ Turnir e'loni {s} ta guruhga yuborildi." + (f"\n⚠️ Xato: {len(f)}" if f else ""))


@admin_router.callback_query(F.data.startswith("a:tclose:"))
async def cb_a_tclose(c: CallbackQuery):
    tid = int(c.data.split(":")[2])
    await db.exec("UPDATE tournaments SET status='closed' WHERE id=?", tid)
    await c.answer("🔒 Ro'yxat yopildi", show_alert=True)
    await cb_a_t(c)


@admin_router.callback_query(F.data.startswith("a:tpair:"))
async def cb_a_tpair(c: CallbackQuery, bot: Bot):
    tid = int(c.data.split(":")[2])
    regs = await db.all("SELECT g.title FROM tregs r JOIN groups g ON g.chat_id=r.chat_id WHERE r.tid=?", tid)
    if len(regs) < 2:
        return await c.answer("Kamida 2 ta guruh kerak", show_alert=True)
    names = [esc(r["title"]) for r in regs]
    random.shuffle(names)
    L = [f"🎲 <b>Turnir #{tid} juftliklari</b>\n"]
    for i in range(0, len(names) - 1, 2):
        L.append(f"⚔️ {names[i]}  <b>VS</b>  {names[i + 1]}")
    if len(names) % 2:
        L.append(f"\n⏭ Navbatsiz o'tadi: {names[-1]}")
    text = "\n".join(L)
    await c.message.answer(text, reply_markup=kb([[B("📣 Guruhlarga yuborish", f"a:tpsend:{tid}")]]))
    await state_cache_pairs(tid, text)
    await c.answer()


_PAIRS = {}


async def state_cache_pairs(tid, text):
    _PAIRS[tid] = text


@admin_router.callback_query(F.data.startswith("a:tpsend:"))
async def cb_a_tpsend(c: CallbackQuery, bot: Bot):
    tid = int(c.data.split(":")[2])
    text = _PAIRS.get(tid)
    if not text:
        return await c.answer("Qaytadan juftlik tuzing", show_alert=True)
    s, f = await broadcast(bot, text=text)
    await c.answer(f"✅ {s} ta guruhga yuborildi", show_alert=True)


# ---- Murojaatlar ----
@admin_router.callback_query(F.data == "a:tix")
async def cb_a_tix(c: CallbackQuery):
    ts = await db.all("SELECT * FROM tickets WHERE status='open' ORDER BY id LIMIT 15")
    rows = [[B(f"#{t['id']} · {short(t['text'], 28)}", f"a:tk:{t['id']}")] for t in ts]
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, f"🎫 <b>Ochiq murojaatlar</b> ({len(ts)})", kb(rows))


@admin_router.callback_query(F.data.startswith("a:tk:"))
async def cb_a_tk(c: CallbackQuery, state: FSMContext):
    t = await db.one("SELECT * FROM tickets WHERE id=?", int(c.data.split(":")[2]))
    if not t:
        return await c.answer("Topilmadi", show_alert=True)
    if t["status"] != "open":
        return await c.answer("Bu murojaatga javob berilgan", show_alert=True)
    u = await db.one("SELECT * FROM users WHERE user_id=?", t["user_id"])
    await state.set_state(AF.tix_reply)
    await state.update_data(tid=t["id"])
    await ui(c, f"🎫 <b>Murojaat #{t['id']}</b> — {mention(t['user_id'], (u or {}).get('name'))}\n\n{esc(t['text'])}\n\n✍️ Javobingizni yozing:",
             kb([[B("⬅️ Bekor", "a:tix")]]))


@admin_router.message(AF.tix_reply, F.text)
async def msg_tix_reply(m: Message, state: FSMContext, bot: Bot):
    d = await state.get_data()
    await state.clear()
    res = await execute_action(bot, m.from_user.id, "reply_ticket", {"id": d["tid"], "text": m.text})
    await m.answer("✅ " + res, reply_markup=kb([[B("🎫 Murojaatlar", "a:tix")]]))


# ---- Qora ro'yxat ----
@admin_router.callback_query(F.data == "a:bl")
async def cb_a_bl(c: CallbackQuery):
    rows_db = await db.all("SELECT * FROM blacklist ORDER BY id DESC LIMIT 15")
    rows = [[B(f"🗑 {r['kind']} {r['target']} {short(r['note'], 14)}", f"a:bld:{r['id']}")] for r in rows_db]
    rows.append([B("➕ Qo'shish", "a:bla")])
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "🚫 <b>Qora ro'yxat</b>\n\nO'chirish uchun yozuvni bosing. Foydalanuvchilar ariza bera olmaydi va ittifoq guruhiga kira olmaydi.", kb(rows))


@admin_router.callback_query(F.data == "a:bla")
async def cb_a_bla(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.bl_add)
    await ui(c, "➕ Yuboring: <code>user 123456789 izoh</code> yoki <code>group -1001234567890 izoh</code>", kb([[B("⬅️ Bekor", "a:bl")]]))


@admin_router.message(AF.bl_add, F.text)
async def msg_bl_add(m: Message, state: FSMContext):
    mt = re.match(r"^(user|group)\s+(-?\d+)\s*(.*)$", m.text.strip(), re.I)
    if not mt:
        return await m.answer("❗ Format: <code>user 123456789 izoh</code>")
    kind, target, note = mt.group(1).lower(), int(mt.group(2)), mt.group(3)[:100]
    await db.exec("INSERT OR IGNORE INTO blacklist(kind,target,note,added_at) VALUES(?,?,?,?)", kind, target, note, now())
    await state.clear()
    rows = [[B("🔨 Barcha guruhlardan ban", f"a:gban:{target}")]] if kind == "user" else []
    rows.append([B("🚫 Qora ro'yxat", "a:bl")])
    await m.answer("✅ Qora ro'yxatga qo'shildi.", reply_markup=kb(rows))


@admin_router.callback_query(F.data.startswith("a:bld:"))
async def cb_a_bld(c: CallbackQuery):
    await db.exec("DELETE FROM blacklist WHERE id=?", int(c.data.split(":")[2]))
    await c.answer("O'chirildi")
    await cb_a_bl(c)


@admin_router.callback_query(F.data.startswith("a:gban:"))
async def cb_a_gban(c: CallbackQuery):
    uid = c.data.split(":")[2]
    await ui(c, f"🔨 <code>{uid}</code> ni barcha ittifoq guruhlaridan ban qilishni tasdiqlaysizmi?",
             kb([[B("✅ Ha", f"a:gbany:{uid}"), B("❌ Yo'q", "a:bl")]]))


@admin_router.callback_query(F.data.startswith("a:gbany:"))
async def cb_a_gbany(c: CallbackQuery, bot: Bot):
    ok, bad = await global_ban(bot, int(c.data.split(":")[2]), "Admin qarori")
    await log_action(c.from_user.id, "gban", c.data)
    await ui(c, f"✅ Ban qilindi: {ok} ta chatda. Xato: {bad}", kb([[B("🚫 Qora ro'yxat", "a:bl")]]))


# ---- Bilim bazasi ----
@admin_router.callback_query(F.data == "a:kb")
async def cb_a_kb(c: CallbackQuery):
    rows_db = await db.all("SELECT id, title FROM kb ORDER BY id")
    rows = [[B(f"🗑 {short(r['title'], 34)}", f"a:kbd:{r['id']}")] for r in rows_db]
    rows.append([B("➕ Qo'shish", "a:kba")])
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "🧠 <b>Bilim bazasi</b>\n\nBu yerga yozganlaringizni AI foydalanuvchilarga javob berishda ishlatadi (qoidalar, narxlar, FAQ). "
                "O'chirish uchun yozuvni bosing.", kb(rows))


@admin_router.callback_query(F.data == "a:kba")
async def cb_a_kba(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.kb_title)
    await ui(c, "🧠 Yozuv <b>sarlavhasi</b> (masalan: «Turnir qoidalari»):", kb([[B("⬅️ Bekor", "a:kb")]]))


@admin_router.message(AF.kb_title, F.text)
async def msg_kb_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text.strip()[:100])
    await state.set_state(AF.kb_content)
    await m.answer("📝 Endi <b>mazmunini</b> yozing:")


@admin_router.message(AF.kb_content, F.text)
async def msg_kb_content(m: Message, state: FSMContext):
    d = await state.get_data()
    await db.exec("INSERT INTO kb(title,content) VALUES(?,?)", d["title"], m.text.strip()[:1500])
    await state.clear()
    await m.answer("✅ Bilim bazasiga qo'shildi.", reply_markup=kb([[B("🧠 Bilim bazasi", "a:kb")]]))


@admin_router.callback_query(F.data.startswith("a:kbd:"))
async def cb_a_kbd(c: CallbackQuery):
    await db.exec("DELETE FROM kb WHERE id=?", int(c.data.split(":")[2]))
    await c.answer("O'chirildi")
    await cb_a_kb(c)


# ---- Adminlar (faqat egalar) ----
@admin_router.callback_query(F.data == "a:adm")
async def cb_a_adm(c: CallbackQuery):
    if not is_super(c.from_user.id):
        return await c.answer("Faqat egalar uchun", show_alert=True)
    rows_db = await db.all("SELECT user_id FROM admins")
    rows = [[B(f"🗑 {r['user_id']}", f"a:admd:{r['user_id']}")] for r in rows_db]
    rows.append([B("➕ Admin qo'shish", "a:adma")])
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, "👥 <b>Adminlar</b>\n\nAdminlar arizalarni ko'rib chiqa oladi, e'lon yuborishi va statistikani ko'ra oladi.\n"
                f"Egalar: {', '.join(str(x) for x in sorted(OWNER_IDS))}", kb(rows))


@admin_router.callback_query(F.data == "a:adma")
async def cb_a_adma(c: CallbackQuery, state: FSMContext):
    if not is_super(c.from_user.id):
        return await c.answer("Faqat egalar uchun", show_alert=True)
    await state.set_state(AF.adm_add)
    await ui(c, "➕ Yangi adminning <b>ID</b> raqamini yuboring yoki uning xabarini forward qiling:", kb([[B("⬅️ Bekor", "a:adm")]]))


@admin_router.message(AF.adm_add)
async def msg_adm_add(m: Message, state: FSMContext):
    uid = None
    fo = getattr(m, "forward_origin", None)
    if fo and getattr(fo, "sender_user", None):
        uid = fo.sender_user.id
    elif m.text and re.fullmatch(r"\d{5,15}", m.text.strip()):
        uid = int(m.text.strip())
    if not uid:
        return await m.answer("❗ ID yoki forward kerak.")
    await db.exec("INSERT OR IGNORE INTO admins VALUES(?,?,?)", uid, m.from_user.id, now())
    await load_admins()
    await state.clear()
    await m.answer(f"✅ {uid} admin qilindi.", reply_markup=kb([[B("👥 Adminlar", "a:adm")]]))


@admin_router.callback_query(F.data.startswith("a:admd:"))
async def cb_a_admd(c: CallbackQuery):
    if not is_super(c.from_user.id):
        return await c.answer("Faqat egalar uchun", show_alert=True)
    await db.exec("DELETE FROM admins WHERE user_id=?", int(c.data.split(":")[2]))
    await load_admins()
    await c.answer("O'chirildi")
    await cb_a_adm(c)


# ---- Ulanishlar ----
@admin_router.callback_query(F.data == "a:bind")
async def cb_a_bind(c: CallbackQuery, bot: Bot):
    al, ch = cfg.get("alliance_chat_id"), cfg.get("stats_channel_id")

    async def title(cid):
        try:
            return (await bot.get_chat(int(cid))).title
        except Exception:
            return "⚠️ bot kira olmaydi"

    t = ("🔗 <b>Ulanishlar</b>\n\n"
         f"⚜️ Ittifoq guruhi: {esc(await title(al)) if al else '❌ ulanmagan'}\n"
         f"📺 Statistika kanali: {esc(await title(ch)) if ch else '❌ ulanmagan'}\n\n"
         "<b>Ittifoq guruhini ulash:</b> botni guruhga TO'LIQ admin qiling va guruhda <code>/bind</code> yozing.\n"
         "<b>Kanalni ulash:</b> botni kanalga admin qiling, «Kanalni ulash» ni bosib, kanaldan istalgan xabarni forward qiling.")
    link = f"https://t.me/{BOT_USERNAME}?startgroup=alliance&admin={ADMIN_RIGHTS}"
    rows = [[B("➕ Botni guruhga qo'shish", url=link)], [B("📺 Kanalni ulash", "a:chan")]]
    if ch:
        rows.append([B("❌ Kanalni uzish", "a:chanx")])
    rows.append([B("⬅️ Panel", "a:home")])
    await ui(c, t, kb(rows))


@admin_router.callback_query(F.data == "a:chan")
async def cb_a_chan(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.chan_fwd)
    await ui(c, "📺 Kanaldan istalgan xabarni shu yerga <b>forward</b> qiling:", kb([[B("⬅️ Bekor", "a:bind")]]))


@admin_router.callback_query(F.data == "a:chanx")
async def cb_a_chanx(c: CallbackQuery):
    await cfg.reset("stats_channel_id")
    await c.answer("Uzildi")
    await cb_a_bind(c, c.bot)


@admin_router.message(AF.chan_fwd)
async def msg_chan_fwd(m: Message, state: FSMContext, bot: Bot):
    fo = getattr(m, "forward_origin", None)
    chat = getattr(fo, "chat", None) if fo else None
    if not chat:
        return await m.answer("❗ Kanaldan forward qilingan xabar kerak.")
    try:
        me = await bot.get_chat_member(chat.id, bot.id)
        if me.status != "administrator":
            raise ValueError
    except Exception:
        return await m.answer("❗ Bot bu kanalda admin emas. Avval botni kanalga admin qiling.")
    await cfg.set("stats_channel_id", chat.id)
    await state.clear()
    await m.answer(f"✅ Kanal ulandi: <b>{esc(chat.title)}</b>", reply_markup=kb([[B("🔗 Ulanishlar", "a:bind")]]))


# ---- AI yordamchi (owner) ----
AI_QUICK = ["tahlil", "kutilayotgan arizalar", "7 kunlik reja", "e'lon yoz"]


@admin_router.callback_query(F.data == "a:ai")
async def cb_a_ai_open(c: CallbackQuery, state: FSMContext):
    await state.set_state(AF.ai)
    rows = [[B("📊 Tahlil", "a:aiq:0"), B("📥 Arizalar", "a:aiq:1")], [B("🚀 O'sish rejasi", "a:aiq:2"), B("✍️ E'lon yoz", "a:aiq:3")],
            [B("⬅️ Panel", "a:home")]]
    await ui(c, "🤖 <b>Legion Organizator AI</b> — operatsion yordamchi\n\nOddiy tilda buyruq bering: arizalarni ko'rish/qabul qilish, "
                "mezonlarni o'zgartirish, e'lon, turnir, ban, tahlil va strategiya. "
                "Xavfli amallar sizning tasdig'ingizdan keyin bajariladi.", kb(rows))


@admin_router.callback_query(F.data.startswith("a:aiq:"))
async def cb_a_aiq(c: CallbackQuery, bot: Bot, state: FSMContext):
    await state.set_state(AF.ai)
    q = AI_QUICK[int(c.data.split(":")[2])]
    await c.answer("🤖 O'ylayapman…")
    ans = await ai_agent(bot, c.from_user, q, True)
    await c.message.answer(ans, reply_markup=kb([[B("⬅️ Panel", "a:home")]]))


@admin_router.message(AF.ai, F.text)
async def msg_a_ai(m: Message, bot: Bot):
    await ai_reply(m, bot, True, "a:home")


# ---- AI amallarini tasdiqlash ----
@admin_router.callback_query(F.data.startswith("pa:"))
async def cb_pa(c: CallbackQuery, bot: Bot):
    _, act, token = c.data.split(":")
    row = await db.one("SELECT * FROM pending_actions WHERE token=?", token)
    if not row or row["actor"] != c.from_user.id:
        return await c.answer("Muddati o'tgan yoki sizga tegishli emas", show_alert=True)
    await db.exec("DELETE FROM pending_actions WHERE token=?", token)
    if act == "no":
        return await ui(c, "❌ Amal bekor qilindi.")
    res = await execute_action(bot, c.from_user.id, row["action"], json.loads(row["payload"]))
    await log_action(c.from_user.id, "ai_confirmed", row["action"])
    await ui(c, f"✅ Bajarildi: {esc(res)}")


# ---- Reklamani tasdiqlash ----
@admin_router.callback_query(F.data.startswith("ap:"))
async def cb_ap(c: CallbackQuery, bot: Bot):
    _, act, aid = c.data.split(":")
    ad = await db.one("SELECT * FROM ads WHERE id=?", int(aid))
    if not ad or ad["status"] != "pending":
        return await c.answer("Allaqachon ko'rib chiqilgan", show_alert=True)
    if act == "no":
        await db.exec("UPDATE ads SET status='rejected' WHERE id=?", ad["id"])
        try:
            await bot.send_message(ad["user_id"], "😔 Reklamangiz rad etildi.")
        except Exception:
            pass
        await c.answer("Rad etildi")
        return await c.message.edit_reply_markup(reply_markup=None)
    await db.exec("UPDATE ads SET status='approved' WHERE id=?", ad["id"])
    await c.answer("🚀 Yuborilmoqda…")
    await c.message.edit_reply_markup(reply_markup=None)
    own = [g["chat_id"] for g in await db.all("SELECT chat_id FROM groups WHERE owner_id=?", ad["user_id"])]

    async def job():
        s, f = await broadcast(bot, src=(ad["src_chat"], ad["src_msg"]), exclude=tuple(own))
        await bot.send_message(c.from_user.id, f"✅ Reklama #{ad['id']} {s} ta guruhga yuborildi.")
        try:
            await bot.send_message(ad["user_id"], f"✅ Reklamangiz tasdiqlandi va {s} ta guruhga yuborildi!")
        except Exception:
            pass

    asyncio.create_task(job())


# ════════════════════════════════════════════════════════════════
#  OXIRGI FALLBACK: erkin matn -> AI
# ════════════════════════════════════════════════════════════════
@user_router.message(StateFilter(None), F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def msg_fallback(m: Message, bot: Bot):
    await ai_reply(m, bot, is_admin(m.from_user.id), "m:home")


# ════════════════════════════════════════════════════════════════
#  ISHGA TUSHIRISH
# ════════════════════════════════════════════════════════════════
async def main():
    global BOT_USERNAME
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN kiritilmagan")
    if not OWNER_IDS:
        raise SystemExit("❌ OWNER_IDS kiritilmagan (masalan: 123456789)")
    await cfg.load()
    await load_admins()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    BOT_USERNAME = (await bot.get_me()).username
    log.info("Bot ishga tushdi: @%s | ichki AI faol", BOT_USERNAME)
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(Touch())
    dp.include_router(admin_router)
    dp.include_router(user_router)
    await bot.set_my_commands([
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="panel", description="Boshqaruv paneli (adminlar)"),
        BotCommand(command="help", description="Yordam"),
    ])
    asyncio.create_task(scheduler(bot))
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member", "chat_member", "chat_join_request"])


if __name__ == "__main__":
    asyncio.run(main())
