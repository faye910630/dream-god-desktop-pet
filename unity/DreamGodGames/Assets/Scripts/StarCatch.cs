using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// 接星星：在永夜山谷的地面左右移動，接住落下的星星糖（+1）與金色流星（+3），避開紫色惡夢球。
/// 漏接星星或碰到惡夢扣一顆心，共 3 顆；越玩越快。
/// </summary>
public class StarCatch : MonoBehaviour
{
    const float W = GameView.W, H = GameView.H;
    const float Floor = 30f;   // 地面高度（從畫面底部往上）
    const float Speed = 150f;
    const float Catch = 20f;   // 左右接得到的範圍
    const float BodyH = 58f;   // 身體高度（接星星的判定）

    class Obj { public float x, y, vy, vx, ph; public string kind; public SpriteRenderer sr; public List<SpriteRenderer> tail; }
    class Fx { public float x, y, vx, vy, life; public SpriteRenderer sr; }

    readonly List<Obj> objs = new List<Obj>();
    readonly List<Fx> fxs = new List<Fx>();
    readonly List<SpriteRenderer> bgStars = new List<SpriteRenderer>();
    float x, vx, t, spawnT, hurt;
    int score, lives, best;
    bool over;
    Character her;
    Transform world;

    void Start()
    {
        var cam = Camera.main != null ? Camera.main : FindAnyObjectByType<Camera>();
        cam.backgroundColor = Pix.C(12, 10, 26);
        best = PlayerPrefs.GetInt("best_stars", 0);
        world = new GameObject("World").transform;
        var rng = new System.Random(9);
        for (int i = 0; i < 60; i++)
        {
            var s = Pix.Make("Star", Pix.Dot, -10, world);
            s.transform.position = new Vector3(rng.Next(0, (int)W), rng.Next((int)Floor + 10, (int)H), 0);
            bgStars.Add(s);
        }
        var moon = Pix.Make("Moon", Pix.Circle(15, Pix.C(226, 228, 214), Pix.C(204, 206, 194)), -9, world);
        moon.transform.position = new Vector3(150, H - 70, 0);
        var ground = Pix.Make("Ground", Pix.Dot, -5, world);
        ground.color = Pix.C(8, 8, 12);
        ground.transform.position = new Vector3(W / 2, Floor / 2, 0);
        ground.transform.localScale = new Vector3(W, Floor, 1);
        var line = Pix.Make("Line", Pix.Dot, -4, world);
        line.color = Pix.C(40, 44, 60);
        line.transform.position = new Vector3(W / 2, Floor, 0);
        line.transform.localScale = new Vector3(W, 1, 1);
        var flower = Pix.Load("moonflower_glow", new Vector2(0.5f, 0f));
        foreach (var fx in new[] { 12f, 48f, 192f, 228f })
        {
            var f = Pix.Make("Moonflower", flower, -3, world);
            f.transform.position = new Vector3(fx, 2, 0);
            f.transform.localScale = new Vector3(0.5f, 0.5f, 1);
        }
        her = Character.Create(Boot.Outfit, world);
        her.FlapSpeed = 6f;
        her.FlapAmp = 0.25f;
        ResetGame();
    }

    void ResetGame()
    {
        foreach (var o in objs) DestroyObj(o);
        objs.Clear();
        x = W / 2; vx = 0; t = 0; spawnT = 0.6f; score = 0; lives = 3; over = false; hurt = 0;
    }

    void DestroyObj(Obj o)
    {
        if (o.sr) Destroy(o.sr.gameObject);
        if (o.tail != null) foreach (var s in o.tail) if (s) Destroy(s.gameObject);
    }

    float Level => Mathf.Min(1f, t / 90f);

    void Update()
    {
        if (GameInput.Escape) Application.Quit();
        float dt = Mathf.Min(Time.deltaTime, 1f / 20f);
        her.Squash = Mathf.Max(0, her.Squash - dt * 4);
        hurt = Mathf.Max(0, hurt - dt);
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
        t += dt;
        int dx = GameInput.Dx;
        if (dx != 0) vx = dx * Speed;
        else if (GameInput.MouseX.HasValue) vx = Mathf.Clamp((GameInput.MouseX.Value - x) * 6, -Speed, Speed);
        else vx *= 0.8f;
        her.Face = Mathf.Abs(vx) > 14 ? (vx > 0 ? 1 : -1) : 0;
        x = Mathf.Clamp(x + vx * dt, 16, W - 16);
        spawnT -= dt;
        if (spawnT <= 0)
        {
            spawnT = Random.Range(0.9f, 1.3f) * (1 - 0.6f * Level);
            float r = Random.value;
            string kind = r < 0.12f ? "gold" : (r < 0.12f + 0.18f + 0.12f * Level ? "nightmare" : "star");
            float sp = Random.Range(75f, 100f) + 120 * Level;
            if (kind == "gold") sp *= 1.5f;
            var o = new Obj { x = Random.Range(12f, W - 12), y = H + 8, vy = sp, kind = kind,
                              vx = kind == "gold" ? Random.Range(-12f, 12f) : 0, ph = Random.Range(0f, 6f) };
            string spr = kind == "nightmare" ? "nightmare" : "star0";
            o.sr = Pix.Make(kind, Pix.Load(spr, new Vector2(0.5f, 0.5f)), 1, world);
            if (kind == "gold")
            {
                o.sr.color = new Color(1f, 0.93f, 0.6f);
                o.tail = new List<SpriteRenderer>();
                for (int k = 1; k <= 5; k++)
                {
                    var tsr = Pix.Make("Tail", Pix.Dot, 0, world);
                    tsr.color = new Color(1f, 0.94f, 0.67f, 1f - k * 0.15f);
                    o.tail.Add(tsr);
                }
            }
            objs.Add(o);
        }
        float top = Floor + BodyH;
        objs.RemoveAll(o =>
        {
            o.y -= o.vy * dt;
            o.x = Mathf.Clamp(o.x + o.vx * dt, 6, W - 6);
            if (o.y <= top && o.y >= Floor && Mathf.Abs(o.x - x) < Catch)
            {
                if (o.kind == "nightmare")
                {
                    lives--;
                    hurt = 0.6f;
                    Burst(o.x, o.y, Pix.C(150, 90, 180));
                }
                else
                {
                    score += o.kind == "gold" ? 3 : 1;
                    her.Squash = 1;
                    Burst(o.x, o.y, Pix.C(255, 248, 206));
                }
                DestroyObj(o);
                return true;
            }
            if (o.y < Floor - 4)
            {
                if (o.kind != "nightmare")
                {
                    lives--;
                    hurt = 0.4f;
                    Burst(o.x, Floor, Pix.C(120, 120, 150));
                }
                DestroyObj(o);
                return true;
            }
            return false;
        });
        if (lives <= 0)
        {
            over = true;
            best = Mathf.Max(best, score);
            PlayerPrefs.SetInt("best_stars", best);
            PlayerPrefs.Save();
            GameResult.Add("stars", score, score, false);
        }
    }

