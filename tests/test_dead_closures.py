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
            _Sock("Subsurface Weight", 0.0),
            _Sock("Subsurface Scale", 0.1),  # Cycles default
            _Sock("Emission Color", (1.0, 1.0, 1.0, 1.0)),
            _Sock("Emission Strength", 0.0),
            _Sock("Normal"),
        ],
        outputs=[_Sock("BSDF")],
    )


def _output():
    return _Node(
        "Material Output", "OUTPUT_MATERIAL",
        inputs=[_Sock("Surface"), _Sock("Volume"), _Sock("Displacement")],
    )


def _bump(name="Bump", strength=1.0):
    return _Node(
        name, "BUMP",
        inputs=[
            _Sock("Strength", strength),
            _Sock("Height", 0.0),
            _Sock("Distance", 1.0),
            _Sock("Normal"),
        ],
        outputs=[_Sock("Normal")],
        bl_idname="ShaderNodeBump",
    )


def _bevel(name="Bevel", radius=0.05):
    return _Node(
        name, "BEVEL",
        inputs=[_Sock("Radius", radius), _Sock("Normal")],
        outputs=[_Sock("Normal")],
        bl_idname="ShaderNodeBevel",
    )


def _bump_strength_mat(name, value=0.0, height_linked=True, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    bump = _bump()
    prin = _principled()
    out = _output()
    nodes = [val, bump, prin, out]
    links = [
        (val, "Value", bump, "Strength"),
        (bump, "Normal", prin, "Normal"),
        (prin, "BSDF", out, "Surface"),
    ]
    if height_linked:
        hval = _Node("Value.001", "VALUE", outputs=[_Sock("Value", 0.5)])
        nodes.append(hval)
        links.append((hval, "Value", bump, "Height"))
    return _mat(name, nodes, links, library=library)


def _bevel_radius_mat(name, value=0.0, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    bevel = _bevel()
    prin = _principled()
    out = _output()
    return _mat(name, [val, bevel, prin, out], [
        (val, "Value", bevel, "Radius"),
        (bevel, "Normal", prin, "Normal"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


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


def _value_sss_mat(name, value=0.0, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    prin = _principled()
    out = _output()
    return _mat(name, [val, prin, out], [
        (val, "Value", prin, "Subsurface Weight"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


def _value_transmission_mat(name, value=0.0, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    prin = _principled()
    out = _output()
    return _mat(name, [val, prin, out], [
        (val, "Value", prin, "Transmission Weight"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


def _value_transmission_sss_mat(name, trans=0.0, sss=0.0, library=None):
    val_t = _Node("Value", "VALUE", outputs=[_Sock("Value", trans)])
    val_s = _Node("Value.001", "VALUE", outputs=[_Sock("Value", sss)])
    prin = _principled()
    out = _output()
    return _mat(name, [val_t, val_s, prin, out], [
        (val_t, "Value", prin, "Transmission Weight"),
        (val_s, "Value", prin, "Subsurface Weight"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


def _image_transmission_mat(name):
    img = Obj(filepath="//glass.png", channels=4, alpha_mode="STRAIGHT",
              file_format="PNG", name="glass.png")
    tex = _Node(
        "Image Texture", "TEX_IMAGE",
        outputs=[_Sock("Color"), _Sock("Alpha", 1.0)],
        image=img, bl_idname="ShaderNodeTexImage",
    )
    prin = _principled()
    out = _output()
    return _mat(name, [tex, prin, out], [
        (tex, "Color", prin, "Transmission Weight"),
        (prin, "BSDF", out, "Surface"),
    ])


def _value_emission_mat(name, value=0.0, library=None):
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", value)])
    prin = _principled()
    out = _output()
    return _mat(name, [val, prin, out], [
        (val, "Value", prin, "Emission Strength"),
        (prin, "BSDF", out, "Surface"),
    ], library=library)


def _image_sss_mat(name):
    img = Obj(filepath="//skin.png", channels=4, alpha_mode="STRAIGHT",
              file_format="PNG", name="skin.png")
    tex = _Node(
        "Image Texture", "TEX_IMAGE",
        outputs=[_Sock("Color"), _Sock("Alpha", 1.0)],
        image=img, bl_idname="ShaderNodeTexImage",
    )
    prin = _principled()
    out = _output()
    return _mat(name, [tex, prin, out], [
        (tex, "Color", prin, "Subsurface Weight"),
        (prin, "BSDF", out, "Surface"),
    ])


def _image_alpha_mat(name, channels, filepath, alpha_mode="STRAIGHT",
                     file_format="", blend="OPAQUE", library=None,
                     packed_data=None):
    img = Obj(filepath=filepath, channels=channels, alpha_mode=alpha_mode,
              file_format=file_format,
              name=os.path.basename(filepath) if filepath else "packed")
    if packed_data is not None:
        img.packed_file = Obj(data=packed_data)
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


def test_packed_jpeg_magic_prunes_alpha():
    section("packed JPEG magic (no filepath / format / channels) → PRUNE_ALPHA")
    mat = _image_alpha_mat(
        "PackedJpeg", None, "",
        packed_data=b"\xff\xd8\xff\xe0\x00\x10\x4a\x46")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "PackedJpeg")
            if r["class"] == dc.PRUNE_ALPHA]
    check(len(hits) == 1, "packed JPEG SOI ffd8 → PRUNE_ALPHA")
    check("no alpha" in hits[0]["reason"] or "JPEG" in hits[0]["reason"],
          "reason names missing alpha / JPEG")


def test_packed_png_magic_kept():
    section("packed PNG signature → KEEP_REAL_CUTOUT (do not prune from magic)")
    mat = _image_alpha_mat(
        "PackedPng", None, "",
        packed_data=b"\x89PNG\r\n\x1a\n")
    records = dc.classify_dead_closures(_with_obj(mat, "Card"))
    hits = _for_mat(records, "PackedPng")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in hits),
          "packed PNG signature is not PRUNE_ALPHA")
    check(any(r["class"] == dc.KEEP_REAL_CUTOUT for r in hits),
          "packed PNG signature → KEEP_REAL_CUTOUT")


def test_empty_packed_data_does_not_guess():
    section("empty packed data does not guess no-alpha")
    mat = _image_alpha_mat("EmptyPacked", None, "", packed_data=b"")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = _for_mat(records, "EmptyPacked")
    check(all(r["class"] != dc.PRUNE_ALPHA for r in hits),
          "empty packed data is not PRUNE_ALPHA")
    check(any(r["class"] == dc.KEEP_REAL_CUTOUT for r in hits),
          "empty packed data stays KEEP_REAL_CUTOUT (no guess)")


def test_packed_bmp_magic_prunes_alpha():
    section("packed BMP magic (no filepath / format / channels) → PRUNE_ALPHA")
    mat = _image_alpha_mat(
        "PackedBmp", None, "",
        packed_data=b"BM\x00\x00\x00\x00\x00\x00")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "PackedBmp")
            if r["class"] == dc.PRUNE_ALPHA]
    check(len(hits) == 1, "packed BMP BM → PRUNE_ALPHA")


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
    sss = _value_sss_mat("Skin")
    emit = _value_emission_mat("DarkEmit")
    trans = _value_transmission_mat("DeadGlass")
    bump = _bump_strength_mat("DeadBump", value=0.0)
    bevel = _bevel_radius_mat("DeadBevel", value=0.0)
    scene = speed_solver_scene([
        _mesh("Wall", material_slots=[Obj(material=mat)]),
        _mesh("Box", material_slots=[Obj(material=vol)]),
        _mesh("Car", material_slots=[Obj(material=mix)]),
        _mesh("Floor", material_slots=[Obj(material=disp)]),
        _mesh("Arm", material_slots=[Obj(material=sss)]),
        _mesh("Card", material_slots=[Obj(material=emit)]),
        _mesh("Dump", material_slots=[Obj(material=trans)]),
        _mesh("BumpMesh", material_slots=[Obj(material=bump)]),
        _mesh("BevelMesh", material_slots=[Obj(material=bevel)]),
    ])
    plan = speed_solver.build_speed_plan(
        scene, {}, Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
                       per_image_mb={}),
        Obj(vram_budget_gb=8.0, min_texture_size=256,
            coverage_frame_samples=5, quality_factor=2.0))
    kinds = [a.kind for a in plan.actions]
    blob = " ".join("%s %s" % (a.kind, a.label) for a in plan.actions)
    check("DEAD_CLOSURE_PRUNE" not in kinds,
          "default Auto plan does not include DEAD_CLOSURE_PRUNE")
    check("PRUNE_SSS" not in kinds and "PRUNE_SSS" not in blob,
          "default Auto plan does not include PRUNE_SSS actions")
    check("PRUNE_EMISSION" not in kinds and "PRUNE_EMISSION" not in blob,
          "default Auto plan does not include PRUNE_EMISSION actions")
    check("PRUNE_TRANSMISSION" not in kinds and "PRUNE_TRANSMISSION" not in blob,
          "default Auto plan does not include PRUNE_TRANSMISSION actions")
    check("PRUNE_BUMP" not in kinds and "PRUNE_BUMP" not in blob,
          "default Auto plan does not include PRUNE_BUMP actions")
    check("PRUNE_BEVEL" not in kinds and "PRUNE_BEVEL" not in blob,
          "default Auto plan does not include PRUNE_BEVEL actions")
    inventory = dc.classify_dead_closures(scene)
    check(any(r["class"] == dc.PRUNE_ALPHA for r in inventory),
          "inventory still sees PRUNE_ALPHA (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_VOLUME for r in inventory),
          "inventory still sees PRUNE_VOLUME (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_MIX_TRANSPARENT for r in inventory),
          "inventory still sees PRUNE_MIX_TRANSPARENT (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_DISPLACE for r in inventory),
          "inventory still sees PRUNE_DISPLACE (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_SSS for r in inventory),
          "inventory still sees PRUNE_SSS (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_EMISSION for r in inventory),
          "inventory still sees PRUNE_EMISSION (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_TRANSMISSION for r in inventory),
          "inventory still sees PRUNE_TRANSMISSION (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_BUMP for r in inventory),
          "inventory still sees PRUNE_BUMP (Auto is a separate gate)")
    check(any(r["class"] == dc.PRUNE_BEVEL for r in inventory),
          "inventory still sees PRUNE_BEVEL (Auto is a separate gate)")
    path = os.path.join(PROJECT_ROOT, "scenequant", "planning",
                        "speed_solver.py")
    with open(path, encoding="utf-8") as handle:
        src = handle.read()
    check(src.count("dead_closure_prune_actions(") == 2,
          "dead_closure_prune_actions is defined once and called from _dead_actions for Auto PRUNE_ALPHA")


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
          and "PRUNE_DISPLACE=" in text and "PRUNE_SSS=" in text
          and "PRUNE_EMISSION=" in text and "PRUNE_TRANSMISSION=" in text
          and "PRUNE_BUMP=" in text and "PRUNE_BEVEL=" in text
          and "Paint" in text,
          "table lists PRUNE_ALPHA / MIX / DISPLACE / SSS / EMISSION / "
          "TRANSMISSION / BUMP / BEVEL")
    check("alpha_src=" in text, "PRUNE_ALPHA row prints alpha_src")


def test_default_plan_kind_absent_empty():
    section("empty scene default plan has no DEAD_CLOSURE_PRUNE")
    scene = speed_solver_scene([])
    plan = speed_solver.build_speed_plan(
        scene, {}, Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
                       per_image_mb={}),
        Obj(vram_budget_gb=8.0, min_texture_size=256,
            coverage_frame_samples=5, quality_factor=2.0))
    kinds = [a.kind for a in plan.actions]
    check("DEAD_CLOSURE_PRUNE" not in kinds
          and "PRUNE_SSS" not in kinds
          and "PRUNE_EMISSION" not in kinds
          and "PRUNE_TRANSMISSION" not in kinds
          and "PRUNE_BUMP" not in kinds
          and "PRUNE_BEVEL" not in kinds,
          "empty default plan has no DEAD_CLOSURE_PRUNE / PRUNE_SSS / "
          "PRUNE_EMISSION / PRUNE_TRANSMISSION / PRUNE_BUMP / PRUNE_BEVEL")



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



def test_sss_weight_zero_prunes():
    section("Subsurface Weight linked to Value=0, Scale default 0.1 → PRUNE_SSS")
    mat = _value_sss_mat("Skin", value=0.0)
    prin = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            prin = node
    check(prin is not None, "fixture has Principled")
    check(prin.inputs.get("Subsurface Scale").default_value == 0.1,
          "Scale stays Cycles default 0.1")
    check(not prin.inputs.get("Subsurface Scale").is_linked,
          "Scale is not linked (must not be the write)")
    records = dc.classify_dead_closures(_with_obj(mat, "Arm"))
    hits = [r for r in _for_mat(records, "Skin") if r["class"] == dc.PRUNE_SSS]
    check(len(hits) == 1, "Weight=0 → one PRUNE_SSS")
    check(hits[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(hits[0]["socket"] == "Subsurface Weight",
          "record.socket is Subsurface Weight")
    check("Arm" in hits[0]["users"], "users lists the mesh")
    scene = _with_obj(mat, "Arm")
    actions = speed_solver.dead_closure_prune_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "DEAD_CLOSURE_PRUNE"
          and actions[0].time_factor == 1.0,
          "manual hook counts PRUNE_SSS")


def test_sss_weight_half_kept():
    section("Subsurface Weight linked to Value=0.5 → no PRUNE_SSS")
    mat = _value_sss_mat("RealSSS", value=0.5)
    records = dc.classify_dead_closures(_with_obj(mat, "Arm"))
    check(all(r["class"] != dc.PRUNE_SSS for r in _for_mat(records, "RealSSS")),
          "Value=0.5 Weight is not PRUNE_SSS")


def test_sss_weight_unlinked_zero_no_record():
    section("Subsurface Weight unlinked 0 → no PRUNE_SSS")
    prin = _principled()
    out = _output()
    mat = _mat("BareSSS", [prin, out], [
        (prin, "BSDF", out, "Surface"),
    ])
    weight = prin.inputs.get("Subsurface Weight")
    check(weight is not None and not weight.is_linked
          and weight.default_value == 0.0,
          "fixture Weight is unlinked 0")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_SSS for r in _for_mat(records, "BareSSS")),
          "unlinked Weight 0 emits no PRUNE_SSS")
    check(all(r.get("socket") != "Subsurface Weight"
              for r in _for_mat(records, "BareSSS")),
          "unlinked Weight emits no Subsurface Weight record")


def test_sss_weight_tex_image_kept():
    section("Subsurface Weight linked to TEX_IMAGE → no PRUNE_SSS")
    mat = _image_sss_mat("TexSSS")
    records = dc.classify_dead_closures(_with_obj(mat, "Arm"))
    check(all(r["class"] != dc.PRUNE_SSS for r in _for_mat(records, "TexSSS")),
          "TEX_IMAGE Weight is not PRUNE_SSS")


def test_emission_strength_zero_prunes():
    section("Emission Strength linked to Value=0, Color default white → PRUNE_EMISSION")
    mat = _value_emission_mat("DarkEmit", value=0.0)
    prin = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            prin = node
    color = prin.inputs.get("Emission Color")
    check(color is not None and not color.is_linked
          and tuple(color.default_value) == (1.0, 1.0, 1.0, 1.0),
          "Color stays default white unlinked")
    records = dc.classify_dead_closures(_with_obj(mat, "Card"))
    hits = [r for r in _for_mat(records, "DarkEmit")
            if r["class"] == dc.PRUNE_EMISSION]
    check(len(hits) == 1, "Strength=0 → one PRUNE_EMISSION")
    check(hits[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(hits[0]["socket"] == "Emission Strength",
          "record.socket is Emission Strength")
    check(all(r.get("socket") != "Emission Color"
              for r in _for_mat(records, "DarkEmit")),
          "never classifies Emission Color")


def test_emission_strength_one_kept():
    section("Emission Strength linked to Value=1.0 → no PRUNE_EMISSION")
    mat = _value_emission_mat("Lit", value=1.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Card"))
    check(all(r["class"] != dc.PRUNE_EMISSION for r in _for_mat(records, "Lit")),
          "Value=1.0 Strength is not PRUNE_EMISSION")


def test_apply_sss_unlink_and_revert():
    section("apply unlinks PRUNE_SSS Weight; revert restores")
    mat = _value_sss_mat("Skin", value=0.0)
    scene = _with_obj(mat, "Arm")
    scene.cycles = Obj(samples=256)
    weight = None
    scale = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            weight = node.inputs.get("Subsurface Weight")
            scale = node.inputs.get("Subsurface Scale")
    check(weight is not None and weight.is_linked, "fixture Weight starts linked")
    check(scale is not None and not scale.is_linked
          and scale.default_value == 0.1,
          "fixture Scale stays unlinked default 0.1")
    records = dc.classify_dead_closures(scene)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    hits = [a for a in applied if a.get("socket") == "Subsurface Weight"]
    check(len(hits) == 1, "apply unlinks the PRUNE_SSS socket")
    check(not weight.is_linked, "Weight is unlinked after apply")
    check(not scale.is_linked and scale.default_value == 0.1,
          "apply never unlinks Subsurface Scale")
    check(scene.cycles.samples == 256, "apply never writes scene.cycles.*")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    payload = jrnl.entries[0]["payload"]
    check(payload["material"] == "Skin"
          and payload["node"] == "Principled BSDF"
          and payload["socket"] == "Subsurface Weight"
          and payload["from_node"] == "Value"
          and payload["from_socket"] == "Value",
          "journal payload is material/node/socket/from_node/from_socket")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and weight.is_linked, "revert restores the Weight link")
    check(not jrnl.entries, "successful revert consumes the NODE_UNLINK entry")



def test_transmission_weight_zero_not_glass_prunes():
    section("Transmission Weight linked to Value=0 → not KEEP_GLASS, is PRUNE_TRANSMISSION")
    mat = _value_transmission_mat("PbrDump", value=0.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = _for_mat(records, "PbrDump")
    check(all(r["class"] != dc.KEEP_GLASS for r in hits),
          "Value=0 Transmission Weight is not KEEP_GLASS")
    prune = [r for r in hits if r["class"] == dc.PRUNE_TRANSMISSION]
    check(len(prune) == 1, "Value=0 Weight → one PRUNE_TRANSMISSION")
    check(prune[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(prune[0]["socket"] == "Transmission Weight",
          "record.socket is Transmission Weight")
    check("Wall" in prune[0]["users"], "users lists the mesh")
    scene = _with_obj(mat, "Wall")
    actions = speed_solver.dead_closure_prune_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "DEAD_CLOSURE_PRUNE"
          and actions[0].time_factor == 1.0,
          "manual hook counts PRUNE_TRANSMISSION")


def test_transmission_zero_also_prunes_sss():
    section("Value-0 Transmission + Value-0 SSS → PRUNE_TRANSMISSION and PRUNE_SSS")
    mat = _value_transmission_sss_mat("PbrDump", trans=0.0, sss=0.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = _for_mat(records, "PbrDump")
    check(all(r["class"] != dc.KEEP_GLASS for r in hits),
          "proven-zero Transmission is not KEEP_GLASS (glass skip no longer blocks)")
    check(any(r["class"] == dc.PRUNE_TRANSMISSION for r in hits),
          "same material emits PRUNE_TRANSMISSION")
    sss = [r for r in hits if r["class"] == dc.PRUNE_SSS]
    check(len(sss) == 1, "same material also emits PRUNE_SSS")
    check(sss[0]["socket"] == "Subsurface Weight",
          "SSS record.socket is Subsurface Weight")


def test_transmission_weight_one_is_glass():
    section("Transmission Weight linked to Value=1.0 → KEEP_GLASS, no PRUNE_TRANSMISSION")
    mat = _value_transmission_mat("RealGlass", value=1.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Pane"))
    hits = _for_mat(records, "RealGlass")
    check(any(r["class"] == dc.KEEP_GLASS for r in hits),
          "Value=1.0 Transmission Weight → KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_TRANSMISSION for r in hits),
          "Value=1.0 Weight is not PRUNE_TRANSMISSION")


def test_transmission_weight_tex_image_is_glass():
    section("Transmission Weight linked to TEX_IMAGE → KEEP_GLASS, no PRUNE_TRANSMISSION")
    mat = _image_transmission_mat("TexGlass")
    records = dc.classify_dead_closures(_with_obj(mat, "Pane"))
    hits = _for_mat(records, "TexGlass")
    check(any(r["class"] == dc.KEEP_GLASS for r in hits),
          "TEX_IMAGE Transmission Weight → KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_TRANSMISSION for r in hits),
          "TEX_IMAGE Weight is not PRUNE_TRANSMISSION")


def test_transmission_unlinked_zero_neither():
    section("Transmission unlinked 0 → neither KEEP_GLASS nor PRUNE_TRANSMISSION")
    prin = _principled()
    out = _output()
    mat = _mat("BareTrans", [prin, out], [
        (prin, "BSDF", out, "Surface"),
    ])
    weight = prin.inputs.get("Transmission Weight")
    check(weight is not None and not weight.is_linked
          and weight.default_value == 0.0,
          "fixture Weight is unlinked 0")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = _for_mat(records, "BareTrans")
    check(all(r["class"] != dc.KEEP_GLASS for r in hits),
          "unlinked Transmission 0 is not KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_TRANSMISSION for r in hits),
          "unlinked Transmission 0 emits no PRUNE_TRANSMISSION")
    check(all(r.get("socket") != "Transmission Weight" for r in hits),
          "unlinked Weight emits no Transmission Weight record")


def test_apply_transmission_unlink_and_revert():
    section("apply unlinks PRUNE_TRANSMISSION Weight; revert restores")
    mat = _value_transmission_mat("PbrDump", value=0.0)
    scene = _with_obj(mat, "Wall")
    scene.cycles = Obj(samples=256)
    weight = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            weight = node.inputs.get("Transmission Weight")
    check(weight is not None and weight.is_linked, "fixture Weight starts linked")
    records = dc.classify_dead_closures(scene)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    hits = [a for a in applied if a.get("socket") == "Transmission Weight"]
    check(len(hits) == 1, "apply unlinks the PRUNE_TRANSMISSION socket")
    check(not weight.is_linked, "Weight is unlinked after apply")
    check(scene.cycles.samples == 256, "apply never writes scene.cycles.*")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    payload = jrnl.entries[0]["payload"]
    check(payload["material"] == "PbrDump"
          and payload["node"] == "Principled BSDF"
          and payload["socket"] == "Transmission Weight"
          and payload["from_node"] == "Value"
          and payload["from_socket"] == "Value",
          "journal payload is material/node/socket/from_node/from_socket")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and weight.is_linked, "revert restores the Weight link")
    check(not jrnl.entries, "successful revert consumes the NODE_UNLINK entry")


def test_bump_strength_zero_prunes_consumer_normal():
    section("Bump Strength linked Value 0, Normal → Principled Normal → PRUNE_BUMP")
    mat = _bump_strength_mat("DeadBump", value=0.0)
    prin = None
    bump = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            prin = node
        if node.type == "BUMP":
            bump = node
    strength = bump.inputs.get("Strength")
    normal = prin.inputs.get("Normal")
    check(strength is not None and strength.is_linked,
          "fixture Strength starts linked")
    check(normal is not None and normal.is_linked,
          "fixture Principled Normal starts linked")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "DeadBump") if r["class"] == dc.PRUNE_BUMP]
    check(len(hits) == 1, "Strength=0 → one PRUNE_BUMP")
    check(hits[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(hits[0]["socket"] == "Normal", "record.socket is consumer Normal")
    check(hits[0]["from_node"] == "Bump", "from_node is Bump")
    check(hits[0]["from_socket"] == "Normal", "from_socket is Bump Normal")
    check(all(r.get("socket") != "Strength" for r in _for_mat(records, "DeadBump")),
          "never classifies Bump Strength")
    scene = _with_obj(mat, "Wall")
    scene.cycles = Obj(samples=256)
    jrnl = _Journal()
    applied = dc.apply_dead_closures(scene, jrnl, records)
    hits_a = [a for a in applied if a.get("socket") == "Normal"]
    check(len(hits_a) == 1, "apply unlinks Principled Normal")
    check(not normal.is_linked, "Principled Normal is unlinked after apply")
    check(strength.is_linked, "apply never unlinks Bump Strength")
    check(scene.cycles.samples == 256, "apply never writes scene.cycles.*")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "journal kind is NODE_UNLINK")
    payload = jrnl.entries[0]["payload"]
    check(payload["material"] == "DeadBump"
          and payload["node"] == "Principled BSDF"
          and payload["socket"] == "Normal"
          and payload["from_node"] == "Bump"
          and payload["from_socket"] == "Normal",
          "journal payload is consumer Normal, not Strength")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and normal.is_linked, "revert restores the Normal link")
    check(not jrnl.entries, "successful revert consumes the NODE_UNLINK entry")


def test_bump_strength_one_kept():
    section("Bump Strength linked Value 1.0 → no PRUNE_BUMP")
    mat = _bump_strength_mat("LiveBump", value=1.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_BUMP for r in _for_mat(records, "LiveBump")),
          "Value=1.0 Strength is not PRUNE_BUMP")


def test_bump_height_unlinked_strength_one_kept():
    section("Bump Height unlinked, Strength unlinked 1.0 → no PRUNE_BUMP")
    bump = _bump(strength=1.0)
    prin = _principled()
    out = _output()
    mat = _mat("FoldedBump", [bump, prin, out], [
        (bump, "Normal", prin, "Normal"),
        (prin, "BSDF", out, "Surface"),
    ])
    height = bump.inputs.get("Height")
    strength = bump.inputs.get("Strength")
    check(height is not None and not height.is_linked,
          "fixture Height is unlinked")
    check(strength is not None and not strength.is_linked
          and strength.default_value == 1.0,
          "fixture Strength is unlinked default 1.0")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_BUMP for r in _for_mat(records, "FoldedBump")),
          "Height-unlinked Strength 1.0 is not PRUNE_BUMP (Cycles already folds)")


def test_bump_strength_unlinked_zero_prunes():
    section("Bump Strength unlinked default 0.0 → PRUNE_BUMP")
    bump = _bump(strength=0.0)
    prin = _principled()
    out = _output()
    mat = _mat("ZeroStrBump", [bump, prin, out], [
        (bump, "Normal", prin, "Normal"),
        (prin, "BSDF", out, "Surface"),
    ])
    strength = bump.inputs.get("Strength")
    check(strength is not None and not strength.is_linked
          and strength.default_value == 0.0,
          "fixture Strength is unlinked 0")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "ZeroStrBump")
            if r["class"] == dc.PRUNE_BUMP]
    check(len(hits) == 1, "unlinked Strength 0 → one PRUNE_BUMP")
    check(hits[0]["node"] == "Principled BSDF" and hits[0]["socket"] == "Normal",
          "record is consumer Normal")


def test_bevel_radius_zero_prunes():
    section("Bevel Radius linked Value 0 → Principled Normal → PRUNE_BEVEL")
    mat = _bevel_radius_mat("DeadBevel", value=0.0)
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    hits = [r for r in _for_mat(records, "DeadBevel") if r["class"] == dc.PRUNE_BEVEL]
    check(len(hits) == 1, "Radius=0 → one PRUNE_BEVEL")
    check(hits[0]["node"] == "Principled BSDF", "record.node is Principled BSDF")
    check(hits[0]["socket"] == "Normal", "record.socket is consumer Normal")
    check(hits[0]["from_node"] == "Bevel", "from_node is Bevel")
    check(all(r.get("socket") != "Radius" for r in _for_mat(records, "DeadBevel")),
          "never classifies Bevel Radius")
    scene = _with_obj(mat, "Wall")
    actions = speed_solver.dead_closure_prune_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "DEAD_CLOSURE_PRUNE"
          and actions[0].time_factor == 1.0,
          "manual hook counts PRUNE_BEVEL")


def test_bevel_radius_default_kept():
    section("Bevel Radius unlinked 0.05 → no PRUNE_BEVEL")
    bevel = _bevel(radius=0.05)
    prin = _principled()
    out = _output()
    mat = _mat("LiveBevel", [bevel, prin, out], [
        (bevel, "Normal", prin, "Normal"),
        (prin, "BSDF", out, "Surface"),
    ])
    radius = bevel.inputs.get("Radius")
    check(radius is not None and not radius.is_linked
          and abs(radius.default_value - 0.05) < 1e-9,
          "fixture Radius is unlinked default 0.05")
    records = dc.classify_dead_closures(_with_obj(mat, "Wall"))
    check(all(r["class"] != dc.PRUNE_BEVEL for r in _for_mat(records, "LiveBevel")),
          "unlinked Radius 0.05 is not PRUNE_BEVEL")


def test_glass_zero_bump_skipped():
    section("BSDF_GLASS tree with zero-strength bump → KEEP_GLASS, no PRUNE_BUMP")
    glass = _Node(
        "Glass BSDF", "BSDF_GLASS",
        inputs=[_Sock("Normal")],
        outputs=[_Sock("BSDF")],
    )
    bump = _bump(strength=0.0)
    val = _Node("Value", "VALUE", outputs=[_Sock("Value", 0.0)])
    out = _output()
    mat = _mat("WindowBump", [val, bump, glass, out], [
        (val, "Value", bump, "Strength"),
        (bump, "Normal", glass, "Normal"),
        (glass, "BSDF", out, "Surface"),
    ])
    records = dc.classify_dead_closures(_with_obj(mat, "Pane"))
    hits = _for_mat(records, "WindowBump")
    check(any(r["class"] == dc.KEEP_GLASS for r in hits),
          "BSDF_GLASS + zero bump → KEEP_GLASS")
    check(all(r["class"] != dc.PRUNE_BUMP for r in hits),
          "glass skip blocks PRUNE_BUMP")
    check(all(r["class"] not in dc.PRUNE_CLASSES for r in hits),
          "glass material has no PRUNE_* writes")



def _plan_mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={}, per_image_mb={})


def _plan_settings(profile=None, intent="STILL"):
    kw = dict(vram_budget_gb=8.0, min_texture_size=256,
              coverage_frame_samples=5, quality_factor=2.0,
              speed_render_intent=intent)
    if profile is not None:
        kw["speed_profile"] = profile
    return Obj(**kw)


def _alpha_plan_scene():
    jpeg = _image_alpha_mat("WallPaint", 3, "//wall.jpg", file_format="JPEG")
    val = _value_alpha_mat("Paint")
    return speed_solver_scene([
        _mesh("Wall", material_slots=[Obj(material=jpeg)]),
        _mesh("Wall2", material_slots=[Obj(material=val)]),
    ])


def test_aggressive_still_prunes_alpha_only():
    section("Aggressive still JPEG/Value-1.0 Alpha -> DEAD_CLOSURE_PRUNE PRUNE_ALPHA only")
    scene = _alpha_plan_scene()
    plan = speed_solver.build_speed_plan(
        scene, {}, _plan_mem(), _plan_settings("AGGRESSIVE", "STILL"))
    hits = [a for a in plan.actions if a.kind == "DEAD_CLOSURE_PRUNE"]
    check(len(hits) == 1, "Aggressive still has one DEAD_CLOSURE_PRUNE")
    recs = hits[0].payload.get("records") or []
    check(len(recs) >= 2 and all(r.get("class") == dc.PRUNE_ALPHA for r in recs),
          "payload records are PRUNE_ALPHA only")
    check(hits[0].time_factor == 1.0, "time_factor stays 1.0")
    check(hits[0].tier <= 1, "Auto PRUNE_ALPHA is tier <= 1")
    check("manual" not in (hits[0].label or "").lower(),
          "Auto label does not say manual")
    other = {dc.PRUNE_VOLUME, dc.PRUNE_MIX_TRANSPARENT, dc.PRUNE_DISPLACE,
             dc.PRUNE_SSS, dc.PRUNE_EMISSION, dc.PRUNE_TRANSMISSION,
             dc.PRUNE_BUMP, dc.PRUNE_BEVEL}
    check(not any(r.get("class") in other for r in recs),
          "Auto payload does not include non-alpha PRUNE_*")


def test_preserve_look_and_missing_profile_withhold_prune_alpha():
    section("Preserve Look / missing profile withhold DEAD_CLOSURE_PRUNE")
    scene = _alpha_plan_scene()
    for label, settings in (
            ("PRESERVE_LOOK", _plan_settings("PRESERVE_LOOK", "STILL")),
            ("missing profile", _plan_settings(None, "STILL")),
    ):
        plan = speed_solver.build_speed_plan(scene, {}, _plan_mem(), settings)
        kinds = [a.kind for a in plan.actions]
        check("DEAD_CLOSURE_PRUNE" not in kinds,
              "%s plan does not include DEAD_CLOSURE_PRUNE" % label)


def test_balanced_withholds_prune_alpha():
    section("Balanced withholds DEAD_CLOSURE_PRUNE")
    scene = _alpha_plan_scene()
    plan = speed_solver.build_speed_plan(
        scene, {}, _plan_mem(), _plan_settings("BALANCED", "STILL"))
    kinds = [a.kind for a in plan.actions]
    check("DEAD_CLOSURE_PRUNE" not in kinds,
          "Balanced plan does not include DEAD_CLOSURE_PRUNE")
    check("DEAD_CLOSURE_PRUNE" in speed_solver.BALANCED_BLOCKED_KINDS,
          "DEAD_CLOSURE_PRUNE is in BALANCED_BLOCKED_KINDS")
    check("DEAD_CLOSURE_PRUNE" in (plan.withheld_kinds or []),
          "Balanced reports DEAD_CLOSURE_PRUNE as withheld")


def test_aggressive_video_withholds_prune_alpha():
    section("Aggressive VIDEO withholds DEAD_CLOSURE_PRUNE")
    scene = _alpha_plan_scene()
    plan = speed_solver.build_speed_plan(
        scene, {}, _plan_mem(), _plan_settings("AGGRESSIVE", "VIDEO"))
    kinds = [a.kind for a in plan.actions]
    check("DEAD_CLOSURE_PRUNE" not in kinds,
          "Aggressive VIDEO plan does not include DEAD_CLOSURE_PRUNE")
    check("DEAD_CLOSURE_PRUNE" in speed_solver.VIDEO_BLOCKED_KINDS,
          "DEAD_CLOSURE_PRUNE is in VIDEO_BLOCKED_KINDS")
    check("DEAD_CLOSURE_PRUNE" in (plan.withheld_kinds or []),
          "Aggressive VIDEO reports DEAD_CLOSURE_PRUNE as withheld")


def test_aggressive_non_alpha_prunes_stay_manual():
    section("Aggressive Auto skips VOLUME/SSS/etc; manual hook still returns them")
    vol = _empty_volume_mat("Hollow")
    sss = _value_sss_mat("Skin")
    emit = _value_emission_mat("DarkEmit")
    scene = speed_solver_scene([
        _mesh("Box", material_slots=[Obj(material=vol)]),
        _mesh("Arm", material_slots=[Obj(material=sss)]),
        _mesh("Card", material_slots=[Obj(material=emit)]),
    ])
    plan = speed_solver.build_speed_plan(
        scene, {}, _plan_mem(), _plan_settings("AGGRESSIVE", "STILL"))
    kinds = [a.kind for a in plan.actions]
    check("DEAD_CLOSURE_PRUNE" not in kinds,
          "no Auto DEAD_CLOSURE_PRUNE without PRUNE_ALPHA")
    manual = speed_solver.dead_closure_prune_actions(scene)
    check(len(manual) == 1 and manual[0].kind == "DEAD_CLOSURE_PRUNE",
          "manual hook still returns non-alpha PRUNE_*")
    recs = manual[0].payload.get("records") or []
    classes = {r.get("class") for r in recs}
    check(dc.PRUNE_VOLUME in classes and dc.PRUNE_SSS in classes
          and dc.PRUNE_EMISSION in classes,
          "manual hook payload includes VOLUME/SSS/EMISSION")
    check(dc.PRUNE_ALPHA not in classes, "this scene has no PRUNE_ALPHA")
    check(manual[0].tier == 2, "manual-all-classes hook stays tier 2")
    check("manual" in (manual[0].label or "").lower(),
          "manual hook label still says manual")


def test_empty_aggressive_has_no_dead_closure_prune():
    section("empty scene Aggressive has no DEAD_CLOSURE_PRUNE")
    scene = speed_solver_scene([])
    plan = speed_solver.build_speed_plan(
        scene, {}, _plan_mem(), _plan_settings("AGGRESSIVE", "STILL"))
    kinds = [a.kind for a in plan.actions]
    check("DEAD_CLOSURE_PRUNE" not in kinds,
          "empty Aggressive plan has no DEAD_CLOSURE_PRUNE")


def _load_speed_apply():
    import importlib.util
    import types
    bpy_mod = types.ModuleType("bpy")
    bpy_mod.types = types.SimpleNamespace()
    saved = sys.modules.get("bpy")
    sys.modules["bpy"] = bpy_mod
    created = []

    def _ensure(name, rel):
        if name in sys.modules and getattr(sys.modules[name], "__path__", None):
            return sys.modules[name]
        mod = types.ModuleType(name)
        mod.__path__ = [os.path.join(PROJECT_ROOT, *rel.split("/"))]
        mod.__package__ = name
        sys.modules[name] = mod
        created.append(name)
        return mod

    try:
        _ensure("scenequant", "scenequant")
        _ensure("scenequant.analysis", "scenequant/analysis")
        _ensure("scenequant.planning", "scenequant/planning")
        _ensure("scenequant.apply", "scenequant/apply")
        cov = types.ModuleType("scenequant.analysis.coverage")
        sys.modules["scenequant.analysis.coverage"] = cov
        presets = types.ModuleType("scenequant.planning.presets")
        presets.TIER_PERCEPTUAL = ()
        presets.TIER_LOSSLESS = ()
        presets.MODE_SET = "set"
        presets.MODE_MIN = "min"
        presets.MODE_MAX = "max"
        sys.modules["scenequant.planning.presets"] = presets
        sys.modules["scenequant.planning.speed_solver"] = speed_solver
        for name in ("guards", "objects_apply", "settings_apply"):
            full = "scenequant.apply.%s" % name
            sys.modules[full] = types.ModuleType(full)
        path = os.path.join(PROJECT_ROOT, "scenequant", "apply", "speed_apply.py")
        spec = importlib.util.spec_from_file_location(
            "scenequant.apply.speed_apply", path)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "scenequant.apply"
        sys.modules["scenequant.apply.speed_apply"] = mod
        spec.loader.exec_module(mod)
    finally:
        if saved is None:
            sys.modules.pop("bpy", None)
        else:
            sys.modules["bpy"] = saved
    return mod


def test_handler_unlinks_and_revert_restores():
    section("DEAD_CLOSURE_PRUNE handler unlinks; revert restores NODE_UNLINK")
    speed_apply = _load_speed_apply()
    check("DEAD_CLOSURE_PRUNE" in speed_apply._HANDLERS,
          "DEAD_CLOSURE_PRUNE is registered in _HANDLERS")
    mat = _value_alpha_mat("Paint")
    scene = _with_obj(mat, "Wall")
    alpha = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            alpha = node.inputs.get("Alpha")
    check(alpha is not None and alpha.is_linked, "fixture Alpha starts linked")
    records = [r for r in dc.classify_dead_closures(scene)
               if r.get("class") == dc.PRUNE_ALPHA]
    check(len(records) == 1, "one PRUNE_ALPHA record for handler")
    jrnl = _Journal()
    skipped = []
    msg = speed_apply._HANDLERS["DEAD_CLOSURE_PRUNE"](
        scene, Obj(), jrnl, {"records": records}, {}, skipped, None)
    check(not skipped, "handler did not skip")
    check(msg and "1" in msg, "handler returns a short unlink summary")
    check(not alpha.is_linked, "handler unlinked Alpha")
    check(jrnl.entries and jrnl.entries[0]["kind"] == "NODE_UNLINK",
          "handler journals NODE_UNLINK")
    restored = dc.revert_dead_closures(scene, jrnl)
    check(restored == 1 and alpha.is_linked, "revert restores the Alpha link")
    check(not jrnl.entries, "successful revert consumes the NODE_UNLINK entry")


def main():
    test_value_one_prunes_alpha()
    test_jpeg_prunes_alpha()
    test_packed_jpeg_magic_prunes_alpha()
    test_packed_png_magic_kept()
    test_empty_packed_data_does_not_guess()
    test_packed_bmp_magic_prunes_alpha()
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
    test_sss_weight_zero_prunes()
    test_sss_weight_half_kept()
    test_sss_weight_unlinked_zero_no_record()
    test_sss_weight_tex_image_kept()
    test_emission_strength_zero_prunes()
    test_emission_strength_one_kept()
    test_apply_sss_unlink_and_revert()
    test_transmission_weight_zero_not_glass_prunes()
    test_transmission_zero_also_prunes_sss()
    test_transmission_weight_one_is_glass()
    test_transmission_weight_tex_image_is_glass()
    test_transmission_unlinked_zero_neither()
    test_apply_transmission_unlink_and_revert()
    test_bump_strength_zero_prunes_consumer_normal()
    test_bump_strength_one_kept()
    test_bump_height_unlinked_strength_one_kept()
    test_bump_strength_unlinked_zero_prunes()
    test_bevel_radius_zero_prunes()
    test_bevel_radius_default_kept()
    test_glass_zero_bump_skipped()
    test_not_in_default_auto_plan()
    test_inventory_print_shape()
    test_default_plan_kind_absent_empty()
    test_aggressive_still_prunes_alpha_only()
    test_preserve_look_and_missing_profile_withhold_prune_alpha()
    test_balanced_withholds_prune_alpha()
    test_aggressive_video_withholds_prune_alpha()
    test_aggressive_non_alpha_prunes_stay_manual()
    test_empty_aggressive_has_no_dead_closure_prune()
    test_handler_unlinks_and_revert_restores()
    finish()


if __name__ == "__main__":
    main()
