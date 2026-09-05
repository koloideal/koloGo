import logging

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger("seatbot.errors")
error_router = Router()


@error_router.error()
async def on_error(event: ErrorEvent) -> None:
    logger.exception("Unhandled exception", exc_info=event.exception)
