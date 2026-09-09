import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
import discord

import importlib

main_module = importlib.import_module('discord_hvz.main')


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_bot(self, *, sink=None, sink_id=None, connection_task=None):
        bot = main_module.HVZBot.__new__(main_module.HVZBot)
        bot._discord_sink = sink
        bot._discord_sink_id = sink_id
        bot._connection_task = connection_task
        bot._close_lock = asyncio.Lock()
        return bot

    async def test_start_owns_and_awaits_connection_task(self):
        started = asyncio.Event()

        async def fake_start(self, token, *, reconnect=True):
            started.set()

        bot = self.make_bot()
        with patch.object(discord.ext.commands.Bot, "start", new=fake_start):
            await bot.start("token", reconnect=False)

        self.assertTrue(started.is_set())
        self.assertTrue(bot._connection_task.done())

    async def test_close_cancels_connection_and_closes_in_order(self):
        order = []

        async def connection():
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                order.append("connection-cancelled")
                raise

        connection_task = asyncio.create_task(connection())
        await asyncio.sleep(0)
        sink = SimpleNamespace(close=AsyncMock(side_effect=lambda: order.append("sink")))
        bot = self.make_bot(sink=sink, sink_id=42, connection_task=connection_task)

        async def fake_super_close(self):
            order.append("super-close")

        with patch.object(main_module.logger, "remove") as remove, \
             patch.object(main_module.utilities, "cancel_delayed_tasks", new=AsyncMock(side_effect=lambda: order.append("delayed"))), \
             patch.object(discord.ext.commands.Bot, "close", new=fake_super_close):
            await bot.close()

        remove.assert_called_once_with(42)
        sink.close.assert_awaited_once()
        self.assertEqual(order, ["sink", "connection-cancelled", "delayed", "super-close"])

    async def test_close_is_safe_when_called_repeatedly(self):
        bot = self.make_bot()

        with patch.object(main_module.utilities, "cancel_delayed_tasks", new=AsyncMock()), \
             patch.object(discord.ext.commands.Bot, "close", new=AsyncMock()) as parent_close:
            await bot.close()
            await bot.close()

        self.assertEqual(parent_close.await_count, 2)


class DiscordSinkTests(unittest.IsolatedAsyncioTestCase):
    def make_sink(self, channel, *, closed=False, loop_closed=False):
        loop = SimpleNamespace(is_closed=Mock(return_value=loop_closed), create_task=asyncio.get_running_loop().create_task)
        bot = SimpleNamespace(is_closed=Mock(return_value=closed), loop=loop)
        return main_module.DiscordSink(channel, bot)

    async def test_send_failure_is_logged_without_sink_recursion(self):
        channel = SimpleNamespace(send=AsyncMock(side_effect=aiohttp.ClientError("offline")))
        sink = self.make_sink(channel)

        with patch.object(main_module.logger, "bind", wraps=main_module.logger.bind) as bind:
            await sink.send("message")

        channel.send.assert_awaited_once_with("message")
        bind.assert_called_once_with(skip_discord=True)

    async def test_write_skips_closed_bot_or_loop(self):
        channel = SimpleNamespace(send=AsyncMock())
        sink = self.make_sink(channel, closed=True)
        sink.write("message")
        await asyncio.sleep(0)
        channel.send.assert_not_awaited()

        sink = self.make_sink(channel, loop_closed=True)
        sink.write("message")
        channel.send.assert_not_awaited()

    async def test_close_cancels_pending_send_tasks(self):
        gate = asyncio.Event()

        async def send(_message):
            await gate.wait()

        sink = self.make_sink(SimpleNamespace(send=send))
        sink.write("message")
        await asyncio.sleep(0)
        self.assertEqual(len(sink.tasks), 1)
        await sink.close()
        self.assertFalse(sink.tasks)


class RunnerTests(unittest.TestCase):
    def test_pycord_run_closes_cleanly_on_request_and_interrupt(self):
        for interrupt in (False, True):
            with self.subTest(interrupt=interrupt):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                bot = main_module.HVZBot.__new__(main_module.HVZBot)
                bot.loop = loop
                bot._closed = False
                bot._close_lock = asyncio.Lock()
                bot._discord_sink = None
                bot._discord_sink_id = None
                bot._connection_task = None
                errors = []
                loop.set_exception_handler(lambda _loop, context: errors.append(context))

                def keyboard_interrupt():
                    raise KeyboardInterrupt

                async def fake_start(self, token, *, reconnect=True):
                    if interrupt:
                        loop.call_soon(keyboard_interrupt)
                    else:
                        loop.create_task(bot.close())
                    await asyncio.Future()

                async def fake_close(self):
                    self._closed = True

                with patch.object(discord.ext.commands.Bot, 'start', new=fake_start), \
                     patch.object(discord.ext.commands.Bot, 'close', new=fake_close):
                    bot.run('test-token')

                self.assertTrue(bot.is_closed())
                self.assertTrue(loop.is_closed())
                self.assertEqual(errors, [])
                asyncio.set_event_loop(None)


if __name__ == "__main__":
    unittest.main()
