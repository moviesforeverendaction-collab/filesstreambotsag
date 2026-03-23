from pyrogram import filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from lastperson07.clients import stream_client as bot
from database import mongo
import config

BOT_NAME    = config.BOT_USERNAME
SUPPORT_URL = f"https://t.me/{config.FORCE_SUB_CHANNEL.lstrip('@')}" if config.FORCE_SUB_CHANNEL else "https://t.me/"


def _start_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Support", url=SUPPORT_URL),
            InlineKeyboardButton("ℹ️ About",   callback_data="cb_about"),
        ],
        [InlineKeyboardButton("👨‍💻 Developer", callback_data="cb_developer")],
    ])


def _start_text(first_name: str) -> str:
    return (
        f"👋 **Hello, {first_name}!**\n\n"
        "I convert any Telegram file into a **stream link** or **download link** instantly.\n\n"
        "📤 Just send me any **video, audio, or document** to get started.\n\n"
        "━━━━━━━━━━━━━━━━\n"
        "🎬 Stream — watch directly in your browser\n"
        "⬇️ Download — get a direct download link\n"
        "━━━━━━━━━━━━━━━━"
    )


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    user = message.from_user
    await mongo.upsert_user(user.id, user.username, user.full_name)
    await message.reply(_start_text(user.first_name), reply_markup=_start_keyboard())


@bot.on_callback_query(filters.regex("^cb_about$"))
async def about_callback(client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text(
        "**ℹ️ About**\n\n"
        "This bot converts Telegram files into stream and download links.\n\n"
        "**How it works:**\n"
        "1. Send any file\n"
        "2. Choose 🎬 Stream or ⬇️ Download\n"
        "3. Choose link expiry time\n"
        "4. Get your link instantly\n\n"
        f"**Default TTL:** {config.LINK_TTL // 3600}h  |  "
        f"**Rate limit:** {config.RATE_LIMIT_MAX}/min",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="cb_back")]]),
    )


@bot.on_callback_query(filters.regex("^cb_developer$"))
async def developer_callback(client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text(
        "**👨‍💻 Developer**\n\n"
        "Built with Kurigram + FastAPI.\n"
        "Dual MTProto clients — one for streaming, one for downloads.\n\n"
        "For custom bots or support, reach out below.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Contact", url=SUPPORT_URL)],
            [InlineKeyboardButton("🔙 Back", callback_data="cb_back")],
        ]),
    )


@bot.on_callback_query(filters.regex("^cb_back$"))
async def back_to_start(client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text(
        _start_text(query.from_user.first_name),
        reply_markup=_start_keyboard(),
    )
