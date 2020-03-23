import datetime
import importlib
import re
import resource
import platform
import sys
import traceback
import wikipedia
from typing import Optional, List

from telegram import Message, Chat, Update, Bot, User
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError, ChatMigrated, TelegramError
from telegram.ext import CommandHandler, Filters, MessageHandler, CallbackQueryHandler
from telegram.ext.dispatcher import run_async, DispatcherHandlerStop, Dispatcher
from telegram.utils.helpers import escape_markdown, mention_html

from emilia import dispatcher, updater, TOKEN, WEBHOOK, OWNER_ID, DONATION_LINK, CERT_PATH, PORT, URL, LOGGER, spamcheck
from emilia.modules import ALL_MODULES
from emilia.modules.languages import tl
from emilia.modules.helper_funcs.chat_status import is_user_admin
from emilia.modules.helper_funcs.misc import paginate_modules
from emilia.modules.helper_funcs.verifier import verify_welcome
from emilia.modules.sql import languages_sql as langsql

from emilia.modules.connection import connect_button
from emilia.modules.languages import set_language

PM_START_TEXT = "start_text"

HELP_STRINGS = "help_text"#.format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else "\nAll commands can either be used with / or !.\n")

DONATE_STRING = "donate_text"

IMPORTED = {}
MIGRATEABLE = []
HELPABLE = {}
STATS = []
USER_INFO = []
DATA_IMPORT = []
DATA_EXPORT = []

CHAT_SETTINGS = {}
USER_SETTINGS = {}

for module_name in ALL_MODULES:
    imported_module = importlib.import_module("emilia.modules." + module_name)
    if not hasattr(imported_module, "__mod_name__"):
        imported_module.__mod_name__ = imported_module.__name__

    if not imported_module.__mod_name__.lower() in IMPORTED:
        IMPORTED[imported_module.__mod_name__.lower()] = imported_module
    else:
        raise Exception("Você não pode ter dois módulos com o mesmo nome! Por favor mude um!")

    if hasattr(imported_module, "__help__") and imported_module.__help__:
        HELPABLE[imported_module.__mod_name__.lower()] = imported_module

    if hasattr(imported_module, "__migrate__"):
        MIGRATEABLE.append(imported_module)

    if hasattr(imported_module, "__stats__"):
        STATS.append(imported_module)

    if hasattr(imported_module, "__user_info__"):
        USER_INFO.append(imported_module)

    if hasattr(imported_module, "__import_data__"):
        DATA_IMPORT.append(imported_module)

    if hasattr(imported_module, "__export_data__"):
        DATA_EXPORT.append(imported_module)

    if hasattr(imported_module, "__chat_settings__"):
        CHAT_SETTINGS[imported_module.__mod_name__.lower()] = imported_module

    if hasattr(imported_module, "__user_settings__"):
        USER_SETTINGS[imported_module.__mod_name__.lower()] = imported_module

def send_help(chat_id, text, keyboard=None):
    if not keyboard:
        keyboard = InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help"))
    dispatcher.bot.send_message(chat_id=chat_id,
                                text=text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=keyboard)


@run_async
def test(update, context):
    update.effective_message.reply_text("Essa pessoa editou uma mensagem!")
    print(context.match)
    print(update.effective_message.text)


@run_async
@spamcheck
def start(update, context):
    if update.effective_chat.type == "private":
        args = context.args
        if len(args) >= 1:
            if args[0].lower() == "help":
                send_help(update.effective_chat.id, tl(update.effective_message, HELP_STRINGS))

            elif args[0].lower() == "get_notes":
                update.effective_message.reply_text(tl(update.effective_message, "Anda sekarang dapat mengambil catatan di grup."))

            elif args[0].lower().startswith("stngs_"):
                match = re.match("stngs_(.*)", args[0].lower())
                chat = dispatcher.bot.getChat(match.group(1))

                if is_user_admin(chat, update.effective_user.id):
                    send_settings(match.group(1), update.effective_user.id, False)
                else:
                    send_settings(match.group(1), update.effective_user.id, True)

            elif args[0][1:].isdigit() and "rules" in IMPORTED:
                IMPORTED["rules"].send_rules(update, args[0], from_pm=True)

            elif args[0][:4] == "wiki":
                wiki = args[0].split("-")[1].replace('_', ' ')
                message = update.effective_message
                getlang = langsql.get_lang(message)
                if getlang == "id":
                    wikipedia.set_lang("id")
                pagewiki = wikipedia.page(wiki)
                judul = pagewiki.title
                summary = pagewiki.summary
                if len(summary) >= 4096:
                    summary = summary[:4000]+"..."
                message.reply_text("<b>{}</b>\n{}".format(judul, summary), parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(
                            [[InlineKeyboardButton(text=tl(update.effective_message, "Baca di Wikipedia"), url=pagewiki.url)]]))

            elif args[0][:6].lower() == "verify":
                chat_id = args[0].split("_")[1]
                verify_welcome(update, context, chat_id)

        else:
            first_name = update.effective_user.first_name
            buttons = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text="🎉 Me adicione em outro grupo!", url="https://t.me/{}?startgroup=new".format(context.bot.username))],
                [InlineKeyboardButton(text="💭 Linguagem", callback_data="main_setlang"), InlineKeyboardButton(text="⚙️ Connect Group", callback_data="main_connect")],
                [InlineKeyboardButton(text="👥 Grupo de Suporte", url="https://t.me/EmiliaOfficial"), InlineKeyboardButton(text="🔔 Update Channel", url="https://t.me/AyraBotNews")],
                [InlineKeyboardButton(text="❓ Ajuda", url="https://t.me/{}?start=help".format(context.bot.username)), InlineKeyboardButton(text="💖 Donate", url="http://ayrahikari.github.io/donations.html")]])
            update.effective_message.reply_text(
                tl(update.effective_message, PM_START_TEXT).format(escape_markdown(first_name), escape_markdown(context.bot.first_name), OWNER_ID),
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=buttons)
    else:
        update.effective_message.reply_text(tl(update.effective_message, "Ada yang bisa saya bantu? 😊"))


