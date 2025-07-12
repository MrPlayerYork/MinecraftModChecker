import unittest
import sys
import types
from pathlib import Path

# Ensure the repository root is on the import path so that the mod_checker
# module can be imported when tests are executed from within the tests
# directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Provide a minimal stub for the requests module so that mod_checker can be
# imported without having the real dependency installed.
sys.modules.setdefault('requests', types.ModuleType('requests'))

# Stub out the 'rich' module hierarchy used in mod_checker so that the module
# can be imported without the real dependency installed.
rich_module = types.ModuleType('rich')
console_module = types.ModuleType('rich.console')
console_module.Console = object  # simple placeholder
table_module = types.ModuleType('rich.table')
table_module.Table = object
table_module.box = object()
panel_module = types.ModuleType('rich.panel')
panel_module.Panel = object
progress_module = types.ModuleType('rich.progress')
progress_module.Progress = object
progress_module.SpinnerColumn = object
progress_module.TextColumn = object
progress_module.BarColumn = object
progress_module.TaskProgressColumn = object

# Minimal stubs for the requests module attributes used in type hints
requests_module = sys.modules['requests']
requests_module.Response = object
requests_module.RequestException = Exception

rich_module.print = print
sys.modules.setdefault('rich', rich_module)
sys.modules.setdefault('rich.console', console_module)
sys.modules.setdefault('rich.table', table_module)
sys.modules.setdefault('rich.panel', panel_module)
sys.modules.setdefault('rich.progress', progress_module)

from mod_checker import ModInfo, find_common_version

class TestFindCommonVersion(unittest.TestCase):
    def test_returns_oldest_version(self):
        # Create dummy ModInfo objects with available versions
        mod1 = ModInfo(name='A', slug='a', url='url', versions=['1.19', '1.18'], available=True)
        mod2 = ModInfo(name='B', slug='b', url='url', versions=['1.19', '1.18'], available=True)
        # Should return 1.18 (oldest) even though versions sorted descending
        self.assertEqual(find_common_version([mod1, mod2]), '1.18')

if __name__ == '__main__':
    unittest.main()
