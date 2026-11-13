import json
import re
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent


class PluginIdentity(unittest.TestCase):
    def test_manifest_name_and_version(self):
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "shared-software-factory")
        self.assertEqual(manifest["version"], "0.2.1")

    def test_no_stale_plugin_namespace(self):
        stale_ns = re.compile(r"(?<!shared-)software-factory:")
        stale_install = re.compile(r"(?<!shared-)software-factory@engineering-skills")
        offenders = []
        for path in PLUGIN.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.name == "test_plugin_identity.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if stale_ns.search(text) or stale_install.search(text):
                offenders.append(str(path.relative_to(PLUGIN)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