def m_connect_button(update, context):
    context.bot.delete_message(update.effective_chat.id, update.effective_message.message_id)
    connect_button(update, context)

def m_change_langs(update, context):
    context.bot.delete_message(update.effective_chat.id, update.effective_message.message_id)
    set_language(update, context)

# for test purposes
def error_callback(update, context):
    devs = [OWNER_ID]
    if update.effective_message:
        text = "Ei. Lamento informar que ocorreu um erro enquanto eu tentava lidar com sua atualização. " \
               "Meu desenvolvedor não foi notificado."
        update.effective_message.reply_text(text)
    trace = "".join(traceback.format_tb(sys.exc_info()[2]))
    payload = ""
    if update.effective_user:
        payload += f' with the user {mention_html(update.effective_user.id, update.effective_user.first_name)}'
    if update.effective_chat:
        payload += f' within the chat <i>{update.effective_chat.title}</i>'
        if update.effective_chat.username:
            payload += f' (@{update.effective_chat.username})'
    if update.poll:
        payload += f' with the poll id {update.poll.id}.'
    text = f"Hey.\n The error <code>{context.error}</code> happened{payload}. The full traceback:\n\n<code>{trace}" \
           f"</code>"
    for dev_id in devs:
        context.bot.send_message(dev_id, text, parse_mode=ParseMode.HTML)
    try:
        raise context.error
    except Unauthorized:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except BadRequest:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except TimedOut:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except NetworkError:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except ChatMigrated as e:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)
    except TelegramError:
        LOGGER.exception('Update "%s" caused error "%s"', update, context.error)


