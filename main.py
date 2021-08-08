# !/usr/bin/env python3
import asyncio
import json
import threading
import logging, subprocess
from time import time, sleep
# from challenge import Challenge
from pyrogram import (Client, filters)
from pyrogram.errors import ChatAdminRequired, ChannelPrivate, ChannelInvalid, PeerIdInvalid
from pyrogram.types import Message, User, InlineKeyboardButton, InlineKeyboardMarkup,ChatPermissions, CallbackQuery
from Timer import Timer
import re
import random

count = random.randint(5,10)
_app: Client = None
_channel: str = None
_start_message: str = None
# _challenge_scheduler = sched.scheduler(time, sleep)
_current_challenges = dict()
_cch_lock = threading.Lock()
_config = dict()
logging.basicConfig(level=logging.INFO)
# 设置一下日志记录，能够在诸如 systemctl status captchabot 这样的地方获得详细输出。

def load_config():
    global _config
    with open("config.json", encoding="utf-8") as f:
        _config = json.load(f)


def save_config():
    with open("config.json", "w") as f:
        json.dump(_config, f, indent=4)


def _update(app):
    
    @app.on_message(filters.command("help") & filters.group)
    async def helping_cmd(client: Client, message: Message):
        _me: User = await client.get_me()
        logging.info(message.text)
        await message.reply(_config["*"]["msg_self_introduction"])

    @app.on_message(filters.command("ping"))
    async def ping_command(client: Client, message: Message):
        await client.unban_chat_member(-1001270223433, 1871248189)
        await message.reply("poi~")

    @app.on_message(filters.command("start") & filters.private)
    async def start_command(client: Client, message: Message):
        await message.reply(_start_message)

    @app.on_callback_query()
    async def challenge_callback(client: Client,
                                 callback_query: CallbackQuery):
        query_data = str(callback_query.data)
        query_id = callback_query.id
        chat_id = callback_query.message.chat.id
        user_id = callback_query.from_user.id
        msg_id = callback_query.message.message_id
        chat_title = callback_query.message.chat.title
        user_name = callback_query.from_user.first_name
        group_config = _config.get(str(chat_id), _config["*"])
        if query_data in ["+", "-"]:
            admins = await client.get_chat_members(chat_id,
                                                   filter="administrators")
            if not any([
                    admin.user.id == user_id and
                (admin.status == "creator" or admin.can_restrict_members)
                    for admin in admins
            ]):
                await client.answer_callback_query(
                    query_id, group_config["msg_permission_denied"])
                return

            ch_id = "{chat}|{msg}".format(chat=chat_id, msg=msg_id)
            _cch_lock.acquire()
            # target: int = None
            target, timeout_event = _current_challenges.get(
                ch_id, (None, None))
            if ch_id in _current_challenges:
                del _current_challenges[ch_id]
            _cch_lock.release()
            timeout_event.stop()

            if query_data == "+":
                try:
                    await client.restrict_chat_member(
                        chat_id,
                        target,
                        permissions=ChatPermissions(
                            can_send_stickers=True,
                            can_send_animations=True,
                            can_send_games=True,
                            can_use_inline_bots=True,
                            can_send_messages=True,
                            can_send_media_messages=True,
                            can_add_web_page_previews=False,
                            can_send_polls=False
                        ))
                except ChatAdminRequired:
                    await client.answer_callback_query(
                        query_id, group_config["msg_bot_no_permission"])
                    return

                await client.edit_message_text(
                    chat_id,
                    msg_id,
                    group_config["msg_approved"].format(user=user_name),
                    reply_markup=None,
                )
                _me: User = await client.get_me()
                try:
                    await client.send_message(
                        int(_channel),
                        _config["msg_passed_admin"].format(
                            botid=str(_me.id),
                            targetuser=str(target),
                            groupid=str(chat_id),
                            grouptitle=str(chat_title),
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logging.error(str(e))
            else:
                try:
                    await client.kick_chat_member(chat_id, target)
                except ChatAdminRequired:
                    await client.answer_callback_query(
                        query_id, group_config["msg_bot_no_permission"])
                    return
                await client.edit_message_text(
                    chat_id,
                    msg_id,
                    group_config["msg_refused"].format(user=user_name),
                    reply_markup=None,
                )
                _me: User = await client.get_me()
                try:
                    await client.send_message(
                        int(_channel),
                        _config["msg_failed_admin"].format(
                            botid=str(_me.id),
                            targetuser=str(target),
                            groupid=str(chat_id),
                            grouptitle=str(chat_title),
                        ),
                        parse_mode="Markdown",
                    )
                except Exception as e:
                    logging.error(str(e))
            await client.answer_callback_query(query_id)
            return

        ch_id = "{chat}|{msg}".format(chat=chat_id, msg=msg_id)
        _cch_lock.acquire()
        target, timeout_event = _current_challenges.get(ch_id, (None, None))
        _cch_lock.release()
        if user_id != target:
            await client.answer_callback_query(
                query_id, group_config["msg_challenge_not_for_you"])
            return None
        timeout_event.stop()
        try:
            await client.restrict_chat_member(
                chat_id,
                target,
                permissions=ChatPermissions(can_send_stickers=True,
                                            can_send_animations=True,
                                            can_send_games=True,
                                            can_use_inline_bots=True,
                                            can_send_messages=True,
                                            can_send_media_messages=True,
                                            can_add_web_page_previews=False,
                                            can_send_polls=False))
        except ChatAdminRequired:
            pass

        correct = "no" == query_data
        if correct:
            await client.edit_message_text(
                chat_id,
                msg_id,
                group_config["msg_challenge_passed"],
                reply_markup=None)
            _me: User = await client.get_me()
            try:
                await client.send_message(
                    int(_channel),
                    _config["msg_passed_answer"].format(
                        botid=str(_me.id),
                        targetuser=str(target),
                        groupid=str(chat_id),
                        grouptitle=str(chat_title),
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(str(e))
        else:
            await client.edit_message_text(
                chat_id,
                msg_id,
                group_config["msg_challenge_failed"],
                reply_markup=None,
            )
            # await client.restrict_chat_member(chat_id, target)
            _me: User = await client.get_me()
            try:
                await client.send_message(
                    int(_channel),
                    _config["msg_failed_answer"].format(
                        botid=str(_me.id),
                        targetuser=str(target),
                        groupid=str(chat_id),
                        grouptitle=str(chat_title),
                    ),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(str(e))
            if group_config["challenge_timeout_action"] == "ban":
                await client.kick_chat_member(chat_id, user_id)
            elif group_config["challenge_timeout_action"] == "kick":
                await client.kick_chat_member(chat_id, user_id)
                await client.unban_chat_member(chat_id, user_id)
            else:
                pass
            if group_config["delete_failed_challenge"]:
                Timer(
                    client.delete_messages(chat_id, msg_id),
                    group_config["delete_failed_challenge_interval"],
                )
        if group_config["delete_passed_challenge"]:
            Timer(
                client.delete_messages(chat_id, msg_id),
                group_config["delete_passed_challenge_interval"],
            )

    # 验证
    @app.on_chat_member_updated()
    async def challenge_user(client: Client, message: Message):
        if message.new_chat_member is None:
            return
        if message.old_chat_member is not None :
            if message.old_chat_member.is_member == True :
                return
        target = message.new_chat_member.user
        if target.id == 905724203 or target.id == 1072874332 :
            return
        # 机器人被拉进群发自我介绍
        if message.from_user.id != target.id:
            if target.is_self:
                group_config = _config.get(str(message.chat.id), _config["*"])
                try:
                    await client.send_message(
                        message.chat.id, group_config["msg_self_introduction"])
                    _me: User = await client.get_me()
                    try:
                        await client.send_message(
                            int(_channel),
                            _config["msg_into_group"].format(
                                botid=str(_me.id),
                                groupid=str(message.chat.id),
                                grouptitle=str(message.chat.title),
                            ),
                            parse_mode="Markdown",
                        )
                    except Exception as e:
                        logging.error(str(e))
                except ChannelPrivate:
                    return
            return
        try:
            # 限制新用户权限 
            await client.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=target.id,
                permissions=ChatPermissions(can_send_stickers=False,
                                            can_send_animations=False,
                                            can_send_games=False,
                                            can_use_inline_bots=False,
                                            can_send_messages=False,
                                            can_send_media_messages=False,
                                            can_add_web_page_previews=False,
                                            can_send_polls=False))
        except ChatAdminRequired:
            return
        group_config = _config.get(str(message.chat.id), _config["*"])

        # 验证选项
        def generate_challenge_button():
            choices = []
            answers = []
            answers.append(InlineKeyboardButton("我不是机器人", callback_data="no"))
            answers.append(InlineKeyboardButton("请把我踢了吧", callback_data="yes"))
            choices.append(answers)
            return choices + [[
                InlineKeyboardButton(group_config["msg_approve_manually"],
                                     callback_data=b"+"),
                InlineKeyboardButton(group_config["msg_refuse_manually"],
                                     callback_data=b"-"),
            ]]

        timeout = group_config["challenge_timeout"]
        reply_message = await client.send_message(
            message.chat.id,
            group_config["msg_challenge"].format(
                target=target.first_name,
                target_id=target.id,
                timeout=timeout,
                challenge=
                "请证明你不是一个广告机器人。\nPlease prove yourself is not a robot."),
            reply_markup=InlineKeyboardMarkup(generate_challenge_button()),
        )
        _me: User = await client.get_me()
        chat_id = message.chat.id
        chat_title = message.chat.title
        target = message.from_user.id
        # 超时
        timeout_event = Timer(
            challenge_timeout(client, message.chat.id, message.from_user.id,
                              reply_message.message_id),
            timeout=group_config["challenge_timeout"],
        )
        _cch_lock.acquire()
        _current_challenges["{chat}|{msg}".format(
            chat=message.chat.id,
            msg=reply_message.message_id)] = (message.from_user.id,
                                              timeout_event)
        _cch_lock.release()

    # 验证超时
    async def challenge_timeout(client: Client, chat_id, from_id, reply_id):
        global _current_challenges
        _me: User = await client.get_me()
        group_config = _config.get(str(chat_id), _config["*"])

        _cch_lock.acquire()
        del _current_challenges["{chat}|{msg}".format(chat=chat_id,
                                                      msg=reply_id)]
        _cch_lock.release()

        # TODO try catch
        await client.edit_message_text(
            chat_id=chat_id,
            message_id=reply_id,
            text=group_config["msg_challenge_failed"],
            reply_markup=None,
        )
        try:
            await client.send_message(
                chat_id=_config["channel"],
                text=_config["msg_failed_timeout"].format(
                    botid=str(_me.id),
                    targetuser=str(from_id),
                    groupid=str(chat_id)))
        except Exception as e:
            logging.error(str(e))
        if group_config["challenge_timeout_action"] == "ban":
            await client.kick_chat_member(chat_id, from_id)
        elif group_config["challenge_timeout_action"] == "kick":
            await client.kick_chat_member(chat_id, from_id)
        else:
            pass

        if group_config["delete_failed_challenge"]:
            Timer(
                client.delete_messages(chat_id, reply_id),
                group_config["delete_failed_challenge_interval"],
            )


def _main():
    global _app, _channel, _start_message, _config
    load_config()
    _api_id = _config["api_id"]
    _api_hash = _config["api_hash"]
    _token = _config["token"]
    _channel = _config["channel"]
    _start_message = _config["msg_start_message"]
    _app = Client("bot",
                    bot_token=_token,
                    api_id=_api_id,
                    api_hash=_api_hash)
    try:
        _update(_app)
        _app.run()
    except KeyboardInterrupt:
        quit()
    except Exception as e:
        logging.error(e)
        # _main()


if __name__ == "__main__":
    _main()
