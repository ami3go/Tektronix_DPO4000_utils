from dpo4000_utils.gui.app import ScopeGui as AppScopeGui
from dpo4000_utils.gui.scope_gui import ScopeGui as BaseScopeGui
from dpo4000_utils.gui.styled_scope_gui import ScopeGui as StyledScopeGui


def test_public_gui_entry_point_uses_styled_scope_gui():
    assert AppScopeGui is StyledScopeGui
    assert issubclass(AppScopeGui, BaseScopeGui)
