#!/usr/bin/env python3
"""
Shaxsiy yordamchi — Telegram «Chat automation» (Business) boti.

Bot shaxsiy akkauntingizga ulanadi (Settings → Chat automation) va sizga
yozganlarga siz nomingizdan javob beradi. Rejimlar:
  ⭐ Aralash   — siz belgilagan odamlarga faqat avtojavob («Hozir bandman,
                 bo'shab o'zim yozaman»), qolganlar bilan AI suhbatlashadi
                 (standart rejim).
  🤖 AI suhbat — hammaga AI javob beradi.
  ⏰ Avtojavob — hammaga tayyor matn.
AI suhbatda muhim gap chiqsa (taklif, uchrashuv, pul, shoshilinch ish), bot
egasiga o'z chatida «⚠️ Ali: ...» deb bildirishnoma yuboradi.
Avtojavob bir suhbatga AVTO_QAYTA soatda bir marta yuboriladi. Guruh, kanal
va botlarga bot hech qachon yozmaydi — faqat odamlar bilan shaxsiy chatlarda.
Siz o'zingiz biror chatda yozsangiz, bot o'sha chatda TINCH daqiqa jim turadi —
suhbatga aralashmaydi.

Sozlash — botning o'ziga (shaxsiy chatda) yoziladi, faqat ulagan egasi uchun:
    /start              holat va rejim tugmalari
    /matn <matn>        avtojavob matni
    /haqimda <matn>     AI uchun siz haqingizda: ism, kasb, narxlar, manzil...
    /tozala             AI suhbat tarixini o'chirish
    ⭐ Belgilanganlar   «➕ Belgilash» tugmasi bilan kontakt tanlanadi

Rejimlar:
    python3 bot.py                 # doimiy (server bo'lsa): long polling
    python3 bot.py --uzluksiz 50   # GitHub Actions: 50 daqiqa ishlaydi
    python3 bot.py --setup         # buyruqlar va tavsifni o'rnatadi

Muhit o'zgaruvchilari:
    BOT_TOKEN          BotFather bergan token (BotFather'da Business Mode yoqilgan bo'lsin)
    ANTHROPIC_API_KEY  AI suhbat uchun Claude API kaliti (console.anthropic.com)
    STATE_FILE         yordamchi.json manzili (ixtiyoriy)
    MODEL              Claude modeli (standart claude-opus-5-5)
    TINCH              egasi yozgandan keyin necha daqiqa jim turish (standart 30)
    AVTO_QAYTA         avtojavob bir suhbatga necha soatda bir marta (standart 6)
    EGALAR             bot ishlaydigan akkauntlar username'i (standart YULDASHEEVO)
    TEZ                AI tez rejimi: 1 — yoqiq (standart), 0 — o'chiq (arzonroq)
"""

import json
import os
import uuid
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import anthropic
except ImportError:              # avtojavob AI'siz ham ishlaydi
    anthropic = None

