from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import log_action

router = Router()


def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="ارسال انتقال میویی", callback_data="transfer")
    kb.button(text="ارسال میو الان", callback_data="meow_now")
    kb.button(text="گربه + برداشت + واریز الان", callback_data="cat_now")
    kb.button(text="ماهی (غذا دادن) الان", callback_data="fish_now")
    kb.adjust(1)
    return kb.as_markup()


@router.message(Command("start"))
async def start_cmd(message: Message, config):
    if message.from_user.id != int(config.get("ADMIN_ID") or 0):
        return
    await log_action(message.from_user.id, "admin_start", "Opened admin panel")
    await message.answer("پنل ادمین آماده است:", reply_markup=admin_menu())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, config):
    if cb.from_user.id != int(config.get("ADMIN_ID") or 0):
        return
    await cb.message.edit_text("پنل ادمین:", reply_markup=admin_menu())
    await cb.answer()
