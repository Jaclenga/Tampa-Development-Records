import ast
import json
import os
from pathlib import Path
import sys
from types import ModuleType
import unittest


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "tampa_development_exploration.ipynb"


class DisplayValue:
    def __init__(self, data):
        self.data = data


class PublicNotebookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        cls.code_cells = [
            "".join(cell["source"])
            for cell in cls.notebook["cells"]
            if cell["cell_type"] == "code"
        ]

    def execute_cells(self, cells=None, display_function=lambda _value: None):
        fake_ipython = ModuleType("IPython")
        fake_display = ModuleType("IPython.display")
        fake_display.HTML = DisplayValue
        fake_display.Markdown = DisplayValue
        fake_display.display = display_function
        previous_modules = {
            name: sys.modules.get(name) for name in ("IPython", "IPython.display")
        }
        previous_directory = Path.cwd()
        namespace = {"__name__": "__main__"}
        try:
            sys.modules["IPython"] = fake_ipython
            sys.modules["IPython.display"] = fake_display
            os.chdir(ROOT)
            selected_cells = self.code_cells if cells is None else cells
            for index, source in enumerate(selected_cells):
                exec(  # noqa: S102 - executing the repository's notebook is the purpose of this test
                    compile(source, f"{NOTEBOOK}:cell-{index}", "exec"),
                    namespace,
                )
        finally:
            os.chdir(previous_directory)
            for name, previous in previous_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
        return namespace

    def test_notebook_is_clean_valid_and_compilable(self):
        self.assertEqual(self.notebook["nbformat"], 4)
        self.assertGreaterEqual(self.notebook["nbformat_minor"], 5)
        for cell in self.notebook["cells"]:
            if cell["cell_type"] == "code":
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])
                ast.parse("".join(cell["source"]))

    def test_all_cells_execute_and_reconcile_with_published_index(self):
        namespace = self.execute_cells()
        self.assertEqual(
            len(namespace["events"]),
            namespace["monthly_index"]["record_count"],
        )
        self.assertEqual(
            namespace["analysis_receipt"]["selected_records"],
            len(namespace["selected_rows"]),
        )
        self.assertEqual(
            namespace["analysis_receipt"]["comparison_is_canonical_monthly"],
            namespace["comparison"]["canonical_monthly_comparison"],
        )
        self.assertRegex(namespace["DATA_REVISION"], r"^[0-9a-f]{40}$")

    def test_render_helpers_escape_untrusted_labels(self):
        captured = []
        namespace = self.execute_cells(
            cells=[self.code_cells[0]],
            display_function=captured.append,
        )
        hostile = "<script>alert('unsafe')</script>"
        namespace["show_table"](
            [{"value": hostile}],
            [("value", hostile)],
        )
        namespace["bar_chart"]([(hostile, 1)], hostile)
        rendered = "\n".join(item.data for item in captured if hasattr(item, "data"))
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_narrative_is_not_tied_to_one_snapshot_and_partial_year_is_labeled(self):
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in self.notebook["cells"]
            if cell["cell_type"] == "markdown"
        )
        self.assertNotIn("August 23 to September 1, 2026", markdown)
        namespace = self.execute_cells()
        current_year = namespace["latest_snapshot"][:4]
        current_row = next(
            row for row in namespace["annual_rows"] if row["year"] == current_year
        )
        self.assertIn("Partial", current_row["coverage"])

    def test_long_chart_labels_get_space_or_safe_truncation(self):
        captured = []
        namespace = self.execute_cells(
            cells=[self.code_cells[0]],
            display_function=captured.append,
        )
        long_label = "A very long neighborhood association name " * 3
        namespace["bar_chart"]([(long_label, 7)], "Long-label test")
        rendered = captured[-1].data
        self.assertIn("<title>" + long_label + "</title>", rendered)
        self.assertIn("...", rendered)


if __name__ == "__main__":
    unittest.main()
