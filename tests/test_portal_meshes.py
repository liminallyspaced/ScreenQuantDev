# L5 PORTAL_MESH inventory classifier.
# Duck-typed meshes; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_portal_meshes.py

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


pm = _load("scenequant/analysis/portal_meshes.py")
speed_solver = _load("scenequant/planning/speed_solver.py")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Poly:
    def __init__(self, material_index):
        self.material_index = material_index


class _MatCol:
    def __init__(self, items):
        self._items = list(items)

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index):
        return self._items[index]


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


class _Link:
    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


class _Links:
    def __init__(self):
        self._items = []

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def new(self, from_sock, to_sock):
        link = _Link(from_sock.node, from_sock, to_sock.node, to_sock)
        self._items.append(link)
        to_sock.links.append(link)
        to_sock.is_linked = True
        from_sock.links.append(link)
        from_sock.is_linked = True
        return link


class _Node:
    def __init__(self, name, ntype, inputs=None, outputs=None, **kw):
        self.name = name
        self.type = ntype
        self.bl_idname = kw.pop("bl_idname", "")
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
        self.links = _Links()


def _mix_node():
    return _Node(
        "Mix Shader", "MIX_SHADER",
        inputs=[
            _Sock("Fac", 0.5),
            _Sock("Shader", identifier="Shader"),
            _Sock("Shader_001", identifier="Shader_001"),
        ],
        outputs=[_Sock("Shader")],
        bl_idname="ShaderNodeMixShader",
    )


def _geom_node():
    return _Node(
        "Geometry", "NEW_GEOMETRY",
        outputs=[
            _Sock("Position"),
            _Sock("Normal"),
            _Sock("Incoming"),
            _Sock("Backfacing"),
        ],
        bl_idname="ShaderNodeNewGeometry",
    )


def _emit_node():
    return _Node(
        "Emission", "EMISSION",
        inputs=[_Sock("Color"), _Sock("Strength", 1.0)],
        outputs=[_Sock("Emission")],
        bl_idname="ShaderNodeEmission",
    )


def _trans_node():
    return _Node(
        "Transparent BSDF", "BSDF_TRANSPARENT",
        inputs=[_Sock("Color")],
        outputs=[_Sock("BSDF")],
        bl_idname="ShaderNodeBsdfTransparent",
    )


def _output_node():
    return _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume"), _Sock("Displacement")],
        bl_idname="ShaderNodeOutputMaterial",
    )


def _principled_node(transmission=0.0):
    return _Node(
        "Principled BSDF", "BSDF_PRINCIPLED",
        inputs=[
            _Sock("Base Color"),
            _Sock("Alpha", 1.0),
            _Sock("Transmission Weight", transmission),
            _Sock("Transmission", transmission),
        ],
        outputs=[_Sock("BSDF")],
    )


def _portal_tree(fac="backfacing", extra_nodes=None, extra_links=None):
    """Mix(Transparent, Emission) feeding Surface. fac: backfacing/incoming/unlinked."""
    mix = _mix_node()
    geom = _geom_node()
    emit = _emit_node()
    trans = _trans_node()
    out = _output_node()
    nodes = [mix, geom, emit, trans, out]
    extra_nodes = list(extra_nodes or [])
    nodes.extend(extra_nodes)
    tree = _Tree(nodes)
    tree.links.new(trans.outputs.get("BSDF"), mix.inputs.get("Shader"))
    tree.links.new(emit.outputs.get("Emission"), mix.inputs.get("Shader_001"))
    tree.links.new(mix.outputs.get("Shader"), out.inputs.get("Surface"))
    if fac == "backfacing":
        tree.links.new(geom.outputs.get("Backfacing"), mix.inputs.get("Fac"))
    elif fac == "incoming":
        tree.links.new(geom.outputs.get("Incoming"), mix.inputs.get("Fac"))
    # unlinked: Fac stays default 0.5
    for src, src_sock, dst, dst_sock in extra_links or ():
        tree.links.new(src.outputs.get(src_sock), dst.inputs.get(dst_sock))
    return tree


def _two_principled_tree():
    mix = _mix_node()
    geom = _geom_node()
    a = _principled_node()
    b = _principled_node()
    out = _output_node()
    tree = _Tree([mix, geom, a, b, out])
    tree.links.new(a.outputs.get("BSDF"), mix.inputs.get("Shader"))
    tree.links.new(b.outputs.get("BSDF"), mix.inputs.get("Shader_001"))
    tree.links.new(geom.outputs.get("Backfacing"), mix.inputs.get("Fac"))
    tree.links.new(mix.outputs.get("Shader"), out.inputs.get("Surface"))
    return tree


