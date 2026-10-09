import math
from datetime import date, datetime, time, timezone
from html import escape
from typing import Any

from aiogram import F
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.api.entities import ChatEvent
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (Button, Calendar, CalendarUserConfig, Cancel,
                                        Column, Group, ManagedCalendar, ManagedTimeSelect,
                                        Row, ScrollingGroup, Select, SwitchTo, TimeSelect)
from aiogram_dialog.widgets.kbd.time import OnValueChanged
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.location import LocationService
from kologo.application.services.ride import RideService
from kologo.domain.exceptions import RideInPastError
from kologo.infrastructure.config import AppConfig
from kologo.infrastructure.database.dao import LocationsDAO, RidesDAO
from kologo.infrastructure.notifications import MessageBuilder, fmt_amount, route_str
from kologo.infrastructure.time import LocalClock

from ..user_dialogs.states import RideCreateSG


@inject
async def get_templates(
    dialog_manager: DialogManager,
    ride_service: FromDishka[RideService],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    templates = await ride_service.list_templates(limit=5)
    if not templates:
        return {"has_templates": False, "empty_text": "🚫 Шаблонов пока нет.", "back_btn": "⬅️ В панель"}
    items = []
    for t in templates:
        price_str = "бесплатно" if t.is_free else f"{fmt_amount(t.price)} BYN"
        time_str = clock.fmt(t.departure_at, "%H:%M")
        note_str = f" • {escape(t.note)}" if t.note else ""
        route = route_str(t)
        route_str_ = f" • {route}" if route else ""
        items.append(
            {
                "ride_id": t.ride_id,
                "title": f"🕒 {time_str} • {price_str} • {t.seats_total} мест{route_str_}{note_str}",
            }
        )
    return {"has_templates": True, "templates": items, "back_btn": "⬅️ В панель"}


class FutureCalendar(Calendar):
    async def _get_user_config(self, data: dict[str, Any], manager: DialogManager) -> CalendarUserConfig:
        return CalendarUserConfig(min_date=data.get("min_date"), timezone=data.get("calendar_tz"))


def _local_today(clock: LocalClock) -> date:
    return clock.to_local(clock.now()).date()


async def _advance(manager: DialogManager, next_state: State | None = None) -> None:
    edit_mode = manager.dialog_data.get("edit_mode")
    if edit_mode == "edit_route" and next_state == RideCreateSG.destination:
        await manager.switch_to(next_state)
    elif manager.dialog_data.pop("edit_mode", None):
        await manager.switch_to(RideCreateSG.confirm)
    elif next_state is not None:
        await manager.switch_to(next_state)
    else:
        await manager.next()


def _selected_departure(data: dict[str, Any], clock: LocalClock) -> datetime | None:
    date_obj = data.get("selected_date_obj")
    if not date_obj:
        return None
    d = date.fromisoformat(date_obj)
    return clock.local_dt(
        d.year, d.month, d.day, data.get("selected_hour", 18), data.get("selected_minute", 0)
    )


async def _app_config(manager: DialogManager) -> AppConfig:
    app_config: AppConfig = await manager.middleware_data["dishka_container"].get(AppConfig)
    return app_config


def _weekdays(data: dict[str, Any], app_config: AppConfig) -> list[int]:
    return list(data.get("weekdays", app_config.all_weekdays))


def _weekdays_label(weekdays: list[int], app_config: AppConfig) -> str:
    days = tuple(sorted(weekdays))
    if days == app_config.all_weekdays:
        return "все дни"
    if days == app_config.workdays:
        return "будни (пн–пт)"
    return ", ".join(app_config.weekdays_ru[i] for i in days)


@inject
async def get_calendar_data(
    dialog_manager: DialogManager,
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    local_now = clock.to_local(clock.now())
    offset = local_now.utcoffset()
    return {
        "min_date": local_now.date(),
        "calendar_tz": timezone(offset) if offset is not None else None,
    }


@inject
async def get_time_data(
    dialog_manager: DialogManager,
    ride_service: FromDishka[RideService],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    selected_date = dialog_manager.dialog_data.get("selected_date", "—")
    selected_time = dialog_manager.dialog_data.get("selected_time", "—")
    presets: list[str] = []
    for r in await ride_service.list_templates(limit=5):
        t = clock.fmt(r.departure_at, "%H:%M")
        if t not in presets:
            presets.append(t)
    return {
        "selected_date": selected_date,
        "selected_time": selected_time,
        "time_presets": [{"id": t.replace(":", ""), "label": f"⚡ {t}"} for t in presets],
        "has_presets": bool(presets),
        "next_btn": "➡️ Дальше",
        "back_btn": "⬅️ К календарю",
    }


@inject
async def get_repeat_data(
    dialog_manager: DialogManager,
    ride_service: FromDishka[RideService],
    messages: FromDishka[MessageBuilder],
    clock: FromDishka[LocalClock],
    app_config: FromDishka[AppConfig],
    **_kwargs: Any,
) -> dict[str, Any]:
    data = dialog_manager.dialog_data
    repeat_days: int = data.get("repeat_days", 1)
    weekdays = _weekdays(data, app_config)
    departure = _selected_departure(data, clock)
    planned = ride_service.plan_departures(departure, repeat_days, set(weekdays)) if departure else []
    preview = "\n".join(f"• {messages.short_date(d)}" for d in planned[:10])
    if len(planned) > 10:
        preview += f"\n… и ещё {len(planned) - 10}"
    text = (
        "🔁 <b>Повтор поездки</b>\n\n"
        f"Период: <b>{repeat_days} дн.</b> с {data.get('selected_date', '—')}\n"
        f"Дни недели: <b>{_weekdays_label(weekdays, app_config)}</b>\n\n"
        f"Будет создано поездок: <b>{len(planned)}</b>\n{preview or '—'}\n\n"
        f"Отметьте дни недели, введите длину периода в днях (1–{app_config.max_repeat_days}) "
        "или выберите готовый вариант."
    )
    return {
        "repeat_info": text,
        "weekday_items": [
            {"id": i, "label": f"{'✅' if i in weekdays else '▫️'}{label}"}
            for i, label in enumerate(app_config.weekdays_ru)
        ],
        "can_continue": bool(planned),
        "back_btn": "⬅️ Назад",
    }


async def get_remind_data(
    dialog_manager: DialogManager,
    **_kwargs: Any,
) -> dict[str, Any]:
    return {
        "remind_info": (
            "⏰ <b>Напоминание перед поездкой</b>\n\n"
            "За сколько минут до отправления напомнить пассажирам?\n"
            "Введите число от 1 до 1440 (например, 30 — за полчаса).\n\n"
            "0 — без напоминания."
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_vip_hold_data(
    dialog_manager: DialogManager,
    **_kwargs: Any,
) -> dict[str, Any]:
    return {
        "vip_hold_info": (
            "⭐ <b>VIP-холд</b>\n\n"
            "После создания поездки первые N минут бронировать "
            "могут только VIP-пользователи, затем — все желающие.\n\n"
            "Введите число минут от 0 до 120.\n"
            "0 — без холда (сразу все могут бронировать)."
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_price_data(
    dialog_manager: DialogManager,
    **_kwargs: Any,
) -> dict[str, Any]:
    return {
        "price_info": (
            "💰 <b>Цена поездки</b>\n\n"
            "Введите цену в BYN.\n"
            "Введите <code>0</code> для бесплатной поездки.\n\n"
            "Пример: <code>15.50</code>"
        ),
        "back_btn": "⬅️ Назад",
    }


async def get_back_btn(dialog_manager: DialogManager, **_kwargs: Any) -> dict[str, Any]:
    return {"back_btn": "⬅️ Назад"}


async def get_seats_data(
    dialog_manager: DialogManager,
    **_kwargs: Any,
) -> dict[str, Any]:
    return {
        "seats_info": (
            "🪑 <b>Количество мест</b>\n\n"
            "Сколько пассажирских мест в поездке?\n"
            "Введите число от 1 до 8.\n\n"
            "Пример: <code>4</code>"
        ),
        "back_btn": "⬅️ Назад",
    }


@inject
async def get_origin_data(
    dialog_manager: DialogManager,
    location_service: FromDishka[LocationService],
    **_kwargs: Any,
) -> dict[str, Any]:
    locations = await location_service.list_all()
    current = dialog_manager.dialog_data.get("origin")
    return {
        "origin_info": (
            "📍 <b>Место отправления</b>\n\n"
            "Выберите точку, отправьте геолокацию\n"
            "или введите название текстом (без гео)."
        ),
        "locations": [{"location_id": loc.location_id, "name": loc.name} for loc in locations],
        "has_locations": bool(locations),
        "has_current": bool(current),
        "current_name": current or "",
        "back_btn": "⬅️ Назад",
    }


@inject
async def get_destination_data(
    dialog_manager: DialogManager,
    location_service: FromDishka[LocationService],
    **_kwargs: Any,
) -> dict[str, Any]:
    locations = await location_service.list_all()
    current = dialog_manager.dialog_data.get("destination")
    return {
        "destination_info": (
            "🏁 <b>Место прибытия</b>\n\n"
            "Выберите точку, отправьте геолокацию\n"
            "или введите название текстом (без гео)."
        ),
        "locations": [{"location_id": loc.location_id, "name": loc.name} for loc in locations],
        "has_locations": bool(locations),
        "has_current": bool(current),
        "current_name": current or "",
        "back_btn": "⬅️ Назад",
    }


@inject
async def get_confirm_data(
    dialog_manager: DialogManager,
    clock: FromDishka[LocalClock],
    ride_service: FromDishka[RideService],
    app_config: FromDishka[AppConfig],
    **_kwargs: Any,
) -> dict[str, Any]:
    selected_date = dialog_manager.dialog_data.get("selected_date", "—")
    selected_time = dialog_manager.dialog_data.get("selected_time", "—")
    price = dialog_manager.dialog_data.get("price", 0)
    auto_approve = dialog_manager.dialog_data.get("auto_approve", False)
    is_visible = dialog_manager.dialog_data.get("is_visible", True)
    note = dialog_manager.dialog_data.get("note")
    repeat_days = dialog_manager.dialog_data.get("repeat_days", 1)
    remind_minutes = dialog_manager.dialog_data.get("remind_minutes", 30)
    vip_hold_minutes = dialog_manager.dialog_data.get("vip_hold_minutes", 0)
    seats_total = dialog_manager.dialog_data.get("seats_total", 4)
    origin = dialog_manager.dialog_data.get("origin")
    destination = dialog_manager.dialog_data.get("destination")
    route = escape(f"{origin} → {destination}" if origin and destination else (origin or destination or "—"))
    price_str = "Бесплатно" if price <= 0 else f"{fmt_amount(price)} BYN"
    weekdays = _weekdays(dialog_manager.dialog_data, app_config)
    departure_at = _selected_departure(dialog_manager.dialog_data, clock)
    rides_count = (
        len(ride_service.plan_departures(departure_at, repeat_days, set(weekdays))) if departure_at else 0
    )
    repeat_str = (
        f"{repeat_days} дн., {_weekdays_label(weekdays, app_config)} → {rides_count} поездок"
        if repeat_days > 1
        else "только этот день"
    )
    remind_str = f"{remind_minutes} мин." if remind_minutes > 0 else "выключено"
    vip_hold_str = f"{vip_hold_minutes} мин" if vip_hold_minutes > 0 else "нет"
    text = (
        "📝 <b>Подтвердите создание поездки</b>\n\n"
        f"📅 Дата: <b>{selected_date}</b>\n"
        f"🕒 Время: <b>{selected_time}</b>\n"
        f"📍 Маршрут: <b>{route}</b>\n"
        f"💰 Цена: <b>{price_str}</b>\n"
        f"🪑 Мест: <b>{seats_total}</b>\n"
        f"🔁 Повтор: <b>{repeat_str}</b>\n"
        f"⏰ Напоминание: <b>{remind_str}</b>\n"
        f"⭐ VIP-холд: <b>{vip_hold_str}</b>\n"
        f"⚡ Авто-апрув: {'ВКЛ' if auto_approve else 'ВЫКЛ'}\n"
        f"👁️ Видимость: {'видна всем' if is_visible else 'скрытая'}\n"
        f"📝 Заметка: {escape(note) if note else '—'}"
    )
    if departure_at:
        minutes_left = (departure_at - clock.now()).total_seconds() / 60
        if minutes_left <= 0:
            text += "\n\n⛔ <b>Время отправления уже прошло — выберите новое время.</b>"
        elif vip_hold_minutes >= minutes_left:
            text += "\n\n⚠️ VIP-холд длиннее, чем осталось до отправления — обычные пассажиры не успеют записаться."
    if rides_count == 0:
        text += "\n\n⛔ <b>По выбранным дням недели не получается ни одной даты.</b>"
    text += "\n\n<i>Нажмите ✏️-кнопку, чтобы изменить поле.</i>"
    return {
        "confirm_text": text,
        "create_btn": "✅ Создать",
        "back_btn": "⬅️ Назад",
        "edit_items": [
            {"id": key, "label": f"✏️ {label}"} for key, (label, _) in app_config.ride_edit_steps.items()
        ],
    }


# ── обработчики ──────────────────────────────────────────────────────────────


async def on_date_selected(
    event: ChatEvent,
    widget: ManagedCalendar,
    manager: DialogManager,
    selected_date: date,
) -> None:
    container = manager.middleware_data["dishka_container"]
    clock: LocalClock = await container.get(LocalClock)
    if selected_date < _local_today(clock):
        if isinstance(event, CallbackQuery):
            await event.answer((await _app_config(manager)).past_date_text, show_alert=True)
        return
    manager.dialog_data["selected_date"] = selected_date.strftime("%d.%m.%Y")
    manager.dialog_data["selected_date_obj"] = selected_date.isoformat()
    template_ride_id = manager.dialog_data.get("template_ride_id")
    if template_ride_id is not None:
        ride_service: RideService = await container.get(RideService)
        try:
            rides = await ride_service.create_ride_from_template(
                template_ride_id,
                clock.to_utc(datetime.combine(selected_date, time.min, tzinfo=clock.tz)),
            )
        except RideInPastError as e:
            if isinstance(event, CallbackQuery):
                await event.answer(
                    f"⛔ Время шаблона ({clock.fmt(e.departure_at, '%H:%M')}) на эту дату уже прошло. "
                    "Выберите другую дату.",
                    show_alert=True,
                )
            return
        if isinstance(event, CallbackQuery):
            if rides:
                await manager.done()
                await event.answer("✅ Поездка создана из шаблона")
            else:
                await event.answer("❌ Шаблон не найден", show_alert=True)
                return
        else:
            await manager.done()
        return
    if isinstance(event, CallbackQuery):
        await event.answer(f"Выбрана дата: {selected_date.strftime('%d.%m.%Y')}")
    await _advance(manager)


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
        clock: LocalClock = await manager.middleware_data["dishka_container"].get(LocalClock)
        d = date.fromisoformat(manager.dialog_data["selected_date_obj"])
        if clock.local_dt(d.year, d.month, d.day, value.hour, value.minute) <= clock.now():
            await widget.set_value(None)
            if isinstance(event, CallbackQuery):
                await event.answer((await _app_config(manager)).past_time_text, show_alert=True)
            return
        time_str = f"{value.hour:02d}:{value.minute:02d}"
        manager.dialog_data["selected_time"] = time_str
        manager.dialog_data["selected_hour"] = value.hour
        manager.dialog_data["selected_minute"] = value.minute
        if isinstance(event, CallbackQuery):
            await event.answer(f"Время: {time_str}")
        await _advance(manager)


on_time_changed = TimeChangedHandler()


@inject
async def on_time_preset(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
    clock: FromDishka[LocalClock],
    app_config: FromDishka[AppConfig],
) -> None:
    hour, minute = int(item_id[:2]), int(item_id[2:])
    d = date.fromisoformat(manager.dialog_data["selected_date_obj"])
    if clock.local_dt(d.year, d.month, d.day, hour, minute) <= clock.now():
        await callback.answer(app_config.past_time_text, show_alert=True)
        return
    manager.dialog_data["selected_time"] = f"{hour:02d}:{minute:02d}"
    manager.dialog_data["selected_hour"] = hour
    manager.dialog_data["selected_minute"] = minute
    await callback.answer(f"Время: {hour:02d}:{minute:02d}")
    await _advance(manager)


async def on_weekday_toggle(
    callback: CallbackQuery, select: Select, manager: DialogManager, item_id: str
) -> None:
    weekdays = _weekdays(manager.dialog_data, await _app_config(manager))
    day = int(item_id)
    if day in weekdays:
        if len(weekdays) == 1:
            await callback.answer("Нужен хотя бы один день недели", show_alert=True)
            return
        weekdays.remove(day)
    else:
        weekdays.append(day)
    manager.dialog_data["weekdays"] = sorted(weekdays)


async def on_repeat_single(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["repeat_days"] = 1
    manager.dialog_data["weekdays"] = list((await _app_config(manager)).all_weekdays)
    await _advance(manager)


async def _repeat_workdays(manager: DialogManager, weeks: int) -> None:
    manager.dialog_data["repeat_days"] = 7 * weeks
    manager.dialog_data["weekdays"] = list((await _app_config(manager)).workdays)
    await _advance(manager)


async def on_repeat_workdays_1(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await _repeat_workdays(manager, 1)


async def on_repeat_workdays_2(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await _repeat_workdays(manager, 2)


async def on_repeat_next(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await _advance(manager)


async def on_skip_to_confirm(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data.pop("edit_mode", None)
    await manager.switch_to(RideCreateSG.confirm)


async def on_quick_defaults(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["seats_total"] = 4
    await manager.switch_to(RideCreateSG.confirm)


def _editing(data: dict[str, Any], widget: Any, manager: DialogManager) -> bool:
    return bool(manager.dialog_data.get("edit_mode"))


def _not_editing(data: dict[str, Any], widget: Any, manager: DialogManager) -> bool:
    return not _editing(data, widget, manager)


def _back_to_confirm() -> Button:
    return Button(
        Const("↩️ К подтверждению"), id="back_to_confirm", on_click=on_skip_to_confirm, when=_editing
    )


async def on_edit_field(
    callback: CallbackQuery, select: Select, manager: DialogManager, item_id: str
) -> None:
    _, state_name = (await _app_config(manager)).ride_edit_steps[item_id]
    state: State = getattr(RideCreateSG, state_name)
    manager.dialog_data["edit_mode"] = item_id
    await manager.switch_to(state)


async def on_origin_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    if message.location:
        manager.dialog_data["origin_lat"] = message.location.latitude
        manager.dialog_data["origin_lon"] = message.location.longitude
        await manager.switch_to(RideCreateSG.origin_name)
        return
    origin = (message.text or "").strip()[:128]
    if not origin:
        await message.answer("❌ Введите название или отправьте геолокацию.")
        return
    manager.dialog_data["origin"] = origin
    manager.dialog_data["origin_lat"] = None
    manager.dialog_data["origin_lon"] = None
    await _advance(manager, RideCreateSG.destination)


async def on_keep_origin(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await _advance(manager, RideCreateSG.destination)


async def on_keep_destination(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await _advance(manager, RideCreateSG.price)


async def on_origin_name_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("❌ Введите название точки отправления.")
        return
    manager.dialog_data["origin"] = name
    await _advance(manager, RideCreateSG.destination)


@inject
async def on_origin_location_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
    locations_dao: FromDishka[LocationsDAO],
) -> None:
    loc = await locations_dao.get_by_id(int(item_id))
    if not loc:
        await callback.answer("Точка не найдена", show_alert=True)
        return
    manager.dialog_data["origin"] = loc.name
    manager.dialog_data["origin_lat"] = loc.lat
    manager.dialog_data["origin_lon"] = loc.lon
    await _advance(manager, RideCreateSG.destination)


async def on_destination_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    if message.location:
        manager.dialog_data["destination_lat"] = message.location.latitude
        manager.dialog_data["destination_lon"] = message.location.longitude
        await manager.switch_to(RideCreateSG.destination_name)
        return
    destination = (message.text or "").strip()[:128]
    if not destination:
        await message.answer("❌ Введите название или отправьте геолокацию.")
        return
    manager.dialog_data["destination"] = destination
    manager.dialog_data["destination_lat"] = None
    manager.dialog_data["destination_lon"] = None
    await _advance(manager, RideCreateSG.price)


async def on_destination_name_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    name = (message.text or "").strip()[:128]
    if not name:
        await message.answer("❌ Введите название точки прибытия.")
        return
    manager.dialog_data["destination"] = name
    await _advance(manager, RideCreateSG.price)


@inject
async def on_destination_location_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
    locations_dao: FromDishka[LocationsDAO],
) -> None:
    loc = await locations_dao.get_by_id(int(item_id))
    if not loc:
        await callback.answer("Точка не найдена", show_alert=True)
        return
    manager.dialog_data["destination"] = loc.name
    manager.dialog_data["destination_lat"] = loc.lat
    manager.dialog_data["destination_lon"] = loc.lon
    await _advance(manager, RideCreateSG.price)


async def on_price_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    max_price = (await _app_config(manager)).max_ride_price
    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
        if not math.isfinite(price) or not 0 <= price <= max_price:
            raise ValueError
    except ValueError:
        await message.answer(
            f"❌ Введите число от 0 до {fmt_amount(max_price)} (например, <code>15.50</code> или <code>0</code>)."
        )
        return
    manager.dialog_data["price"] = round(price, 2)
    await _advance(manager)


async def on_seats_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip()
    try:
        seats = int(text)
        if not 1 <= seats <= 8:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 8.")
        return
    manager.dialog_data["seats_total"] = seats
    await _advance(manager)


async def on_repeat_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    max_days = (await _app_config(manager)).max_repeat_days
    text = (message.text or "").strip()
    try:
        repeat_days = int(text)
        if not 1 <= repeat_days <= max_days:
            raise ValueError
    except ValueError:
        await message.answer(f"❌ Введите число от 1 до {max_days}.")
        return
    manager.dialog_data["repeat_days"] = repeat_days


async def on_remind_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip()
    try:
        remind_minutes = int(text)
        if not 0 <= remind_minutes <= 1440:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 0 до 1440.")
        return
    manager.dialog_data["remind_minutes"] = remind_minutes
    await _advance(manager)


async def on_vip_hold_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    text = (message.text or "").strip()
    try:
        vip_hold_minutes = int(text)
        if not 0 <= vip_hold_minutes <= 120:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 0 до 120.")
        return
    manager.dialog_data["vip_hold_minutes"] = vip_hold_minutes
    await _advance(manager)


async def on_vip_hold_skip(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["vip_hold_minutes"] = 0
    await _advance(manager)


async def on_note_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    manager.dialog_data["note"] = (message.text or "").strip()[:512] or None
    await _advance(manager)


async def on_note_skip(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["note"] = None
    await _advance(manager)


async def on_auto_yes(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["auto_approve"] = True
    await _advance(manager)


async def on_auto_no(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["auto_approve"] = False
    await _advance(manager)


async def on_vis_yes(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["is_visible"] = True
    await _advance(manager)


async def on_vis_no(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    manager.dialog_data["is_visible"] = False
    await _advance(manager)


@inject
async def on_create(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
    clock: FromDishka[LocalClock],
    app_config: FromDishka[AppConfig],
) -> None:
    date_str: str = manager.dialog_data["selected_date_obj"]
    hour: int = manager.dialog_data.get("selected_hour", 18)
    minute: int = manager.dialog_data.get("selected_minute", 0)
    price: float = manager.dialog_data["price"]
    auto_approve: bool = manager.dialog_data.get("auto_approve", False)
    is_visible: bool = manager.dialog_data.get("is_visible", True)
    note: str | None = manager.dialog_data.get("note")
    repeat_days: int = manager.dialog_data.get("repeat_days", 1)
    remind_minutes: int = manager.dialog_data.get("remind_minutes", 30)
    vip_hold_minutes: int = manager.dialog_data.get("vip_hold_minutes", 0)
    seats_total: int = manager.dialog_data.get("seats_total", 4)
    origin: str = manager.dialog_data["origin"]
    destination: str = manager.dialog_data["destination"]
    origin_lat: float | None = manager.dialog_data.get("origin_lat")
    origin_lon: float | None = manager.dialog_data.get("origin_lon")
    destination_lat: float | None = manager.dialog_data.get("destination_lat")
    destination_lon: float | None = manager.dialog_data.get("destination_lon")

    d = date.fromisoformat(date_str)
    departure_at = clock.local_dt(d.year, d.month, d.day, hour, minute)

    try:
        rides = await ride_service.create_ride(
            departure_at=departure_at,
            price=price,
            auto_approve=auto_approve,
            seats_total=seats_total,
            note=note,
            origin=origin,
            destination=destination,
            origin_lat=origin_lat,
            origin_lon=origin_lon,
            destination_lat=destination_lat,
            destination_lon=destination_lon,
            is_visible=is_visible,
            repeat_days=repeat_days,
            remind_minutes=remind_minutes,
            vip_hold_minutes=vip_hold_minutes,
            template_ride_id=manager.dialog_data.get("template_ride_id"),
            weekdays=set(_weekdays(manager.dialog_data, app_config)),
        )
    except RideInPastError:
        await callback.answer(app_config.past_time_text, show_alert=True)
        await manager.switch_to(RideCreateSG.time)
        return
    if not rides:
        await callback.answer("⛔ По выбранным дням недели нет ни одной даты", show_alert=True)
        await manager.switch_to(RideCreateSG.repeat_days)
        return
    count = len(rides)
    await manager.done()
    await callback.answer(f"✅ Создано поездок: {count}!")


async def on_template_delete_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    manager.dialog_data["delete_template_id"] = int(item_id)
    await manager.switch_to(RideCreateSG.template_delete_confirm)


@inject
async def get_template_delete_confirm(
    dialog_manager: DialogManager,
    rides_dao: FromDishka[RidesDAO],
    clock: FromDishka[LocalClock],
    **_kwargs: Any,
) -> dict[str, Any]:
    template = await rides_dao.get_by_id(dialog_manager.dialog_data.get("delete_template_id", 0))
    if not template:
        return {"confirm_text": "🚫 Шаблон не найден"}
    price = "бесплатно" if template.is_free else f"{fmt_amount(template.price)} BYN"
    note = f"\n📝 {escape(template.note)}" if template.note else ""
    return {
        "confirm_text": (
            "🗑 <b>Удалить шаблон?</b>\n\n"
            f"📍 {route_str(template) or '—'}\n"
            f"🕒 {clock.fmt(template.departure_at, '%H:%M')} • {price} • {template.seats_total} мест{note}\n\n"
            "Поездки и их история не удаляются — шаблон просто пропадёт из списка."
        )
    }


@inject
async def on_template_delete_confirm(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    ride_service: FromDishka[RideService],
) -> None:
    ok = await ride_service.hide_template(manager.dialog_data.pop("delete_template_id", 0))
    await callback.answer("🗑 Шаблон удалён" if ok else "Шаблон не найден")
    await manager.switch_to(RideCreateSG.template_delete)


async def on_template_selected(
    callback: CallbackQuery,
    select: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
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
    manager.dialog_data["vip_hold_minutes"] = template.vip_hold_minutes
    manager.dialog_data["seats_total"] = template.seats_total
    manager.dialog_data["origin"] = template.origin
    manager.dialog_data["destination"] = template.destination
    manager.dialog_data["origin_lat"] = template.origin_lat
    manager.dialog_data["origin_lon"] = template.origin_lon
    manager.dialog_data["destination_lat"] = template.destination_lat
    manager.dialog_data["destination_lon"] = template.destination_lon
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
        Format("{empty_text}", when=~F["has_templates"]),
        SwitchTo(Const("🆕 Новая поездка"), id="new_ride", state=RideCreateSG.calendar),
        SwitchTo(
            Const("🗑 Удалить шаблоны"),
            id="to_template_delete",
            state=RideCreateSG.template_delete,
            when="has_templates",
        ),
        Cancel(Format("{back_btn}")),
        state=RideCreateSG.select_template,
        getter=get_templates,
    ),
    Window(
        Const("🗑 <b>Удаление шаблонов</b>\n\nВыберите шаблон, который нужно убрать:"),
        Column(
            Select(
                Format("🗑 {item[title]}"),
                id="templates_del_sel",
                item_id_getter=lambda item: str(item["ride_id"]),
                items="templates",
                on_click=on_template_delete_selected,
                when="has_templates",
            ),
        ),
        Format("{empty_text}", when=~F["has_templates"]),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.select_template),
        state=RideCreateSG.template_delete,
        getter=get_templates,
    ),
    Window(
        Format("{confirm_text}"),
        Button(Const("🗑 Да, удалить"), id="confirm_template_delete", on_click=on_template_delete_confirm),
        SwitchTo(Const("⬅️ Отмена"), id="back", state=RideCreateSG.template_delete),
        state=RideCreateSG.template_delete_confirm,
        getter=get_template_delete_confirm,
    ),
    # 2. Календарь — выбор даты
    Window(
        Const("📅 <b>Выберите дату отправления</b>"),
        FutureCalendar(id="date_cal", on_click=on_date_selected),
        _back_to_confirm(),
        Cancel(Const("⬅️ Отмена")),
        state=RideCreateSG.calendar,
        getter=get_calendar_data,
    ),
    # 3. Выбор времени
    Window(
        Format("📅 Дата: <b>{selected_date}</b>\n\n🕒 <b>Выберите время отправления:</b>"),
        Group(
            Select(
                Format("{item[label]}"),
                id="time_presets",
                item_id_getter=lambda item: item["id"],
                items="time_presets",
                on_click=on_time_preset,
            ),
            width=3,
            when="has_presets",
        ),
        TimeSelect(
            id="time_sel",
            hour_header=Const("Час"),
            minute_header=Const("Минута"),
            on_value_changed=on_time_changed,
        ),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.calendar),
        state=RideCreateSG.time,
        getter=get_time_data,
    ),
    # 3b. Место отправления
    Window(
        Format("{origin_info}"),
        MessageInput(on_origin_input, content_types=["location", "text"]),
        ScrollingGroup(
            Select(
                Format("📍 {item[name]}"),
                id="origin_loc_sel",
                item_id_getter=lambda item: str(item["location_id"]),
                items="locations",
                on_click=on_origin_location_selected,
                when="has_locations",
            ),
            width=1,
            height=6,
            id="origin_loc_scroll",
        ),
        Button(
            Format("➡️ Оставить: {current_name}"),
            id="keep_origin",
            on_click=on_keep_origin,
            when="has_current",
        ),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.time),
        state=RideCreateSG.origin,
        getter=get_origin_data,
    ),
    # 3c. Название точки отправления (после гео)
    Window(
        Const("📍 <b>Название точки отправления</b>\n\nВведите название для этой геоточки:"),
        MessageInput(on_origin_name_input),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.origin),
        state=RideCreateSG.origin_name,
        getter=get_back_btn,
    ),
    # 3d. Место прибытия
    Window(
        Format("{destination_info}"),
        MessageInput(on_destination_input, content_types=["location", "text"]),
        ScrollingGroup(
            Select(
                Format("📍 {item[name]}"),
                id="dest_loc_sel",
                item_id_getter=lambda item: str(item["location_id"]),
                items="locations",
                on_click=on_destination_location_selected,
                when="has_locations",
            ),
            width=1,
            height=6,
            id="dest_loc_scroll",
        ),
        Button(
            Format("➡️ Оставить: {current_name}"),
            id="keep_destination",
            on_click=on_keep_destination,
            when="has_current",
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.origin),
        state=RideCreateSG.destination,
        getter=get_destination_data,
    ),
    # 3e. Название точки прибытия (после гео)
    Window(
        Const("🏁 <b>Название точки прибытия</b>\n\nВведите название для этой геоточки:"),
        MessageInput(on_destination_name_input),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.destination),
        state=RideCreateSG.destination_name,
        getter=get_back_btn,
    ),
    # 4. Цена
    Window(
        Format("{price_info}"),
        MessageInput(on_price_input),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.destination),
        state=RideCreateSG.price,
        getter=get_price_data,
    ),
    # 4b. Количество мест
    Window(
        Format("{seats_info}"),
        MessageInput(on_seats_input),
        Button(
            Const("⚡ 4 места, остальное по умолчанию"),
            id="quick_defaults",
            on_click=on_quick_defaults,
            when=_not_editing,
        ),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.price),
        state=RideCreateSG.seats,
        getter=get_seats_data,
    ),
    # 5. Повтор (на сколько дней)
    Window(
        Format("{repeat_info}"),
        MessageInput(on_repeat_input),
        Group(
            Select(
                Format("{item[label]}"),
                id="weekday_sel",
                item_id_getter=lambda item: str(item["id"]),
                items="weekday_items",
                on_click=on_weekday_toggle,
            ),
            width=7,
        ),
        Button(Const("1️⃣ Только этот день"), id="repeat_single", on_click=on_repeat_single),
        Row(
            Button(Const("📅 Будни, 1 нед."), id="repeat_wd1", on_click=on_repeat_workdays_1),
            Button(Const("📅 Будни, 2 нед."), id="repeat_wd2", on_click=on_repeat_workdays_2),
        ),
        Button(Const("➡️ Дальше"), id="repeat_next", on_click=on_repeat_next, when="can_continue"),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.seats),
        state=RideCreateSG.repeat_days,
        getter=get_repeat_data,
    ),
    # 6. Напоминание
    Window(
        Format("{remind_info}"),
        MessageInput(on_remind_input),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.repeat_days),
        state=RideCreateSG.remind,
        getter=get_remind_data,
    ),
    # 6b. VIP-холд
    Window(
        Format("{vip_hold_info}"),
        MessageInput(on_vip_hold_input),
        Button(Const("⏭️ Без холда"), id="vip_hold_skip", on_click=on_vip_hold_skip),
        _back_to_confirm(),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.remind),
        state=RideCreateSG.vip_hold,
        getter=get_vip_hold_data,
    ),
    # 7. Авто-одобрение
    Window(
        Const("⚡ <b>Авто-одобрение?</b>\n\nОдобрять брони автоматически без вашего участия?"),
        Row(
            Button(Const("✅ Да"), id="auto_yes", on_click=on_auto_yes),
            Button(Const("❌ Нет"), id="auto_no", on_click=on_auto_no),
        ),
        _back_to_confirm(),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.vip_hold),
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
        _back_to_confirm(),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.auto_approve),
        state=RideCreateSG.visibility,
    ),
    # 8. Заметка
    Window(
        Const("📝 <b>Заметка</b> (необязательно)\n\nВведите текст или нажмите «Пропустить»."),
        MessageInput(on_note_input),
        Button(Const("⏭️ Пропустить"), id="note_skip", on_click=on_note_skip),
        _back_to_confirm(),
        SwitchTo(Const("⬅️ Назад"), id="back", state=RideCreateSG.visibility),
        state=RideCreateSG.note,
    ),
    # 9. Подтверждение
    Window(
        Format("{confirm_text}"),
        Button(Format("{create_btn}"), id="create", on_click=on_create),
        Group(
            Select(
                Format("{item[label]}"),
                id="edit_sel",
                item_id_getter=lambda item: item["id"],
                items="edit_items",
                on_click=on_edit_field,
            ),
            width=2,
        ),
        SwitchTo(Format("{back_btn}"), id="back", state=RideCreateSG.note),
        state=RideCreateSG.confirm,
        getter=get_confirm_data,
    ),
)
