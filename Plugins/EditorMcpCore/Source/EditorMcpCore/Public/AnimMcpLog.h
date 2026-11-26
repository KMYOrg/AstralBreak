#pragma once

#include "Logging/LogMacros.h"

/**
 * 에디터 MCP 공용 로그 카테고리. 이름은 플러그인 분리(2026-11-14) 전 그대로 둔다 — 로그를 grep 하는 기존 스크립트 · 문서 호환.
 * 정의는 코어(EditorMcpCoreModule.cpp), 기능 플러그인(AnimGraphMcp · StateTreeMcp · WidgetMcp)도 같은 카테고리를 쓴다.
 */
EDITORMCPCORE_API DECLARE_LOG_CATEGORY_EXTERN(LogAnimGraphMcp, Log, All);
