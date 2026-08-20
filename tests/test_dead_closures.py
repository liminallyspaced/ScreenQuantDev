# L1 DEAD_CLOSURE_PRUNE classifier + optional journaled apply.
# Duck-typed node trees; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_dead_closures.py

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


dc = _load("scenequant/analysis/dead_closures.py")
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

    def remove(self, link):
        if link in self._items:
            self._items.remove(link)
        for sock in (link.from_socket, link.to_socket):
            if sock is None:
                continue
            if link in sock.links:
                sock.links.remove(link)
            sock.is_linked = bool(sock.links)


class _Node:
    def __init__(self, name, ntype, inputs=None, outputs=None, **kw):
        self.name = name
        self.type = ntype
        self.bl_idname = kw.pop("bl_idname", "")
        self.image = kw.pop("image", None)
        self.node_tree = kw.pop("node_tree", None)
        self.aov_name = kw.pop("aov_name", None)
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


class _Journal:
    def __init__(self):
        self.entries = []

    def record_action(self, kind, payload, tag, run_id=None):
        entry = {"t": "action", "kind": kind, "payload": dict(payload), "tag": tag}
        if run_id is not None:
            entry["run"] = run_id
        self.entries.append(entry)


def _mesh(name, **kw):
    defaults = dict(
        name=name, type="MESH", hide_render=False, data=None,
        scenequant=Obj(override="AUTO"), material_slots=(),
        library=None, override_library=None,
    )
    defaults.update(kw)
    return Obj(**defaults)


def _scene(objects, **kw):
    data = dict(
        objects=objects, world=None, view_layers=[],
        use_nodes=False, node_tree=None, compositing_node_group=None,
        cycles=Obj(samples=256),
    )
    data.update(kw)
    return Obj(**data)


def _principled():
    return _Node(
        "Principled BSDF", "BSDF_PRINCIPLED",
        inputs=[
            _Sock("Alpha", 1.0),
            _Sock("Transmission Weight", 0.0),
            _Sock("Transmission", 0.0),
        ],
        outputs=[_Sock("BSDF")],
    )


def _output():
    return _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume"), _Sock("Displacement")],
    )


def _mat(name, nodes, links, library=None, blend="OPAQUE"):
    tree = _Tree(nodes)
    for src, src_sock, dst, dst_sock in links:
        tree.links.new(src.outputs.get(src_sock), dst.inputs.get(dst_sock))
    return Obj(
        name=name, library=library, override_library=None,
        blend_method=blend, node_tree=tree, use_nodes=True,
        use_transparent_shadow=True,
    )


def _classes(records):
    return [r["class"] for r in records]


def _for_mat(records, name):
    return [r for r in records if r.get("material") == name]


