from typing import Any

from aiogram import F
from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Button, Row, Start
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.ride import RideService
from kologo.domain.schemas import RideStatus, RideWithStats
from kologo.infrastructure.notifications import MessageBuilder, route_str

from ..user_dialogs.states import (AdminPanelSG, AdminRequisitesSG, AdminSettingsSG,
                                   AdminStatsSG, BroadcastSG, PendingSG, RideCreateSG,
                                   RidesMgmtSG, UsersSG)


def _ride_line(messages: MessageBuilder, rws: RideWithStats) -> str:
    route = route_str(rws.ride)
    return (
        f"🕒 {messages.short_date(rws.ride.departure_at)}" + (f" · {route}" if route else "") + "\n"
        f"{messages.seats_line(rws.ride, rws.approved_seats, rws.pending_seats)}"
    )


@inject
async def get_panel(
    dialog_manager: DialogManager,
    ride_service: FromDishka[RideService],
    messages: FromDishka[MessageBuilder],
    **_kwargs: Any,
) -> dict[str, Any]:
    lines = ["🚗 Привет, <b>Создатель</b>\n"]
    in_progress = await ride_service.get_in_progress_ride()
    upcoming = next(iter(await ride_service.list_active_rides()), None)
    pending_count = len(await ride_service.list_pending_bookings())

    if in_progress and (rws := await ride_service.get_ride_stats(in_progress.ride_id)):
        dialog_manager.dialog_data["in_progress_id"] = in_progress.ride_id
        lines += [
            "🚙 <b>Сейчас в пути</b>",
            _ride_line(messages, rws),
            f"🛣 Проехано: {in_progress.track_distance_m / 1000:.1f} км\n",
        ]
    if upcoming and (rws := await ride_service.get_ride_stats(upcoming.ride_id)):
        dialog_manager.dialog_data["upcoming_id"] = upcoming.ride_id
        lines += ["🗓 <b>Ближайшая поездка</b>", _ride_line(messages, rws) + "\n"]
    elif not in_progress:
        lines.append("🗓 Запланированных поездок нет.\n")
    lines.append(
        f"⏳ Заявок ждут решения: <b>{pending_count}</b>" if pending_count else "✨ Все заявки разобраны"
    )
    lines.append("\n<i><b>made by kolo</b></i>")
    return {
        "panel_text": "\n".join(lines),
        "has_in_progress": in_progress is not None and in_progress.status == RideStatus.IN_PROGRESS,
        "has_upcoming": upcoming is not None,
        "pending_btn": f"⏳ Заявки ({pending_count})" if pending_count else "⏳ Заявки",
        "has_templates": bool(await ride_service.list_templates(limit=1)),
    }


async def on_open_in_progress(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.start(RidesMgmtSG.ride_detail, data={"ride_id": manager.dialog_data["in_progress_id"]})


async def on_open_upcoming(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await manager.start(RidesMgmtSG.ride_detail, data={"ride_id": manager.dialog_data["upcoming_id"]})


admin_panel_dialog = Dialog(
    Window(
        Format("{panel_text}"),
        Row(
            Button(
                Const("🚙 В пути"), id="in_progress", on_click=on_open_in_progress, when="has_in_progress"
            ),
            Button(Const("🗓 Ближайшая"), id="upcoming", on_click=on_open_upcoming, when="has_upcoming"),
        ),
        Start(Format("{pending_btn}"), id="pending", state=PendingSG.list),
        Row(
            Start(
                Const("➕ Создать поездку"),
                id="ride_create",
                state=RideCreateSG.select_template,
                when="has_templates",
            ),
            Start(
                Const("➕ Создать поездку"),
                id="ride_create_direct",
                state=RideCreateSG.calendar,
                when=~F["has_templates"],
            ),
            Start(Const("🚗 Мои поездки"), id="rides_mgmt", state=RidesMgmtSG.rides_list),
        ),
        Row(
            Start(Const("👥 Клиенты"), id="users", state=UsersSG.users_list),
            Start(Const("📊 Статистика"), id="stats", state=AdminStatsSG.stats),
        ),
        Row(
            Start(Const("💸 Реквизиты"), id="requisites", state=AdminRequisitesSG.list),
            Start(Const("💬 Рассылка"), id="broadcast", state=BroadcastSG.text),
        ),
        Start(Const("⚙️ Настройки"), id="settings", state=AdminSettingsSG.main),
        state=AdminPanelSG.main,
        getter=get_panel,
    ),
)
