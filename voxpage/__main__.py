import sys


def _run(argv: list[str]) -> int:
    if not argv or argv == ["--gui-self-test"]:
        try:
            import wx  # noqa: F401
        except ImportError:
            print("L'interface graphique nécessite wxPython : pip install \"voxpage[gui]\".", file=sys.stderr)
            return 1
        from voxpage import gui

        return gui.self_test() if argv else gui.run()
    from voxpage.cli import main

    return main(argv)


if __name__ == "__main__":
    sys.exit(_run(sys.argv[1:]))
