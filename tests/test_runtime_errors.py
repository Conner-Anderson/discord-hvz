import importlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import requests

from discord_hvz import display

main_module = importlib.import_module('discord_hvz.main')


class RuntimeErrorTests(unittest.TestCase):
    def test_exit_prompt_accepts_eof_and_interrupt(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), \
                 patch.object(main_module, 'TOKEN', None), \
                 patch.object(main_module.sys, 'stdin', SimpleNamespace(isatty=lambda: True)), \
                 patch('builtins.input', side_effect=error):
                main_module.main()

    def test_noninteractive_exit_does_not_prompt(self):
        with patch.object(main_module, 'TOKEN', None), \
             patch.object(main_module.sys, 'stdin', SimpleNamespace(isatty=lambda: False)), \
             patch('builtins.input') as prompt:
            main_module.main()
        prompt.assert_not_called()

    def test_failed_plot_download_preserves_cached_file_and_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'plots').mkdir()
            cached = root / 'plots/latest_gameplot.png'
            cached.write_bytes(b'previous plot')
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.raise_for_status.side_effect = requests.HTTPError('unavailable')
            with patch.object(display, 'config', SimpleNamespace(path_root=root, silent_oz=False)), \
                 patch.object(display, 'LAST_GAME_PLOT_URL', 'previous url'), \
                 patch.object(display.sqlalchemy, 'create_engine'), \
                 patch.object(display.pd, 'read_sql', return_value=pd.DataFrame()), \
                 patch.object(display.requests, 'get', return_value=response) as get:
                with self.assertRaises(requests.HTTPError):
                    display.create_quickchart(root / 'unused.db')
                self.assertEqual(cached.read_bytes(), b'previous plot')
                self.assertEqual(display.LAST_GAME_PLOT_URL, 'previous url')
                self.assertEqual(get.call_args.kwargs['timeout'], (5, 15))

    def test_plot_timeout_keeps_other_panel_elements(self):
        panel = display.HVZPanel(SimpleNamespace(bot=Mock()))
        panel.elements = [SimpleNamespace(add=Mock(side_effect=requests.Timeout('offline')))]
        def add_count(embed, panel):
            embed.add_field(name='Players', value='12')
        panel.elements.append(SimpleNamespace(add=add_count))
        embed, file = panel.create_embed()
        self.assertIsNone(file)
        self.assertEqual(embed.fields[0].name, 'Game Plot')
        self.assertIn('unavailable', embed.fields[0].value)
        self.assertEqual(embed.fields[1].value, '12')


if __name__ == '__main__':
    unittest.main()
