from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.statistics import StatisticsService
from seatbot.infrastructure.notifications import fmt_amount

from ..user_dialogs.states import AdminStatsSG


@inject
async def get_admin_stats(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    **_kwargs,
):
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
    return {"stats_text": text, "back_btn": "⬅️ В панель"}


statistics_dialog = Dialog(
    Window(
        Format("{stats_text}"),
        Cancel(Format("{back_btn}")),
        state=AdminStatsSG.stats,
        getter=get_admin_stats,
    ),
)
