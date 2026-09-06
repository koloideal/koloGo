from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from seatbot.application.services.ride import RideService

from .user_dialogs.states import AdminPanelSG

admin_router = Router()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, dialog_manager: DialogManager):
    await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)


async def _edit_log_message(callback: CallbackQuery, suffix: str) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n{suffix}")
    except TelegramBadRequest:
        pass


@admin_router.callback_query(F.data.startswith("adm_approve:"))
async def cb_approve_booking(
    callback: CallbackQuery,
    ride_service: FromDishka[RideService],
):
    booking_id = int((callback.data or "").split(":", 1)[1])
    booking = await ride_service.approve_booking(booking_id)
    if booking:
        await _edit_log_message(callback, "✅ Одобрена")
        await callback.answer("Бронь одобрена", show_alert=True)
    else:
        await callback.answer("Бронь уже обработана или не найдена", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm_reject:"))
async def cb_reject_booking(
    callback: CallbackQuery,
    ride_service: FromDishka[RideService],
):
    booking_id = int((callback.data or "").split(":", 1)[1])
    booking = await ride_service.reject_booking(booking_id)
    if booking:
        await _edit_log_message(callback, "❌ Отклонена, возврат выполнен")
        await callback.answer("Бронь отклонена, возврат выполнен", show_alert=True)
    else:
        await callback.answer("Бронь уже обработана или не найдена", show_alert=True)
