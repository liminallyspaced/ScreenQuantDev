# Write-through optimization journal. Invariant: every scene/datablock write any
# SceneQuant feature performs goes through Journal.set_prop or Journal.record_action,
# so one Revert All restores the scene. Entries are JSON-serializable and persisted
# to scene.scenequant.journal_data plus a sidecar file on save.
#
# Storage schema v2: {"v": 2, "session": token, "entries": [...]}. load() also
# accepts legacy v1 bare entry lists; newer schemas are refused untouched.
# Every journaled write is read back after setattr: a value that did not stick
# (Edit Mode, driven property, RNA clamping) is never recorded, and a revert
# write that did not stick keeps its entry so the change stays revertible.
#
# Datablock identity: entries carry ID.session_uid, which is unique for the
# whole Blender session and — unlike as_pointer() — never recycled onto a
# different datablock after a delete. Uids die with the session that minted
# them, so load() strips them from entries stored by another session. Entries
# that lost their uid fall back to a NAME lookup on revert; that is the one
# residual risk left in this module: after reopening a .blend, a datablock
# recreated with a journaled name is indistinguishable from the original and
# will be reverted onto. Same-session entries never take that risk — a uid
# that no longer resolves is an honest failure, and the entry is retained.

import json
import math
import os
import uuid

import bpy
from bpy.app.handlers import persistent

SCHEMA_VERSION = 2
FLOAT_TOLERANCE = 1e-5      # read-back match: relative
FLOAT_ABS_TOLERANCE = 1e-9  # read-back match: absolute, for values near zero
_SESSION = uuid.uuid4().hex

ID_KINDS = {
    "Scene": "scenes",
    "Object": "objects",
    "Mesh": "meshes",
    "Image": "images",
    "Material": "materials",
    "World": "worlds",
}


def _kind_of(datablock):
    for type_name in ID_KINDS:
        if isinstance(datablock, getattr(bpy.types, type_name)):
            return type_name
    return None


def _session_uid(datablock):
    """ID.session_uid (Blender 4.2+), or None on a build without it — such an
    entry is recorded name-only and reverts like a cross-session one."""
    uid = getattr(datablock, "session_uid", None)
    return uid if isinstance(uid, int) else None


def _find_datablock(kind, name, uid=None):
    """Resolve a journaled datablock: by session_uid when the entry still has
    one, else by name.

    A uid identifies the exact datablock regardless of renames, and never
    matches a different one. When it fails to resolve the datablock is gone,
    and there is deliberately NO name fallback: a same-name datablock created
    after the original was deleted is an impostor, and reverting onto it would
    silently rewire unrelated data. Name lookup is reached only by entries
    whose uid load() stripped as cross-session.
    """
    collection = getattr(bpy.data, ID_KINDS.get(kind, ""), None)
    if collection is None:
        return None
    if uid is not None:
        for candidate in collection:
            if _session_uid(candidate) == uid:
                return candidate
        return None
    return collection.get(name) if isinstance(name, str) else None


def _resolve_owner(datablock, rna_path):
    """Resolve 'a.b.c' or 'modifiers["Name"].prop' to (owner, final_attr).

    Uses RNA path_resolve so collection subscripts work; the final segment is
    split off textually and never contains brackets by construction.
    Returns (None, None) if any hop is missing (e.g. modifier deleted).
    """
    if "." not in rna_path:
        return datablock, rna_path
    prefix, attr = rna_path.rsplit(".", 1)
    try:
        owner = datablock.path_resolve(prefix)
    except ValueError:
        return None, None
    if owner is None:
        return None, None
    return owner, attr


def _values_match(expected, actual):
    """Read-back comparison: floats within FLOAT_TOLERANCE relative, sequences
    element-wise, bool/int/str/enum exact.

    The absolute floor only covers exact-zero round-trips; anything larger
    would call a write that landed on 0.0 instead of a small requested value
    a match, and record fiction.
    """
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, float) or isinstance(actual, float):
        try:
            return math.isclose(expected, actual,
                                rel_tol=FLOAT_TOLERANCE,
                                abs_tol=FLOAT_ABS_TOLERANCE)
        except TypeError:
            return False
    if isinstance(expected, str) or isinstance(actual, str):
        return expected == actual
    try:
        expected_seq, actual_seq = list(expected), list(actual)
    except TypeError:
        return expected == actual
    if len(expected_seq) != len(actual_seq):
        return False
    return all(_values_match(e, a) for e, a in zip(expected_seq, actual_seq))


