import os
import subprocess

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

package_name = "ratelimit"


def get_version(package: str = package_name) -> str:
    """
    Return version.
    """
    _globals: dict = {}
    with open(os.path.join(here, package, "__version__.py")) as f:
        exec(f.read(), _globals)

    return _globals["__version__"]


os.chdir(here)
subprocess.check_call(f"poetry version {get_version()}", shell=True)
subprocess.check_call(
    f"git add {package_name}/__version__.py pyproject.toml", shell=True
)
subprocess.check_call(f'git commit -m "v{get_version()}"', shell=True)
subprocess.check_call("git push", shell=True)
subprocess.check_call("git tag v{0}".format(get_version()), shell=True)
subprocess.check_call("git push --tags", shell=True)
