// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class AstralBreak : ModuleRules
{
	public AstralBreak(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
	
		PublicIncludePaths.AddRange(
			new string[] {
				"AstralBreak"
			}
		);

		
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core", 
			"CoreUObject", 
			"Engine", 
			"InputCore", 
			"EnhancedInput", 
			
			// GAS
			"GameplayAbilities",
			"GameplayTags",
			"GameplayTasks",
			
			"ModularGameplay",
			"GameFeatures",

			// 공격 방향 보정 — anim 루트모션의 로컬 트랜스폼을 월드 변환 직전에 수정 (락온 4단계)
			"MotionWarping",

			// 팀/피아 판정 (IGenericTeamAgentInterface) + 추후 M3 AIController/Perception
			"AIModule",
			
			// Networking
			"NetCore",
			
			// UMG / UI (디버그 위젯용)
			"UMG",
			"Slate",
			"SlateCore",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"DeveloperSettings",        // UDeveloperSettings 기반 프로젝트 세팅용
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });
		
		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
