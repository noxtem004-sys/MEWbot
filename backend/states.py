"""
FSM States for the Telegram bot (aiogram only).
Used for the admin transfer flow.
"""

from aiogram.fsm.state import State, StatesGroup


class TransferState(StatesGroup):
    waiting_for_number: State = State()