@run_async
def help_button(update, context):
    query = update.callback_query
    mod_match = re.match(r"help_module\((.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back", query.data)

    print(query.message.chat.id)

    try:
        if mod_match:
            module = mod_match.group(1)
            text = tl(update.effective_message, "Isso é ajuda para o módulo *{}*:\n").format(HELPABLE[module].__mod_name__) \
                   + tl(update.effective_message, HELPABLE[module].__help__)

            query.message.reply_text(text=text,
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        [[InlineKeyboardButton(text=tl(query.message, "Voltar"), callback_data="help_back")]]))

        elif prev_match:
            curr_page = int(prev_match.group(1))
            query.message.reply_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(curr_page - 1, HELPABLE, "help")))

        elif next_match:
            next_page = int(next_match.group(1))
            query.message.reply_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(next_page + 1, HELPABLE, "help")))

        elif back_match:
            query.message.reply_text(text=tl(query.message, HELP_STRINGS),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help")))

        query.message.delete()
        context.bot.answer_callback_query(query.id)
    except Exception as excp:
        if excp.message == "A mensagem não pode ser modificada":
            pass
        elif excp.message == "Query_id_invalid":
            pass
        elif excp.message == "A mensagem não pode ser excluída":
            pass
        else:
            query.message.edit_text(excp.message)
            LOGGER.exception("Exception in help buttons. %s", str(query.data))


@run_async
@spamcheck
def get_help(update, context):
    chat = update.effective_chat
    args = update.effective_message.text.split(None, 1)

    if chat.type != chat.PRIVATE:

        update.effective_message.reply_text(tl(update.effective_message, "Entre em contato comigo no PM para obter uma lista de pedidos."),
                                            reply_markup=InlineKeyboardMarkup(
                                                [[InlineKeyboardButton(text=tl(update.effective_message, "Tolong"),
                                                                       url="t.me/{}?start=help".format(
                                                                           context.bot.username))]]))
        return

    elif len(args) >= 2 and any(args[1].lower() == x for x in HELPABLE):
        module = args[1].lower()
        text = tl(update.effective_message, "Esta é a ajuda disponível para o módulo *{}*:\n").format(HELPABLE[module].__mod_name__) \
               + tl(update.effective_message, HELPABLE[module].__help__)
        send_help(chat.id, text, InlineKeyboardMarkup([[InlineKeyboardButton(text=tl(update.effective_message, "Voltar"), callback_data="help_back")]]))

    else:
        send_help(chat.id, tl(update.effective_message, HELP_STRINGS))


def send_settings(chat_id, user_id, user=False):
    if user:
        if USER_SETTINGS:
            settings = "\n\n".join(
                "*{}*:\n{}".format(mod.__mod_name__, mod.__user_settings__(user_id)) for mod in USER_SETTINGS.values())
            dispatcher.bot.send_message(user_id, tl(chat_id, "Essas são as suas configurações atuais:") + "\n\n" + settings,
                                        parse_mode=ParseMode.MARKDOWN)

        else:
            dispatcher.bot.send_message(user_id, tl(chat_id, "Parece que não há configurações específicas do usuário disponíveis 😢"),
                                        parse_mode=ParseMode.MARKDOWN)

    else:
        if CHAT_SETTINGS:
            chat_name = dispatcher.bot.getChat(chat_id).title
            dispatcher.bot.send_message(user_id,
                                        text=tl(chat_id, "Qual módulo você deseja verificar nas configurações {}?").format(
                                            chat_name),
                                        reply_markup=InlineKeyboardMarkup(
                                            paginate_modules(0, CHAT_SETTINGS, "stngs", chat=chat_id)))
        else:
            dispatcher.bot.send_message(user_id, tl(chat_id, "Parece que não há configurações para o chat disponíveis 😢\nEnvie Isto "
                                                 "ao seu bate-papo como administrador para encontrar as configurações atuais!"),
                                        parse_mode=ParseMode.MARKDOWN)


@run_async
def settings_button(update, context):
    query = update.callback_query
    user = update.effective_user
    mod_match = re.match(r"stngs_module\((.+?),(.+?)\)", query.data)
    prev_match = re.match(r"stngs_prev\((.+?),(.+?)\)", query.data)
    next_match = re.match(r"stngs_next\((.+?),(.+?)\)", query.data)
    back_match = re.match(r"stngs_back\((.+?)\)", query.data)
    try:
        if mod_match:
            chat_id = mod_match.group(1)
            module = mod_match.group(2)
            chat = context.bot.get_chat(chat_id)
            getstatusadmin = context.bot.get_chat_member(chat_id, user.id)
            isadmin = getstatusadmin.status in ('administrador', 'criador')
            if isadmin == False or user.id != OWNER_ID:
                query.message.edit_text("Seu status de administrador mudou")
                return
            text = tl(update.effective_message, "*{}* possui as seguintes configurações para o módulo *{}*:\n\n").format(escape_markdown(chat.title),
                                                                                     CHAT_SETTINGS[
                                                                                        module].__mod_name__) + \
                   CHAT_SETTINGS[module].__chat_settings__(chat_id, user.id)
            try:
                set_button = CHAT_SETTINGS[module].__chat_settings_btn__(chat_id, user.id)
            except AttributeError:
                set_button = []
            set_button.append([InlineKeyboardButton(text=tl(query.message, "Voltar"),
                                                               callback_data="stngs_back({})".format(chat_id))])
            query.message.reply_text(text=text,
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(set_button))

        elif prev_match:
            chat_id = prev_match.group(1)
            curr_page = int(prev_match.group(2))
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Oi! Existem várias configurações para {} - vá em frente e escolha "
                                       "no que você está interessado.").format(chat.title),
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(curr_page - 1, CHAT_SETTINGS, "stngs",
                                                         chat=chat_id)))

        elif next_match:
            chat_id = next_match.group(1)
            next_page = int(next_match.group(2))
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Oi! Existem várias configurações para {} - vá em frente e escolha "
                                       "no que você está interessado.").format(chat.title),
                                  reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(next_page + 1, CHAT_SETTINGS, "stngs",
                                                         chat=chat_id)))

        elif back_match:
            chat_id = back_match.group(1)
            chat = context.bot.get_chat(chat_id)
            query.message.reply_text(text=tl(update.effective_message, "Oi! Existem várias configurações para {} - vá em frente e escolha "
                                       "no que você está interessado.").format(escape_markdown(chat.title)),
                                  parse_mode=ParseMode.MARKDOWN,
                                  reply_markup=InlineKeyboardMarkup(paginate_modules(0, CHAT_SETTINGS, "stngs",
                                                                                     chat=chat_id)))

        query.message.delete()
        context.bot.answer_callback_query(query.id)
    except Exception as excp:
        if excp.message == "A mensagem não pode ser modificada":
            pass
        elif excp.message == "Query_id_invalid":
            pass
        elif excp.message == "A mensagem não pode ser excluída":
            pass
        else:
            query.message.edit_text(excp.message)
            LOGGER.exception("Exceção no botão de configurações. %s", str(query.data))


