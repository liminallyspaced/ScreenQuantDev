# L3 UNUSED_SLOTS classifier + journaled apply.
# Duck-typed meshes; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_unused_slots.py

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402


def _load(rel):
    path = os.path.join(PROJECT_ROOT, *rel.split("/"))
    name = rel.replace("/", ".").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


us = _load("scenequant/analysis/unused_slots.py")
speed_solver = _load("scenequant/planning/speed_solver.py")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Poly:
    def __init__(self, material_index):
        self.material_index = material_index


class _MatCol:
    """Duck-typed mesh.materials. pop() remaps face indices like Blender."""

    def __init__(self, items, mesh=None):
        self._items = list(items)
        self.mesh = mesh

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __setitem__(self, index, value):
        self._items[index] = value

    def append(self, value):
        self._items.append(value)

    def pop(self, index=-1):
        mat = self._items.pop(index)
        if self.mesh is not None:
            for poly in self.mesh.polygons:
                if poly.material_index > index:
                    poly.material_index -= 1
        return mat


class _Slot:
    def __init__(self, col, index):
        self._col = col
        self._index = index

    @property
    def material(self):
        if 0 <= self._index < len(self._col):
            return self._col[self._index]
        return None


class _SlotView:
    def __init__(self, col):
        self._col = col

    def __iter__(self):
        for i in range(len(self._col)):
            yield _Slot(self._col, i)

    def __len__(self):
        return len(self._col)

    def __getitem__(self, index):
        return _Slot(self._col, index)


class _Journal:
    def __init__(self):
        self.entries = []

    def record_action(self, kind, payload, tag, run_id=None):
        entry = {"t": "action", "kind": kind, "payload": dict(payload),
                 "tag": tag}
        if run_id is not None:
            entry["run"] = run_id
        self.entries.append(entry)


def _mat(name, node_tree=None, use_nodes=None):
    kw = dict(name=name, library=None, override_library=None)
    if node_tree is not None:
        kw["node_tree"] = node_tree
        kw["use_nodes"] = True if use_nodes is None else use_nodes
    elif use_nodes is not None:
        kw["use_nodes"] = use_nodes
    return Obj(**kw)


class _Sock:
    def __init__(self, name, default=None, identifier=None):
        self.name = name
        self.identifier = identifier or name
        self.default_value = default
        self.is_linked = False
        self.links = []
        self.node = None


class _SockMap:
    def __init__(self, items):
        self._items = list(items)
        self._by = {}
        for sock in self._items:
            self._by[sock.name] = sock
            self._by[sock.identifier] = sock

    def get(self, key):
        return self._by.get(key)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._items[key]
        sock = self._by.get(key)
        if sock is None:
            raise KeyError(key)
        return sock


class _Link:
    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class _Node:
    def __init__(self, name, ntype, inputs=None, outputs=None, **kw):
        self.name = name
        self.type = ntype
        self.bl_idname = kw.pop("bl_idname", "")
        self.node_tree = kw.pop("node_tree", None)
        self.attribute_name = kw.pop("attribute_name", "")
        for key, value in kw.items():
            setattr(self, key, value)
        self.inputs = _SockMap(inputs or [])
        self.outputs = _SockMap(outputs or [])
        for sock in self.inputs:
            sock.node = self
        for sock in self.outputs:
            sock.node = self


class _Tree:
    def __init__(self, nodes):
        self.nodes = list(nodes)


def _plain_tree():
    prin = _Node(
        "Principled BSDF", "BSDF_PRINCIPLED",
        inputs=[_Sock("Base Color"), _Sock("Alpha", 1.0)],
        outputs=[_Sock("BSDF")],
    )
    out = _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume")],
    )
    return _Tree([prin, out])


def _tex_image_tree():
    tex = _Node(
        "Image Texture", "TEX_IMAGE",
        inputs=[_Sock("Vector")],
        outputs=[_Sock("Color"), _Sock("Alpha")],
        bl_idname="ShaderNodeTexImage",
    )
    prin = _Node(
        "Principled BSDF", "BSDF_PRINCIPLED",
        inputs=[_Sock("Base Color"), _Sock("Alpha", 1.0)],
        outputs=[_Sock("BSDF")],
    )
    out = _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume")],
    )
    return _Tree([tex, prin, out])


