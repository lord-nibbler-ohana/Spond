"""Test suite for Spond class."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from spond import ReadOnlyError
from spond.base import _SpondBase
from spond.spond import Spond

if TYPE_CHECKING:
    from spond import JSONDict


MOCK_USERNAME, MOCK_PASSWORD = "MOCK_USERNAME", "MOCK_PASSWORD"
MOCK_TOKEN = "MOCK_TOKEN"
MOCK_PAYLOAD = {"accepted": "false", "declineMessage": "sick cannot make it"}


# Mock the `require_authentication` decorator to bypass authentication
def mock_require_authentication(func):
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)

    return wrapper


_SpondBase.require_authentication = mock_require_authentication(Spond.get_event)


@pytest.fixture
def mock_token() -> str:
    return MOCK_TOKEN


@pytest.fixture
def mock_payload() -> JSONDict:
    return MOCK_PAYLOAD


class TestEventMethods:
    @pytest.fixture
    def mock_events(self) -> list[JSONDict]:
        """Mock a minimal list of events."""
        return [
            {
                "id": "ID1",
                "name": "Event One",
            },
            {
                "id": "ID2",
                "name": "Event Two",
            },
        ]

    @pytest.mark.asyncio
    async def test_get_event__happy_path(
        self, mock_events: list[JSONDict], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching event."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token
        g = await s.get_event("ID1")

        assert g == {
            "id": "ID1",
            "name": "Event One",
        }

    @pytest.mark.asyncio
    async def test_get_event__no_match_raises_exception(
        self, mock_events: list[JSONDict], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("ID3")

    @pytest.mark.asyncio
    async def test_get_event__blank_id_match_raises_exception(
        self, mock_events: list[JSONDict], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.events = mock_events
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_event("")

    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.put")
    async def test_change_response(self, mock_put, mock_payload, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_response_data = {
            "acceptedIds": ["PID1", "PID2"],
            "declinedIds": ["PID3"],
            "unansweredIds": [],
            "waitinglistIds": [],
            "unconfirmedIds": [],
            "declineMessages": {"PID3": "sick cannot make it"},
        }
        mock_put.return_value.__aenter__.return_value.status = 200
        mock_put.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_response_data
        )

        response = await s.change_response(uid="ID1", user="PID3", payload=mock_payload)

        mock_url = "https://api.spond.com/core/v1/sponds/ID1/responses/PID3"
        mock_put.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
            json=mock_payload,
        )
        assert response == mock_response_data


class TestGroupMethods:
    @pytest.fixture
    def mock_groups(self) -> list[JSONDict]:
        """Mock a minimal list of groups."""
        return [
            {
                "id": "ID1",
                "name": "Group One",
            },
            {
                "id": "ID2",
                "name": "Group Two",
            },
        ]

    @pytest.mark.asyncio
    async def test_get_group__happy_path(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a valid `id` returns the matching group."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token
        g = await s.get_group("ID2")

        assert g == {
            "id": "ID2",
            "name": "Group Two",
        }

    @pytest.mark.asyncio
    async def test_get_group__no_match_raises_exception(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a non-matched `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("ID3")

    @pytest.mark.asyncio
    async def test_get_group__blank_id_raises_exception(
        self, mock_groups: list[JSONDict], mock_token
    ) -> None:
        """Test that a blank `id` raises KeyError."""

        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.groups = mock_groups
        s.token = mock_token

        with pytest.raises(KeyError):
            await s.get_group("")


class TestExportMethod:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_export(self, mock_get, mock_token) -> None:
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_binary = b"\x68\x65\x6c\x6c\x6f\x77\x6f\x72\x6c\x64"  # helloworld
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.read = AsyncMock(
            return_value=mock_binary
        )

        data = await s.get_event_attendance_xlsx(uid="ID1")

        mock_url = "https://api.spond.com/core/v1/sponds/ID1/export"
        mock_get.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
        )
        assert data == mock_binary


class TestReadOnlyMode:
    @pytest.mark.asyncio
    async def test_read_only__update_event_raises(self, mock_token) -> None:
        """update_event raises ReadOnlyError on a read-only instance."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD, read_only=True)
        s.token = mock_token
        with pytest.raises(ReadOnlyError):
            await s.update_event(uid="ID1", updates={"description": "x"})

    @pytest.mark.asyncio
    async def test_read_only__change_response_raises(self, mock_token) -> None:
        """change_response raises ReadOnlyError on a read-only instance."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD, read_only=True)
        s.token = mock_token
        with pytest.raises(ReadOnlyError):
            await s.change_response(uid="ID1", user="PID1", payload={"accepted": "true"})

    @pytest.mark.asyncio
    async def test_read_only__send_message_raises(self, mock_token) -> None:
        """send_message raises ReadOnlyError on a read-only instance."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD, read_only=True)
        s.token = mock_token
        with pytest.raises(ReadOnlyError):
            await s.send_message(text="hello", chat_id="CHAT1")

    @pytest.mark.asyncio
    async def test_read_only__get_events_allowed(
        self, mock_token
    ) -> None:
        """Read methods are still allowed on a read-only instance."""
        mock_events: list[JSONDict] = [{"id": "ID1", "name": "Event One"}]
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD, read_only=True)
        s.token = mock_token
        s.events = mock_events
        result = await s.get_event("ID1")
        assert result == {"id": "ID1", "name": "Event One"}


class TestUpcomingMethod:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession.get")
    async def test_get_upcoming__happy_path(self, mock_get, mock_token) -> None:
        """get_upcoming returns list[JSONDict] and sets s.upcoming."""
        s = Spond(MOCK_USERNAME, MOCK_PASSWORD)
        s.token = mock_token

        mock_upcoming_data: list[JSONDict] = [
            {"id": "EV1", "updated": "2026-02-01T10:00:00Z", "startTime": "2026-03-01T10:00:00Z", "heading": "Training"},
            {"id": "EV2", "updated": "2026-02-02T10:00:00Z", "startTime": "2026-03-05T10:00:00Z", "heading": "Match", "unanswered": True},
        ]
        mock_get.return_value.__aenter__.return_value.status = 200
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value=mock_upcoming_data
        )

        result = await s.get_upcoming()

        mock_url = "https://api.spond.com/core/v1/sponds/upcoming"
        mock_get.assert_called_once_with(
            mock_url,
            headers={
                "content-type": "application/json",
                "Authorization": f"Bearer {mock_token}",
            },
        )
        assert result == mock_upcoming_data
        assert s.upcoming == mock_upcoming_data
