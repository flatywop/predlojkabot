import os
import logging
import random
import json
import mimetypes
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

from sqlhelper import Base, User, Post, Settings

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARN)

print('[Predlozhka] Введите токен Telegram-бота:')
token = input('TOKEN: ').strip()
if not token:
    raise SystemExit("Не введён токен. Завершение работы.")

print('[Predlozhka]Initializing database...')

engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

print('[Predlozhka]Initializing Telegram API...')
updater = Updater(token, use_context=True)

print('[Predlozhka]Creating temp folder...')
if not os.path.exists('temp'):
    os.makedirs('temp')

print('[Predlozhka]Checking settings...')
session = Session()
settings = session.query(Settings).first()

if not settings:
    settings = Settings(False, None, None)
    session.add(settings)

initialized = settings.initialized
target_channel = settings.target_channel

if initialized:
    if target_channel:
        print('[Predlozhka]Settings...[OK], target_channel: {}'.format(target_channel))
    elif settings.initializer_id:
        print('[Predlozhka][WARN]Bot seems to be initialized, but no target selected.')
        updater.bot.send_message(settings.initializer_id, 'Warning! No target channel specified.')
else:
    print('[Predlozhka][CRITICAL]Bot is not initialized! Waiting for initializer...')

session.commit()
session.close()

print('[Predlozhka]Declaring functions and handlers...')

# ============================
#         HELPERS
# ============================

def is_admin(user_id):
    db = Session()
    user = db.query(User).filter_by(user_id=user_id).first()
    db.close()
    return user and user.is_admin


def _unique_path(original_name: str) -> str:
    base = Path(original_name).name
    uniq = f"{random.randint(1, 10**12)}_{base}"
    return os.path.join('temp', uniq)


def _guess_type_by_path(path: str) -> str:
    if not path:
        return 'text'
    ext = Path(path).suffix.lower()
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.heic', '.webp') and ext != '.webp':
        return 'photo'
    if ext == '.webp':
        return 'sticker'
    if ext in ('.mp4', '.mov', '.mkv', '.avi', '.webm'):
        return 'video'
    if ext in ('.mp3', '.m4a', '.flac', '.wav', '.aac'):
        return 'audio'
    if ext in ('.ogg', '.oga'):
        return 'voice'
    return 'document'


# ============================
#     КОМАНДЫ АДМИНИСТРАЦИИ
# ============================