def _value_alpha_mat(name, value=1.0, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    prin = _principled()
    out = _output()
    return _mat(name, [val, prin, out], [
        (val, "Value", prin, "Alpha"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


def _image_alpha_mat(name, channels, filepath, alpha_mode="STRAIGHT",
                     file_format="", blend="OPAQUE", library=None):
    img = Obj(filepath=filepath, channels=channels, alpha_mode=alpha_mode,
              file_format=file_format, name=os.path.basename(filepath))
    tex = _Node(
        "Image Texture", "TEX_IMAGE",
        outputs=[_Sock("Color"), _Sock("Alpha", 1.0)],
        image=img, bl_idname="ShaderNodeTexImage",
    )
    prin = _principled()
    out = _output()
    return _mat(name, [tex, prin, out], [
        (tex, "Alpha", prin, "Alpha"),
        (prin, "BSDF", out, "Surface"),
    ], library=library, blend=blend)


def _hashed_cutout_mix_mat(name):
    img = Obj(filepath="//leaf.png", channels=4, alpha_mode="STRAIGHT",
              file_format="PNG", name="leaf.png")
    tex = _Node(
        "Image Texture", "TEX_IMAGE",
        outputs=[_Sock("Color"), _Sock("Alpha", 1.0)],
        image=img, bl_idname="ShaderNodeTexImage",
    )
    diff = _Node("Diffuse BSDF", "BSDF_DIFFUSE", outputs=[_Sock("BSDF")])
    trans = _Node("Transparent BSDF", "BSDF_TRANSPARENT", outputs=[_Sock("BSDF")])
    mix = _Node(
        "Mix Shader", "MIX_SHADER",
        inputs=[_Sock("Fac", 0.5), _Sock("Shader"), _Sock("Shader.001")],
        outputs=[_Sock("Shader")],
    )
    out = _output()
    return _mat(name, [tex, diff, trans, mix, out], [
        (tex, "Alpha", mix, "Fac"),
        (diff, "BSDF", mix, "Shader"),
        (trans, "BSDF", mix, "Shader.001"),
        (mix, "Shader", out, "Surface"),
    ], blend="HASHED")


def _glass_mat(name):
    glass = _Node("Glass BSDF", "BSDF_GLASS", outputs=[_Sock("BSDF")])
    out = _output()
    return _mat(name, [glass, out], [(glass, "BSDF", out, "Surface")])


def _group_mat(name):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", 1.0)])
    prin = _principled()
    out = _output()
    grp = _Node("Group", "GROUP", node_tree=Obj(nodes=[]))
    return _mat(name, [val, prin, out, grp], [
        (val, "Value", prin, "Alpha"),
        (prin, "BSDF", out, "Surface"),
    ])


def _empty_volume_mat(name):
    prin = _principled()
    out = _output()
    dummy = _Node("Value", "VALUE", outputs=[_Sock("Value", 0.0)])
    return _mat(name, [prin, out, dummy], [
        (prin, "BSDF", out, "Surface"),
        (dummy, "Value", out, "Volume"),
    ])


def _real_volume_mat(name):
    prin = _principled()
    out = _output()
    vol = _Node(
        "Principled Volume", "PRINCIPLED_VOLUME",
        inputs=[_Sock("Density", 1.0)],
        outputs=[_Sock("Volume")],
    )
    return _mat(name, [prin, out, vol], [
        (prin, "BSDF", out, "Surface"),
        (vol, "Volume", out, "Volume"),
    ])


def _aov_mat(name, aov="Dust"):
    prin = _principled()
    out = _output()
    aov_node = _Node("AOV Output", "OUTPUT_AOV", aov_name=aov,
                     inputs=[_Sock("Color"), _Sock("Value")])
    return _mat(name, [prin, out, aov_node], [
        (prin, "BSDF", out, "Surface"),
    ])



def _zero_disp_mat(name, value=0.0, source="VALUE", library=None):
    """Displacement linked to Value / Noise / GROUP."""
    prin = _principled()
    out = _output()
    nodes = [prin, out]
    links = [(prin, "BSDF", out, "Surface")]
    if source == "VALUE":
        val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
        nodes.append(val)
        links.append((val, "Value", out, "Displacement"))
    elif source == "NOISE":
        noise = _Node(
            "Noise Texture", "TEX_NOISE",
            outputs=[_Sock("Fac", 0.0), _Sock("Color")],
            bl_idname="ShaderNodeTexNoise",
        )
        nodes.append(noise)
        links.append((noise, "Fac", out, "Displacement"))
    elif source == "GROUP":
        val = _Node("Value", "VALUE", outputs=[_Sock("Value", 0.0)])
        grp = _Node("Group", "GROUP", node_tree=Obj(nodes=[]))
        nodes.extend([val, grp])
        links.append((val, "Value", out, "Displacement"))
    elif source == "NONE":
        pass
    return _mat(name, nodes, links, library=library)


def _with_obj(mat, obj_name="Mesh", **kw):
    return _scene([_mesh(obj_name, material_slots=[Obj(material=mat)], **kw)])



def _mix_transparent_mat(name, fac=1.0, fac_from=None, both_principled=False,
                         glass=False):
    """Mix Shader with optional constant Fac and Transparent on one side.

    Mix = (1-Fac)*Shader + Fac*Shader_001. Fac=1 → first unused; Fac=0 → second.
    fac_from: None (unlinked default), "VALUE", or "TEX".
    """
    prin = _principled()
    prin2 = _principled()
    prin2.name = "Principled BSDF.001"
    trans = _Node("Transparent BSDF", "BSDF_TRANSPARENT", outputs=[_Sock("BSDF")])
    glass_node = _Node("Glass BSDF", "BSDF_GLASS", outputs=[_Sock("BSDF")])
    mix = _Node(
        "Mix Shader", "MIX_SHADER",
        inputs=[_Sock("Fac", fac), _Sock("Shader"), _Sock("Shader.001")],
        outputs=[_Sock("Shader")],
    )
    out = _output()
    nodes = [prin, prin2, trans, mix, out]
    links = []
    if glass:
        nodes = [glass_node, trans, mix, out]
        # Fac=1: first unused Transparent would prune if glass did not skip.
        links = [
            (trans, "BSDF", mix, "Shader"),
            (glass_node, "BSDF", mix, "Shader.001"),
            (mix, "Shader", out, "Surface"),
        ]
    elif both_principled:
        links = [
            (prin, "BSDF", mix, "Shader"),
            (prin2, "BSDF", mix, "Shader.001"),
            (mix, "Shader", out, "Surface"),
        ]
    else:
        # Transparent on unused side for Fac=1 (first socket).
        links = [
            (trans, "BSDF", mix, "Shader"),
            (prin, "BSDF", mix, "Shader.001"),
            (mix, "Shader", out, "Surface"),
        ]
    if fac_from == "VALUE":
        val = _Node("Value", "VALUE", outputs=[_Sock("Value", fac)])
        nodes.append(val)
        links.append((val, "Value", mix, "Fac"))
        mix.inputs.get("Fac").default_value = 0.5  # linked; ignore default
    elif fac_from == "TEX":
        img = Obj(filepath="//mask.png", channels=4, alpha_mode="STRAIGHT",
                  file_format="PNG", name="mask.png")
        tex = _Node(
            "Image Texture", "TEX_IMAGE",
            outputs=[_Sock("Color"), _Sock("Alpha", 1.0)],
            image=img, bl_idname="ShaderNodeTexImage",
        )
        nodes.append(tex)
        links.append((tex, "Alpha", mix, "Fac"))
    return _mat(name, nodes, links)


def test_value_one_prunes_alpha():
    section("Principled Alpha linked to Value=1.0 → PRUNE_ALPHA")
    mat = _value_alpha_mat("Paint")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "Paint") if r["class"] == dc.PRUNE_ALPHA]
    check(len(hits) == 1, "Value=1.0 Alpha → one PRUNE_ALPHA")
    check(hits[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(hits[0]["socket"] == "Alpha", "record.socket is Alpha")
    check("Wall" in hits[0]["users"], "users lists the mesh")
    check("opaque" in hits[0]["reason"], "reason names opaque constant")


def test_jpeg_prunes_alpha():
    section("Principled Alpha linked to Image with no alpha / JPEG → PRUNE_ALPHA")
    mat = _image_alpha_mat("WallPaint", 3, "//wall.jpg", file_format="JPEG")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "WallPaint") if r["class"] == dc.PRUNE_ALPHA]
    check(len(hits) == 1, "JPEG / 3-channel Image Alpha → PRUNE_ALPHA")
    check("no alpha" in hits[0]["reason"] or "JPEG" in hits[0]["reason"],
          "reason names missing alpha / JPEG")
    check("wall.jpg" in (hits[0].get("alpha_src") or ""),
          "alpha_src names the Image filepath")


def test_real_cutout_kept():
    section("Image with alpha / HASHED cutout mix → KEEP_REAL_CUTOUT")
    png = _image_alpha_mat("Leaf", 4, "//leaf.png", file_format="PNG", blend="HASHED")
    records = dc.classify_dead_closures(_with_obj(png, "Card"))
    hits = [r for r in _for_mat(records, "Leaf") if r["class"] == dc.KEEP_REAL_CUTOUT]
    check(len(hits) >= 1, "4-channel PNG Alpha → KEEP_REAL_CUTOUT")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in _for_mat(records, "Leaf")),
          "real cutout is not PRUNE_ALPHA")

    mix = _hashed_cutout_mix_mat("Wire")
    records = dc.classify_dead_closures(_with_obj(mix, "Fence"))
    hits = [r for r in _for_mat(records, "Wire") if r["class"] == dc.KEEP_REAL_CUTOUT]
    check(len(hits) >= 1, "HASHED Mix(Transparent, surface) → KEEP_REAL_CUTOUT")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in _for_mat(records, "Wire")),
          "HASHED mix is not PRUNE_ALPHA")


