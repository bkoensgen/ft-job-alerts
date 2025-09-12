import sys


def main():
    # Allow running without installing the package
    sys.path.insert(0, "src")
    from ft_job_alerts.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    main()

