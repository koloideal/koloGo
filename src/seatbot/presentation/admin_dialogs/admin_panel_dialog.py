from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Row, Start
from aiogram_dialog.widgets.text import Const

from ..user_dialogs.states import (AdminPanelSG, AdminStatsSG, BroadcastSG, RideCreateSG,
                                   RidesMgmtSG, UsersSG)

admin_panel_dialog = Dialog(
    Window(
        Const(
            "🚗 <b>Панель водителя</b>\n\n"
            "Создавай поездки, управляй бронями и клиентами.\n\n"
            "<i><b>made by kolo</b></i>"
        ),
        Row(
            Start(Const("➕ Создать поездку"), id="ride_create", state=RideCreateSG.select_template),
            Start(Const("🚗 Мои поездки"), id="rides_mgmt", state=RidesMgmtSG.rides_list),
        ),
        Row(
            Start(Const("👥 Клиенты"), id="users", state=UsersSG.users_list),
            Start(Const("� Статистика"), id="stats", state=AdminStatsSG.stats),
        ),
        Row(
            Start(Const("� Рассылка"), id="broadcast", state=BroadcastSG.text),
        ),
        state=AdminPanelSG.main,
    ),
)