def _normal_map_tree():
    nmap = _Node(
        "Normal Map", "NORMAL_MAP",
        inputs=[_Sock("Color"), _Sock("Strength", 1.0)],
        outputs=[_Sock("Normal")],
        bl_idname="ShaderNodeNormalMap",
    )
    prin = _Node(
        "Principled BSDF", "BSDF_PRINCIPLED",
        inputs=[_Sock("Base Color"), _Sock("Normal")],
        outputs=[_Sock("BSDF")],
    )
    out = _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume")],
    )
    return _Tree([nmap, prin, out])


def _mesh_data(name, materials, face_indices, library=None):
    data = Obj(
        name=name, library=library, override_library=None,
        polygons=[_Poly(i) for i in face_indices],
        materials=None,
    )
    data.materials = _MatCol(materials, mesh=data)
    return data


def _obj(name, data, library=None, override="AUTO", hide_render=False):
    return Obj(
        name=name, type="MESH", hide_render=hide_render, data=data,
        library=library, override_library=None,
        scenequant=Obj(override=override),
        material_slots=_SlotView(data.materials),
    )


def _scene(objects, **kw):
    data = dict(
        objects=objects, world=None, view_layers=[],
        use_nodes=False, node_tree=None, compositing_node_group=None,
        cycles=Obj(samples=256),
        materials_by_name={},
    )
    data.update(kw)
    scene = Obj(**data)
    by_name = dict(scene.materials_by_name)
    for obj in objects:
        mesh = getattr(obj, "data", None)
        mats = getattr(mesh, "materials", None) if mesh is not None else None
        if mats is None:
            continue
        for mat in list(mats):
            if mat is not None and getattr(mat, "name", None):
                by_name[mat.name] = mat
    scene.materials_by_name = by_name
    return scene


def _names(mats):
    return [getattr(m, "name", None) if m is not None else None for m in mats]


def _mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
               per_image_mb={})


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def speed_solver_scene(objects):
    cycles = Obj(
        device="GPU", use_adaptive_sampling=True, adaptive_threshold=0.02,
        samples=256, use_denoising=True, adaptive_min_samples=48,
        max_bounces=8, diffuse_bounces=3, glossy_bounces=4,
        transmission_bounces=6, transparent_max_bounces=8,
        sample_clamp_indirect=5.0, blur_glossy=1.0, use_light_tree=True,
        caustics_reflective=False, caustics_refractive=False,
        use_guiding=False, use_animated_seed=True, use_camera_cull=False,
        denoising_use_gpu=True,
    )
    render = Obj(
        engine="CYCLES", use_lock_interface=True, use_persistent_data=True,
        use_motion_blur=False, compositor_device="GPU",
    )
    scene = _scene(objects)
    scene.cycles = cycles
    scene.render = render
    scene.frame_start = 1
    scene.frame_end = 1
    scene.camera = Obj()
    scene.cycles_curves = Obj(shape="RIBBONS")
    return scene


def test_unused_extra_slot_pruned():
    section("unused extra slot pruned; used slot kept")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    data = _mesh_data("rug", [carpet, lamp], [0, 0, 0])
    obj = _obj("Rug", data)
    scene = _scene([obj], materials_by_name={"Carpet": carpet, "Lamp": lamp})
    records = us.classify_unused_slots(scene)
    check(len(records) == 1 and records[0]["index"] == 1
          and records[0]["material"] == "Lamp"
          and records[0]["unique_shader"] is True,
          "inventory flags the unused extra slot")
    check(all(r["index"] != 0 for r in records),
          "used slot 0 is not a prune candidate")
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(len(applied) == 1 and applied[0]["index"] == 1,
          "apply removes the unused extra slot")
    check(_names(data.materials) == ["Carpet"],
          "used Carpet slot remains; Lamp slot gone")
    check(all(p.material_index == 0 for p in data.polygons),
          "face indices still point at Carpet")
    check(jrnl.entries and jrnl.entries[0]["kind"] == us.ACTION_KIND,
          "journal records SLOT_REMOVE")


