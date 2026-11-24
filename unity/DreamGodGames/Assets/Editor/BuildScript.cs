using System.IO;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

/// <summary>
/// 一鍵建置：建立只有 Boot 物件的場景、設定視窗，輸出 Windows 執行檔到 unity/Build/DreamGodGames.exe。
/// 批次模式：Unity.exe -batchmode -quit -projectPath unity/DreamGodGames -executeMethod BuildScript.Build
/// </summary>
public static class BuildScript
{
    const string ScenePath = "Assets/Scenes/Main.unity";

    [MenuItem("DreamGod/Build Windows")]
    public static void Build()
    {
        AssetDatabase.Refresh();
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        new GameObject("Boot").AddComponent<Boot>();
        EditorSceneManager.SaveScene(scene, ScenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };

        PlayerSettings.companyName = "DreamGod";
        PlayerSettings.productName = "夢境神明小遊戲";
        PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
        PlayerSettings.defaultScreenWidth = GameView.W * GameView.Zoom;
        PlayerSettings.defaultScreenHeight = GameView.H * GameView.Zoom;
        PlayerSettings.resizableWindow = false;
        PlayerSettings.runInBackground = true;
        PlayerSettings.visibleInBackground = true;
        PlayerSettings.SplashScreen.show = false;
        var icon = AssetDatabase.LoadAssetAtPath<Texture2D>("Assets/Resources/Pixel/icon.png");
        if (icon != null)
        {
            PlayerSettings.SetIcons(NamedBuildTarget.Unknown, new[] { icon }, IconKind.Any);   // 預設圖示
            var sizes = PlayerSettings.GetIconSizes(NamedBuildTarget.Standalone, IconKind.Any);
            var icons = new Texture2D[sizes.Length];
            for (int i = 0; i < icons.Length; i++) icons[i] = icon;
            PlayerSettings.SetIcons(NamedBuildTarget.Standalone, icons, IconKind.Any);          // exe／視窗圖示
        }

        var opts = new BuildPlayerOptions
        {
            scenes = new[] { ScenePath },
            locationPathName = Path.GetFullPath("../Build/DreamGodGames.exe"),
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None,
        };
        var report = BuildPipeline.BuildPlayer(opts);
        Debug.Log("DREAMGOD BUILD RESULT: " + report.summary.result + " -> " + opts.locationPathName);
        if (Application.isBatchMode && report.summary.result != BuildResult.Succeeded)
            EditorApplication.Exit(1);
    }
}
