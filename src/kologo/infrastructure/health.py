import logging

from aiohttp import web

from kologo.infrastructure.config.models import HealthConfig

logger = logging.getLogger(__name__)


class HealthServer:
    def __init__(self, config: HealthConfig) -> None:
        self._config = config
        self._runner: web.AppRunner | None = None

    @staticmethod
    async def _health(_: web.Request) -> web.Response:
        return web.Response(text="OK")

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(self._config.path, self._health)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self._config.host, self._config.port).start()
        logger.info(
            "Health endpoint on http://%s:%s%s", self._config.host, self._config.port, self._config.path
        )

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
