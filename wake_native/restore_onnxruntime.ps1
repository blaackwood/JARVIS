$ErrorActionPreference = "Stop"

$version = "1.32.0"
$package = "Microsoft.ML.OnnxRuntime"
$uri = "https://api.nuget.org/v3-flatcontainer/microsoft.ml.onnxruntime/$version/microsoft.ml.onnxruntime.$version.nupkg"
$destination = Join-Path $PSScriptRoot "deps\ort"
$header = Join-Path $destination "build\native\include\onnxruntime_c_api.h"
$library = Join-Path $destination "runtimes\win-x64\native\onnxruntime.lib"
$dll = Join-Path $destination "runtimes\win-x64\native\onnxruntime.dll"

if ((Test-Path -LiteralPath $header) -and (Test-Path -LiteralPath $library) -and (Test-Path -LiteralPath $dll)) {
    Write-Host "ONNX Runtime $version is already restored."
    exit 0
}

$tempNupkg = Join-Path $env:TEMP "$package.$version.nupkg"
$tempZip = Join-Path $env:TEMP "$package.$version.zip"

try {
    Write-Host "Downloading pinned ONNX Runtime $version from NuGet..."
    Invoke-WebRequest -Uri $uri -OutFile $tempNupkg -UseBasicParsing
    Copy-Item -LiteralPath $tempNupkg -Destination $tempZip -Force

    if (Test-Path -LiteralPath $destination) {
        Remove-Item -LiteralPath $destination -Recurse -Force
    }
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Expand-Archive -LiteralPath $tempZip -DestinationPath $destination -Force

    foreach ($required in @($header, $library, $dll)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "The NuGet package is missing a required file: $required"
        }
    }

    Write-Host "ONNX Runtime $version restored to $destination"
}
finally {
    Remove-Item -LiteralPath $tempNupkg, $tempZip -Force -ErrorAction SilentlyContinue
}
