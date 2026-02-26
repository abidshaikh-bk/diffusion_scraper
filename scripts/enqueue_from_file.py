from app.platforms.registry import PlatformRegistry


def read_urls(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def main():
    registry = PlatformRegistry.from_yaml()

    urls = read_urls("inputs/seed_urls.txt")

    allowed = [u for u in urls if registry.is_allowed(u)]
    rejected = [u for u in urls if not registry.is_allowed(u)]

    print(f"Total URLs: {len(urls)}")
    print(f"Allowed: {len(allowed)}")
    print(f"Rejected: {len(rejected)}")

    if rejected:
        print("\nRejected URLs:")
        for r in rejected:
            print("-", r)


if __name__ == "__main__":
    main()