def test_glass_kept():
    section("Glass / transmission / BSDF_GLASS → KEEP_GLASS")
    mat = _glass_mat("Window")
    records = dc.classify_dead_closures(_with_obj(mat, "Pane"))
    hits = [r for r in _for_mat(records, "Window") if r["class"] == dc.KEEP_GLASS]
    check(len(hits) == 1, "BSDF_GLASS → KEEP_GLASS")
    check(all(r["class"] not in dc.PRUNE_CLASSES for r in _for_mat(records, "Window")),
          "glass material has no PRUNE_* writes")

    val = _Node("Value", "VALUE", outputs=[_Sock("Value", 1.0)])
    prin = _principled()
    prin.inputs.get("Transmission Weight").default_value = 1.0
    out = _output()
    trans = _mat("GlassP", [val, prin, out], [
        (val, "Value", prin, "Alpha"),
        (prin, "BSDF", out, "Surface"),
    ])
    records = dc.classify_dead_closures(_with_obj(trans, "Pane2"))
    check(any(r["class"] == dc.KEEP_GLASS for r in _for_mat(records, "GlassP")),
          "principled transmission → KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in _for_mat(records, "GlassP")),
          "transmission Alpha=1 is not pruned")


def test_group_skipped():
    section("GROUP tree → SKIP_GROUP")
    mat = _group_mat("Grouped")
    records = dc.classify_dead_closures(_with_obj(mat, "Prop"))
    hits = [r for r in _for_mat(records, "Grouped") if r["class"] == dc.SKIP_GROUP]
    check(len(hits) == 1, "GROUP node → SKIP_GROUP")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in _for_mat(records, "Grouped")),
          "GROUP is not proven-opaque")


