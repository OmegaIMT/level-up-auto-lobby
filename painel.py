import os
import sys
import tkinter as tk

# Caminho do arquivo temporário de status (ficará na mesma pasta)
STATUS_FILE = "panel_status.txt"

def ler_status_atual():
    """Lê o arquivo de texto apenas se ele existir e atualiza a tela."""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, "r") as f:
                linhas = f.read().splitlines()
                if len(linhas) >= 3:
                    partidas = linhas[0].strip()
                    max_rehost = linhas[1].strip()
                    ciclos = linhas[2].strip()
                    
                    # Atualiza os textos na interface
                    label_rehost.config(text=f"re-host = {partidas}/{max_rehost}")
                    label_ciclos.config(text=f"ciclos = {ciclos}")
        except Exception:
            pass # Ignora erros de leitura simultânea para não travar

def monitorar_arquivo_leve():
    """Verifica se o arquivo mudou. Consumo de CPU insignificante."""
    ler_status_atual()
    # Verifica a cada 800ms (ajuste ideal para ser rápido e não gastar CPU)
    root.after(800, monitorar_arquivo_leve)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("Painel Overlay")
    
    # Configurações de transparência e fixação (Sem bordas)
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", 0.80)
    root.configure(bg="black")

    # Posicionamento no canto superior direito
    largura_painel, altura_painel = 160, 55
    largura_tela = root.winfo_screenwidth()
    pos_x = largura_tela - largura_painel - 20
    pos_y = 20
    root.geometry(f"{largura_painel}x{altura_painel}+{pos_x}+{pos_y}")

    # Textos estilo Hacker / Prompt
    label_rehost = tk.Label(root, text="re-host = 0/0", fg="#00FF00", bg="black", font=("Consolas", 11, "bold"), anchor="w")
    label_rehost.pack(fill="x", padx=10, pady=(5, 0))

    label_ciclos = tk.Label(root, text="ciclos = 0", fg="#00FF00", bg="black", font=("Consolas", 11, "bold"), anchor="w")
    label_ciclos.pack(fill="x", padx=10, pady=(0, 5))

    # Inicializa o monitoramento inteligente
    monitorar_arquivo_leve()
    root.mainloop()