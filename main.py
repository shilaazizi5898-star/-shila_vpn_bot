import os
import asyncio
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7915327070"))
DB_PATH = os.getenv("DB_PATH", "/data/shilan_vpn.sqlite3")

PRICES = {
    10: 55000,
    20: 105000,
    30: 125000,
    50: 175000,
    75: 265000,
    100: 385000,
    200: 690000
}

DURATIONS = {
    10: 30,
    20: 30,
    30: 30,
    50: 60,
    75: 60,
    100: 90,
    200: 90
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gb INTEGER,
            link TEXT,
            used INTEGER DEFAULT 0
        )
        """)

        cursor = await db.execute("PRAGMA table_info(stock)")
        columns = [row[1] for row in await cursor.fetchall()]

        if "days" not in columns:
            await db.execute(
                "ALTER TABLE stock ADD COLUMN days INTEGER DEFAULT 30"
            )

        await db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            gb INTEGER,
            price INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        await db.commit()


async def get_card():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT value FROM settings WHERE key='card'"
        )
        row = await cursor.fetchone()
        return row[0] if row else None


def shop_keyboard():
    buttons = []

    for gb, price in PRICES.items():
        days = DURATIONS[gb]

        buttons.append([
            InlineKeyboardButton(
                text=f"{gb} گیگ - {price:,} تومان - {days} روز",
                callback_data=f"buy_{gb}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_keyboard(order_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ تأیید پرداخت",
                callback_data=f"approve_{order_id}"
            ),
            InlineKeyboardButton(
                text="❌ رد پرداخت",
                callback_data=f"reject_{order_id}"
            )
        ]
    ])


def is_admin(user_id):
    return user_id == ADMIN_ID


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "سلام 🌷\n"
        "به فروشگاه SHILAN VPN خوش آمدی.\n\n"
        "برای مشاهده بسته‌ها دکمه زیر را بزن.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🛍 مشاهده بسته‌ها",
                callback_data="shop"
            )]
        ])
    )


@dp.callback_query(F.data == "shop")
async def show_shop(call: CallbackQuery):
    await call.message.answer(
        "📦 بسته موردنظرت رو انتخاب کن:",
        reply_markup=shop_keyboard()
    )
    await call.answer()


@dp.callback_query(F.data.startswith("buy_"))
async def buy_package(call: CallbackQuery):
    gb = int(call.data.split("_")[1])
    price = PRICES[gb]
    days = DURATIONS[gb]

    card = await get_card()

    if not card:
        await call.answer(
            "اطلاعات کارت هنوز ثبت نشده است.",
            show_alert=True
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO orders
            (user_id, username, gb, price, status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            call.from_user.id,
            call.from_user.username or "",
            gb,
            price,
            "awaiting_payment"
        ))

        order_id = cursor.lastrowid
        await db.commit()

    await call.message.answer(
        f"🛍 سفارش شماره {order_id}\n\n"
        f"حجم: {gb} گیگابایت\n"
        f"اعتبار: {days} روز\n"
        f"مبلغ: {price:,} تومان\n\n"
        f"💳 اطلاعات کارت:\n{card}\n\n"
        "پس از پرداخت، عکس رسید بانکی را همین‌جا ارسال کن."
    )

    await call.answer()


@dp.message(Command("setcard"))
async def set_card(message: Message):
    if not is_admin(message.from_user.id):
        return

    value = message.text.replace("/setcard", "", 1).strip()

    if not value:
        await message.answer(
            "فرمت:\n/setcard شماره کارت | نام صاحب کارت"
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO settings (key, value)
            VALUES ('card', ?)
        """, (value,))
        await db.commit()

    await message.answer("✅ اطلاعات کارت ذخیره شد.")


@dp.message(Command("addstock"))
async def add_stock(message: Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=3)

    if len(parts) != 4:
        await message.answer(
            "فرمت:\n/addstock 50 60 vless://LINK"
        )
        return

    try:
        gb = int(parts[1])
        days = int(parts[2])
        link = parts[3].strip()

        if gb not in PRICES or days != DURATIONS[gb]:
            await message.answer(
                "حجم یا مدت اعتبار اشتباه است."
            )
            return

        if not link.startswith("vless://"):
            await message.answer(
                "لینک باید با vless:// شروع شود."
            )
            return

    except ValueError:
        await message.answer("اطلاعات واردشده معتبر نیست.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO stock (gb, link, days)
            VALUES (?, ?, ?)
        """, (gb, link, days))
        await db.commit()

    await message.answer(
        f"✅ کانفیگ {gb} گیگ با اعتبار {days} روز اضافه شد."
    )


@dp.message(Command("stock"))
async def show_stock(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT gb, COUNT(*)
            FROM stock
            WHERE used=0
            GROUP BY gb
        """)
        rows = await cursor.fetchall()

    result = "📦 موجودی کانفیگ‌ها:\n\n"

    for gb in PRICES:
        count = next(
            (r[1] for r in rows if r[0] == gb), 0
        )
        result += f"{gb} گیگ: {count} عدد\n"

    await message.answer(result)


