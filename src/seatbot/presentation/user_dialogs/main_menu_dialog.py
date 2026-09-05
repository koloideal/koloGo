from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Row, Start
from aiogram_dialog.widgets.text import Const

from .states import BalanceSG, MainMenuSG, MyBookingsSG, RidesSG, StatsSG

main_menu_dialog = Dialog(
    Window(
        Const(
            "<b>🚗 SeatBot — поездки в Минск</b>\n\n"
            "Я — студент колледжа, подкидываю людей до Минска после пар.\n"
            "Всего 4 места на поездку. Бронируй заранее!"
        ),
        Row(
            Start(Const("🚗 Поездки"), id="rides", state=RidesSG.list),
            Start(Const("📋 Мои брони"), id="mybookings", state=MyBookingsSG.list),
        ),
        Row(
            Start(Const("💰 Депозит"), id="balance", state=BalanceSG.balance),
            Start(Const("📊 Статистика"), id="stats", state=StatsSG.stats),
        ),
        state=MainMenuSG.main,
    ),
)
