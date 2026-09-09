from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (Button, Cancel, Group, ScrollingGroup, Select,
                                        SwitchTo)
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.application.services.statistics import StatisticsService
from seatbot.domain.exceptions import NoFreeSeatsError
from seatbot.domain.schemas import BookingStatus, RideStatus
from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import (BOOKING_STATUS_RU, MessageBuilder,
                                                  fmt_amount, user_display)
from seatbot.infrastructure.time import LocalClock

from ..user_dialogs.states import RideBookingsSG

_STATUS_EMOJI = {
    BookingStatus.PENDING: "⏳",
    BookingStatus.APPROVED: "✅",
    BookingStatus.REJECTED: "❌",
    BookingStatus.CANCELLED: "🚫",
    BookingStatus.COMPLETED: "🏁",
    BookingStatus.NO_SHOW: "🙅",
}


@inject
async def get_ride_bookings(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    rides_dao: FromDishka[RidesDAO],
    messages: FromDishka[MessageBuilder],
    **_kwargs,
):
    if "ride_id" not in dialog_manager.dialog_data:
        start_data = dialog_manager.start_data
        if isinstance(start_data, dict):
            dialog_manager.dialog_data["ride_id"] = start_data["ride_id"]
    ride_id: int = dialog_manager.dialog_data.get("ride_id", 0)
    if not ride_id:
        return {
            "has_bookings": False,
            "empty_text": "🚫 Нет броней.",
            "back_btn": "⬅️ Назад",
            "can_add_passenger": False,
        }
    dialog_manager.dialog_data["ride_id"] = ride_id
    ride = await rides_dao.get_by_id(ride_id)
    can_add = ride is not None and ride.status == RideStatus.OPEN
    bookings = await bookings_dao.list_for_ride(ride_id, only_active=True)
    if not bookings:
        return {
            "has_bookings": False,
            "empty_text": "🚫 На эту поездку нет броней.",
            "back_btn": "⬅️ Назад",
            "can_add_passenger": can_add,
        }
    items = []
    for b in bookings:
        user = await users_dao.get_by_id(b.user_id)
        emoji = _STATUS_EMOJI.get(b.status, "•")
        vip = " ⭐" if (user and user.is_vip) else ""
        uname = user_display(user.username, user.first_name, b.user_id) if user else f"id:{b.user_id}"
        status_ru = BOOKING_STATUS_RU.get(b.status, b.status.value)
        pay = (
            messages.payment_short(
                b.paid_amount,
                float(ride.price),
                ride.is_free or bool(user and user.is_vip),
            )
            if ride
            else fmt_amount(b.paid_amount)
        )
        items.append(
            {
                "booking_id": b.booking_id,
                "title": f"{emoji} #{b.booking_id} • {uname}{vip} • {status_ru} • {pay}",
            }
        )
    return {"has_bookings": True, "bookings": items, "back_btn": "⬅️ К поездке", "can_add_passenger": can_add, "has_approved": any(b.status == BookingStatus.APPROVED for b in bookings) if bookings else False}


@inject
async def get_booking_detail(
    dialog_manager: DialogManager,
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    rides_dao: FromDishka[RidesDAO],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    **_kwargs,
):
    booking_id: int = dialog_manager.dialog_data["booking_id"]
    booking = await bookings_dao.get_by_id(booking_id)
    if not booking:
        return {"booking_text": "🚫 Бронь не найдена", "back_btn": "⬅️ Назад"}
    user = await users_dao.get_by_id(booking.user_id)
    ride = await rides_dao.get_by_id(booking.ride_id)
    uname = user_display(user.username, user.first_name, booking.user_id) if user else f"id:{booking.user_id}"
    vip = " ⭐VIP" if (user and user.is_vip) else ""
    text = f"<b>Бронь #{booking.booking_id}</b>\n\n👤 Пользователь: {uname}{vip} ({booking.user_id})\n"
    if ride:
        text += f"🚗 Поездка: {clock.fmt(ride.departure_at, '%d.%m.%Y %H:%M')}\n"
        text += (
            messages.payment_full(
                booking.paid_amount,
                float(ride.price),
                ride.is_free or bool(user and user.is_vip),
            )
            + "\n"
        )
    status_ru = BOOKING_STATUS_RU.get(booking.status, booking.status.value)
    text += f"📋 Статус: {_STATUS_EMOJI.get(booking.status, '•')} {status_ru.capitalize()}"
    is_pending = booking.status == BookingStatus.PENDING
    is_approved = booking.status == BookingStatus.APPROVED
    is_active = booking.status in (BookingStatus.PENDING, BookingStatus.APPROVED)
    return {
        "booking_text": text,
        "is_pending": is_pending,
        "is_approved": is_approved,
        "is_active": is_active,
        "approve_btn": "✅ Одобрить",
        "reject_btn": "❌ Отклонить",
        "noshow_btn": "🙅 Неявка",
        "kick_btn": "🚫 Кикнуть",
        "back_btn": "⬅️ К броням",
    }