@dp.message(Command("pending"))
async def pending_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, user_id, gb, price
            FROM orders
            WHERE status='review'
            ORDER BY id DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        await message.answer(
            "سفارشی در انتظار بررسی وجود ندارد."
        )
        return

    for order in rows:
        await message.answer(
            f"سفارش {order[0]}\n"
            f"کاربر: {order[1]}\n"
            f"حجم: {order[2]} گیگ\n"
            f"مبلغ: {order[3]:,} تومان"
        )


@dp.message(F.photo)
async def receive_receipt(message: Message):
    if is_admin(message.from_user.id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT id, gb, price
            FROM orders
            WHERE user_id=? AND status='awaiting_payment'
            ORDER BY id DESC LIMIT 1
        """, (message.from_user.id,))

        order = await cursor.fetchone()

        if not order:
            await message.answer(
                "سفارش پرداخت‌نشده‌ای برایت پیدا نشد."
            )
            return

        await db.execute("""
            UPDATE orders SET status='review'
            WHERE id=?
        """, (order[0],))

        await db.commit()

    caption = (
        f"🧾 رسید پرداخت جدید\n\n"
        f"شماره سفارش: {order[0]}\n"
        f"کاربر: {message.from_user.id}\n"
        f"حجم: {order[1]} گیگ\n"
        f"مبلغ: {order[2]:,} تومان"
    )

    await bot.send_photo(
        ADMIN_ID,
        message.photo[-1].file_id,
        caption=caption,
        reply_markup=admin_keyboard(order[0])
    )

    await message.answer(
        "✅ رسید دریافت شد.\n"
        "پس از بررسی پرداخت توسط مدیر، کانفیگ ارسال می‌شود."
    )


@dp.callback_query(F.data.startswith("approve_"))
async def approve_order(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی ندارید.", show_alert=True)
        return

    order_id = int(call.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id, gb, status
            FROM orders WHERE id=?
        """, (order_id,))

        order = await cursor.fetchone()

        if not order or order[2] != "review":
            await call.answer(
                "این سفارش قابل تأیید نیست.",
                show_alert=True
            )
            return

        days = DURATIONS[order[1]]

        cursor = await db.execute("""
            SELECT id, link FROM stock
            WHERE gb=? AND days=? AND used=0
            ORDER BY id LIMIT 1
        """, (order[1], days))

        item = await cursor.fetchone()

        if not item:
            await call.answer(
                "برای این بسته کانفیگ موجود نیست.",
                show_alert=True
            )
            return

        await db.execute(
            "UPDATE stock SET used=1 WHERE id=?",
            (item[0],)
        )

        await db.execute("""
            UPDATE orders SET status='approved'
            WHERE id=?
        """, (order_id,))

        await db.commit()

    await bot.send_message(
        order[0],
        f"🎉 پرداختت تأیید شد!\n\n"
        f"کانفیگ {order[1]} گیگابایتی:\n\n"
        f"<code>{item[1]}</code>\n\n"
        f"اعتبار بسته: {days} روز",
        parse_mode="HTML"
    )

    await call.message.edit_reply_markup(
        reply_markup=None
    )

    await call.message.answer(
        "✅ سفارش تأیید و کانفیگ ارسال شد."
    )

    await call.answer("تأیید شد.")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("دسترسی ندارید.", show_alert=True)
        return

    order_id = int(call.data.split("_")[1])

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT user_id FROM orders
            WHERE id=? AND status='review'
        """, (order_id,))

        order = await cursor.fetchone()

        if not order:
            await call.answer(
                "سفارش پیدا نشد.",
                show_alert=True
            )
            return

        await db.execute("""
            UPDATE orders SET status='rejected'
            WHERE id=?
        """, (order_id,))

        await db.commit()

    await bot.send_message(
        order[0],
        "❌ رسید پرداخت تأیید نشد. لطفاً با مدیر تماس بگیر."
    )

    await call.message.edit_reply_markup(
        reply_markup=None
    )

    await call.answer("رد شد.")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")

    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("SHILAN VPN bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
