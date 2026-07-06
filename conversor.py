import os
from PIL import Image

LANGUAGE_ROOT = "language"
BASE_RESOLUTION = "1920x1080"
TARGET_RESOLUTIONS = ["1600x900", "1366x768"]


def resolution_size(res: str) -> tuple[int, int]:
    w, h = res.split("x")
    return int(w), int(h)


BASE_W, BASE_H = resolution_size(BASE_RESOLUTION)


def convert_image(src_path: str, dst_path: str, target_w: int) -> None:
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    scale = target_w / BASE_W  # mesma escala em x e y, já que a proporção (16:9) é igual
    with Image.open(src_path) as img:
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        resized = img.resize(new_size, Image.LANCZOS)
        resized.save(dst_path)


def convert_language(language_folder: str) -> int:
    base_path = os.path.join(LANGUAGE_ROOT, language_folder, BASE_RESOLUTION)
    if not os.path.isdir(base_path):
        return 0

    count = 0
    for target_res in TARGET_RESOLUTIONS:
        target_w, _ = resolution_size(target_res)
        target_root = os.path.join(LANGUAGE_ROOT, language_folder, target_res)

        for dirpath, _dirnames, filenames in os.walk(base_path):
            rel_dir = os.path.relpath(dirpath, base_path)
            dest_dir = target_root if rel_dir == "." else os.path.join(target_root, rel_dir)

            for filename in filenames:
                if not filename.lower().endswith(".png"):
                    continue
                src_path = os.path.join(dirpath, filename)
                dst_path = os.path.join(dest_dir, filename)
                convert_image(src_path, dst_path, target_w)
                count += 1

    return count


def main() -> None:
    if not os.path.isdir(LANGUAGE_ROOT):
        print(f"Pasta '{LANGUAGE_ROOT}' não encontrada. Rode este script na raiz do projeto.")
        return

    total = 0
    for language_folder in sorted(os.listdir(LANGUAGE_ROOT)):
        if not os.path.isdir(os.path.join(LANGUAGE_ROOT, language_folder)):
            continue
        gerados = convert_language(language_folder)
        if gerados:
            print(f"{language_folder}: {gerados} arquivo(s) gerado(s) em {len(TARGET_RESOLUTIONS)} resolução(ões).")
        else:
            print(f"{language_folder}: nenhuma pasta '{BASE_RESOLUTION}' encontrada, pulando.")
        total += gerados

    print(f"Concluído. Total de arquivos gerados: {total}.")


if __name__ == "__main__":
    main()