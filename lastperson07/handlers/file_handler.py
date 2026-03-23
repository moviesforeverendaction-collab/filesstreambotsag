from pyrogram import filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from lastperson07.clients import stream_client as bot
from lastperson07.utils.file_info import extract_file_info, is_streamable
from lastperson07.utils.force_sub import check_force_sub
from lastperson07.utils.human_size import human_size
from database import mongo, redis as rdb
import config

_media = (
    filters.video | filters.document | filters.audio
    | filters.voice | filters.video_note | filters.animation
)


@bot.on_message(_media & filters.private)
async def file_received(client, message: Message):
    user = message.from_user

    if await mongo.is_banned(user.id):
        await message.reply("🚫 You are banned from using this bot.")
        return

    if not await check_force_sub(client, message):
        return

    if not await rdb.check_rate_limit(user.id):
        ttl = await rdb.rate_limit_ttl(user.id)
        await message.reply(
            f"⚠️ **Slow down!**\n\nYou're generating links too fast.\n"
            f"Please wait **{ttl}s** before trying again."
        )
        return

    file_data = extract_file_info(message)
    if not file_data:
        await message.reply("❌ Could not read this file. Please try a different one.")
        return

    # ── Forward to private storage channel ────────────────────────────────────
    status = await message.reply("⏳ Storing file, please wait...")

    try:
        result = await client.forward_messages(
            chat_id=config.STORAGE_CHANNEL,
            from_chat_id=message.chat.id,
            message_ids=message.id,
        )
        # forward_messages always returns a list in Pyrogram
        if isinstance(result, list):
            if not result:
                raise ValueError("forward_messages returned an empty list")
            stored_msg = result[0]
        else:
            # Defensive: handle if a future Pyrogram version returns a single message
            stored_msg = result
    except Exception as e:
        await status.edit_text(f"❌ Failed to store file.\n`{e}`")
        return

    # Overwrite file_id with the stored copy — file_ids from storage channels never expire
    stored_media = (
        stored_msg.video or stored_msg.document or stored_msg.audio
        or stored_msg.voice or stored_msg.video_note or stored_msg.animation
    )
    if stored_media:
        file_data["file_id"]        = stored_media.file_id
        file_data["file_unique_id"] = stored_media.file_unique_id
        # Prefer stored media's file_size if original was missing
        if not file_data.get("file_size"):
            file_data["file_size"] = getattr(stored_media, "file_size", 0) or 0
    else:
        # Storage forward succeeded but media extraction failed — abort
        await status.edit_text("❌ Could not read the stored file. Please try again.")
        return

    file_data["storage_chat_id"] = config.STORAGE_CHANNEL
    file_data["storage_msg_id"]  = stored_msg.id

    # Validate file_size before proceeding
    if not file_data.get("file_size"):
        await status.edit_text(
            "⚠️ File size is unknown. Streaming and download links require a known size.\n"
            "Please try re-sending the file."
        )
        return

    # ── Cache pending state (10 min) ──────────────────────────────────────────
    await rdb.set_pending(user.id, file_data, ttl=600)
    await mongo.upsert_user(user.id, user.username, user.full_name)

    # ── Ask: Stream or Download? ──────────────────────────────────────────────
    streamable = is_streamable(file_data["mime_type"])
    size_str   = human_size(file_data["file_size"])

    text = (
        f"✅ **File stored!**\n\n"
        f"📄 **{file_data['file_name']}**\n"
        f"📦 Size: `{size_str}`\n"
        f"🗂 Type: `{file_data['mime_type']}`\n\n"
        "─────────────────\n"
        "What type of link do you want?"
    )

    row = []
    if streamable:
        row.append(InlineKeyboardButton("🎬 Stream Link", callback_data="choose_stream"))
    row.append(InlineKeyboardButton("⬇️ Download Link", callback_data="choose_download"))

    await status.edit_text(text, reply_markup=InlineKeyboardMarkup([row]))
