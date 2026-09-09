import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from googleapiclient.errors import HttpError

from discord_hvz import display, sheets


def discord_http_error(status=503, exception_type=discord.HTTPException):
    response = SimpleNamespace(status=status, reason="test failure")
    return exception_type(response, "test failure")


class SheetsErrorHandlingTests(unittest.TestCase):
    def test_export_handles_clear_http_error(self):
        db = Mock()
        db.get_table.return_value = []
        db.get_column_names.return_value = ["id"]
        interface = sheets.SheetsInterface.__new__(sheets.SheetsInterface)
        interface.db = db
        interface.sheet_id = "sheet-id"

        values_api = Mock()
        values_api.clear.return_value.execute.side_effect = HttpError(
            SimpleNamespace(status=503, reason="unavailable"), b"temporary failure", uri="test"
        )
        interface.spreadsheets = Mock()
        interface.spreadsheets.values.return_value = values_api

        with patch.object(interface, "check_creds"):
            # A Sheets outage should be logged and contained by _export.
            interface._export("members")

        values_api.update.assert_not_called()

    def test_read_sheet_returns_zero_for_exception_without_details(self):
        interface = sheets.SheetsInterface.__new__(sheets.SheetsInterface)
        interface.sheet_id = "sheet-id"
        interface.spreadsheets = Mock()
        interface.spreadsheets.values.return_value.get.return_value.execute.side_effect = RuntimeError(
            "connection dropped"
        )

        self.assertEqual(interface.read_sheet("Members", "A:B"), 0)


class PanelErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def make_panel(self, channel, message=None):
        bot = SimpleNamespace(
            guild=SimpleNamespace(get_channel=Mock(return_value=channel)),
            db=SimpleNamespace(delete_row=Mock()),
        )
        cog = SimpleNamespace(bot=bot, delete_panel=Mock())
        panel = display.HVZPanel.__new__(display.HVZPanel)
        panel.cog = cog
        panel.bot = bot
        panel.channel = None
        panel.message = message
        panel.elements = []
        panel.listener_events = set()
        return panel

    async def test_load_removes_missing_message(self):
        channel = SimpleNamespace(
            fetch_message=AsyncMock(side_effect=discord_http_error(404, discord.NotFound))
        )
        panel = self.make_panel(channel)

        # NotFound is the one case where the persistent row is stale.
        result = await panel.load({"channel_id": 10, "message_id": 20, "elements": ""})

        self.assertIsNone(result)
        panel.bot.db.delete_row.assert_called_once_with("persistent_panels", "message_id", 20)

    async def test_load_preserves_row_for_other_http_error(self):
        channel = SimpleNamespace(
            fetch_message=AsyncMock(side_effect=discord_http_error(503))
        )
        panel = self.make_panel(channel)

        result = await panel.load({"channel_id": 10, "message_id": 20, "elements": ""})

        self.assertIsNone(result)
        panel.bot.db.delete_row.assert_not_called()

    async def test_refresh_removes_panel_when_message_is_gone(self):
        message = SimpleNamespace(id=20, edit=AsyncMock(side_effect=discord_http_error(404, discord.NotFound)))
        panel = self.make_panel(SimpleNamespace(), message)
        panel.create_embed = Mock(return_value=(Mock(), None))

        await panel._refresh()

        panel.cog.delete_panel.assert_called_once_with(20)

    async def test_refresh_keeps_panel_for_other_http_error(self):
        message = SimpleNamespace(id=20, edit=AsyncMock(side_effect=discord_http_error(503)))
        panel = self.make_panel(SimpleNamespace(), message)
        panel.create_embed = Mock(return_value=(Mock(), None))

        await panel._refresh()

        panel.cog.delete_panel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
