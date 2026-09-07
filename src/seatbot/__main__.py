import asyncio
import os
import sys
from logging import Logger, getLogger

import orjson
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram_dialog import setup_dialogs
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import make_async_container
from dishka.integrations.aiogram import setup_dishka
from redis.asyncio import Redis

from seatbot.infrastructure.config import load_config
from seatbot.infrastructure.config.models import Config
from seatbot.infrastructure.ioc import (DatabaseProvider, RedisProvider,
                                        SchedulerProvider, ServicesProvider, TimeProvider,
                                        UserAppProvider)
from seatbot.infrastructure.logging.logger import setup_logging
from seatbot.presentation.middlewares.check_ban import CheckBanMiddleware
from seatbot.presentation.middlewares.reject_not_admin import RejectNotAdminMiddleware

config: Config = load_config("secret_data/config.toml")
bot_token: str = config.bot.token

session = AiohttpSession(timeout=30)
bot: Bot = Bot(
    token=bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=session,
)

logger: Logger = getLogger("seatbot")
os.makedirs("logs", exist_ok=True)
setup_logging("secret_data/logger-config.json")

container = make_async_container(
    DatabaseProvider(),
    RedisProvider(),
    TimeProvider(),
    SchedulerProvider(),
    ServicesProvider(),
    UserAppProvider(),
    context={Config: config, Bot: bot},
)

fsm_redis: Redis = Redis.from_url(config.redis.fsm_dsn, decode_responses=True, max_connections=5)
storage: RedisStorage = RedisStorage(
    fsm_redis,
    key_builder=DefaultKeyBuilder(with_destiny=True),
    json_dumps=lambda data: orjson.dumps(data).decode(),
    json_loads=orjson.loads,
    state_ttl=9000,
    data_ttl=7200,
)
logger.critical("Successful connecting to Redis")
dp: Dispatcher = Dispatcher(storage=storage)


async def main() -> None:
    from seatbot.presentation.admin_dialogs import \
        admin_panel_dialog as admin_panel_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        broadcast_dialog as broadcast_dialog_mod
    from seatbot.presentation.admin_dialogs import deposit_dialog as deposit_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        requisites_dialog as admin_requisites_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        ride_create_dialog as ride_create_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        ride_detail_dialog as ride_detail_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        rides_management_dialog as rides_management_dialog_mod
    from seatbot.presentation.admin_dialogs import settings_dialog as settings_dialog_mod
    from seatbot.presentation.admin_dialogs import \
        statistics_dialog as statistics_dialog_mod
    from seatbot.presentation.admin_dialogs import users_dialog as users_dialog_mod
    from seatbot.presentation.admin_handlers import admin_router
    from seatbot.presentation.error_handlers import error_router
    from seatbot.presentation.user_dialogs import main_menu_dialog as main_menu_dialog_mod
    from seatbot.presentation.user_dialogs import \
        my_bookings_dialog as my_bookings_dialog_mod
    from seatbot.presentation.user_dialogs import \
        requisites_dialog as user_requisites_dialog_mod
    from seatbot.presentation.user_dialogs import rides_dialog as rides_dialog_mod
    from seatbot.presentation.user_dialogs import stats_dialog as stats_dialog_mod
    from seatbot.presentation.user_dialogs import vip_dialog as vip_dialog_mod
    from seatbot.presentation.user_handlers import user_router

    dp.include_routers(error_router, user_router, admin_router)
    dp.include_routers(
        main_menu_dialog_mod.main_menu_dialog,
        rides_dialog_mod.rides_dialog,
        my_bookings_dialog_mod.my_bookings_dialog,
        user_requisites_dialog_mod.requisites_dialog,
        stats_dialog_mod.stats_dialog,
        vip_dialog_mod.vip_dialog,
    )
    dp.include_routers(
        admin_panel_dialog_mod.admin_panel_dialog,
        rides_management_dialog_mod.rides_management_dialog,
        ride_create_dialog_mod.ride_create_dialog,
        ride_detail_dialog_mod.ride_detail_dialog,
        users_dialog_mod.users_dialog,
        deposit_dialog_mod.deposit_dialog,
        admin_requisites_dialog_mod.requisites_dialog,
        broadcast_dialog_mod.broadcast_dialog,
        statistics_dialog_mod.statistics_dialog,
        settings_dialog_mod.settings_dialog,
    )

    admin_router.message.middleware(RejectNotAdminMiddleware())
    admin_router.callback_query.middleware(RejectNotAdminMiddleware())

    dp.update.middleware(CheckBanMiddleware())

    setup_dialogs(dp)
    setup_dishka(router=dp, container=container, auto_inject=True)

    from seatbot.application.services.bot import BotService

    async with container() as nested_container:
        bot_service = await nested_container.get(BotService)
        await bot_service.process_set_commands()

    await bot.delete_webhook(drop_pending_updates=True)

    scheduler = await container.get(AsyncIOScheduler)
    scheduler.start()

    logger.critical("Starting SeatBot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.critical("End of work...")
        sys.exit()
