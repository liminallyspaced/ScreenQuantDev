# ZERO_SHADER_LIGHT classifier + journaled apply.
# Duck-typed noded lights; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_zero_shader_lights.py

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


zsl = _load("scenequant/analysis/zero_shader_lights.py")
zel = _load("scenequant/analysis/zero_energy_lights.py")
speed_solver = _load("scenequant/planning/speed_solver.py")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


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
        self.mute = kw.pop("mute", False)
        self.is_active_output = kw.pop("is_active_output", True)
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
        self.library = None
        self.animation_data = None


class _Journal:
    def __init__(self):
        self.entries = []

    def set_prop(self, datablock, rna_path, value, tag=None, **kwargs):
        owner = datablock
        parts = rna_path.split(".")
        for part in parts[:-1]:
            owner = getattr(owner, part, None)
            if owner is None:
                return False
        attr = parts[-1]
        if not hasattr(owner, attr):
            return False
        old = getattr(owner, attr)
        setattr(owner, attr, value)
        self.entries.append({
            "t": "set",
            "path": rna_path,
            "old": old,
            "new": value,
            "tag": tag,
            "owner": datablock,
        })
        return True

    def revert(self):
        n = 0
        for entry in reversed(self.entries):
            owner = entry["owner"]
            parts = entry["path"].split(".")
            for part in parts[:-1]:
                owner = getattr(owner, part)
            setattr(owner, parts[-1], entry["old"])
            n += 1
        return n


def _emission(name="Emit", strength=0.0, color=(1.0, 1.0, 1.0)):
    return _Node(name, "EMISSION", inputs=[
        _Sock("Color", color),
        _Sock("Strength", strength),
    ], outputs=[_Sock("Emission")], bl_idname="ShaderNodeEmission")


def _output(name="Light Output"):
    return _Node(name, "OUTPUT_LIGHT", inputs=[
        _Sock("Surface"),
    ], bl_idname="ShaderNodeOutputLight")


def _value(name, value):
    node = _Node(name, "VALUE", outputs=[_Sock("Value", value)],
                 bl_idname="ShaderNodeValue")
    return node


def _mix(name="Mix"):
    return _Node(name, "MIX_SHADER", inputs=[
        _Sock("Fac", 0.5),
        _Sock("Shader"),
        _Sock("Shader.001"),
    ], outputs=[_Sock("Shader")], bl_idname="ShaderNodeMixShader")


def _group(name="Group"):
    return _Node(name, "GROUP", inputs=[], outputs=[_Sock("Shader")],
                 bl_idname="ShaderNodeGroup")


def _tree_emission(strength=0.0, color=(1.0, 1.0, 1.0), connect=True):
    emit = _emission(strength=strength, color=color)
    out = _output()
    tree = _Tree([emit, out])
    if connect:
        tree.links.new(emit.outputs.get("Emission"), out.inputs.get("Surface"))
    return tree


def _tree_value_strength(value=0.0, strength_default=1.0):
    emit = _emission(strength=strength_default)
    val = _value("Zero", value)
    out = _output()
    tree = _Tree([emit, val, out])
    tree.links.new(val.outputs.get("Value"), emit.inputs.get("Strength"))
    tree.links.new(emit.outputs.get("Emission"), out.inputs.get("Surface"))
    return tree


def _tree_mix(fac, strength_a, strength_b):
    a = _emission("A", strength=strength_a)
    b = _emission("B", strength=strength_b)
    mix = _mix()
    mix.inputs.get("Fac").default_value = fac
    out = _output()
    tree = _Tree([a, b, mix, out])
    tree.links.new(a.outputs.get("Emission"), mix.inputs.get("Shader"))
    tree.links.new(b.outputs.get("Emission"), mix.inputs.get("Shader.001"))
    tree.links.new(mix.outputs.get("Shader"), out.inputs.get("Surface"))
    return tree


