import os

from .releasefile import InvalidReleaseFileError, parse_release_file
from .utils import PATHS


def main() -> None:
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:  # noqa: PTH123
        if not PATHS.RELEASE_FILE.exists():
            f.write("status=no_release_file\n")
        else:
            try:
                contents = PATHS.RELEASE_FILE.read_text("utf-8")
                if not contents.strip():
                    f.write("status=empty_file\n")
                else:
                    parse_release_file(contents)
                    f.write("status=ready\n")  # Ready to release
            except InvalidReleaseFileError:
                f.write("status=invalid_file\n")


if __name__ == "__main__":
    main()