def test_used_slot_kept_middle_unused():
    section("used slots kept when an unused slot sits in the middle")
    a = _mat("A")
    extra = _mat("Extra")
    b = _mat("B")
    data = _mesh_data("body", [a, extra, b], [0, 2, 0, 2])
    obj = _obj("Body", data)
    scene = _scene([obj], materials_by_name={"A": a, "Extra": extra, "B": b})
    records = us.classify_unused_slots(scene)
    check([r["index"] for r in records] == [1],
          "only the unused middle slot is a candidate")
    jrnl = _Journal()
    us.apply_unused_slots(scene, jrnl)
    check(_names(data.materials) == ["A", "B"],
          "used A and B kept after middle-slot pop")
    check(sorted({p.material_index for p in data.polygons}) == [0, 1],
          "Blender-style pop remaps B faces 2 → 1")


def test_linked_mesh_skipped():
    section("linked mesh skipped")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    data = _mesh_data("linked_rug", [carpet, lamp], [0], library=Obj())
    obj = _obj("LinkedRug", data)
    scene = _scene([obj], materials_by_name={"Carpet": carpet, "Lamp": lamp})
    records = us.classify_unused_slots(scene)
    check(records == [], "mesh.library → no prune records")
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(applied == [] and _names(data.materials) == ["Carpet", "Lamp"],
          "linked mesh is not written")

    data2 = _mesh_data("obj_linked", [carpet, lamp], [0])
    obj2 = _obj("ObjLinked", data2, library=Obj())
    scene2 = _scene([obj2], materials_by_name={"Carpet": carpet, "Lamp": lamp})
    check(us.classify_unused_slots(scene2) == [],
          "obj.library → no prune records")


def test_all_slots_used_noop():
    section("unique mesh with all slots used is no-op")
    a = _mat("A")
    b = _mat("B")
    data = _mesh_data("two", [a, b], [0, 1, 0, 1])
    obj = _obj("Two", data)
    scene = _scene([obj], materials_by_name={"A": a, "B": b})
    records = us.classify_unused_slots(scene)
    check(records == [], "all-used unique mesh has no unused slots")
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(applied == [] and jrnl.entries == [],
          "all-used unique mesh apply is a no-op")
    check(_names(data.materials) == ["A", "B"], "slots unchanged")


def test_revert_restores():
    section("revert restores removed slot at original index")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    extra = _mat("Spare")
    data = _mesh_data("rug", [carpet, extra, lamp], [0, 2, 0])
    obj = _obj("Rug", data)
    mats = {"Carpet": carpet, "Lamp": lamp, "Spare": extra}
    scene = _scene([obj], materials_by_name=mats)
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(len(applied) == 1 and applied[0]["index"] == 1,
          "only unused Extra at index 1 is removed")
    check(_names(data.materials) == ["Carpet", "Lamp"],
          "apply left used slots")
    restored = us.revert_unused_slots(scene, jrnl, materials=mats)
    check(restored == 1, "revert reinserts one slot")
    check(_names(data.materials) == ["Carpet", "Spare", "Lamp"],
          "revert restores Extra at index 1")
    check(sorted({p.material_index for p in data.polygons}) == [0, 2],
          "face indices restored to Carpet=0 / Lamp=2")
    check(not jrnl.entries, "successful revert consumes SLOT_REMOVE")


def test_hero_and_zero_materials_skipped():
    section("HERO/EXCLUDE skipped; never strip last material on a faced mesh")
    a = _mat("A")
    extra = _mat("Extra")
    data = _mesh_data("hero_mesh", [a, extra], [0])
    obj = _obj("HeroRug", data, override="HERO")
    scene = _scene([obj], materials_by_name={"A": a, "Extra": extra})
    check(us.classify_unused_slots(scene) == [], "HERO object mesh is skipped")

    only = _mat("OnlyUnused")
    data2 = _mesh_data("orphan", [only], [0, 0])
    obj2 = _obj("Orphan", data2)
    scene2 = _scene([obj2], materials_by_name={"OnlyUnused": only})
    # faces use index 0 and slot 0 has the only material → used, not unused.
    check(us.classify_unused_slots(scene2) == [],
          "the only used slot is not pruned")
    # faces use index 0 which is empty; filled slot 1 is unused → would
    # leave zero materials on a faced mesh.
    empty = None
    leftover = _mat("Leftover")
    data3 = _mesh_data("empty0", [empty, leftover], [0, 0])
    obj3 = _obj("Empty0", data3)
    scene3 = _scene([obj3], materials_by_name={"Leftover": leftover})
    check(us.classify_unused_slots(scene3) == [],
          "skip prune that would leave zero materials on a faced mesh")


