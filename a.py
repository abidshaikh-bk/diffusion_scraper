import os
from pathlib import Path

def generate_tree(directory: Path, prefix: str = ""):
    entries = sorted(directory.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    tree_lines = []

    for index, entry in enumerate(entries):
        connector = "└── " if index == len(entries) - 1 else "├── "
        tree_lines.append(prefix + connector + entry.name)

        if entry.is_dir():
            extension = "    " if index == len(entries) - 1 else "│   "
            tree_lines.extend(generate_tree(entry, prefix + extension))

    return tree_lines


def create_markdown_tree(target_directory: str, output_file: str = "directory_structure.md"):
    path = Path(target_directory)

    if not path.exists() or not path.is_dir():
        print("Invalid directory path.")
        return

    tree = [f"# Directory Structure for `{path.resolve()}`\n"]
    tree.append("```")
    tree.append(path.name)
    tree.extend(generate_tree(path))
    tree.append("```")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(tree))

    print(f"Markdown file created: {output_file}")


if __name__ == "__main__":
    directory = input("Enter directory path: ").strip()
    create_markdown_tree(directory)