def _action_fcurves(action):
    """Fcurves across API generations: legacy Action.fcurves (<= 4.x) and
    layered slotted actions (Action.layers, the only surface on 5.x). All
    slots are scanned — over-matching skips a write, the safe direction."""
    yield from getattr(action, "fcurves", None) or ()
    for layer in getattr(action, "layers", None) or ():
        for strip in getattr(layer, "strips", None) or ():
            for bag in getattr(strip, "channelbags", None) or ():
                yield from getattr(bag, "fcurves", None) or ()


def _action_drives_path(action, path):
    return any(fcurve.data_path == path for fcurve in _action_fcurves(action))


def _is_animated(owner, attr):
    """True if the resolved property is driven or keyframed on its owning ID.

    Journaled writes to animated properties record fiction: the render
    evaluates the animation, not the written value. Best effort by design —
    any RNA/API surprise (future action shapes, unresolvable paths) reads as
    False.
    """
    try:
        id_data = owner.id_data
        anim = getattr(id_data, "animation_data", None)
        if anim is None:
            return False
        path = attr if owner is id_data else owner.path_from_id(attr)
        for fcurve in getattr(anim, "drivers", None) or ():
            if fcurve.data_path == path:
                return True
        action = getattr(anim, "action", None)
        if action is not None and _action_drives_path(action, path):
            return True
        # NLA-only animation: animation_data.action is None and the action
        # lives on a strip, but the render still evaluates it.
        for track in getattr(anim, "nla_tracks", None) or ():
            for strip in getattr(track, "strips", None) or ():
                strip_action = getattr(strip, "action", None)
                if strip_action is not None and _action_drives_path(strip_action, path):
                    return True
    except Exception:
        return False
    return False


_REQUIRED_KEYS = {
    "prop": ("kind", "name", "path", "old", "new", "tag"),
    "action": ("kind", "payload", "tag"),
}
# Payload fields naming a datablock, per action kind: (name key, kind, uid key).
_PAYLOAD_IDS = {
    "TEX_SWAP": (("orig_image", "Image", "orig_uid"),
                 ("new_image", "Image", "new_uid")),
    "DATA_RELINK": (("object", "Object", "object_uid"),
                    ("old_mesh", "Mesh", "old_mesh_uid")),
    "NODE_UNLINK": (("material", "Material", "material_uid"),),
}


def _entry_ok(entry):
    """True for an entry every consumer can read without guessing. JSON-valid
    but shape-invalid entries reach here from hand-edited or foreign journals;
    dropping them at load keeps bare subscripts safe everywhere downstream."""
    if not isinstance(entry, dict):
        return False
    required = _REQUIRED_KEYS.get(entry.get("t"))
    if required is None or not all(key in entry for key in required):
        return False
    if not isinstance(entry.get("tag"), str) or not isinstance(entry.get("kind"), str):
        return False
    if entry["t"] == "prop":
        return isinstance(entry.get("name"), str) and isinstance(entry.get("path"), str)
    return isinstance(entry.get("payload"), dict)


def _chain_key(entry):
    """Identity of the property an entry writes, for last-writer-wins chaining.

    Keyed on the uid while the entry is session-current, so two runs still
    chain across a rename of the datablock between them; name-keyed only once
    the uid is gone, which is also the point at which a rename is undetectable.
    """
    identity = entry.get("uid")
    if identity is None:
        identity = entry.get("name")
    return (entry.get("kind"), identity, entry.get("path"))


def _strip_session_ids(entries):
    """Drop the session-scoped ids from entries stored by another session.

    Uids from a dead session either resolve to nothing or, worse, to whatever
    datablock the new session happened to mint with that uid, so they are
    removed and the entries fall back to name lookup. "ptr" is the field this
    schema used before uids and is stripped wherever it survives.
    """
    stripped = []
    for entry in entries:
        if not isinstance(entry, dict):
            stripped.append(entry)
            continue
        clean = {k: v for k, v in entry.items() if k not in ("uid", "ptr")}
        payload = clean.get("payload")
        if isinstance(payload, dict):
            uid_keys = {uid_key for _n, _k, uid_key in _PAYLOAD_IDS.get(clean.get("kind"), ())}
            clean["payload"] = {k: v for k, v in payload.items() if k not in uid_keys}
        stripped.append(clean)
    return stripped


