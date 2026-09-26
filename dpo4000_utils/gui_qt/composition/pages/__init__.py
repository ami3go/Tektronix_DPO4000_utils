"""Native composed control-page builders for DPO4000 Desk."""

from .connection import build_connection_page
from .recipe import build_recipe_page
from .scientific_export import attach_scientific_export_panel
from .trend import attach_measurement_trend_panel
from .trigger import build_trigger_page

__all__ = [
    "attach_measurement_trend_panel",
    "attach_scientific_export_panel",
    "build_connection_page",
    "build_recipe_page",
    "build_trigger_page",
]
