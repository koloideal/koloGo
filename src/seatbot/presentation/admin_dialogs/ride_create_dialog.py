from datetime import UTC, date, datetime, time

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.api.entities import ChatEvent
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (Button, Calendar, Cancel, Column, ManagedCalendar,
                                        ManagedTimeSelect, Row, Select, SwitchTo,
                                        TimeSelect)
from aiogram_dialog.widgets.kbd.time import OnValueChanged
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.ride import RideService
from seatbot.infrastructure.database.dao import RidesDAO

from ..user_dialogs.states import RideCreateSG, RidesMgmtSG


@inject
async def get_templates(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    **_kwargs,
):
    templates = await rides_dao.list_templates(limit=8)
    if not templates:
        return {"has_templates": False, "empty_text": "🚫 Шаблонов пока нет.", "back_btn": "⬅️ В панель"}
    items = []
    for t in templates:
        price_str = "бесплатно" if t.is_free else f"{t.price:.2f} BYN"
        time_str = t.departure_at.strftime("%H:%M")
        note_str = f" • {t.note}" if t.note else ""
        items.append(
            {
                "ride_id": t.ride_id,
                "title": f"🕒 {time_str} • {price_str}{note_str}",
            }
        )
    return {"has_templates": True, "templates": items, "back_btn": "⬅️ В панель"}


async def get_calendar_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    selected_date = dialog_manager.dialog_data.get("selected_date")
    return {
        "has_date": selected_date is not None,
        "selected_date": selected_date or "—",
        "next_btn": "➡️ Выбрать время",
        "back_btn": "⬅️ Назад",
    }


async def get_time_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    selected_date = dialog_manager.dialog_data.get("selected_date", "—")
    selected_time = dialog_manager.dialog_data.get("selected_time", "—")
    return {
        "selected_date": selected_date,
        "selected_time": selected_time,
        "next_btn": "➡️ Дальше",
        "back_btn": "⬅️ К календарю",
    }


