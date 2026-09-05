from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Start
from aiogram_dialog.widgets.text import Const

from ..user_dialogs.states import (AdminPanelSG, AdminStatsSG, BroadcastSG, RideCreateSG,
                                   RidesMgmtSG, UsersSG)

admin_panel_dialog = Dialog(
    Window(
        Const(
            "<b>🚗 Панель водителя</b>\n\n"
            "Управление поездками, клиентами и депозитами."
        ),
        Start(Const("🚗 Мои поездки"), id="rides_mgmt", state=RidesMgmtSG.rides_list),
        Start(Const("➕ Создать поездку"), id="ride_create", state=RideCreateSG.departure),
        Start(Const("👥 Клиенты"), id="users", state=UsersSG.users_list),
        Start(Const("📢 Рассылка"), id="broadcast", state=BroadcastSG.text),
        Start(Const("📊 Статистика"), id="stats", state=AdminStatsSG.stats),
        state=AdminPanelSG.main,
    ),
)
