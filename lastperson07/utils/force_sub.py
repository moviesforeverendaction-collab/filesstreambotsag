from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant, ChatAdminRequired, ChannelPrivate, PeerIdInvalid
import config


async def check_force_sub(client, message: Message) -> bool:
    """
    Returns True if the user is subscribed or force-sub is disabled.
    Returns False and sends a join prompt if the user is not subscribed.

    Previously this caught ALL exceptions and treated them as "not subscribed",
    which meant bot misconfiguration errors (e.g. ChatAdminRequired, invalid
    channel ID) would silently block every user with a join prompt. Now we:
      - Re-raise configuration errors so they appear in logs.
      - Only intercept genuine "not a member" errors (UserNotParticipant,
        LEFT/BANNED status) to show the join prompt.
    """
    if not config.FORCE_SUB_ENABLED or not config.FORCE_SUB_CHANNEL:
        return True

    channel = config.FORCE_SUB_CHANNEL.lstrip("@")

    try:
        member = await client.get_chat_member(config.FORCE_SUB_CHANNEL, message.from_user.id)
        if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
            # User has left or was banned from the channel
            raise UserNotParticipant()
        return True

    except UserNotParticipant:
        # User is genuinely not in the channel — show join prompt
        await message.reply(
            "**⚠️ Access Restricted**\n\n"
            "You must join our channel before using this bot.\n"
            "Join below, then send your file again.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel}")
            ]]),
        )
        return False

    except (ChatAdminRequired, ChannelPrivate, PeerIdInvalid) as e:
        # Misconfiguration — bot is not admin, channel is private/invalid.
        # Log the error clearly and allow the user through (fail-open) so
        # legitimate users aren't blocked due to an admin config mistake.
        print(
            f"⚠️ FORCE_SUB misconfiguration for channel '{config.FORCE_SUB_CHANNEL}': "
            f"{type(e).__name__}: {e}. Fix your FORCE_SUB_CHANNEL setting or bot permissions."
        )
        return True

    except Exception as e:
        # Unexpected error — log and fail-open rather than blocking all users.
        print(f"⚠️ check_force_sub unexpected error: {type(e).__name__}: {e}")
        return True