def _trans_principled_tree():
    """Mix(Transparent, Principled) Fac=Backfacing — no Emission."""
    mix = _mix_node()
    geom = _geom_node()
    trans = _trans_node()
    prin = _principled_node()
    out = _output_node()
    tree = _Tree([mix, geom, trans, prin, out])
    tree.links.new(trans.outputs.get("BSDF"), mix.inputs.get("Shader"))
    tree.links.new(prin.outputs.get("BSDF"), mix.inputs.get("Shader_001"))
    tree.links.new(geom.outputs.get("Backfacing"), mix.inputs.get("Fac"))
    tree.links.new(mix.outputs.get("Shader"), out.inputs.get("Surface"))
    return tree


def _mat(name, node_tree, library=None):
    return Obj(
        name=name, library=library, override_library=None,
        node_tree=node_tree, use_nodes=True, blend_method="HASHED",
        use_transparent_shadow=True,
    )


def _mesh_data(name, materials, face_indices, library=None):
    data = Obj(
        name=name, library=library, override_library=None,
        polygons=[_Poly(i) for i in face_indices],
        materials=None,
    )
    data.materials = _MatCol(materials)
    return data


def _obj(name, data, library=None, override="AUTO", hide_render=False,
         otype="MESH"):
    return Obj(
        name=name, type=otype, hide_render=hide_render, data=data,
        library=library, override_library=None,
        scenequant=Obj(override=override),
        material_slots=_SlotView(data.materials),
        cycles=Obj(is_portal=False),
    )


def _scene(objects, **kw):
    data = dict(
        objects=objects, world=None, view_layers=[],
        use_nodes=False, node_tree=None, compositing_node_group=None,
        cycles=Obj(samples=256),
    )
    data.update(kw)
    return Obj(**data)


def _portal_scene(obj_name="Window", mesh_name="pane", mat_name="portal_card",
                  fac="backfacing", extra_nodes=None, library=None,
                  mesh_library=None, override="AUTO"):
    mat = _mat(mat_name, _portal_tree(fac=fac, extra_nodes=extra_nodes),
               library=library)
    data = _mesh_data(mesh_name, [mat], [0], library=mesh_library)
    return _scene([_obj(obj_name, data, override=override)])


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


def test_backfacing_mix_is_portal():
    section("Mix Transparent+Emission, Fac=Backfacing → 1 record")
    scene = _portal_scene()
    records = pm.classify_portal_meshes(scene)
    check(len(records) == 1, "one PORTAL_MESH record")
    rec = records[0]
    check(rec["object"] == "Window" and rec["mesh"] == "pane"
          and rec["material"] == "portal_card"
          and "Backfacing" in rec["reason"],
          "record fields are object/mesh/material/reason")
    check(rec["role"] == pm.ROLE_MESH_EMIT_BACKFACE,
          "Mix+Emission+Backfacing role is MESH_EMIT_BACKFACE")


def test_unlinked_fac_is_not_portal():
    section("same mix, Fac unlinked 0.5 → 0")
    scene = _portal_scene(fac="unlinked")
    check(pm.classify_portal_meshes(scene) == [],
          "unlinked Fac 0.5 is not a portal mesh")


def test_incoming_fac_is_not_portal():
    section("same mix, Fac=Incoming → 0")
    scene = _portal_scene(fac="incoming")
    check(pm.classify_portal_meshes(scene) == [],
          "Geometry Incoming on Fac is a different trick, not PORTAL_MESH")


def test_two_principled_is_not_portal():
    section("Mix two Principled, Fac=Backfacing → 0")
    mat = _mat("Paint", _two_principled_tree())
    data = _mesh_data("body", [mat], [0])
    scene = _scene([_obj("Body", data)])
    check(pm.classify_portal_meshes(scene) == [],
          "Mix of two Principled is not a portal mesh")


def test_backfacing_transparent_without_emission_is_not_emit():
    section("Mix Transparent+Principled, Fac=Backfacing is NOT MESH_EMIT_BACKFACE")
    mat = _mat("Card", _trans_principled_tree())
    data = _mesh_data("card", [mat], [0])
    scene = _scene([_obj("Card", data)])
    records = pm.classify_portal_meshes(scene)
    check(len(records) == 1, "Transparent+Backfacing without Emission inventories")
    check(records[0]["role"] == pm.ROLE_WORLD_PORTAL_CARD,
          "role is WORLD_PORTAL_CARD")
    check(records[0]["role"] != pm.ROLE_MESH_EMIT_BACKFACE,
          "without proven Emission is NOT MESH_EMIT_BACKFACE")