def _stamp_payload_uids(kind, payload):
    """Return a copy of an action payload with a session_uid recorded next to
    every datablock name it references, so revert survives a rename and refuses
    a same-name impostor. Names stay: they are the cross-session fallback."""
    ids = _PAYLOAD_IDS.get(kind)
    if not ids or not isinstance(payload, dict):
        return payload
    stamped = dict(payload)
    for name_key, id_kind, uid_key in ids:
        datablock = _find_datablock(id_kind, payload.get(name_key))
        uid = _session_uid(datablock) if datablock is not None else None
        if uid is not None:
            stamped[uid_key] = uid
    return stamped


class Journal:
    def __init__(self, entries=None):
        self.entries = entries or []
        self.skipped_on_revert = 0
        # Entries a revert consumed by transferring their pre-value into a
        # later surviving write — real bookkeeping, but zero writes performed.
        self.last_superseded = 0
        # (datablock_name, rna_path, reason) per refused write this instance.
        self.skip_log = []
        # Set when load() could not faithfully read the stored journal.
        self.load_error = None
        # True when load() trusted NOTHING it read (so save() must not clobber).
        self.load_refused = False
        # Raw stored string load() could not fully read, kept for quarantine.
        self.preserved_raw = None

    @classmethod
    def load(cls, scene, preserve_corrupt=True):
        """Read the stored journal, keeping only well-formed entries.

        preserve_corrupt=False skips every filesystem write, for read-only
        callers (UI redraw) that must not touch the disk on each redraw.
        """
        raw = scene.scenequant.journal_data
        jrnl = cls()
        if not raw:
            return jrnl
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            jrnl._refuse(raw, "journal data unreadable", preserve_corrupt)
            return jrnl
        if isinstance(data, list):  # legacy v1: a bare entry list, no session
            jrnl._accept(_strip_session_ids(data), raw, preserve_corrupt)
            return jrnl
        if isinstance(data, dict):
            version = data.get("v")
            if isinstance(version, int) and version > SCHEMA_VERSION:
                jrnl._refuse(
                    raw,
                    f"journal schema v{version} is newer than supported "
                    f"v{SCHEMA_VERSION}; not touching it",
                    preserve_corrupt, located=False)
                return jrnl
            entries = data.get("entries")
            if isinstance(entries, list):
                if data.get("session") != _SESSION:
                    entries = _strip_session_ids(entries)
                jrnl._accept(entries, raw, preserve_corrupt)
                return jrnl
        jrnl._refuse(raw, "journal data unrecognized", preserve_corrupt)
        return jrnl

    def _refuse(self, raw, reason, preserve, located=True):
        """Nothing in the stored data could be trusted: keep every byte of it."""
        preserved = _preserve_corrupt(raw) if preserve else False
        self.preserved_raw = raw
        self.load_refused = True
        self.load_error = f"{reason}; {_where(preserved)}" if located else reason

    def _accept(self, entries, raw, preserve):
        """Take the well-formed entries live and quarantine the raw string if
        any had to be dropped — a shape this build cannot read is never thrown
        away, only removed from the live list."""
        self.entries = [entry for entry in entries if _entry_ok(entry)]
        dropped = len(entries) - len(self.entries)
        if dropped:
            if preserve:
                _preserve_corrupt(raw)
            self.preserved_raw = raw
            self.load_error = f"{dropped} malformed entries quarantined"

    def save(self, scene):
        if self.load_refused and not self.entries:
            # Refuse to clobber stored data this instance could not load.
            return
        if self.preserved_raw:
            # Overwriting is unavoidable now (there are live entries to
            # persist): park the unreadable original on the scene first.
            _quarantine(scene, self.preserved_raw)
        if not self.entries:
            scene.scenequant.journal_data = ""
            return
        scene.scenequant.journal_data = json.dumps(
            {"v": SCHEMA_VERSION, "session": _SESSION, "entries": self.entries})

    def entry_count(self):
        return len(self.entries)

    def tags(self):
        seen = []
        for entry in self.entries:
            tag = entry.get("tag") if isinstance(entry, dict) else None
            if tag is not None and tag not in seen:
                seen.append(tag)
        return seen

    def set_prop(self, datablock, rna_path, value, tag, run_id=None):
        """Record then write, verifying the write stuck. Returns True only if
        the property existed, changed, and read back as the requested value.
        Refused writes (animated/driven target, value did not stick) are
        appended to self.skip_log with a reason."""
        kind = _kind_of(datablock)
        if kind is None:
            return False
        owner, attr = _resolve_owner(datablock, rna_path)
        if owner is None or not hasattr(owner, attr):
            return False
        old = _to_json_value(getattr(owner, attr))
        new = _to_json_value(value)
        if old == new:
            return False
        if _is_animated(owner, attr):
            self.skip_log.append((datablock.name, rna_path, "animated/driven"))
            return False
        try:
            setattr(owner, attr, value)
        except (AttributeError, TypeError):
            return False
        if not _values_match(new, _to_json_value(getattr(owner, attr))):
            # Silent no-op or clamped write (Edit Mode, RNA limits): put the
            # old value back and refuse to record fiction.
            try:
                setattr(owner, attr, old)
            except (AttributeError, TypeError):
                pass
            self.skip_log.append((datablock.name, rna_path, "write did not stick"))
            return False
        entry = {
            "t": "prop",
            "kind": kind,
            "name": datablock.name,
            "path": rna_path,
            "old": old,
            "new": new,
            "tag": tag,
        }
        uid = _session_uid(datablock)
        if uid is not None:
            entry["uid"] = uid
        if run_id is not None:
            entry["run"] = run_id
        self.entries.append(entry)
        return True

    def record_action(self, kind, payload, tag, run_id=None):
        entry = {"t": "action", "kind": kind,
                 "payload": _stamp_payload_uids(kind, payload), "tag": tag}
        if run_id is not None:
            entry["run"] = run_id
        self.entries.append(entry)

    def revert_all(self):
        return self._revert(list(self.entries))

    def revert_tag(self, tag):
        return self._revert([e for e in self.entries if e.get("tag") == tag])

    def revert_run(self, run_id):
        """Roll back one operator invocation recorded with run_id (all-or-nothing
        apply support). Same last-writer-wins semantics as revert_tag."""
        if run_id is None:
            return 0
        return self._revert([e for e in self.entries if e.get("run") == run_id])

    def _revert(self, selected):
        """Revert selected entries newest-first. Failed entries stay in the
        journal (counted in skipped_on_revert). Last-writer-wins: a selected
        write superseded by a later surviving write of the same property is
        not replayed — its pre-value is transferred into that survivor's "old"
        so a later revert still reaches the true original.

        Returns the number of entries that actually WROTE something. Entries
        consumed by transfer changed no scene state and are counted separately
        in self.last_superseded, so callers never report writes that a
        transfer merely bookkept.
        """
        self.skipped_on_revert = 0
        self.last_superseded = 0
        count = 0
        consumed = set()
        for entry in reversed(selected):
            survivor = self._later_surviving_writer(entry, consumed)
            if survivor is not None:
                survivor["old"] = entry.get("old")
                consumed.add(id(entry))
                self.last_superseded += 1
                continue
            if self._revert_entry(entry):
                consumed.add(id(entry))
                count += 1
            else:
                self.skipped_on_revert += 1
        self.entries = [e for e in self.entries if id(e) not in consumed]
        return count

    def _later_surviving_writer(self, entry, consumed):
        """Nearest entry after `entry` writing the same property that will
        outlive this revert pass, or None. Newest-first processing guarantees
        every later selected entry has already been consumed or kept-as-failed
        by the time `entry` is examined."""
        if entry.get("t") != "prop":
            return None
        key = _chain_key(entry)
        seen_entry = False
        for candidate in self.entries:
            if candidate is entry:
                seen_entry = True
                continue
            if not seen_entry or id(candidate) in consumed:
                continue
            if candidate.get("t") != "prop":
                continue
            if _chain_key(candidate) == key:
                return candidate
        return None

    def _revert_entry(self, entry):
        if entry.get("t") == "prop":
            return self._revert_prop(entry)
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return False
        if entry.get("kind") == "TEX_SWAP":
            return self._revert_tex_swap(payload)
        if entry.get("kind") == "DATA_RELINK":
            return self._revert_data_relink(payload)
        if entry.get("kind") == "NODE_UNLINK":
            return self._revert_node_unlink(payload)
        return False

    def _revert_prop(self, entry):
        datablock = _find_datablock(entry.get("kind"), entry.get("name"),
                                    entry.get("uid"))
        if datablock is None:
            return False
        path = entry.get("path")
        if not isinstance(path, str):
            return False
        owner, attr = _resolve_owner(datablock, path)
        if owner is None or not hasattr(owner, attr):
            return False
        try:
            setattr(owner, attr, entry.get("old"))
        except (AttributeError, TypeError):
            return False
        # Read back: a revert that did not stick must not consume the entry.
        return _values_match(entry.get("old"), _to_json_value(getattr(owner, attr)))

    def _revert_tex_swap(self, payload):
        """Two-phase and all-or-nothing.

        Phase 1 resolves EVERY recorded pair without writing anything, so a
        pair that can no longer be reached (deleted material, node gone) aborts
        the revert with the scene untouched instead of leaving it half
        restored behind a permanently failing entry. Only once every pair is
        resolved and rewritten — and re-verified — is fake_user stripped and
        the replacement removed: that fake_user may be the only thing keeping
        the full-res image alive.
        """
        original = _find_datablock("Image", payload.get("orig_image"),
                                   payload.get("orig_uid"))
        replacement = _find_datablock("Image", payload.get("new_image"),
                                      payload.get("new_uid"))
        if original is None:
            return False
        pairs = payload.get("users") or []
        resolved = []
        for pair in pairs:
            nodes = _swap_nodes(pair, original, replacement)
            if nodes is None:
                return False
            resolved.append(nodes)
        for nodes in resolved:
            for node in nodes:
                if getattr(node, "image", None) is replacement:
                    node.image = original
        for nodes in resolved:
            if not all(getattr(node, "image", None) is original for node in nodes):
                return False
        original.use_fake_user = payload.get("orig_had_fake_user", False)
        if replacement is not None and replacement.users == 0:
            bpy.data.images.remove(replacement)
        return True

    def _revert_node_unlink(self, payload):
        """Restore one unlinked shader socket. Additive journal kind."""
        mat = _find_datablock("Material", payload.get("material"),
                              payload.get("material_uid"))
        if mat is None:
            return False
        try:
            from .analysis.dead_closures import restore_node_unlink_on_material
        except Exception:
            return False
        return restore_node_unlink_on_material(mat, payload)

    def _revert_data_relink(self, payload):
        obj = _find_datablock("Object", payload.get("object"),
                              payload.get("object_uid"))
        old_mesh = _find_datablock("Mesh", payload.get("old_mesh"),
                                   payload.get("old_mesh_uid"))
        if obj is None or old_mesh is None:
            return False
        try:
            obj.data = old_mesh
        except TypeError:
            return False
        if obj.data is not old_mesh:
            # Edit Mode assignment is a silent no-op on 4.5 and 5.1.
            return False
        old_mesh.use_fake_user = payload.get("old_had_fake_user", False)
        return True


