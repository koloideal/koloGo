from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer

from seatbot.infrastructure.scheduling.tasks import check_cryptobot_payment_status


class PaymentStatusPoller:
    def __init__(self, scheduler: AsyncIOScheduler, app_container: AsyncContainer) -> None:
        self._scheduler = scheduler
        self._app_container = app_container

    def start_polling(self, payment_id: str) -> None:
        self._scheduler.add_job(
            check_cryptobot_payment_status,
            trigger="interval",
            seconds=5,
            id=f"check_payment_{payment_id}",
            kwargs={"payment_id": payment_id, "container": self._app_container},
            max_instances=1,
            replace_existing=True,
        )
