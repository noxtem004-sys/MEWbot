from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import log_action
from states import TransferState

router = Router()


def back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="بازگشت", callback_data="back_to_menu")
    return kb.as_markup()


def _is_admin(user_id: int, config) -> bool:
    return user_id == int(config.get("ADMIN_ID") or 0)


@router.callback_query(F.data == "transfer")
async def transfer_start(cb: CallbackQuery, state: FSMContext, config):
    if not _is_admin(cb.from_user.id, config):
        return
    await state.set_state(TransferState.waiting_for_number)
    await cb.message.edit_text("عدد انتقال را بفرست (مثلاً 14):", reply_markup=back_kb())
    await cb.answer()
    await log_action(cb.from_user.id, "transfer_flow", "Waiting for number")


@router.message(TransferState.waiting_for_number)
async def transfer_number(message: Message, state: FSMContext, config, user_client):
    if not _is_admin(message.from_user.id, config):
        return

    text = (message.text or "").strip()
    try:
        number = int(text)
    except ValueError:
        await message.answer("عدد معتبر نیست. فقط عدد بفرست.", reply_markup=back_kb())
        return

    await state.clear()
    ok = await user_client.send_transfer_meow(number)
    await log_action(message.from_user.id, "transfer_meow", f"number={number}, ok={ok}")
    await message.answer("انجام شد." if ok else "خطا در ارسال.", reply_markup=back_kb())


@router.callback_query(F.data == "meow_now")
async def meow_now(cb: CallbackQuery, config, user_client):
    if not _is_admin(cb.from_user.id, config):
        return
    ok = await user_client.send_auto_meow()
    await log_action(cb.from_user.id, "meow_now", f"ok={ok}")
    await cb.answer("ارسال شد" if ok else "خطا", show_alert=False)


@router.callback_query(F.data == "cat_now")
async def cat_now(cb: CallbackQuery, config, user_client):
    if not _is_admin(cb.from_user.id, config):
        return
    ok = await user_client.collect_cat_and_deposit_to_bank()
    await log_action(cb.from_user.id, "cat_now", f"ok={ok}")
    await cb.answer("انجام شد" if ok else "خطا", show_alert=False)


@router.callback_query(F.data == "fish_now")
async def fish_now(cb: CallbackQuery, config, user_client):
    if not _is_admin(cb.from_user.id, config):
        return
    ok = await user_client.do_fish_feed()
    await log_action(cb.from_user.id, "fish_now", f"ok={ok}")
    await cb.answer("انجام شد" if ok else "خطا", show_alert=False)
