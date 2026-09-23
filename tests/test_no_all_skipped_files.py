"""The --fail-on-all-skipped-file guard (tests/conftest.py): both directions, via pytester."""
from pathlib import Path

pytest_plugins = ["pytester"]
CONFTEST = (Path(__file__).resolve().parent / "conftest.py").read_text()


def _run(pytester, files):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(**files)
    return pytester.runpytest("--fail-on-all-skipped-file", "-p", "no:cacheprovider")


def test_file_with_all_tests_skipped_fails_the_session(pytester):
    r = _run(pytester, {"test_ok": "def test_a():\n    pass\n",
                        "test_ghost": "import pytest\n\n@pytest.mark.skip('no cases')\ndef test_b():\n    pass\n"
                                      "\ndef test_c():\n    pytest.skip('not built')\n"})
    assert r.ret == 1
    r.stdout.fnmatch_lines(["*every test in these files was SKIPPED*", "*test_ghost.py*"])


def test_partly_skipped_file_passes(pytester):
    r = _run(pytester, {"test_mix": "import pytest\n\ndef test_a():\n    pass\n\n"
                                    "def test_b():\n    pytest.skip('x')\n"})
    assert r.ret == 0


def test_module_level_skip_fails(pytester):
    r = _run(pytester, {"test_ok": "def test_a():\n    pass\n",
                        "test_mod": "import pytest\npytest.skip('whole module', allow_module_level=True)\n"
                                    "def test_x():\n    pass\n"})
    assert r.ret == 1 and "test_mod.py" in r.stdout.str()


def test_without_the_flag_nothing_changes(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_ghost="import pytest\n\ndef test_c():\n    pytest.skip('x')\n")
    assert pytester.runpytest("-p", "no:cacheprovider").ret == 0