def test_linked_skipped():
    section("linked material → SKIP_LINKED")
    mat = _value_alpha_mat("LibPaint", library="assets/lib.blend")
    records = dc.classify_dead_closures(_with_obj(mat, "Chair"))
    hits = [r for r in _for_mat(records, "LibPaint") if r["class"] == dc.SKIP_LINKED]
    check(len(hits) == 1, "linked material → SKIP_LINKED")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in _for_mat(records, "LibPaint")),
          "linked material is not pruned")


def test_volume_empty_and_real():
    section("Volume socket empty → PRUNE_VOLUME; PRINCIPLED_VOLUME → not prune")
    empty = _empty_volume_mat("Hollow")
    records = dc.classify_dead_closures(_with_obj(empty, "Box"))
    hits = [r for r in _for_mat(records, "Hollow") if r["class"] == dc.PRUNE_VOLUME]
    check(len(hits) == 1, "Volume linked to no volume nodes → PRUNE_VOLUME")
    check(hits[0]["socket"] == "Volume", "volume record socket is Volume")

    real = _real_volume_mat("Fog")
    records = dc.classify_dead_closures(_with_obj(real, "FogMesh"))
    check(all(r["class"] != dc.PRUNE_VOLUME for r in _for_mat(records, "Fog")),
          "Volume linked to PRINCIPLED_VOLUME is not pruned")


