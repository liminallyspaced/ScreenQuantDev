# ZERO_WORLD_BG classifier + journaled apply.
# Duck-typed noded worlds; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_zero_world_bg.py

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


zwb = _load("scenequant/analysis/zero_world_bg.py")
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


def _bg(name="Background", strength=0.0, color=(0.8, 0.8, 0.8)):
    return _Node(name, "BACKGROUND", inputs=[
        _Sock("Color", color),
        _Sock("Strength", strength),
    ], outputs=[_Sock("Background")], bl_idname="ShaderNodeBackground")


def _output(name="World Output"):
    return _Node(name, "OUTPUT_WORLD", inputs=[
        _Sock("Surface"),
        _Sock("Volume"),
    ], bl_idname="ShaderNodeOutputWorld")


def _env(name="Env"):
    return _Node(name, "TEX_ENVIRONMENT", inputs=[
        _Sock("Vector"),
    ], outputs=[_Sock("Color", (1.0, 1.0, 1.0))],
        bl_idname="ShaderNodeTexEnvironment")


def _value(name, value):
    return _Node(name, "VALUE", outputs=[_Sock("Value", value)],
                 bl_idname="ShaderNodeValue")


def _group(name="Group"):
    return _Node(name, "GROUP", inputs=[], outputs=[_Sock("Shader"), _Sock("Color")],
                 bl_idname="ShaderNodeGroup")


def _mix_rgb(name="Mix"):
    return _Node(name, "MIX_RGB", inputs=[
        _Sock("Fac", 0.5),
        _Sock("Color1", (0.0, 0.0, 0.0)),
        _Sock("Color2", (1.0, 1.0, 1.0)),
    ], outputs=[_Sock("Color")], bl_idname="ShaderNodeMixRGB")


def _tree_env_strength(strength=0.0, connect_env=True, connect_surface=True):
    bg = _bg(strength=strength)
    out = _output()
    env = _env()
    tree = _Tree([bg, out, env])
    if connect_env:
        tree.links.new(env.outputs.get("Color"), bg.inputs.get("Color"))
    if connect_surface:
        tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    return tree


def _tree_value_strength(value=0.0, connect_env=True):
    bg = _bg(strength=1.0)
    val = _value("Zero", value)
    out = _output()
    env = _env()
    tree = _Tree([bg, val, out, env])
    tree.links.new(val.outputs.get("Value"), bg.inputs.get("Strength"))
    tree.links.new(env.outputs.get("Color"), bg.inputs.get("Color"))
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    return tree


def _tree_solid(strength=0.0):
    bg = _bg(strength=strength)
    out = _output()
    tree = _Tree([bg, out])
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    return tree


def _tree_mix_rgb_env(strength=0.0):
    bg = _bg(strength=strength)
    mix = _mix_rgb()
    mix.inputs.get("Fac").default_value = 1.0
    env = _env()
    out = _output()
    tree = _Tree([bg, mix, env, out])
    tree.links.new(env.outputs.get("Color"), mix.inputs.get("Color2"))
    tree.links.new(mix.outputs.get("Color"), bg.inputs.get("Color"))
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    return tree


def _world(tree, sampling="AUTOMATIC", use_nodes=True, library=None,
           animated=False, tree_animated=False, override="AUTO"):
    if tree is not None:
        tree.library = None
        if tree_animated:
            tree.animation_data = Obj(action=Obj(), nla_tracks=[], drivers=[])
    return Obj(
        use_nodes=use_nodes,
        node_tree=tree,
        library=library,
        animation_data=Obj(action=Obj(), nla_tracks=[], drivers=[]) if animated else None,
        cycles=Obj(sampling_method=sampling),
        scenequant=Obj(override=override),
        color=(0.05, 0.05, 0.05),
    )


def _portal(name="Portal"):
    return Obj(
        name=name, type="LIGHT", hide_render=False,
        data=Obj(energy=1.0, type="AREA", cycles=Obj(is_portal=True),
                 library=None, animation_data=None, use_nodes=False,
                 node_tree=None),
        library=None, animation_data=None,
        scenequant=Obj(override="AUTO"),
    )


def _scene(world=None, objects=None, engine="CYCLES"):
    return Obj(
        cycles=Obj(device="GPU"),
        render=Obj(engine=engine),
        objects=list(objects or []),
        world=world,
    )


def _speed_scene(world=None, objects=None):
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
        camera=Obj(), objects=list(objects or []), world=world,
        view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"), use_nodes=False, node_tree=None,
    )


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def _mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
               per_image_mb={})


