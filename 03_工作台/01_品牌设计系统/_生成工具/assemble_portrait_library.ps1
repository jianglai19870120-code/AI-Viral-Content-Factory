Add-Type -AssemblyName System.Drawing

$root = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $root '人物头像\portrait-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$portraitEntries = @($manifest.portraits.psobject.Properties)
$names = @{
  xiaojiang = '小姜'; xiaoshen = '小审'; xiaoxi = '小息'; xiaochai = '小拆'; xiaojing = '小镜'; xiaoce = '小策';
  xiaoxie = '小写'; xiaotu = '小图'; xiaoshu = '小数'; xiaojian = '小剪'; xiaofa = '小发'
}
$sheetPath = Join-Path $root '组件目录\人物总览-v1.png'

$cellWidth = 260; $cellHeight = 305; $gridColumns = 4
$gridRows = [math]::Ceiling([double]$portraitEntries.Count / [double]$gridColumns)
$sheet = [System.Drawing.Bitmap]::new($cellWidth * $gridColumns, $cellHeight * $gridRows, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$graphics = [System.Drawing.Graphics]::FromImage($sheet)
$graphics.Clear([System.Drawing.Color]::FromArgb(251,250,248))
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
$titleFont = [System.Drawing.Font]::new('Microsoft YaHei', 18, [System.Drawing.FontStyle]::Regular)
$idFont = [System.Drawing.Font]::new('Arial', 10, [System.Drawing.FontStyle]::Regular)
$brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(21,21,21))
$muted = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(130,125,118))

$index = 0
foreach ($entry in $portraitEntries) {
  $source = Join-Path $root ("人物头像\" + $entry.Value)
  $image = [System.Drawing.Image]::FromFile($source)
  $gridColumn = $index % $gridColumns; $gridRow = [math]::Floor($index / $gridColumns)
  $x = $gridColumn * $cellWidth; $y = $gridRow * $cellHeight
  $graphics.FillRectangle([System.Drawing.SolidBrush]::new([System.Drawing.Color]::White), $x + 12, $y + 12, 236, 281)
  $graphics.DrawImage($image, [System.Drawing.Rectangle]::new($x + 35, $y + 22, 190, 190))
  $graphics.DrawString($names[$entry.Name], $titleFont, $brush, $x + 20, $y + 225)
  $graphics.DrawString($entry.Name, $idFont, $muted, $x + 20, $y + 256)
  $image.Dispose(); $index += 1
}

$sheet.Save($sheetPath, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose(); $sheet.Dispose(); $titleFont.Dispose(); $idFont.Dispose(); $brush.Dispose(); $muted.Dispose()
