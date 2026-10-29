"""AYON attribute definitions as Cinema 4D dialog gadgets.

    editor = AttributeEditor(dialog, first_id=5000)
    editor.add_section("Creator", instance.creator_attributes)
    ...
    dialog.Command -> editor.command(gadget_id) -> True if it was one of ours

Values are written into the `AttributeValues` object right away (the caller
saves them). Unknown definition types (files...) are shown read-only with a
hint to use the Publisher.
"""
import c4d

from ayon_core.lib.attribute_definitions import (
    BoolDef,
    EnumDef,
    HiddenDef,
    NumberDef,
    TextDef,
    UILabelDef,
    UISeparatorDef,
)

from . import widgets


class AttributeEditor:
    def __init__(self, dialog, first_id):
        self.dialog = dialog
        self._next_id = first_id
        self._gadgets = {}  # gadget id -> (values, attr_def)
        self.on_change = None  # callable(values, key, value)

    def _new_id(self):
        self._next_id += 1
        return self._next_id

    def add_section(self, title, values, defs=None):
        """Gadgets for every visible definition of `values`."""
        defs = defs if defs is not None else values.attr_defs
        defs = [d for d in defs
                if getattr(d, "visible", True) and not isinstance(d, HiddenDef)]
        if not defs:
            return
        dlg = self.dialog
        dlg.AddStaticText(0, c4d.BFH_SCALEFIT, name=title,
                          borderstyle=c4d.BORDER_WITH_TITLE_BOLD)
        if dlg.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2):
            dlg.GroupBorderSpace(8, 0, 0, 4)
            for attr_def in defs:
                self._add(values, attr_def)
        dlg.GroupEnd()

    def _add(self, values, attr_def):
        dlg = self.dialog
        if isinstance(attr_def, UISeparatorDef):
            dlg.AddSeparatorH(0)
            dlg.AddSeparatorH(0)
            return
        if isinstance(attr_def, UILabelDef):
            dlg.AddStaticText(0, c4d.BFH_LEFT, name="")
            dlg.AddStaticText(0, c4d.BFH_SCALEFIT, name=attr_def.label or "")
            return

        key = attr_def.key
        value = values.get(key, getattr(attr_def, "default", None))
        dlg.AddStaticText(0, c4d.BFH_LEFT, name=attr_def.label or key)
        gadget_id = self._new_id()
        flags = c4d.BFH_SCALEFIT

        if isinstance(attr_def, BoolDef):
            dlg.AddCheckbox(gadget_id, flags, 0, 0, name="")
            dlg.SetBool(gadget_id, bool(value))
        elif isinstance(attr_def, NumberDef):
            dlg.AddEditNumberArrows(gadget_id, flags, 80, 0)
            minimum = max(attr_def.minimum, -1e9)
            maximum = min(attr_def.maximum, 1e9)
            if attr_def.decimals:
                dlg.SetFloat(
                    gadget_id, float(value or 0), min=minimum, max=maximum,
                    step=10 ** -attr_def.decimals)
            else:
                dlg.SetInt32(
                    gadget_id, int(value or 0), min=int(minimum),
                    max=int(maximum))
        elif isinstance(attr_def, TextDef):
            dlg.AddEditText(gadget_id, flags, 160, 0)
            dlg.SetString(gadget_id, value or "")
        elif isinstance(attr_def, EnumDef) and not attr_def.multiselection:
            dlg.AddComboBox(gadget_id, flags, 160, 0)
            selected = 0
            for index, item in enumerate(attr_def.items):
                dlg.AddChild(gadget_id, index, str(item["label"]))
                if item["value"] == value:
                    selected = index
            dlg.SetInt32(gadget_id, selected)
        elif isinstance(attr_def, EnumDef):
            dlg.AddButton(gadget_id, flags, name=self._multi_label(
                attr_def, value))
        else:
            dlg.AddStaticText(
                gadget_id, flags, name=f"{value!r}  (edit in the Publisher)")
            dlg.Enable(gadget_id, False)
            return

        if not getattr(attr_def, "enabled", True):
            dlg.Enable(gadget_id, False)
        self._gadgets[gadget_id] = (values, attr_def)

    @staticmethod
    def _multi_label(attr_def, value):
        value = value or []
        labels = [i["label"] for i in attr_def.items if i["value"] in value]
        if not labels:
            return "None"
        if len(labels) > 2:
            return f"{len(labels)} selected"
        return ", ".join(str(label) for label in labels)

    def command(self, gadget_id):
        """Read a changed gadget into its values. True if handled."""
        entry = self._gadgets.get(gadget_id)
        if entry is None:
            return False
        values, attr_def = entry
        dlg = self.dialog
        if isinstance(attr_def, BoolDef):
            value = dlg.GetBool(gadget_id)
        elif isinstance(attr_def, NumberDef):
            value = (dlg.GetFloat(gadget_id) if attr_def.decimals
                     else dlg.GetInt32(gadget_id))
        elif isinstance(attr_def, TextDef):
            value = dlg.GetString(gadget_id)
        elif not attr_def.multiselection:
            index = dlg.GetInt32(gadget_id)
            value = attr_def.items[index]["value"]
        else:
            self._edit_multi(gadget_id, values, attr_def)
            return True
        self._set(values, attr_def, value)
        return True

    def _edit_multi(self, gadget_id, values, attr_def):
        current = list(values.get(attr_def.key) or [])

        def toggle(item_value):
            if item_value in current:
                current.remove(item_value)
            else:
                current.append(item_value)
            self._set(values, attr_def, list(current))
            self.dialog.SetString(
                gadget_id, self._multi_label(attr_def, current))

        widgets.popup([
            (("*" if item["value"] in current else "") + str(item["label"]),
             lambda v=item["value"]: toggle(v))
            for item in attr_def.items
        ])

    def _set(self, values, attr_def, value):
        values[attr_def.key] = value
        if self.on_change:
            self.on_change(values, attr_def.key, value)
