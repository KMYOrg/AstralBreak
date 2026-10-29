"""Provider 레지스트리 — providers.json 매니페스트 + 이름별 구현. 테스트는 replace() 로 자리에 Mock 을 끼운다."""
from __future__ import annotations

import json
import pathlib

from .envelope import AnimGenError
from .providers.base import Provider
from .providers.blender import BlenderProvider
from .providers.body_fit import BodyFitPipe
from .providers.builtin import DirectKey, ExistingMotion, RetargetPipe
from .providers.inactive import InactiveProvider
from .providers.integrate import AnimBpPipe, PackagePipe
from .providers.local_ai import KimodoProvider
from .providers.meshy import MeshyProvider
from .providers.review import ReviewPipe

MANIFEST_FILE = pathlib.Path(__file__).with_name("providers.json")
IMPLEMENTATIONS = {
    "retarget": RetargetPipe,
    "existing_motion": ExistingMotion,
    "direct_key": DirectKey,
    "blender": BlenderProvider,
    "local_ai": KimodoProvider,
    "external.meshy": MeshyProvider,
    "package": PackagePipe,
    "anim_bp": AnimBpPipe,
    "review": ReviewPipe,
    "body_fit": BodyFitPipe,
}


def load_manifests() -> list[dict]:
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))["providers"]


class Registry:
    def __init__(self, manifests: list[dict] | None = None):
        self._providers: dict[str, Provider] = {}
        for manifest in manifests or load_manifests():
            self._providers[manifest["name"]] = IMPLEMENTATIONS.get(manifest["name"], InactiveProvider)(manifest)

    def get(self, name: str) -> Provider:
        try:
            return self._providers[name]
        except KeyError:
            raise AnimGenError("BAD_REQUEST", f"Unknown provider '{name}'", reason="UNKNOWN_PROVIDER", known=self.names()) from None

    def has(self, name: str) -> bool:
        return name in self._providers

    def names(self) -> list[str]:
        return list(self._providers)

    def all(self) -> list[Provider]:
        return list(self._providers.values())

    def manifests(self) -> dict[str, dict]:
        return {name: p.manifest for name, p in self._providers.items()}

    def replace(self, provider: Provider) -> None:
        """같은 이름 자리에 다른 구현을 끼운다 (테스트용 Mock, 이후 Phase 의 실제 어댑터)."""
        self._providers[provider.name] = provider
