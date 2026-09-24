import logging
from typing import Any, Literal

import aiohttp

from seatbot.infrastructure.config.models import CryptoBotConfig
from seatbot.infrastructure.payments.models import CryptoBotPayment

logger = logging.getLogger(__name__)


class CryptoBotPaymentService:
    def __init__(self, config: CryptoBotConfig) -> None:
        self._token = config.api_token
        self._base_url = config.api_url.rstrip("/") + "/"
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Crypto-Pay-API-Token": self._token,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self._base_url + endpoint.lstrip("/")
        session = await self._get_session()
        logger.debug("CryptoBot API %s %s params=%s", method, url, params)
        try:
            if method.upper() == "GET":
                async with session.get(url, params=params) as response:
                    return await self._parse_response(response, method, endpoint)
            elif method.upper() == "POST":
                async with session.post(url, json=params) as response:
                    return await self._parse_response(response, method, endpoint)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
        except aiohttp.ClientError:
            # Reset session on network errors
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            raise

    async def _parse_response(self, response: aiohttp.ClientResponse, method: str, endpoint: str) -> Any:
        if response.status >= 400:
            text = await response.text()
            logger.error("CryptoBot API error %s %s → %d: %s", method, endpoint, response.status, text)
            response.raise_for_status()
        data = await response.json()
        logger.debug("CryptoBot API response %s %s: %s", method, endpoint, data)
        if not data.get("ok"):
            error = data.get("error", {})
            raise ConnectionError(
                f"API Error: {error.get('name', 'Unknown')} - {error.get('message', 'No details')}"
            )
        return data.get("result")

    async def create_payment(
        self, amount: float, asset: str = "USDT", expires_in: int | None = None
    ) -> CryptoBotPayment:
        params: dict[str, Any] = {
            "amount": str(amount),
            "asset": asset,
            "description": "Пополнение баланса SeatBot",
        }
        if expires_in:
            params["expires_in"] = expires_in
        logger.info("Creating CryptoBot invoice: amount=%s %s", amount, asset)
        result = await self._make_request("POST", "createInvoice", params=params)
        logger.info("CryptoBot invoice created: invoice_id=%s", result.get("invoice_id"))
        return CryptoBotPayment.from_dict(result, status="waiting")

    async def check_payment(self, invoice_id: str) -> Literal["paid", "not_paid"]:
        params = {"invoice_ids": invoice_id}
        invoices_data = await self._make_request("GET", "getInvoices", params=params)
        items = invoices_data.get("items", [])
        if not items:
            logger.warning("CryptoBot getInvoices returned no items for invoice_id=%s", invoice_id)
            return "not_paid"
        result: dict[str, Any] = items[0]
        invoice_status = result.get("status", "unknown")
        logger.info("CryptoBot invoice %s status=%s", invoice_id, invoice_status)
        return "paid" if invoice_status == "paid" else "not_paid"

    async def delete_invoice(self, invoice_id: str) -> bool:
        try:
            return bool(
                await self._make_request("POST", "deleteInvoice", params={"invoice_id": int(invoice_id)})
            )
        except (aiohttp.ClientError, ConnectionError, ValueError):
            logger.warning("CryptoBot deleteInvoice(%s) failed", invoice_id, exc_info=True)
            return False
