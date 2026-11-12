import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import envdiff as ed


def write_env(root, name, text):
    path = os.path.join(root, name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return path


class TTY(io.StringIO):
    def isatty(self):
        return True


class Parse(unittest.TestCase):
    def test_plain_pairs(self):
        self.assertEqual(ed.parse_env("A=1\nB=two\n"), {"A": "1", "B": "two"})

    def test_blank_lines_and_comments(self):
        text = "\n   \n# comment\n  # indented comment\nA=1\n\nB=2 # trailing\n"
        self.assertEqual(ed.parse_env(text), {"A": "1", "B": "2"})

    def test_export_prefix(self):
        self.assertEqual(ed.parse_env("export A=1\nexport   B=2\n"), {"A": "1", "B": "2"})

    def test_double_quoted_value(self):
        self.assertEqual(ed.parse_env('A="hello world"\n'), {"A": "hello world"})

    def test_single_quoted_value_literal(self):
        self.assertEqual(ed.parse_env("A='x # y'\n"), {"A": "x # y"})
        self.assertEqual(ed.parse_env(r"A='no \n escapes'" + "\n"), {"A": r"no \n escapes"})

    def test_inline_comment_unquoted(self):
        self.assertEqual(ed.parse_env("A=val # comment\nB=plain\n"),
                         {"A": "val", "B": "plain"})

    def test_hash_inside_unquoted_value_kept(self):
        self.assertEqual(ed.parse_env("A=a#b\n"), {"A": "a#b"})

    def test_comment_after_quoted_value(self):
        self.assertEqual(ed.parse_env('A="v" # comment\n'), {"A": "v"})
        self.assertEqual(ed.parse_env("A='v'   # comment\n"), {"A": "v"})

    def test_double_quote_escapes(self):
        self.assertEqual(ed.parse_env(r'A="a\"b\\c\nd"' + "\n"), {"A": 'a"b\\c\nd'})

    def test_empty_values(self):
        self.assertEqual(ed.parse_env("A=\nB=   \nC= # comment\nD=\"\"\n"),
                         {"A": "", "B": "", "C": "", "D": ""})

    def test_duplicate_key_last_wins(self):
        self.assertEqual(ed.parse_env("A=1\nA=2\n"), {"A": "2"})

    def test_value_containing_equals(self):
        self.assertEqual(ed.parse_env("A=a=b=c\n"), {"A": "a=b=c"})

    def test_surrounding_whitespace_trimmed(self):
        self.assertEqual(ed.parse_env("  A=  val  \n"), {"A": "val"})
        self.assertEqual(ed.parse_env('A="  keep  "\n'), {"A": "  keep  "})

    def test_malformed_line_raises(self):
        for bad in ("NOT_AN_ASSIGNMENT\n", "1BAD=x\n", "FOO bar\n", "export A\n", "=v\n"):
            with self.assertRaises(ed.EnvError):
                ed.parse_env(bad)

    def test_unterminated_quote_raises(self):
        with self.assertRaises(ed.EnvError):
            ed.parse_env('A="unclosed\n')
        with self.assertRaises(ed.EnvError):
            ed.parse_env("A='unclosed\n")

    def test_load_bom_and_crlf_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.env")
            with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                fh.write("A=1\r\nB=2\r\n")
            self.assertEqual(ed.load_env(path), {"A": "1", "B": "2"})


class Diff(unittest.TestCase):
    def test_identical_no_drift(self):
        d = ed.diff({"A": "1"}, {"A": "1"})
        self.assertEqual(d, {"missing": [], "extra": [], "changed": []})
        self.assertFalse(ed.has_drift(d))

    def test_missing_extra_changed(self):
        d = ed.diff({"GONE": "1", "HOST": "a", "SAME": "x"},
                    {"NEW": "2", "HOST": "b", "SAME": "x"})
        self.assertEqual(d["missing"], ["GONE"])
        self.assertEqual(d["extra"], ["NEW"])
        self.assertEqual(d["changed"], [{"key": "HOST", "old": "a", "new": "b"}])
        self.assertTrue(ed.has_drift(d))

    def test_changed_only(self):
        d = ed.diff({"A": ""}, {"A": "x"})
        self.assertEqual(d["missing"], [])
        self.assertEqual(d["extra"], [])
        self.assertEqual(d["changed"], [{"key": "A", "old": "", "new": "x"}])

    def test_ignore_keys(self):
        a = {"GONE": "1", "HOST": "a", "TOKEN": "t1"}
        b = {"NEW": "2", "HOST": "b", "TOKEN": "t2"}
        d = ed.diff(a, b, ignore=["GONE", "NEW", "HOST", "TOKEN"])
        self.assertFalse(ed.has_drift(d))

    def test_sorted_output(self):
        d = ed.diff({"Z": "1", "A": "1", "M": "1"}, {"Y": "2", "B": "2", "N": "2"})
        self.assertEqual(d["missing"], ["A", "M", "Z"])
        self.assertEqual(d["extra"], ["B", "N", "Y"])
        d2 = ed.diff({"Z": "1", "A": "1"}, {"Z": "2", "A": "2"})
        self.assertEqual([c["key"] for c in d2["changed"]], ["A", "Z"])


class Mask(unittest.TestCase):
    def test_secret_markers(self):
        for key in ("DB_SECRET", "AUTH_TOKEN", "PASSWORD", "PASSWD", "API_KEY",
                    "MONKEY", "stripe_api", "MY_CREDENTIAL_X"):
            self.assertTrue(ed.is_secret(key), key)

    def test_non_secret_keys(self):
        for key in ("HOST", "PORT", "APP_NAME", "DEBUG"):
            self.assertFalse(ed.is_secret(key), key)

    def test_mask_changed_by_default(self):
        d = ed.diff({"API_TOKEN": "t1", "HOST": "a"}, {"API_TOKEN": "t2", "HOST": "b"})
        masked = ed.mask_result(d)
        self.assertEqual(masked["changed"][0], {"key": "API_TOKEN", "old": "****", "new": "****"})
        self.assertEqual(masked["changed"][1], {"key": "HOST", "old": "a", "new": "b"})

    def test_show_values_reveals(self):
        d = ed.diff({"API_TOKEN": "t1"}, {"API_TOKEN": "t2"})
        shown = ed.mask_result(d, show_values=True)
        self.assertEqual(shown["changed"], [{"key": "API_TOKEN", "old": "t1", "new": "t2"}])

    def test_mask_does_not_mutate_input(self):
        d = ed.diff({"SECRET": "s1"}, {"SECRET": "s2"})
        ed.mask_result(d)
        self.assertEqual(d["changed"], [{"key": "SECRET", "old": "s1", "new": "s2"}])


class Report(unittest.TestCase):
    def test_report_plain_groups(self):
        d = ed.diff({"GONE": "1", "HOST": "a"}, {"NEW": "2", "HOST": "b"})
        text = ed.report(d, "a.env", "b.env", False)
        self.assertIn("a.env -> b.env", text)
        self.assertIn("MISSING (1)", text)
        self.assertIn("  - GONE", text)
        self.assertIn("EXTRA (1)", text)
        self.assertIn("  + NEW", text)
        self.assertIn("CHANGED (1)", text)
        self.assertIn("  ~ HOST: a -> b", text)
        self.assertNotIn("\x1b", text)

    def test_report_clean(self):
        text = ed.report(ed.diff({"A": "1"}, {"A": "1"}), "a.env", "b.env", False)
        self.assertIn("no drift", text)
        self.assertNotIn("MISSING", text)

    def test_report_ansi_colors(self):
        d = ed.diff({"GONE": "1", "HOST": "a"}, {"NEW": "2", "HOST": "b"})
        text = ed.report(d, "a.env", "b.env", True)
        self.assertIn("\x1b[31mMISSING (1)\x1b[0m", text)
        self.assertIn("\x1b[32mEXTRA (1)\x1b[0m", text)
        self.assertIn("\x1b[33mCHANGED (1)\x1b[0m", text)
        self.assertIn("\x1b[1m", text)

    def test_report_empty_value_rendering(self):
        d = ed.diff({"A": ""}, {"A": "x"})
        self.assertIn('~ A: "" -> x', ed.report(d, "a", "b", False))

    def test_report_masks_secret_values(self):
        d = ed.mask_result(ed.diff({"API_TOKEN": "t1"}, {"API_TOKEN": "t2"}))
        text = ed.report(d, "a", "b", False)
        self.assertIn("~ API_TOKEN: **** -> ****", text)
        self.assertNotIn("t1", text)
        self.assertNotIn("t2", text)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ed.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_exit_identical(self):
        a = write_env(self.root, "a.env", "A=1\nB=2\n")
        b = write_env(self.root, "b.env", "# different comment\nB=2\nexport A=1\n")
        code, out, _ = self._run([a, b, "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn("no drift", out)

    def test_exit_drift(self):
        a = write_env(self.root, "a.env", "A=1\n")
        b = write_env(self.root, "b.env", "A=2\n")
        code, out, _ = self._run([a, b, "--no-color"])
        self.assertEqual(code, 1)
        self.assertIn("CHANGED (1)", out)

    def test_exit_missing_path(self):
        a = write_env(self.root, "a.env", "A=1\n")
        code, _, err = self._run([a, os.path.join(self.root, "nope.env")])
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_exit_directory_path(self):
        a = write_env(self.root, "a.env", "A=1\n")
        code, _, err = self._run([a, self.root])
        self.assertEqual(code, 2)
        self.assertIn("envdiff:", err)

    def test_exit_malformed_input(self):
        a = write_env(self.root, "a.env", "this is not a pair\n")
        b = write_env(self.root, "b.env", "A=1\n")
        code, _, err = self._run([a, b])
        self.assertEqual(code, 2)
        self.assertIn("expected KEY=VALUE", err)

    def test_json_output_masked(self):
        a = write_env(self.root, "a.env", "GONE=1\nHOST=a\nAPI_TOKEN=t1\n")
        b = write_env(self.root, "b.env", "NEW=2\nHOST=b\nAPI_TOKEN=t2\n")
        code, out, _ = self._run([a, b, "--json"])
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(set(data), {"missing", "extra", "changed"})
        self.assertEqual(data["missing"], ["GONE"])
        self.assertEqual(data["extra"], ["NEW"])
        self.assertEqual(data["changed"], [{"key": "API_TOKEN", "old": "****", "new": "****"},
                                           {"key": "HOST", "old": "a", "new": "b"}])
        self.assertNotIn("t1", out)
        self.assertNotIn("\x1b", out)

    def test_json_show_values(self):
        a = write_env(self.root, "a.env", "API_TOKEN=t1\n")
        b = write_env(self.root, "b.env", "API_TOKEN=t2\n")
        code, out, _ = self._run([a, b, "--json", "--show-values"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["changed"],
                         [{"key": "API_TOKEN", "old": "t1", "new": "t2"}])

    def test_json_identical_exit_zero(self):
        a = write_env(self.root, "a.env", "A=1\n")
        code, out, _ = self._run([a, a, "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"missing": [], "extra": [], "changed": []})

    def test_ignore_flag_commas_and_repeat(self):
        a = write_env(self.root, "a.env", "GONE=1\nHOST=a\nPORT=1\n")
        b = write_env(self.root, "b.env", "NEW=2\nHOST=b\nPORT=2\n")
        code, out, _ = self._run([a, b, "--ignore", "GONE,NEW", "--ignore", "HOST,PORT",
                                  "--no-color"])
        self.assertEqual(code, 0)
        self.assertIn("no drift", out)

    def test_ignore_with_spaces(self):
        a = write_env(self.root, "a.env", "A=1\nB=2\n")
        b = write_env(self.root, "b.env", "A=9\nB=2\n")
        code, _, _ = self._run([a, b, "--ignore", " A , ", "--no-color"])
        self.assertEqual(code, 0)

    def test_version_flag(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            ed.main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("envdiff " + ed.__version__, out.getvalue())

    def test_no_color_output(self):
        a = write_env(self.root, "a.env", "A=1\n")
        b = write_env(self.root, "b.env", "A=2\n")
        _, out, _ = self._run([a, b, "--no-color"])
        self.assertNotIn("\x1b", out)

    def test_want_color_policy(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(ed.want_color(False, TTY()))
            self.assertFalse(ed.want_color(True, TTY()))
            self.assertFalse(ed.want_color(False, io.StringIO()))
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(ed.want_color(False, TTY()))


if __name__ == "__main__":
    unittest.main()