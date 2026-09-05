from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Start
from aiogram_dialog.widgets.text import Const

from .states import BalanceSG, MainMenuSG, MyBookingsSG, RidesSG, StatsSG

main_menu_dialog = Dialog(
    Window(
        Const(
            "<b>🚗 SeatBot — поездки в Минск</b>\n\n"
            "Я — студент колледжа, подкидываю людей до Минска после пар.\n"
            "Всего 4 места на поездку. Бронируй заранее!"
        ),
        Start(Const("🚗 Ближайшие поездки"), id="rides", state=RidesSG.list),
        Start(Const("📋 Мои брони"), id="mybookings", state=MyBookingsSG.list),
        Start(Const("💰 Мой депозит"), id="balance", state=BalanceSG.balance),
        Start(Const("📊 Моя статистика"), id="stats", state=StatsSG.stats),
        state=MainMenuSG.main,
    ),
)