def _find_nodes(node_tree, node_name, _visited=None, _depth=0):
    """Yield EVERY node named node_name in the tree, recursing into groups.

    Names repeat across group instances, so callers must disambiguate matches
    (e.g. by the image a node currently shows). Visited-set guards reused groups.
    """
    if _visited is None:
        _visited = set()
    if _depth > 8 or node_tree in _visited:
        return
    _visited.add(node_tree)
    for candidate in node_tree.nodes:
        if candidate.name == node_name:
            yield candidate
        if candidate.type == "GROUP" and candidate.node_tree:
            yield from _find_nodes(candidate.node_tree, node_name, _visited, _depth + 1)


def _swap_nodes(pair, original, replacement):
    """Nodes a TEX_SWAP pair covers, or None when the pair cannot be resolved.

    Node names repeat across nested group instances, so a pair resolves only
    through nodes actually showing the swapped-in image (or already showing the
    original, i.e. restored by a previous pass). An empty result is a failure,
    not a no-op: the recorded node is gone and the revert cannot be completed.
    """
    try:
        mat_name, node_name = pair
    except (TypeError, ValueError):
        return None
    mat = bpy.data.materials.get(mat_name) if isinstance(mat_name, str) else None
    if mat is None or not mat.node_tree:
        return None
    matched = []
    for node in _find_nodes(mat.node_tree, node_name):
        image = getattr(node, "image", None)
        if image is original or (replacement is not None and image is replacement):
            matched.append(node)
    return matched or None