TOKEN = os.environ.get("BOT_TOKEN", "").strip()
STORE = os.environ.get("STATE_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "yordamchi.json")
API = "https://api.telegram.org/bot%s/" % TOKEN
MODEL = os.environ.get("MODEL") or "claude-opus-5-5"
TINCH = int(os.environ.get("TINCH") or 30) * 60
AVTO_QAYTA = int(os.environ.get("AVTO_QAYTA") or 6) * 3600
BOT_NOMI = "Yordamchi"
BOTPIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rasmlar", "botpic.png")
# Bot faqat shu akkauntlarga ishlaydi (username, vergul bilan). Boshqa kimdir
# ulasa — javob bermaydi, AI pulingiz sarflanmaydi.
EGALAR = {x.strip().lstrip("@").lower()
          for x in (os.environ.get("EGALAR") or "YULDASHEEVO").split(",") if x.strip()}
TEZ = os.environ.get("TEZ", "1") != "0"   # AI tez rejimi (2 baravar qimmatroq)
KUTISH = 1.5               # ketma-ket yozilgan xabarlarni bitta javob bilan qamrash uchun
TARIX = 30                 # AI uchun har bir suhbatdan nechta oxirgi xabar saqlanadi

STANDART_MATN = "Assalomu alaykum! Hozir bandman, bo'shashim bilan o'zim yozaman"
TAVSIF = ("🤝 Shaxsiy yordamchi — Telegram'da siz band paytingizda "
          "yozganlarga javob beradi.\n\n"
          "⭐ Belgilaganlaringizga — «hozir bandman», qolganlar bilan — 🤖 AI suhbat.\n\n"
          "Ulash: Settings → Chat automation → shu botni tanlang.")
QISQA_TAVSIF = "🤝 Band paytingizda yozganlarga siz nomingizdan javob beradi"
BUYRUQLAR = [
    {"command": "start", "description": "🏠 Holat va rejim"},
    {"command": "matn", "description": "⏰ Avtojavob matni"},
    {"command": "haqimda", "description": "🤖 AI uchun siz haqingizda"},
    {"command": "tozala", "description": "🧹 AI suhbat tarixini o'chirish"},
]
REJIMLAR = {"aralash": "⭐ Belgilanganlarga avtojavob, qolganlarga AI",
            "ai": "🤖 Hammaga AI", "avto": "⏰ Hammaga avtojavob", "off": "⛔ O'chiq"}
BELGILASH = "➕ Belgilash"
ROYXAT = "⭐ Belgilanganlar"
KLAVIATURA = {"keyboard": [[{"text": BELGILASH, "request_users": {
                  "request_id": 1, "user_is_bot": False, "max_quantity": 10,
                  "request_name": True, "request_username": True}},
                            {"text": ROYXAT}]],
              "resize_keyboard": True, "is_persistent": True}

_db_lock = threading.Lock()


# ---------------------------------------------------------------- Telegram API
def call(method, **params):
    data = urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                      for k, v in params.items() if v is not None}).encode()
    try:
        with urlopen(Request(API + method, data=data), timeout=70) as r:
            return json.load(r)
    except HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            body = {"description": str(e)}
        print("telegram xatosi:", method, body.get("description"), file=sys.stderr)
        return {"ok": False, **body}
    except (URLError, OSError) as e:
        print("tarmoq xatosi:", method, e, file=sys.stderr)
        return {"ok": False}


def upload(method, fields, files):
    """multipart/form-data: fields — oddiy qiymatlar, files — {nom: yo'l}."""
    chegara = "----yordamchi" + uuid.uuid4().hex
    qism = []
    for k, v in fields.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        qism.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                     % (chegara, k, v)).encode())
    for k, yol in files.items():
        qism.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                     'Content-Type: image/png\r\n\r\n' % (chegara, k, os.path.basename(yol))).encode())
        with open(yol, "rb") as f:
            qism.append(f.read())
        qism.append(b"\r\n")
    qism.append(("--%s--\r\n" % chegara).encode())
    req = Request(API + method, data=b"".join(qism),
                  headers={"Content-Type": "multipart/form-data; boundary=" + chegara})
    try:
        with urlopen(req, timeout=120) as r:
            return json.load(r)
    except HTTPError as e:
        try:
            body = json.load(e)
        except ValueError:
            body = {"description": str(e)}
        print("telegram xatosi:", method, body.get("description"), file=sys.stderr)
        return {"ok": False, **body}
    except (URLError, OSError) as e:
        print("tarmoq xatosi:", method, e, file=sys.stderr)
        return {"ok": False}


def send(chat_id, text, keyboard=None, business=None):
    return call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML",
                disable_web_page_preview="true", reply_markup=keyboard,
                business_connection_id=business)


def inline(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                for row in rows]}


# ---------------------------------------------------------------- saqlash
def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            db = json.load(f)
    except (OSError, ValueError):
        db = {}
    db.setdefault("ulanish", {})    # business_connection_id → {"egasi", "yoqiq", "javob"}
    db.setdefault("egalar", {})     # egasi id → {"ism", "rejim", "matn", "haqimda"}
    db.setdefault("chatlar", {})    # "ulanish:chat" → {"tarix", "tinch", "avto", "oxirgi"}
    return db


