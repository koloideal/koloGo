from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message)
from aiogram_dialog import DialogManager, StartMode
from dishka import FromDishka

from seatbot.application.services.ride import RideService
from seatbot.application.services.tracking import TrackingService
from seatbot.infrastructure.notifications import fmt_amount

from .user_dialogs.states import AdminPanelSG, RidesMgmtSG

admin_router = Router()


@admin_router.message(Command("admin"))
async def cmd_admin(message: Message, dialog_manager: DialogManager) -> None:
    await dialog_manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)


async def _edit_log_message(callback: CallbackQuery, suffix: str, ride_id: int) -> None:
    if not isinstance(callback.message, Message):
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚗 К поездке", callback_data=f"adm_ride:{ride_id}")]]
    )
    try:
        await callback.message.edit_text(f"{callback.message.html_text}\n\n{suffix}", reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@admin_router.callback_query(F.data.startswith("adm_approve:"))
async def cb_approve_booking(
    callback: CallbackQuery,
    ride_service: FromDishka[RideService],
) -> None:
    booking_id = int((callback.data or "").split(":", 1)[1])
    booking = await ride_service.approve_booking(booking_id)
    if booking:
        await _edit_log_message(callback, "✅ Одобрена", booking.ride_id)
        await callback.answer("Бронь одобрена", show_alert=True)
    else:
        await callback.answer("Бронь уже обработана или не найдена", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm_reject:"))
async def cb_reject_booking(
    callback: CallbackQuery,
    ride_service: FromDishka[RideService],
) -> None:
    booking_id = int((callback.data or "").split(":", 1)[1])
    booking = await ride_service.reject_booking(booking_id)
    if booking:
        if booking.paid_amount > 0:
            suffix = f"❌ Отклонена, возврат {fmt_amount(booking.paid_amount)} BYN выполнен"
        else:
            suffix = "❌ Отклонена, списаний не было"
        await _edit_log_message(callback, suffix, booking.ride_id)
        await callback.answer(f"Бронь {suffix.lower()}", show_alert=True)
    else:
        await callback.answer("Бронь уже обработана или не найдена", show_alert=True)


@admin_router.callback_query(F.data.startswith("adm_ride:"))
async def cb_open_ride(callback: CallbackQuery, dialog_manager: DialogManager) -> None:
    ride_id = int((callback.data or "").split(":", 1)[1])
    await callback.answer()
    await dialog_manager.start(RidesMgmtSG.ride_detail, data={"ride_id": ride_id})


@admin_router.message(F.location, F.location.live_period)
async def msg_live_location(
    message: Message,
    tracking_service: FromDishka[TrackingService],
) -> None:
    loc = message.location
    if loc is None or message.chat is None:
        return
    ride = await tracking_service.handle_live_start(
        message.chat.id, message.message_id, loc.latitude, loc.longitude
    )
    if ride is None:
        await message.answer(
            "ℹ️ Live-гео получено, но сейчас нет поездки, ожидающей старта.\n"
            "Нажмите «🚀 Старт поездки» в карточке поездки."
        )
        return
    await message.answer(
        f"🚙 <b>Трекинг запущен!</b>\n\n"
        f"Поездка #{ride.ride_id} — поехали.\n"
        "Бот завершит поездку автоматически по прибытии в точку назначения."
    )


@admin_router.edited_message(F.location)
async def msg_live_location_update(
    message: Message,
    tracking_service: FromDishka[TrackingService],
) -> None:
    loc = message.location
    if loc is None or message.chat is None:
        return
    await tracking_service.handle_update(
        chat_id=message.chat.id,
        message_id=message.message_id,
        lat=loc.latitude,
        lon=loc.longitude,
        live_period=loc.live_period,
        horizontal_accuracy=loc.horizontal_accuracy,
    )
