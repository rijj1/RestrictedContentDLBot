# Copyright (C) @Rij1
# Channel: https://t.me/rijj_1

import os
import shutil
import psutil
import asyncio
from time import time

from pyleaves import Leaves
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, BadRequest
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from helpers.utils import (
    processMediaGroup,
    progressArgs,
    send_media
)

from helpers.files import (
    get_download_path,
    fileSizeLimit,
    get_readable_file_size,
    get_readable_time,
    cleanup_download
)

from helpers.msg import (
    getChatMsgID,
    get_file_name,
    get_parsed_msg
)

from config import PyroConf
from logger import LOGGER

# Adding Allowed users only
from functools import wraps
from config import PyroConf

ALLOWED_USERS_FILE = "allowed_users.txt"

def load_allowed_users():
    if not os.path.exists(ALLOWED_USERS_FILE):
        return set()
    with open(ALLOWED_USERS_FILE, "r") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_allowed_users(users):
    with open(ALLOWED_USERS_FILE, "w") as f:
        for uid in users:
            f.write(f"{uid}\n")

ALLOWED_USERS = load_allowed_users()

def allowed_user_only(func):
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        user_id = message.from_user.id if message.from_user else None
        if user_id != PyroConf.OWNER_ID and user_id not in ALLOWED_USERS:
            await message.reply("❌ You are not allowed to use this bot.")
            return
        return await func(client, message, *args, **kwargs)
    return wrapper


# Initialize the bot client
bot = Client(
    "media_bot",
    api_id=PyroConf.API_ID,
    api_hash=PyroConf.API_HASH,
    bot_token=PyroConf.BOT_TOKEN,
    workers=1000,
    parse_mode=ParseMode.MARKDOWN,
)

# Client for user session
user = Client("user_session", workers=1000, session_string=PyroConf.SESSION_STRING)

RUNNING_TASKS = set()

def track_task(coro):
    task = asyncio.create_task(coro)
    RUNNING_TASKS.add(task)
    def _remove(_):
        RUNNING_TASKS.discard(task)
    task.add_done_callback(_remove)
    return task

@bot.on_message(filters.command("allow") & filters.private)
@allowed_user_only
async def allow_user(_, message: Message):
    if message.from_user.id != PyroConf.OWNER_ID:
        await message.reply("Only the owner can allow users.")
        return
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply("Usage: /allow <user_id>")
        return
    user_id = int(message.command[1])
    if user_id == PyroConf.OWNER_ID:
        await message.reply("Owner is always allowed.")
        return
    ALLOWED_USERS.add(user_id)
    save_allowed_users(ALLOWED_USERS)
    await message.reply(f"✅ Allowed user {user_id}.")

@bot.on_message(filters.command("disallow") & filters.private)
@allowed_user_only
async def disallow_user(_, message: Message):
    if message.from_user.id != PyroConf.OWNER_ID:
        await message.reply("Only the owner can disallow users.")
        return
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply("Usage: /disallow <user_id>")
        return
    user_id = int(message.command[1])
    if user_id == PyroConf.OWNER_ID:
        await message.reply("You cannot disallow the owner.")
        return
    ALLOWED_USERS.discard(user_id)
    save_allowed_users(ALLOWED_USERS)
    await message.reply(f"🚫 Disallowed user {user_id}.")

@bot.on_message(filters.command("allowed") & filters.private)
@allowed_user_only
async def list_allowed_users(client, message: Message):
    if message.from_user.id != PyroConf.OWNER_ID:
        await message.reply("Only the owner can view allowed users.")
        return
    if not ALLOWED_USERS:
        await message.reply("No allowed users.")
        return

    user_lines = []
    for uid in sorted(ALLOWED_USERS):
        try:
            user = await client.get_users(uid)
            name = f"@{user.username}" if user.username else user.first_name
        except Exception:
            name = "Unknown"
        user_lines.append(f"`{uid}` - {name}")

    await message.reply("**Allowed Users:**\n" + "\n".join(user_lines))

@bot.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    welcome_text = (
        "👋 **Welcome to Media Downloader Bot!**\n\n"
        "I can grab photos, videos, audio, and documents from any Telegram post.\n"
        "Just send me a link (paste it directly or use `/dl <link>`),\n"
        "or reply to a message with `/dl`.\n\n"
        "ℹ️ Use `/help` to view all commands and examples.\n"
        "Ready? Send me a Telegram post link!\n"
        "NOTE: Only Allowed Users can use this Bot."
    )

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Contact Developer", url="https://t.me/rijj_1")]]
    )
    await message.reply(welcome_text, reply_markup=markup, disable_web_page_preview=True)