def _to_json_value(value):
    if isinstance(value, (bool, int, float, str)):
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def sidecar_path():
    blend = bpy.data.filepath
    return blend + ".scenequant.json" if blend else ""


def _corrupt_path():
    blend = bpy.data.filepath
    return blend + ".scenequant.corrupt.json" if blend else ""


def _preserve_corrupt(raw):
    """Best effort: park journal data load() could not read beside the .blend
    before a later save() can overwrite it. Returns whether a file was actually
    written — an unsaved .blend has nowhere to put one, and the caller must not
    claim otherwise. Never raises."""
    path = _corrupt_path()
    if not path:
        return False
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(raw)
    except OSError:
        return False
    return True


def _where(preserved):
    return ("raw copy saved beside the .blend" if preserved
            else "raw copy kept on the scene")


def _quarantine(scene, raw):
    """Stash unreadable journal data on the scene before save() overwrites it.
    The property is optional so this module still loads against a build without
    it; the .corrupt.json copy is the fallback there. Never raises."""
    settings = getattr(scene, "scenequant", None)
    if not raw or not hasattr(settings, "journal_quarantine"):
        return
    try:
        settings.journal_quarantine = raw
    except (AttributeError, TypeError):
        pass


def _scene_journal_state(scene):
    """(entries, readable) for a scene's stored journal.

    readable is False only when NON-EMPTY stored data could not be parsed into
    an entry list this build can re-serialize. Callers must not treat that as
    "no entries": an unreadable journal is exactly when the existing sidecar is
    the last good recovery copy.
    """
    raw = scene.scenequant.journal_data
    if not raw:
        return [], True
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return [], False
    if isinstance(data, list):
        return data, True
    if not isinstance(data, dict):
        return [], False
    version = data.get("v")
    if isinstance(version, int) and version > SCHEMA_VERSION:
        return [], False
    entries = data.get("entries")
    if isinstance(entries, list):
        return entries, True
    return [], False


