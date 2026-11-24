using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 雲端之夢：自動往上彈，左右移動，從月光花山谷的葉子、穿過薄霧與雲海，一層一層跳到雲端之上的星空。
/// 座標：1 world unit = 1 點陣格，y 向上；鏡頭只往上跟。
/// </summary>
public class CloudJump : MonoBehaviour
{
    const float W = GameView.W, H = GameView.H;
    const float Grav = 700f, Jump = 360f, Speed = 130f, Goal = 3200f;   // 跳躍高度約 92 格

    class Plat { public float x, y, w, vx; public string kind; public bool alive = true; public SpriteRenderer sr; }
    class Item { public float x, y; public bool got; public SpriteRenderer sr; }
    class Fx { public float x, y, vx, vy, life; public SpriteRenderer sr; }

    readonly List<Plat> plats = new List<Plat>();
    readonly List<Item> items = new List<Item>();
    readonly List<Fx> fxs = new List<Fx>();
    readonly List<SpriteRenderer> bgStars = new List<SpriteRenderer>();
    readonly List<Vector2> bgStarBase = new List<Vector2>();
    readonly List<SpriteRenderer> sea = new List<SpriteRenderer>();

    float x, y, vx, vy, cam, topGen, height, t, bannerT;
    int stars, best;
    bool reached, over;
    Character her;
    Camera cam0;
    Transform world;
    SpriteRenderer moon;

    static readonly (float h, Color top, Color bottom)[] Bands =
    {
        (0, Pix.C(6, 6, 12), Pix.C(20, 16, 38)),
        (930, Pix.C(18, 20, 44), Pix.C(40, 46, 84)),
        (2000, Pix.C(58, 66, 112), Pix.C(140, 150, 196)),
        (2800, Pix.C(20, 24, 60), Pix.C(70, 76, 130)),
        (3460, Pix.C(6, 8, 24), Pix.C(22, 22, 58)),
    };

    int Meters => (int)(height / 8f);
    const float SeaY = 2020f, LeafTop = 930f, CloudTop = 2000f, MoonFrom = 2530f;

    void Start()
    {
        cam0 = Camera.main != null ? Camera.main : FindAnyObjectByType<Camera>();
        best = PlayerPrefs.GetInt("best_cloud", 0);
        world = new GameObject("World").transform;
        var rng = new System.Random(3);
        for (int i = 0; i < 90; i++)
        {
            var s = Pix.Make("Star", Pix.Dot, -10, world);
            bgStars.Add(s);
            bgStarBase.Add(new Vector2(rng.Next(0, (int)W), rng.Next(0, (int)H * 3)));
        }
        // 山谷底：黑色地面與月光花
        var ground = Pix.Make("Ground", Pix.Dot, -5, world);
        ground.color = Pix.C(8, 8, 12);
        ground.transform.position = new Vector3(W / 2, -40, 0);
        ground.transform.localScale = new Vector3(W, 80, 1);
        var flower = Pix.Load("moonflower_glow", new Vector2(0.5f, 0f));
        foreach (var fx in new[] { 14f, 52f, 188f, 226f })
        {
            var f = Pix.Make("Moonflower", flower, -4, world);
            f.transform.position = new Vector3(fx, -6, 0);
        }
        // 雲海
        var cloud = Pix.Load("cloud", new Vector2(0.5f, 0.5f));
        for (int k = 0; k < 14; k++)
        {
            var c = Pix.Make("Sea", cloud, -3, world);
            c.transform.localScale = new Vector3(2.2f, 2.6f, 1);
            sea.Add(c);
        }
        moon = Pix.Make("Moon", Pix.Circle(22, Pix.C(230, 232, 216), Pix.C(208, 210, 196)), -6, world);
        her = Character.Create(Boot.Outfit, world);
        ResetGame();
    }

    void ResetGame()
    {
        foreach (var p in plats) if (p.sr) Destroy(p.sr.gameObject);
        foreach (var i in items) if (i.sr) Destroy(i.sr.gameObject);
        plats.Clear();
        items.Clear();
        x = W / 2; y = 10; vx = 0; vy = Jump; cam = 0; topGen = 10; height = 0; stars = 0;
        reached = false; over = false; bannerT = 0; t = 0; her.Squash = 0;
        AddPlat(new Plat { x = W / 2, y = 8, w = W, kind = "ground" });
        GenUntil(H + 80);
    }

    void AddPlat(Plat p)
    {
        Sprite s = p.kind switch
        {
            "leaf" => Pix.Load("leaf", new Vector2(0.5f, 1f)),
            "cloud" => Pix.Load(p.vx != 0 ? "cloud_move" : "cloud", new Vector2(0.5f, 1f)),
            "bubble" => Pix.Load("bubble", new Vector2(0.5f, 0.5f)),
            _ => Pix.Dot,
        };
        p.sr = Pix.Make("Plat", s, 0, world);
        if (p.kind == "ground")
        {
            p.sr.color = Pix.C(30, 46, 40);
            p.sr.transform.localScale = new Vector3(W, 3, 1);
        }
        else if (p.kind != "bubble")
            p.sr.transform.localScale = new Vector3(p.w / s.rect.width, 1, 1);
        plats.Add(p);
    }

