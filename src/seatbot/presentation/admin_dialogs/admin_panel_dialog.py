from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Row, Start
from aiogram_dialog.widgets.text import Const

from ..user_dialogs.states import (AdminPanelSG, AdminRequisitesSG, AdminSettingsSG,
                                   AdminStatsSG, BroadcastSG, RideCreateSG, RidesMgmtSG,
                                   UsersSG)

admin_panel_dialog = Dialog(
    Window(
        Const(
            "🚗 Привет, <b>Создатель</b>, rewrite in Rust please\n\n"
            "<i><b>made by kolo</b></i>"
        ),
        Row(
            Start(Const("➕ Создать поездку"), id="ride_create", state=RideCreateSG.select_template),
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
    ),
)
