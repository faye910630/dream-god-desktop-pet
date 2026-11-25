using UnityEngine;

/// <summary>
/// 夢境神明小遊戲的進入點。命令列參數：
///   -game cloud|stars   雲端之夢／接星星
///   -outfit N           衣服編號（對應 Resources/outfits.json）
///   -result path        遊戲結束時把成績寫到這個 JSON 檔（給桌寵讀）
/// 場景裡只有一個掛著 Boot 的物件，其餘全部在執行時用程式產生。
/// </summary>
public class Boot : MonoBehaviour
{
    public static string Game = "cloud";
    public static int Outfit = 0;
    public static string ResultPath = "";
    string shotPath = "";
    float shotDelay = 4f;

    void Awake()
    {
        var args = System.Environment.GetCommandLineArgs();
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (args[i] == "-game") Game = args[i + 1];
            else if (args[i] == "-outfit") int.TryParse(args[i + 1], out Outfit);
            else if (args[i] == "-result") ResultPath = args[i + 1];
            else if (args[i] == "-shot") shotPath = args[i + 1];   // 測試用：幾秒後存截圖並結束
            else if (args[i] == "-shotdelay") float.TryParse(args[i + 1], out shotDelay);
        }

        Application.targetFrameRate = 60;
        QualitySettings.vSyncCount = 0;
        Screen.SetResolution(GameView.W * GameView.Zoom, GameView.H * GameView.Zoom, FullScreenMode.Windowed);

        var camGo = new GameObject("Camera") { tag = "MainCamera" };
        var cam = camGo.AddComponent<Camera>();
        cam.orthographic = true;
        cam.orthographicSize = GameView.H / 2f;
        cam.transform.position = new Vector3(GameView.W / 2f, GameView.H / 2f, -10f);
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = Color.black;

        gameObject.AddComponent<GameInput>();
        if (!string.IsNullOrEmpty(shotPath)) StartCoroutine(Shot());
        if (Game == "stars") gameObject.AddComponent<StarCatch>();
        else gameObject.AddComponent<CloudJump>();
    }

    System.Collections.IEnumerator Shot()
    {
        yield return new WaitForSeconds(shotDelay);
        yield return new WaitForEndOfFrame();
        ScreenCapture.CaptureScreenshot(shotPath);
        yield return new WaitForSeconds(0.5f);
        Application.Quit();
    }
}

/// <summary>畫面尺寸：遊戲內以「點陣格」為單位，1 格 = 1 world unit。</summary>
public static class GameView
{
    public const int W = 240;
    public const int H = 360;
    public const int Zoom = 2;
}
