import sys


def main():
    # Allow running without installing the package
    sys.path.insert(0, "src")
    from ft_job_alerts.gui import main as gui_main

    gui_main(None)


if __name__ == "__main__":
    main()

