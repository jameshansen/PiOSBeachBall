"""Builds the beachball scene and renders the spinner frames.

Standalone:  blender -b -P blender/make_beachball.py
Writes blender/beachball.blend and blender/frames/beachball_NN.png (RGBA, transparent background).
The frames cover one full clockwise turn, so they loop seamlessly.
"""
import math
import os

import bmesh
import bpy

OUT = globals().get("OUT") or os.path.dirname(os.path.abspath(__file__))
SIZE = 128
FRAMES = 36
SWIRL = 2.2  # radians of twist from centre to rim
COLOURS = ["#2F7BF6", "#36C759", "#FFD60A", "#FF9F0A", "#FF453A", "#BF5AF2"]


def rgba(hexstr):
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c] + [1.0]


scene = bpy.data.scenes.new("BeachBall")
scene.world = bpy.data.worlds.new("BeachBallWorld")
scene.world.use_nodes = True
bg = next(n for n in scene.world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (1, 1, 1, 1)
bg.inputs["Strength"].default_value = 0.45

r = scene.render
try:
    r.engine = "CYCLES"
except TypeError:
    pass
scene.cycles.samples = 96
scene.cycles.use_denoising = True
r.resolution_x = r.resolution_y = SIZE
r.resolution_percentage = 100
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
try:
    scene.view_settings.view_transform = "Standard"
except TypeError:
    pass

# Ball: a slightly flattened sphere reads as the classic glossy pinwheel when seen head on.
mesh = bpy.data.meshes.new("BeachBall")
ball = bpy.data.objects.new("BeachBall", mesh)
scene.collection.objects.link(ball)
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=96, v_segments=48, radius=1.0)
bm.to_mesh(mesh)
bm.free()
for p in mesh.polygons:
    p.use_smooth = True
ball.scale = (1, 1, 0.55)

# Material: hue segment = floor(N * fract((atan2(y, x) + SWIRL * r) / 2pi)), using object coordinates
# so the colours turn with the object while the lights and highlight stay put.
mat = bpy.data.materials.new("BeachBall")
mat.use_nodes = True
nt = mat.node_tree
N = nt.nodes
L = nt.links
bsdf = next(n for n in N if n.type == "BSDF_PRINCIPLED")
bsdf.inputs["Roughness"].default_value = 0.25
bsdf.inputs["Coat Weight"].default_value = 1.0
bsdf.inputs["Coat Roughness"].default_value = 0.04

tc = N.new("ShaderNodeTexCoord")
sep = N.new("ShaderNodeSeparateXYZ")
L.new(tc.outputs["Object"], sep.inputs[0])


def math_node(op, a, b=None):
    m = N.new("ShaderNodeMath")
    m.operation = op
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            L.new(v, m.inputs[i])
    return m.outputs[0]


theta = math_node("ARCTAN2", sep.outputs["Y"], sep.outputs["X"])
rad = math_node("SQRT", math_node("ADD", math_node("MULTIPLY", sep.outputs["X"], sep.outputs["X"]),
                                  math_node("MULTIPLY", sep.outputs["Y"], sep.outputs["Y"])))
t = math_node("FRACT", math_node("DIVIDE", math_node("ADD", theta, math_node("MULTIPLY", rad, SWIRL)), 2 * math.pi))

ramp = N.new("ShaderNodeValToRGB")
ramp.color_ramp.interpolation = "CONSTANT"
els = ramp.color_ramp.elements
while len(els) < len(COLOURS):
    els.new(0.5)
for i, (e, c) in enumerate(zip(els, COLOURS)):
    e.position = i / len(COLOURS)
    e.color = rgba(c)
L.new(t, ramp.inputs["Fac"])

# Lighten toward the centre for the soft inner glow.
glow = N.new("ShaderNodeMix")
glow.data_type = "RGBA"
glow.blend_type = "SCREEN"
L.new(math_node("MULTIPLY", math_node("POWER", math_node("SUBTRACT", 1.0, rad), 3.0), 0.35), glow.inputs[0])
L.new(ramp.outputs["Color"], glow.inputs[6])  # A_Color
glow.inputs[7].default_value = (1, 1, 1, 1)  # B_Color
L.new(glow.outputs[2], bsdf.inputs["Base Color"])  # Result_Color
ball.data.materials.append(mat)

# Camera straight down the view axis, ball filling ~92% of the frame.
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 2.18
cam.location = (0, 0, 10)
scene.collection.objects.link(cam)
scene.camera = cam

key = bpy.data.objects.new("Key", bpy.data.lights.new("Key", "AREA"))
key.data.energy = 900
key.data.size = 1.5
key.location = (-4.5, 4.5, 4.0)  # upper left, so the highlight sits off centre
key.rotation_euler = (-key.location.normalized()).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(key)

frames_dir = os.path.join(OUT, "frames")
os.makedirs(frames_dir, exist_ok=True)
for i in range(FRAMES):
    ball.rotation_euler.z = -math.radians(360 * i / FRAMES)  # clockwise as seen from the camera
    r.filepath = os.path.join(frames_dir, f"beachball_{i:02d}.png")
    bpy.ops.render.render(write_still=True, scene=scene.name)
ball.rotation_euler.z = 0

bpy.data.libraries.write(os.path.join(OUT, "beachball.blend"), {scene}, fake_user=True)
print("rendered", FRAMES, "frames to", frames_dir)
