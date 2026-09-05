from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.statistics import StatisticsService

from ..user_dialogs.states import AdminSG


@inject
async def get_admin_stats(
    dialog_manager: DialogManager,
    statistics_service: FromDishka[StatisticsService],
    **_kwargs,
):
    stats = await statistics_service.overall_stats()
    text = (
        "📊 <b>Общая статистика</b>\n\n"
        f"👥 Всего пользователей: <b>{stats.total_users}</b>\n"
        f"🚗 Поездок создано: <b>{stats.total_rides_created}</b>\n"
        f"✅ Завершено поездок: <b>{stats.total_completed_rides}</b>\n"
        f"🟢 Активных поездок: <b>{stats.active_rides}</b>\n"
        f"💰 Общий доход: <b>{stats.total_revenue:.2f} BYN</b>"
    )
    return {"stats_text": text, "back_btn": "⬅️ В панель"}


statistics_dialog = Dialog(
    Window(
        Format("{stats_text}"),
        Cancel(Const("{back_btn}")),
        state=AdminSG.stats,
        getter=get_admin_stats,
    ),
)
