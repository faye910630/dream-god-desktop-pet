using UnityEditor;
using UnityEngine;

/// <summary>Resources/Pixel 底下的點陣圖：最近鄰、不壓縮、不產生 mipmap，保持清楚。</summary>
public class PixelImport : AssetPostprocessor
{
    void OnPreprocessTexture()
    {
        if (!assetPath.StartsWith("Assets/Resources/Pixel")) return;
        var ti = (TextureImporter)assetImporter;
        ti.textureType = TextureImporterType.Default;
        ti.filterMode = FilterMode.Point;
        ti.mipmapEnabled = false;
        ti.textureCompression = TextureImporterCompression.Uncompressed;
        ti.npotScale = TextureImporterNPOTScale.None;
        ti.alphaIsTransparency = true;
        ti.wrapMode = TextureWrapMode.Clamp;
    }

    void OnPreprocessAsset()
    {
        if (assetPath.EndsWith(".ttf") && assetImporter is TrueTypeFontImporter fi)
        {
            fi.fontRenderingMode = FontRenderingMode.HintedRaster;   // 點陣字不要糊
        }
    }
}