async def on_booking_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["booking_id"] = int(item_id)
    await manager.next()


@inject
async def on_approve(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.approve_booking(booking_id)
    await callback.answer("Одобрено", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


@inject
async def on_reject(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.reject_booking(booking_id)
    await callback.answer("Отклонено, возврат выполнен", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


@inject
async def on_noshow(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    await ride_service.mark_no_show(booking_id)
    await callback.answer("Отмечена неявка", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


async def on_kick(callback: CallbackQuery, button: Button, manager: DialogManager):
    await manager.switch_to(RideBookingsSG.kick_reason)


@inject
async def on_kick_reason_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    booking_id: int = manager.dialog_data["booking_id"]
    reason = (message.text or "").strip()[:512]
    booking = await ride_service.kick_booking(booking_id, reason)
    if not booking:
        await message.answer("❌ Не удалось кикнуть. Бронь уже не активна.")
        return
    await message.answer("✅ Пассажир кикнут, уведомлён.")
    await manager.switch_to(RideBookingsSG.bookings_list)


async def on_broadcast_click(callback: CallbackQuery, button: Button, manager: DialogManager):
    await manager.switch_to(RideBookingsSG.broadcast_text)


async def on_broadcast_text_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    manager.dialog_data["broadcast_text"] = text
    await manager.switch_to(RideBookingsSG.broadcast_confirm)


async def get_broadcast_preview(dialog_manager: DialogManager, **_kwargs):
    text = dialog_manager.dialog_data.get("broadcast_text", "")
    return {"broadcast_text": text, "send_btn": "📢 Отправить", "back_btn": "⬅️ Назад"}


@inject
async def on_broadcast_send(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
    bookings_dao: FromDishka[BookingsDAO],
):
    ride_id: int = manager.dialog_data.get("ride_id", 0)
    text: str = manager.dialog_data.get("broadcast_text", "")
    if not ride_id or not text:
        await callback.answer("Ошибка данных", show_alert=True)
        await manager.switch_to(RideBookingsSG.bookings_list)
        return
    approved = await bookings_dao.list_for_ride_with_status(ride_id, {BookingStatus.APPROVED})
    sent = await ride_service.broadcast_ride(ride_id, text)
    await callback.answer(f"Отправлено {sent}/{len(approved)}", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


@inject
async def get_passengers_list(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    bookings_dao: FromDishka[BookingsDAO],
    config: FromDishka[Config],
    **_kwargs,
):
    ride_id: int = dialog_manager.dialog_data.get("ride_id", 0)
    if not ride_id:
        return {"has_users": False, "empty_text": "🚫 Поездка не найдена.", "back_btn": "⬅️ К броням"}
    stats = await statistics_service.all_users_stats(limit=100, exclude_user_id=config.bot.creator_id)
    if not stats:
        return {"has_users": False, "empty_text": "🚫 Нет пользователей.", "back_btn": "⬅️ К броням"}
    existing = await bookings_dao.list_for_ride(ride_id, only_active=True)
    existing_ids = {b.user_id for b in existing}
    items = []
    for s in stats:
        if s.user_id in existing_ids:
            continue
        badges = []
        if s.is_vip:
            badges.append("⭐")
        if s.is_banned:
            badges.append("🚫")
        badge_str = " " + "".join(badges) if badges else ""
        uname = user_display(s.username, s.first_name, s.user_id)
        items.append(
            {
                "user_id": s.user_id,
                "title": f"{uname}{badge_str} • {fmt_amount(s.balance)} BYN",
            }
        )
    if not items:
        return {"has_users": False, "empty_text": "🚫 Все клиенты уже в поездке.", "back_btn": "⬅️ К броням"}
    return {"has_users": True, "users": items, "back_btn": "⬅️ К броням"}


async def on_passenger_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    ride_id: int = manager.dialog_data.get("ride_id", 0)
    user_id = int(item_id)
    container = manager.middleware_data["dishka_container"]
    ride_service: RideService = await container.get(RideService)
    rides_dao: RidesDAO = await container.get(RidesDAO)
    users_dao: UsersDAO = await container.get(UsersDAO)
    try:
        booking = await ride_service.add_passenger(ride_id, user_id)
    except NoFreeSeatsError:
        await callback.answer("Нет свободных мест", show_alert=True)
        return
    if not booking:
        await callback.answer("Не удалось добавить", show_alert=True)
        await manager.switch_to(RideBookingsSG.bookings_list)
        return
    ride = await rides_dao.get_by_id(ride_id)
    user = await users_dao.get_by_id(user_id)
    messages: MessageBuilder = await container.get(MessageBuilder)
    pay = messages.payment_short(
        booking.paid_amount,
        float(ride.price) if ride else booking.paid_amount,
        bool(ride and (ride.is_free or (user and user.is_vip))),
    )
    await callback.answer(f"Клиент добавлен ({pay}), уведомление отправлено", show_alert=True)
    await manager.switch_to(RideBookingsSG.bookings_list)


ride_detail_dialog = Dialog(
    Window(
        Const("📋 <b>Брони на поездку</b>"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="bookings_sel",
                item_id_getter=lambda item: str(item["booking_id"]),
                items="bookings",
                on_click=on_booking_selected,
                when="has_bookings",
            ),
            width=1,
            height=8,
            id="bookings_scroll",
        ),
        Format("{empty_text}", when="not has_bookings"),
        SwitchTo(
            Const("➕ Добавить клиента"),
            id="add_passenger",
            state=RideBookingsSG.add_passenger,
            when="can_add_passenger",
        ),
        SwitchTo(
            Const("📢 Рассылка пассажирам"),
            id="broadcast",
            state=RideBookingsSG.broadcast_text,
            when="has_approved",
        ),
        Cancel(Format("{back_btn}")),
        state=RideBookingsSG.bookings_list,
        getter=get_ride_bookings,
    ),
    Window(
        Format("{booking_text}"),
        Group(
            Button(Format("{approve_btn}"), id="approve", on_click=on_approve, when="is_pending"),
            Button(Format("{reject_btn}"), id="reject", on_click=on_reject, when="is_pending"),
            Button(Format("{noshow_btn}"), id="noshow", on_click=on_noshow, when="is_approved"),
            Button(Format("{kick_btn}"), id="kick", on_click=on_kick, when="is_active"),
            width=2,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RideBookingsSG.bookings_list),
        state=RideBookingsSG.booking_detail,
        getter=get_booking_detail,
    ),
    Window(
        Const("➕ <b>Добавить клиента в поездку</b>\n\nВыберите клиента:"),
        ScrollingGroup(
            Select(
                Format("{item[title]}"),
                id="users_sel",
                item_id_getter=lambda item: str(item["user_id"]),
                items="users",
                on_click=on_passenger_selected,
                when="has_users",
            ),
            width=1,
            height=8,
            id="users_scroll",
        ),
        Format("{empty_text}", when="not has_users"),
        SwitchTo(Format("{back_btn}"), id="back", state=RideBookingsSG.bookings_list),
        state=RideBookingsSG.add_passenger,
        getter=get_passengers_list,
    ),
    Window(
        Const(
            "🚫 <b>Кикнуть пассажира</b>\n\n"
            "Введите причину (или «-» чтобы без причины):\n"
            "Пассажир будет уведомлён, бронь отменена."
        ),
        MessageInput(on_kick_reason_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideBookingsSG.booking_detail),
        state=RideBookingsSG.kick_reason,
        getter=get_booking_detail,
    ),
    Window(
        Const(
            "📢 <b>Рассылка пассажирам поездки</b>\n\n"
            "Отправьте текст сообщения.\n"
            "Оно будет отправлено всем одобренным пассажирам."
        ),
        MessageInput(on_broadcast_text_input),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideBookingsSG.bookings_list),
        state=RideBookingsSG.broadcast_text,
    ),
    Window(
        Const("📋 <b>Предпросмотр рассылки</b>\n\nСообщение:"),
        Format("{broadcast_text}"),
        Button(Format("{send_btn}"), id="send_broadcast", on_click=on_broadcast_send),
        SwitchTo(Format("{back_btn}"), id="back", state=RideBookingsSG.broadcast_text),
        state=RideBookingsSG.broadcast_confirm,
        getter=get_broadcast_preview,
    ),
)