def test_hero_skipped():
    section("HERO material → skip")
    mat = _value_alpha_mat("HeroPaint")
    scene = _scene([_mesh(
        "HeroWall", scenequant=Obj(override="HERO"),
        material_slots=[Obj(material=mat)])])
    records = dc.classify_dead_closures(scene)
    check(_for_mat(records, "HeroPaint") == [],
          "HERO-only material emits no records")

    shared = _value_alpha_mat("SharedPaint")
    scene = _scene([
        _mesh("HeroWall", scenequant=Obj(override="HERO"),
              material_slots=[Obj(material=shared)]),
        _mesh("AutoWall", material_slots=[Obj(material=shared)]),
    ])
    records = dc.classify_dead_closures(scene)
    check(_for_mat(records, "SharedPaint") == [],
          "material shared with HERO is skipped")


def test_unused_aov():
    section("unused AOV Output → PRUNE_AOV")
    mat = _aov_mat("Dusty", "Dust")
    records = dc.classify_dead_closures(_with_obj(mat, "Floor"))
    hits = [r for r in _for_mat(records, "Dusty") if r["class"] == dc.PRUNE_AOV]
    check(len(hits) == 1, "unused AOV Dust → PRUNE_AOV")

    rlayer = Obj(
        type="R_LAYERS", layer="ViewLayer", inputs=(),
        outputs=[Obj(name="Dust", is_linked=True),
                 Obj(name="Image", is_linked=True)])
    scene = _with_obj(mat, "Floor")
    scene.use_nodes = True
    scene.node_tree = Obj(nodes=[rlayer])
    records = dc.classify_dead_closures(scene)
    check(all(r["class"] != dc.PRUNE_AOV for r in _for_mat(records, "Dusty")),
          "compositor-linked AOV is kept")


def test_apply_unlink_and_revert():
    section("apply unlinks with journal; revert restores links")
    mat = _value_alpha_mat("Paint")
    scene = _with_obj(mat, "Wall")
    scene.cycles = Obj(samples=256)
    alpha = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            alpha = node.inputs.get("Alpha")
    check(alpha is not None and alpha.is_linked, "fixture Alpha starts linked")
    records = dc.classify_dead_closures(scene)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    check(len(applied) == 1, "apply unlinks the one PRUNE_ALPHA socket")
    check(not alpha.is_linked, "Alpha is unlinked after apply")
    check(mat.use_transparent_shadow is True,
          "apply never writes use_transparent_shadow")
    check(scene.cycles.samples == 256, "apply never writes scene.cycles.*")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    payload = jrnl.entries[0]["payload"]
    check(payload["material"] == "Paint"
          and payload["node"] == "Principled BSDF"
          and payload["socket"] == "Alpha"
          and payload["from_node"] == "Value"
          and payload["from_socket"] == "Value",
          "journal payload is material/node/socket/from_node/from_socket")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and alpha.is_linked, "revert restores the Alpha link")
    check(not jrnl.entries, "successful revert consumes the NODE_UNLINK entry")

    # KEEP / SKIP records must not write
    glass = _glass_mat("Window")
    scene = _with_obj(glass, "Pane")
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl)
    check(applied == [] and jrnl.entries == [],
          "KEEP_GLASS is not applied")