def add_admin(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ У вас нет прав.")
        return

    if len(context.args) != 1:
        update.message.reply_text("Использование:\n/addadmin <user_id>")
        return

    admin_id = int(context.args[0])
    db = Session()
    target = db.query(User).filter_by(user_id=admin_id).first()

    if target:
        target.is_admin = True
    else:
        target = User(user_id=admin_id, is_admin=True)
        db.add(target)

    db.commit()
    db.close()

    update.message.reply_text(f"✅ Пользователь {admin_id} теперь администратор.")


def remove_admin(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ У вас нет прав.")
        return

    if len(context.args) != 1:
        update.message.reply_text("Использование:\n/removeadmin <user_id>")
        return

    admin_id = int(context.args[0])
    db = Session()
    target = db.query(User).filter_by(user_id=admin_id).first()

    if not target or not target.is_admin:
        update.message.reply_text("Пользователь не является админом.")
        return

    target.is_admin = False
    db.commit()
    db.close()

    update.message.reply_text(f"🗑 Пользователь {admin_id} больше НЕ администратор.")


def set_channel(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ У вас нет прав.")
        return

    if len(context.args) != 1:
        update.message.reply_text("Использование:\n/setchannel <channel_id>")
        return

    channel_id = context.args[0]

    db = Session()
    settings = db.query(Settings).first()
    settings.target_channel = channel_id
    db.commit()
    db.close()

    global target_channel
    target_channel = channel_id

    update.message.reply_text(f"📡 Целевой канал обновлён:\n{channel_id}")


def list_admins(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id):
        update.message.reply_text("❌ У вас нет прав.")
        return

    db = Session()
    admins = db.query(User).filter_by(is_admin=True).all()
    db.close()

    if not admins:
        update.message.reply_text("Администраторов нет.")
        return

    msg = "👑 Администраторы:\n\n"
    for a in admins:
        msg += f"• {a.user_id}\n"

    update.message.reply_text(msg)


# ============================
#          СТАРТ
# ============================

def start(update: Update, context: CallbackContext):
    print('[Predlozhka][start]Start command message triggered')
    db = Session()
    if not db.query(User).filter_by(user_id=update.effective_user.id).first():
        db.add(User(update.effective_user.id))
    update.message.reply_text('Добро пожаловать! Чтобы предложить пост — отправьте сообщение.')
    db.commit()
    db.close()


def initialize(update: Update, context: CallbackContext):
    global initialized, target_channel
    if not initialized:
        db = Session()
        print('[Predlozhka][INFO]Initialize!')
        initialized = True
        initializer = update.effective_user.id
        parameters = update.message.text.replace('/init ', '').split(';')
        target_channel = parameters[0]

        settings = db.query(Settings).first()
        settings.initialized = True
        settings.initializer_id = initializer
        settings.target_channel = target_channel

        update.message.reply_text(f'Bot initialized:\n{repr(settings)}')
        print('[Predlozhka]Admin:', parameters[1])

        target_user = db.query(User).filter_by(user_id=int(parameters[1])).first()
        if target_user:
            target_user.is_admin = True
        else:
            db.add(User(user_id=int(parameters[1]), is_admin=True))

        db.commit()
        db.close()


# ============================
#   УНИВЕРСАЛЬНАЯ ОТПРАВКА
# ============================

def send_to_admin_with_buttons(update: Update, context: CallbackContext, attachment_path=None, text=None):
    db = Session()

    post = Post(update.effective_user.id, attachment_path, text)
    db.add(post)
    db.commit()
    db.refresh(post)

    buttons = [[
        InlineKeyboardButton('✅', callback_data=json.dumps({'post': post.post_id, 'action': 'accept'})),
        InlineKeyboardButton('❌', callback_data=json.dumps({'post': post.post_id, 'action': 'decline'})),
        InlineKeyboardButton('BAN', callback_data=json.dumps({'post': post.post_id, 'action': 'ban'}))
    ]]

    admin = db.query(User).filter_by(is_admin=True).first()

    if not admin:
        update.message.reply_text("Ошибка: админ не найден.")
        db.close()
        return

    owner = update.effective_user

    caption = (
        f"📩 Новая предложка\n"
        f"👤 От: {owner.first_name}\n"
    )

    if owner.username:
        caption += f"🔗 @{owner.username}\n"

    caption += f"🆔 {owner.id}\n"

    if text:
        caption += f"\n📝 {text}"

    if attachment_path:
        media_type = _guess_type_by_path(attachment_path)
        try:
            if media_type == 'photo':
                context.bot.send_photo(admin.user_id, open(attachment_path, 'rb'), caption=caption,
                                       reply_markup=InlineKeyboardMarkup(buttons))
            elif media_type == 'video':
                context.bot.send_video(admin.user_id, open(attachment_path, 'rb'), caption=caption,
                                       reply_markup=InlineKeyboardMarkup(buttons))
            elif media_type == 'audio':
                context.bot.send_audio(admin.user_id, open(attachment_path, 'rb'), caption=caption,
                                       reply_markup=InlineKeyboardMarkup(buttons))
            elif media_type == 'voice':
                context.bot.send_voice(admin.user_id, open(attachment_path, 'rb'), caption=caption,
                                       reply_markup=InlineKeyboardMarkup(buttons))
            elif media_type == 'sticker':
                context.bot.send_sticker(admin.user_id, open(attachment_path, 'rb'),
                                         reply_markup=InlineKeyboardMarkup(buttons))
            else:
                context.bot.send_document(admin.user_id, open(attachment_path, 'rb'), caption=caption,
                                          reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            print('[Error sending attachment]', e)
            context.bot.send_message(admin.user_id, caption)
    else:
        context.bot.send_message(admin.user_id, caption, reply_markup=InlineKeyboardMarkup(buttons))

    db.close()
    update.message.reply_text("Ваше сообщение отправлено администратору.")


# ============================
#   ХЕНДЛЕРЫ МЕДИА
# ============================

def photo_handler(update: Update, context: CallbackContext):
    photo = update.message.photo[-1].get_file()
    original = getattr(photo, 'file_path', f"{photo.file_id}.jpg")
    path = _unique_path(original)
    photo.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path, text=update.message.caption)


def text_handler(update: Update, context: CallbackContext):
    send_to_admin_with_buttons(update, context, text=update.message.text)


def document_handler(update: Update, context: CallbackContext):
    doc = update.message.document.get_file()
    original = update.message.document.file_name or getattr(doc, 'file_path', f"{doc.file_id}")
    path = _unique_path(original)
    doc.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path, text=update.message.caption)


def audio_handler(update: Update, context: CallbackContext):
    a = update.message.audio.get_file()
    original = getattr(update.message.audio, 'file_name', getattr(a, 'file_path', f"{a.file_id}.mp3"))
    path = _unique_path(original)
    a.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path, text=update.message.caption)


def voice_handler(update: Update, context: CallbackContext):
    v = update.message.voice.get_file()
    original = getattr(v, 'file_path', f"{v.file_id}.ogg")
    path = _unique_path(original)
    v.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path)


