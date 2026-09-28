from typing import Any

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from kologo.application.services.statistics import StatisticsService
from kologo.infrastructure.notifications import fmt_amount

from .states import StatsSG


@inject
async def get_user_stats(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    **_kwargs: Any,
) -> dict[str, Any]:
    user_id = dialog_manager.middleware_data["event_from_user"].id
    stats = await statistics_service.user_stats(user_id)
    if not stats:
        return {"stats_text": "🚫 Пользователь не найден. Нажмите /start", "back_btn": "⬅️ В меню"}

    last_ride = stats.last_ride_at.strftime("%d.%m.%Y") if stats.last_ride_at else "—"
    vip_text = "\n⭐ VIP-статус активен" if stats.is_vip else ""
    text = (
        f"📊 <b>Моя статистика</b>\n\n"
        f"🚗 Завершённых поездок: <b>{stats.total_rides}</b>\n"
        f"💰 Всего потрачено: <b>{fmt_amount(stats.total_spent)} BYN</b>\n"
        f"💳 Текущий депозит: <b>{fmt_amount(stats.balance)} BYN</b>\n"
        f"📅 Последняя бронь: <b>{last_ride}</b>{vip_text}"
    )
    return {"stats_text": text, "back_btn": "⬅️ В меню"}


stats_dialog = Dialog(
    Window(
        Format("{stats_text}"),
        Cancel(Format("{back_btn}")),
        state=StatsSG.stats,
        getter=get_user_stats,
    ),
)