def save(db):
    with _db_lock:
        data = json.dumps(db, ensure_ascii=False)
    os.makedirs(os.path.dirname(os.path.abspath(STORE)), exist_ok=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, STORE)


def ega(db, uid):
    e = db["egalar"].setdefault(str(uid), {})
    if e.get("rejim") not in REJIMLAR:
        e["rejim"] = "aralash"
    e.setdefault("belgilangan", {})  # user id → ism: ularga faqat avtojavob
    e.setdefault("matn", STANDART_MATN)
    e.setdefault("haqimda", "")
    return e


def chat_holati(db, conn_id, chat_id):
    c = db["chatlar"].setdefault("%s:%s" % (conn_id, chat_id), {})
    c.setdefault("tarix", [])       # [{"kim": "u"|"men", "matn"}]
    return c


def xabar_matni(msg):
    """AI uchun xabar matni; rasm/ovoz va hokazo — qisqa belgi bilan."""
    matn = msg.get("text") or msg.get("caption") or ""
    for tur, nom in (("photo", "rasm"), ("video", "video"), ("voice", "ovozli xabar"),
                     ("video_note", "video xabar"), ("audio", "audio"),
                     ("document", "fayl"), ("sticker", "stiker"), ("location", "joylashuv"),
                     ("contact", "kontakt")):
        if msg.get(tur):
            belgi = "[%s]" % nom
            if tur == "sticker" and msg["sticker"].get("emoji"):
                belgi = "[stiker %s]" % msg["sticker"]["emoji"]
            matn = (belgi + " " + matn).strip()
            break
    return matn


# ---------------------------------------------------------------- AI
def ai_tizim(e):
    ism = e.get("ism") or "akkaunt egasi"
    qism = [
        "Siz Telegram'da %s nomidan uning shaxsiy chatlarida javob yozayotgan "
        "yordamchisiz. Suhbatdoshga xuddi messenjerda odam yozgandek qisqa, "
        "samimiy va tabiiy javob bering: 1-3 gap, ortiqcha rasmiyatsiz, "
        "markdown ishlatmang. Suhbatdosh qaysi tilda yozsa, o'sha tilda javob bering." % ism,
        "Faqat quyidagi ma'lumotga va suhbat tarixiga tayaning. Narx, sana, uchrashuv "
        "yoki va'da kabi aniq narsalarni o'ylab topmang — bilmasangiz, %s o'zi "
        "keyinroq javob berishini ayting. Agar sizdan bot yoki sun'iy intellekt "
        "ekanligingizni so'rashsa, rostini ayting." % ism,
        "%s yozishmalarni o'zi o'qimaydi. Shuning uchun suhbatdoshning oxirgi "
        "xabarlarida %s o'zi bilishi yoki qaror qilishi kerak bo'lgan gap bo'lsa — "
        "taklif yoki chaqiruv (uyga, to'yga, biror joyga), uchrashuv, vaqt, pul, "
        "iltimos, shoshilinch yoki yomon xabar — muhim=true qiling va «qisqa» "
        "maydoniga buni bir gapda yozing (masalan: «kechqurun uyiga oshga "
        "chaqiryapti»). Oddiy salom-alik, hazil, gap-so'zda muhim=false, qisqa=\"\"." % (ism, ism),
    ]
    if e.get("haqimda"):
        qism.append("%s haqida ma'lumot:\n%s" % (ism, e["haqimda"]))
    return "\n\n".join(qism)


def ai_xabarlar(tarix):
    """Tarixni Claude formatiga: suhbatdosh — user, egasi/bot — assistant."""
    xabarlar = []
    for t in tarix:
        rol = "user" if t["kim"] == "u" else "assistant"
        if xabarlar and xabarlar[-1]["role"] == rol:
            xabarlar[-1]["content"] += "\n" + t["matn"]
        else:
            xabarlar.append({"role": rol, "content": t["matn"]})
    while xabarlar and xabarlar[0]["role"] != "user":
        xabarlar.pop(0)
    return xabarlar


