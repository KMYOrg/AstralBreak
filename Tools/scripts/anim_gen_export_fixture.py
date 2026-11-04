"""AI 애니 생성 Phase 1 테스트 픽스처 — 마켓 UE4 마네킹 애니를 프리뷰 메시째 FBX 로 내보낸다 (DevelopmentGuide §14 완료 기준 1).

    python Tools/ue_exec.py Tools/scripts/anim_gen_export_fixture.py

에디터 안에서 실행된다. 소스 애셋은 읽기만 한다(내보내기는 패키지를 더티로 만들지 않는다 — 출력 끝의 dirty 수로 확인).
출력: <Project>/Saved/AnimGen/Import/Katana_Attack_Slash1.fbx ([AnimGraphMcp] ImportSourceRoots 아래)
"""
import os

import unreal

SOURCE = "/Game/Assets/CombatMasterAnimBundle/Animations/HandsomeKatanaAnims/Mannequin_UE4/RootMotion/Attack/Katana_Attack_Slash1"
OUT_DIR = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()), "AnimGen", "Import")
OUT = os.path.join(OUT_DIR, "Katana_Attack_Slash1.fbx")


def dirty_count() -> int:
    return len(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())


def main() -> None:
    before = dirty_count()
    os.makedirs(OUT_DIR, exist_ok=True)
    seq = unreal.load_asset(SOURCE)
    options = unreal.FbxExportOption()
    options.export_preview_mesh = True
    task = unreal.AssetExportTask()
    task.object = seq
    task.filename = OUT
    task.automated = True
    task.prompt = False
    task.replace_identical = True
    task.exporter = unreal.AnimSequenceExporterFBX()
    task.options = options
    ok = unreal.Exporter.run_asset_export_task(task)
    size = os.path.getsize(OUT) if os.path.exists(OUT) else -1
    print(f"EXPORT ok={ok} file={OUT.replace(os.sep, '/')} bytes={size} skeleton={seq.get_editor_property('skeleton').get_path_name()} "
          f"frames={seq.get_editor_property('number_of_sampled_keys')} dirty_before={before} dirty_after={dirty_count()}")


main()
