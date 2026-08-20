# L3b UNUSED_COLOR_ATTRS inventory classifier.
# Duck-typed meshes; no .blend, no bpy.ops, no GPU.
# Apply is not wired (pixel values cannot be restored without a blob).
#   python3 tests/test_unused_color_attrs.py

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


uca = _load("scenequant/analysis/unused_color_attrs.py")
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


class _Node:
    def __init__(self, name, ntype, inputs=None, outputs=None, **kw):
        self.name = name
        self.type = ntype
        self.bl_idname = kw.pop("bl_idname", "")
        self.attribute_name = kw.pop("attribute_name", "")
        self.layer_name = kw.pop("layer_name", "")
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


def _attr_tree(attr_name, ntype="ATTRIBUTE", bl_idname="ShaderNodeAttribute",
               name_key="attribute_name"):
    kw = {name_key: attr_name, "bl_idname": bl_idname}
    node = _Node(
        "Attribute", ntype,
        outputs=[_Sock("Color"), _Sock("Vector"), _Sock("Fac")],
        **kw,
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
    return _Tree([node, prin, out])


def _mat(name, node_tree=None):
    kw = dict(name=name, library=None, override_library=None)
    if node_tree is not None:
        kw["node_tree"] = node_tree
        kw["use_nodes"] = True
    return Obj(**kw)


def _attr(name, domain="POINT", data_type="FLOAT_COLOR"):
    return Obj(name=name, domain=domain, data_type=data_type)


def _mesh_data(name, materials, face_indices, color_attrs=None,
               uv_layers=None, library=None):
    data = Obj(
        name=name, library=library, override_library=None,
        polygons=[_Poly(i) for i in face_indices],
        materials=None,
        color_attributes=list(color_attrs or []),
        uv_layers=list(uv_layers or []),
        vertex_colors=[],
    )
    data.materials = _MatCol(materials)
    return data


def _obj(name, data, library=None, override="AUTO", hide_render=False,
         modifiers=None):
    return Obj(
        name=name, type="MESH", hide_render=hide_render, data=data,
        library=library, override_library=None,
        scenequant=Obj(override=override),
        material_slots=_SlotView(data.materials),
        modifiers=list(modifiers or []),
    )


def _scene(objects, **kw):
    data = dict(
        objects=objects, world=None, view_layers=[],
        use_nodes=False, node_tree=None, compositing_node_group=None,
        cycles=Obj(samples=256),
    )
    data.update(kw)
    return Obj(**data)


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


def test_unused_color_attr_recorded():
    section("unused color attr on unique local mesh → record")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "body", [paint], [0, 0],
        color_attrs=[_attr("Col", domain="POINT", data_type="FLOAT_COLOR")],
        uv_layers=[Obj(name="UVMap")],
    )
    scene = _scene([_obj("Body", data)])
    records = uca.classify_unused_color_attrs(scene)
    check(len(records) == 1, "one unused color attr record")
    rec = records[0]
    check(rec["mesh"] == "body" and rec["object"] == "Body"
          and rec["attr_name"] == "Col"
          and rec["domain"] == "POINT"
          and rec["data_type"] == "FLOAT_COLOR"
          and "Body" in rec["users"],
          "record fields are mesh/object/attr_name/domain/data_type/users")


def test_named_in_attribute_node_kept():
    section("attr named in an Attribute node on a used material → no record")
    used = _mat("Paint", node_tree=_attr_tree("Col"))
    data = _mesh_data(
        "body", [used], [0],
        color_attrs=[_attr("Col")],
    )
    scene = _scene([_obj("Body", data)])
    records = uca.classify_unused_color_attrs(scene)
    check(records == [], "used Attribute node name match is not unused")

    vcol = _mat("PaintV", node_tree=_attr_tree(
        "Col", ntype="VERTEX_COLOR",
        bl_idname="ShaderNodeVertexColor", name_key="layer_name"))
    data2 = _mesh_data(
        "body2", [vcol], [0],
        color_attrs=[_attr("Col")],
    )
    scene2 = _scene([_obj("Body2", data2)])
    check(uca.classify_unused_color_attrs(scene2) == [],
          "used Color Attribute / VERTEX_COLOR name match is not unused")


