import asyncio
import time
from pyrogram import filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated, PeerIdInvalid
from lastperson07.clients import stream_client as bot
from database import mongo
import config


# ── Admin guard ───────────────────────────────────────────────────────────────
# NOTE: Do NOT use a decorator for admin checks with Pyrogram handlers.
# Decorators that wrap async handlers interfere with Pyrogram's internal
# introspection of the handler signature, causing silent failures.
# Instead, check admin status as the first line of each handler.

def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


@bot.on_message(filters.command("stats") & filters.private)
async def stats_handler(client, message: Message):
    if not _is_admin(message.from_user.id):
        return
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
async def ban_handler(client, message: Message):
    if not _is_admin(message.from_user.id):
        return
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
async def unban_handler(client, message: Message):
    if not _is_admin(message.from_user.id):
        return
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
async def broadcast_handler(client, message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.reply("Usage: `/broadcast <message>`")
        return

    text     = parts[1]
    user_ids = await mongo.get_all_user_ids()
    sent = failed = blocked = 0
    status = await message.reply(f"📡 Broadcasting to `{len(user_ids)}` users...")

    for uid in user_ids:
        try:
            await client.send_message(uid, text)
            sent += 1
            # Respect Telegram rate limits: ~30 messages/sec max for bots.
            # A small delay prevents FloodWait bans during large broadcasts.
            await asyncio.sleep(0.05)
        except FloodWait as e:
            # Telegram told us to slow down — honor the wait time exactly.
            await asyncio.sleep(e.value + 1)
            try:
                await client.send_message(uid, text)
                sent += 1
            except Exception:
                failed += 1
        except (UserIsBlocked, InputUserDeactivated, PeerIdInvalid):
            # User blocked the bot or deactivated their account — skip silently.
            blocked += 1
        except Exception:
            failed += 1

    await status.edit_text(
        f"✅ **Broadcast complete**\n\n"
        f"📨 Sent:    `{sent}`\n"
        f"🚫 Blocked: `{blocked}`\n"
        f"❌ Failed:  `{failed}`"
    )


@bot.on_message(filters.command("ping") & filters.private)
async def ping_handler(client, message: Message):
    if not _is_admin(message.from_user.id):
        return
    t = time.monotonic()
    m = await message.reply("🏓 Pong!")
    ms = (time.monotonic() - t) * 1000
    await m.edit_text(f"🏓 **Pong!**\n\n⚡ Latency: `{ms:.1f} ms`")
