import unreal, sys, os, glob

full = unreal.Paths.convert_relative_path_to_full
log = unreal.log

log("PROJECT  : " + full(unreal.Paths.project_dir()))
log("ENGINE   : " + full(unreal.Paths.engine_dir()))
log("PYTHON   : " + sys.version.split()[0])

tools = [p for p in sys.path if "Tools" in p.replace("\\", "/")]
log("SYSPATH  : " + (str(tools) if tools else "!! Tools/lib 미등록 - 폴더 생성/재시작 확인"))

hits = glob.glob(os.path.join(full(unreal.Paths.engine_dir()),
                              "Plugins", "**", "remote_execution.py"), recursive=True)
for h in hits:
    log("REMOTEEXE: " + h.replace("\\", "/"))
if not hits:
    log("!! remote_execution.py 없음 - Python Editor Script Plugin 활성화 확인")