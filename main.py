import os
import logging
import random
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CallbackContext, CommandHandler, CallbackQueryHandler, MessageHandler, Filters

from sqlhelper import Base, User, Post, Settings

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARN)
print('[Predlozhka]Initializing database...')

engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

print('[Predlozhka]Initializing Telegram API...')
token = '8079268730:AAER_kXt7qSVqK0shp0IFUyDYGur6FrzGCo'
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
#          СТАРЫЕ ФУНКЦИИ
# ============================

def start(update: Update, context: CallbackContext):
    print('[Predlozhka][start]Start command message triggered')
    db = Session()
    if not db.query(User).filter_by(user_id=update.effective_user.id).first():
        db.add(User(update.effective_user.id))
    update.message.reply_text('Добро пожаловать! Для того чтобы предложить пост, просто отправьте изображение.')
    db.commit()


def initialize(update: Update, context: CallbackContext):
    global initialized, target_channel
    if not initialized:
        db = Session()
        print('[Predlozhka][INFO]Initialize command triggered!')
        initialized = True
        initializer = update.effective_user.id
        parameters = update.message.text.replace('/init ', '').split(';')
        target_channel = parameters[0]

        settings = db.query(Settings).first()
        settings.initialized = True
        settings.initializer_id = initializer
        settings.target_channel = target_channel

        update.message.reply_text('Bot initialized successfully:\n{}'.format(repr(settings)))
        print('[Predlozhka]User {} selected as admin'.format(parameters[1]))

        target_user = db.query(User).filter_by(user_id=int(parameters[1])).first()
        if target_user:
            target_user.is_admin = True
        else:
            db.add(User(user_id=int(parameters[1]), is_admin=True))

        db.commit()
        db.close()


def photo_handler(update: Update, context: CallbackContext):
    print('[Predlozhka][photo_handler]Image accepted, downloading...')
    db = Session()
    photo = update.message.photo[-1].get_file()
    path = 'temp/{}_{}'.format(random.randint(1, 100000000000), photo.file_path.split('/')[-1])
    photo.download(path)

    print('[Predlozhka][photo_handler]Image downloaded, generating post...')
    post = Post(update.effective_user.id, path, update.message.caption)
    db.add(post)
    db.commit()

    print('[Predlozhka][photo_handler]Sending message to admin...')
    buttons = [
        [InlineKeyboardButton('✅', callback_data=json.dumps({'post': post.post_id, 'action': 'accept'})),
         InlineKeyboardButton('❌', callback_data=json.dumps({'post': post.post_id, 'action': 'decline'}))]
    ]

    owner = update.effective_user

    caption = f"📩 Новое сообщение в предложку\n" \
              f"👤 Отправитель: {owner.first_name}\n"

    if owner.username:
        caption += f"🔗 Username: @{owner.username}\n"

    caption += f"🆔 ID: {owner.id}\n"

    if post.text:
        caption += f"\n📝 Текст: {post.text}"

    admin = db.query(User).filter_by(is_admin=True).first()

    updater.bot.send_photo(
        admin.user_id,
        open(post.attachment_path, 'rb'),
        caption,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    db.close()

    update.message.reply_text('Ваш пост отправлен администратору.')


def callback_handler(update: Update, context: CallbackContext):
    print('[Predlozhka][callback_handler]Processing admin interaction')
    db = Session()
    user = db.query(User).filter_by(user_id=update.effective_user.id).first()

    if user and user.is_admin:
        data = json.loads(update.callback_query.data)
        post = db.query(Post).filter_by(post_id=data['post']).first()

        if post:
            if data['action'] == 'accept':
                updater.bot.send_photo(target_channel, open(post.attachment_path, 'rb'), caption=post.text)
                update.callback_query.answer('✅ Пост успешно отправлен')
                updater.bot.send_message(post.owner_id, 'Ваш пост опубликован!')
            elif data['action'] == 'decline':
                update.callback_query.answer('Пост отклонён')

            try:
                os.remove(post.attachment_path)
            except:
                pass

            db.delete(post)
            updater.bot.delete_message(update.callback_query.message.chat_id, update.callback_query.message.message_id)

        else:
            update.callback_query.answer('Ошибка: пост не найден')

    else:
        update.callback_query.answer('Unauthorized')

    db.commit()
    db.close()


# ============================
#        РЕГИСТРАЦИЯ
# ============================

updater.dispatcher.add_handler(CommandHandler('start', start))
updater.dispatcher.add_handler(CommandHandler('init', initialize))

# новые команды
updater.dispatcher.add_handler(CommandHandler('addadmin', add_admin))
updater.dispatcher.add_handler(CommandHandler('removeadmin', remove_admin))
updater.dispatcher.add_handler(CommandHandler('setchannel', set_channel))
updater.dispatcher.add_handler(CommandHandler('admins', list_admins))

updater.dispatcher.add_handler(MessageHandler(Filters.photo & Filters.private, photo_handler))
updater.dispatcher.add_handler(CallbackQueryHandler(callback_handler))

updater.start_polling()
