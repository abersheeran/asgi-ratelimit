import os

here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

package_name = 'example'  # TODO Custom package name


def get_version(package: str = package_name) -> str:
    """
    Return version.
    """
    _globals: dict = {}
    with open(os.path.join(here, package, "__version__.py")) as f:
        exec(f.read(), _globals)

    return _globals["__version__"]


os.chdir(here)
os.system(f"poetry version {get_version()}")
os.system(f"git add {package_name}/__version__.py pyproject.toml")
os.system(f'git commit -m "v{get_version()}"')
os.system("git push")
os.system(f"poetry publish --build")
os.system("git tag v{0}".format(get_version()))
os.system("git push --tags")
