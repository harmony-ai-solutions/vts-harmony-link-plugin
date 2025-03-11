@echo off
setlocal

REM ----------------------------------------------------------------------------
REM 1. Download micromamba (win-64) if not present
REM ----------------------------------------------------------------------------
IF NOT EXIST "micromamba.exe" (
    echo Downloading micromamba for Windows...
    curl.exe -L -o micromamba.exe ^
        https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64
)

REM ----------------------------------------------------------------------------
REM 2. Create env (if missing), specifying conda-forge for Python 3.12
REM ----------------------------------------------------------------------------
IF NOT EXIST "env" (
    echo Creating local environment with Python 3.12 from conda-forge...
    micromamba.exe create -y -p "%CD%\env" -c conda-forge python=3.12
) ELSE (
    echo Environment already exists. Skipping creation.
)

REM ----------------------------------------------------------------------------
REM 3. Install/Update your pip requirements
REM ----------------------------------------------------------------------------
echo Installing/Updating pip requirements from requirements.txt...
micromamba.exe run -p "%CD%\env" python -m pip install --upgrade pip
micromamba.exe run -p "%CD%\env" python -m pip install -r requirements.txt

REM ----------------------------------------------------------------------------
REM 4. Run the application
REM ----------------------------------------------------------------------------
echo Launching the application...
micromamba.exe run -p "%CD%\env" python main.py

endlocal