async def get_repeat_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    return {
        "repeat_info": (
            "🔁 <b>Повтор поездки</b>\n\n"
            "На сколько дней вперёд создать эту поездку?\n"
            "1 — только на выбранный день.\n"
            "3 — на 3 дня подряд (каждый день в то же время).\n\n"
            "Введите число от 1 до 14:"
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_remind_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    return {
        "remind_info": (
            "⏰ <b>Напоминание перед поездкой</b>\n\n"
            "За сколько минут до отправления напомнить пассажирам?\n"
            "Введите число от 1 до 1440 (например, 30 — за полчаса).\n\n"
            "0 — без напоминания."
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_price_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    return {
        "price_info": (
            "💰 <b>Цена поездки</b>\n\n"
            "Введите цену в BYN.\n"
            "Введите <code>0</code> для бесплатной поездки.\n\n"
            "Пример: <code>15.50</code>"
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_confirm_data(
    dialog_manager: DialogManager,
    **_kwargs,
):
    selected_date = dialog_manager.dialog_data.get("selected_date", "—")
    selected_time = dialog_manager.dialog_data.get("selected_time", "—")
    price = dialog_manager.dialog_data.get("price", 0)
    auto_approve = dialog_manager.dialog_data.get("auto_approve", False)
    is_visible = dialog_manager.dialog_data.get("is_visible", True)
    note = dialog_manager.dialog_data.get("note")
    repeat_days = dialog_manager.dialog_data.get("repeat_days", 1)
    remind_minutes = dialog_manager.dialog_data.get("remind_minutes", 30)
    price_str = "Бесплатно" if price <= 0 else f"{price:.2f} BYN"
    repeat_str = f"{repeat_days} дн." if repeat_days > 1 else "1 день"
    remind_str = f"{remind_minutes} мин." if remind_minutes > 0 else "выключено"
    text = (
        "📝 <b>Подтвердите создание поездки</b>\n\n"
        f"📅 Дата: <b>{selected_date}</b>\n"
        f"🕒 Время: <b>{selected_time}</b>\n"
        f"💰 Цена: <b>{price_str}</b>\n"
        f"🪑 Мест: <b>4</b>\n"
        f"🔁 Повтор: <b>{repeat_str}</b>\n"
        f"⏰ Напоминание: <b>{remind_str}</b>\n"
        f"⚡ Авто-апрув: {'ВКЛ' if auto_approve else 'ВЫКЛ'}\n"
        f"👁️ Видимость: {'видна всем' if is_visible else 'скрытая'}\n"
        f"📝 Заметка: {note or '—'}"
    )
    return {"confirm_text": text, "create_btn": "✅ Создать", "back_btn": "⬅️ Назад"}


# ── обработчики ──────────────────────────────────────────────────────────────


async def on_date_selected(
    event: ChatEvent,
    widget: ManagedCalendar,
    manager: DialogManager,
    selected_date: date,
):
    manager.dialog_data["selected_date"] = selected_date.strftime("%d.%m.%Y")
    manager.dialog_data["selected_date_obj"] = selected_date.isoformat()
    if isinstance(event, CallbackQuery):
        await event.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}")
    await manager.next()


class TimeChangedHandler(OnValueChanged):
    async def __call__(
        self,
        event: ChatEvent,
        widget: ManagedTimeSelect,
        manager: DialogManager,
        value: time | None,
    ) -> None:
        if value is None:
            return
        time_str = f"{value.hour:02d}:{value.minute:02d}"
        manager.dialog_data["selected_time"] = time_str
        manager.dialog_data["selected_hour"] = value.hour
        manager.dialog_data["selected_minute"] = value.minute
        if isinstance(event, CallbackQuery):
            await event.answer(f"Время: {time_str}")
        await manager.next()


on_time_changed = TimeChangedHandler()


async def on_price_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Введите неотрицательное число (например, <code>15.50</code> или <code>0</code>)."
        )
        return
    manager.dialog_data["price"] = price
    await manager.next()


async def on_repeat_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip()
    try:
        repeat_days = int(text)
        if not 1 <= repeat_days <= 14:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 14.")
        return
    manager.dialog_data["repeat_days"] = repeat_days
    await manager.next()


async def on_remind_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip()
    try:
        remind_minutes = int(text)
        if not 0 <= remind_minutes <= 1440:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 0 до 1440.")
        return
    manager.dialog_data["remind_minutes"] = remind_minutes
    await manager.next()


async def on_note_input(message: Message, widget: MessageInput, manager: DialogManager):
    manager.dialog_data["note"] = (message.text or "").strip()[:512] or None
    await manager.next()


async def on_note_skip(callback: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["note"] = None
    await manager.next()


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


@inject
async def on_create(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
):
    date_str: str = manager.dialog_data["selected_date_obj"]
    hour: int = manager.dialog_data.get("selected_hour", 18)
    minute: int = manager.dialog_data.get("selected_minute", 0)
    price: float = manager.dialog_data["price"]
    auto_approve: bool = manager.dialog_data.get("auto_approve", False)
    is_visible: bool = manager.dialog_data.get("is_visible", True)
    note: str | None = manager.dialog_data.get("note")
    repeat_days: int = manager.dialog_data.get("repeat_days", 1)
    remind_minutes: int = manager.dialog_data.get("remind_minutes", 30)

    d = date.fromisoformat(date_str)
    departure_at = datetime(
        year=d.year,
        month=d.month,
        day=d.day,
        hour=hour,
        minute=minute,
        tzinfo=UTC,
    )

    rides = await ride_service.create_ride(
        departure_at=departure_at,
        price=price,
        auto_approve=auto_approve,
        note=note,
        is_visible=is_visible,
        repeat_days=repeat_days,
        remind_minutes=remind_minutes,
    )
    count = len(rides)
    await callback.answer(f"✅ Создано поездок: {count}!", show_alert=True)
    await manager.start(RidesMgmtSG.rides_list, mode=StartMode.RESET_STACK)


async def on_template_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
):
    ride_id = int(item_id)
    container = manager.middleware_data["dishka_container"]
    rides_dao: RidesDAO = await container.get(RidesDAO)
    template = await rides_dao.get_by_id(ride_id)
    if not template:
        await callback.answer("Шаблон не найден", show_alert=True)
        return
    manager.dialog_data["template_ride_id"] = ride_id
    manager.dialog_data["price"] = float(template.price)
    manager.dialog_data["auto_approve"] = template.auto_approve
    manager.dialog_data["is_visible"] = template.is_visible
    manager.dialog_data["note"] = template.note
    manager.dialog_data["remind_minutes"] = template.remind_minutes
    await callback.answer("Шаблон загружен, выберите дату", show_alert=True)
    await manager.switch_to(RideCreateSG.calendar)


# ── диалог ───────────────────────────────────────────────────────────────────


ride_create_dialog = Dialog(
    # 1. Выбор: шаблон или новая поездка
    Window(
        Const("➕ <b>Создание поездки</b>\n\nВыберите шаблон или создайте новую:"),
        Column(
            Select(
                Format("{item[title]}"),
                id="templates_sel",
                item_id_getter=lambda item: str(item["ride_id"]),
                items="templates",
                on_click=on_template_selected,
                when="has_templates",
            ),
        ),
        Format("{empty_text}", when="not has_templates"),
        SwitchTo(Const("🆕 Новая поездка"), id="new_ride", state=RideCreateSG.calendar),
        Cancel(Format("{back_btn}")),
        state=RideCreateSG.select_template,
        getter=get_templates,
    ),
    # 2. Календарь — выбор даты
    Window(
        Const("📅 <b>Выберите дату отправления</b>"),
        Calendar(id="date_cal", on_click=on_date_selected),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.calendar,
    ),
    # 3. Выбор времени
    Window(
        Format("📅 Дата: <b>{selected_date}</b>\n\n🕒 <b>Выберите время отправления:</b>"),
        TimeSelect(
            id="time_sel",
            hour_header=Const("Час"),
            minute_header=Const("Минута"),
            on_value_changed=on_time_changed,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.calendar),
        state=RideCreateSG.time,
        getter=get_time_data,
    ),
    # 4. Цена
    Window(
        Format("{price_info}"),
        MessageInput(on_price_input),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.time),
        state=RideCreateSG.price,
        getter=get_price_data,
    ),
    # 5. Повтор (на сколько дней)
    Window(
        Format("{repeat_info}"),
        MessageInput(on_repeat_input),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.price),
        state=RideCreateSG.repeat_days,
        getter=get_repeat_data,
    ),
    # 6. Напоминание
    Window(
        Format("{remind_info}"),
        MessageInput(on_remind_input),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.repeat_days),
        state=RideCreateSG.remind,
        getter=get_remind_data,
    ),
    # 7. Авто-одобрение
    Window(
        Const("⚡ <b>Авто-одобрение?</b>\n\nОдобрять брони автоматически без вашего участия?"),
        Row(
            Button(Const("✅ Да"), id="auto_yes", on_click=on_auto_yes),
            Button(Const("❌ Нет"), id="auto_no", on_click=on_auto_no),
        ),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.remind),
        state=RideCreateSG.auto_approve,
    ),
    # 7. Видимость
    Window(
        Const(
            "👁️ <b>Видимость</b>\n\nСделать поездку видимой всем, или скрытой (видна только забронировавшим)?"
        ),
        Row(
            Button(Const("👁️ Видна всем"), id="vis_yes", on_click=on_vis_yes),
            Button(Const("🔒 Скрытая"), id="vis_no", on_click=on_vis_no),
        ),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.auto_approve),
        state=RideCreateSG.visibility,
    ),
    # 8. Заметка
    Window(
        Const("📝 <b>Заметка</b> (необязательно)\n\nВведите текст или нажмите «Пропустить»."),
        MessageInput(on_note_input),
        Button(Const("⏭️ Пропустить"), id="note_skip", on_click=on_note_skip),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.visibility),
        state=RideCreateSG.note,
    ),
    # 9. Подтверждение
    Window(
        Format("{confirm_text}"),
        Button(Format("{create_btn}"), id="create", on_click=on_create),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.note),
        state=RideCreateSG.confirm,
        getter=get_confirm_data,
    ),
)