def _light(name="Lamp", energy=10.0, use_nodes=True, tree=None,
           hide_render=False, is_portal=False, library=None,
           data_library=None, animated=False, data_animated=False,
           tree_animated=False, override="AUTO", light_type="POINT"):
    if tree is None and use_nodes:
        tree = _tree_emission(0.0)
    if tree is not None:
        tree.library = None
        if tree_animated:
            tree.animation_data = Obj(action=Obj(), nla_tracks=[], drivers=[])
    data = Obj(
        energy=energy,
        type=light_type,
        cycles=Obj(is_portal=is_portal),
        library=data_library,
        animation_data=Obj(action=Obj(), nla_tracks=[], drivers=[]) if data_animated else None,
        use_nodes=use_nodes,
        node_tree=tree,
    )
    return Obj(
        name=name,
        type="LIGHT",
        hide_render=hide_render,
        data=data,
        library=library,
        animation_data=Obj(action=Obj(), nla_tracks=[], drivers=[]) if animated else None,
        scenequant=Obj(override=override),
    )


def _mesh(name="Cube"):
    return Obj(
        name=name, type="MESH", hide_render=False, data=Obj(),
        library=None, animation_data=None,
        scenequant=Obj(override="AUTO"),
    )


def _scene(lights=None, engine="CYCLES"):
    return Obj(
        cycles=Obj(device="GPU"),
        render=Obj(engine=engine),
        objects=list(lights or []),
        world=None,
    )


def _speed_scene(lights=None):
    cycles = Obj(
        device="GPU", use_adaptive_sampling=True, adaptive_threshold=0.02,
        samples=256, use_denoising=True, adaptive_min_samples=48,
        max_bounces=8, diffuse_bounces=3, glossy_bounces=4,
        transmission_bounces=6, transparent_max_bounces=8,
        sample_clamp_indirect=10.0, sample_clamp_direct=0.0,
        blur_glossy=1.0, use_light_tree=True,
        caustics_reflective=False, caustics_refractive=False,
        use_guiding=False, use_animated_seed=True, use_camera_cull=False,
        denoising_use_gpu=True,
    )
    render = Obj(
        engine="CYCLES", use_lock_interface=True, use_persistent_data=True,
        use_motion_blur=False, compositor_device="GPU",
    )
    return Obj(
        cycles=cycles, render=render, frame_start=1, frame_end=1,
        camera=Obj(), objects=list(lights or []), world=None, view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"), use_nodes=False, node_tree=None,
    )


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def _mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
               per_image_mb={})


def test_classify_shader_zero_energy_live():
    section("classify: shader Strength 0 + RNA energy > 0 fires")
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Dead", energy=10.0, tree=_tree_emission(0.0))]))
    check(len(recs) == 1 and recs[0]["class"] == "ZERO_SHADER_LIGHT",
          "Strength 0 + energy 10 → one ZERO_SHADER_LIGHT")
    check(recs[0]["object"] == "Dead" and recs[0]["to"] is True,
          "record names the light and hide_render True")
    check(recs[0]["energy"] == 10.0 and recs[0]["prop"] == "hide_render",
          "record keeps RNA energy; write is hide_render")
    check(recs[0]["use_nodes"] is True, "record notes use_nodes")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Live", energy=10.0, tree=_tree_emission(1.0))]))
    check(recs == [], "Strength 1 + energy 10 → no record")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Tiny", energy=10.0, tree=_tree_emission(0.01))]))
    check(recs == [], "Strength 0.01 is not proven zero")


def test_skips_use_nodes_off_and_energy_zero():
    section("use_nodes off ignores a leftover Strength-0 tree; energy 0 is owned elsewhere")
    leftover = _tree_emission(0.0)
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Plain", energy=10.0, use_nodes=False, tree=leftover)]))
    check(recs == [], "use_nodes False → Cycles uses Emission strength 1, skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("RnaZero", energy=0.0, tree=_tree_emission(0.0))]))
    check(recs == [], "RNA energy 0 → ZERO_ENERGY_LIGHT owns it")
    recs = zel.classify_zero_energy_lights(_scene([
        _light("RnaZero", energy=0.0, tree=_tree_emission(0.0))]))
    check(len(recs) == 1, "ZERO_ENERGY_LIGHT still fires on energy 0")


def test_value_node_and_black_color_and_disconnected():
    section("Value 0 one hop / unlinked black Color / disconnected Surface")
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("ViaValue", energy=4.0, tree=_tree_value_strength(0.0))]))
    check(len(recs) == 1, "Strength linked to Value 0 → proven zero")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("ViaValueLive", energy=4.0, tree=_tree_value_strength(1.0))]))
    check(recs == [], "Strength linked to Value 1 → live")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Black", energy=8.0,
               tree=_tree_emission(strength=1.0, color=(0.0, 0.0, 0.0)))]))
    check(len(recs) == 1, "unlinked black Color * Strength 1 → estimate 0")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Open", energy=3.0, tree=_tree_emission(1.0, connect=False))]))
    check(len(recs) == 1, "unconnected Light Output Surface → zero_float3")