def test_not_in_default_auto_plan():
    section("DEAD_CLOSURE_PRUNE is not in the default Auto plan")
    mat = _value_alpha_mat("Paint")
    vol = _empty_volume_mat("Hollow")
    mix = _mix_transparent_mat("Passthrough", fac=1.0)
    disp = _zero_disp_mat("Flat")
    scene = speed_solver_scene([
        _mesh("Wall", material_slots=[Obj(material=mat)]),
        _mesh("Box", material_slots=[Obj(material=vol)]),
        _mesh("Car", material_slots=[Obj(material=mix)]),
        _mesh("Floor", material_slots=[Obj(material=disp)]),
    ])
    plan = speed_solver.build_speed_plan(
        scene, {}, Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
                       per_image_mb={}),
        Obj(vram_budget_gb=8.0, min_texture_size=256,
            coverage_frame_samples=5, quality_factor=2.0))
    check(all(a.kind != "DEAD_CLOSURE_PRUNE" for a in plan.actions),
          "default Auto plan does not include DEAD_CLOSURE_PRUNE")
    inventory = dc.classify_dead_closures(scene)
    check(any(r["class"] == dc.PRUNE_ALPHA for r in inventory),
          "inventory still sees PRUNE_ALPHA (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_VOLUME for r in inventory),
          "inventory still sees PRUNE_VOLUME (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_MIX_TRANSPARENT for r in inventory),
          "inventory still sees PRUNE_MIX_TRANSPARENT (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_DISPLACE for r in inventory),
          "inventory still sees PRUNE_DISPLACE (Auto is a separate gate)")
    path = os.path.join(PROJECT_ROOT, "scenequant", "planning",
                        "speed_solver.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    check(src.count("dead_closure_prune_actions(") == 1,
          "dead_closure_prune_actions is defined once and not called from build_speed_plan")


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
    return Obj(
        cycles=cycles, render=render, frame_start=1, frame_end=1,
        camera=Obj(), objects=objects, world=None, view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"), use_nodes=False, node_tree=None,
    )


def test_inventory_print_shape():
    section("inventory formatter names every class and prints no time claim")
    mat = _value_alpha_mat("Paint")
    text = dc.format_inventory(dc.classify_dead_closures(_with_obj(mat, "Wall")))
    check("no writes" in text and "no time claim" in text,
          "inventory header refuses a time claim")
    check("PRUNE_ALPHA=" in text and "PRUNE_MIX_TRANSPARENT=" in text
          and "PRUNE_DISPLACE=" in text and "Paint" in text,
          "table lists PRUNE_ALPHA / PRUNE_MIX_TRANSPARENT / PRUNE_DISPLACE")
    check("alpha_src=" in text, "PRUNE_ALPHA row prints alpha_src")


def test_default_plan_kind_absent_empty():
    section("empty scene default plan has no DEAD_CLOSURE_PRUNE")
    scene = speed_solver_scene([])
    plan = speed_solver.build_speed_plan(
        scene, {}, Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
                       per_image_mb={}),
        Obj(vram_budget_gb=8.0, min_texture_size=256,
            coverage_frame_samples=5, quality_factor=2.0))
    check(all(a.kind != "DEAD_CLOSURE_PRUNE" for a in plan.actions),
          "empty default plan has no DEAD_CLOSURE_PRUNE")



def test_mix_fac_one_unused_transparent_prunes():
    section("Mix Fac=1.0, Transparent on unused side → PRUNE_MIX_TRANSPARENT")
    mat = _mix_transparent_mat("Passthrough", fac=1.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "Passthrough")
            if r["class"] == dc.PRUNE_MIX_TRANSPARENT]
    check(len(hits) == 1, "Fac=1 + unused Transparent → one PRUNE_MIX_TRANSPARENT")
    check(hits[0]["node"] == "Mix Shader", "record.node is Mix Shader")
    check(hits[0]["socket"] in ("Shader", "Shader.001"),
          "record.socket is the dead shader input")
    check("MIX_TRANSPARENT" in hits[0]["reason"], "reason names MIX_TRANSPARENT")

    mat = _mix_transparent_mat("PassthroughV", fac=1.0, fac_from="VALUE")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall2"))
    hits = [r for r in _for_mat(records, "PassthroughV")
            if r["class"] == dc.PRUNE_MIX_TRANSPARENT]
    check(len(hits) == 1, "Fac from Value=1.0 → PRUNE_MIX_TRANSPARENT")

    mat = _mix_transparent_mat("Passthrough0", fac=0.0)
    # For Fac=0 unused is second; put Transparent there.
    # Rebuild: first Principled, second Transparent.
    prin = _principled()
    trans = _Node("Transparent BSDF", "BSDF_TRANSPARENT", outputs=[_Sock("BSDF")])
    mix = _Node(
        "Mix Shader", "MIX_SHADER",
        inputs=[_Sock("Fac", 0.0), _Sock("Shader"), _Sock("Shader.001")],
        outputs=[_Sock("Shader")],
    )
    out = _output()
    mat = _mat("Passthrough0", [prin, trans, mix, out], [
        (prin, "BSDF", mix, "Shader"),
        (trans, "BSDF", mix, "Shader.001"),
        (mix, "Shader", out, "Surface"),
    ])
    records = dc.classify_dead_closures(_with_obj(mat, "Wall3"))
    hits = [r for r in _for_mat(records, "Passthrough0")
            if r["class"] == dc.PRUNE_MIX_TRANSPARENT]
    check(len(hits) == 1, "Fac=0 + unused Transparent → PRUNE_MIX_TRANSPARENT")


