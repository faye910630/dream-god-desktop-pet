using System.Collections.Generic;
using System.IO;
using UnityEngine;

/// <summary>把每一局的成績累積寫到 -result 指定的 JSON，桌寵在遊戲視窗關掉後讀取、加心情。</summary>
public static class GameResult
{
    [System.Serializable]
    class Entry { public string game; public int score; public int stars; public bool reached; }

    [System.Serializable]
    class Doc { public List<Entry> rounds = new List<Entry>(); }

    static readonly Doc doc = new Doc();

    public static void Add(string game, int score, int stars, bool reached)
    {
        doc.rounds.Add(new Entry { game = game, score = score, stars = stars, reached = reached });
        if (string.IsNullOrEmpty(Boot.ResultPath)) return;
        try { File.WriteAllText(Boot.ResultPath, JsonUtility.ToJson(doc)); }
        catch (System.Exception e) { Debug.LogWarning("寫入成績失敗：" + e.Message); }
    }
}
