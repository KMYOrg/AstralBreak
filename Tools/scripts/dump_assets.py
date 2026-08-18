import sys, json
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import unreal
import ab_assets as A

OUT = r"D:/UE5Projects/AstralBreak/Tools/data/asset_catalog.json"

meshes = A.catalog("/Game", limit=300)
engine = [A.mesh_bounds(f"/Engine/BasicShapes/{n}")
          for n in ("Cube", "Cylinder", "Sphere", "Cone", "Plane")]

data = {"project_meshes": meshes, "engine_shapes": engine}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

unreal.log(f"[OK] project {len(meshes)}개, engine {len(engine)}개 -> {OUT}")