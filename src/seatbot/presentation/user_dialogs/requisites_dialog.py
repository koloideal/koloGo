from typing import Any

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.kbd import Cancel, CopyText, ListGroup
from aiogram_dialog.widgets.text import Format
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from seatbot.domain.schemas import Requisite
from seatbot.infrastructure.database.dao import RequisitesDAO

from .states import RequisitesSG


@inject
async def get_requisites(
    dialog_manager: DialogManager,
    requisites_dao: FromDishka[RequisitesDAO],
    **_kwargs: Any,
) -> dict[str, Any]:
    requisites = await requisites_dao.list_all()
    if not requisites:
        text = "💳 <b>Реквизиты</b>\n\nРеквизитов пока нет."
    else:
        text = "💳 <b>Реквизиты</b>\n\nНажмите на реквизит, чтобы скопировать значение."
    return {
        "requisites_text": text,
        "requisites": requisites,
    }


def _item_id_getter(item: Requisite) -> int:
    return item.requisite_id


requisites_dialog = Dialog(
    Window(
        Format("{requisites_text}"),
        ListGroup(
            CopyText(
                text=Format("{item.title}"),
                copy_text=Format("{item.value}"),
            ),
            id="requisites_list",
            item_id_getter=_item_id_getter,
            items="requisites",
            when="requisites",
        ),
        Cancel(Format("⬅️ В меню")),
        state=RequisitesSG.list,
        getter=get_requisites,
    )
)
