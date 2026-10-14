"""The hosted balance portal: mint a link for one of your customers.

Only the mint is here. The two reads behind the page — the balance and the ledger — are made by
the person holding the link, with the link's own token; this client holds a secret key, and the
two must never be the same credential.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._http import RequestSpec
from ..types import PortalLinkRequest, PortalLinkResponse

if TYPE_CHECKING:
    from ..client import AsyncMeterFlow, MeterFlow

_DOC = """Mint a link to the hosted balance page for one of your customers.

        Call this from **your** server and send the ``url`` to that customer. It carries a
        short-lived token that reads their balance and their ledger and nothing else, in the
        environment of the key you called with; it is never your API key and it can write nothing.

        The page shows the balance and sends "buy more" to your own checkout (``topup_url``):
        MeterFlow never takes the payment. ``expires_in_minutes`` defaults to 60, maximum 1440.
        """


def create_session_spec(body: PortalLinkRequest) -> RequestSpec:
    return RequestSpec("POST", "portal/sessions", body=body)


class PortalResource:
    def __init__(self, client: MeterFlow) -> None:
        self._client = client

    def create_session(self, body: PortalLinkRequest) -> PortalLinkResponse:
        result: PortalLinkResponse = self._client.request(create_session_spec(body))
        return result

    create_session.__doc__ = _DOC


class AsyncPortalResource:
    def __init__(self, client: AsyncMeterFlow) -> None:
        self._client = client

    async def create_session(self, body: PortalLinkRequest) -> PortalLinkResponse:
        result: PortalLinkResponse = await self._client.request(create_session_spec(body))
        return result

    create_session.__doc__ = _DOC