@bot.on_message(filters.command("help") & filters.private)
async def help_command(_, message: Message):
    help_text = (
        "💡 **Media Downloader Bot Help**\n\n"
        "➤ **Download Media**\n"
        "   – Send `/dl <post_URL>` **or** just paste a Telegram post link to fetch photos, videos, audio, or documents.\n\n"
        "➤ **Batch Download**\n"
        "   – Send `/bdl start_link end_link` to grab a series of posts in one go.\n"
        "     💡 Example: `/bdl https://t.me/mychannel/100 https://t.me/mychannel/120`\n"
        "**It will download all posts from ID 100 to 120.**\n\n"
        "➤ **Requirements**\n"
        "   – Make sure the user client is part of the chat.\n\n"
        "➤ **If the bot hangs**\n"
        "   – Send `/killall` to cancel any pending downloads.\n\n"
        "➤ **Logs**\n"
        "   – Send `/logs` to download the bot’s logs file.\n\n"
        "➤ **Stats**\n"
        "   – Send `/stats` to view current status:\n\n"
        "**Example**:\n"
        "  • `/dl https://t.me/channel_id/547`\n"
        "  • `https://t.me/channel_id/547`"
    )
    
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Contact Developer", url="https://t.me/rijj_1")]]
    )
    await message.reply(help_text, reply_markup=markup, disable_web_page_preview=True)


async def handle_download(bot: Client, message: Message, post_url: str):
    # Cut off URL at '?' if present
    if "?" in post_url:
        post_url = post_url.split("?", 1)[0]

    try:
        chat_id, message_id = getChatMsgID(post_url)
        chat_message = await user.get_messages(chat_id=chat_id, message_ids=message_id)

        LOGGER(__name__).info(f"Downloading media from URL: {post_url}")

        if chat_message.document or chat_message.video or chat_message.audio:
            file_size = (
                chat_message.document.file_size
                if chat_message.document
                else chat_message.video.file_size
                if chat_message.video
                else chat_message.audio.file_size
            )

            if not await fileSizeLimit(
                file_size, message, "download", user.me.is_premium
            ):
                return

        parsed_caption = await get_parsed_msg(
            chat_message.caption or "", chat_message.caption_entities
        )
        parsed_text = await get_parsed_msg(
            chat_message.text or "", chat_message.entities
        )

        if chat_message.media_group_id:
            if not await processMediaGroup(chat_message, bot, message):
                await message.reply(
                    "**Could not extract any valid media from the media group.**"
                )
            return

        elif chat_message.media:
            start_time = time()
            progress_message = await message.reply("**📥 Downloading Progress...**")

            filename = get_file_name(message_id, chat_message)
            download_path = get_download_path(message.id, filename)

            media_path = await chat_message.download(
                file_name=download_path,
                progress=Leaves.progress_for_pyrogram,
                progress_args=progressArgs(
                    "📥 Downloading Progress", progress_message, start_time
                ),
            )

            LOGGER(__name__).info(f"Downloaded media: {media_path}")

            media_type = (
                "photo"
                if chat_message.photo
                else "video"
                if chat_message.video
                else "audio"
                if chat_message.audio
                else "document"
            )
            await send_media(
                bot,
                message,
                media_path,
                media_type,
                parsed_caption,
                progress_message,
                start_time,
            )

            cleanup_download(media_path)
            await progress_message.delete()

        elif chat_message.text or chat_message.caption:
            await message.reply(parsed_text or parsed_caption)
        else:
            await message.reply("**No media or text found in the post URL.**")

    except (PeerIdInvalid, BadRequest, KeyError):
        await message.reply("**Make sure the user client is part of the chat.**")
    except Exception as e:
        error_message = f"**❌ {str(e)}**"
        await message.reply(error_message)
        LOGGER(__name__).error(e)


