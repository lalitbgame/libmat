# -*- coding: utf-8 -*-
"""GUI form + dialog. Sync runs in the GUI process (pure Python) before the
dialog opens, so the combo box always lists the latest cards; the import itself
is sent to the kernel as matlib_kernel.importMaterial(...)."""
from abaqusGui import *
import matlib_sync


class MatLibForm(AFXForm):

    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self.cmd = AFXGuiCommand(mode=self, method="importMaterial",
                                 objectName="matlib_kernel", registerQuery=False)
        self.modelKw = AFXStringKeyword(self.cmd, "modelName", True, "")
        self.materialKw = AFXStringKeyword(self.cmd, "materialKey", True, "")
        self.newNameKw = AFXStringKeyword(self.cmd, "newName", False, "")
        self.overwriteKw = AFXBoolKeyword(self.cmd, "overwrite",
                                          AFXBoolKeyword.TRUE_FALSE, True, False)
        self.choices = []
        self.status = ""

    def getFirstDialog(self):
        cfg = matlib_sync.load_config()
        msgs = []
        try:
            index, n, online = matlib_sync.sync(cfg, log=msgs.append)
        except Exception as e:  # never block the user because of sync
            msgs.append("MATLIB sync error: %s" % e)
            index, online = matlib_sync.load_cached_index(cfg["cache_dir"]), False
        for m in msgs:
            getAFXApp().getAFXMainWindow().writeToMessageArea(m)

        self.choices = [matlib_sync.choice_label(m)
                        for m in matlib_sync.list_choices(index, cfg.get("include_drafts", False))]
        self.status = "%s | commit %s | %d cards" % (
            "online" if online else "OFFLINE (cached)", index.get("commit", "?")[:8], len(self.choices))

        self.modelKw.setValue(getCurrentContext().get("modelName", ""))
        if self.choices:
            self.materialKw.setValue(self.choices[0])
        return MatLibDB(self)

    def doCustomChecks(self):
        if not self.materialKw.getValue():
            showAFXErrorDialog(self.getCurrentDialog(), "No material selected / library is empty.")
            return False
        return True


class MatLibDB(AFXDataDialog):

    def __init__(self, form):
        AFXDataDialog.__init__(self, form, "Material Library - Import",
                               self.OK | self.APPLY | self.CANCEL, DIALOG_ACTIONS_SEPARATOR)
        FXLabel(self, form.status)

        va = AFXVerticalAligner(self)
        AFXTextField(va, 30, "Target model:", form.modelKw, 0)

        combo = AFXComboBox(va, 0, min(12, max(1, len(form.choices))), "Material card:",
                            form.materialKw, 0)
        for c in form.choices:
            combo.appendItem(c)

        AFXTextField(va, 30, "Name in model (blank = ID_vX-Y-Z):", form.newNameKw, 0)
        FXCheckButton(self, "Overwrite if material exists", form.overwriteKw, 0)
