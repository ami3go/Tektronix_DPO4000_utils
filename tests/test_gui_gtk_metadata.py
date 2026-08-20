from pathlib import Path


def test_gtk_package_lazy_import_metadata():
    import dpo4000_utils.gui_gtk as gui_gtk

    assert "GtkScopeWindow" in gui_gtk.__all__


def test_gtk_runner_exports_main_without_importing_gtk():
    from dpo4000_utils.gui_gtk.runner import main

    assert callable(main)


def test_gtk_theme_file_exists_and_mentions_dark_palette():
    theme_path = Path("dpo4000_utils/gui_gtk/theme.css")

    assert theme_path.exists()
    content = theme_path.read_text(encoding="utf-8")
    assert "#111827" in content
    assert ".card" in content


def test_pyproject_declares_gtk_entry_point_and_optional_dependency():
    content = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'gtk = [' in content
    assert '"PyGObject>=3.46"' in content
    assert 'dpo4000-gui-gtk = "dpo4000_utils.gui_gtk.runner:main"' in content
