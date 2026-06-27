// Copyright Epic Games, Inc. All Rights Reserved.

using UnrealBuildTool;

public class TPSample : ModuleRules
{
	public TPSample(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[] {
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"AIModule",
			"StateTreeModule",
			"GameplayStateTreeModule",
			"UMG",
			"Slate"
		});

		PrivateDependencyModuleNames.AddRange(new string[] { });

		PublicIncludePaths.AddRange(new string[] {
			"TPSample",
			"TPSample/Variant_Platforming",
			"TPSample/Variant_Platforming/Animation",
			"TPSample/Variant_Combat",
			"TPSample/Variant_Combat/AI",
			"TPSample/Variant_Combat/Animation",
			"TPSample/Variant_Combat/Gameplay",
			"TPSample/Variant_Combat/Interfaces",
			"TPSample/Variant_Combat/UI",
			"TPSample/Variant_SideScrolling",
			"TPSample/Variant_SideScrolling/AI",
			"TPSample/Variant_SideScrolling/Gameplay",
			"TPSample/Variant_SideScrolling/Interfaces",
			"TPSample/Variant_SideScrolling/UI"
		});

		// Uncomment if you are using Slate UI
		// PrivateDependencyModuleNames.AddRange(new string[] { "Slate", "SlateCore" });

		// Uncomment if you are using online features
		// PrivateDependencyModuleNames.Add("OnlineSubsystem");

		// To include OnlineSubsystemSteam, add it to the plugins section in your uproject file with the Enabled attribute set to true
	}
}