@run_async
@spamcheck
def get_settings(update, context):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    args = msg.text.split(None, 1)

    if chat.type != chat.PRIVATE:
        if is_user_admin(chat, user.id):
            text = tl(update.effective_message, "Clique aqui para obter essas configurações do chat, assim como as suas.")
            msg.reply_text(text,
                           reply_markup=InlineKeyboardMarkup(
                               [[InlineKeyboardButton(text="Configurações",
                                                      url="t.me/{}?start=stngs_{}".format(
                                                          context.bot.username, chat.id))]]))
    else:
        send_settings(chat.id, user.id, True)


@run_async
@spamcheck
def donate(update, context):
    user = update.effective_message.from_user
    chat = update.effective_chat

    if chat.type == "private":
        update.effective_message.reply_text(tl(update.effective_message, DONATE_STRING), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

        if OWNER_ID != 388576209 and DONATION_LINK:
            update.effective_message.reply_text(tl(update.effective_message, "Você também pode contribuir com a pessoa que está me hospedando no momento"
                                                "[disini]({})").format(DONATION_LINK),
                                                parse_mode=ParseMode.MARKDOWN)

    else:
        try:
            context.bot.send_message(user.id, tl(update.effective_message, DONATE_STRING), parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

            update.effective_message.reply_text(tl(update.effective_message, "Entre em contato para doar para o nosso criador!"))
        except Unauthorized:
            update.effective_message.reply_text(tl(update.effective_message, "Entre em contato comigo primeiro para obter informações sobre doações."))

def memory_limit(percentage: float):
    if platform.system() != "Linux":
        print('Funciona apenas no Linux!')
        return
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    resource.setrlimit(resource.RLIMIT_AS, (int(get_memory() * 1024 * percentage), hard))

def get_memory():
    with open('/proc/meminfo', 'r') as mem:
        free_memory = 0
        for i in mem:
            sline = i.split()
            if str(sline[0]) in ('MemFree:', 'Buffers:', 'Cached:'):
                free_memory += int(sline[1])
    return free_memory

def memory(percentage=0.5):
    def decorator(function):
        def wrapper(*args, **kwargs):
            memory_limit(percentage)
            try:
                function(*args, **kwargs)
            except MemoryError:
                mem = get_memory() / 1024 /1024
                print('Remain: %.2f GB' % mem)
                sys.stderr.write('\n\nERRO: Exceção de Memória\n')
                sys.exit(1)
        return wrapper
    return decorator


@memory(percentage=0.8)
def main():
    test_handler = CommandHandler("teste", test)
    start_handler = CommandHandler("Iniciar", start, pass_args=True)

    help_handler = CommandHandler("Ajuda", get_help)
    help_callback_handler = CallbackQueryHandler(help_button, pattern=r"help_")

    settings_handler = CommandHandler("Configurações", get_settings)
    settings_callback_handler = CallbackQueryHandler(settings_button, pattern=r"stngs_")

    donate_handler = CommandHandler("Doar", donate)
    M_CONNECT_BTN_HANDLER = CallbackQueryHandler(m_connect_button, pattern=r"main_connect")
    M_SETLANG_BTN_HANDLER = CallbackQueryHandler(m_change_langs, pattern=r"main_setlang")

    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(settings_handler)
    dispatcher.add_handler(help_callback_handler)
    dispatcher.add_handler(settings_callback_handler)
    dispatcher.add_handler(donate_handler)
    dispatcher.add_handler(M_CONNECT_BTN_HANDLER)
    dispatcher.add_handler(M_SETLANG_BTN_HANDLER)

    if WEBHOOK:
        LOGGER.info("Using webhooks.")
        updater.start_webhook(listen="127.0.0.1",
                              port=PORT,
                              url_path=TOKEN)

        if CERT_PATH:
            updater.bot.set_webhook(url=URL + TOKEN,
                                    certificate=open(CERT_PATH, 'rb'))
        else:
            updater.bot.set_webhook(url=URL + TOKEN)

    else:
        LOGGER.info("Usando sondagens longas.")
        updater.start_polling(timeout=15, read_latency=4)

    updater.idle()

if __name__ == '__main__':
    LOGGER.info("Módulos inicializados com sucesso!: " + str(ALL_MODULES))
    main()
