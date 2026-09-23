from html import escape
from typing import Any

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.statistics import StatisticsService
from seatbot.domain.schemas import RideGeoStats
from seatbot.infrastructure.notifications import fmt_amount, fmt_duration

from ..user_dialogs.states import AdminStatsSG


@inject
async def get_admin_stats(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    **_kwargs: Any,
) -> dict[str, Any]:
    stats = await statistics_service.overall_stats()
    text = (
        "📊 <b>Общая статистика</b>\n\n"
        f"👥 Клиентов: <b>{stats.total_users}</b>\n"
        f"🚗 Поездок создано: <b>{stats.total_rides_created}</b>\n"
        f"✅ Завершено поездок: <b>{stats.total_completed_rides}</b>\n"
        f"🟢 Открытых поездок: <b>{stats.active_rides}</b>\n\n"
        f"💰 Доход с депозита: <b>{fmt_amount(stats.deposit_revenue)} BYN</b>\n"
        f"💵 Оплачено по факту: <b>{fmt_amount(stats.fact_revenue)} BYN</b>\n"
        f"Σ Итого: <b>{fmt_amount(stats.total_revenue)} BYN</b>"
    )
    if stats.geo:
        text += "\n\n" + _geo_block(stats.geo)
    return {"stats_text": text, "back_btn": "⬅️ В панель"}


def _geo_block(geo: RideGeoStats) -> str:
    lines = ["🗺 <b>Маршруты</b>"]
    if geo.top_route:
        lines.append(
            f"🔁 Частый маршрут: <b>{escape(geo.top_route[0])} → {escape(geo.top_route[1])}</b> "
            f"({geo.top_route[2]})"
        )
    if geo.top_origin:
        lines.append(f"📍 Частая точка отправления: <b>{escape(geo.top_origin[0])}</b> ({geo.top_origin[1]})")
    if geo.top_destination:
        lines.append(
            f"🏁 Частая точка прибытия: <b>{escape(geo.top_destination[0])}</b> ({geo.top_destination[1]})"
        )
    lines.append(
        f"🧍 Пассажиров в среднем: <b>{geo.avg_passengers:.1f}</b> (заполняемость {geo.avg_fill_ratio:.0%})"
    )
    lines.append("")
    lines.append(f"🛰 <b>Трекинг</b> (поездок с треком: {geo.tracked_rides})")
    if not geo.tracked_rides:
        lines.append("Пока нет поездок с записанным треком.")
        return "\n".join(lines)
    lines += [
        f"🛣 Проехано всего: <b>{geo.total_distance_m / 1000:.1f} км</b>",
        f"⏱ В пути всего: <b>{fmt_duration(geo.total_duration_s)}</b>",
        f"⚡ Ср. скорость: <b>{geo.avg_speed_kmh:.0f} км/ч</b>",
        f"🚀 Макс. скорость: <b>{geo.max_speed_mps * 3.6:.0f} км/ч</b>",
        f"📏 Ср. поездка: <b>{geo.avg_distance_m / 1000:.1f} км</b> за <b>{fmt_duration(geo.avg_duration_s)}</b>",
        f"🏆 Самая длинная: <b>{geo.longest_ride_m / 1000:.1f} км</b>",
        f"👥 Пассажиро-км: <b>{geo.passenger_distance_m / 1000:.0f}</b>",
    ]
    if geo.avg_departure_delay_s is not None:
        delay_min = geo.avg_departure_delay_s / 60
        label = "позже" if delay_min >= 0 else "раньше"
        lines.append(f"🕒 Выезд в среднем: <b>на {abs(delay_min):.0f} мин {label}</b> плана")
    return "\n".join(lines)


statistics_dialog = Dialog(
    Window(
        Format("{stats_text}"),
        Cancel(Format("{back_btn}")),
        state=AdminStatsSG.stats,
        getter=get_admin_stats,
    ),
)
