from kurigram import filters
from kurigram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from lastperson07.clients import stream_client as bot
from lastperson07.utils.token import gen_token, stream_url, download_url
from lastperson07.utils.human_size import human_size
from database import mongo, redis as rdb
import config

EXPIRY_OPTIONS = {
    "exp_1h":    ("1 Hour",    3_600),
    "exp_6h":    ("6 Hours",   21_600),
    "exp_12h":   ("12 Hours",  43_200),
    "exp_24h":   ("24 Hours",  86_400),
    "exp_3d":    ("3 Days",    259_200),
    "exp_7d":    ("7 Days",    604_800),
    "exp_never": ("No Expiry", 0),
}

EXPIRY_KB = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("⏱ 1 Hour",   callback_data="exp_1h"),
        InlineKeyboardButton("⏱ 6 Hours",  callback_data="exp_6h"),
        InlineKeyboardButton("⏱ 12 Hours", callback_data="exp_12h"),
    ],
    [
        InlineKeyboardButton("📅 24 Hours", callback_data="exp_24h"),
        InlineKeyboardButton("📅 3 Days",   callback_data="exp_3d"),
        InlineKeyboardButton("📅 7 Days",   callback_data="exp_7d"),
    ],
    [InlineKeyboardButton("♾ Never Expire", callback_data="exp_never")],
])


# ── Step 2a: user picked Stream ───────────────────────────────────────────────
@bot.on_callback_query(filters.regex("^choose_stream$"))
async def choose_stream(client, query: CallbackQuery):
    await query.answer()
    data = await rdb.get_pending(query.from_user.id)
    if not data:
        await query.message.edit_text("❌ Session expired. Please send the file again.")
        return
    data["link_type"] = "stream"
    await rdb.set_pending(query.from_user.id, data, ttl=600)
    await query.message.edit_text(
        "🎬 **Stream Link**\n\n─────────────────\n⏳ How long should this link stay active?",
        reply_markup=EXPIRY_KB,
    )


# ── Step 2b: user picked Download ────────────────────────────────────────────
@bot.on_callback_query(filters.regex("^choose_download$"))
async def choose_download(client, query: CallbackQuery):
    await query.answer()
    data = await rdb.get_pending(query.from_user.id)
    if not data:
        await query.message.edit_text("❌ Session expired. Please send the file again.")
        return
    data["link_type"] = "download"
    await rdb.set_pending(query.from_user.id, data, ttl=600)
    await query.message.edit_text(
        "⬇️ **Download Link**\n\n─────────────────\n⏳ How long should this link stay active?",
        reply_markup=EXPIRY_KB,
    )


# ── Step 3: user picked expiry → generate link ────────────────────────────────
@bot.on_callback_query(filters.regex("^exp_"))
async def expiry_chosen(client, query: CallbackQuery):
    exp_key = query.data
    if exp_key not in EXPIRY_OPTIONS:
        await query.answer("❌ Invalid option.", show_alert=True)
        return
    await query.answer("⚡ Generating your link...")

    user_id        = query.from_user.id
    label, ttl_sec = EXPIRY_OPTIONS[exp_key]

    data = await rdb.get_pending(user_id)
    if not data:
        await query.message.edit_text("❌ Session expired. Please send the file again.")
        return

    link_type = data.get("link_type", "download")
    token     = gen_token()

    await rdb.set_token(token, {**data, "ttl_label": label, "ttl": ttl_sec}, ttl=ttl_sec)
    await mongo.log_file(user_id, token, link_type, data)
    await rdb.del_pending(user_id)

    if link_type == "stream":
        url       = stream_url(token)
        emoji     = "🎬"
        type_lbl  = "Stream"
    else:
        url       = download_url(token)
        emoji     = "⬇️"
        type_lbl  = "Download"

    expiry_line = "♾ Never expires" if ttl_sec == 0 else f"⏱ Expires in **{label}**"
    size_str    = human_size(data.get("file_size", 0))

    text = (
        f"{emoji} **Your {type_lbl} Link is Ready!**\n\n"
        f"📄 `{data.get('file_name', 'Unknown')}`\n"
        f"📦 {size_str}\n"
        f"{expiry_line}\n\n"
        f"─────────────────\n"
        f"🔗 **Link:**\n`{url}`\n"
        f"─────────────────\n\n"
        "⚠️ _Keep this link private if the file is personal._"
    )

    await query.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Link", url=url)],
            [InlineKeyboardButton("🔄 New File", callback_data="gen_another")],
        ]),
    )


@bot.on_callback_query(filters.regex("^gen_another$"))
async def gen_another(client, query: CallbackQuery):
    await query.answer()
    await query.message.edit_text("📤 Send me a new file to generate a fresh link!")