def test_mix_fac_half_kept():
    section("Mix Fac=0.5 → keep (not PRUNE_MIX_TRANSPARENT)")
    mat = _mix_transparent_mat("Half", fac=0.5)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_MIX_TRANSPARENT
              for r in _for_mat(records, "Half")),
          "Fac=0.5 is not PRUNE_MIX_TRANSPARENT")


def test_mix_fac_from_texture_kept():
    section("Mix Fac from texture → keep")
    mat = _mix_transparent_mat("TexFac", fac=1.0, fac_from="TEX")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_MIX_TRANSPARENT
              for r in _for_mat(records, "TexFac")),
          "Fac from Image Texture is not PRUNE_MIX_TRANSPARENT")
    check(any(r["class"] == dc.KEEP_REAL_CUTOUT
              for r in _for_mat(records, "TexFac")),
          "texture Fac Transparent mix is KEEP_REAL_CUTOUT")


def test_mix_both_principled_not_mix_class():
    section("Mix Fac=1.0 both Principled → not PRUNE_MIX_TRANSPARENT")
    mat = _mix_transparent_mat("OpaqueMix", fac=1.0, both_principled=True)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_MIX_TRANSPARENT
              for r in _for_mat(records, "OpaqueMix")),
          "no Transparent side → not this class")


def test_mix_glass_skipped():
    section("Glass mix → KEEP_GLASS / skip Mix prune")
    mat = _mix_transparent_mat("WindowMix", fac=1.0, glass=True)
    records = dc.classify_dead_closures(_with_obj(mat, "Pane"))
    check(any(r["class"] == dc.KEEP_GLASS for r in _for_mat(records, "WindowMix")),
          "glass mix → KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_MIX_TRANSPARENT
              for r in _for_mat(records, "WindowMix")),
          "glass mix is not PRUNE_MIX_TRANSPARENT")


def test_apply_mix_transparent_unlink():
    section("apply unlinks dead Transparent Mix input; revert restores")
    mat = _mix_transparent_mat("Passthrough", fac=1.0)
    scene = _with_obj(mat, "Wall")
    dead = None
    for node in mat.node_tree.nodes:
        if node.type == "MIX_SHADER":
            dead = node.inputs.get("Shader")
    check(dead is not None and dead.is_linked, "fixture dead Shader starts linked")
    records = dc.classify_dead_closures(scene)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    mix_hits = [a for a in applied if a.get("node") == "Mix Shader"]
    check(len(mix_hits) == 1, "apply unlinks the dead Mix Shader input")
    check(not dead.is_linked, "dead Transparent input is unlinked after apply")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and dead.is_linked, "revert restores the Mix Shader link")



def test_displace_value_zero_prunes():
    section("Displacement linked to Value=0 → PRUNE_DISPLACE")
    mat = _zero_disp_mat("Flat", value=0.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Floor"))
    hits = [r for r in _for_mat(records, "Flat") if r["class"] == dc.PRUNE_DISPLACE]
    check(len(hits) == 1, "Value=0 Displacement → one PRUNE_DISPLACE")
    check(hits[0]["node"] == "Material Output", "record.node is Material Output")
    check(hits[0]["socket"] == "Displacement", "record.socket is Displacement")
    check("Floor" in hits[0]["users"], "users lists the mesh")
    scene = _with_obj(mat, "Floor")
    actions = speed_solver.dead_closure_prune_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "DEAD_CLOSURE_PRUNE"
          and actions[0].time_factor == 1.0,
          "manual hook counts PRUNE_DISPLACE")


