using UnityEngine;

/// <summary>
/// 小遊戲裡的她：和桌寵同樣的 64 格點陣（正面／左／右）＋白色半透明翅膀，會拍翅膀、落地壓扁。
/// 原點在腳底中央。
/// </summary>
public class Character : MonoBehaviour
{
    SpriteRenderer body, wingL, wingR;
    Sprite front, left, right;
    public int Face;            // 0 正面、1 往右、-1 往左
    public float Squash;        // 0~1，落地壓扁
    public float FlapSpeed = 30f;
    public float FlapAmp = 0.5f;
    public bool Hidden;
    float t;

    const int WingRootRow = 22;   // wing.png 的根部（從上往下數）
    const float BodyRoot = 31f;   // 64 格圖裡翅膀根部離圖片底部的高度（肩胛骨）
    const float FeetPad = 3f;     // 64 格圖腳底下的透明邊

    public static Character Create(int outfit, Transform parent)
    {
        var go = new GameObject("Her");
        go.transform.SetParent(parent, false);
        var c = go.AddComponent<Character>();
        string dir = "outfit" + outfit + "/";
        var bottom = new Vector2(0.5f, 0f);
        c.front = Pix.Load(dir + "front", bottom);
        c.left = Pix.Load(dir + "left", bottom);
        c.right = Pix.Load(dir + "right", bottom);
        if (c.front.texture == Texture2D.whiteTexture)
        {
            c.front = Pix.Load("outfit0/front", bottom);
            c.left = Pix.Load("outfit0/left", bottom);
            c.right = Pix.Load("outfit0/right", bottom);
        }
        var wingTex = Resources.Load<Texture2D>("Pixel/wing");
        float wh = wingTex != null ? wingTex.height : 36f;
        var wing = Pix.Load("wing", new Vector2(0f, (wh - WingRootRow) / wh));
        c.wingL = Pix.Make("WingL", wing, 1, go.transform);
        c.wingR = Pix.Make("WingR", wing, 1, go.transform);
        c.body = Pix.Make("Body", c.front, 2, go.transform);
        return c;
    }

    void LateUpdate()
    {
        t += Time.deltaTime;
        body.enabled = !Hidden;
        body.sprite = Face == 0 ? front : (Face > 0 ? right : left);
        float sq = Squash;
        body.transform.localPosition = new Vector3(0f, -FeetPad * (1f - 0.15f * sq), 0f);
        body.transform.localScale = new Vector3(1f + 0.1f * sq, 1f - 0.15f * sq, 1f);
        float flap = 1f - FlapAmp * (0.5f + 0.5f * Mathf.Sin(t * FlapSpeed));
        float rootY = (BodyRoot - FeetPad) * (1f - 0.15f * sq);
        if (Face == 0)
        {
            wingR.enabled = wingL.enabled = true;
            wingR.transform.localPosition = new Vector3(2f, rootY, 0f);
            wingR.transform.localScale = new Vector3(flap, 1f, 1f);
            wingL.transform.localPosition = new Vector3(-2f, rootY, 0f);
            wingL.transform.localScale = new Vector3(-flap, 1f, 1f);
        }
        else
        {
            wingL.enabled = false;
            wingR.enabled = true;
            wingR.transform.localPosition = new Vector3(-Face * 4f, rootY, 0f);
            wingR.transform.localScale = new Vector3(-Face * flap, 1f, 1f);
        }
    }
}