    void GenUntil(float h)
    {
        while (topGen < h)
        {
            float gap = 34 + Mathf.Min(26, topGen / 160f);
            topGen += Random.Range(gap * 0.75f, gap * 1.15f);
            float py = topGen;
            string kind = py < LeafTop ? "leaf" : py < CloudTop ? "cloud" : (Random.value < 0.33f ? "bubble" : "cloud");
            float w = kind == "bubble" ? 22 : Random.Range(40, 57);
            float pvx = (kind == "cloud" && py > 1200 && Random.value < 0.4f) ? (Random.value < 0.5f ? 26 : -26) : 0;
            AddPlat(new Plat { x = Random.Range(w / 2 + 2, W - w / 2 - 2), y = py, w = w, kind = kind, vx = pvx });
            if (Random.value < 0.28f)
            {
                var it = new Item { x = Random.Range(12f, W - 12), y = py + Random.Range(20f, 44f) };
                it.sr = Pix.Make("Candy", Pix.Load("star1", new Vector2(0.5f, 0.5f)), 1, world);
                items.Add(it);
            }
        }
    }

    void Update()
    {
        if (GameInput.Escape) Application.Quit();
        float dt = Mathf.Min(Time.deltaTime, 1f / 20f);
        t += dt;
        bannerT = Mathf.Max(0, bannerT - dt);
        her.Squash = Mathf.Max(0, her.Squash - dt * 4);
        UpdateFx(dt);
        if (over)
        {
            if (GameInput.ConsumeClick()) ResetGame();
        }
        else Step(dt);
        Draw();
    }

    void Step(float dt)
    {
        GameInput.ConsumeClick();
        int dx = GameInput.Dx;
        if (dx != 0) vx = dx * Speed;
        else if (GameInput.MouseX.HasValue)
        {
            float d = GameInput.MouseX.Value - x;
            if (Mathf.Abs(d) > W / 2) d -= Mathf.Sign(d) * W;   // 從另一邊繞過去比較近
            vx = Mathf.Clamp(d * 5, -Speed, Speed);
        }
        else vx *= 0.85f;
        her.Face = Mathf.Abs(vx) > 12 ? (vx > 0 ? 1 : -1) : 0;
        x = Mathf.Repeat(x + vx * dt, W);
        vy -= Grav * dt;
        float y0 = y;
        y += vy * dt;
        foreach (var p in plats)
        {
            if (p.vx == 0) continue;
            p.x += p.vx * dt;
            if (p.x < p.w / 2 || p.x > W - p.w / 2) p.vx = -p.vx;
        }
        if (vy < 0)
        {
            foreach (var p in plats)
            {
                if (p.alive && y0 >= p.y && p.y >= y && Mathf.Abs(x - p.x) <= p.w / 2 + 8)
                {
                    y = p.y;
                    vy = Jump;
                    her.Squash = 1;
                    if (p.kind == "bubble")
                    {
                        p.alive = false;
                        p.sr.enabled = false;
                        Burst(p.x, p.y, Pix.C(196, 226, 250));
                    }
                    break;
                }
            }
        }
        foreach (var it in items)
        {
            if (!it.got && Mathf.Abs(it.x - x) < 16 && it.y - y > -4 && it.y - y < 56)
            {
                it.got = true;
                it.sr.enabled = false;
                stars++;
                Burst(it.x, it.y, Pix.C(255, 248, 206));
            }
        }
        height = Mathf.Max(height, y);
        if (!reached && y >= Goal) { reached = true; bannerT = 3f; }
        float target = y - H * 0.45f;
        if (target > cam) cam = target;
        GenUntil(cam + H + 80);
        plats.RemoveAll(p =>
        {
            if (p.y > cam - 30) return false;
            Destroy(p.sr.gameObject);
            return true;
        });
        items.RemoveAll(i =>
        {
            if (i.y > cam - 30 && !i.got) return false;
            Destroy(i.sr.gameObject);
            return true;
        });
        if (y < cam - 30)
        {
            over = true;
            best = Mathf.Max(best, Meters);
            PlayerPrefs.SetInt("best_cloud", best);
            PlayerPrefs.Save();
            GameResult.Add("cloud", Meters, stars, reached);
        }
    }

    void Burst(float bx, float by, Color c)
    {
        for (int i = 0; i < 6; i++)
        {
            float a = Random.Range(0f, Mathf.PI * 2);
            var sr = Pix.Make("Fx", Pix.Dot, 3, world);
            sr.color = c;
            fxs.Add(new Fx { x = bx, y = by, vx = Mathf.Cos(a) * 35, vy = Mathf.Sin(a) * 35, life = 0.45f, sr = sr });
        }
    }

    void UpdateFx(float dt)
    {
        fxs.RemoveAll(f =>
        {
            f.life -= dt;
            f.x += f.vx * dt;
            f.y += f.vy * dt;
            f.sr.transform.position = new Vector3(Mathf.Round(f.x), Mathf.Round(f.y), 0);
            if (f.life > 0) return false;
            Destroy(f.sr.gameObject);
            return true;
        });
    }

