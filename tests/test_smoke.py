import tidyup


def test_package_has_version():
    assert isinstance(tidyup.__version__, str)
    assert tidyup.__version__.count(".") == 2


def test_modules_import():
    from tidyup import actions, cli, duplicates, rules, scanner, undo  # noqa: F401
