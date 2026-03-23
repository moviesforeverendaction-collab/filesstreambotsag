import functools
import time
from kurigram import filters
from kurigram.types import Message
from lastperson07.clients import stream_client as bot
from database import mongo
import config


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(client, message: Message):
        if message.from_user.id not in config.ADMIN_IDS:
            return
        await func(client, message)
    return wrapper


@bot.on_message(filters.command("stats") & filters.private)
@admin_only
async def stats_handler(client, message: Message):
    users     = await mongo.count_users()
    files     = await mongo.count_files()
    streams   = await mongo.count_by_type("stream")
    downloads = await mongo.count_by_type("download")
    await message.reply(
        "📊 **Bot Statistics**\n\n"
        f"👥 Total users:     `{users}`\n"
        f"📁 Total links:     `{files}`\n"
        f"🎬 Stream links:    `{streams}`\n"
        f"⬇️ Download links:  `{downloads}`"
    )


@bot.on_message(filters.command("ban") & filters.private)
@admin_only
async def ban_handler(client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: `/ban <user_id>`")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.reply("❌ Invalid user ID.")
        return
    await mongo.ban_user(uid)
    await message.reply(f"✅ User `{uid}` has been banned.")


@bot.on_message(filters.command("unban") & filters.private)
@admin_only
async def unban_handler(client, message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("Usage: `/unban <user_id>`")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.reply("❌ Invalid user ID.")
        return
    await mongo.unban_user(uid)
    await message.reply(f"✅ User `{uid}` has been unbanned.")


@bot.on_message(filters.command("broadcast") & filters.private)
@admin_only
async def broadcast_handler(client, message: Message):
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("Usage: `/broadcast <message>`")
        return
    text     = parts[1]
    user_ids = await mongo.get_all_user_ids()
    sent = failed = 0
    status = await message.reply(f"📡 Broadcasting to `{len(user_ids)}` users...")
    for uid in user_ids:
        try:
            await client.send_message(uid, text)
            sent += 1
        except Exception:
            failed += 1
    await status.edit_text(
        f"✅ **Broadcast complete**\n\n📨 Sent: `{sent}`\n❌ Failed: `{failed}`"
    )


@bot.on_message(filters.command("ping") & filters.private)
@admin_only
async def ping_handler(client, message: Message):
    t = time.monotonic()
    m = await message.reply("🏓 Pong!")
    ms = (time.monotonic() - t) * 1000
    await m.edit_text(f"🏓 **Pong!**\n\n⚡ Latency: `{ms:.1f} ms`")