    Color Sky(float h)
    {
        for (int i = 0; i < Bands.Length - 1; i++)
        {
            if (h < Bands[i + 1].h)
            {
                float k = (h - Bands[i].h) / (Bands[i + 1].h - Bands[i].h);
                return Color.Lerp(Color.Lerp(Bands[i].top, Bands[i].bottom, 0.5f),
                                  Color.Lerp(Bands[i + 1].top, Bands[i + 1].bottom, 0.5f), k);
            }
        }
        var last = Bands[Bands.Length - 1];
        return Color.Lerp(last.top, last.bottom, 0.5f);
    }

    void Draw()
    {
        cam0.transform.position = new Vector3(W / 2, Mathf.Round(cam + H / 2), -10);
        cam0.backgroundColor = Sky(cam + H / 2);
        float bright = Mathf.Min(1f, 0.35f + cam / Goal);
        for (int i = 0; i < bgStars.Count; i++)
        {
            var b = bgStarBase[i];
            float sy = (b.y + cam * 0.3f) % H;
            float tw = 0.5f + 0.5f * Mathf.Sin(t * (1 + i % 3) + i);
            var s = bgStars[i];
            s.transform.position = new Vector3(b.x, Mathf.Round(cam + sy), 0);
            float v = tw * bright > 0.3f ? (0.47f + 0.53f * tw * bright) : 0f;
            s.color = new Color(v, v, Mathf.Min(1, v + 0.08f), v > 0 ? 1 : 0);
        }
        for (int k = 0; k < sea.Count; k++)
        {
            float cx = (k * 41 + t * (4 + k % 3)) % (W + 70) - 35;
            sea[k].transform.position = new Vector3(Mathf.Round(cx), SeaY + (k % 3) * 50, 0);
        }
        moon.enabled = cam > MoonFrom;
        moon.transform.position = new Vector3(W - 52, Mathf.Round(cam + H - 50 - Mathf.Max(0, 3460 - cam) * 0.15f), 0);
        foreach (var p in plats)
            if (p.sr) p.sr.transform.position = new Vector3(Mathf.Round(p.x), Mathf.Round(p.kind == "ground" ? p.y - 1.5f : p.y), 0);
        foreach (var it in items)
            it.sr.transform.position = new Vector3(Mathf.Round(it.x), Mathf.Round(it.y + Mathf.Sin(t * 3 + it.x) * 1.5f), 0);
        her.transform.position = new Vector3(Mathf.Round(x), Mathf.Round(y), 0);
    }

    void OnGUI()
    {
        float z = Screen.height / H;
        int fs = Mathf.RoundToInt(11 * z);
        var white = Pix.Label(fs, Pix.C(232, 228, 255));
        var green = Pix.Label(fs, Pix.C(206, 226, 168));
        Pix.Box(new Rect(2 * z, 2 * z, 76 * z, 30 * z), Pix.C(8, 8, 16), Pix.C(60, 56, 92));
        GUI.Label(new Rect(5 * z, 3 * z, 200, 40), Meters + " m", white);
        GUI.Label(new Rect(5 * z, 16 * z, 300, 40), "★" + stars + "  最佳" + best, green);
        if (!reached)
        {
            float frac = Mathf.Min(1f, height / Goal);
            Pix.Box(new Rect((W - 8) * z, 6 * z, 4 * z, (H - 12) * z), Pix.C(30, 28, 46), Pix.C(30, 28, 46));
            var fill = new Rect((W - 8) * z, (6 + (H - 12) * (1 - frac)) * z, 4 * z, (H - 12) * frac * z);
            Pix.Box(fill, Pix.C(214, 236, 255), Pix.C(214, 236, 255));
        }
        if (bannerT > 0)
        {
            Pix.Box(new Rect(0, (H / 2 - 14) * z, W * z, 28 * z), Pix.C(10, 10, 24), Pix.C(10, 10, 24));
            GUI.Label(new Rect((W / 2 - 34) * z, (H / 2 - 7) * z, 300, 40), "……雲端之上。", Pix.Label(fs, Pix.C(255, 248, 206)));
        }
        if (over)
        {
            Pix.Box(new Rect(10 * z, (H / 2 - 36) * z, (W - 20) * z, 72 * z), Pix.C(8, 8, 16), Pix.C(150, 148, 186));
            GUI.Label(new Rect(22 * z, (H / 2 - 30) * z, 400, 40), "……掉下去了。", white);
            GUI.Label(new Rect(22 * z, (H / 2 - 14) * z, 400, 40), "高度 " + Meters + " m（目標 " + (int)(Goal / 8) + " m）", green);
            GUI.Label(new Rect(22 * z, (H / 2 + 2) * z, 400, 40), "星星糖 " + stars + "  最佳 " + best + " m", green);
            GUI.Label(new Rect(22 * z, (H / 2 + 18) * z, 400, 40), "空白鍵／點一下：再玩", Pix.Label(fs, Pix.C(176, 214, 244)));
        }
    }
}
