import os
from ayon_core.addon import AYONAddon, IHostAddon, IPluginPaths

from .version import __version__

CINEMA4D_ADDON_ROOT = os.path.dirname(os.path.abspath(__file__))


def get_config_module_paths(app):
    """Return `g_additionalModulePath` entries from Cinema 4D's `config.txt`.

    The file lives in `<install>/resource/config.txt`. On macOS the
    executable sits inside the app bundle, hence the parent folder search.
    """
    executable = app.find_executable()
    if not executable:
        return []

    folder = os.path.dirname(str(executable))
    for _ in range(4):
        config_path = os.path.join(folder, "resource", "config.txt")
        if os.path.isfile(config_path):
            break
        folder = os.path.dirname(folder)
    else:
        return []

    paths = []
    with open(config_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            key, sep, value = line.strip().partition("=")
            if sep and key.strip().lower() == "g_additionalmodulepath":
                paths.extend(p.strip() for p in value.split(";"))
    return [p for p in paths if p]


class Cinema4DAddon(AYONAddon, IHostAddon, IPluginPaths):
    name = "cinema4d"
    version = __version__
    host_name = "cinema4d"

    def get_publish_plugin_paths(self, host_name):
        """Publish plugins that run without Cinema 4D.

        Registered in the Cinema 4D session and in the Deadline publish job,
        which runs `AYON_HOST_NAME` = cinema4d without the application. The
        plugins must not import `c4d` or `ayon_cinema4d.api`.
        """
        if host_name != self.host_name:
            return []
        return [
            os.path.join(CINEMA4D_ADDON_ROOT, "plugins", "publish_shared")
        ]

    def get_loader_action_plugin_paths(self, host_name=None):
        """Generic Loader / Browser actions, also in the tray Loader."""
        return [os.path.join(CINEMA4D_ADDON_ROOT, "plugins", "load_actions")]

    def get_launch_hook_paths(self, app):
        if app.host_name != self.host_name:
            return []
        return [os.path.join(CINEMA4D_ADDON_ROOT, "hooks")]

    def add_implementation_envs(self, env, app):
        # Set default values if are not already set via settings
        defaults = {"AYON_LOG_NO_COLORS": "1"}
        for key, value in defaults.items():
            if not env.get(key):
                env[key] = value

        # Register the startup `ayon_cinema4d.pyp`
        startup_path = os.path.join(CINEMA4D_ADDON_ROOT, "startup")
        new_g_module_path = [startup_path]

        path_key = "g_additionalModulePath"
        if os.name == "nt":
            path_key = path_key.upper()

        # Windows env names are case-insensitive, but the dict is not: a
        # 'g_additionalModulePath' from the application settings next to our
        # key would end up twice in the process environment and one of them
        # would win. Merge every spelling into one key.
        paths = []
        for key in [k for k in env if k.lower() == path_key.lower()]:
            paths.extend((env.pop(key) or "").split(os.pathsep))

        # The environment variable replaces `g_additionalModulePath` from
        # the application's `config.txt`, so its paths are carried over.
        paths.extend(get_config_module_paths(app))
        for path in paths:
            if not path:
                continue

            norm_path = os.path.normpath(path)
            if norm_path not in new_g_module_path:
                new_g_module_path.append(norm_path)

        env[path_key] = os.pathsep.join(new_g_module_path)

    def get_workfile_extensions(self):
        return [".c4d"]