def test_mix_and_group():
    section("Mix Fac 0/1 dead side; GROUP on the path is unproven")
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("MixDead", energy=5.0, tree=_tree_mix(1.0, 1.0, 0.0))]))
    check(len(recs) == 1, "Fac 1 + live side Strength 0 → proven zero")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("MixLive", energy=5.0, tree=_tree_mix(1.0, 0.0, 1.0))]))
    check(recs == [], "Fac 1 + live side Strength 1 → keep")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("MixBoth", energy=5.0, tree=_tree_mix(0.5, 0.0, 0.0))]))
    check(len(recs) == 1, "Fac 0.5 + both Strength 0 → proven zero")

    grp = _group()
    out = _output()
    tree = _Tree([grp, out])
    # GROUP is the Surface source (unexpanded).
    tree.links.new(grp.outputs.get("Shader"), out.inputs.get("Surface"))
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Grouped", energy=5.0, tree=tree)]))
    check(recs == [], "GROUP on the Surface path → unproven, skip")


def test_skips_portal_linked_animated_hero_mesh_eevee():
    section("classify skips portal / linked / animated / HERO / mesh / EEVEE")
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Portal", energy=10.0, is_portal=True)]))
    check(recs == [], "is_portal → skip (world MIS rectangle)")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Linked", energy=10.0, library=Obj())]))
    check(recs == [], "linked object → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("LinkedData", energy=10.0, data_library=Obj())]))
    check(recs == [], "linked light datablock → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Keyed", energy=10.0, animated=True)]))
    check(recs == [], "object animation_data → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("KeyedData", energy=10.0, data_animated=True)]))
    check(recs == [], "light datablock animation_data → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("KeyedTree", energy=10.0, tree_animated=True)]))
    check(recs == [], "node tree animation_data → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Hero", energy=10.0, override="HERO")]))
    check(recs == [], "HERO override → skip")

    recs = zsl.classify_zero_shader_lights(_scene([
        _light("Keep", energy=10.0, override="KEEP")]))
    check(recs == [], "KEEP override → skip")

    recs = zsl.classify_zero_shader_lights(_scene([_mesh()]))
    check(recs == [], "mesh is not a light → no record")

    recs = zsl.classify_zero_shader_lights(_scene(
        [_light("Dead", energy=10.0)], engine="BLENDER_EEVEE"))
    check(recs == [], "EEVEE engine → no record")

    already = _light("Hidden", energy=10.0, hide_render=True)
    recs = zsl.classify_zero_shader_lights(_scene([already]))
    check(recs == [], "already hide_render → no record")


def test_never_writes_energy_or_nodes():
    section("apply never writes Light.energy and never unlinks")
    lamp = _light("Dead", energy=12.0, tree=_tree_emission(0.0))
    scene = _scene([lamp])
    jrnl = _Journal()
    applied = zsl.apply_zero_shader_lights(scene, jrnl)
    check(len(applied) == 1, "apply hides the shader-zero light")
    check(lamp.hide_render is True, "hide_render became True")
    check(lamp.data.energy == 12.0, "energy stayed 12")
    check(lamp.data.use_nodes is True, "use_nodes stayed True")
    check(all(e["path"] == "hide_render" for e in jrnl.entries),
          "journal only recorded hide_render")
    check(all(e["owner"] is lamp for e in jrnl.entries),
          "journal owner is the light object")
    counts = zsl.inventory_counts(applied)
    check(counts["ENERGY_WRITES"] == 0 and counts["NODE_UNLINKS"] == 0,
          "inventory never counts energy writes or unlinks")