_ai = None
JAVOB_SXEMA = {
    "type": "object",
    "properties": {
        "javob": {"type": "string", "description": "suhbatdoshga yuboriladigan javob"},
        "muhim": {"type": "boolean", "description": "egasiga bildirishnoma kerakmi"},
        "qisqa": {"type": "string", "description": "muhim gap bir gapda; muhim bo'lmasa bo'sh"},
    },
    "required": ["javob", "muhim", "qisqa"],
    "additionalProperties": False,
}


def ai_javob(e, tarix):
    """(javob, muhim gap yoki None) — yoki xato bo'lsa None."""
    global _ai
    xabarlar = ai_xabarlar(tarix)
    if not xabarlar or xabarlar[-1]["role"] != "user":
        return None
    if _ai is None:
        _ai = anthropic.Anthropic()
    so_rov = dict(
        model=MODEL,
        max_tokens=4000,
        system=ai_tizim(e),
        messages=xabarlar,
        output_config={"effort": "low",        # oddiy suhbat — tez va arzon
                       "format": {"type": "json_schema", "schema": JAVOB_SXEMA}},
        cache_control={"type": "ephemeral"},
        # Xavfsizlik filtri rad etsa, Anthropic tavsiya qilgan model qayta urinadi.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    try:
        if TEZ:
            try:                                  # tez rejim: javob ~2 baravar tezroq yoziladi
                r = _ai.beta.messages.create(**dict(
                    so_rov, speed="fast",
                    betas=so_rov["betas"] + ["fast-mode-2026-02-01"]))
            except (anthropic.RateLimitError, anthropic.BadRequestError) as x:
                print("tez rejim ishlamadi, oddiy rejim:", x.status_code, file=sys.stderr)
                r = _ai.beta.messages.create(**so_rov)
        else:
            r = _ai.beta.messages.create(**so_rov)
    except anthropic.APIStatusError as x:
        print("AI xatosi:", x.status_code, x.message, file=sys.stderr)
        return None
    except anthropic.APIConnectionError as x:
        print("AI tarmoq xatosi:", x, file=sys.stderr)
        return None
    if r.stop_reason == "refusal":
        print("AI rad etdi:", getattr(r.stop_details, "category", None), file=sys.stderr)
        return None
    try:
        d = json.loads("".join(b.text for b in r.content if b.type == "text"))
    except ValueError:
        print("AI javobi JSON emas:", r.stop_reason, file=sys.stderr)
        return None
    javob = (d.get("javob") or "").strip()
    if not javob:
        return None
    return javob, ((d.get("qisqa") or "").strip() or "muhim gap yozdi") if d.get("muhim") else None


# ---------------------------------------------------------------- business
def ulanish(bc, db):
    """Kimdir botni Chat automation orqali uladi, o'zgartirdi yoki uzdi."""
    uid = bc["user"]["id"]
    rights = bc.get("rights") or {}
    chat = bc.get("user_chat_id") or uid
    print("ulanish: @%s yoqiq=%s ruxsatlar=%s" % (bc["user"].get("username"),
                                                  bc.get("is_enabled"), rights))
    if (bc["user"].get("username") or "").lower() not in EGALAR:
        print("begona ulanish rad etildi:", uid, bc["user"].get("username"))
        with _db_lock:
            db["ulanish"].pop(bc["id"], None)
        if bc.get("is_enabled"):
            send(chat, "⛔ Bu shaxsiy bot, u faqat egasining akkauntida ishlaydi.")
        return
    with _db_lock:
        db["ulanish"][bc["id"]] = {"egasi": uid, "chat": bc.get("user_chat_id") or uid,
                                   "yoqiq": bool(bc.get("is_enabled")),
                                   "javob": bool(rights.get("can_reply", bc.get("can_reply")))}
        e = ega(db, uid)
        e["ism"] = bc["user"].get("first_name") or e.get("ism") or ""
    if not bc.get("is_enabled"):
        send(chat, "🔌 Yordamchi akkauntingizdan uzildi. Qayta ulash: "
                   "Settings → Chat automation.")
    elif not db["ulanish"][bc["id"]]["javob"]:
        send(chat, "⚠️ Bot ulandi, lekin <b>xabarlarga javob berish</b> ruxsati yo'q.\n"
                   "Settings → Chat automation → botni oching va ruxsatni yoqing.")
    else:
        holat(chat, uid, db, "✅ Yordamchi akkauntingizga ulandi!\n\n")


def biznes_xabar(msg, db, pool):
    conn_id = msg.get("business_connection_id")
    u = db["ulanish"].get(conn_id)
    frm = msg.get("from") or {}
    print("biznes xabar: chat %s, kimdan %s" % (msg["chat"].get("id"), frm.get("id")))
    if not u or not u["yoqiq"]:
        print("  o'tkazildi: ulanish topilmadi yoki o'chiq")
        return
    if msg.get("sender_business_bot"):            # botning o'zi yuborgani — tarixda bor
        return
    chat_id = msg["chat"]["id"]
    if msg["chat"].get("type", "private") != "private":   # guruh va kanallarga yozmaymiz
        return
    matn = xabar_matni(msg)
    with _db_lock:
        c = chat_holati(db, conn_id, chat_id)
        if frm.get("id") == u["egasi"]:
            # Egasi o'zi yozyapti — bot bu chatda bir muddat aralashmaydi.
            c["tinch"] = time.time() + TINCH
            print("  egasi o'zi yozdi — bu chatda %d daqiqa jim" % (TINCH // 60))
            if matn:
                c["tarix"] = (c["tarix"] + [{"kim": "men", "matn": matn}])[-TARIX:]
            return
        if frm.get("is_bot") or not matn:
            return
        c["tarix"] = (c["tarix"] + [{"kim": "u", "matn": matn}])[-TARIX:]
        c["ism"] = " ".join(x for x in (frm.get("first_name"), frm.get("last_name")) if x)
        c["username"] = frm.get("username") or ""
        c["oxirgi"] = msg["message_id"]
    pool.submit(javob_ber, db, conn_id, chat_id, msg["message_id"])


def yubor(c, conn_id, chat_id, matn):
    r = call("sendMessage", chat_id=chat_id, text=matn, business_connection_id=conn_id)
    if r.get("ok"):
        with _db_lock:
            c["tarix"] = (c["tarix"] + [{"kim": "men", "matn": matn}])[-TARIX:]
        print("javob:", chat_id, matn[:40].replace("\n", " "))


def bildir(u, chat_id, c, muhim, tarix):
    """Egasiga bot chatida: kim, nima muhim gap yozdi."""
    kim = '<a href="tg://user?id=%s">%s</a>' % (chat_id, escape(c.get("ism") or "Kimdir"))
    if c.get("username"):
        kim += " (@%s)" % escape(c["username"])
    oxirgi = [t["matn"] for t in tarix if t["kim"] == "u"][-3:]
    send(u.get("chat") or u["egasi"],
         "⚠️ %s muhim gap yozdi:\n<b>%s</b>\n\n💬 <i>%s</i>"
         % (kim, escape(muhim), escape("\n".join(oxirgi))[:1000]))


def javob_ber(db, conn_id, chat_id, message_id):
    try:
        time.sleep(KUTISH)
        with _db_lock:
            u = db["ulanish"].get(conn_id) or {}
            if not u.get("yoqiq") or not u.get("javob"):
                print("  javob yo'q: javob berish ruxsati o'chiq")
                return
            c = chat_holati(db, conn_id, chat_id)
            e = ega(db, u["egasi"])
            if c.get("oxirgi") != message_id:         # ketidan yana yozdi — o'sha javob beradi
                return
            if e["rejim"] == "off":
                print("  javob yo'q: rejim o'chiq")
                return
            if c.get("tinch", 0) > time.time():
                print("  javob yo'q: egasi yaqinda yozgan, yana %d daqiqa jim"
                      % ((c["tinch"] - time.time()) // 60 + 1))
                return
            ai_bor = anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))
            belgili = str(chat_id) in e["belgilangan"]
            if e["rejim"] == "aralash":
                ai = ai_bor and not belgili
            else:
                ai = ai_bor and e["rejim"] == "ai"
            avto = not ai
            avto_matn = None
            if avto and time.time() - c.get("avto", 0) >= AVTO_QAYTA:
                c["avto"] = time.time()
                avto_matn = e["matn"]
            elif avto:
                print("  javob yo'q: avtojavob bu odamga %d soat ichida yuborilgan"
                      % (AVTO_QAYTA // 3600))
            tarix = list(c["tarix"])
            ega_nusxa = dict(e)
        if avto_matn:
            yubor(c, conn_id, chat_id, avto_matn)
        if not ai:
            return
        call("sendChatAction", chat_id=chat_id, action="typing",
             business_connection_id=conn_id)
        natija = ai_javob(ega_nusxa, tarix)
        if not natija:
            return
        matn, muhim = natija
        with _db_lock:
            if c.get("oxirgi") != message_id or c.get("tinch", 0) > time.time():
                return                                # bu orada egasi yoki suhbatdosh yozdi
        yubor(c, conn_id, chat_id, matn)
        if muhim:
            bildir(u, chat_id, c, muhim, tarix)
    except Exception as x:
        print("xato:", repr(x), file=sys.stderr)


# ---------------------------------------------------------------- egasi bilan
def ulangan(db, uid):
    return any(u["egasi"] == uid and u["yoqiq"] for u in db["ulanish"].values())


def holat(chat, uid, db, bosh=""):
    e = ega(db, uid)
    ai_bor = anthropic is not None and bool(os.environ.get("ANTHROPIC_API_KEY"))
    javob_bor = any(u["egasi"] == uid and u["yoqiq"] and u["javob"]
                    for u in db["ulanish"].values())
    matn = (bosh + "📍 Rejim: <b>%s</b>\n" % REJIMLAR[e["rejim"]] +
            ("✅ Javob berish ruxsati bor\n\n" if javob_bor else
             "❌ <b>Javob berish ruxsati yo'q</b> — Settings → Chat automation → "
             "Manage Messages → Reply to messages ni yoqing\n\n") +
            "⏰ Avtojavob matni:\n<i>%s</i>\n\n" % escape(e["matn"]) +
            "⭐ Belgilanganlar: <b>%d ta</b> — ularga faqat avtojavob boradi\n\n"
            % len(e["belgilangan"]) +
            "🤖 AI uchun siz haqingizda:\n<i>%s</i>\n\n"
            % (escape(e["haqimda"]) or "— hali yozilmagan (/haqimda)") +
            "Siz o'zingiz chatda yozsangiz, bot u yerda %d daqiqa jim turadi.\n\n"
            "/matn &lt;matn&gt; — avtojavob matnini o'zgartirish\n"
            "/haqimda &lt;matn&gt; — AI uchun: ism, kasb, narxlar, manzil, ish vaqti\n"
            "/tozala — AI suhbat tarixini o'chirish" % (TINCH // 60))
    if not ai_bor:
        matn += ("\n\n⚠️ AI kaliti (ANTHROPIC_API_KEY) qo'yilmagan — "
                 "hozircha faqat avtojavob yuboriladi.")
    tugmalar = [[(("✅ " if e["rejim"] == k else "") + v, "rejim:" + k)]
                for k, v in REJIMLAR.items()] + [[(ROYXAT, "royxat")]]
    send(chat, matn, inline(tugmalar))


def royxat(chat, uid, db, bosh=""):
    with _db_lock:
        b = dict(ega(db, uid)["belgilangan"])
    if b:
        qator = ["%d. %s — /ochir_%s" % (i, escape(nom), k)
                 for i, (k, nom) in enumerate(b.items(), 1)]
        matn = "⭐ <b>Belgilanganlar</b> — ularga faqat avtojavob boradi:\n\n" + "\n".join(qator)
    else:
        matn = "⭐ Hali hech kim belgilanmagan."
    send(chat, bosh + matn + "\n\nQo'shish: pastdagi <b>%s</b> tugmasi → kontaktlarni "
                             "tanlang. Olib tashlash: ism yonidagi /ochir_… ni bosing." % BELGILASH,
         KLAVIATURA)


def handle(msg, db):
    chat = msg["chat"]["id"]
    if msg["chat"].get("type") != "private":
        return
    uid = (msg.get("from") or {}).get("id")
    text = (msg.get("text") or "").strip()
    buyruq, _, qolgan = text.partition(" ")
    buyruq = buyruq.split("@")[0].lower()
    if not ulangan(db, uid):
        send(chat, "👋 Men — shaxsiy yordamchi botman.\n\n"
                   "Meni akkauntingizga ulang: <b>Settings → Chat automation</b> → "
                   "shu botni tanlang. Shundan keyin siz band paytingizda "
                   "yozganlarga javob beraman.\n\n"
                   "<i>Eslatma: bu funksiya uchun Telegram Premium kerak bo'lishi mumkin.</i>")
        return
    if msg.get("users_shared"):
        with _db_lock:
            b = ega(db, uid)["belgilangan"]
            for u in msg["users_shared"].get("users", []):
                nom = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x)
                b[str(u["user_id"])] = nom or ("@" + u["username"] if u.get("username")
                                               else str(u["user_id"]))
        royxat(chat, uid, db, "✅ Belgilandi.\n\n")
        return
    if text == ROYXAT:
        royxat(chat, uid, db)
        return
    if buyruq.startswith("/ochir_"):
        with _db_lock:
            nom = ega(db, uid)["belgilangan"].pop(buyruq[7:], None)
        royxat(chat, uid, db, ("❌ %s ro'yxatdan olindi.\n\n" % escape(nom)) if nom else "")
        return
    with _db_lock:
        e = ega(db, uid)
        if buyruq == "/matn" and qolgan.strip():
            e["matn"] = qolgan.strip()[:2000]
            javob = "✅ Avtojavob matni saqlandi."
        elif buyruq == "/haqimda" and qolgan.strip():
            e["haqimda"] = qolgan.strip()[:4000]
            javob = "✅ Saqlandi. AI endi shu ma'lumot asosida javob beradi."
        elif buyruq == "/tozala":
            for kalit in [k for k in db["chatlar"]
                          if db["ulanish"].get(k.split(":")[0], {}).get("egasi") == uid]:
                db["chatlar"][kalit]["tarix"] = []
            javob = "🧹 AI suhbat tarixi o'chirildi."
        elif buyruq in ("/matn", "/haqimda"):
            javob = ("Buyruqdan keyin matnni yozing, masalan:\n<code>%s</code>" %
                     ("/matn Hozir bandman, bo'shab o'zim yozaman"
                      if buyruq == "/matn" else
                      "/haqimda Ismim Ali, dizaynerman. Logotip 300 ming so'm, 3 kunda tayyor."))
        else:
            javob = None
    if javob:
        send(chat, javob)
    else:
        holat(chat, uid, db)


def callback(cq, db):
    uid = cq["from"]["id"]
    data = cq.get("data") or ""
    m = cq.get("message") or {}
    if data.startswith("rejim:") and data[6:] in REJIMLAR and ulangan(db, uid):
        with _db_lock:
            ega(db, uid)["rejim"] = data[6:]
        call("answerCallbackQuery", callback_query_id=cq["id"], text=REJIMLAR[data[6:]])
        if m:
            call("deleteMessage", chat_id=m["chat"]["id"], message_id=m["message_id"])
            holat(m["chat"]["id"], uid, db)
    elif data == "royxat" and ulangan(db, uid):
        call("answerCallbackQuery", callback_query_id=cq["id"])
        royxat(cq["from"]["id"], uid, db)
    else:
        call("answerCallbackQuery", callback_query_id=cq["id"])


def process(updates, db, pool):
    last = None
    for upd in updates:
        last = upd["update_id"]
        try:                                      # bitta xato botni to'xtatmasin
            if upd.get("business_connection"):
                ulanish(upd["business_connection"], db)
            elif upd.get("business_message"):
                biznes_xabar(upd["business_message"], db, pool)
            elif upd.get("message"):
                handle(upd["message"], db)
            elif upd.get("callback_query"):
                callback(upd["callback_query"], db)
            else:
                print("boshqa yangilanish:", [k for k in upd if k != "update_id"])
        except Exception as e:
            print("xato:", repr(e), file=sys.stderr)
    return last


def setup():
    r1 = call("setMyCommands", commands=BUYRUQLAR)
    r2 = call("setMyDescription", description=TAVSIF)
    r3 = call("setMyShortDescription", short_description=QISQA_TAVSIF)
    r4 = call("setMyName", name=BOT_NOMI)
    r5 = {"ok": False}
    if os.path.exists(BOTPIC):
        r5 = upload("setMyProfilePhoto", {"photo": {"type": "static", "photo": "attach://rasm"}},
                    {"rasm": BOTPIC})
    me = call("getMe").get("result", {})
    print("bot: @%s" % me.get("username", "?"),
          "| business:", me.get("can_connect_to_business"))
    if not me.get("can_connect_to_business"):
        print("ogohlantirish: BotFather → /mybots → bot → Bot Settings → "
              "Business Mode ni yoqing.", file=sys.stderr)
    print("buyruqlar:", r1.get("ok"), "| tavsif:", r2.get("ok"), r3.get("ok"),
          "| nom:", r4.get("ok"), "| rasm:", r5.get("ok"), r5.get("description") or "")
    return all(x.get("ok") for x in (r1, r2, r3))


def main(argv):
    if not TOKEN:
        sys.exit("BOT_TOKEN o'zgaruvchisini kiriting.")
    if anthropic is None:
        print("ogohlantirish: anthropic o'rnatilmagan — faqat avtojavob ishlaydi "
              "(pip install anthropic).", file=sys.stderr)
    db = load()

    if "--setup" in argv:
        sys.exit(0 if setup() else 1)

    tugash = None
    if "--uzluksiz" in argv:
        i = argv.index("--uzluksiz")
        daqiqa = int(argv[i + 1]) if len(argv) > i + 1 and argv[i + 1].isdigit() else 50
        tugash = time.time() + daqiqa * 60

    if not db.get("sozlandi_v2"):                 # bir marta: nom, rasm, buyruqlar, tavsif
        db["sozlandi_v2"] = setup()
    print("Yordamchi bot ishga tushdi")
    pool = ThreadPoolExecutor(max_workers=8)
    offset, soni, keyingi_saqlash = None, 0, 0
    try:
        while True:
            timeout = 50
            if tugash is not None:
                qoldi = int(tugash - time.time())
                if qoldi <= 0:
                    break
                timeout = max(1, min(50, qoldi))
            r = call("getUpdates", offset=offset, timeout=timeout,
                     allowed_updates=["message", "callback_query",
                                      "business_connection", "business_message"])
            natija = r.get("result", [])
            last = process(natija, db, pool)
            if last is not None:
                offset = last + 1
                soni += len(natija)
            elif not r.get("ok"):
                time.sleep(5)
            if time.time() >= keyingi_saqlash:
                save(db)
                keyingi_saqlash = time.time() + 60
    finally:
        pool.shutdown(wait=True)                  # boshlangan javoblar tugasin
        if offset is not None:
            call("getUpdates", offset=offset, timeout=0)   # «shulargacha ko'rdim»
        save(db)
        print("qayta ishlandi: %d ta" % soni)


if __name__ == "__main__":
    main(sys.argv[1:])
