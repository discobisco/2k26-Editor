from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


@dataclass
class MultiSelectListState:
    """Selection state for a Dear PyGui list rendered from selectables."""

    selected: set[str] = field(default_factory=set)

    def prune(self, items: Iterable[str]) -> None:
        valid = set(items)
        self.selected.intersection_update(valid)

    def toggle(self, item: str) -> bool:
        if item in self.selected:
            self.selected.remove(item)
            return False
        self.selected.add(item)
        return True

    def clear(self) -> None:
        self.selected.clear()

    def selected_items(self, items: Iterable[str]) -> list[str]:
        return [item for item in items if item in self.selected]

    def copy_text(self, items: Iterable[str]) -> str:
        return "\n".join(self.selected_items(items))


def render_multi_select_list(
    dpg: Any,
    *,
    container_tag: str,
    row_tag: Callable[[int, str], str],
    items: list[str],
    state: MultiSelectListState,
    on_select: Callable[[str], None],
) -> None:
    """Render a left-click list that supports multiple active selections."""

    state.prune(items)
    dpg.delete_item(container_tag, children_only=True)
    for index, item in enumerate(items):
        marker = "✓ " if item in state.selected else "  "
        dpg.add_selectable(
            label=f"{marker}{item}",
            tag=row_tag(index, item),
            default_value=item in state.selected,
            width=-1,
            callback=lambda *_args, selected=item: on_select(selected),
            parent=container_tag,
        )


def copy_multi_select_to_clipboard(dpg: Any, state: MultiSelectListState, items: Iterable[str]) -> int:
    selected = state.selected_items(items)
    dpg.set_clipboard_text("\n".join(selected))
    return len(selected)
