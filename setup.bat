@echo off
:: Garante que o terminal entenda acentos corretamente (padrão UTF-8)
chcp 65001 > nul

echo ============================================================
echo      INSTALADOR DE DEPENDÊNCIAS - BOT DOTA 2
echo ============================================================
echo.

:: 1. Verifica se o Python está instalado no sistema
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] O Python não foi encontrado no seu sistema!
    echo Por favor, instale o Python antes de continuar.
    echo ATENÇÃO: Marque a opção "Add Python to PATH" no instalador.
    echo.
    pause
    exit /b
)

echo [1/3] Python detectado com sucesso.
echo ------------------------------------------------------------

:: 2. Atualiza o PIP (Gerenciador de pacotes)
echo [2/3] Atualizando o gerenciador de pacotes (pip)...
python -m pip install --upgrade pip
echo.
echo ------------------------------------------------------------

:: 3. Instala as bibliotecas obrigatórias do projeto
echo [3/3] Instalando as bibliotecas necessárias para o Bot...
echo.

:: Se houver o arquivo requirements.txt, usa ele. Se não, instala direto pelos nomes.
if exist requirements.txt (
    pip install -r requirements.txt
) else (
    pip install pyautogui keyboard opencv-python
)

echo.
echo ============================================================
echo   TUDO PRONTO! Seu projeto está configurado para rodar.
echo ============================================================
echo.
pause