from dpo4000_utils.gui.app import ScopeGui as AppScopeGui
from dpo4000_utils.gui.scope_gui import ScopeGui


def test_public_gui_entry_point_uses_flattened_scope_gui():
    assert AppScopeGui is ScopeGui