def test_unique_mesh_processed_once():
    section("shared unique mesh is processed once")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    data = _mesh_data("shared", [carpet, lamp], [0])
    a = _obj("CopyA", data)
    b = _obj("CopyB", data)
    scene = _scene([a, b], materials_by_name={"Carpet": carpet, "Lamp": lamp})
    records = us.classify_unused_slots(scene)
    check(len(records) == 1, "two objects / one mesh → one unused slot")
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(len(applied) == 1 and len(data.materials) == 1,
          "apply pops the shared mesh once")


def test_not_in_default_auto_plan():
    section("UNUSED_SLOTS is not in the default Auto plan")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    data = _mesh_data("rug", [carpet, lamp], [0, 0])
    scene = speed_solver_scene([_obj("Rug", data)])
    scene.materials_by_name = {"Carpet": carpet, "Lamp": lamp}
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "UNUSED_SLOTS" for a in plan.actions),
          "default Auto plan does not include UNUSED_SLOTS")
    inventory = us.classify_unused_slots(scene)
    check(len(inventory) == 1, "inventory still sees the unused slot (Auto is a separate gate)")
    actions = speed_solver.unused_slots_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "UNUSED_SLOTS"
          and actions[0].tier == 2 and actions[0].time_factor == 1.0,
          "planner hook exists, tier 2, no time claim")


def test_inventory_print_shape():
    section("inventory formatter prints no time claim")
    carpet = _mat("Carpet")
    lamp = _mat("Lamp")
    data = _mesh_data("rug", [carpet, lamp], [0])
    text = us.format_inventory(
        us.classify_unused_slots(_scene([_obj("Rug", data)])))
    check("no time claim" in text and "Auto off" in text,
          "inventory header refuses a time claim")
    check("UNIQUE_UNUSED_SLOTS=1" in text and "Lamp" in text,
          "table lists the unused slot")
    check("UNIQUE_UNUSED_SHADERS=1" in text
          and "SKIPPED_DUPLICATE_UNUSED=0" in text
          and "EXTRA_ATTR_SLOTS=0" in text
          and "Auto off" in text,
          "inventory prints unique-shader / skip / extra-attr counts")
    check("    Lamp  1" in text, "UNIQUE_UNUSED_SHADERS list names Lamp")


def test_inventory_print_quiet():
    section("inventory formatter lists shaders and caps mesh rows at 12")
    used = _mat("Plain")
    objects = []
    extras = []
    for i in range(8):
        extra = _mat("Extra%02d" % i)
        extras.append(extra)
        data = _mesh_data("mesh%02d" % i, [used, extra], [0])
        objects.append(_obj("Obj%02d" % i, data))
    many = _mat("Many")
    data = _mesh_data("loud", [used] + [many] * 10, [0])
    objects.append(_obj("Loud", data))
    mats = {"Plain": used, "Many": many}
    for extra in extras:
        mats[extra.name] = extra
    records = us.classify_unused_slots(_scene(objects, materials_by_name=mats))
    check(len(records) == 18, "8 unique extras + 10 Many slots = 18 records")
    text = us.format_inventory(records)
    mesh_rows = [ln for ln in text.splitlines() if ln.startswith("  mesh=")]
    check(len(mesh_rows) == 12, "at most 12 example mesh rows")
    check("... 6 more" in text, "remainder line names the unprinted rows")
    check("    Extra00  1" in text and "    Many  10" in text,
          "UNIQUE_UNUSED_SHADERS list has material name + slot count")
    check(text.count("mesh=") == 12, "does not dump every unused slot")
    check("no time claim" in text and "Auto off" in text,
          "quiet inventory still refuses a time claim")


def test_default_plan_kind_absent_empty():
    section("empty scene default plan has no UNUSED_SLOTS")
    scene = speed_solver_scene([])
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "UNUSED_SLOTS" for a in plan.actions),
          "empty default plan has no UNUSED_SLOTS")


