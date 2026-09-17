"""
Telegram License Management Bot

Admin-only bot for managing licenses via Telegram.
Provides a complete interface for license CRUD operations.

Security:
- Telegram User ID based authorization
- All commands verify admin access
- Callback data validation to prevent manipulation
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from license_database import LicenseDatabase, LicenseStatus
from license_server import LicenseServer

logger = logging.getLogger(__name__)

# ==================== FSM STATES ====================

class CreateLicenseState(StatesGroup):
    waiting_for_duration = State()

class SearchLicenseState(StatesGroup):
    waiting_for_query = State()

class ExtendLicenseState(StatesGroup):
    license_id = State()
    waiting_for_duration = State()

# ==================== PREDEFINED PLANS ====================

PREDEFINED_PLANS = [
    {"label": "1 Day", "duration_seconds": 86400, "plan_name": "1_day"},
    {"label": "3 Days", "duration_seconds": 259200, "plan_name": "3_days"},
    {"label": "7 Days", "duration_seconds": 604800, "plan_name": "7_days"},
    {"label": "30 Days", "duration_seconds": 2592000, "plan_name": "30_days"},
    {"label": "90 Days", "duration_seconds": 7776000, "plan_name": "90_days"},
    {"label": "180 Days", "duration_seconds": 15552000, "plan_name": "180_days"},
    {"label": "365 Days", "duration_seconds": 31536000, "plan_name": "365_days"},
]

# ==================== HELPER FUNCTIONS ====================

def format_time_remaining(seconds: int) -> str:
    """Format seconds into human-readable time"""
    if seconds <= 0:
        return "Expired"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    
    return " ".join(parts) if parts else "< 1m"

def format_license_info(license_data: Dict[str, Any], activations: Optional[List[Dict[str, Any]]] = None) -> str:
    """Format license information for display"""
    status = license_data["status"]
    status_emoji = {
        "PENDING": "⏳",
        "ACTIVE": "✅",
        "EXPIRED": "⏰",
        "REVOKED": "❌",
        "BLOCKED": "🚫"
    }.get(status, "❓")
    
    info = f"<b>License #{license_data['id']}</b>\n\n"
    info += f"Status: {status_emoji} <b>{status}</b>\n"
    info += f"Plan: <code>{license_data['plan']}</code>\n"
    info += f"Duration: {format_time_remaining(license_data['duration_seconds'])}\n\n"
    
    info += f"Created: <code>{license_data['created_at']}</code>\n"
    
    if license_data['activated_at']:
        info += f"Activated: <code>{license_data['activated_at']}</code>\n"
    
    if license_data['expires_at']:
        info += f"Expires: <code>{license_data['expires_at']}</code>\n"
        
        # Calculate remaining time
        if license_data['expires_at_utc']:
            now_ts = int(datetime.now(timezone.utc).timestamp())
            remaining = license_data['expires_at_utc'] - now_ts
            if remaining > 0:
                info += f"Remaining: <b>{format_time_remaining(remaining)}</b>\n"
    
    if license_data['revoked_at']:
        info += f"Revoked: <code>{license_data['revoked_at']}</code>\n"
    
    if license_data['blocked_at']:
        info += f"Blocked: <code>{license_data['blocked_at']}</code>\n"
    
    info += f"\nMax Devices: {license_data['max_devices']}\n"
    
    # Show active devices
    if activations:
        active_devices = [a for a in activations if not a['revoked_at']]
        info += f"Active Devices: {len(active_devices)}\n"
        
        if active_devices:
            info += "\n<b>Devices:</b>\n"
            for activation in active_devices:
                device_short = activation['device_id'][:12] + "..."
                info += f"  • <code>{device_short}</code>\n"
                info += f"    Last seen: {activation['last_seen_at']}\n"
    
    return info

def parse_duration_input(text: str) -> Optional[int]:
    """
    Parse duration input like "12 hours", "2 days", "45 days"
    Returns duration in seconds, or None if invalid
    """
    text = text.strip().lower()
    
    # Try to extract number and unit
    parts = text.split()
    if len(parts) != 2:
        return None
    
    try:
        value = int(parts[0])
    except ValueError:
        return None
    
    unit = parts[1]
    
    # Handle plural/singular
    unit = unit.rstrip('s')
    
    multipliers = {
        'second': 1,
        'minute': 60,
        'hour': 3600,
        'day': 86400,
        'week': 604800,
        'month': 2592000,  # 30 days
        'year': 31536000   # 365 days
    }
    
    if unit in multipliers:
        return value * multipliers[unit]
    
    return None

# ==================== LICENSE BOT ====================

class LicenseBot:
    """Telegram bot for license management"""
    
    def __init__(
        self,
        bot_token: str,
        admin_ids: List[int],
        license_server: LicenseServer
    ):
        self.bot_token = bot_token
        self.admin_ids = set(admin_ids)
        self.license_server = license_server
        self.db = license_server.db
        
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.router = Router()
        
        self._setup_handlers()
        self.dp.include_router(self.router)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is authorized admin"""
        return user_id in self.admin_ids
    
    async def send_unauthorized(self, message: Message):
        """Send unauthorized message"""
        await message.answer(
            "❌ <b>Unauthorized</b>\n\n"
            "This bot is for administrators only.",
            parse_mode="HTML"
        )
    
    def _setup_handlers(self):
        """Setup all command and callback handlers"""
        
        # Commands
        self.router.message(CommandStart())(self.cmd_start)
        self.router.message(Command("menu"))(self.cmd_menu)
        self.router.message(Command("stats"))(self.cmd_stats)
        self.router.message(Command("cancel"))(self.cmd_cancel)
        
        # Main menu callbacks
        self.router.callback_query(F.data == "main_menu")(self.show_main_menu)
        self.router.callback_query(F.data == "create_license")(self.create_license_menu)
        self.router.callback_query(F.data == "list_licenses")(self.list_licenses)
        self.router.callback_query(F.data == "search_license")(self.search_license_prompt)
        self.router.callback_query(F.data == "statistics")(self.show_statistics)
        
        # Create license callbacks
        self.router.callback_query(F.data.startswith("plan_"))(self.create_license_with_plan)
        self.router.callback_query(F.data == "plan_custom")(self.create_license_custom_prompt)
        
        # License info callbacks
        self.router.callback_query(F.data.startswith("info_"))(self.show_license_info)
        self.router.callback_query(F.data.startswith("extend_"))(self.extend_license_prompt)
        self.router.callback_query(F.data.startswith("revoke_"))(self.revoke_license)
        self.router.callback_query(F.data.startswith("block_"))(self.block_license)
        self.router.callback_query(F.data.startswith("unblock_"))(self.unblock_license)
        self.router.callback_query(F.data.startswith("reset_dev_"))(self.reset_device)
        self.router.callback_query(F.data.startswith("copy_key_"))(self.copy_license_key)
        
        # Extend license duration callbacks
        self.router.callback_query(F.data.startswith("extend_dur_"))(self.extend_license_with_duration)
        
        # Status filter callbacks
        self.router.callback_query(F.data.startswith("filter_"))(self.list_licenses_filtered)
        
        # FSM message handlers
        self.router.message(CreateLicenseState.waiting_for_duration)(self.create_license_custom_duration)
        self.router.message(SearchLicenseState.waiting_for_query)(self.search_license_execute)
        self.router.message(ExtendLicenseState.waiting_for_duration)(self.extend_license_custom_duration)
    
    # ==================== COMMAND HANDLERS ====================
    
    async def cmd_start(self, message: Message):
        """Handle /start command"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        await message.answer(
            "🔐 <b>License Management Bot</b>\n\n"
            "Welcome to the License Management System.\n"
            "Use /menu to access the main menu.",
            parse_mode="HTML"
        )
        
        await self.show_main_menu_keyboard(message)
    
    async def cmd_menu(self, message: Message):
        """Handle /menu command"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        await self.show_main_menu_keyboard(message)
    
    async def cmd_stats(self, message: Message):
        """Handle /stats command"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        stats = await self.db.get_statistics()
        
        text = "📊 <b>License Statistics</b>\n\n"
        text += f"Total Licenses: <b>{stats['total_licenses']}</b>\n"
        text += f"Active Devices: <b>{stats['active_devices']}</b>\n"
        text += f"Activations (24h): <b>{stats['activations_24h']}</b>\n\n"
        
        text += "<b>By Status:</b>\n"
        for status, count in stats.get('by_status', {}).items():
            emoji = {
                "PENDING": "⏳",
                "ACTIVE": "✅",
                "EXPIRED": "⏰",
                "REVOKED": "❌",
                "BLOCKED": "🚫"
            }.get(status, "❓")
            text += f"  {emoji} {status}: {count}\n"
        
        await message.answer(text, parse_mode="HTML")
    
    async def cmd_cancel(self, message: Message, state: FSMContext):
        """Handle /cancel command"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        await state.clear()
        await message.answer("❌ Operation cancelled.")
        await self.show_main_menu_keyboard(message)
    
    # ==================== MAIN MENU ====================
    
    async def show_main_menu_keyboard(self, message: Message):
        """Show main menu with inline keyboard"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Create License", callback_data="create_license")],
            [InlineKeyboardButton(text="📋 License List", callback_data="list_licenses")],
            [InlineKeyboardButton(text="🔍 Search License", callback_data="search_license")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="statistics")],
        ])
        
        await message.answer(
            "🔐 <b>License Management</b>\n\n"
            "Select an option:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    async def show_main_menu(self, callback: CallbackQuery):
        """Show main menu (callback version)"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Create License", callback_data="create_license")],
            [InlineKeyboardButton(text="📋 License List", callback_data="list_licenses")],
            [InlineKeyboardButton(text="🔍 Search License", callback_data="search_license")],
            [InlineKeyboardButton(text="📊 Statistics", callback_data="statistics")],
        ])
        
        await callback.message.edit_text(
            "🔐 <b>License Management</b>\n\n"
            "Select an option:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
    
    # ==================== CREATE LICENSE ====================
    
    async def create_license_menu(self, callback: CallbackQuery):
        """Show create license menu with predefined plans"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        keyboard_buttons = []
        for plan in PREDEFINED_PLANS:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"📅 {plan['label']}",
                    callback_data=f"plan_{plan['plan_name']}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="✏️ Custom Duration", callback_data="plan_custom")
        ])
        keyboard_buttons.append([
            InlineKeyboardButton(text="« Back", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(
            "➕ <b>Create License</b>\n\n"
            "Select a plan:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
    
    async def create_license_with_plan(self, callback: CallbackQuery):
        """Create license with predefined plan"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        # Extract plan name from callback data
        plan_name = callback.data.replace("plan_", "")
        
        # Find the plan
        plan = next((p for p in PREDEFINED_PLANS if p['plan_name'] == plan_name), None)
        if not plan:
            await callback.answer("Invalid plan", show_alert=True)
            return
        
        # Generate license key
        license_key = self.license_server.generate_license_key()
        
        # Create license in database
        license_id = await self.db.create_license(
            key=license_key,
            plan=plan['label'],
            duration_seconds=plan['duration_seconds'],
            max_devices=1
        )
        
        await self.db.log_action(
            action="LICENSE_CREATED_BY_ADMIN",
            license_id=license_id,
            admin_id=callback.from_user.id,
            details=f"Plan: {plan['label']}"
        )
        
        # Show license info
        text = (
            "✅ <b>License Created</b>\n\n"
            f"Plan: <b>{plan['label']}</b>\n"
            f"Status: ⏳ <b>PENDING</b>\n"
            f"License ID: <code>{license_id}</code>\n\n"
            f"<b>License Key:</b>\n"
            f"<code>{license_key}</code>\n\n"
            "<i>The timer starts when the license is first activated.</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Key", callback_data=f"copy_key_{license_id}")],
            [InlineKeyboardButton(text="ℹ️ License Info", callback_data=f"info_{license_id}")],
            [InlineKeyboardButton(text="« Back to Menu", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer("License created successfully! ✅")
    
    async def create_license_custom_prompt(self, callback: CallbackQuery, state: FSMContext):
        """Prompt for custom license duration"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        await callback.message.edit_text(
            "✏️ <b>Custom Duration</b>\n\n"
            "Enter the license duration:\n\n"
            "Examples:\n"
            "  • <code>12 hours</code>\n"
            "  • <code>2 days</code>\n"
            "  • <code>15 days</code>\n"
            "  • <code>45 days</code>\n"
            "  • <code>400 days</code>\n\n"
            "Use /cancel to abort.",
            parse_mode="HTML"
        )
        await state.set_state(CreateLicenseState.waiting_for_duration)
        await callback.answer()
    
    async def create_license_custom_duration(self, message: Message, state: FSMContext):
        """Handle custom duration input"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        duration_seconds = parse_duration_input(message.text)
        
        if duration_seconds is None:
            await message.answer(
                "❌ Invalid duration format.\n\n"
                "Please use format like:\n"
                "  • <code>12 hours</code>\n"
                "  • <code>2 days</code>\n"
                "  • <code>45 days</code>",
                parse_mode="HTML"
            )
            return
        
        # Generate license key
        license_key = self.license_server.generate_license_key()
        
        # Create license
        plan_name = f"Custom ({format_time_remaining(duration_seconds)})"
        license_id = await self.db.create_license(
            key=license_key,
            plan=plan_name,
            duration_seconds=duration_seconds,
            max_devices=1
        )
        
        await self.db.log_action(
            action="LICENSE_CREATED_BY_ADMIN",
            license_id=license_id,
            admin_id=message.from_user.id,
            details=f"Custom plan: {plan_name}"
        )
        
        await state.clear()
        
        # Show license info
        text = (
            "✅ <b>License Created</b>\n\n"
            f"Plan: <b>{plan_name}</b>\n"
            f"Status: ⏳ <b>PENDING</b>\n"
            f"License ID: <code>{license_id}</code>\n\n"
            f"<b>License Key:</b>\n"
            f"<code>{license_key}</code>\n\n"
            "<i>The timer starts when the license is first activated.</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Key", callback_data=f"copy_key_{license_id}")],
            [InlineKeyboardButton(text="ℹ️ License Info", callback_data=f"info_{license_id}")],
            [InlineKeyboardButton(text="« Back to Menu", callback_data="main_menu")]
        ])
        
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    
    # ==================== LICENSE LIST ====================
    
    async def list_licenses(self, callback: CallbackQuery):
        """List all licenses"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        licenses = await self.db.search_licenses(limit=20)
        
        if not licenses:
            await callback.message.edit_text(
                "📋 <b>License List</b>\n\n"
                "No licenses found.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Back", callback_data="main_menu")]
                ])
            )
            await callback.answer()
            return
        
        text = "📋 <b>License List</b>\n\n"
        text += f"Showing {len(licenses)} most recent licenses:\n\n"
        
        keyboard_buttons = []
        
        # Add filter buttons
        filter_row = [
            InlineKeyboardButton(text="All", callback_data="filter_all"),
            InlineKeyboardButton(text="Active", callback_data="filter_ACTIVE"),
            InlineKeyboardButton(text="Pending", callback_data="filter_PENDING"),
        ]
        keyboard_buttons.append(filter_row)
        
        for lic in licenses:
            status_emoji = {
                "PENDING": "⏳",
                "ACTIVE": "✅",
                "EXPIRED": "⏰",
                "REVOKED": "❌",
                "BLOCKED": "🚫"
            }.get(lic['status'], "❓")
            
            button_text = f"{status_emoji} #{lic['id']} - {lic['plan']}"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"info_{lic['id']}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="« Back", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    
    async def list_licenses_filtered(self, callback: CallbackQuery):
        """List licenses with status filter"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        filter_status = callback.data.replace("filter_", "")
        
        if filter_status == "all":
            licenses = await self.db.search_licenses(limit=20)
            filter_label = "All"
        else:
            licenses = await self.db.search_licenses(status=filter_status, limit=20)
            filter_label = filter_status
        
        if not licenses:
            await callback.answer(f"No {filter_label} licenses found", show_alert=True)
            return
        
        text = f"📋 <b>License List - {filter_label}</b>\n\n"
        text += f"Showing {len(licenses)} licenses:\n\n"
        
        keyboard_buttons = []
        
        # Add filter buttons
        filter_row = [
            InlineKeyboardButton(text="All", callback_data="filter_all"),
            InlineKeyboardButton(text="Active", callback_data="filter_ACTIVE"),
            InlineKeyboardButton(text="Pending", callback_data="filter_PENDING"),
        ]
        keyboard_buttons.append(filter_row)
        
        for lic in licenses:
            status_emoji = {
                "PENDING": "⏳",
                "ACTIVE": "✅",
                "EXPIRED": "⏰",
                "REVOKED": "❌",
                "BLOCKED": "🚫"
            }.get(lic['status'], "❓")
            
            button_text = f"{status_emoji} #{lic['id']} - {lic['plan']}"
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"info_{lic['id']}"
                )
            ])
        
        keyboard_buttons.append([
            InlineKeyboardButton(text="« Back", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    
    # ==================== SEARCH LICENSE ====================
    
    async def search_license_prompt(self, callback: CallbackQuery, state: FSMContext):
        """Prompt for search query"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        await callback.message.edit_text(
            "🔍 <b>Search License</b>\n\n"
            "Enter license ID or license key:\n\n"
            "Examples:\n"
            "  • <code>123</code> (license ID)\n"
            "  • <code>ABCD-1234-EFGH-5678</code> (license key)\n\n"
            "Use /cancel to abort.",
            parse_mode="HTML"
        )
        await state.set_state(SearchLicenseState.waiting_for_query)
        await callback.answer()
    
    async def search_license_execute(self, message: Message, state: FSMContext):
        """Execute license search"""
        if not self.is_admin(message.from_user.id):
            await self.send_unauthorized(message)
            return
        
        query = message.text.strip()
        
        # Try to search by ID first
        try:
            license_id = int(query)
            license_data = await self.db.get_license_by_id(license_id)
        except ValueError:
            # Search by key
            license_data = await self.db.get_license_by_key(query)
        
        await state.clear()
        
        if not license_data:
            await message.answer(
                "❌ License not found.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="« Back", callback_data="main_menu")]
                ])
            )
            return
        
        # Show license info
        activations = await self.db.get_license_activations(license_data['id'])
        text = format_license_info(license_data, activations)
        
        keyboard = self._build_license_actions_keyboard(license_data)
        
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    
    # ==================== LICENSE INFO ====================
    
    async def show_license_info(self, callback: CallbackQuery):
        """Show detailed license information"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("info_", ""))
        
        license_data = await self.db.get_license_by_id(license_id)
        if not license_data:
            await callback.answer("License not found", show_alert=True)
            return
        
        activations = await self.db.get_license_activations(license_id)
        text = format_license_info(license_data, activations)
        
        keyboard = self._build_license_actions_keyboard(license_data)
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    
    def _build_license_actions_keyboard(self, license_data: Dict[str, Any]) -> InlineKeyboardMarkup:
        """Build action buttons for license"""
        license_id = license_data['id']
        status = license_data['status']
        
        buttons = []
        
        # Extend button (for ACTIVE or EXPIRED licenses)
        if status in [LicenseStatus.ACTIVE.value, LicenseStatus.EXPIRED.value]:
            buttons.append([
                InlineKeyboardButton(text="⏱ Extend License", callback_data=f"extend_{license_id}")
            ])
        
        # Block/Unblock buttons
        if status == LicenseStatus.BLOCKED.value:
            buttons.append([
                InlineKeyboardButton(text="✅ Unblock License", callback_data=f"unblock_{license_id}")
            ])
        elif status not in [LicenseStatus.REVOKED.value]:
            buttons.append([
                InlineKeyboardButton(text="🚫 Block License", callback_data=f"block_{license_id}")
            ])
        
        # Revoke button (if not already revoked)
        if status != LicenseStatus.REVOKED.value:
            buttons.append([
                InlineKeyboardButton(text="❌ Revoke License", callback_data=f"revoke_{license_id}")
            ])
        
        # Reset device button
        buttons.append([
            InlineKeyboardButton(text="🔄 Reset Device", callback_data=f"reset_dev_{license_id}")
        ])
        
        # Back button
        buttons.append([
            InlineKeyboardButton(text="« Back to List", callback_data="list_licenses")
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # ==================== LICENSE ACTIONS ====================
    
    async def extend_license_prompt(self, callback: CallbackQuery, state: FSMContext):
        """Prompt for license extension duration"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("extend_", ""))
        
        # Show quick extension options
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="+ 1 Day", callback_data=f"extend_dur_{license_id}_86400")],
            [InlineKeyboardButton(text="+ 7 Days", callback_data=f"extend_dur_{license_id}_604800")],
            [InlineKeyboardButton(text="+ 30 Days", callback_data=f"extend_dur_{license_id}_2592000")],
            [InlineKeyboardButton(text="+ 90 Days", callback_data=f"extend_dur_{license_id}_7776000")],
            [InlineKeyboardButton(text="✏️ Custom", callback_data=f"extend_custom_{license_id}")],
            [InlineKeyboardButton(text="« Cancel", callback_data=f"info_{license_id}")]
        ])
        
        await callback.message.edit_text(
            "⏱ <b>Extend License</b>\n\n"
            "Select extension duration:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
    
    async def extend_license_with_duration(self, callback: CallbackQuery):
        """Extend license with specified duration"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        # Parse callback data: extend_dur_{license_id}_{seconds}
        parts = callback.data.split("_")
        license_id = int(parts[2])
        additional_seconds = int(parts[3])
        
        result = await self.db.extend_license(
            license_id=license_id,
            additional_seconds=additional_seconds,
            admin_id=callback.from_user.id
        )
        
        if result["success"]:
            await callback.answer(f"✅ License extended by {format_time_remaining(additional_seconds)}")
            # Refresh license info
            await self.show_license_info(callback)
        else:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
    
    async def revoke_license(self, callback: CallbackQuery):
        """Revoke a license"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("revoke_", ""))
        
        result = await self.db.revoke_license(
            license_id=license_id,
            admin_id=callback.from_user.id
        )
        
        if result["success"]:
            await callback.answer("✅ License revoked")
            await self.show_license_info(callback)
        else:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
    
    async def block_license(self, callback: CallbackQuery):
        """Block a license"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("block_", ""))
        
        result = await self.db.block_license(
            license_id=license_id,
            admin_id=callback.from_user.id
        )
        
        if result["success"]:
            await callback.answer("✅ License blocked")
            await self.show_license_info(callback)
        else:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
    
    async def unblock_license(self, callback: CallbackQuery):
        """Unblock a license"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("unblock_", ""))
        
        result = await self.db.unblock_license(
            license_id=license_id,
            admin_id=callback.from_user.id
        )
        
        if result["success"]:
            await callback.answer("✅ License unblocked")
            await self.show_license_info(callback)
        else:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
    
    async def reset_device(self, callback: CallbackQuery):
        """Reset device binding"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        license_id = int(callback.data.replace("reset_dev_", ""))
        
        result = await self.db.reset_device(
            license_id=license_id,
            admin_id=callback.from_user.id
        )
        
        if result["success"]:
            await callback.answer("✅ Device binding reset")
            await self.show_license_info(callback)
        else:
            await callback.answer(f"❌ {result['message']}", show_alert=True)
    
    async def copy_license_key(self, callback: CallbackQuery):
        """Show license key for copying"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        await callback.answer(
            "⚠️ License keys are hashed and cannot be retrieved.\n"
            "You can only copy the key when first creating a license.",
            show_alert=True
        )
    
    # ==================== STATISTICS ====================
    
    async def show_statistics(self, callback: CallbackQuery):
        """Show license statistics"""
        if not self.is_admin(callback.from_user.id):
            await callback.answer("Unauthorized", show_alert=True)
            return
        
        stats = await self.db.get_statistics()
        
        text = "📊 <b>License Statistics</b>\n\n"
        text += f"Total Licenses: <b>{stats['total_licenses']}</b>\n"
        text += f"Active Devices: <b>{stats['active_devices']}</b>\n"
        text += f"Activations (24h): <b>{stats['activations_24h']}</b>\n\n"
        
        text += "<b>By Status:</b>\n"
        for status, count in stats.get('by_status', {}).items():
            emoji = {
                "PENDING": "⏳",
                "ACTIVE": "✅",
                "EXPIRED": "⏰",
                "REVOKED": "❌",
                "BLOCKED": "🚫"
            }.get(status, "❓")
            text += f"  {emoji} {status}: {count}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="statistics")],
            [InlineKeyboardButton(text="« Back", callback_data="main_menu")]
        ])
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()
    
    # ==================== BOT LIFECYCLE ====================
    
    async def start(self):
        """Start the bot"""
        logger.info("Starting License Management Bot...")
        await self.dp.start_polling(self.bot)
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping License Management Bot...")
        await self.bot.session.close()


# ==================== STANDALONE BOT SCRIPT ====================

async def main():
    """Standalone bot entry point"""
    import os
    import sys
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get configuration from environment
    bot_token = os.environ.get('LICENSE_BOT_TOKEN')
    admin_ids_str = os.environ.get('LICENSE_BOT_ADMIN_IDS', '')
    server_secret_key = os.environ.get('LICENSE_SERVER_SECRET_KEY')
    
    if not bot_token:
        logger.error("LICENSE_BOT_TOKEN not set in environment")
        sys.exit(1)
    
    if not admin_ids_str:
        logger.error("LICENSE_BOT_ADMIN_IDS not set in environment")
        sys.exit(1)
    
    if not server_secret_key:
        logger.error("LICENSE_SERVER_SECRET_KEY not set in environment")
        sys.exit(1)
    
    # Parse admin IDs
    try:
        admin_ids = [int(id.strip()) for id in admin_ids_str.split(',')]
    except ValueError:
        logger.error("Invalid LICENSE_BOT_ADMIN_IDS format (should be comma-separated integers)")
        sys.exit(1)
    
    logger.info(f"Authorized admin IDs: {admin_ids}")
    
    # Create license server instance (for key generation)
    license_server = LicenseServer(secret_key=server_secret_key)
    await license_server.db.init_db()
    
    # Create and start bot
    bot = LicenseBot(
        bot_token=bot_token,
        admin_ids=admin_ids,
        license_server=license_server
    )
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bot.stop()


if __name__ == '__main__':
    asyncio.run(main())
