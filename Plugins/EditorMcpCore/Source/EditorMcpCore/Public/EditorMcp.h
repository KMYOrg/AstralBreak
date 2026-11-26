#pragma once

/**
 * 새 기능 플러그인(WidgetMcp 등)용 이름 — 코어 타입의 EditorMcp* 별칭.
 *
 * 코어 타입은 플러그인 분리(2026-11-14) 전 이름(FAnimMcp* · AnimMcp*)을 그대로 쓴다 — AnimGraphMcp · StateTreeMcp 의 기존 코드
 * 수천 줄을 건드리지 않기 위해서다. 새 코드는 이 별칭을 쓰고, 언젠가 이름을 뒤집을 때 이 파일만 바꾼다.
 * (별칭은 전방 선언이 안 되므로 헤더에서는 이 파일을 포함한다)
 */

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "EditorMcpCoreModule.h"

using FEditorMcpDispatcher = FAnimMcpDispatcher;
using FEditorMcpError = FAnimMcpError;
using FEditorMcpRequest = FAnimMcpRequest;
using FEditorMcpContext = FAnimMcpContext;
using FEditorMcpHandler = FAnimMcpHandler;

namespace EditorMcpErrorCodes = AnimMcpErrorCodes;
namespace EditorMcpJson = AnimMcpJson;
