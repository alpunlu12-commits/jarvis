import os
import ast
from pathlib import Path
import argparse

def analyze_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        functions = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                docstring = ast.get_docstring(node)
                functions.append({
                    "name": node.name,
                    "docstring": docstring or "Belgeleme bulunmamaktadır."
                })
        return functions
    except Exception as e:
        print(f"⚠️ {file_path} dosyası analiz edilemedi: {e}")
        return []

def walk_directory(dir_path):
    for root, dirs, files in os.walk(dir_path):
        relative_path = Path(root).relative_to(dir_path)
        project_structure.append(f"## {relative_path}")
        for file in files:
            if file.endswith(".py"):
                file_path = Path(root) / file
                functions = analyze_file(file_path)
                if functions:
                    project_structure.append(f"### {file}")
                    for func in functions:
                        project_structure.append(
                            f"- **{func['name']}**\n  > {func['docstring']}"
                        )
        for dir in dirs:
            walk_directory(Path(root) / dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Projeyi analiz ederek map.md dosyası oluşturur.")
    parser.add_argument("project_dir", help="Analiz edilecek proje klasörünün yolu.")
    parser.add_argument("--exclude", default="Jules", help="Hariç bırakılacak klasör (varsayılan: Jules).")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).expanduser()
    map_file = project_dir / "map.md"
    project_structure = []

    if not project_dir.exists():
        print(f"❌ '{args.project_dir}' klasörü bulunamadı.")
        exit(1)

    walk_directory(project_dir)

    try:
        with open(map_file, "w", encoding="utf-8") as f:
            f.write("# Jarvis Proje Haritası\n\n")
            f.write("\n".join(project_structure))
        print(f"✅ '{map_file}' başarıyla oluşturuldu.")
    except Exception as e:
        print(f"❌ '{map_file}' oluşturulamadı: {e}")