def video_handler(update: Update, context: CallbackContext):
    vid = update.message.video.get_file()
    original = getattr(update.message.video, 'file_name', getattr(vid, 'file_path', f"{vid.file_id}.mp4"))
    path = _unique_path(original)
    vid.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path, text=update.message.caption)


def sticker_handler(update: Update, context: CallbackContext):
    st = update.message.sticker.get_file()
    path = _unique_path(f"{st.file_id}.webp")
    st.download(path)
    send_to_admin_with_buttons(update, context, attachment_path=path)


def forward_all_handler(update: Update, context: CallbackContext):
    msg = update.message
    if msg.text:
        return text_handler(update, context)
    if msg.photo:
        return photo_handler(update, context)
    if msg.document:
        return document_handler(update, context)
    if msg.video:
        return video_handler(update, context)
    if msg.audio:
        return audio_handler(update, context)
    if msg.voice:
        return voice_handler(update, context)
    if msg.sticker:
        return sticker_handler(update, context)

    send_to_admin_with_buttons(update, context, text="(Неизвестный тип сообщения)")


# ============================
# CALLBACK
# ============================

def _publish_post_to_channel(post, bot):
    if not post:
        return False

    if not post.attachment_path:
        try:
            bot.send_message(chat_id=target_channel, text=post.text or '')
            return True
        except Exception as e:
            print('[Publish error]', e)
            return False

    media_type = _guess_type_by_path(post.attachment_path)
    try:
        if media_type == 'photo':
            bot.send_photo(target_channel, open(post.attachment_path, 'rb'), caption=post.text or '')
        elif media_type == 'video':
            bot.send_video(target_channel, open(post.attachment_path, 'rb'), caption=post.text or '')
        elif media_type == 'audio':
            bot.send_audio(target_channel, open(post.attachment_path, 'rb'), caption=post.text or '')
        elif media_type == 'voice':
            bot.send_voice(target_channel, open(post.attachment_path, 'rb'), caption=post.text or '')
        elif media_type == 'sticker':
            bot.send_sticker(target_channel, open(post.attachment_path, 'rb'))
        else:
            bot.send_document(target_channel, open(post.attachment_path, 'rb'), caption=post.text or '')
        return True
    except Exception as e:
        print('[Publish error]', e)
        return False


def callback_handler(update: Update, context: CallbackContext):
    db = Session()
    user = db.query(User).filter_by(user_id=update.effective_user.id).first()

    try:
        data = json.loads(update.callback_query.data)
    except:
        update.callback_query.answer('Неверный формат данных')
        db.close()
        return

    post = db.query(Post).filter_by(post_id=data.get('post')).first()

    if not user or not user.is_admin:
        update.callback_query.answer('Unauthorized')
        db.close()
        return

    if not post:
        update.callback_query.answer('Пост не найден')
        db.close()
        return

    action = data.get('action')

    if action == 'accept':
        ok = _publish_post_to_channel(post, updater.bot)
        if ok:
            update.callback_query.answer('Опубликовано')
            try:
                updater.bot.send_message(post.owner_id, 'Ваш пост опубликован!')
            except:
                pass
        else:
            update.callback_query.answer('Ошибка публикации')

    elif action == 'decline':
        update.callback_query.answer('Отклонено')
        try:
            updater.bot.send_message(post.owner_id, 'Ваш пост отклонён.')
        except:
            pass

    elif action == 'ban':
        try:
            context.bot.ban_chat_member(target_channel, post.owner_id)
        except Exception as e:
            print('[Ban error]', e)

        update.callback_query.answer('Пользователь забанен')

        try:
            updater.bot.send_message(post.owner_id, "Вы заблокированы.")
        except:
            pass

    else:
        update.callback_query.answer('Неизвестно')

    db.close()


# ============================
#        РЕГИСТРАЦИЯ
# ============================

updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(CommandHandler('init', initialize))

updater.dispatcher.add_handler(CommandHandler('addadmin', add_admin))
updater.dispatcher.add_handler(CommandHandler('removeadmin', remove_admin))
updater.dispatcher.add_handler(CommandHandler('setchannel', set_channel))
updater.dispatcher.add_handler(CommandHandler('admins', list_admins))

updater.dispatcher.add_handler(MessageHandler(Filters.photo & Filters.private, photo_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.document & Filters.private, document_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.video & Filters.private, video_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.audio & Filters.private, audio_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.voice & Filters.private, voice_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.sticker & Filters.private, sticker_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.text & Filters.private, text_handler))
updater.dispatcher.add_handler(MessageHandler(Filters.all & Filters.private, forward_all_handler))

updater.dispatcher.add_handler(CallbackQueryHandler(callback_handler))

updater.start_polling()
print('[Predlozhka] Bot started.')
