import logging
from typing import Any, Literal, cast

import aiohttp

from seatbot.infrastructure.config.models import CryptoBotConfig
from seatbot.infrastructure.payments.models import CryptoBotPayment

logger = logging.getLogger(__name__)


class CryptoBotPaymentService:
    def __init__(self, config: CryptoBotConfig) -> None:
        self._token = config.api_token
        self._base_url = config.api_url.rstrip("/") + "/"

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = {
            "Content-Type": "application/json",
            "Crypto-Pay-API-Token": self._token,
        }
        url = self._base_url + endpoint.lstrip("/")
        async with aiohttp.ClientSession(headers=headers) as session:
            if method.upper() == "GET":
                async with session.get(url, params=params) as response:
                    return await self._parse_response(response, method, endpoint)
            elif method.upper() == "POST":
                async with session.post(url, json=params) as response:
                    return await self._parse_response(response, method, endpoint)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

    async def _parse_response(
        self, response: aiohttp.ClientResponse, method: str, endpoint: str
    ) -> Any:
        if response.status >= 400:
            text = await response.text()
            logger.error("CryptoBot API error %s %s → %d: %s", method, endpoint, response.status, text)
            response.raise_for_status()
        data = await response.json()
        if not data.get("ok"):
            error = data.get("error", {})
            raise ConnectionError(
                f"API Error: {error.get('name', 'Unknown')} - {error.get('message', 'No details')}"
            )
        return data.get("result")

    async def create_payment(self, amount: float, asset: str = "USDT") -> CryptoBotPayment:
        params = {
            "amount": str(amount),
            "asset": asset,
            "description": "Пополнение баланса SeatBot",
        }
        result = await self._make_request("POST", "createInvoice", params=params)
        return CryptoBotPayment.from_dict(result, status="waiting")

    async def check_payment(self, invoice_id: str) -> Literal["paid", "not_paid"]:
        params = {"invoice_ids": invoice_id}
        invoices_data = await self._make_request("GET", "getInvoices", params=params)
        items = invoices_data.get("items", [])
        if not items:
            return "not_paid"
        result: dict[str, str] = items[0]
        return cast(Literal["paid", "not_paid"], "not_paid" if result["status"] == "active" else "paid")
