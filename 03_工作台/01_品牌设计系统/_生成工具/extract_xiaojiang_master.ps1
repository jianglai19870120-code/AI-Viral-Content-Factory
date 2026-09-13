param(
    [Parameter(Mandatory = $true)]
    [string]$Source
)

Add-Type -AssemblyName System.Drawing

if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
    throw "Source image does not exist: $Source"
}

$source = (Resolve-Path -LiteralPath $Source).Path
$destination = Join-Path (Split-Path -Parent $PSScriptRoot) '人物头像\正式头像\xiaojiang-master.png'
$sourceImage = [System.Drawing.Bitmap]::new($source)
$canvas = [System.Drawing.Bitmap]::new(443, 445, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($canvas)
$graphics.Clear([System.Drawing.Color]::Transparent)
$graphics.DrawImage($sourceImage, [System.Drawing.Rectangle]::new(0, 0, 443, 445), [System.Drawing.Rectangle]::new(0, 0, 443, 445), [System.Drawing.GraphicsUnit]::Pixel)
$canvas.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$canvas.Dispose()
$sourceImage.Dispose()
