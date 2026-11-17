# -*- coding: utf-8 -*-
"""Registers 'Plug-ins > Material Library > Import Material...' in Abaqus/CAE.

Copy the whole 'matlib' folder into  <home>/abaqus_plugins/  (or the site
abaqus_plugins dir) and restart CAE.
"""
from abaqusGui import getAFXApp, AFXMode
from abaqusConstants import ALL
from matlibForm import MatLibForm

toolset = getAFXApp().getAFXMainWindow().getPluginToolset()

toolset.registerGuiMenuButton(
    buttonText="Material Library|Import Material...",
    object=MatLibForm(toolset),
    messageId=AFXMode.ID_ACTIVATE,
    icon=None,
    kernelInitString="import matlib_kernel",
    applicableModules=ALL,
    version="0.1.0",
    author="CAE Methods",
    description="Sync material cards from GitLab and add a selected, versioned card to the model.",
    helpUrl="N/A",
)