def write_sidecar(scene=None):
    """Best effort crash-recovery copy of EVERY scene's journal next to the
    .blend, as {"v": 2, "scenes": {scene_name: entries}}. The scene argument
    is accepted for API compatibility and ignored. Never raises."""
    path = sidecar_path()
    if not path:
        return
    try:
        scenes = {}
        all_readable = True
        for candidate in bpy.data.scenes:
            entries, readable = _scene_journal_state(candidate)
            all_readable = all_readable and readable
            if entries:
                scenes[candidate.name] = entries
        if not scenes:
            # Delete only when every scene is verifiably empty. A journal this
            # build cannot parse is not an empty one, and the sidecar it would
            # take with it is the last recoverable copy of that data.
            if all_readable and os.path.exists(path):
                os.remove(path)
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"v": SCHEMA_VERSION, "scenes": scenes}))
        os.replace(tmp, path)
    except Exception:
        pass


def recover_from_sidecar(scene):
    """Restore this scene's journal entries from the sidecar after a crash.

    Fills the live journal only when it is empty and loadable; returns the
    number of entries restored (0 on any miss or failure). Session ids are
    stripped: the sidecar is by definition from another Blender session.
    """
    path = sidecar_path()
    if not path:
        return 0
    try:
        live = Journal.load(scene)
        if live.entries or live.load_error:
            return 0
        with open(path, "r", encoding="utf-8") as handle:
            data = json.loads(handle.read())
        entries = _sidecar_scene_entries(data, scene.name)
        if not entries:
            return 0
        entries = _strip_session_ids(entries)
        Journal(entries).save(scene)
        return len(entries)
    except Exception:
        return 0


def _sidecar_scene_entries(data, scene_name):
    if isinstance(data, list):  # legacy sidecar: one raw v1 journal
        return data
    if not isinstance(data, dict):
        return None
    version = data.get("v")
    if isinstance(version, int) and version > SCHEMA_VERSION:
        return None
    scenes = data.get("scenes")
    if isinstance(scenes, dict):
        entries = scenes.get(scene_name)
        return entries if isinstance(entries, list) else None
    entries = data.get("entries")  # tolerate a single-journal v2 dict
    return entries if isinstance(entries, list) else None


@persistent
def _on_save_post(*_args):
    write_sidecar()


@persistent
def _on_load_post(*_args):
    """Start a new session token on every file load.

    Opening a .blend replaces every datablock in Main, so the session_uids the
    previous contents were journaled under are dead — but the process (and this
    module's globals) live on. Rotating the token is what makes load() strip
    those uids and fall back to name lookup, instead of trusting a uid that now
    belongs to whatever the new file minted.
    """
    global _SESSION
    _SESSION = uuid.uuid4().hex


def register():
    if _on_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(_on_save_post)
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)


def unregister():
    if _on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(_on_save_post)
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