def test_linked_mesh_skipped():
    section("linked mesh skipped")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "lib_body", [paint], [0],
        color_attrs=[_attr("Col")],
        library=Obj(),
    )
    scene = _scene([_obj("Linked", data)])
    check(uca.classify_unused_color_attrs(scene) == [],
          "mesh.library → no unused color attr records")

    data2 = _mesh_data(
        "obj_linked", [paint], [0],
        color_attrs=[_attr("Col")],
    )
    obj2 = _obj("ObjLinked", data2, library=Obj())
    check(uca.classify_unused_color_attrs(_scene([obj2])) == [],
          "obj.library → no unused color attr records")


def test_mesh_with_modifier_skipped():
    section("mesh with a modifier skipped")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "deformed", [paint], [0],
        color_attrs=[_attr("Col")],
    )
    obj = _obj("Deformed", data, modifiers=[Obj(type="NODES", name="GN")])
    scene = _scene([obj])
    check(uca.classify_unused_color_attrs(scene) == [],
          "Geometry Nodes / any modifier → skip the mesh")


def test_uvmap_never_candidate():
    section("UV map named UVMap is never a candidate")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "uv_mesh", [paint], [0],
        color_attrs=[_attr("UVMap", domain="CORNER", data_type="FLOAT_COLOR")],
        uv_layers=[Obj(name="UVMap")],
    )
    scene = _scene([_obj("UVObj", data)])
    records = uca.classify_unused_color_attrs(scene)
    check(all(r.get("attr_name") != "UVMap" for r in records),
          "UVMap is never a color-attr prune candidate")
    check(records == [], "UVMap-only mesh emits no unused color attr records")


def test_not_in_default_auto_plan():
    section("Auto plan does not include UNUSED_COLOR_ATTRS")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "body", [paint], [0],
        color_attrs=[_attr("Col")],
    )
    scene = speed_solver_scene([_obj("Body", data)])
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "UNUSED_COLOR_ATTRS" for a in plan.actions),
          "default Auto plan does not include UNUSED_COLOR_ATTRS")
    inventory = uca.classify_unused_color_attrs(scene)
    check(len(inventory) == 1, "inventory still sees the unused color attr")
    actions = speed_solver.unused_color_attrs_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "UNUSED_COLOR_ATTRS"
          and actions[0].tier == 2 and actions[0].time_factor == 1.0,
          "planner hook exists, tier 2, no time claim")


def test_builtins_and_hero_skipped():
    section("position/normal built-ins and HERO skipped")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "body", [paint], [0],
        color_attrs=[
            _attr("position", data_type="FLOAT_VECTOR"),
            _attr("normal", data_type="FLOAT_VECTOR"),
        ],
    )
    scene = _scene([_obj("Body", data)])
    check(uca.classify_unused_color_attrs(scene) == [],
          "position/normal built-ins are never candidates")

    data2 = _mesh_data(
        "hero_mesh", [paint], [0],
        color_attrs=[_attr("Col")],
    )
    obj = _obj("HeroBody", data2, override="HERO")
    check(uca.classify_unused_color_attrs(_scene([obj])) == [],
          "HERO object mesh is skipped")


def test_inventory_print_shape():
    section("inventory formatter prints no time claim")
    paint = _mat("Paint", node_tree=_plain_tree())
    data = _mesh_data(
        "body", [paint], [0],
        color_attrs=[_attr("Col")],
    )
    text = uca.format_inventory(
        uca.classify_unused_color_attrs(_scene([_obj("Body", data)])))
    check("no time claim" in text and "Auto off" in text
          and "inventory only" in text,
          "inventory header refuses a time claim and marks inventory-only")
    check("UNUSED_COLOR_ATTRS=1" in text and "Col" in text,
          "table lists the unused color attr")


def test_no_cycles_writes_in_module():
    section("UNUSED_COLOR_ATTRS source never writes scene.cycles")
    path = os.path.join(PROJECT_ROOT, "scenequant", "analysis",
                        "unused_color_attrs.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    check("scene.cycles" not in src,
          "unused_color_attrs.py does not mention scene.cycles")


def main():
    test_unused_color_attr_recorded()
    test_named_in_attribute_node_kept()
    test_linked_mesh_skipped()
    test_mesh_with_modifier_skipped()
    test_uvmap_never_candidate()
    test_not_in_default_auto_plan()
    test_builtins_and_hero_skipped()
    test_inventory_print_shape()
    test_no_cycles_writes_in_module()
    finish()


if __name__ == "__main__":
    main()