def test_gap_strength_zero_env_connected():
    section("classify: Strength 0 + connected Env Tex is the WORLD_MIS_NONE gap")
    recs = zwb.classify_zero_world_bg(_scene(_world(_tree_env_strength(0.0))))
    check(len(recs) == 1 and recs[0]["class"] == "ZERO_WORLD_BG",
          "Strength 0 + Env Tex → one ZERO_WORLD_BG")
    check(recs[0]["to"] == "NONE" and recs[0]["prop"] == "sampling_method",
          "write is sampling_method NONE")
    check(recs[0]["from"] == "AUTOMATIC" and recs[0]["spatial"] is True,
          "record keeps previous sampling; spatial proven")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(1.0))))
    check(recs == [], "Strength 1 + Env Tex → live world, no record")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.01))))
    check(recs == [], "Strength 0.01 is not proven zero")


def test_world_mis_none_owns_solid():
    section("solid Strength 0 is WORLD_MIS_NONE, not this lever")
    recs = zwb.classify_zero_world_bg(_scene(_world(_tree_solid(0.0))))
    check(recs == [], "solid Background Strength 0 → no ZERO_WORLD_BG")

    recs = zwb.classify_zero_world_bg(_scene(_world(
        _tree_env_strength(0.0, connect_env=False))))
    check(recs == [], "Env Tex in tree but not on Color → Cycles simplify drops it")

    recs = zwb.classify_zero_world_bg(_scene(_world(
        None, use_nodes=False)))
    check(recs == [], "use_nodes False → WORLD_MIS_NONE owns solid")


def test_value_node_and_mix_rgb():
    section("Value 0 one hop / Mix RGB wrapping Env Tex")
    recs = zwb.classify_zero_world_bg(_scene(_world(_tree_value_strength(0.0))))
    check(len(recs) == 1, "Strength linked to Value 0 + Env Tex → proven zero")

    recs = zwb.classify_zero_world_bg(_scene(_world(_tree_value_strength(1.0))))
    check(recs == [], "Strength linked to Value 1 → live")

    recs = zwb.classify_zero_world_bg(_scene(_world(_tree_mix_rgb_env(0.0))))
    check(len(recs) == 1, "Mix RGB Fac 1 wrapping Env Tex + Strength 0 → fire")


def test_skips_none_linked_portal_volume_group_hero_eevee():
    section("classify skips NONE / linked / portal / Volume / GROUP / HERO / EEVEE")
    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), sampling="NONE")))
    check(recs == [], "sampling already NONE → no record")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), library=Obj())))
    check(recs == [], "linked world → skip")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0)), objects=[_portal()]))
    check(recs == [], "portal light → skip (has_portal keeps the map)")

    bg = _bg(strength=0.0)
    env = _env()
    out = _output()
    vol = _Node("Scatter", "VOLUME_SCATTER",
                inputs=[_Sock("Color", (1, 1, 1)), _Sock("Density", 1.0)],
                outputs=[_Sock("Volume")],
                bl_idname="ShaderNodeVolumeScatter")
    tree = _Tree([bg, env, out, vol])
    tree.links.new(env.outputs.get("Color"), bg.inputs.get("Color"))
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    tree.links.new(vol.outputs.get("Volume"), out.inputs.get("Volume"))
    recs = zwb.classify_zero_world_bg(_scene(_world(tree)))
    check(recs == [], "Volume socket linked → skip")

    grp = _group()
    bg = _bg(strength=0.0)
    out = _output()
    tree = _Tree([grp, bg, out])
    tree.links.new(grp.outputs.get("Color"), bg.inputs.get("Color"))
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    recs = zwb.classify_zero_world_bg(_scene(_world(tree)))
    check(recs == [], "GROUP on Color path → unproven")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), override="HERO")))
    check(recs == [], "HERO override → skip")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), override="KEEP")))
    check(recs == [], "KEEP override → skip")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0)), engine="BLENDER_EEVEE"))
    check(recs == [], "EEVEE engine → no record")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), animated=True)))
    check(recs == [], "world animation_data → skip")

    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0), tree_animated=True)))
    check(recs == [], "node tree animation_data → skip")

    muted_env = _env()
    muted_env.mute = True
    bg = _bg(strength=0.0)
    out = _output()
    tree = _Tree([bg, out, muted_env])
    tree.links.new(muted_env.outputs.get("Color"), bg.inputs.get("Color"))
    tree.links.new(bg.outputs.get("Background"), out.inputs.get("Surface"))
    recs = zwb.classify_zero_world_bg(_scene(_world(tree)))
    check(recs == [], "muted Env Tex → Cycles bypass, skip")


def test_never_unlinks_nodes():
    section("apply never unlinks and only writes sampling_method")
    world = _world(_tree_env_strength(0.0))
    scene = _scene(world)
    jrnl = _Journal()
    applied = zwb.apply_zero_world_bg(scene, jrnl)
    check(len(applied) == 1, "apply writes NONE")
    check(world.cycles.sampling_method == "NONE", "sampling_method became NONE")
    check(world.use_nodes is True, "use_nodes stayed True")
    check(all(e["path"] == "cycles.sampling_method" for e in jrnl.entries),
          "journal only recorded sampling_method")
    check(all(e["owner"] is world for e in jrnl.entries),
          "journal owner is the world")
    counts = zwb.inventory_counts(applied)
    check(counts["NODE_UNLINKS"] == 0 and counts["WORLD_MIS_NONE"] == 0,
          "inventory never counts unlinks or WORLD_MIS_NONE")


