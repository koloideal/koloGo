from datetime import UTC, datetime

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.infrastructure.config.models import Config

from ..user_dialogs.states import RideCreateSG, RidesMgmtSG


def _parse_datetime(text: str) -> datetime | None:
    """Парсит дату/время в форматах ДД.ММ.ГГГГ ЧЧ:ММ или ДД.ММ ЧЧ:ММ (текущий год)."""
    text = text.strip()
    now = datetime.now(UTC)
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)  # noqa: DTZ007 — tzinfo добавляется ниже  # noqa: DTZ007 — tzinfo добавляется ниже
            if dt.year == 1900:
                dt = dt.replace(year=now.year)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


async def on_departure_input(message: Message, widget: MessageInput, manager: DialogManager):
    dt = _parse_datetime(message.text or "")
    if not dt:
        await message.answer(
            "❌ Неверный формат. Используйте: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> или <code>ДД.ММ ЧЧ:ММ</code>"
        )
        return
    if dt <= datetime.now(UTC):
        await message.answer("❌ Дата должна быть в будущем.")
        return
    manager.dialog_data["departure_at"] = dt.isoformat()
    manager.dialog_data["departure_display"] = dt.strftime("%d.%m.%Y %H:%M")
    await manager.next()


async def on_price_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите неотрицательное число (например, <code>15.50</code> или <code>0</code> для бесплатной).")
        return
    manager.dialog_data["price"] = price
    await manager.next()


async def on_seats_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip()
    try:
        seats = int(text)
        if not 1 <= seats <= 10:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 10 (по умолчанию 4).")
        return
    manager.dialog_data["seats"] = seats
    await manager.next()


async def on_note_input(message: Message, widget: MessageInput, manager: DialogManager):
    manager.dialog_data["note"] = (message.text or "").strip()[:512] or None
    await manager.next()


async def on_note_skip(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["note"] = None
    await manager.next()


@inject
async def get_confirm_data(
    dialog_manager: DialogManager,
    config: FromDishka[Config],
    **_kwargs,
):
    departure_display = dialog_manager.dialog_data.get("departure_display", "—")
    price = dialog_manager.dialog_data.get("price", 0)
    seats = dialog_manager.dialog_data.get("seats", config.bot.seats_per_ride)
    auto_approve = dialog_manager.dialog_data.get("auto_approve", False)
    is_visible = dialog_manager.dialog_data.get("is_visible", True)
    note = dialog_manager.dialog_data.get("note")
    price_str = "Бесплатно" if price <= 0 else f"{price:.2f} BYN"
    text = (
        "📝 <b>Подтвердите создание поездки</b>\n\n"
        f"🕒 Отправление: <b>{departure_display}</b>\n"
        f"💰 Цена: <b>{price_str}</b>\n"
        f"🪑 Мест: <b>{seats}</b>\n"
        f"⚡ Авто-апрув: {'ВКЛ' if auto_approve else 'ВЫКЛ'}\n"
        f"👁️ Видимость: {'видна всем' if is_visible else 'скрытая'}\n"
        f"📝 Заметка: {note or '—'}"
    )
    return {"confirm_text": text, "create_btn": "✅ Создать", "back_btn": "⬅️ Назад"}


@inject
async def on_create(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
    config: FromDishka[Config],
):
    departure_str: str = manager.dialog_data["departure_at"]
    departure_at = datetime.fromisoformat(departure_str)
    price: float = manager.dialog_data["price"]
    seats: int = manager.dialog_data.get("seats", config.bot.seats_per_ride)
    auto_approve: bool = manager.dialog_data.get("auto_approve", False)
    is_visible: bool = manager.dialog_data.get("is_visible", True)
    note: str | None = manager.dialog_data.get("note")

    await ride_service.create_ride(
        departure_at=departure_at,
        price=price,
        seats_total=seats,
        auto_approve=auto_approve,
        note=note,
        is_visible=is_visible,
    )
    await callback.answer("✅ Поездка создана!", show_alert=True)
    await manager.start(RidesMgmtSG.rides_list, mode=StartMode.RESET_STACK)


async def on_auto_yes(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["auto_approve"] = True
    await manager.next()


async def on_auto_no(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["auto_approve"] = False
    await manager.next()


async def on_vis_yes(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["is_visible"] = True
    await manager.next()


async def on_vis_no(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["is_visible"] = False
    await manager.next()


ride_create_dialog = Dialog(
    Window(
        Const(
            "➕ <b>Создание поездки</b>\n\n"
            "Введите дату и время отправления.\n"
            "Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> или <code>ДД.ММ ЧЧ:ММ</code>\n\n"
            "Пример: <code>05.09 18:00</code>"
        ),
        MessageInput(on_departure_input),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.departure,
    ),
    Window(
        Const(
            "💰 <b>Цена поездки</b>\n\n"
            "Введите цену в BYN.\n"
            "Введите <code>0</code> для бесплатной поездки.\n\n"
            "Пример: <code>15.50</code>"
        ),
        MessageInput(on_price_input),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.price,
    ),
    Window(
        Const("🪑 <b>Количество мест</b>\n\nВведите число от 1 до 10 (по умолчанию 4)."),
        MessageInput(on_seats_input),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.seats,
    ),
    Window(
        Const("⚡ <b>Авто-одобрение?</b>\n\nОдобрять брони автоматически без вашего участия?"),
        Button(Const("✅ Да, авто-апрув"), id="auto_yes", on_click=on_auto_yes),
        Button(Const("❌ Нет, вручную"), id="auto_no", on_click=on_auto_no),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.auto_approve,
    ),
    Window(
        Const(
            "👁️ <b>Видимость</b>\n\n"
            "Сделать поездку видимой всем, или скрытой (видна только забронировавшим)?"
        ),
        Button(Const("👁️ Видна всем"), id="vis_yes", on_click=on_vis_yes),
        Button(Const("🔒 Скрытая"), id="vis_no", on_click=on_vis_no),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.visibility,
    ),
    Window(
        Const(
            "📝 <b>Заметка</b> (необязательно)\n\n"
            "Введите текст заметки или нажмите «Пропустить»."
        ),
        MessageInput(on_note_input),
        Button(Const("⏭️ Пропустить"), id="note_skip", on_click=on_note_skip),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.note,
    ),
    Window(
        Format("{confirm_text}"),
        Button(Format("{create_btn}"), id="create", on_click=on_create),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.departure),
        state=RideCreateSG.confirm,
        getter=get_confirm_data,
    ),
)
