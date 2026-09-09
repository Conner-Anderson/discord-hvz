import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord

from discord_hvz.chatbot.chatbot import ChatBotManager
from discord_hvz.chatbot.script_models import load_model
from discord_hvz.config import ConfigError


def discord_http_error(status=503):
    response = SimpleNamespace(status=status, reason="test failure")
    return discord.HTTPException(response, "test failure")


class ChatbotErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def make_manager(self):
        manager = ChatBotManager.__new__(ChatBotManager)
        manager.active_chatbots = {}
        manager.thread_manager = SimpleNamespace(delete_thread=AsyncMock())
        return manager

    async def test_modal_failure_with_no_thread_sends_interaction_error_and_cleans_up(self):
        manager = self.make_manager()
        chatbot = SimpleNamespace(
            processing=False,
            thread=None,
            receive=AsyncMock(side_effect=RuntimeError("modal processor failed")),
        )
        manager.active_chatbots[42] = chatbot
        interaction = SimpleNamespace(respond=AsyncMock())
        manager.remove_chatbot = AsyncMock()

        await manager.receive_response(42, "submit", interaction=interaction)

        interaction.respond.assert_awaited_once_with(
            "The chatbot had a critical error. You will need to retry from the beginning.",
            ephemeral=True,
        )
        manager.remove_chatbot.assert_awaited_once_with(chatbot, delay=30.0)

    async def test_error_reply_http_failure_still_cleans_up(self):
        manager = self.make_manager()
        chatbot = SimpleNamespace(
            processing=False,
            thread=None,
            receive=AsyncMock(side_effect=RuntimeError("processor failed")),
        )
        manager.active_chatbots[42] = chatbot
        interaction = SimpleNamespace(respond=AsyncMock(side_effect=discord_http_error()))
        manager.remove_chatbot = AsyncMock()

        await manager.receive_response(42, "submit", interaction=interaction)

        interaction.respond.assert_awaited_once()
        manager.remove_chatbot.assert_awaited_once_with(chatbot, delay=30.0)

    async def test_delayed_removal_does_not_delete_replacement(self):
        manager = self.make_manager()
        old_chatbot = SimpleNamespace(thread=SimpleNamespace(id=100))
        replacement = SimpleNamespace(thread=SimpleNamespace(id=200))
        manager.active_chatbots[42] = old_chatbot
        scheduled = {}

        def capture_schedule(func, delay):
            scheduled["func"] = func
            scheduled["delay"] = delay

        with patch("discord_hvz.chatbot.chatbot.schedule_delayed", side_effect=capture_schedule):
            await manager.remove_chatbot(42, delay=30.0)

        manager.active_chatbots[42] = replacement
        await scheduled["func"]()

        self.assertIs(manager.active_chatbots[42], replacement)
        manager.thread_manager.delete_thread.assert_not_awaited()


class ScriptLoadErrorTests(unittest.TestCase):
    def test_missing_script_raises_config_error(self):
        with self.assertRaises(ConfigError):
            load_model(Path(tempfile.gettempdir()) / "discord-hvz-script-that-does-not-exist.yml")

    def test_malformed_script_raises_config_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scripts.yml"
            path.write_text("scripts: [", encoding="utf-8")

            with self.assertRaises(ConfigError):
                load_model(path)


if __name__ == "__main__":
    unittest.main()
