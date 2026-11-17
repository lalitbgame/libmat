# -*- coding: utf-8 -*-
"""Abaqus/CAE kernel side: add a cached material card to a model.

Strategy: wrap card.inp in a throwaway input file, import it as a temporary
model, copy the material into the target model, delete the temp model.
This lets Abaqus parse every keyword the card uses (plastic, hyperelastic,
user material...) without us re-implementing the keyword parser.
"""
from __future__ import print_function

import json
import os
import re
import tempfile

from abaqus import mdb
import matlib_sync

TMP_MODEL = "__MATLIB_TMP__"
MAT_KW = re.compile(r"^\*material\s*,\s*name\s*=\s*([^,\s]+)", re.I | re.M)


def _abaqus_name(s):
    # Abaqus names: no dots/spaces, max 80 chars
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)[:80]


def importMaterial(modelName, materialKey, newName="", overwrite=False):
    """materialKey is the dialog label 'ID | vX.Y.Z | status | units'."""
    cfg = matlib_sync.load_config()
    mat_id, version = matlib_sync.parse_label(materialKey)
    d = matlib_sync.card_dir(cfg["cache_dir"], mat_id, version)
    card_p, meta_p = os.path.join(d, "card.inp"), os.path.join(d, "metadata.json")
    if not os.path.isfile(card_p):
        raise ValueError("Card %s v%s not in local cache - run sync first." % (mat_id, version))

    with open(card_p) as f:
        card = f.read()
    with open(meta_p) as f:
        meta = json.load(f)

    if modelName not in mdb.models.keys():
        raise ValueError("Model '%s' not found." % modelName)
    model = mdb.models[modelName]

    model_units = cfg.get("model_units")
    if model_units and meta["units"] != model_units:
        raise ValueError("Unit mismatch: card is %s, model convention is %s."
                         % (meta["units"], model_units))

    card_name = MAT_KW.search(card).group(1)
    target = _abaqus_name(newName or "%s_v%s" % (mat_id, version.replace(".", "-")))
    if target in model.materials.keys():
        if not overwrite:
            raise ValueError("Material '%s' already exists in model (tick overwrite)." % target)
        del model.materials[target]

    fd, tmp_inp = tempfile.mkstemp(suffix=".inp", prefix="matlib_")
    os.close(fd)
    try:
        with open(tmp_inp, "w") as f:
            f.write("*Heading\nMATLIB temporary import\n" + card)
        if TMP_MODEL in mdb.models.keys():
            del mdb.models[TMP_MODEL]
        tmp = mdb.ModelFromInputFile(name=TMP_MODEL, inputFileName=tmp_inp)
        # ModelFromInputFile upper-cases keyword names; look up case-insensitively
        src = [k for k in tmp.materials.keys() if k.upper() == card_name.upper()][0]
        mat = model.Material(name=target, objectToCopy=tmp.materials[src])
    finally:
        if TMP_MODEL in mdb.models.keys():
            del mdb.models[TMP_MODEL]
        try:
            os.remove(tmp_inp)
        except OSError:
            pass

    # Traceability: stamp library provenance into the material description
    idx = matlib_sync.load_cached_index(cfg["cache_dir"])
    sha = next((m["card_sha256"][:12] for m in idx.get("materials", [])
                if m["id"] == mat_id and m["version"] == version), "?")
    mat.setValues(description="MATLIB id=%s version=%s status=%s units=%s sha=%s commit=%s source=%s"
                  % (mat_id, version, meta["status"], meta["units"], sha,
                     idx.get("commit", "?")[:8], meta.get("source", "")))
    if meta["status"] == "draft":
        print("MATLIB WARNING: %s v%s is a DRAFT card - not approved for release." % (mat_id, version))
    print("MATLIB: added '%s' (%s v%s) to model '%s'." % (target, mat_id, version, modelName))
    return target


def syncLibrary():
    """Callable from the kernel command line / scripts: matlib_kernel.syncLibrary()"""
    return matlib_sync.sync()[1]
