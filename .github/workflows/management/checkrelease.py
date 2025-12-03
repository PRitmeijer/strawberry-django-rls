import os

from .releasefile import InvalidReleaseFileError, parse_release_file
from .utils import PATHS


def main() -> None:
    with open(os.environ["GITHUB_OUTPUT"], "w") as f:  # noqa: PTH123
        if not PATHS.RELEASE_FILE.exists():
            f.write("status=Release file doesn't exist")
        else:
            try:
                contents = PATHS.RELEASE_FILE.read_text("utf-8")
                if not contents.strip():
                    f.write("status=Release file is empty")
                else:
                    parse_release_file(contents)
                    f.write(f"status={''}")
            except InvalidReleaseFileError:
                f.write("status=Release file is invalid or missing release type")


if __name__ == "__main__":
    main()