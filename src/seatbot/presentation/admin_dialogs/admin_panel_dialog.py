from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Start
from aiogram_dialog.widgets.text import Const

from ..user_dialogs.states import AdminSG

admin_panel_dialog = Dialog(
    Window(
        Const(
            "<b>🚗 Панель водителя</b>\n\n"
            "Управление поездками, клиентами и депозитами."
        ),
        Start(Const("🚗 Мои поездки"), id="rides_mgmt", state=AdminSG.rides_list),
        Start(Const("➕ Создать поездку"), id="ride_create", state=AdminSG.ride_create_departure),
        Start(Const("👥 Клиенты"), id="users", state=AdminSG.users_list),
        Start(Const("📢 Рассылка"), id="broadcast", state=AdminSG.broadcast_text),
        Start(Const("📊 Статистика"), id="stats", state=AdminSG.stats),
        state=AdminSG.main,
    ),
)