def test_apply_revert_identity():
    section("apply → revert restores sampling_method")
    world = _world(_tree_env_strength(0.0), sampling="AUTOMATIC")
    scene = _scene(world)
    before = world.cycles.sampling_method
    jrnl = _Journal()
    zwb.apply_zero_world_bg(scene, jrnl)
    check(world.cycles.sampling_method == "NONE", "applied NONE")
    n = jrnl.revert()
    check(n == 1, "one journal entry reverted")
    check(world.cycles.sampling_method == before, "revert restored AUTOMATIC")


def test_apply_reproves():
    section("apply re-proves Strength 0 + spatial and not portal")
    live = _world(_tree_env_strength(1.0))
    jrnl = _Journal()
    applied = zwb.apply_zero_world_bg(_scene(live), jrnl)
    check(applied == [], "Strength 1 → apply no-op")
    check(live.cycles.sampling_method == "AUTOMATIC", "live sampling unchanged")
    check(jrnl.entries == [], "no journal write when world is live")

    portal_scene = _scene(_world(_tree_env_strength(0.0)), objects=[_portal()])
    applied = zwb.apply_zero_world_bg(portal_scene, _Journal())
    check(applied == [], "portal → apply no-op")
    check(portal_scene.world.cycles.sampling_method == "AUTOMATIC",
          "portal scene sampling unchanged")


def test_planner_hook_auto_off():
    section("planner hook exists; Auto plan does not call it")
    world = _world(_tree_env_strength(0.0))
    scene = _speed_scene(world)
    actions = speed_solver.zero_world_bg_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "ZERO_WORLD_BG",
          "hook fires on Strength 0 + Env Tex")
    check(actions[0].tier == 2, "tier 2 (Auto-off)")
    check(abs(actions[0].time_factor - 1.0) < 1e-9,
          "time_factor 1.0 (no claim)")
    check(len(actions[0].payload.get("records") or []) == 1,
          "payload carries the classify record")

    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check("ZERO_WORLD_BG" not in kinds,
          "ZERO_WORLD_BG is not in the default Auto plan")
    check("WORLD_MIS_NONE" not in kinds,
          "Env Tex world is not solid — WORLD_MIS_NONE still skips")
    check(all(a.tier <= 1 for a in plan.actions),
          "default plan still tier 0+1 only")

    solid = _speed_scene(_world(_tree_solid(0.0)))
    check(speed_solver.zero_world_bg_actions(solid) == [],
          "hook silent on solid (WORLD_MIS_NONE territory)")
    solid_plan = speed_solver.build_speed_plan(solid, {}, _mem(), _settings())
    check(any(a.kind == "WORLD_MIS_NONE" for a in solid_plan.actions),
          "solid noded world still gets WORLD_MIS_NONE on Auto")

    live = _speed_scene(_world(_tree_env_strength(1.0)))
    check(speed_solver.zero_world_bg_actions(live) == [],
          "hook silent when Strength is live")


def test_scene_agnostic_not_name_gated():
    section("classifier is DNA, never a scene/world name")
    recs = zwb.classify_zero_world_bg(_scene(
        _world(_tree_env_strength(0.0))))
    check(len(recs) == 1, "Classroom-named or loft-named is irrelevant — DNA fires")
    recs = zwb.classify_zero_world_bg(_scene(
        Obj(use_nodes=True,
            node_tree=_tree_env_strength(0.0),
            library=None, animation_data=None,
            cycles=Obj(sampling_method="MANUAL"),
            scenequant=Obj(override="AUTO"),
            name="World.ClassroomHDRI")))
    check(len(recs) == 1 and recs[0]["from"] == "MANUAL",
          "MANUAL sampling + Strength 0 + Env still fires regardless of name")


def test_inventory_never_counts_unlinks():
    section("inventory counts")
    counts = zwb.inventory_counts(
        zwb.classify_zero_world_bg(_scene(_world(_tree_env_strength(0.0)))))
    check(counts["ZERO_WORLD_BG"] == 1, "inventory counts the MIS off")
    check(counts["NODE_UNLINKS"] == 0, "inventory never counts unlinks")
    check(counts["WORLD_MIS_NONE"] == 0, "does not steal WORLD_MIS_NONE count")


def main():
    test_gap_strength_zero_env_connected()
    test_world_mis_none_owns_solid()
    test_value_node_and_mix_rgb()
    test_skips_none_linked_portal_volume_group_hero_eevee()
    test_never_unlinks_nodes()
    test_apply_revert_identity()
    test_apply_reproves()
    test_planner_hook_auto_off()
    test_scene_agnostic_not_name_gated()
    test_inventory_never_counts_unlinks()
    finish()


if __name__ == "__main__":
    main()
