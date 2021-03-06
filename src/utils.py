# -*- coding: utf-8 -*-

import json
import logging

from telegram import (
    Chat, Update,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import CallbackContext

import ffmpeg

from analytics import AnalyticsType
from constants import (
    MAX_VIDEO_NOTE_LENGTH,
    VIDEO_NOTE_CROP_OFFSET_PARAMS, VIDEO_NOTE_CROP_SIZE_PARAMS,
    ATTACHMENT_FILE_ID_KEY,
    OutputType
)

logger = logging.getLogger(__name__)


def check_admin(bot, message, analytics, admin_user_id):
    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    if not admin_user_id or message.from_user.id != admin_user_id:
        bot.send_message(message.chat_id, 'You are not allowed to use this command')

        return False

    return True


def ensure_size_under_limit(size, limit, update: Update, context: CallbackContext, file_reference_text='File'):
    if size <= limit:
        return True

    chat_type = update.effective_chat.type

    if chat_type == Chat.PRIVATE:
        message = update.message

        message_id = message.message_id
        chat_id = message.chat.id

        context.bot.send_message(
            chat_id,
            '{} size {} exceeds the maximum limit of {} (limit imposed by Telegram, not by this bot).'.format(
                file_reference_text,
                get_size_string_from_bytes(size),
                get_size_string_from_bytes(limit)
            ),
            reply_to_message_id=message_id
        )

    return False


def send_video(bot, chat_id, message_id, output_bytes, attachment, caption, chat_type):
    if chat_type == Chat.PRIVATE and attachment is not None:
        data = {
            ATTACHMENT_FILE_ID_KEY: attachment.file_id
        }

        button = InlineKeyboardButton('Rounded', callback_data=json.dumps(data))
        reply_markup = InlineKeyboardMarkup([[button]])
    else:
        reply_markup = None

    bot.send_video(
        chat_id,
        output_bytes,
        caption=caption,
        supports_streaming=True,
        reply_to_message_id=message_id,
        reply_markup=reply_markup
    )


def send_video_note(bot, chat_id, message_id, output_bytes):
    bot.send_video_note(
        chat_id,
        output_bytes,
        reply_to_message_id=message_id
    )


def convert(output_type, input_video_url=None, input_audio_url=None):
    if output_type == OutputType.AUDIO:
        return (
            ffmpeg
            .input(input_video_url)
            .output('pipe:', format='opus', strict='-2')
            .run(capture_stdout=True)
        )[0]
    elif output_type == OutputType.VIDEO:
        if input_audio_url is None:
            return (
                ffmpeg
                .input(input_video_url)
                .output('pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')
                .run(capture_stdout=True)
            )[0]
        else:
            input_video = ffmpeg.input(input_video_url)
            input_audio = ffmpeg.input(input_audio_url)

            return (
                ffmpeg
                .output(input_video, input_audio, 'pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')
                .run(capture_stdout=True)
            )[0]
    elif output_type == OutputType.VIDEO_NOTE:
        # Copied from https://github.com/kkroening/ffmpeg-python/issues/184#issuecomment-504390452.

        ffmpeg_input = (
            ffmpeg
            .input(input_video_url, t=MAX_VIDEO_NOTE_LENGTH)
        )
        ffmpeg_input_video = (
            ffmpeg_input
            .video
            .crop(
                VIDEO_NOTE_CROP_OFFSET_PARAMS,
                VIDEO_NOTE_CROP_OFFSET_PARAMS,
                VIDEO_NOTE_CROP_SIZE_PARAMS,
                VIDEO_NOTE_CROP_SIZE_PARAMS
            )
        )
        ffmpeg_input_audio = ffmpeg_input.audio
        ffmpeg_joined = ffmpeg.concat(ffmpeg_input_video, ffmpeg_input_audio, v=1, a=1).node
        ffmpeg_output = ffmpeg.output(ffmpeg_joined[0], ffmpeg_joined[1], 'pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')

        return ffmpeg_output.run(capture_stdout=True)[0]


def get_size_string_from_bytes(bytes, suffix='B'):
    """
    Partially copied from https://stackoverflow.com/a/1094933/865175.
    """

    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(bytes) < 1000.0:
            return '%3.1f %s%s' % (bytes, unit, suffix)

        bytes /= 1000.0

    return '%.1f %s%s' % (bytes, 'Y', suffix)
