# create_shortcut_altP.ps1
# Usage: depuis le dossier du projet, exécuter :
#   powershell -ExecutionPolicy Bypass -File .\create_shortcut_altP.ps1

$WshShell = New-Object -ComObject WScript.Shell

# Chemin vers l'exécutable dans le dossier dist
$target = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Definition) 'dist\ping_gui.exe'
$arguments = ""

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Ping-Intelligent.lnk"

# Create or overwrite the shortcut
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
if ($arguments) { $shortcut.Arguments = $arguments }
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.WindowStyle = 1
$shortcut.Description = "Ping Intelligent - Lanceur"
$shortcut.Hotkey = "ALT+P"
$shortcut.Save()

Write-Host "Raccourci créé sur le Bureau : $shortcutPath (Hotkey ALT+P)"