    void Burst(float bx, float by, Color c)
    {
        for (int i = 0; i < 6; i++)
        {
            float a = Random.Range(0f, Mathf.PI * 2);
            var sr = Pix.Make("Fx", Pix.Dot, 3, world);
            sr.color = c;
            fxs.Add(new Fx { x = bx, y = by, vx = Mathf.Cos(a) * 35, vy = Mathf.Sin(a) * 35 + 20, life = 0.5f, sr = sr });
        }
    }

    void UpdateFx(float dt)
    {
        fxs.RemoveAll(f =>
        {
            f.life -= dt;
            f.x += f.vx * dt;
            f.y += f.vy * dt;
            f.vy -= 60 * dt;
            f.sr.transform.position = new Vector3(Mathf.Round(f.x), Mathf.Round(f.y), 0);
            if (f.life > 0) return false;
            Destroy(f.sr.gameObject);
            return true;
        });
    }

    void Draw()
    {
        for (int i = 0; i < bgStars.Count; i++)
        {
            float tw = 0.5f + 0.5f * Mathf.Sin(Time.time * (1 + i % 3) + i);
            float v = tw > 0.35f ? 0.55f + 0.43f * tw : 0f;
            bgStars[i].color = new Color(v, v, Mathf.Min(1, v + 0.08f), v > 0 ? 1 : 0);
        }
        foreach (var o in objs)
        {
            float wob = o.kind == "nightmare" ? Mathf.Round(Mathf.Sin(Time.time * 8 + o.ph)) : 0;
            o.sr.transform.position = new Vector3(Mathf.Round(o.x + wob), Mathf.Round(o.y), 0);
            if (o.tail != null)
                for (int k = 0; k < o.tail.Count; k++)
                    o.tail[k].transform.position = new Vector3(Mathf.Round(o.x - o.vx * 0.02f * (k + 1)), Mathf.Round(o.y + (k + 1) * 3), 0);
        }
        her.Hidden = hurt > 0 && ((int)(hurt * 12)) % 2 == 1;
        her.transform.position = new Vector3(Mathf.Round(x), Floor, 0);
    }

    void OnGUI()
    {
        float z = Screen.height / H;
        int fs = Mathf.RoundToInt(11 * z);
        Pix.Box(new Rect(2 * z, 2 * z, 80 * z, 30 * z), Pix.C(8, 8, 16), Pix.C(60, 56, 92));
        GUI.Label(new Rect(5 * z, 3 * z, 200, 40), "★ " + score, Pix.Label(fs, Pix.C(255, 248, 206)));
        GUI.Label(new Rect(5 * z, 16 * z, 200, 40), "最佳 " + best, Pix.Label(fs, Pix.C(206, 226, 168)));
        for (int i = 0; i < 3; i++)
        {
            var c = i < lives ? Pix.C(255, 150, 182) : Pix.C(60, 56, 80);
            Pix.Box(new Rect((W - 14 - i * 11) * z, 6 * z, 5 * z, 4 * z), c, c);
        }
        if (over)
        {
            var green = Pix.Label(fs, Pix.C(206, 226, 168));
            Pix.Box(new Rect(10 * z, (H / 2 - 36) * z, (W - 20) * z, 72 * z), Pix.C(8, 8, 16), Pix.C(150, 148, 186));
            GUI.Label(new Rect(22 * z, (H / 2 - 30) * z, 400, 40), "……結束了。", Pix.Label(fs, Pix.C(232, 228, 255)));
            GUI.Label(new Rect(22 * z, (H / 2 - 14) * z, 400, 40), "接到 " + score + " 顆星星", Pix.Label(fs, Pix.C(255, 248, 206)));
            GUI.Label(new Rect(22 * z, (H / 2 + 2) * z, 400, 40), "最佳 " + best, green);
            GUI.Label(new Rect(22 * z, (H / 2 + 18) * z, 400, 40), "空白鍵／點一下：再玩", Pix.Label(fs, Pix.C(176, 214, 244)));
        }
    }
}