def test_glass_in_tree_skipped():
    section("Glass in the tree → 0")
    glass = _Node(
        "Glass BSDF", "BSDF_GLASS",
        inputs=[_Sock("Color")],
        outputs=[_Sock("BSDF")],
        bl_idname="ShaderNodeBsdfGlass",
    )
    scene = _portal_scene(extra_nodes=[glass])
    check(pm.classify_portal_meshes(scene) == [],
          "BSDF_GLASS anywhere in the material skips PORTAL_MESH")


def test_hero_skipped():
    section("HERO object → 0")
    scene = _portal_scene(override="HERO")
    check(pm.classify_portal_meshes(scene) == [],
          "HERO object is skipped")


def test_linked_mesh_skipped():
    section("linked mesh → 0")
    scene = _portal_scene(mesh_library=Obj())
    check(pm.classify_portal_meshes(scene) == [],
          "mesh.library → no PORTAL_MESH records")


def test_name_is_not_how_we_detect():
    section("name is NOT how we detect")
    scene = _portal_scene(obj_name="Lamp", mesh_name="Lamp", mat_name="Lamp")
    records = pm.classify_portal_meshes(scene)
    check(len(records) == 1,
          "a mesh named Lamp with the Mix+Backfacing pattern still matches")

    prin = _principled_node()
    out = _output_node()
    tree = _Tree([prin, out])
    tree.links.new(prin.outputs.get("BSDF"), out.inputs.get("Surface"))
    mat = _mat("dayLight_portal", tree)
    data = _mesh_data("dayLight_portal", [mat], [0])
    scene2 = _scene([_obj("dayLight_portal", data)])
    check(pm.classify_portal_meshes(scene2) == [],
          "a mesh named dayLight_portal without the pattern does not match")


def test_not_in_default_auto_plan():
    section("default Auto plan has no PORTAL_MESH")
    scene = speed_solver_scene(_portal_scene().objects)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "PORTAL_MESH" for a in plan.actions),
          "default Auto plan does not include PORTAL_MESH")
    inventory = pm.classify_portal_meshes(scene)
    check(len(inventory) == 1, "inventory still sees the portal mesh")
    check(inventory[0]["role"] == pm.ROLE_MESH_EMIT_BACKFACE,
          "Auto-off inventory still classifies Classroom-shaped card as MESH_EMIT_BACKFACE")
    actions = speed_solver.portal_mesh_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "PORTAL_MESH"
          and actions[0].tier == 2 and actions[0].time_factor == 1.0,
          "planner hook exists, tier 2, no time claim")


def test_inventory_print_shape():
    section("inventory formatter refuses a time claim")
    text = pm.format_inventory(
        pm.classify_portal_meshes(_portal_scene()))
    check("no time claim" in text and "Auto off" in text
          and "no convert" in text,
          "inventory header refuses a time claim and marks no convert")
    check("PORTAL_MESH=1" in text and "portal_card" in text,
          "table lists the portal mesh")
    check("MESH_EMIT_BACKFACE=1" in text and "WORLD_PORTAL_CARD=0" in text
          and "role=MESH_EMIT_BACKFACE" in text,
          "inventory prints role counts and MESH_EMIT_BACKFACE on the record")


def test_no_name_special_case_or_cycles_write():
    section("classifier does not special-case names or write scene.cycles")
    path = os.path.join(PROJECT_ROOT, "scenequant", "analysis",
                        "portal_meshes.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    check("scene.cycles" not in src,
          "portal_meshes.py does not mention scene.cycles")
    check('if name == "dayLight_portal"' not in src
          and "if name == 'dayLight_portal'" not in src,
          "no if name == dayLight_portal special case")


def main():
    test_backfacing_mix_is_portal()
    test_unlinked_fac_is_not_portal()
    test_incoming_fac_is_not_portal()
    test_two_principled_is_not_portal()
    test_backfacing_transparent_without_emission_is_not_emit()
    test_glass_in_tree_skipped()
    test_hero_skipped()
    test_linked_mesh_skipped()
    test_name_is_not_how_we_detect()
    test_not_in_default_auto_plan()
    test_inventory_print_shape()
    test_no_name_special_case_or_cycles_write()
    finish()


if __name__ == "__main__":
    main()
