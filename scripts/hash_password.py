import sys

from app.web.auth import hash_password


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/hash_password.py <password>")
        raise SystemExit(1)
    print(hash_password(sys.argv[1]))


if __name__ == "__main__":
    main()