def test_displace_value_half_kept():
    section("Displacement linked to Value=0.5 → not prune")
    mat = _zero_disp_mat("Bump", value=0.5)
    records = dc.classify_dead_closures(_with_obj(mat, "Floor"))
    check(all(r["class"] != dc.PRUNE_DISPLACE for r in _for_mat(records, "Bump")),
          "Value=0.5 Displacement is not PRUNE_DISPLACE")


def test_displace_noise_and_group_kept():
    section("Displacement linked to Noise / GROUP → not prune")
    noise = _zero_disp_mat("Noisy", source="NOISE")
    records = dc.classify_dead_closures(_with_obj(noise, "Floor"))
    check(all(r["class"] != dc.PRUNE_DISPLACE
              for r in _for_mat(records, "Noisy")),
          "Noise Displacement is not PRUNE_DISPLACE")
    grouped = _zero_disp_mat("GroupedDisp", source="GROUP")
    records = dc.classify_dead_closures(_with_obj(grouped, "Prop"))
    check(all(r["class"] != dc.PRUNE_DISPLACE
              for r in _for_mat(records, "GroupedDisp")),
          "GROUP Displacement is not PRUNE_DISPLACE")
    check(any(r["class"] == dc.SKIP_GROUP
              for r in _for_mat(records, "GroupedDisp")),
          "GROUP tree is SKIP_GROUP")


def test_displace_unconnected_no_record():
    section("unconnected Displacement → no record")
    mat = _zero_disp_mat("Bare", source="NONE")
    records = dc.classify_dead_closures(_with_obj(mat, "Floor"))
    check(all(r["class"] != dc.PRUNE_DISPLACE
              for r in _for_mat(records, "Bare")),
          "unconnected Displacement emits no PRUNE_DISPLACE")
    check(all(r.get("socket") != "Displacement" for r in _for_mat(records, "Bare")),
          "unconnected Displacement emits no Displacement record")


def test_apply_displace_unlink_and_revert():
    section("apply unlinks Displacement; revert restores")
    mat = _zero_disp_mat("Flat", value=0.0)
    scene = _with_obj(mat, "Floor")
    disp = None
    for node in mat.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            disp = node.inputs.get("Displacement")
    check(disp is not None and disp.is_linked, "fixture Displacement starts linked")
    records = dc.classify_dead_closures(scene)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    hits = [a for a in applied if a.get("socket") == "Displacement"]
    check(len(hits) == 1, "apply unlinks the PRUNE_DISPLACE socket")
    check(not disp.is_linked, "Displacement is unlinked after apply")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and disp.is_linked, "revert restores the Displacement link")


def main():
    test_value_one_prunes_alpha()
    test_jpeg_prunes_alpha()
    test_real_cutout_kept()
    test_glass_kept()
    test_group_skipped()
    test_linked_skipped()
    test_volume_empty_and_real()
    test_hero_skipped()
    test_unused_aov()
    test_mix_fac_one_unused_transparent_prunes()
    test_mix_fac_half_kept()
    test_mix_fac_from_texture_kept()
    test_mix_both_principled_not_mix_class()
    test_mix_glass_skipped()
    test_apply_unlink_and_revert()
    test_apply_mix_transparent_unlink()
    test_displace_value_zero_prunes()
    test_displace_value_half_kept()
    test_displace_noise_and_group_kept()
    test_displace_unconnected_no_record()
    test_apply_displace_unlink_and_revert()
    test_not_in_default_auto_plan()
    test_inventory_print_shape()
    test_default_plan_kind_absent_empty()
    finish()


if __name__ == "__main__":
    main()
