using UnityEngine;

/// <summary>
/// 用 OnGUI 的事件讀鍵盤與滑鼠，不依賴新舊輸入系統的專案設定。
/// </summary>
public class GameInput : MonoBehaviour
{
    static bool left, right;
    static bool clicked;
    public static float? MouseX;   // 遊戲座標（點陣格）；滑鼠離開視窗時為 null
    public static bool Escape;

    public static int Dx => (right ? 1 : 0) - (left ? 1 : 0);

    public static bool ConsumeClick()
    {
        bool c = clicked;
        clicked = false;
        return c;
    }

    void OnGUI()
    {
        var e = Event.current;
        if (e == null) return;
        if (e.type == EventType.KeyDown || e.type == EventType.KeyUp)
        {
            bool down = e.type == EventType.KeyDown;
            switch (e.keyCode)
            {
                case KeyCode.LeftArrow:
                case KeyCode.A:
                    left = down;
                    if (down) MouseX = null;
                    break;
                case KeyCode.RightArrow:
                case KeyCode.D:
                    right = down;
                    if (down) MouseX = null;
                    break;
                case KeyCode.Space:
                case KeyCode.Return:
                    if (down) clicked = true;
                    break;
                case KeyCode.Escape:
                    if (down) Escape = true;
                    break;
            }
        }
        if (e.type == EventType.MouseDown) clicked = true;
        if (e.type == EventType.MouseMove || e.type == EventType.MouseDrag)
        {
            if (!left && !right)
                MouseX = e.mousePosition.x / Screen.width * GameView.W;
        }
    }

    void OnApplicationFocus(bool focus)
    {
        if (!focus) { left = right = false; }
    }
}