@bot.on_message(filters.command("dl") & filters.private)
@allowed_user_only
async def download_media(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("**Provide a post URL after the /dl command.**")
        return

    post_url = message.command[1]
    await track_task(handle_download(bot, message, post_url))


@bot.on_message(filters.command("bdl") & filters.private)
@allowed_user_only
async def download_range(bot: Client, message: Message):
    args = message.text.split()

    if len(args) != 3 or not all(arg.startswith("https://t.me/") for arg in args[1:]):
        await message.reply(
            "🚀 **Batch Download Process**\n"
            "`/bdl start_link end_link`\n\n"
            "💡 **Example:**\n"
            "`/bdl https://t.me/mychannel/100 https://t.me/mychannel/120`"
        )
        return

    try:
        start_chat, start_id = getChatMsgID(args[1])
        end_chat,   end_id   = getChatMsgID(args[2])
    except Exception as e:
        return await message.reply(f"**❌ Error parsing links:\n{e}**")

    if start_chat != end_chat:
        return await message.reply("**❌ Both links must be from the same channel.**")
    if start_id > end_id:
        return await message.reply("**❌ Invalid range: start ID cannot exceed end ID.**")

    try:
        await user.get_chat(start_chat)
    except Exception:
        pass

    prefix = args[1].rsplit("/", 1)[0]
    loading = await message.reply(f"📥 **Downloading posts {start_id}–{end_id}…**")

    downloaded = skipped = failed = 0

    for msg_id in range(start_id, end_id + 1):
        url = f"{prefix}/{msg_id}"
        try:
            chat_msg = await user.get_messages(chat_id=start_chat, message_ids=msg_id)
            if not chat_msg:
                skipped += 1
                continue

            has_media = bool(chat_msg.media_group_id or chat_msg.media)
            has_text  = bool(chat_msg.text or chat_msg.caption)
            if not (has_media or has_text):
                skipped += 1
                continue

            task = track_task(handle_download(bot, message, url))
            try:
                await task
                downloaded += 1
            except asyncio.CancelledError:
                await loading.delete()
                return await message.reply(
                    f"**❌ Batch canceled** after downloading `{downloaded}` posts."
                )

        except Exception as e:
            failed += 1
            LOGGER(__name__).error(f"Error at {url}: {e}")

        await asyncio.sleep(3)

    await loading.delete()
    await message.reply(
        "**✅ Batch Process Complete!**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"📥 **Downloaded** : `{downloaded}` post(s)\n"
        f"⏭️ **Skipped**    : `{skipped}` (no content)\n"
        f"❌ **Failed**     : `{failed}` error(s)"
    )


@bot.on_message(filters.private & ~filters.command(["start", "help", "dl", "stats", "logs", "killall"]))
@allowed_user_only
async def handle_any_message(bot: Client, message: Message):
    if message.text and not message.text.startswith("/"):
        await track_task(handle_download(bot, message, message.text))


@bot.on_message(filters.command("stats") & filters.private)
@allowed_user_only
async def stats(_, message: Message):
    currentTime = get_readable_time(time() - PyroConf.BOT_START_TIME)
    total, used, free = shutil.disk_usage(".")
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    cpuUsage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process(os.getpid())

    stats = (
        "**≧◉◡◉≦ Bot is Up and Running successfully.**\n\n"
        f"**➜ Bot Uptime:** `{currentTime}`\n"
        f"**➜ Total Disk Space:** `{total}`\n"
        f"**➜ Used:** `{used}`\n"
        f"**➜ Free:** `{free}`\n"
        f"**➜ Memory Usage:** `{round(process.memory_info()[0] / 1024**2)} MiB`\n\n"
        f"**➜ Upload:** `{sent}`\n"
        f"**➜ Download:** `{recv}`\n\n"
        f"**➜ CPU:** `{cpuUsage}%` | "
        f"**➜ RAM:** `{memory}%` | "
        f"**➜ DISK:** `{disk}%`"
    )
    await message.reply(stats)


@bot.on_message(filters.command("logs") & filters.private)
@allowed_user_only
async def logs(_, message: Message):
    if os.path.exists("logs.txt"):
        await message.reply_document(document="logs.txt", caption="**Logs**")
    else:
        await message.reply("**Not exists**")


@bot.on_message(filters.command("killall") & filters.private)
@allowed_user_only
async def cancel_all_tasks(_, message: Message):
    cancelled = 0
    for task in list(RUNNING_TASKS):
        if not task.done():
            task.cancel()
            cancelled += 1
    await message.reply(f"**Cancelled {cancelled} running task(s).**")


if __name__ == "__main__":
    try:
        LOGGER(__name__).info("Bot Started!")
        user.start()
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err)
    finally:
        LOGGER(__name__).info("Bot Stopped")
