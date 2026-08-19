# Journal regression suite (review P1/1.5): schema versioning, read-back
# verification, animated-prop refusal, rename-safe + honest revert semantics,
# last-writer-wins, run scoping, and the crash-recovery sidecar.
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_journal.py
# Builds its own fixtures; needs no .blend argument. Must pass on 4.2-5.x.

import json
import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import check, clear_default_scene, finish, section  # noqa: E402


def new_cube(name):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "_mesh"
    return obj


def test_schema(scene, journal):
    section("schema versioning")
    v1_entries = [{"t": "prop", "kind": "Scene", "name": scene.name,
                   "path": "render.use_simplify", "old": False, "new": True,
                   "tag": "legacy"}]
    scene.scenequant.journal_data = json.dumps(v1_entries)
    jrnl = journal.Journal.load(scene)
    check(jrnl.entries == v1_entries and jrnl.load_error is None,
          "legacy v1 bare-list journal loads")

    scene.scenequant.journal_data = ""
    jrnl = journal.Journal.load(scene)
    ok = jrnl.set_prop(scene, "render.use_simplify", True, "roundtrip")
    check(ok, "set_prop records a real change")
    jrnl.save(scene)
    stored = json.loads(scene.scenequant.journal_data)
    check(stored.get("v") == 2 and "session" in stored,
          "saved journal is a v2 wrapper with a session token")
    reloaded = journal.Journal.load(scene)
    check(reloaded.entries == jrnl.entries, "v2 journal round-trips")
    check(reloaded.revert_all() == 1 and scene.render.use_simplify is False,
          "v2 reload reverts cleanly")
    reloaded.save(scene)
    check(scene.scenequant.journal_data == "", "empty journal stores empty string")

    newer = json.dumps({"v": 3, "entries": [{"t": "prop"}]})
    scene.scenequant.journal_data = newer
    jrnl = journal.Journal.load(scene)
    check(not jrnl.entries and jrnl.load_error is not None,
          "newer schema (v3) refused with load_error")
    jrnl.save(scene)
    check(scene.scenequant.journal_data == newer,
          "save() refuses to clobber a journal it could not load")
    scene.scenequant.journal_data = ""


