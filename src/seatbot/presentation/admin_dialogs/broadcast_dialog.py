from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Cancel, SwitchTo
from aiogram_dialog.widgets.text import Const, Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.application.services.broadcast import BroadcastService

from ..user_dialogs.states import AdminSG


async def on_broadcast_text_input(message: Message, widget: MessageInput, manager: DialogManager):
    text = (message.text or "").strip()
    if not text or len(text) > 4096:
        await message.answer("❌ Текст пустой или слишком длинный (макс. 4096 символов).")
        return
    manager.dialog_data["broadcast_text"] = text
    await manager.next()


async def get_broadcast_confirm(dialog_manager: DialogManager, **_kwargs):
    text: str = dialog_manager.dialog_data.get("broadcast_text", "")
    return {"preview_text": text, "send_btn": "📢 Отправить всем", "back_btn": "⬅️ Назад"}


@inject
async def on_send_broadcast(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
    broadcast_service: FromDishka[BroadcastService],
):
    text: str = manager.dialog_data["broadcast_text"]
    await callback.answer("📤 Рассылка началась...")
    success, total = await broadcast_service.broadcast(text)
    if callback.message:
        await callback.message.answer(f"✅ Рассылка завершена.\nОтправлено: {success}/{total}")
    await manager.start(AdminSG.main, mode=StartMode.RESET_STACK)


broadcast_dialog = Dialog(
    Window(
        Const(
            "📢 <b>Рассылка</b>\n\n"
            "Введите текст сообщения для всех пользователей:"
        ),
        MessageInput(on_broadcast_text_input),
        Cancel(Const("⬅️ Отмена")),
        state=AdminSG.broadcast_text,
    ),
    Window(
        Const("📋 <b>Предпросмотр:</b>\n\n"),
        Format("{preview_text}"),
        Button(Format("{send_btn}"), id="send", on_click=on_send_broadcast),
        SwitchTo(Format("{back_btn}"), id="back", state=AdminSG.broadcast_text),
        state=AdminSG.broadcast_confirm,
        getter=get_broadcast_confirm,
    ),
)