def test_duplicate_unused_of_used_material_skipped():
    section("unused slot of an already-used material is RNA noise")
    carpet = _mat("Carpet")
    data = _mesh_data("rug", [carpet, carpet], [0, 0, 0])
    obj = _obj("Rug", data)
    scene = _scene([obj], materials_by_name={"Carpet": carpet})
    records = us.classify_unused_slots(scene)
    check(len(records) == 0, "duplicate unused slot is not a prune record")
    counts = us.inventory_counts(records)
    check(counts["SKIPPED_DUPLICATE_UNUSED"] >= 1,
          "SKIPPED_DUPLICATE_UNUSED counts the duplicate unused slot")
    check(counts["UNIQUE_UNUSED_SLOTS"] == 0
          and counts["UNIQUE_UNUSED_SHADERS"] == 0,
          "no unique unused shaders kept")
    jrnl = _Journal()
    applied = us.apply_unused_slots(scene, jrnl)
    check(applied == [] and _names(data.materials) == ["Carpet", "Carpet"],
          "apply inherits the gate and does not pop a duplicate slot")


def test_unique_unused_shader_kept():
    section("unused slot of a unique material is a keeper")
    used = _mat("Plain", node_tree=_plain_tree())
    extra = _mat("UniqueUnused", node_tree=_plain_tree())
    data = _mesh_data("body", [used, extra], [0, 0])
    obj = _obj("Body", data)
    scene = _scene([obj], materials_by_name={
        "Plain": used, "UniqueUnused": extra})
    records = us.classify_unused_slots(scene)
    check(len(records) == 1 and records[0]["material"] == "UniqueUnused"
          and records[0]["unique_shader"] is True
          and records[0]["index"] == 1,
          "unique unused material is one prune record")
    counts = us.inventory_counts(records)
    check(counts["UNIQUE_UNUSED_SHADERS"] == 1
          and counts["SKIPPED_DUPLICATE_UNUSED"] == 0,
          "inventory counts the unique unused shader")


def test_unique_unused_extra_attrs_uv_and_tangent():
    section("unique unused TEX_IMAGE / NORMAL_MAP tags extra attrs")
    plain = _mat("Plain", node_tree=_plain_tree())
    mapped = _mat("Mapped", node_tree=_tex_image_tree())
    data = _mesh_data("uv_mesh", [plain, mapped], [0])
    scene = _scene([_obj("UVObj", data)],
                   materials_by_name={"Plain": plain, "Mapped": mapped})
    records = us.classify_unused_slots(scene)
    check(len(records) == 1 and records[0]["unique_shader"] is True,
          "unique unused mapped material is kept")
    check("UV" in (records[0].get("extra_attrs") or []),
          "TEX_IMAGE vs empty Principled tags extra UV")
    counts = us.inventory_counts(records)
    check(counts["EXTRA_ATTR_SLOTS"] >= 1,
          "EXTRA_ATTR_SLOTS counts the mapped unused slot")

    nmap = _mat("BumpCard", node_tree=_normal_map_tree())
    data2 = _mesh_data("t_mesh", [plain, nmap], [0])
    scene2 = _scene([_obj("TObj", data2)],
                    materials_by_name={"Plain": plain, "BumpCard": nmap})
    recs2 = us.classify_unused_slots(scene2)
    check(len(recs2) == 1 and recs2[0]["unique_shader"] is True,
          "unique unused normal-map material is kept")
    check("UV_TANGENT" in (recs2[0].get("extra_attrs") or []),
          "NORMAL_MAP vs empty Principled tags extra UV_TANGENT")


def test_no_cycles_writes_in_module():
    section("UNUSED_SLOTS source never writes scene.cycles")
    path = os.path.join(PROJECT_ROOT, "scenequant", "analysis",
                        "unused_slots.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    check("scene.cycles" not in src,
          "unused_slots.py does not mention scene.cycles")


def main():
    test_unused_extra_slot_pruned()
    test_used_slot_kept_middle_unused()
    test_linked_mesh_skipped()
    test_all_slots_used_noop()
    test_revert_restores()
    test_hero_and_zero_materials_skipped()
    test_unique_mesh_processed_once()
    test_not_in_default_auto_plan()
    test_inventory_print_shape()
    test_inventory_print_quiet()
    test_default_plan_kind_absent_empty()
    test_duplicate_unused_of_used_material_skipped()
    test_unique_unused_shader_kept()
    test_unique_unused_extra_attrs_uv_and_tangent()
    test_no_cycles_writes_in_module()
    finish()


if __name__ == "__main__":
    main()
