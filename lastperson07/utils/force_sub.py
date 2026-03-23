from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
import config


async def check_force_sub(client, message: Message) -> bool:
    """
    Returns True if the user is subscribed or force-sub is off.
    Returns False and sends a join prompt if the user is not subscribed.
    """
    if not config.FORCE_SUB_ENABLED or not config.FORCE_SUB_CHANNEL:
        return True

    try:
        member = await client.get_chat_member(config.FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            raise ValueError("not subscribed")
        return True
    except Exception:
        channel = config.FORCE_SUB_CHANNEL.lstrip("@")
        await message.reply(
            "**⚠️ Access Restricted**\n\n"
            "You must join our channel before using this bot.\n"
            "Join below, then send your file again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel}")
            ]]),
        )
        return False