def test_apply_revert_identity():
    section("apply → revert restores hide_render")
    lamp = _light("Dead", energy=9.0, tree=_tree_emission(0.0))
    live = _light("Live", energy=9.0, tree=_tree_emission(1.0))
    scene = _scene([lamp, live])
    before_dead = lamp.hide_render
    before_live = live.hide_render
    before_energy = lamp.data.energy
    jrnl = _Journal()
    zsl.apply_zero_shader_lights(scene, jrnl)
    check(lamp.hide_render is True, "applied hide_render")
    check(live.hide_render is False, "live light untouched")
    n = jrnl.revert()
    check(n == 1, "one journal entry reverted")
    check(lamp.hide_render is before_dead, "revert restored hide_render False")
    check(live.hide_render is before_live, "live light still visible")
    check(lamp.data.energy == before_energy, "energy still 9")


def test_apply_reproves():
    section("apply re-proves shader zero and not portal")
    live = _light("Live", energy=10.0, tree=_tree_emission(1.0))
    jrnl = _Journal()
    applied = zsl.apply_zero_shader_lights(_scene([live]), jrnl)
    check(applied == [], "Strength 1 → apply no-op")
    check(live.hide_render is False, "live hide_render unchanged")
    check(jrnl.entries == [], "no journal write when shader is live")

    portal = _light("Portal", energy=10.0, is_portal=True)
    applied = zsl.apply_zero_shader_lights(_scene([portal]), _Journal())
    check(applied == [], "portal → apply no-op")
    check(portal.hide_render is False, "portal not hidden")


def test_planner_hook_auto_off():
    section("planner hook exists; Auto plan does not call it")
    dead = _light("Dead", energy=10.0, tree=_tree_emission(0.0))
    scene = _speed_scene([dead])
    actions = speed_solver.zero_shader_light_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "ZERO_SHADER_LIGHT",
          "hook fires on shader Strength 0")
    check(actions[0].tier == 2, "tier 2 (Auto-off)")
    check(abs(actions[0].time_factor - 1.0) < 1e-9,
          "time_factor 1.0 (no claim)")
    check(len(actions[0].payload.get("records") or []) == 1,
          "payload carries the classify record")

    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check("ZERO_SHADER_LIGHT" not in kinds,
          "ZERO_SHADER_LIGHT is not in the default Auto plan")
    check("ZERO_ENERGY_LIGHT" not in kinds,
          "ZERO_ENERGY_LIGHT still Auto-off")
    check(all(a.tier <= 1 for a in plan.actions),
          "default plan still tier 0+1 only")

    scene2 = _speed_scene([_light("Live", energy=8.0, tree=_tree_emission(1.0))])
    check(speed_solver.zero_shader_light_actions(scene2) == [],
          "hook silent when shader emission is live")


def test_scene_agnostic_not_name_gated():
    section("classifier is DNA, never a scene/object name")
    recs = zsl.classify_zero_shader_lights(_scene([
        _light("chair.001", energy=4.0, tree=_tree_emission(0.0)),
        _light("ClassroomLamp", energy=4.0, tree=_tree_emission(1.0)),
        _light("exterior_sun", energy=4.0, tree=_tree_emission(0.0)),
    ]))
    names = sorted(r["object"] for r in recs)
    check(names == ["chair.001", "exterior_sun"],
          "two shader-zero lights fire regardless of name; live ClassroomLamp skipped")


def test_inventory_never_counts_energy_writes():
    section("inventory counts")
    counts = zsl.inventory_counts(
        zsl.classify_zero_shader_lights(_scene([
            _light("Dead", energy=2.0, tree=_tree_emission(0.0))])))
    check(counts["ZERO_SHADER_LIGHT"] == 1, "inventory counts the hide")
    check(counts["ENERGY_WRITES"] == 0, "inventory never counts energy writes")
    check(counts["NODE_UNLINKS"] == 0, "inventory never counts unlinks")


def main():
    test_classify_shader_zero_energy_live()
    test_skips_use_nodes_off_and_energy_zero()
    test_value_node_and_black_color_and_disconnected()
    test_mix_and_group()
    test_skips_portal_linked_animated_hero_mesh_eevee()
    test_never_writes_energy_or_nodes()
    test_apply_revert_identity()
    test_apply_reproves()
    test_planner_hook_auto_off()
    test_scene_agnostic_not_name_gated()
    test_inventory_never_counts_energy_writes()
    finish()


if __name__ == "__main__":
    main()
