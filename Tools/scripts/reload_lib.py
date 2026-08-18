"""에디터가 캐시한 Tools/lib 모듈을 강제 재로드한다.

ab_level.py 등을 수정한 뒤 build 스크립트를 돌리기 전에 한 번 실행한다.
UE 에디터 프로세스는 한 번 import한 모듈을 계속 들고 있어서,
이걸 안 하면 수정 전 코드로 빌드된다.
"""
import sys
sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

import importlib
import unreal

for name in ("ab_level", "ab_assets", "ab_montage"):
    if name in sys.modules:
        importlib.reload(sys.modules[name])
        unreal.log(f"reloaded: {name}")
    else:
        importlib.import_module(name)
        unreal.log(f"imported: {name}")
