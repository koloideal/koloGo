from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.domain.schemas import TransactionType
from seatbot.infrastructure.database.dao import TransactionsDAO, UsersDAO

from .states import BalanceSG


@inject
async def get_balance(
    dialog_manager: DialogManager,
    users_dao: FromDishka[UsersDAO],
    transactions_dao: FromDishka[TransactionsDAO],
    **_kwargs,
):
    user_id = dialog_manager.middleware_data["event_from_user"].id
    user = await users_dao.get_by_id(user_id)
    if not user:
        return {"balance_text": "🚫 Пользователь не найден. Нажмите /start", "back_btn": "⬅️ В меню"}

    transactions = await transactions_dao.list_for_user(user_id, limit=10)
    vip_text = "\n⭐ VIP-статус: все поездки бесплатны!" if user.is_vip else ""

    lines = [
        "💰 <b>Ваш депозит</b>\n\n",
        f"Текущий баланс: <b>{user.balance:.2f} BYN</b>{vip_text}\n\n",
        "📝 <b>Последние операции:</b>\n",
    ]
    if not transactions:
        lines.append("Пока нет операций.")
    else:
        for t in transactions:
            sign = "+" if t.amount > 0 else ""
            type_label = {
                TransactionType.ADMIN_TOPUP: "Пополнение",
                TransactionType.ADMIN_DECREASE: "Списание",
                TransactionType.RIDE_PAYMENT: "Оплата поездки",
                TransactionType.REFUND: "Возврат",
            }.get(t.type, t.type.value)
            lines.append(f"• {t.created_at.strftime('%d.%m %H:%M')} {type_label}: {sign}{t.amount:.2f}")

    return {
        "balance_text": "".join(lines),
        "back_btn": "⬅️ В меню",
    }


balance_dialog = Dialog(
    Window(
        Format("{balance_text}"),
        Cancel(Format("{back_btn}")),
        state=BalanceSG.balance,
        getter=get_balance,
    ),
)
