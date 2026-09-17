"""
Admin keyboards module.
Contains inline keyboards for the admin panel.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """
    Returns the main admin panel inline keyboard.
    
    Returns:
        InlineKeyboardMarkup: Keyboard with admin actions.
    """
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="انتقال میویی",
                    callback_data="transfer_meow"
                )
            ]
        ]
    )
    return keyboard
