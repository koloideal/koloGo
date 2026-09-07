from dataclasses import dataclass
from typing import Any, Literal, Self


@dataclass(frozen=True)
class CryptoBotPayment:
    invoice_id: int
    bot_invoice_url: str
    amount: str
    asset: str
    status: Literal["waiting", "paid", "not_paid"]

    @classmethod
    def from_dict(
        cls, data: dict[str, Any], status: Literal["waiting", "paid", "not_paid"]
    ) -> Self:
        return cls(
            invoice_id=data["invoice_id"],
            bot_invoice_url=data["bot_invoice_url"],
            amount=data["amount"],
            asset=data["asset"],
            status=status,
        )
