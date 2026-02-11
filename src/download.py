import argparse

from downloader import download_rutube


def parse_args():
    parser = argparse.ArgumentParser(description="Download Rutube video")
    parser.add_argument("url", help="Rutube video URL")
    parser.add_argument("--out", default="data", help="Output directory (default: data)")
    return parser.parse_args()


def main():
    args = parse_args()
    path = download_rutube(args.url, output_dir=args.out)
    print(f"Saved to {path}")


if __name__ == "__main__":
    main()
