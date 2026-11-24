using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 點陣素材載入（Resources/Pixel，由桌寵的 python l2d_pet.pyw --export-unity 產生）與共用繪圖工具。
/// </summary>
public static class Pix
{
    static readonly Dictionary<string, Sprite> cache = new Dictionary<string, Sprite>();
    static Font font;

    public static Sprite Load(string path, Vector2 pivot)
    {
        string key = path + "|" + pivot;
        if (cache.TryGetValue(key, out var s)) return s;
        var tex = Resources.Load<Texture2D>("Pixel/" + path);
        if (tex == null)
        {
            Debug.LogWarning("找不到素材 Pixel/" + path);
            tex = Texture2D.whiteTexture;
        }
        tex.filterMode = FilterMode.Point;
        s = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), pivot, 1f);
        cache[key] = s;
        return s;
    }

    public static SpriteRenderer Make(string name, Sprite sprite, int order, Transform parent)
    {
        var go = new GameObject(name);
        go.transform.SetParent(parent, false);
        var sr = go.AddComponent<SpriteRenderer>();
        sr.sprite = sprite;
        sr.sortingOrder = order;
        return sr;
    }

    /// <summary>1×1 白點：拿來畫星星、地面、色塊（用 scale 拉伸）。</summary>
    public static Sprite Dot => Load("pixel", new Vector2(0.5f, 0.5f));

    public static Font Font
    {
        get
        {
            if (font == null) font = Resources.Load<Font>("Fonts/Cubic_11");
            return font;
        }
    }

    /// <summary>畫一個點陣圓（月亮）。</summary>
    public static Sprite Circle(int r, Color fill, Color spot)
    {
        int d = r * 2 + 1;
        var tex = new Texture2D(d, d, TextureFormat.RGBA32, false) { filterMode = FilterMode.Point };
        for (int y = 0; y < d; y++)
            for (int x = 0; x < d; x++)
            {
                float dx = x - r, dy = y - r;
                Color c = dx * dx + dy * dy <= r * r ? fill : Color.clear;
                if ((dx - r * 0.3f) * (dx - r * 0.3f) + (dy - r * 0.2f) * (dy - r * 0.2f) < r * r * 0.06f && c.a > 0) c = spot;
                tex.SetPixel(x, y, c);
            }
        tex.Apply();
        return Sprite.Create(tex, new Rect(0, 0, d, d), new Vector2(0.5f, 0.5f), 1f);
    }

    public static Color C(int r, int g, int b) => new Color(r / 255f, g / 255f, b / 255f, 1f);

    /// <summary>點陣風的文字框（OnGUI 用）。</summary>
    public static GUIStyle Label(int px, Color color)
    {
        var st = new GUIStyle { font = Font, fontSize = px, richText = false };
        st.normal.textColor = color;
        return st;
    }

    public static void Box(Rect r, Color fill, Color border)
    {
        var old = GUI.color;
        GUI.color = border;
        GUI.DrawTexture(r, Texture2D.whiteTexture);
        GUI.color = fill;
        GUI.DrawTexture(new Rect(r.x + 2, r.y + 2, r.width - 4, r.height - 4), Texture2D.whiteTexture);
        GUI.color = old;
    }
}
