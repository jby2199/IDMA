"""Entry point for the template app."""

from app.core.logic import add  # Example usage


def main() -> None:
    print("Template app running — example add:", add(2, 3)) # Example usage


if __name__ == "__main__": # 이 코드가 있으면 main() 함수가 직접 실행될 때만 호출됩니다.
    main()
