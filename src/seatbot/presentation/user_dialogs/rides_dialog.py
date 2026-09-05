
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, Cancel, Select, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.domain.exceptions import (AlreadyBookedError, InsufficientBalanceError,
                                       NoFreeSeatsError, RideNotBookableError,
                                       UserBannedError)
from seatbot.infrastructure.database.dao import BookingsDAO, RidesDAO, UsersDAO
from seatbot.infrastructure.notifications import MessageBuilder

from .states import MainMenuSG, RidesSG


@inject
async def get_rides_list(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    **_kwargs,
):
    rides = await rides_dao.list_upcoming_visible()
    if not rides:
        return {
            "has_rides": False,
            "empty_text": "🚫 Сейчас нет запланированных поездок. Загляни позже!",
            "back_btn": "⬅️ В меню",
        }
    items = []
    for rws in rides:
        price_str = "Бесплатно" if rws.ride.is_free else f"{rws.ride.price:.2f} BYN"
        items.append(
            {
                "ride_id": rws.ride.ride_id,
                "title": (
                    f"#{rws.ride.ride_id} • {rws.ride.departure_at.strftime('%d.%m %H:%M')} • "
                    f"{price_str} • {rws.free_seats} мест"
                ),
            }
        )
    return {
        "has_rides": True,
        "rides": items,
        "back_btn": "⬅️ В меню",
    }


@inject
async def get_ride_detail(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    bookings_dao: FromDishka[BookingsDAO],
    users_dao: FromDishka[UsersDAO],
    **_kwargs,
):
    ride_id: int = dialog_manager.dialog_data["ride_id"]
    rws = await rides_dao.get_with_stats(ride_id)
    if not rws:
        return {"ride_text": "🚫 Поездка не найдена", "back_btn": "⬅️ Назад"}

    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    existing = await bookings_dao.get_by_ride_and_user(ride_id, user_id)

    ride_text = MessageBuilder.ride_card(rws)
    can_book = (
        rws.free_seats > 0
        and rws.ride.status.value == "open"
        and not existing
        and (user is None or not user.is_banned)
    )

    return {
        "ride_text": ride_text,
        "ride_id": ride_id,
        "can_book": can_book,
        "already_booked": existing is not None,
        "book_btn": "🪑 Забронировать",
        "already_booked_text": "✅ Вы уже забронировали эту поездку",
        "no_seats_text": "🚫 Мест нет",
        "back_btn": "⬅️ К поездкам",
    }


async def on_ride_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    manager.dialog_data["ride_id"] = int(item_id)
    await manager.next()


@inject
async def on_book_click(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
    users_dao: FromDishka[UsersDAO],
):
    ride_id: int = manager.dialog_data["ride_id"]
    user_id = manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        await callback.answer("Сначала нажмите /start", show_alert=True)
        return
    try:
        booking = await ride_service.book_ride(ride_id, user)
    except InsufficientBalanceError as e:
        await callback.answer(
            f"Недостаточно депозита: нужно {e.required:.2f}, есть {e.available:.2f}",
            show_alert=True,
        )
        return
    except NoFreeSeatsError:
        await callback.answer("Мест больше нет", show_alert=True)
        return
    except AlreadyBookedError:
        await callback.answer("Вы уже забронировали эту поездку", show_alert=True)
        return
    except UserBannedError:
        await callback.answer("Вы в чёрном списке", show_alert=True)
        return
    except RideNotBookableError as e:
        await callback.answer(f"Нельзя забронировать: {e.reason}", show_alert=True)
        return

    status_text = "✅ Одобрено автоматически!" if booking.status.value == "approved" else "⏳ Ожидает подтверждения водителем."
    await callback.answer(f"Бронь #{booking.booking_id} создана. {status_text}", show_alert=True)
    await manager.start(MainMenuSG.main, mode=StartMode.RESET_STACK)


rides_dialog = Dialog(
    Window(
        Const("🚗 <b>Ближайшие поездки</b>\n\nВыберите поездку:"),
        Select(
            Format("{item[title]}"),
            id="rides_sel",
            item_id_getter=lambda item: str(item["ride_id"]),
            items="rides",
            on_click=on_ride_selected,
            when="has_rides",
        ),
        Format("{empty_text}", when="not has_rides"),
        Cancel(Format("{back_btn}")),
        state=RidesSG.list,
        getter=get_rides_list,
    ),
    Window(
        Format("{ride_text}"),
        Button(Format("{book_btn}"), id="book", on_click=on_book_click, when="can_book"),
        Format("{already_booked_text}", when="already_booked"),
        Format("{no_seats_text}", when="not can_book and not already_booked"),
        SwitchTo(Format("{back_btn}"), id="back", state=RidesSG.list),
        state=RidesSG.detail,
        getter=get_ride_detail,
    ),
)
