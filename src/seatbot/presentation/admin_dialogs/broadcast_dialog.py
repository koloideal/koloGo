from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.broadcast import BroadcastService

from ..user_dialogs.states import AdminPanelSG, BroadcastSG


async def on_broadcast_message_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
):
    """Принимает любое сообщение — текст, фото, видео, голос, и т.д."""
    if not message or not message.message_id:
        await message.answer("❌ Не удалось получить сообщение.")
        return
    manager.dialog_data["from_chat_id"] = message.chat.id
    manager.dialog_data["message_id"] = message.message_id
    await manager.next()


async def get_broadcast_confirm(dialog_manager: DialogManager, **_kwargs):
    from_chat_id: int = dialog_manager.dialog_data.get("from_chat_id", 0)
    message_id: int = dialog_manager.dialog_data.get("message_id", 0)
    has_msg = bool(from_chat_id and message_id)
    return {
        "has_msg": has_msg,
        "send_btn": "📢 Отправить всем",
        "back_btn": "⬅️ Назад",
    }


@inject
async def on_send_broadcast(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    broadcast_service: FromDishka[BroadcastService],
):
    from_chat_id: int = manager.dialog_data["from_chat_id"]
    message_id: int = manager.dialog_data["message_id"]
    await callback.answer("📤 Рассылка запущена в фоне. Статистика придёт позже.")
    broadcast_service.start_broadcast(from_chat_id, message_id)
    await manager.start(AdminPanelSG.main, mode=StartMode.RESET_STACK)


broadcast_dialog = Dialog(
    Window(
        Const(
            "📢 <b>Рассылка</b>\n\n"
            "Отправьте любое сообщение — текст, фото, видео, голосовое, файл.\n"
            "Оно будет скопировано и отправлено всем пользователям."
        ),
        MessageInput(on_broadcast_message_input),
        Cancel(Const("⬅️ Отмена")),
        state=BroadcastSG.text,
    ),
    Window(
        Const("📋 <b>Сообщение получено.</b>\n\nОтправляем всем пользователям?"),
        Button(Format("{send_btn}"), id="send", on_click=on_send_broadcast, when="has_msg"),
        SwitchTo(Format("{back_btn}"), id="back", state=BroadcastSG.text),
        state=BroadcastSG.confirm,
        getter=get_broadcast_confirm,
    ),
)