def test_corrupt(scene, journal):
    section("corrupt journal preservation")
    # A saved .blend gives the corrupt sidecar a home; unsaved files skip it.
    blend_path = os.path.join(tempfile.mkdtemp(prefix="sq_journal_"), "t.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    raw = '{"v": 2, "entries": [BROKEN'
    scene.scenequant.journal_data = raw
    jrnl = journal.Journal.load(scene)
    check(not jrnl.entries and jrnl.load_error is not None,
          "corrupt journal loads empty with load_error")
    corrupt_path = blend_path + ".scenequant.corrupt.json"
    preserved = os.path.exists(corrupt_path)
    check(preserved, "corrupt raw preserved to .scenequant.corrupt.json")
    if preserved:
        with open(corrupt_path, "r", encoding="utf-8") as handle:
            check(handle.read() == raw, "preserved corrupt copy is byte-identical")
    jrnl.save(scene)
    check(scene.scenequant.journal_data == raw,
          "save() does not overwrite corrupt-but-recoverable data")
    scene.scenequant.journal_data = ""


def test_read_back(scene, journal):
    section("read-back verification")
    jrnl = journal.Journal()
    old_x = scene.render.resolution_x
    # RNA clamps resolution_x to >= 4: the write cannot stick as requested.
    ok = jrnl.set_prop(scene, "render.resolution_x", 1, "clamped")
    check(ok is False and not jrnl.entries, "clamped write refused, not recorded")
    check(scene.render.resolution_x == old_x, "clamped write restored the old value")
    check(any(reason == "write did not stick" for _n, _p, reason in jrnl.skip_log),
          "skip_log records 'write did not stick'")

    # REVERT side of the same mechanism (was untested: replacing _revert_prop's
    # read-back with `return True` left every suite green). Journal a real
    # write, then tamper the recorded old value to one RNA will clamp: the
    # revert write cannot stick, must count as skipped, and must RETAIN the
    # entry instead of reporting success.
    jrnl = journal.Journal()
    check(jrnl.set_prop(scene, "render.resolution_x", 100, "clamped"),
          "legit write recorded for revert tampering")
    jrnl.entries[0]["old"] = 1  # below the RNA minimum of 4
    count = jrnl.revert_all()
    check(count == 0 and jrnl.skipped_on_revert == 1,
          "revert whose write cannot stick counts skipped, not reverted")
    check(len(jrnl.entries) == 1, "failed revert write RETAINS the entry")
    scene.render.resolution_x = old_x


def test_animated_skip(scene, journal):
    section("animated/driven property refusal")
    keyed = new_cube("KeyedCube")
    keyed.keyframe_insert(data_path="hide_render")
    driven = new_cube("DrivenCube")
    driven.driver_add("hide_viewport")
    jrnl = journal.Journal()
    ok = jrnl.set_prop(keyed, "hide_render", True, "trim")
    check(ok is False and not jrnl.entries,
          "keyframed property refused (covers 5.x layered actions)")
    ok = jrnl.set_prop(driven, "hide_viewport", True, "trim")
    check(ok is False and not jrnl.entries, "driven property refused")
    reasons = {reason for _n, _p, reason in jrnl.skip_log}
    check(reasons == {"animated/driven"}, f"skip reasons are animated/driven ({reasons})")
    bpy.data.objects.remove(keyed, do_unlink=True)
    bpy.data.objects.remove(driven, do_unlink=True)


def test_rename_and_honest_revert(scene, journal):
    section("rename-safe and honest revert")
    renamed = new_cube("RenameMe")
    jrnl = journal.Journal()
    check(jrnl.set_prop(renamed, "hide_render", True, "trim"), "write recorded")
    renamed.name = "RenamedAfterApply"
    check(jrnl.revert_all() == 1 and renamed.hide_render is False,
          "revert restores a renamed datablock via its session_uid")

    doomed = new_cube("DoomedCube")
    check(jrnl.set_prop(doomed, "hide_render", True, "trim"), "write recorded")
    entry = dict(jrnl.entries[0])
    bpy.data.objects.remove(doomed, do_unlink=True)
    count = jrnl.revert_all()
    check(count == 0 and jrnl.skipped_on_revert == 1,
          "revert of a deleted datablock counts skipped_on_revert")
    check(len(jrnl.entries) == 1 and jrnl.entries[0]["name"] == entry["name"],
          "failed revert RETAINS the entry")
    jrnl.save(scene)
    check(journal.Journal.load(scene).entry_count() == 1,
          "retained entry survives save/load")
    scene.scenequant.journal_data = ""
    bpy.data.objects.remove(renamed, do_unlink=True)


def test_last_writer_wins(scene, journal):
    section("last-writer-wins (draft over fit-budget)")
    cycles = scene.cycles
    original = cycles.samples
    jrnl = journal.Journal()
    check(jrnl.set_prop(scene, "cycles.samples", original + 100, "draft"),
          "draft write recorded")
    check(jrnl.set_prop(scene, "cycles.samples", original + 200, "quantize"),
          "later fit-budget write recorded")
    reverted = jrnl.revert_tag("draft")
    check(reverted == 0 and jrnl.last_superseded == 1,
          "superseded entry is consumed without counting as a write")
    check(cycles.samples == original + 200,
          "draft-off keeps the later fit-budget value (no resurrection)")
    check(len(jrnl.entries) == 1 and jrnl.entries[0]["old"] == original,
          "survivor inherited the true original value")
    check(jrnl.revert_all() == 1 and cycles.samples == original,
          "Revert All still reaches the true original")


def test_revert_run(scene, journal):
    section("run-scoped rollback")
    cycles = scene.cycles
    bounces = cycles.max_bounces
    samples = cycles.samples
    jrnl = journal.Journal()
    check(jrnl.set_prop(scene, "cycles.max_bounces", bounces + 2, "tune",
                        run_id="run-A"), "run write 1 recorded")
    check(jrnl.set_prop(scene, "cycles.samples", samples + 64, "tune",
                        run_id="run-A"), "run write 2 recorded")
    check(jrnl.set_prop(scene, "render.use_simplify", True, "tune"),
          "unscoped write recorded")
    check(jrnl.revert_run(None) == 0, "revert_run(None) reverts nothing")
    count = jrnl.revert_run("run-A")
    check(count == 2 and cycles.max_bounces == bounces and cycles.samples == samples,
          "revert_run rolls back exactly the run's writes")
    check(len(jrnl.entries) == 1 and scene.render.use_simplify is True,
          "unscoped entry untouched by run rollback")
    check(jrnl.revert_all() == 1 and scene.render.use_simplify is False,
          "remaining entry reverts")


def test_sidecar(scene, journal):
    section("sidecar write + recovery")
    # @persistent stamps the attribute with value None: existence is the signal.
    check(hasattr(journal._on_save_post, "_bpy_persistent"),
          "_on_save_post is @persistent (survives file loads)")
    jrnl = journal.Journal()
    check(jrnl.set_prop(scene, "render.use_simplify", True, "tune"),
          "entry to persist recorded")
    jrnl.save(scene)
    bpy.ops.wm.save_mainfile()
    sidecar = journal.sidecar_path()
    check(bool(sidecar) and os.path.exists(sidecar), "sidecar written on save")
    with open(sidecar, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    check(data.get("v") == 2 and scene.name in data.get("scenes", {}),
          "sidecar is v2 and keyed per scene")

    scene.scenequant.journal_data = ""  # simulate the post-crash empty journal
    restored = journal.recover_from_sidecar(scene)
    check(restored == 1, f"recover_from_sidecar restores the entry ({restored})")
    recovered = journal.Journal.load(scene)
    check(recovered.entry_count() == 1
          and all("ptr" not in entry for entry in recovered.entries),
          "recovered entries have stale ptr fields stripped")
    check(journal.recover_from_sidecar(scene) == 0,
          "recovery refuses to overwrite a live journal")
    check(recovered.revert_all() == 1 and scene.render.use_simplify is False,
          "recovered journal reverts")
    recovered.save(scene)
    bpy.ops.wm.save_mainfile()
    check(not os.path.exists(sidecar), "sidecar deleted when no scene has entries")


def main():
    import scenequant
    from scenequant import journal
    scenequant.register()
    clear_default_scene()
    scene = bpy.context.scene

    test_schema(scene, journal)
    test_read_back(scene, journal)
    test_animated_skip(scene, journal)
    test_rename_and_honest_revert(scene, journal)
    test_last_writer_wins(scene, journal)
    test_revert_run(scene, journal)
    test_corrupt(scene, journal)   # saves the .blend: run before the sidecar test
    test_sidecar(scene, journal)
    finish()


main()
