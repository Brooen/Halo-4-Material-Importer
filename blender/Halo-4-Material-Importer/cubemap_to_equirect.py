"""
Cubemap ➜ Equirectangular Converter
==================================
This file now works **both** as a stand‑alone script (run it in Blender’s
*Scripting* tab) **and** as a helper module you can import from other parts of
your add‑on:

```python
from . import cubemap_to_equirect as c2e
rgb_png, alpha_png = c2e.convert_cubemap(r"C:/path/sky_00.dds", rotate_deg=[0]*6)
```

*Dependencies* (py360convert • imageio • Pillow) are auto‑installed the first
 time the script runs.
"""

# ─────────────────────────────────────────────────────────────────────────────
# USER DEFAULTS – used when you run this file directly
# ─────────────────────────────────────────────────────────────────────────────
INPUT_FIRST_FACE  = r"F:/SteamLibrary/steamapps/common/H4EK/images/environments/shared/textures/cubemap/wraparound_sky_cube_00_00.dds"
FACE_SIZE_OUT     = 0        # 0 ⇒ original res, otherwise pixels per cube face
LOAD_IN_BLENDER   = False    # True ⇒ load the resulting PNGs into Blender
ROTATE_DEG        = [90, -90, 0, 180, 180, 0]  # CW degrees for faces 00‑05

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTS & DEP HANDLING
# ─────────────────────────────────────────────────────────────────────────────
import os, sys, subprocess, importlib, re, bpy, numpy as np, types

def _ensure(pkg: str, module_name: str | None = None):
    try:
        return importlib.import_module(module_name or pkg)
    except ImportError:
        print(f"[INFO] Installing {pkg} …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
        return importlib.import_module(module_name or pkg)

py360   = _ensure("py360convert")
imageio = _ensure("imageio").v2
PIL     = _ensure("pillow", "PIL")
from PIL import Image  # noqa: E402  (import after ensuring Pillow)

# ─────────────────────────────────────────────────────────────────────────────
# CORE IMPLEMENTATION wrapped in a function so we can call it programmatically
# ─────────────────────────────────────────────────────────────────────────────

def _process(first_face: str, rotate_deg: list[int], face_size_out: int, load_in_blender: bool):
    """Convert the cubemap starting at *first_face* into RGB & Alpha PNG paths."""

    # ---------------------------------------------------------------------
    # Helper – load DDS into numpy RGBA
    # ---------------------------------------------------------------------
    def _load_dds_rgba(path: str) -> np.ndarray:
        img = bpy.data.images.load(path, check_existing=False)
        if img is None:
            raise FileNotFoundError(path)
        w, h = img.size
        arr = (np.asarray(img.pixels[:], dtype=np.float32)
                .reshape(h, w, 4) * 255 + 0.5).astype(np.uint8)
        img.user_clear(); bpy.data.images.remove(img)
        return arr

    def _rot(arr: np.ndarray, deg_cw: int) -> np.ndarray:
        deg_cw %= 360
        if deg_cw == 0:
            return arr
        if deg_cw % 90 != 0:
            raise ValueError("ROTATE_DEG values must be multiples of 90°.")
        k = (-deg_cw // 90) % 4  # 90 CW ⇒ 3 CCW rot90 steps
        return np.rot90(arr, k)

    first_face = os.path.normpath(first_face)
    if not os.path.isfile(first_face):
        raise FileNotFoundError(first_face)
    base, ext = os.path.splitext(first_face)
    if ext.lower() != ".dds":
        raise ValueError("Input file must be .dds")
    idx = base[-2:]
    if not idx.isdigit() or not 0 <= int(idx) <= 5:
        raise ValueError("Cubemap face index must be 00‑05 before .dds")

    prefix = base[:-2]
    faces = [f"{prefix}{i:02d}{ext}" for i in range(6)]
    for fp in faces:
        if not os.path.isfile(fp):
            raise FileNotFoundError(f"Missing cubemap face: {fp}")

    print("[INFO] Found all six faces:")
    for fp in faces:
        print("    ", os.path.basename(fp))

    if len(rotate_deg) != 6:
        raise ValueError("rotate_deg must list six values")

    # Load + rotate faces
    faces_np = [_rot(_load_dds_rgba(fp), rotate_deg[i]) for i, fp in enumerate(faces)]
    res_in = faces_np[0].shape[0]
    if any(f.shape[0] != f.shape[1] or f.shape[0] != res_in for f in faces_np):
        raise ValueError("All faces must be square and same resolution")

    face_sz = face_size_out if face_size_out > 0 else res_in
    w, h = face_sz * 4, face_sz * 2
    print(f"[INFO] Converting to equirectangular … ({w}×{h})")

    # Map index → py360 key
    idx2key = {0: "L", 1: "R", 2: "B", 3: "F", 4: "U", 5: "D"}

    cube_rgb = {idx2key[i]: faces_np[i][:, :, :3].astype(np.float32) / 255.0 for i in range(6)}
    cube_a   = {idx2key[i]: np.repeat(faces_np[i][:, :, 3:4], 3, axis=2).astype(np.float32) / 255.0 for i in range(6)}

    rgb_equi = py360.c2e(cube_rgb, h=h, w=w, cube_format="dict")
    a_equi   = py360.c2e(cube_a,  h=h, w=w, cube_format="dict")[:, :, 0]

    rgb_png = (rgb_equi * 255 + 0.5).astype(np.uint8)
    a_png   = (a_equi  * 255 + 0.5).astype(np.uint8)

    base_out   = re.sub(r"[0-5]{2}\.dds$", "", first_face, flags=re.IGNORECASE)
    rgb_path   = base_out + "equirect_rgb.png"
    alpha_path = base_out + "equirect_alpha.png"

    imageio.imwrite(rgb_path, rgb_png)
    imageio.imwrite(alpha_path, a_png)

    print("[DONE] Saved:\n    ", rgb_path, "\n    ", alpha_path)

    if load_in_blender:
        bpy.data.images.load(rgb_path,   check_existing=True)
        bpy.data.images.load(alpha_path, check_existing=True)
        print("[INFO] PNGs loaded into Blender.")

    return rgb_path, alpha_path

# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC FUNCTION – what the add‑on will call
# ─────────────────────────────────────────────────────────────────────────────

def convert_cubemap(first_face_path: str,
                    rotate_deg: list[int] | None = None,
                    face_size_out: int = 0,
                    load_in_blender: bool = False):
    """Convert cubemap (6 DDS faces) ➔ equirect PNGs.

    Returns *(rgb_path, alpha_path)*.
    """
    return _process(first_face_path,
                    rotate_deg or [0]*6,
                    face_size_out,
                    load_in_blender)

# ─────────────────────────────────────────────────────────────────────────────
# STAND‑ALONE ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    convert_cubemap(INPUT_FIRST_FACE, ROTATE_DEG, FACE_SIZE_OUT, LOAD_IN_BLENDER)
